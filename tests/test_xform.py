# SPDX-License-Identifier: MIT

"""Dragging in the 3D preview (0.4.0): the world-space result of a drag is converted into the frame the value is stored in
(finding R1). The conversion itself is www/xform.js; this file holds a Python mirror of it and proves what matters, with
the server's own XML generator and evaluator: a stored value, put back into the project, lands exactly where it was
dragged to, for several parent rotations (frames), for every node kind that can be dragged:

  frame  -> its matrix            part -> its matrix, or the mesh placement (position + Rz*Ry*Rx) when it has none
  tool   -> its position          rotation axis -> its pivot (rzx/rzy/rzz, with MCS_Origin and the axis offset around it)

tests/ui/ui_check.py runs the JS module in the browser (round trip for five parents, a known value, rounding) and drags
through the real save path."""

import math
import unittest

from app import geom, xmlgen, xmleval
from app.project import validate

IDENT = geom.IDENTITY
XML_TOL = 2e-4          # the XML writes numbers with 7 significant digits (xmlgen.num)


# ---- Python mirror of www/xform.js
def inverse(m):
    a = [[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    inv = [[(a[(c + 1) % 3][(r + 1) % 3] * a[(c + 2) % 3][(r + 2) % 3] - a[(c + 1) % 3][(r + 2) % 3] * a[(c + 2) % 3][(r + 1) % 3]) / det
            for c in range(3)] for r in range(3)]
    t = [m[3], m[7], m[11]]
    out = []
    for r in range(3):
        out += [inv[r][0], inv[r][1], inv[r][2], -sum(inv[r][c] * t[c] for c in range(3))]
    return out + [0, 0, 0, 1.0]


def local_matrix(parent_world, world):
    return geom.mul(inverse(parent_world), world)


def local_point(parent_world, p):
    return geom.apply(inverse(parent_world), p)


def clean(v, step):
    r = round(v / step) * step
    return 0.0 if abs(r) < step / 2 else round(r, 12)


def clean_matrix(m):
    return [clean(c, 1e-6) if i in (3, 7, 11) else (1.0 if i == 15 else 0.0) if i >= 12 else clean(c, 1e-9) for i, c in enumerate(m)]


def decompose(m):                       # www/app.js decompose: position, rotation Rz*Ry*Rx in degrees
    scale = [math.hypot(m[c], m[4 + c], m[8 + c]) for c in range(3)]
    r = [[m[i * 4 + c] / scale[c] for c in range(3)] for i in range(3)]
    ry = math.asin(max(-1, min(1, -r[2][0])))
    if abs(math.cos(ry)) > 1e-9:
        rx, rz = math.atan2(r[2][1], r[2][2]), math.atan2(r[1][0], r[0][0])
    else:
        rx, rz = math.atan2(-r[1][2], r[1][1]), 0.0
    rnd = lambda v: round(v, 6) + 0
    return {"pos": [rnd(m[3]), rnd(m[7]), rnd(m[11])], "rot": [rnd(math.degrees(a)) for a in (rx, ry, rz)]}


def rot(axis, deg, t=(0, 0, 0)):
    m = geom.rot3(geom.axis_angle(axis, deg))
    m[3], m[7], m[11] = t
    return m


# parents: rotated about z by 90 and 33 degrees, a tilted one with offsets, and a chain
PARENTS = [rot([0, 0, 1], 90, (100, 0, 0)), rot([0, 0, 1], 33, (-5, 7, 11)),
           geom.mul(rot([1, 0, 0], 70, (0, 0, 300)), rot([0, 0, 1], -20, (1, 2, 3))),
           geom.mul(rot([0, 1, 0], -115, (40, -60, 5)), rot([1, 1, 0], 17, (0, 9, 0)))]
# desired world poses of the dragged item (a snapped drag: positions on a 10 mm grid, rotations by 15 degrees)
WORLDS = [geom.mul(rot([0, 0, 1], 45, (120, 10, -10)), rot([1, 0, 0], 30)), rot([0, 1, 0], 15, (-30, 50, 200)),
          rot([0, 0, 1], 0, (0, 0, 0))]


def project(tree, meshes=None):
    return validate({"name": "T", "meshes": meshes or {}, "tree": tree})


def geometry(p, name):
    ev = xmleval.evaluate(xmlgen.build_xml(p))
    return next(g for g in ev["geometry"] if g["name"] == name)["matrix"]


def close(a, b, tol=1e-5):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


class RoundTripTest(unittest.TestCase):

    def test_frame_matrix(self):
        for P in PARENTS:
            for W in WORLDS:
                stored = clean_matrix(local_matrix(P, W))
                p = project([{"kind": "frame", "id": "p", "name": "P", "matrix": P, "children": [
                    {"kind": "frame", "id": "f", "name": "F", "matrix": stored, "children": [
                        {"kind": "tool", "id": "t", "name": "Tip", "position": [0, 0, 0]}]}]}])
                self.assertTrue(close(geometry(p, "Tip"), W, XML_TOL), (P, W))

    def test_part_matrix_with_unit_scale(self):
        scale = geom.rot3([[25.4, 0, 0], [0, 25.4, 0], [0, 0, 25.4]])              # a mesh in inch: the wrapper carries the scale
        for P in PARENTS:
            for W in WORLDS:
                world = geom.mul(W, scale)
                stored = clean_matrix(local_matrix(P, world))
                p = project([{"kind": "frame", "id": "p", "name": "P", "matrix": P, "children": [
                    {"kind": "part", "id": "g", "name": "G", "mesh": "m", "matrix": stored, "colour": [0.5, 0.5, 0.5]}]}],
                            {"m": {"file": "m.stl", "unit": "inch"}})
                self.assertTrue(close(geometry(p, "G"), world, XML_TOL * 10), (P, W))

    def test_part_mesh_placement(self):
        for unit, s in (("mm", 1.0), ("inch", 25.4), ("m", 1000.0)):
            for P in PARENTS:
                for W in WORLDS:
                    world = geom.mul(W, geom.rot3([[s, 0, 0], [0, s, 0], [0, 0, s]]))
                    local = local_matrix(P, world)
                    d = decompose(local)               # the app saves position and rotation; the unit scale stays the mesh's
                    p = project([{"kind": "frame", "id": "p", "name": "P", "matrix": P, "children": [
                        {"kind": "part", "id": "g", "name": "G", "mesh": "m", "colour": [0.5, 0.5, 0.5]}]}],
                                {"m": {"file": "m.stl", "unit": unit, "placement": {"position": d["pos"], "rotation": d["rot"]}}})
                    self.assertTrue(close(geometry(p, "G"), world, 2e-3 * max(1, s)), (unit, P, W))

    def test_tool_position(self):
        for P in PARENTS:
            for W in WORLDS:
                pos = [clean(c, 1e-6) for c in local_point(P, geom.origin(W))]
                p = project([{"kind": "frame", "id": "p", "name": "P", "matrix": P, "children": [
                    {"kind": "tool", "id": "t", "name": "Tip", "position": pos}]}])
                self.assertTrue(close(geom.origin(geometry(p, "Tip")), geom.origin(W), XML_TOL), (P, W))

    def test_axis_pivot_with_zone_shift_and_offset(self):
        """The stored pivot is in the frame the axis element is in. An MCS_Origin shift is inside that frame (pivot = local + shift)
        and the fixed <axis>_Offset transform keeps the pivot in place, so neither changes the world point."""
        for P in PARENTS:
            for mcs in ([0, 0, 0], [12.5, -3, 40]):
                for offset in (0.0, 30.0):
                    frame_world = geom.mul(P, geom.translation(mcs)) if any(mcs) else P      # the frame the pivot is written in
                    for w in ([90, 10, 0], [-30, 55, 12.5], [0, 0, 0]):
                        local = [clean(c, 1e-6) for c in local_point(frame_world, w)]
                        pivot = [local[i] + mcs[i] for i in range(3)]                          # what the app stores
                        p = project([{"kind": "frame", "id": "p", "name": "P", "matrix": P, "children": [
                            {"kind": "axis", "id": "a", "name": "A", "type": "rotation", "direction": [0, 0, 1], "pivot": pivot,
                             "range": [-180, 180], "offset": offset, "mcs_origin": mcs if any(mcs) else None, "children": []}]}])
                        ev = xmleval.evaluate(xmlgen.build_xml(p))["axes"]["A"]
                        world_pivot = geom.apply(ev["parent"], ev["pivot"])
                        self.assertTrue(close(world_pivot, w, XML_TOL), (P, mcs, offset, w, world_pivot))

    def test_rounding(self):
        m = clean_matrix([1, 0, 0, 9.999999999997, 0, 1, 0, -1e-10, 0, 0, 1, 1.0000004, 0, 0, 0, 1])
        self.assertEqual([m[3], m[7], m[11]], [10.0, 0.0, 1.0])
        self.assertEqual(m[12:], [0.0, 0.0, 0.0, 1.0])

    def test_inverse(self):
        for P in PARENTS:
            self.assertTrue(close(geom.mul(P, inverse(P)), IDENT, 1e-12))
        scaled = geom.mul(PARENTS[1], geom.rot3([[2, 0, 0], [0, 3, 0], [0, 0, 4]]))
        self.assertTrue(close(geom.mul(scaled, inverse(scaled)), IDENT, 1e-12))


if __name__ == "__main__":
    unittest.main()
