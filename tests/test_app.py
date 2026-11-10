# SPDX-License-Identifier: MIT

"""Unit tests against the simulated ctrlX (no Data Layer library needed):  python3 -m unittest -q
(tests/framework/ tests the framework copy the app ships)."""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import app
from app import web
from app.core import ConfigError, Core
from app.fake import FakeBus
from app.framework.web import TcpServer

BASE = "/" + app.NAME


class CoreTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.core = Core(os.path.join(self.dir.name, app.NAME), FakeBus(), log=lambda m: None)
        self.path = self.core.settings.path

    def tearDown(self):
        self.core.stop()
        self.dir.cleanup()

    def test_defaults_without_a_file(self):
        self.assertEqual(self.core.config["setpoint"], 0.0)

    def test_update_saves(self):
        self.core.update_config({"setpoint": 2})
        with open(self.path) as f:
            self.assertEqual(json.load(f)["setpoint"], 2.0)

    def test_bad_values_are_refused(self):
        for bad in ({"setpoint": "x"}, {"setpoint": True}, {"cycle_s": 0}, {"other": 1}):
            with self.assertRaises(ConfigError):
                self.core.update_config(bad)

    def test_file_replaced_from_outside_is_reloaded(self):
        self.core.update_config({"setpoint": 1})
        with open(self.path, "w") as f:
            json.dump({"setpoint": 7.5, "note": "from a backup"}, f)
        self.assertTrue(self.core.settings.reload_if_changed())
        self.assertEqual(self.core.config["setpoint"], 7.5)


class WebTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        web.core = Core(cls.dir.name, FakeBus(), log=lambda m: None)
        web.RequestHandler.www_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "www")
        cls.server = TcpServer(("127.0.0.1", 0), web.RequestHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        web.core.stop()
        cls.dir.cleanup()

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=5) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def test_page_and_framework_files_are_served(self):
        for path in ("/", "/framework/ctrlx.js", "/framework/base.css", "/app.js"):
            with self.opener.open(self.base + BASE + path, timeout=5) as r:
                self.assertEqual(r.status, 200, path)

    def test_config_round_trip(self):
        self.assertEqual(self.call("PATCH", BASE + "/api/v1/config", {"setpoint": 3.5}), (200, web.core.config))
        self.assertEqual(self.call("GET", BASE + "/api/v1/config")[1]["setpoint"], 3.5)
        status, body = self.call("PATCH", BASE + "/api/v1/config", {"setpoint": "high"})
        self.assertEqual(status, 400)
        self.assertIn("setpoint", body["error"])

    def test_node_read_write(self):
        self.assertEqual(self.call("GET", BASE + "/api/v1/node?path=demo/flag"), (200, {"path": "demo/flag", "value": False}))
        self.assertEqual(self.call("PUT", BASE + "/api/v1/node?path=demo/flag", {"value": True})[1]["value"], True)
        status, body = self.call("GET", BASE + "/api/v1/node?path=no/such")
        self.assertEqual((status, body["code"]), (502, "DL_INVALID_ADDRESS"))


if __name__ == "__main__":
    unittest.main()
