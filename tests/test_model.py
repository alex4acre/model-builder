# SPDX-License-Identifier: MIT

"""Generator, forward kinematics, zone check, storage and kinematic import (no web server)."""

import copy
import os
import random
import tempfile
import unittest

from app import fake, geom, motion, project, storage, xmlgen, xmleval, zone
from app.fake import FakeBus

HERE = os.path.dirname(os.path.abspath(__file__))
GANTRY = "/media/sf_Claude_TEest/Robot Problem"


def axis(i, name, kind, direction, pivot=(0, 0, 0), rng=(-1000, 1000), children=(), **kw):
    return {"kind": "axis", "id": i, "name": name, "type": kind, "direction": list(direction), "pivot": list(pivot),
            "range": list(rng), "initial": 0, "offset": 0, "invert": False, "binding": kw.pop("binding", name),
            "children": list(children), **kw}


def part(i, name, mesh, colour=(0.6, 0.6, 0.6)):
    return {"kind": "part", "id": i, "name": name, "mesh": mesh, "colour": list(colour)}


def tool(i, pos, name="Tool"):
    return {"kind": "tool", "id": i, "name": name, "position": list(pos)}


def mesh(file, unit="mm", pos=(0, 0, 0), rot=(0, 0, 0)):
    return {"file": file, "unit": unit, "placement": {"position": list(pos), "rotation": list(rot)}}


def make(tree, name="T", meshes=None, **kw):
    return project.validate({"name": name, "meshes": meshes or {"cube": mesh("cube.stl")}, "tree": tree, **kw})


