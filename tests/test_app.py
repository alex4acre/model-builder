# SPDX-License-Identifier: MIT

"""Unit tests of the REST API against the simulated ctrlX (no Data Layer library needed):  python3 -m unittest -q
(tests/framework/ tests the framework copy the app ships)."""

import http.client
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile

import app
from app import fake, web
from app.core import Core, error_types
from app.fake import FakeBus
from app.framework.web import TcpServer
from app.storage import ProjectStore
from app.viewer import FakeViewer

BASE = "/" + app.NAME
API = BASE + "/api/v1"
HEADERS = {"Authorization": "Bearer dev"}


class WebTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.viewer = FakeViewer()
        cls.store = ProjectStore(os.path.join(cls.dir.name, "cfg"), os.path.join(cls.dir.name, "common"))
        bus = FakeBus()
        web.core = Core(cls.store, lambda token: bus, lambda token: cls.viewer, log=lambda m: None)
        web.RequestHandler.www_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "www")
        cls.server = TcpServer(("127.0.0.1", 0), web.RequestHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.dir.cleanup()

    def setUp(self):
        for p in self.store.list():
            self.store.delete(p["name"])
        self.viewer.store.clear()
        self.viewer.log.clear()
        self.viewer.installed = True

    def raw(self, method, path, body=None, ctype="application/json"):
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={**HEADERS, "Content-Type": ctype})
        try:
            with self.opener.open(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def call(self, method, path, body=None):
        status, raw = self.raw(method, API + path, body)
        return status, json.loads(raw or b"null")

    def make_gantry(self, name="G", location="config"):
        self.assertEqual(self.call("POST", "/projects", {"name": name, "location": location})[0], 201)
        status, p = self.call("PUT", f"/projects/{name}/meshes/cube.stl?unit=mm", None)
        self.assertEqual(status, 400)                    # an empty body is not an STL
        status, p = self.call_raw_put(f"/projects/{name}/meshes/cube.stl?unit=mm", fake.demo_stl())
        self.assertEqual(status, 200)
        status, t = self.call("POST", f"/projects/{name}/from-kinematic", {"kinematic": "Gantry"})
        self.assertEqual(status, 200)
        p["tree"], p["kinematic"] = t["tree"], t["kinematic"]
        p["tree"][0]["children"][0]["children"][0]["children"].insert(0, {"kind": "part", "id": "p1", "name": "Head",
                                                                           "mesh": "cube", "colour": [0.5, 0.5, 0.5]})
        status, p = self.call("PUT", f"/projects/{name}", p)
        self.assertEqual(status, 200, p)
        return p

    def call_raw_put(self, path, data):
        status, raw = self.raw("PUT", API + path, data, "application/octet-stream")
        return status, json.loads(raw)

    def test_page_and_vendored_three_are_served(self):
        for path in ("/", "/framework/ctrlx.js", "/framework/ui.js", "/app.js", "/vendor/three/three.module.js",
                     "/vendor/three/jsm/loaders/STLLoader.js", "/vendor/three/jsm/controls/OrbitControls.js", "/vendor/three/LICENSE"):
            self.assertEqual(self.raw("GET", BASE + path)[0], 200, path)

    def test_projects_crud(self):
        self.assertEqual(self.call("POST", "/projects", {"name": "A", "location": "common"})[0], 201)
        self.assertEqual(self.call("POST", "/projects", {"name": "A", "location": "config"})[0], 409)
        self.assertEqual(self.call("POST", "/projects", {"name": "../A", "location": "config"})[0], 400)
        listing = self.call("GET", "/projects")[1]["projects"]
        self.assertEqual([(p["name"], p["location"]) for p in listing], [("A", "common")])
        self.assertEqual(self.call("POST", "/projects/A/rename", {"name": "B"})[1]["name"], "B")
        self.assertEqual(self.call("POST", "/projects/B/duplicate", {"name": "C"})[1]["location"], "common")
        self.assertEqual(self.call("POST", "/projects/B/move", {"location": "config"})[1]["location"], "config")
        self.assertEqual(self.call("GET", "/projects/Z")[0], 404)
        self.assertEqual(self.call("DELETE", "/projects/B")[0], 204)
        self.assertEqual(self.call("GET", "/projects/B")[0], 404)
        self.assertEqual(self.call("GET", "/storage")[1]["locations"][1]["in_backup"], False)

    def test_xml_package_and_zone_check(self):
        self.make_gantry()
        status, raw = self.raw("GET", API + "/projects/G/xml")
        self.assertEqual(status, 200)
        self.assertIn(b'<axis name="AxisX"', raw)
        self.assertIn(b'geo="cube.stl"', raw)
        status, raw = self.raw("GET", API + "/projects/G/package")
        z = zipfile.ZipFile(io.BytesIO(raw))
        self.assertEqual(sorted(z.namelist()), ["G.json", "Model.zip"])
        inner = zipfile.ZipFile(io.BytesIO(z.read("Model.zip")))
        self.assertEqual(sorted(inner.namelist()), ["G.xml", "cube.stl"])
        self.assertEqual(len(json.loads(z.read("G.json"))["ConfiguredAxis"]), 3)
        check = self.call("GET", "/projects/G/zone-check")[1]
        self.assertTrue(check["checked"])
        self.assertTrue(check["ok"])                     # tool at (0,0,0), parent at the origin
        p = self.call("GET", "/projects/G")[1]
        p["tree"][0]["children"][0]["children"][0]["children"][1]["position"] = [0, 0, -120]
        self.call("PUT", "/projects/G", p)
        self.assertFalse(self.call("GET", "/projects/G/zone-check")[1]["ok"])
        fixed = self.call("POST", "/projects/G/zone-fix")[1]
        self.assertTrue(fixed["check"]["ok"])
        self.assertEqual(fixed["project"]["tree"][0]["mcs_origin"], [0, 0, -120])

    def test_part_without_mesh_and_missing_mesh_file(self):
        self.make_gantry()
        status, body = self.call("DELETE", "/projects/G/meshes/cube.stl")
        self.assertEqual(status, 409)
        self.assertIn("Head", body["error"])

    def test_motion_lists(self):
        self.assertEqual(len(self.call("GET", "/motion/axes")[1]["axes"]), 7)
        self.assertEqual([k["name"] for k in self.call("GET", "/motion/kinematics")[1]["kinematics"]], ["Gantry", "Scara"])
        self.call("POST", "/projects", {"name": "A", "location": "config"})
        status, body = self.call("POST", "/projects/A/from-kinematic", {"kinematic": "Nope"})
        self.assertNotEqual(status, 200)

    def test_upload_to_viewer_configures_after_every_create(self):
        self.make_gantry()
        status, r = self.call("POST", "/projects/G/upload-to-viewer", {})
        self.assertEqual((status, r["replaced"], r["bound_axes"]), (200, False, 3))
        self.assertEqual(self.viewer.log, [("create", "G"), ("configure", "G")])
        self.assertEqual(len(self.viewer.store["G"]["configuration"]["ConfiguredAxis"]), 3)
        self.assertEqual(sorted(self.viewer.store["G"]["files"]), ["G.xml", "cube.stl"])
        status, r = self.call("POST", "/projects/G/upload-to-viewer", {})
        self.assertEqual((status, r["code"]), (409, "EXISTS"))
        self.assertEqual(len(self.viewer.log), 2)                      # nothing was sent
        status, r = self.call("POST", "/projects/G/upload-to-viewer?replace=1", {})
        self.assertEqual((status, r["replaced"]), (200, True))
        self.assertEqual(self.viewer.log[2:], [("create", "G"), ("configure", "G")])
        self.assertEqual(len(self.viewer.store["G"]["configuration"]["ConfiguredAxis"]), 3)
        self.assertTrue(self.call("GET", "/projects/G")[1]["extra"]["uploaded_at"])

    def test_viewer_not_installed(self):
        self.make_gantry()
        self.viewer.installed = False
        status, r = self.call("POST", "/projects/G/upload-to-viewer", {})
        self.assertEqual(status, 503)
        self.assertIn("not installed", r["error"])

    def test_body_limit_and_draining_on_a_kept_alive_connection(self):
        self.make_gantry()
        old = web.RequestHandler.MAX_MESH
        web.RequestHandler.MAX_MESH = 200_000
        try:
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            big = b"x" * 3_000_000
            c.request("PUT", API + "/projects/G/meshes/big.stl", body=big, headers={**HEADERS, "Content-Type": "application/octet-stream"})
            r = c.getresponse()
            self.assertEqual(r.status, 413)
            r.read()
            # the same connection must still work: the unread body was drained, not read as the next request
            c.request("GET", API + "/projects/G", headers=HEADERS)
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            r.read()
            # a rejected STL (invalid content) after reading the whole body, then a POST with an unused body
            c.request("PUT", API + "/projects/G/meshes/bad.stl", body=b"y" * 100_000, headers=HEADERS)
            r = c.getresponse()
            self.assertEqual(r.status, 400)
            r.read()
            c.request("POST", API + "/projects/G/zone-fix", body=b'{"unused": true}', headers=HEADERS)
            r = c.getresponse()
            r.read()
            c.request("GET", API + "/state", headers=HEADERS)
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            r.read()
            c.close()
        finally:
            web.RequestHandler.MAX_MESH = old

    def test_large_mesh_upload_within_limit(self):
        self.call("POST", "/projects", {"name": "L", "location": "config"})
        stl = fake.demo_stl()
        # pad a binary STL to ~12 MB with valid triangles
        tris = (12_000_000 - 84) // 50
        data = stl[:80] + tris.to_bytes(4, "little") + stl[84:134] * tris
        status, p = self.call_raw_put("/projects/L/meshes/large.stl?unit=inch", data)
        self.assertEqual(status, 200)
        self.assertEqual(p["meshes"]["large"]["unit"], "inch")
        self.assertEqual(len(self.raw("GET", API + "/projects/L/meshes/large.stl")[1]), len(data))

    def test_configuration_loaded_hook_bumps_generation(self):
        before = self.call("GET", "/projects")[1]["generation"]
        self.assertEqual(self.raw("POST", API + "/admin/cfg/load", {"phase": "load"})[0], 204)
        self.assertEqual(self.call("GET", "/projects")[1]["generation"], before + 1)


if __name__ == "__main__":
    unittest.main()
