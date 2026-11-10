# SPDX-License-Identifier: MIT

"""Editable import of 3D viewer projects (0.3.0): the round trip viewer project -> editable project -> XML and
configuration must give the same model, formulas and unknown content; formulas, upload under a viewer name."""

import copy
import json
import os
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from app import demos, geom, project as proj, xmlgen, xmlimport, xmleval, zone
from app.core import Core
from app.fake import FakeBus, demo_stl
from app.framework.web import HttpError
from app.storage import Conflict, ProjectStore
from app.viewer import FakeViewer

SHARED = "/media/sf_Claude_TEest"


def shared_example(label, zip_rel, json_rel):
    zp, jp = os.path.join(SHARED, zip_rel), os.path.join(SHARED, json_rel)
    if not (os.path.isfile(zp) and os.path.isfile(jp)):
        return None

    def load():
        with zipfile.ZipFile(zp) as z:
            files = {os.path.basename(i.filename): z.read(i) for i in z.infolist() if not i.is_dir()}
        with open(jp, "rb") as f:
            cfg = json.loads(f.read().decode("utf-8-sig"))
        return files, cfg
    return load


def examples():
    out = {}
    for name, loader in demos.catalog().items():
        if name.startswith("Demo"):
            out[name] = (lambda l=loader: (lambda r: (r["files"], r["configuration"]))(l()))
    for label, z, j in (("Scara Sort", "Scara Sort/Model.zip", "Scara Sort/Scara Sort.json"),
                        ("Delta_Ori_Sort", "Delta_Ori_Sort/Model.zip", "Delta_Ori_Sort/Delta_Ori_Sort.json"),
                        ("L10409A_Gantry original", "Robot Problem/Model.zip", "Robot Problem/Model/L10409A_Gantry.json"),
                        ("L10409A_Gantry Model_baked", "Robot Problem/Model_baked/Model.zip", "Robot Problem/Model_baked/L10409A_Gantry.json")):
        loader = shared_example(label, z, j)
        if loader:
            out[label] = loader
    return out


def xml_of(files):
    name = next(f for f in files if f.lower().endswith(".xml"))
    return files[name].decode("utf-8-sig")


def sig(el):
    """(tag, name, children signatures) of the elements (comments ignored)."""
    return (el.tag, el.get("name"), [sig(c) for c in el if isinstance(c.tag, str)])


def pairs(a, b, out=None):
    """Paired elements of two trees with the same signature."""
    out = [] if out is None else out
    out.append((a, b))
    ka, kb = [c for c in a if isinstance(c.tag, str)], [c for c in b if isinstance(c.tag, str)]
    assert len(ka) == len(kb)
    for x, y in zip(ka, kb):
        pairs(x, y, out)
    return out


def same_value(x, y):
    if x == y:
        return True
    try:
        fx, fy = float(x), float(y)
    except ValueError:
        return False
    return abs(fx - fy) <= 1e-9 * max(1.0, abs(fx), abs(fy))


def mat_close(a, b, tol_t=0.01, tol_r=1e-6):
    return all(abs(a[i] - b[i]) <= (tol_t if i % 4 == 3 else tol_r) for i in range(16))


def imported_project(files, cfg, name="Imp"):
    conv = xmlimport.convert(xml_of(files), cfg, list(files))
    p = conv["project"]
    p["name"] = name
    p["viewer_name"] = "Orig"
    return proj.validate(p), conv