def close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class GeneratorTest(unittest.TestCase):

    def test_same_output_as_robot_configurator(self):
        # tests/data/rc_reference.xml was made with robot-configurator's build_xml for the equivalent spec
        p = make([part("1", "Base", "base", (0.5, 0.5, 0.5)),
                  axis("2", "A1", "rotation", (0, 0, 1), pivot=(10, 20, 0), rng=(-180, 180), children=[
                      part("3", "Arm", "arm", (1, 0.8235294, 0.05882353)),
                      axis("4", "A2", "translation", (1, 0, 0), rng=(0, 300), initial=5,
                           children=[tool("5", (300, 0, 50))])])],
                 name="Eq", meshes={"base": mesh("base.stl", pos=(10, 0, 0)), "arm": mesh("arm.stl")})
        with open(os.path.join(HERE, "data", "rc_reference.xml")) as f:
            self.assertEqual(xmlgen.build_xml(p), f.read())

    def test_mesh_unit_and_placement(self):
        p = make([part("1", "P", "m")], meshes={"m": mesh("m.stl", unit="inch", pos=(1, 2, 3), rot=(0, 0, 90))})
        ev = xmleval.evaluate(xmlgen.build_xml(p))
        m = ev["geometry"][0]["matrix"]
        self.assertTrue(close(geom.apply(m, [1, 0, 0]), [1, 2 + 25.4, 3], 1e-9))      # x -> y after Rz(90), scaled
        self.assertTrue(close(geom.origin(m), [1, 2, 3]))

    def test_offset_and_invert_are_baked_numerically(self):
        rnd = random.Random(7)
        for trial in range(30):
            o1, o2 = rnd.uniform(-300, 300), rnd.uniform(-90, 90)
            inv1, inv2 = rnd.random() < 0.5, rnd.random() < 0.5
            d1 = geom.unit([rnd.uniform(-1, 1) for _ in range(3)])
            d2 = geom.unit([rnd.uniform(-1, 1) for _ in range(3)])
            piv = [rnd.uniform(-200, 200) for _ in range(3)]
            tl = [rnd.uniform(-200, 200) for _ in range(3)]
            p = make([axis("1", "T1", "translation", d1, offset=o1, invert=inv1, children=[
                axis("2", "R1", "rotation", d2, pivot=piv, offset=o2, invert=inv2, children=[tool("3", tl)])])])
            u1, u2 = rnd.uniform(-500, 500), rnd.uniform(-180, 180)
            ev = xmleval.evaluate(xmlgen.build_xml(p), {"T1": u1, "R1": u2})
            q1 = o1 + (-1 if inv1 else 1) * u1
            q2 = o2 + (-1 if inv2 else 1) * u2
            # independent expectation: authored pose is model value 0; the model moves by q1 along d1 and q2 about d2
            # through the pivot (which has moved with the translation)
            m = geom.mul(geom.translation([q1 * c for c in d1]), geom.rotation_about(d2, q2, piv))
            self.assertTrue(close(xmleval.tool_point(ev), geom.apply(m, tl), 0.01), trial)   # num() keeps 7 digits

    def test_limits_and_initial_stay_in_axis_units(self):
        p = make([axis("1", "X", "translation", (1, 0, 0), rng=(10, 20), initial=12, offset=100, invert=True)])
        xml = xmlgen.build_xml(p)
        self.assertIn('x="-1" y="0" z="0" channelId="0" minvalue="10" maxvalue="20" initial_value="12"', xml)
        self.assertIn('<transform name="X_Offset"', xml)

    def test_pivot_frame_conversion_with_mcs_origin(self):
        rnd = random.Random(3)
        for trial in range(20):
            t = [rnd.uniform(-500, 500) for _ in range(3)]
            piv = [rnd.uniform(-200, 200) for _ in range(3)]
            def tree(shift):
                kw = {"mcs_origin": t} if shift else {}
                return [axis("1", "R1", "rotation", (0, 0, 1), pivot=piv, offset=rnd_off, **kw, children=[
                    part("2", "P", "cube"), axis("3", "X", "translation", (1, 0, 0), children=[tool("4", [5, 6, 7])])])]
            rnd_off = rnd.uniform(-60, 60)
            plain, shifted = make(tree(False)), make(tree(True))
            vals = {"R1": rnd.uniform(-180, 180), "X": rnd.uniform(-100, 100)}
            a, b = xmleval.evaluate(xmlgen.build_xml(plain), vals), xmleval.evaluate(xmlgen.build_xml(shifted), vals)
            self.assertTrue(close(xmleval.tool_point(a), xmleval.tool_point(b), 0.01))
            for ga, gb in zip(a["geometry"], b["geometry"]):
                self.assertTrue(close(ga["matrix"], gb["matrix"], 1e-3))
            # the origin of the parent of the first axis moved by t (when there is no offset wrapper in between)
        xml = xmlgen.build_xml(make([axis("1", "R1", "rotation", (0, 0, 1), pivot=(100, 0, 0), mcs_origin=(100, 0, 0))]))
        self.assertIn('rzx="0" rzy="0" rzz="0"', xml)

    def test_configuration_binds_only_bound_axes_with_value_expression(self):
        p = make([axis("1", "X", "translation", (1, 0, 0), binding="AxisX", offset=50, invert=True),
                  axis("2", "Free", "translation", (0, 1, 0), binding="")])
        cfg = xmlgen.configuration(p)
        self.assertEqual(cfg["ConfiguredAxis"], [{"ModelAxisName": "X", "ConnectionType": "datalayerAxes",
                                                  "DatalayerNode": "AxisX", "ExpressionScript": "value"}])

    def test_unknown_keys_survive(self):
        d = {"name": "K", "meshes": {}, "extra": {"customdata": "assignKin(a,b)"},
             "tree": [axis("1", "X", "translation", (1, 0, 0), customdata="assignKin(a,joint-1-1)", note="x")], "future": 1}
        v = project.validate(d)
        self.assertEqual(v["extra"], {"customdata": "assignKin(a,b)"})
        self.assertEqual(v["tree"][0]["customdata"], "assignKin(a,joint-1-1)")
        self.assertEqual(v["future"], 1)

    def test_validation_errors(self):
        for bad in ({"name": "../x"}, {"name": "a", "tree": [{"kind": "x", "id": "1", "name": "n"}]},
                    {"name": "a", "tree": [axis("1", "X", "translation", (0, 0, 0))]},
                    {"name": "a", "tree": [axis("1", "X", "translation", (1, 0, 0)), axis("2", "X", "translation", (1, 0, 0))]},
                    {"name": "a", "tree": [part("1", "P", "missing")]},
                    {"name": "a", "meshes": {"m": mesh("../m.stl")}}):
            with self.assertRaises(ValueError, msg=str(bad)):
                project.validate(bad)


GANTRY_TREE = lambda tool_pos, mcs=None: [axis("1", "X", "translation", (1, 0, 0), binding="AxisX", **({"mcs_origin": mcs} if mcs else {}), children=[
    axis("2", "Y", "translation", (0, 1, 0), binding="AxisY", children=[
        axis("3", "Z", "translation", (0, 0, 1), binding="AxisZ", children=[part("4", "Head", "cube"), tool("5", tool_pos)])])])]
KIN = {"name": "Gantry", "type": "Cartesian_XYZ", "axes": [{"name": "AxisX", "dir": "+"}, {"name": "AxisY", "dir": "+"}, {"name": "AxisZ", "dir": "+"}]}


