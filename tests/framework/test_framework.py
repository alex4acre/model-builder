# SPDX-License-Identifier: MIT

"""Unit tests of the ctrlx-baseline framework (no Data Layer library needed). They come with the framework into
every app, so `python3 -m unittest` in an app also checks the framework copy it ships."""

import http.client
import http.server
import inspect
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from app.framework import appdata, runtime, web
from app.framework.bus import BusError, DatalayerBus
from app.framework.fakebus import FakeBus
from app.framework.rest import RestBus, problem


def public_methods(cls) -> set:
    return {n for n, f in inspect.getmembers(cls, inspect.isfunction) if not n.startswith("_")}


class InterfaceTest(unittest.TestCase):

    def test_fake_and_rest_have_the_interface_of_the_real_bus(self):
        real = public_methods(DatalayerBus)
        self.assertEqual(real - public_methods(FakeBus), set(), "missing in FakeBus")
        self.assertEqual(real - public_methods(RestBus), set(), "missing in RestBus")

    def test_bus_error_has_a_code(self):
        self.assertEqual(BusError("x").code, "DL_FAILED")
        self.assertEqual(BusError("x", "DL_TIMEOUT").code, "DL_TIMEOUT")


class FakeBusTest(unittest.TestCase):

    def setUp(self):
        self.bus = FakeBus({"a/flag": False, "a/pos": 1.5, "a/obj": {"x": 1}, "a/method": lambda args: args["n"] * 2})

    def test_browse_read_write(self):
        self.assertEqual(self.bus.browse(""), ["a"])
        self.assertEqual(self.bus.browse("a"), ["flag", "method", "obj", "pos"])
        self.bus.write("a/pos", 2)
        self.assertEqual(self.bus.read_typed("a/pos"), ("float64", 2.0))
        self.assertEqual(self.bus.read_typed("a/obj")[0], "flatbuffers")

    def test_errors_carry_codes(self):
        with self.assertRaises(BusError) as e:
            self.bus.read("no/such")
        self.assertEqual(e.exception.code, "DL_INVALID_ADDRESS")
        with self.assertRaises(BusError) as e:
            self.bus.write("a/flag", 1)
        self.assertEqual(e.exception.code, "DL_TYPE_MISMATCH")
        self.bus.readonly.add("a/flag")
        with self.assertRaises(BusError) as e:
            self.bus.write("a/flag", True)
        self.assertEqual(e.exception.code, "DL_PERMISSION_DENIED")

    def test_method_node_and_session(self):
        self.assertEqual(self.bus.read_args("a/method", {"n": 4}), 8)
        self.bus.denied.add("viewer")
        with self.bus.session("viewer") as b, self.assertRaises(BusError) as e:
            b.read("a/flag")
        self.assertEqual(e.exception.code, "DL_PERMISSION_DENIED")
        self.assertFalse(self.bus.read("a/flag"))           # the token ends with the session


