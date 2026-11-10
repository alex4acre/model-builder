# SPDX-License-Identifier: MIT

"""Read-only view of existing 3D viewer projects: formula parser, safe extraction, analysis and warnings, zone check on
a viewed model (no web server; the REST routes are in test_app.py)."""

import io
import json
import os
import tempfile
import unittest
import zipfile

from app import demos, geom, viewanalysis, viewcache
from app.viewanalysis import analyse, decompose, parse_formula
from app.viewer import FakeViewer

SHARED = "/media/sf_Claude_TEest"
GANTRY = SHARED + "/Robot Problem"


def make_zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def codes(a, code=None):
    return [w for w in a["warnings"] if code is None or w["code"] == code]


class FormulaTest(unittest.TestCase):

    def test_understood_forms(self):
        cases = {"value": (1, 0), " value ": (1, 0), "-value": (-1, 0), "-  value": (-1, 0), "2250 - value": (-1, 2250),
                 "1500 - value ": (-1, 1500), "value + 5": (1, 5), "value - 90": (1, -90), "value - 2000": (1, -2000),
                 "2 * value": (2, 0), "value * 0.5": (0.5, 0), "value / 4": (0.25, 0), "10 + value": (1, 10),
                 "value - -5": (1, 5), "1.5e2 - value": (-1, 150), ".5*value": (0.5, 0), "value+3": (1, 3)}
        for text, want in cases.items():
            self.assertEqual(parse_formula(text), want, text)
        self.assertEqual(parse_formula(None), (1, 0))
        self.assertEqual(parse_formula(""), (1, 0))

    def test_not_understood_and_never_evaluated(self):
        for text in ["value * value", "value + other", "__import__('os').system('x')", "(value)", "value / 0", "sin(value)",
                     "value + 1 + 2", "VALUE", "2 - 3", "value -", "1e999 - value", "value ** 2", "value; 1"]:
            self.assertIsNone(parse_formula(text), text)