class RoundTripTest(unittest.TestCase):

    def check_round_trip(self, label, files, cfg):
        orig_xml = xml_of(files)
        p, conv = imported_project(files, cfg)
        self.assertEqual(conv["report"]["dropped"], [], label)
        new_xml = xmlgen.build_xml(p)
        a, b = ET.fromstring(orig_xml), ET.fromstring(new_xml)
        # (b) the same structure by name: axes, parts, tools, frames; no wrapper transforms
        self.assertEqual(sig(a), sig(b), label)
        if 'name="Mounting"' not in orig_xml:
            self.assertNotIn('name="Mounting"', new_xml)            # no wrapper transform is added
        def kinds(root):
            out = {"axes": [], "parts": [], "tools": [], "frames": []}
            for el in root.iter():
                if el.tag == "axis":
                    out["axes"].append(el.get("name"))
                elif el.tag == "geometry":
                    out["tools" if el.get("objtype") == "tool" else "parts"].append(el.get("name"))
                elif el.tag == "transform":
                    kids = [c for c in el if isinstance(c.tag, str)]
                    if not (len(kids) == 1 and kids[0].tag == "geometry"):
                        out["frames"].append(el.get("name"))
            return {k: sorted(v) for k, v in out.items()}
        self.assertEqual(kinds(a), kinds(b), label)
        # the editor's tree has the same numbers
        counts = conv["report"]["counts"]
        k = kinds(a)
        self.assertEqual((counts["axes"], counts["parts"], counts["tools"], counts["frames"]),
                         (len(k["axes"]), len(k["parts"]), len(k["tools"]), len(k["frames"])), label)
        # (d) every attribute of every element comes back (numbers equal, text unchanged), geo in any case
        for x, y in pairs(a, b):
            self.assertEqual(set(x.attrib), set(y.attrib), (label, x.tag, x.get("name")))
            for key, v in x.attrib.items():
                if key == "geo":
                    self.assertEqual(v.lower(), y.get(key).lower())
                elif key == "initialvalue":
                    self.assertTrue(mat_close([float(t) for t in v.split(",")], [float(t) for t in y.get(key).split(",")], 1e-9, 1e-9))
                else:
                    self.assertTrue(same_value(v, y.get(key)), (label, x.tag, x.get("name"), key, v, y.get(key)))
        # (c) bindings and ExpressionScripts, character for character
        cfg2 = xmlgen.configuration(p)
        want = {e["ModelAxisName"]: e for e in cfg["ConfiguredAxis"]}
        got = {e["ModelAxisName"]: e for e in cfg2["ConfiguredAxis"]}
        self.assertEqual(want, got, label)
        self.assertEqual({k: v for k, v in cfg.items() if k not in ("ConfiguredAxis", "TrackId")},
                         {k: v for k, v in cfg2.items() if k != "ConfiguredAxis"}, label)
        # (a) the same world matrices for 20 random poses, raw axis values (formulas not applied)
        rnd = random.Random(7)
        axes = [x for x in a.iter("axis")]
        for _ in range(20):
            values = {x.get("name"): rnd.uniform(float(x.get("minvalue") or -100), float(x.get("maxvalue") or 100)) for x in axes}
            e1, e2 = xmleval.evaluate(orig_xml, values), xmleval.evaluate(new_xml, values)
            self.assertEqual(len(e1["geometry"]), len(e2["geometry"]))
            for g1, g2 in zip(e1["geometry"], e2["geometry"]):
                self.assertEqual((g1["name"], g1["objtype"]), (g2["name"], g2["objtype"]))
                self.assertTrue(mat_close(g1["matrix"], g2["matrix"]), (label, g1["name"]))
            self.assertEqual(set(e1["axes"]), set(e2["axes"]))
            for n, x1 in e1["axes"].items():
                x2 = e2["axes"][n]
                self.assertTrue(mat_close(x1["parent"], x2["parent"]) and mat_close(x1["world"], x2["world"]), (label, n))
                self.assertTrue(all(abs(u - v) < 1e-6 for u, v in zip(x1["dir"], x2["dir"])))
                if x1["pivot"] is not None:
                    pw1, pw2 = geom.apply(x1["parent"], x1["pivot"]), geom.apply(x2["parent"], x2["pivot"])
                    self.assertTrue(all(abs(u - v) <= 0.01 for u, v in zip(pw1, pw2)), (label, n))
        return p

    def test_round_trip_all_examples(self):
        ex = examples()
        self.assertIn("Demo Gantry", ex)
        for label, loader in ex.items():
            with self.subTest(label):
                files, cfg = loader()
                self.check_round_trip(label, files, cfg)

    def test_shared_examples_are_covered_when_present(self):
        names = set(examples())
        if os.path.isdir(SHARED + "/Robot Problem/Model_baked"):
            self.assertIn("L10409A_Gantry Model_baked", names)
        if os.path.isdir(SHARED + "/Scara Sort"):
            self.assertIn("Scara Sort", names)

    def test_no_wrapper_for_imported_projects(self):
        files, cfg = demos.gantry_demo()["files"], demos.gantry_demo()["configuration"]
        p, _ = imported_project(files, cfg)
        self.assertNotIn('"Mounting"', xmlgen.build_xml(p))
        self.assertEqual(p["root"], "none")

    def test_mapping_rules(self):
        files, cfg = demos.gantry_demo()["files"], demos.gantry_demo()["configuration"]
        p, conv = imported_project(files, cfg)
        by = {n["name"]: n for n, _ in ((n, 0) for n in xmlgen.walk(p["tree"]))}
        self.assertEqual(by["ViewTransform"]["kind"], "frame")
        self.assertEqual(by["GantryTransform"]["kind"], "frame")
        self.assertEqual(by["XBeam"]["kind"], "part")
        self.assertEqual(by["XBeam"]["transform_name"], "BeamGeo")              # the transform's name is kept
        self.assertEqual(len(by["XBeam"]["matrix"]), 16)
        self.assertEqual(by["Tool"]["kind"], "tool")
        self.assertTrue(by["Camera"]["bare"])                                   # a geometry directly in an axis
        self.assertEqual(by["XBeam"]["mesh"], "beam")
        self.assertEqual(p["meshes"]["beam"]["file"], "beam.stl")               # stored under its real file name
        self.assertIn('geo="beam.stl"', xmlgen.build_xml(p))                    # was Beam.STL
        self.assertEqual(by["X"]["formula"], "2250 - value")
        self.assertEqual(by["X"]["binding"], "AxisX")
        self.assertEqual(p["machine_data"]["attrs"]["version"], "1.9")
        self.assertEqual(len(p["machine_data"]["xml_extra"]), 1)                # view_transform kept

    def test_delta_keeps_unknown_attributes_and_comments(self):
        ex = examples()
        if "Delta_Ori_Sort" not in ex:
            self.skipTest("shared folder not available")
        files, cfg = ex["Delta_Ori_Sort"]()
        p, conv = imported_project(files, cfg)
        ax = {n["name"]: n for n in xmlgen.walk(p["tree"]) if n["kind"] == "axis"}
        self.assertEqual(ax["_r1h1"]["xattrs"]["customdata"], "assignKin(Delta,joint-1-2b)")
        self.assertEqual(ax["_r1h2"]["xattrs"]["supports_spinning"], "True")
        self.assertEqual(ax["DeltaRot1"]["xattrs"]["channelId"], "0")
        self.assertEqual(ax["DeltaRot1"]["xattrs"]["rotationAxisRolloverEnabled"], "False")
        xml = xmlgen.build_xml(p)
        self.assertIn("Extension for ellbow hinge arm 1", xml)                  # comments are kept
        self.assertIn("Adapted machine model created by a program", xml)        # also the one before the root
        self.assertTrue(conv["report"]["kept"])
        self.assertEqual(conv["report"]["dropped"], [])

    def test_unknown_elements_are_kept_and_text_is_reported(self):
        xml = """<machine_definition><machine_data name="M" units="metric"><extra a="1"/></machine_data>
          <transform name="T" initialvalue="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1"><geometry name="G" objtype="geometry" geo="A.stl" colour="red"><note>x</note></geometry></transform>
          <foo bar="2"><baz/></foo><!-- hello --></machine_definition>"""
        conv = xmlimport.convert(xml, None, ["a.stl"])
        p = conv["project"]
        self.assertEqual(conv["report"]["dropped"], [])
        p["name"] = "X"
        out = xmlgen.build_xml(proj.validate(p))
        self.assertIn('<foo bar="2">', out)
        self.assertIn("<!-- hello -->", out)
        self.assertIn('<note>x</note>', out)
        self.assertIn('colour="red"', out)
        self.assertIn('<extra a="1" />', out.replace("<extra a=\"1\"/>", '<extra a="1" />'))
        bad = xml.replace("<foo", "stray text <foo")
        self.assertTrue(xmlimport.convert(bad, None, ["a.stl"])["report"]["dropped"])
        with self.assertRaises(xmlimport.ImportProblem):
            xmlimport.convert('<machine_definition><transform name="T"/></machine_definition>', None, [])
        with self.assertRaises(xmlimport.ImportProblem):
            xmlimport.convert('<!DOCTYPE x><machine_definition/>', None, [])

    def test_missing_mesh_is_kept_as_a_reference(self):
        xml = ('<machine_definition><transform name="T" initialvalue="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1">'
               '<geometry name="G" objtype="geometry" geo="gone.stl"/></transform></machine_definition>')
        conv = xmlimport.convert(xml, None, [])
        self.assertEqual(conv["report"]["missing_meshes"], ["gone.stl"])
        conv["project"]["name"] = "X"
        p = proj.validate(conv["project"])
        gen = xmlgen.generate(p, lambda f: (_ for _ in ()).throw(KeyError(f)))
        self.assertEqual(gen["missing"], ["gone.stl"])

    def test_orphan_bindings_and_extras_are_kept(self):
        files, cfg = demos.gantry_demo()["files"], copy.deepcopy(demos.gantry_demo()["configuration"])
        cfg["ConfiguredAxis"].append({"ModelAxisName": "Nowhere", "ConnectionType": "datalayerAxes", "DatalayerNode": "AxisQ", "ExpressionScript": "value + 1"})
        cfg["ConfiguredAxis"][0]["Extra"] = {"k": 1}
        cfg["ToolNodes"] = {"deletion": {"useDataLayerNode": True}}
        p, conv = imported_project(files, cfg)
        out = xmlgen.configuration(p)
        self.assertEqual({e["ModelAxisName"]: e for e in out["ConfiguredAxis"]}, {e["ModelAxisName"]: e for e in cfg["ConfiguredAxis"]})
        self.assertEqual(out["ToolNodes"], cfg["ToolNodes"])
        self.assertNotIn("TrackId", out)
        self.assertTrue(conv["report"]["notes"])

    def test_edit_changes_only_that(self):
        files, cfg = demos.gantry_demo()["files"], demos.gantry_demo()["configuration"]
        p, _ = imported_project(files, cfg)
        before_xml, before_cfg = xmlgen.build_xml(p), xmlgen.configuration(p)
        q = copy.deepcopy(p)
        nodes = {n["name"]: n for n in xmlgen.walk(q["tree"])}
        nodes["Y"]["formula"] = "1500 - value"
        nodes["GantryTransform"]["matrix"][3] += 25.0
        q = proj.validate(q)
        after_xml, after_cfg = xmlgen.build_xml(q), xmlgen.configuration(q)
        diff = [(x.get("name"), k) for x, y in pairs(ET.fromstring(before_xml), ET.fromstring(after_xml))
                for k in set(x.attrib) | set(y.attrib) if x.get(k) != y.get(k)]
        self.assertEqual(diff, [("GantryTransform", "initialvalue")])
        changed = [e["ModelAxisName"] for e, f in zip(before_cfg["ConfiguredAxis"], after_cfg["ConfiguredAxis"]) if e != f]
        self.assertEqual(changed, ["Y"])
        self.assertEqual(after_cfg["ConfiguredAxis"][1]["ExpressionScript"], "1500 - value")