class ZoneTest(unittest.TestCase):

    def test_not_checked_for_other_kinematics(self):
        r = zone.check(make([], kinematic={"name": "S", "type": "Scara_LinearAxisFlange"}))
        self.assertFalse(r["checked"])
        self.assertIn("Not checked", r["note"])

    def test_synthetic_pass_and_warn_and_fix(self):
        good = make(GANTRY_TREE([0, 0, 0]), kinematic=KIN)
        self.assertTrue(zone.check(good)["ok"])
        bad = make(GANTRY_TREE([0, 0, -150]), kinematic=KIN)
        r = zone.check(bad)
        self.assertFalse(r["ok"])
        self.assertFalse(r["rows"][0]["ok"])
        fixed = zone.fix(bad)
        self.assertEqual(fixed["tree"][0]["mcs_origin"], [0, 0, -150])
        self.assertTrue(zone.check(fixed)["ok"])
        rnd = random.Random(1)
        for _ in range(5):
            vals = {k: rnd.uniform(-300, 300) for k in "XYZ"}
            a = xmleval.evaluate(xmlgen.build_xml(bad), vals)
            b = xmleval.evaluate(xmlgen.build_xml(fixed), vals)
            self.assertTrue(close(xmleval.tool_point(a), xmleval.tool_point(b), 1e-6))
            for ga, gb in zip(a["geometry"], b["geometry"]):
                self.assertTrue(close(ga["matrix"], gb["matrix"], 1e-6))

    def test_left_handed_frame_fails(self):
        tree = [axis("1", "X", "translation", (1, 0, 0), binding="AxisX", children=[
            axis("2", "Y", "translation", (0, 1, 0), binding="AxisY", children=[
                axis("3", "Z", "translation", (0, 0, -1), binding="AxisZ", children=[tool("5", [0, 0, 0])])])])]
        r = zone.check(make(tree, kinematic=KIN))
        self.assertFalse(r["ok"])
        self.assertFalse(next(x for x in r["rows"] if x["name"] == "Right-handed")["ok"])

    def test_kinematic_axis_direction_counts(self):
        kin = copy.deepcopy(KIN)
        kin["axes"][2]["dir"] = "-"
        r = zone.check(make(GANTRY_TREE([0, 0, 0]), kinematic=kin))
        self.assertFalse(next(x for x in r["rows"] if x["name"] == "Right-handed")["ok"])

    def test_tilted_axes_orthogonality(self):
        tree = [axis("1", "X", "translation", (1, 0, 0), binding="AxisX", children=[
            axis("2", "Y", "translation", (1, 1, 0), binding="AxisY", children=[
                axis("3", "Z", "translation", (0, 0, 1), binding="AxisZ", children=[tool("5", [0, 0, 0])])])])]
        r = zone.check(make(tree, kinematic=KIN))
        self.assertFalse(next(x for x in r["rows"] if x["name"] == "Directions orthogonal")["ok"])

    @unittest.skipUnless(os.path.exists(GANTRY + "/Model_baked/L10409A_Gantry.xml"), "Gantry files not readable")
    def test_gantry_v3_passes_and_original_warns(self):
        """The viewer draws the MCS zones in the parent frame of X. Gantry v3 (baked, MCS_Origin) is right; the original
        is not (ExpressionScripts 2250 - value ... put the tool at 2250/1500/-2000 while the parent sits at the origin)."""
        proj = {"name": "G", "kinematic": KIN, "meshes": {}, "tree": [
            axis("1", "X", "translation", (1, 0, 0), binding="AxisX"), axis("2", "Y", "translation", (0, 1, 0), binding="AxisY"),
            axis("3", "Z", "translation", (0, 0, 1), binding="AxisZ")]}
        with open(GANTRY + "/Model_baked/L10409A_Gantry.xml") as f:
            baked = f.read()
        with open(GANTRY + "/Model/L10409A_Gantry.xml") as f:
            original = f.read()
        ok = zone.check(proj, baked, {})
        self.assertTrue(ok["ok"], ok["rows"])
        warn = zone.check(proj, original, {"X": 2250, "Y": 1500, "Z": -2000, "R": -90, "Camera_Z": 0})
        self.assertFalse(warn["ok"])
        self.assertFalse(warn["rows"][0]["ok"])
        # the fix would move the origin by (2250, 1500, -2000) in the world: the origin of Gantry v3's MCS_Origin
        self.assertTrue(close(warn["shift"], [2250, 1500, -2000], 0.01), warn["shift"])


class StorageTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.s = storage.ProjectStore(os.path.join(self.dir.name, "cfg"), os.path.join(self.dir.name, "common"))

    def tearDown(self):
        self.dir.cleanup()

    def test_create_list_and_unique_names_across_locations(self):
        self.s.create("A", "config")
        self.s.create("B", "common")
        self.assertEqual([(p["name"], p["location"]) for p in self.s.list()], [("A", "config"), ("B", "common")])
        with self.assertRaises(storage.Conflict):
            self.s.create("A", "common")
        with self.assertRaises(storage.Conflict):
            self.s.create("a", "config")           # case-insensitive

    def test_name_validation(self):
        for bad in ("", "../x", "a/b", ".hidden", "a\\b", "x" * 65, "end.", "a..b"):
            with self.assertRaises(ValueError, msg=bad):
                self.s.create(bad, "config")
        with self.assertRaises(ValueError):
            self.s.create("ok", "cloud")
        with self.assertRaises(ValueError):
            self.s.mesh_path("A", "../x.stl")

    def test_rename_duplicate_move_delete(self):
        self.s.create("A", "config")
        self.s.put_mesh("A", "cube.stl", fake.demo_stl(), "m")
        self.assertEqual(self.s.rename("A", "B")["name"], "B")
        with self.assertRaises(KeyError):
            self.s.get("A")
        c = self.s.duplicate("B", "C", "common")
        self.assertEqual(c["location"], "common")
        self.assertEqual(c["meshes"]["cube"]["unit"], "m")
        self.assertTrue(os.path.exists(self.s.mesh_path("C", "cube.stl")))
        m = self.s.move("B", "common")
        self.assertEqual(m["location"], "common")
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, "cfg", "B")))
        self.assertEqual(self.s.read_mesh("B", "cube.stl"), fake.demo_stl())
        with self.assertRaises(storage.Conflict):
            self.s.rename("B", "C")
        self.s.delete("B")
        self.assertEqual([p["name"] for p in self.s.list()], ["C"])

    def test_put_keeps_name_and_drops_location(self):
        self.s.create("A", "config")
        p = self.s.get("A")
        p["name"] = "Other"
        p["location"] = "common"
        saved = self.s.put("A", p)
        self.assertEqual((saved["name"], saved["location"]), ("A", "config"))

    def test_mesh_upload_replace_and_delete_rules(self):
        self.s.create("A", "config")
        p = self.s.put_mesh("A", "cube.stl", fake.demo_stl())
        p["tree"] = [part("1", "P", "cube")]
        self.s.put("A", p)
        with self.assertRaises(storage.Conflict):
            self.s.delete_mesh("A", "cube.stl")
        p["tree"] = []
        self.s.put("A", p)
        self.assertEqual(self.s.delete_mesh("A", "cube.stl")["meshes"], {})
        with self.assertRaises(ValueError):
            self.s.put_mesh("A", "bad.stl", b"this is not an stl file at all")
        with self.assertRaises(ValueError):
            self.s.put_mesh("A", "x.stl", fake.demo_stl(), "furlong")

    def test_ascii_stl_is_accepted(self):
        storage.check_stl(b"solid x\n facet normal 0 0 1\n outer loop\n vertex 0 0 0\n vertex 1 0 0\n vertex 0 1 0\n endloop\n endfacet\nendsolid x\n")


class MotionTest(unittest.TestCase):

    def test_axes_and_kinematics(self):
        bus = FakeBus()
        ax = {a["name"]: a for a in motion.axes(bus)}
        self.assertEqual(ax["AxisX"]["type"], "translation")
        self.assertEqual(ax["ScaraRot1"]["type"], "rotation")
        self.assertEqual(ax["AxisZ"]["range"], [0.0, 800.0])
        kins = {k["name"]: k for k in motion.kinematics(bus)}
        self.assertTrue(kins["Gantry"]["cartesian"])
        self.assertFalse(kins["Scara"]["cartesian"])

    def test_tree_from_kinematic(self):
        r = motion.tree_from_kinematic(FakeBus(), "Gantry")
        self.assertEqual(r["kinematic"]["type"], "Cartesian_XYZ")
        x = r["tree"][0]
        self.assertEqual((x["name"], x["binding"], x["direction"], x["range"]), ("AxisX", "AxisX", [1, 0, 0], [0.0, 2500.0]))
        self.assertEqual(x["children"][0]["children"][0]["direction"], [0, 0, 1])
        leaf = x["children"][0]["children"][0]["children"][0]
        self.assertEqual(leaf["kind"], "tool")
        project.validate({"name": "G", "kinematic": r["kinematic"], "tree": r["tree"]})
        s = motion.tree_from_kinematic(FakeBus(), "Scara")
        self.assertEqual(s["tree"][0]["type"], "rotation")
        self.assertEqual(s["tree"][0]["direction"], [0, 0, 1])
        with self.assertRaises(Exception):
            motion.tree_from_kinematic(FakeBus(), "Nope")


if __name__ == "__main__":
    unittest.main()