class DecomposeTest(unittest.TestCase):

    def test_round_trip(self):
        for rx, ry, rz in [(0, 0, 0), (10, 20, 30), (-90, 0, 45), (180, 30, -60), (0, -90, 0)]:
            r = geom.euler(rx, ry, rz)
            m = geom.mul(geom.translation([1, 2, 3]), geom.rot3(r))
            pos, rot, scale = decompose(m)
            back = geom.euler(*rot)
            self.assertTrue(all(abs(back[i][j] - r[i][j]) < 1e-6 for i in range(3) for j in range(3)), (rx, ry, rz, rot))
            self.assertEqual(pos, [1, 2, 3])
            self.assertEqual(scale, [1, 1, 1])

    def test_scale(self):
        pos, rot, scale = decompose([2.7, 0, 0, 100, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
        self.assertEqual((pos, rot, scale), ([100, 0, 0], [0, 0, 0], [2.7, 1, 1]))


class ExtractTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = os.path.join(self.tmp.name, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def test_flat_layout(self):
        r = viewcache.extract(make_zip({"a.xml": "<x/>", "b.STL": b"123", "c.json": "{}", "note.txt": "x"}), self.dest)
        self.assertEqual(sorted(r["files"]), ["a.xml", "b.STL", "c.json"])
        self.assertTrue(any("note.txt" in w for w in r["warnings"]))
        self.assertEqual(r["json"]["c.json"], {})

    def test_package_layout(self):
        inner = make_zip({"P.xml": "<x/>", "m.stl": b"1"})
        r = viewcache.extract(make_zip({"Model.zip": inner, "P.json": json.dumps({"ConfiguredAxis": []}), "thumbnail.png": "data:image/png;base64,AAAA"}), self.dest)
        self.assertEqual(sorted(r["files"]), ["P.json", "P.xml", "m.stl", "thumbnail.png"])
        self.assertIn("ConfiguredAxis", r["json"]["P.json"])

    def test_traversal_and_absolute_paths_are_refused(self):
        r = viewcache.extract(make_zip({"../evil.stl": b"x", "/abs/evil2.stl": b"x", "a/../../evil3.stl": b"x", "C:\\evil4.stl": b"x",
                                        "..\\evil5.stl": b"x", "sub/ok.stl": b"x"}), self.dest)
        self.assertEqual(list(r["files"]), ["ok.stl"])
        self.assertEqual(len(r["warnings"]), 5)
        self.assertEqual(sorted(os.listdir(self.dest)), ["ok.stl"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "evil.stl")))

    def test_size_limits(self):
        data = make_zip({"a.stl": b"x" * 3000, "b.stl": b"x" * 3000})
        with self.assertRaises(viewcache.ExtractError):
            viewcache.extract(data, self.dest, viewcache._Budget(5000, 100000))        # total
        with self.assertRaises(viewcache.ExtractError):
            viewcache.extract(data, self.dest, viewcache._Budget(100000, 2000))        # one file
        viewcache.extract(data, self.dest, viewcache._Budget(7000, 4000))

    def test_declared_size_is_not_trusted(self):
        # a zip whose entries are bigger than they claim cannot be built with zipfile; the stream is counted anyway
        z = make_zip({"a.stl": b"\0" * 200000})
        with self.assertRaises(viewcache.ExtractError):
            viewcache.extract(z, self.dest, viewcache._Budget(100000, 100000))

    def test_not_a_zip(self):
        with self.assertRaises(viewcache.ExtractError):
            viewcache.extract(b"hello", self.dest)

    def test_case_insensitive_lookup(self):
        viewcache.extract(make_zip({"Beam.stl": b"x", "other.STL": b"y"}), self.dest)
        self.assertTrue(viewcache.find_file(self.dest, "beam.STL").endswith("Beam.stl"))
        self.assertTrue(viewcache.find_file(self.dest, "OTHER.stl").endswith("other.STL"))
        self.assertIsNone(viewcache.find_file(self.dest, "../x"))
        self.assertIsNone(viewcache.find_file(self.dest, "missing.stl"))

    def test_open_project_replaces_the_cache(self):
        v = FakeViewer()
        v.store["One"] = demos.delta_demo()
        v.store["Two"] = demos.gantry_demo()
        root = os.path.join(self.tmp.name, "cache")
        a = viewcache.open_project(v, "One", root)
        self.assertEqual(os.listdir(root), ["One"])
        b = viewcache.open_project(v, "Two", root)
        self.assertEqual(os.listdir(root), ["Two"])
        self.assertEqual((a["name"], b["name"]), ("One", "Two"))
        self.assertEqual(len(b["axes"]), 5)

    def test_package_layout_takes_json_from_the_package(self):
        inner = make_zip({"P.xml": demos.delta_demo()["files"]["Demo Delta.xml"], "cube.stl": b"x"})
        cfg = demos.delta_demo()["configuration"]
        v = FakeViewer()
        v.store["P"] = {"files": {"Model.zip": inner, "P.json": json.dumps(cfg).encode()}, "configuration": None}
        r = viewcache.open_project(v, "P", os.path.join(self.tmp.name, "c"))
        self.assertEqual(len(r["configuration"]["ConfiguredAxis"]), 2)
        self.assertTrue(any(w["code"] == "extract" and "package" in w["text"] for w in r["warnings"]))
        self.assertEqual([a["binding"] for a in r["axes"] if not a["passive"]], ["ScaraRot1", "ScaraRot3"])


XML = """<machine_definition>
  <transform name="T" initialvalue="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1">
    <axis name="A" type="translation" x="1" y="0" z="0" minvalue="0" maxvalue="10" initial_value="0">
      <axis name="A" type="translation" x="0" y="1" z="0">
        <geometry name="g1" objtype="geometry" geo="Part.STL" clrr="1" clrg="0" clrb="0" alpha="0" />
        <geometry name="g2" objtype="geometry" geo="missing.stl" clrr="1" clrg="0" clrb="0" alpha="0" />
      </axis>
    </axis>
    <axis name="J" customdata="assignKin(K,joint-1-1)" type="rotation" x="0" y="0" z="1" rzx="1" rzy="2" rzz="3" />
    <axis name="B" type="rotation" x="0" y="0" z="1" rzx="0" rzy="0" rzz="0" />
  </transform>
</machine_definition>"""


class AnalysisTest(unittest.TestCase):

    def test_synthetic_warnings(self):
        cfg = {"ConfiguredAxis": [{"ModelAxisName": "A", "DatalayerNode": "M1", "ExpressionScript": "10 - value"},
                                  {"ModelAxisName": "Ghost", "DatalayerNode": "M9", "ExpressionScript": "value"}]}
        a = analyse(XML, cfg, ["part.stl"])
        by = {c: codes(a, c) for c in ("expression", "unbound", "binding_without_axis", "assignkin", "missing_mesh", "no_tool", "duplicate_axis")}
        self.assertEqual([w["axis"] for w in by["expression"]], ["A", "A"])      # both axes of that name
        self.assertEqual([w["axis"] for w in by["unbound"]], ["B"])
        self.assertEqual([w["axis"] for w in by["binding_without_axis"]], ["Ghost"])
        self.assertEqual([w["axis"] for w in by["assignkin"]], ["J"])
        self.assertEqual(len(by["missing_mesh"]), 1)
        self.assertIn("missing.stl", by["missing_mesh"][0]["text"])
        self.assertEqual(len(by["no_tool"]), 1)
        self.assertEqual([w["axis"] for w in by["duplicate_axis"]], ["A"])
        self.assertIn("MCS", by["expression"][0]["text"])
        # case-insensitive mesh check: Part.STL is found as part.stl
        self.assertTrue(next(g for g in _flat(a["structure"]) if g["name"] == "g1")["present"])
        self.assertEqual(a["tools"], 0)

    def test_structure_and_axis_data(self):
        a = analyse(XML, None, None)
        self.assertEqual(codes(a, "missing_mesh"), [])                           # files unknown: no check
        self.assertEqual(len(codes(a, "no_configuration")), 1)
        axes = {x["name"]: x for x in a["axes"] if x["name"] != "A"}
        self.assertEqual(axes["J"]["pivot"], [1, 2, 3])
        self.assertTrue(axes["J"]["passive"])
        self.assertIsNone(axes["B"]["binding"] or None)
        kinds = [n["kind"] for n in _flat(a["structure"])]
        self.assertEqual(kinds.count("axis"), 4)
        self.assertEqual(kinds[0], "transform")

    def test_value_script_and_binding_are_ok(self):
        cfg = {"ConfiguredAxis": [{"ModelAxisName": n, "DatalayerNode": "M" + n, "ExpressionScript": "value"} for n in ["A", "A2", "B"]]}
        a = analyse(XML.replace("<axis name=\"A\" type=\"translation\" x=\"0\" y=\"1\"", "<axis name=\"A2\" type=\"translation\" x=\"0\" y=\"1\""), cfg, ["part.stl", "missing.stl"])
        self.assertEqual(sorted(w["code"] for w in a["warnings"]), ["assignkin", "no_tool"])

    def test_bad_xml(self):
        for text in ["<machine_definition", "<other/>", '<!DOCTYPE x [<!ENTITY a "b">]><machine_definition/>']:
            with self.assertRaises(ValueError):
                analyse(text)


def _flat(nodes):
    for n in nodes:
        yield n
        yield from _flat(n.get("children") or [])


def _load(rel_zip, rel_json):
    z, j = os.path.join(SHARED, rel_zip), os.path.join(SHARED, rel_json)
    with zipfile.ZipFile(z) as zf:
        files = {os.path.basename(i.filename): zf.read(i) for i in zf.infolist() if not i.is_dir()}
    xml = next(v for k, v in files.items() if k.endswith(".xml")).decode("utf-8-sig")
    with open(j, "rb") as f:
        cfg = json.loads(f.read().decode("utf-8-sig"))
    return xml, cfg, list(files)


@unittest.skipUnless(os.path.exists(SHARED + "/Scara Sort/Model.zip") and os.path.exists(SHARED + "/Delta_Ori_Sort/Model.zip")
                     and os.path.exists(GANTRY + "/Model.zip"), "shared-folder examples not readable")
class ExampleTest(unittest.TestCase):

    def test_scara_sort(self):
        a = analyse(*_load("Scara Sort/Model.zip", "Scara Sort/Scara Sort.json"))
        self.assertEqual([x["name"] for x in a["axes"]], ["C1", "C2", "Z", "C3"])
        self.assertEqual([x["binding"] for x in a["axes"]], ["ScaraRot1", "ScaraRot2", "ScaraLin1", "ScaraRot3"])
        self.assertEqual(a["warnings"], [])
        self.assertEqual(a["tools"], 1)
        self.assertEqual(a["axes"][1]["pivot"], [220, 0, 0])

    def test_delta_ori_sort(self):
        a = analyse(*_load("Delta_Ori_Sort/Model.zip", "Delta_Ori_Sort/Delta_Ori_Sort.json"))
        passive = [x["name"] for x in a["axes"] if x["passive"]]
        self.assertEqual(len(passive), 13)
        self.assertEqual(sorted(w["code"] for w in a["warnings"]), ["assignkin"] * 13)
        self.assertEqual(sorted(x["binding"] for x in a["axes"] if not x["passive"]), ["DeltaRot1", "DeltaRot2", "DeltaRot3", "DeltaRot4", "DeltaRot5"])
        self.assertEqual(sorted(x["name"] for x in a["axes"] if not x["passive"]), ["DeltaRot1", "DeltaRot2", "DeltaRot3", "OriRot1", "OriRot2"])

    def test_gantry_original_and_baked(self):
        orig = analyse(*_load("Robot Problem/Model.zip", "Robot Problem/Model/L10409A_Gantry.json"))
        self.assertEqual(sorted(w["axis"] for w in codes(orig, "expression")), ["Camera_Z", "R", "X", "Y", "Z"])
        self.assertEqual([x["formula"] for x in orig["axes"] if x["name"] == "X"], [[-1.0, 2250.0]])
        self.assertEqual([x["formula"] for x in orig["axes"] if x["name"] == "Y"], [[-1.0, 1500.0]])     # "1500 - value " with a space
        self.assertEqual(codes(orig, "missing_mesh"), [])
        baked_files = os.path.join(GANTRY, "Model_baked")
        with open(baked_files + "/L10409A_Gantry.xml", encoding="utf-8-sig") as f:
            bxml = f.read()
        with open(baked_files + "/L10409A_Gantry.json", encoding="utf-8-sig") as f:
            bcfg = json.load(f)
        baked = analyse(bxml, bcfg, orig and os.listdir(baked_files))
        self.assertEqual(codes(baked, "expression"), [])
        self.assertEqual(baked["warnings"], [])
        # the STL names differ in case from the files on disk (.STL / .stl): no missing mesh in either
        self.assertEqual(codes(analyse(bxml, bcfg, [f.upper() for f in os.listdir(baked_files)]), "missing_mesh"), [])
        # a deleted file is reported
        self.assertEqual(len(codes(analyse(bxml, bcfg, [f for f in os.listdir(baked_files) if f != "CAMERA.STL"]), "missing_mesh")), 1)

    def test_zone_check_on_the_viewed_gantry(self):
        kin = [("G1_X", 1.0), ("G1_Y", 1.0), ("G1_Z", 1.0)]
        xml, cfg, _ = _load("Robot Problem/Model.zip", "Robot Problem/Model/L10409A_Gantry.json")
        warn = viewanalysis.zone_check(xml, cfg, "Cartesian_XYZ", kin)
        self.assertTrue(warn["checked"])
        self.assertFalse(warn["ok"])
        self.assertFalse(warn["rows"][0]["ok"])
        self.assertTrue(all(abs(a - b) < 0.01 for a, b in zip(warn["shift"], [2250, 1500, -2000])), warn["shift"])
        with open(GANTRY + "/Model_baked/L10409A_Gantry.xml", encoding="utf-8-sig") as f:
            bxml = f.read()
        with open(GANTRY + "/Model_baked/L10409A_Gantry.json", encoding="utf-8-sig") as f:
            bcfg = json.load(f)
        ok = viewanalysis.zone_check(bxml, bcfg, "Cartesian_XYZ", kin)
        self.assertTrue(ok["ok"], ok["rows"])
        # unbound kinematic axis and a non-Cartesian type
        self.assertFalse(viewanalysis.zone_check(bxml, bcfg, "Cartesian_XYZ", [("Nope", 1.0)] * 3)["ok"])
        self.assertFalse(viewanalysis.zone_check(bxml, bcfg, "Scara_LinearAxisFlange", kin)["checked"])


class DemoTest(unittest.TestCase):

    def test_demo_gantry(self):
        d = demos.gantry_demo()
        a = analyse(d["files"]["Demo Gantry.xml"].decode(), d["configuration"], list(d["files"]))
        self.assertEqual(sorted(w["axis"] for w in codes(a, "expression")), ["R", "X"])
        self.assertEqual([w["axis"] for w in codes(a, "unbound")], ["Camera_Z"])
        self.assertEqual(codes(a, "missing_mesh"), [])                              # Beam.STL is stored as beam.stl
        self.assertEqual(a["tools"], 1)
        names = [n["name"] for n in _flat(a["structure"]) if n["kind"] == "transform"]
        self.assertIn("ToolTransform", names)

    def test_demo_delta(self):
        d = demos.delta_demo()
        a = analyse(d["files"]["Demo Delta.xml"].decode(), d["configuration"], list(d["files"]))
        self.assertEqual([w["axis"] for w in codes(a, "assignkin")], ["_r1h1"])

    def test_fake_viewer_lists_demos(self):
        v = FakeViewer(demos=True)
        self.assertIn("Demo Gantry", v.projects())
        self.assertIn("Demo Delta", v.projects())
        self.assertTrue(zipfile.ZipFile(io.BytesIO(v.project_zip("Demo Gantry"))).namelist())
        self.assertEqual(len(v.project_configuration("Demo Gantry")["ConfiguredAxis"]), 4)
        self.assertEqual(FakeViewer().projects(), [])


if __name__ == "__main__":
    unittest.main()
