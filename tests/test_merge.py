# SPDX-License-Identifier: MIT

"""0.5.0: what the viewer has is kept on re-upload (merge rules), customdata / Display ID round trip, the name rule of
"always visible"."""

import copy
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from app import customdata, demos, merge, project as proj, xmlgen, xmlimport
from app.core import Core
from app.fake import FakeBus
from app.framework.web import HttpError
from app.storage import ProjectStore
from app.viewer import FakeViewer, ViewerError

VAR = {"ModelAxisName": "A2", "ConnectionType": "datalayerVariable", "DatalayerNode": "", "DatalayerVariable": "plc/app/Application/sym/PLC_PRG/pos",
       "ExpressionScript": "value * 2"}


def axis(i, name, binding=""):
    return {"kind": "axis", "id": i, "name": name, "type": "translation", "direction": [1, 0, 0], "binding": binding, "children": []}


class MergeUnitTest(unittest.TestCase):

    def test_rules(self):
        app = {"ConfiguredAxis": [{"ModelAxisName": "A1", "ConnectionType": "datalayerAxes", "DatalayerNode": "X", "ExpressionScript": "value"},
                                  {"ModelAxisName": "Orphan", "ConnectionType": "datalayerAxes", "DatalayerNode": "Q", "ExpressionScript": "value"}],
               "ToolNodes": {"deletion": {"useDataLayerNode": False}}, "IsDemoModelDeleted": False}
        viewer = {"ConfiguredAxis": [{"ModelAxisName": "A1", "ConnectionType": "datalayerVariable", "DatalayerVariable": "v"}, VAR,
                                     {"ModelAxisName": "Gone", "ConnectionType": "datalayerVariable", "DatalayerVariable": "w"}],
                  "TrackId": "t-1", "SafeZones": [{"n": 1}], "GeometryProperties": [{"id": "G1"}], "ToolNodes": {"deletion": {"useDataLayerNode": True}}}
        cfg, rep = merge.merge_configuration(app, viewer, ["A1", "A2", "A3"], {"A1"}, {})
        by = {e["ModelAxisName"]: e for e in cfg["ConfiguredAxis"]}
        self.assertEqual(sorted(by), ["A1", "A2"])
        self.assertEqual(by["A1"]["DatalayerNode"], "X")                      # the app's binding wins
        self.assertEqual(by["A2"], VAR)                                      # the viewer's variable binding is kept
        self.assertEqual(rep["dropped"], ["Gone"])
        self.assertEqual(rep["kept_bindings"], ["A2"])
        self.assertNotIn("TrackId", cfg)
        self.assertEqual(cfg["SafeZones"], [{"n": 1}])
        self.assertEqual(cfg["GeometryProperties"], [{"id": "G1"}])
        self.assertEqual(cfg["ToolNodes"], {"deletion": {"useDataLayerNode": True}})
        self.assertEqual(sorted(rep["kept_settings"]), ["GeometryProperties", "SafeZones", "ToolNodes"])
        self.assertIs(cfg["IsDemoModelDeleted"], False)                      # the app's key stays when the viewer has none

    def test_entry_the_app_sent_is_dropped_when_unbound(self):
        sent = {"ModelAxisName": "A2", "ConnectionType": "datalayerAxes", "DatalayerNode": "Y", "ExpressionScript": "value"}
        viewer = {"ConfiguredAxis": [dict(sent, DatalayerVariable="")]}      # the viewer adds an empty key: still the same entry
        cfg, rep = merge.merge_configuration({"ConfiguredAxis": []}, viewer, ["A2"], set(), {"A2": sent})
        self.assertEqual(cfg["ConfiguredAxis"], [])
        self.assertEqual(rep["cleared"], ["A2"])
        changed = {"ConfiguredAxis": [dict(sent, DatalayerNode="Z")]}        # the user changed it in the viewer: kept
        cfg, rep = merge.merge_configuration({"ConfiguredAxis": []}, changed, ["A2"], set(), {"A2": sent})
        self.assertEqual(len(cfg["ConfiguredAxis"]), 1)


class MergeUploadTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = ProjectStore(os.path.join(self.dir.name, "cfg"), os.path.join(self.dir.name, "common"))
        self.viewer = FakeViewer()
        bus = FakeBus()
        self.core = Core(self.store, lambda t: bus, lambda t: self.viewer, log=lambda m: None, cache_root=os.path.join(self.dir.name, "vc"))
        self.store.create("P", "config")
        p = self.store.get("P")
        p["tree"] = [axis("a1", "A1", "AxisX"), axis("a2", "A2"), axis("a3", "A3")]
        self.store.put("P", p)

    def tearDown(self):
        self.dir.cleanup()

    def entries(self, name="P"):
        return {e["ModelAxisName"]: e for e in self.viewer.store[name]["configuration"]["ConfiguredAxis"]}

    def edit(self, fn):
        p = self.store.get("P")
        fn(p)
        self.store.put("P", p)

    def test_new_name_upload_is_as_before(self):
        r = self.core.upload("P", "t", False)
        self.assertEqual((r["replaced"], r["bound_axes"], r["kept_bindings"], r["dropped_bindings"]), (False, 1, [], []))
        cfg = self.viewer.store["P"]["configuration"]
        self.assertEqual(cfg, xmlgen.configuration(self.store.get("P")))
        self.assertEqual(r["kept_settings"], [])

    def test_viewer_settings_survive_a_second_upload(self):
        self.core.upload("P", "t", False)
        cfg = self.viewer.store["P"]["configuration"]
        cfg["ConfiguredAxis"].append(dict(VAR))
        cfg["ConfiguredAxis"].append({"ModelAxisName": "Old", "ConnectionType": "datalayerVariable", "DatalayerVariable": "x"})
        cfg["GeometryProperties"] = [{"displayId": "G1"}]
        cfg["SafeZones"] = [{"z": 1}]
        cfg["TrackId"] = "viewer-track"
        r = self.core.upload("P", "t", True)
        self.assertEqual(self.viewer.log, [("create", "P"), ("configure", "P"), ("create", "P"), ("configure", "P")])
        new = self.viewer.store["P"]["configuration"]
        self.assertEqual(sorted(self.entries()), ["A1", "A2"])
        self.assertEqual(self.entries()["A2"], VAR)
        self.assertEqual(self.entries()["A1"]["DatalayerNode"], "AxisX")
        self.assertEqual((new["GeometryProperties"], new["SafeZones"]), ([{"displayId": "G1"}], [{"z": 1}]))
        self.assertNotIn("TrackId", new)
        self.assertEqual((r["kept_bindings"], r["dropped_bindings"]), (["A2"], ["Old"]))
        self.assertTrue({"GeometryProperties", "SafeZones"} <= set(r["kept_settings"]))
        r = self.core.upload("P", "t", True)                   # and again: still there
        self.assertEqual(self.entries()["A2"], VAR)

    def test_binding_cleared_in_the_app_is_dropped(self):
        self.core.upload("P", "t", False)
        self.edit(lambda p: p["tree"][1].update(binding="AxisY"))          # bind A2 in the app, upload
        self.core.upload("P", "t", True)
        self.assertEqual(self.entries()["A2"]["DatalayerNode"], "AxisY")
        self.edit(lambda p: p["tree"][1].update(binding=""))               # clear it in the app
        r = self.core.upload("P", "t", True)
        self.assertNotIn("A2", self.entries())
        self.assertEqual(r["cleared_bindings"], ["A2"])
        self.edit(lambda p: p["tree"][1].update(binding="AxisY"))
        self.core.upload("P", "t", True)
        cfg = self.viewer.store["P"]["configuration"]
        for e in cfg["ConfiguredAxis"]:
            if e["ModelAxisName"] == "A2":
                e.update(ConnectionType="datalayerVariable", DatalayerNode="", DatalayerVariable="v")
        self.edit(lambda p: p["tree"][1].update(binding=""))
        self.core.upload("P", "t", True)
        self.assertEqual(self.entries()["A2"]["DatalayerVariable"], "v")   # changed in the viewer since: kept

    def test_removed_axis_is_dropped_and_reported(self):
        self.core.upload("P", "t", False)
        cfg = self.viewer.store["P"]["configuration"]
        cfg["ConfiguredAxis"].append(dict(VAR, ModelAxisName="A3"))
        self.edit(lambda p: p.update(tree=p["tree"][:2]))
        r = self.core.upload("P", "t", True)
        self.assertEqual(r["dropped_bindings"], ["A3"])
        self.assertNotIn("A3", self.entries())

    def test_get_failure_aborts_before_anything_is_sent(self):
        self.core.upload("P", "t", False)
        self.viewer.log.clear()
        self.viewer.fail_configuration = True
        with self.assertRaises(ViewerError) as c:
            self.core.upload("P", "t", True)
        self.assertIn("nothing was uploaded", str(c.exception))
        self.assertEqual(self.viewer.log, [])

    def test_replace_text_mentions_the_viewer_settings(self):
        self.core.upload("P", "t", False)
        with self.assertRaises(HttpError) as c:
            self.core.upload("P", "t", False)
        self.assertIn("visual effects", str(c.exception))
        self.assertIn("bindings", str(c.exception))

    def test_viewer_state_lists_unbound_axes(self):
        self.core.upload("P", "t", False)
        self.viewer.store["P"]["configuration"]["ConfiguredAxis"].append(dict(VAR))
        st = self.core.viewer_state("P", "t")
        self.assertEqual(st["bindings"]["A2"]["variable"], VAR["DatalayerVariable"])
        self.assertNotIn("A1", st["bindings"])