class FormulaTest(unittest.TestCase):

    def setUp(self):
        p = proj.new_project("F", "config")
        p["meshes"] = {}
        p["tree"] = [{"kind": "axis", "id": "a", "name": "A", "type": "translation", "direction": [1, 0, 0], "binding": "AxisX"}]
        self.p = p

    def test_default_and_written_unchanged(self):
        v = proj.validate(self.p)
        self.assertEqual(v["tree"][0]["formula"], "value")
        self.assertEqual(xmlgen.configuration(v)["ConfiguredAxis"][0]["ExpressionScript"], "value")
        self.p["tree"][0]["formula"] = " 2250 -  value "
        self.assertEqual(xmlgen.configuration(proj.validate(self.p))["ConfiguredAxis"][0]["ExpressionScript"], " 2250 -  value ")

    def test_validation(self):
        for bad in ("", "   ", "a\nb", "x" * 201, 5):
            self.p["tree"][0]["formula"] = bad
            with self.assertRaises(ValueError, msg=repr(bad)):
                proj.validate(self.p)
        self.p["tree"][0]["formula"] = "x" * 200
        proj.validate(self.p)

    def test_zone_check_warns_about_formulas(self):
        p = proj.validate({"name": "Z", "kinematic": {"name": "Gantry", "type": "Cartesian_XYZ", "axes": [{"name": "AxisX", "dir": "+"}]},
                           "meshes": {}, "tree": [
                               {"kind": "axis", "id": "a", "name": "A", "type": "translation", "direction": [1, 0, 0], "binding": "AxisX",
                                "formula": "value - 5", "children": [{"kind": "tool", "id": "t", "name": "T", "position": [0, 0, 0]}]}]})
        res = zone.check(p)
        row = [r for r in res["rows"] if r["name"] == "Formulas"]
        self.assertEqual(len(row), 1)
        self.assertFalse(row[0]["ok"])
        p["tree"][0]["formula"] = "value"
        self.assertEqual([r for r in zone.check(p)["rows"] if r["name"] == "Formulas"], [])


class CoreImportTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = ProjectStore(os.path.join(self.dir.name, "cfg"), os.path.join(self.dir.name, "common"))
        self.viewer = FakeViewer(demos=True)
        bus = FakeBus()
        self.core = Core(self.store, lambda t: bus, lambda t: self.viewer, log=lambda m: None, cache_root=os.path.join(self.dir.name, "vc"))

    def tearDown(self):
        self.dir.cleanup()

    def test_import_creates_a_normal_project(self):
        r = self.core.import_viewer("Demo Gantry", "G2", "common", False, "t")
        p = r["project"]
        self.assertEqual((p["name"], p["location"], p["viewer_name"]), ("G2", "common", "Demo Gantry"))
        self.assertEqual(r["report"]["counts"], {"axes": 5, "parts": 6, "tools": 1, "frames": 3})
        self.assertEqual(sorted(self.store.mesh_sizes("G2")), ["beam.stl", "cube.stl", "floor.stl"])
        self.assertIn('name="Demo Gantry"', self.core.xml("G2"))                 # machine_data as it was
        self.assertNotIn("import-tmp", os.listdir(self.dir.name))                # the temp folder is gone
        self.assertEqual(self.core.view, None)                                   # the read-only cache is not touched
        with self.assertRaises(Conflict):
            self.core.import_viewer("Demo Gantry", "g2", "config", False, "t")   # names are unique, any case
        with self.assertRaises(HttpError) as c:
            self.core.import_viewer("No such", "N", "config", False, "t")
        self.assertEqual(c.exception.status, 404)

    def test_drops_need_a_confirmation(self):
        files = demos.gantry_demo()["files"]
        files["Demo Gantry.xml"] = files["Demo Gantry.xml"].replace(b"<transform name=\"FloorGeo\"", b"stray <transform name=\"FloorGeo\"", 1)
        self.viewer.store["Dirty"] = {"files": files, "configuration": None}
        with self.assertRaises(HttpError) as c:
            self.core.import_viewer("Dirty", "D", "config", False, "t")
        self.assertEqual((c.exception.status, c.exception.code), (409, "DROPS"))
        self.assertIn("stray", str(c.exception))
        self.assertEqual(self.store.list(), [])
        self.core.import_viewer("Dirty", "D", "config", True, "t")
        self.assertEqual(len(self.store.list()), 1)

    def test_upload_back_and_as_new_name(self):
        self.core.import_viewer("Demo Gantry", "G2", "config", False, "t")
        with self.assertRaises(HttpError) as c:
            self.core.upload("G2", "t", False)
        self.assertEqual(c.exception.code, "EXISTS")
        self.assertEqual(str(c.exception), "Replaces Demo Gantry in the 3D viewer: its files are replaced, the axis bindings are sent "
                                           "again and the library picture is redrawn.")
        r = self.core.upload("G2", "t", True)
        self.assertEqual((r["viewer_name"], r["replaced"], r["bound_axes"]), ("Demo Gantry", True, 4))
        self.assertEqual(self.viewer.log[-2:], [("create", "Demo Gantry"), ("configure", "Demo Gantry")])
        self.assertIn("Demo Gantry.xml", self.viewer.store["Demo Gantry"]["files"])
        self.assertEqual(self.viewer.store["Demo Gantry"]["configuration"]["ConfiguredAxis"][0]["ExpressionScript"], "2250 - value")
        with self.assertRaises(HttpError) as c:
            self.core.upload("G2", "t", False, "Demo Delta")
        self.assertEqual(c.exception.code, "NAME_TAKEN")
        r = self.core.upload("G2", "t", False, "Gantry Copy")
        self.assertEqual((r["viewer_name"], r["replaced"]), ("Gantry Copy", False))
        self.assertEqual(self.store.get("G2")["viewer_name"], "Gantry Copy")
        self.assertIn("Gantry Copy.xml", self.viewer.store["Gantry Copy"]["files"])
        self.assertEqual(len(self.viewer.store["Gantry Copy"]["configuration"]["ConfiguredAxis"]), 4)    # PUT after the POST
        with self.assertRaises(HttpError) as c:                                                           # now it replaces that one
            self.core.upload("G2", "t", False)
        self.assertIn("Replaces Gantry Copy", str(c.exception))

    def test_own_project_uploads_under_its_name(self):
        self.store.create("Own", "config")
        r = self.core.upload("Own", "t", False)
        self.assertEqual(r["viewer_name"], "Own")
        self.assertEqual(self.store.get("Own")["viewer_name"], "Own")

    def test_zone_fix_in_a_rotated_frame_uses_local_units(self):
        # the first axis sits in a frame turned 90 degrees about Z: the shift in the parent's frame is the world shift turned back
        p = proj.validate({"name": "R", "kinematic": {"name": "G", "type": "Cartesian_XY", "axes": [{"name": "AX", "dir": "+"}, {"name": "AY", "dir": "+"}]},
                           "meshes": {}, "root": "none", "tree": [
                               {"kind": "frame", "id": "f", "name": "F", "src": True, "matrix": geom.mul(geom.translation([0, 0, 0]), geom.rot3(geom.euler(0, 0, 90))),
                                "children": [
                                    {"kind": "axis", "id": "x", "name": "X", "type": "translation", "direction": [1, 0, 0], "binding": "AX", "children": [
                                        {"kind": "axis", "id": "y", "name": "Y", "type": "translation", "direction": [0, 1, 0], "binding": "AY", "children": [
                                            {"kind": "tool", "id": "t", "name": "T", "position": [100, 0, 0]}]}]}]}]})
        res = zone.check(p)
        self.assertAlmostEqual(res["shift"][1], 100, 6)                    # world: the local +X is world +Y
        fixed = zone.fix(p)
        mcs = [n for n in xmlgen.walk(fixed["tree"]) if n["kind"] == "axis"][0]["mcs_origin"]
        self.assertAlmostEqual(mcs[0], 100, 6)
        self.assertTrue(zone.check(fixed)["ok"] or all(r["ok"] for r in zone.check(fixed)["rows"] if r["name"] != "Right-handed"))


if __name__ == "__main__":
    unittest.main()