class RestBusTest(unittest.TestCase):
    """RestBus against a stand-in for the ctrlX REST API."""

    @classmethod
    def setUpClass(cls):
        nodes = cls.nodes = {"a/flag": ("bool8", False), "a/pos": ("float64", 1.5)}
        cls.requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, status, obj):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                cls.requests.append(("GET", self.path, self.headers.get("Authorization")))
                path, _, query = self.path[len("/automation/api/v2/nodes/"):].partition("?")
                if query == "type=browse":
                    return self.answer(200, {"type": "arstring", "value": sorted({k.split("/")[1] for k in nodes})})
                if path not in nodes:
                    return self.answer(404, {"title": "DL_INVALID_ADDRESS", "detail": path})
                t, v = nodes[path]
                self.answer(200, {"type": t, "value": v})

            def do_PUT(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                cls.requests.append(("PUT", self.path, body))
                path = self.path[len("/automation/api/v2/nodes/"):]
                if self.headers.get("Authorization") == "Bearer viewer":
                    return self.answer(403, {"title": "Forbidden", "detail": "no permission"})
                nodes[path] = (body["type"], body["value"])
                self.answer(200, body)

        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.bus = RestBus(f"http://127.0.0.1:{cls.server.server_address[1]}", "dev")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_read_browse_write_in_the_node_type(self):
        self.assertEqual(self.bus.browse("a"), ["flag", "pos"])
        self.assertEqual(self.bus.read_typed("a/pos"), ("float64", 1.5))
        self.bus.write("a/pos", 3)
        self.assertEqual(self.requests[-1], ("PUT", "/automation/api/v2/nodes/a/pos", {"type": "float64", "value": 3}))
        self.assertIn(("GET", "/automation/api/v2/nodes/a/pos", "Bearer dev"), self.requests)

    def test_errors_carry_codes(self):
        with self.assertRaises(BusError) as e:
            self.bus.read("a/none")
        self.assertEqual(e.exception.code, "DL_INVALID_ADDRESS")
        with self.bus.session("viewer") as b, self.assertRaises(BusError) as e:
            b.write("a/flag", True)
        self.assertEqual(e.exception.code, "DL_PERMISSION_DENIED")

    def test_problem_details(self):
        self.assertEqual(problem(b'{"title": "DL_TIMEOUT", "detail": "slow"}', 500), ("DL_TIMEOUT - slow", "DL_TIMEOUT"))
        self.assertEqual(problem(b"plain text", 404), ("plain text", "DL_INVALID_ADDRESS"))


class Locked(Exception):
    pass


class Handler(web.ApiHandler):
    BASE = "/t"
    ROUTES = [("GET", r"/ok", "get_ok"), ("POST", r"/echo", "post_echo"), ("GET", r"/items/([^/]+)", "get_item"),
              ("GET", r"/fail/(\w+)", "get_fail"), ("GET", r"/whoami", "get_whoami"), ("GET", r"/file", "get_file"),
              ("POST", r"/ignore", "post_ignore")]
    ERRORS = ((Locked, 409),)
    loaded = 0

    def get_ok(self):
        self.send_json(200, {"ok": True})

    def post_echo(self):
        self.send_json(200, self.read_json(kind=None))

    def get_item(self, name):
        self.send_json(200, {"name": name})

    def get_fail(self, kind):
        raise {"value": ValueError("bad value"), "key": KeyError("no item"), "locked": Locked("locked"),
               "denied": BusError("read x: DL_PERMISSION_DENIED", "DL_PERMISSION_DENIED"),
               "bus": BusError("read x: DL_TIMEOUT", "DL_TIMEOUT"), "http": web.HttpError(418, "teapot", "TEA"),
               "bug": RuntimeError("bug")}[kind]

    def get_whoami(self):
        self.send_json(200, {"token": self.token()})

    def get_file(self):
        self.send_file(b"abc", "my file.txt", "text/plain")

    def post_ignore(self):
        self.no_content()

    def configuration_loaded(self):
        Handler.loaded += 1


class WebTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.www = tempfile.TemporaryDirectory()
        with open(os.path.join(cls.www.name, "index.html"), "w") as f:
            f.write("<title>t</title>")
        Handler.www_dir = cls.www.name
        cls.server = web.TcpServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_address[1]
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.www.cleanup()

    def call(self, method, path, body=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, headers=headers or {},
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with self.opener.open(req, timeout=5) as r:
                raw = r.read()
                return r.status, json.loads(raw) if r.headers.get("Content-Type") == "application/json" and raw else raw
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def test_routes_and_groups(self):
        self.assertEqual(self.call("GET", "/t/api/v1/ok"), (200, {"ok": True}))
        self.assertEqual(self.call("GET", "/t/api/v1/items/a%20b")[1], {"name": "a b"})
        self.assertEqual(self.call("GET", "/t/api/v1/nothing")[0], 404)
        self.assertEqual(self.call("DELETE", "/t/api/v1/ok")[0], 405)

    def test_error_mapping(self):
        expect = {"value": (400, None), "key": (404, None), "locked": (409, None), "denied": (403, "DL_PERMISSION_DENIED"),
                  "bus": (502, "DL_TIMEOUT"), "http": (418, "TEA"), "bug": (500, None)}
        for kind, (status, code) in expect.items():
            got_status, body = self.call("GET", f"/t/api/v1/fail/{kind}")
            self.assertEqual(got_status, status, kind)
            self.assertIn("error", body)
            self.assertEqual(body.get("code"), code, kind)

    def test_json_body_and_token(self):
        self.assertEqual(self.call("POST", "/t/api/v1/echo", [1, 2]), (200, [1, 2]))
        self.assertEqual(self.call("GET", "/t/api/v1/whoami")[0], 401)
        self.assertEqual(self.call("GET", "/t/api/v1/whoami", headers={"Authorization": "Bearer abc"}),
                         (200, {"token": "abc"}))

    def test_static_files_views_and_downloads(self):
        self.assertIn(b"<title>", self.call("GET", "/t/")[1])
        self.assertEqual(self.call("GET", "/t/tools")[0], 404)
        Handler.VIEWS = ("/tools",)
        self.assertIn(b"<title>", self.call("GET", "/t/tools")[1])
        self.assertEqual(self.call("GET", "/t/../etc/passwd")[0], 404)
        with self.opener.open(f"http://127.0.0.1:{self.port}/t/api/v1/file", timeout=5) as r:
            self.assertEqual(r.headers["Content-Disposition"], 'attachment; filename="my_file.txt"')

    def test_configuration_hooks(self):
        before = Handler.loaded
        self.assertEqual(self.call("POST", "/t/api/v1/admin/cfg/load", {"phase": "prepare"})[0], 204)
        self.assertEqual(self.call("POST", "/t/api/v1/admin/cfg/load", {"phase": "load"})[0], 204)
        self.assertEqual(Handler.loaded, before + 1)
        self.assertEqual(self.call("POST", "/t/api/v1/admin/cfg/save", {})[0], 204)

    def test_unread_body_does_not_break_the_next_request(self):
        """The ctrlX proxy reuses connections: a body the handler ignored must be drained."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", "/t/api/v1/ignore", body=b'{"x": 1}', headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        r.read()
        self.assertEqual(r.status, 204)
        conn.request("GET", "/t/api/v1/ok")
        r = conn.getresponse()
        self.assertEqual((r.status, json.loads(r.read())), (200, {"ok": True}))
        conn.close()


class AppDataTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "app", "config.json")

        def validate(d):
            out = {"n": 0, **d}
            if not isinstance(out["n"], int):
                raise ValueError('"n" must be a whole number')
            return out
        self.file = appdata.JsonFile(self.path, validate, log=lambda m: None)

    def tearDown(self):
        self.dir.cleanup()

    def test_defaults_then_atomic_update(self):
        self.assertEqual(self.file.data, {"n": 0})
        self.assertFalse(os.path.exists(self.path))
        self.file.update({"n": 2})
        with open(self.path) as f:
            self.assertEqual(json.load(f), {"n": 2})
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        with self.assertRaises(ValueError):
            self.file.update({"n": "x"})
        self.assertEqual(self.file.data, {"n": 2})

    def test_replaced_from_outside_is_reloaded_and_reported(self):
        self.file.update({"n": 1})
        self.assertFalse(self.file.reload_if_changed())
        seen = []
        self.file.listeners.append(seen.append)
        with open(self.path, "w") as f:
            json.dump({"n": 7}, f)
        self.assertTrue(self.file.reload_if_changed())
        self.assertEqual((self.file.data, seen), ({"n": 7}, [{"n": 7}]))

    def test_a_broken_file_gives_the_defaults(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("{broken")
        self.assertEqual(appdata.JsonFile(self.path, lambda d: {"n": 0, **d}, log=lambda m: None).data, {"n": 0})


class RuntimeTest(unittest.TestCase):

    def test_development_folders_and_settings(self):
        with tempfile.TemporaryDirectory() as src:
            os.environ["T_APP_DATA"] = os.path.join(src, "d")
            try:
                rt = runtime.Runtime("t-app", env="T_APP", port=12000, src=src, log=lambda m: None)
                self.assertFalse(rt.in_snap)
                self.assertEqual(rt.port, 12000)
                self.assertEqual(rt.data_dir(), os.path.join(src, "d"))
                self.assertTrue(os.path.isdir(rt.common_dir("esi")))
                self.assertEqual(rt.bundled("www"), os.path.join(src, "www"))
            finally:
                del os.environ["T_APP_DATA"]

    def test_fake_datalayer_and_main_loop(self):
        rt = runtime.Runtime("t-app", env="T_APP", port=0, src=".", log=lambda m: None)
        os.environ["T_APP_FAKE"] = "1"
        try:
            dl = rt.start_datalayer(fake=FakeBus)
        finally:
            del os.environ["T_APP_FAKE"]
        self.assertTrue(dl.fake)
        self.assertIs(dl.client(), dl.bus)
        calls, order = [], []
        rt.every(0.05, lambda: calls.append(1))
        rt.every(0.05, lambda: 1 / 0)                # logged, the loop goes on
        rt.at_stop(lambda: order.append("first added"))
        rt.at_stop(lambda: order.append("last added"))
        threading.Timer(0.5, rt.stopping.set).start()
        start = time.monotonic()
        rt.run()
        self.assertLess(time.monotonic() - start, 2)
        self.assertGreaterEqual(len(calls), 3)
        self.assertEqual(order, ["last added", "first added"])


if __name__ == "__main__":
    unittest.main()