class CustomdataTest(unittest.TestCase):

    def test_parse_and_compose(self):
        self.assertEqual(customdata.parse("displayid(G1)"), "G1")
        self.assertEqual(customdata.parse("visible(always),;DisplayID( Part#1-a )"), "Part#1-a")
        self.assertEqual(customdata.parse("assignKin(K,joint-1-1)"), "")
        self.assertEqual(customdata.compose("", "G1"), "displayid(G1)")
        raw = "visible(always),; displayid( G1 ) ,;foo(bar)"
        self.assertEqual(customdata.compose(raw, "G1"), raw)                              # unchanged
        self.assertEqual(customdata.compose(raw, "G2"), "visible(always),;displayid(G2),;foo(bar)")
        self.assertEqual(customdata.compose(raw, ""), "visible(always),;foo(bar)")
        self.assertEqual(customdata.compose("foo(bar)", "G1"), "displayid(G1),;foo(bar)")
        self.assertEqual(customdata.compose("displayid(G1)", ""), "")
        self.assertEqual(customdata.other_entries(raw), ["visible(always)", "foo(bar)"])
        with self.assertRaises(ValueError):
            customdata.check_id("a b")

    def test_import_and_write_round_trip(self):
        xml = ('<machine_definition><transform name="F" initialvalue="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1" customdata="displayid(Grp),;visible(always)">'
               '<transform name="T" initialvalue="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1"><geometry name="P_active" objtype="geometry" geo="a.stl" '
               'customdata="foo,;displayid( G7 ),;visible(active)" /></transform></transform></machine_definition>')
        conv = xmlimport.convert(xml, None, ["a.stl"])
        conv["project"]["name"] = "X"
        p = proj.validate(conv["project"])
        frame = p["tree"][0]
        part = frame["children"][0]
        self.assertEqual((frame["display_id"], part["display_id"]), ("Grp", "G7"))
        self.assertEqual(frame["xattrs"]["customdata"], "displayid(Grp),;visible(always)")
        out = xmlgen.build_xml(p)
        self.assertIn('customdata="displayid(Grp),;visible(always)"', out)
        self.assertIn('customdata="foo,;displayid( G7 ),;visible(active)"', out)       # byte-identical when unchanged
        part["display_id"] = "G8"
        frame["display_id"] = ""
        out = xmlgen.build_xml(proj.validate(p))
        root = ET.fromstring(out)
        g = root.find(".//geometry")
        self.assertEqual(customdata.parse(g.get("customdata")), "G8")
        self.assertEqual(customdata.other_entries(g.get("customdata")), ["foo", "visible(active)"])
        self.assertEqual(root.find("transform").get("customdata"), "visible(always)")

    def test_own_project_writes_customdata_only_when_set(self):
        p = proj.validate({"name": "O", "meshes": {"m": {"file": "m.stl"}}, "tree": [
            {"kind": "part", "id": "p1", "name": "Housing", "mesh": "m", "display_id": "Hs"},
            {"kind": "part", "id": "p2", "name": "Plain", "mesh": "m"},
            {"kind": "frame", "id": "f1", "name": "Fr", "display_id": "Fd", "children": []}]})
        out = xmlgen.build_xml(p)
        self.assertEqual(out.count("customdata"), 2)
        self.assertIn('<geometry name="Housing" objtype="geometry" alpha="0" clrr="0.6" clrg="0.6" clrb="0.6" geo="m.stl" customdata="displayid(Hs)" />', out)
        self.assertIn('<transform name="Fr" initialvalue="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1" customdata="displayid(Fd)">', out)
        p["tree"][0]["display_id"] = "bad id"
        with self.assertRaises(ValueError):
            proj.validate(p)

    def test_unchanged_projects_stay_byte_identical(self):
        p = proj.validate({"name": "O", "meshes": {"m": {"file": "m.stl"}}, "tree": [{"kind": "part", "id": "p1", "name": "Housing", "mesh": "m"}]})
        self.assertNotIn("customdata", xmlgen.build_xml(p))
