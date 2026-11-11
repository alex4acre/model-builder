# SPDX-License-Identifier: MIT

"""The project document: validation and defaults. Unknown keys (project "extra", unknown node keys) are kept as they are.

Coordinates are in the common assembly frame at the zero pose, in mm; rotations in degrees.
"""

import copy
import math
import re

from app import customdata
from app.formula import check_formula

NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_. -]{0,63}$")
MESH_RE = re.compile(r"^[^/\\\x00-\x1f.][^/\\\x00-\x1f]{0,110}\.stl$", re.IGNORECASE)
UNITS = ("mm", "m", "inch")
KINDS = ("part", "axis", "tool", "frame")
IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
AXIS_TYPES = ("rotation", "translation")


def check_name(name) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name) or name.endswith((".", " ")) or ".." in name:
        raise ValueError("A project name has 1 to 64 letters, digits, spaces, '_', '-' or '.' and starts with a letter, "
                         "digit or '_'")
    return name


def check_mesh_file(file) -> str:
    if not isinstance(file, str) or not MESH_RE.match(file) or ".." in file:
        raise ValueError("A mesh file name has no '/' or '\\', does not start with '.' and ends with .stl")
    return file


def _vec(v, what, n=3):
    if (not isinstance(v, (list, tuple)) or len(v) != n
            or any(isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) for c in v)):
        raise ValueError(f"{what} must be {n} numbers")
    return [float(c) for c in v]


def _number(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{what} must be a number")
    return float(v)


def new_project(name: str, location: str) -> dict:
    return {"name": name, "units": "mm", "location": location, "kinematic": None, "meshes": {}, "tree": [], "extra": {}}


def validate(p) -> dict:
    """A validated deep copy with defaults filled in; ValueError says what is wrong."""
    if not isinstance(p, dict):
        raise ValueError("A project is a JSON object")
    out = copy.deepcopy(p)
    check_name(out.get("name"))
    out["units"] = "mm"
    out.setdefault("kinematic", None)
    if out["kinematic"] is not None:
        k = out["kinematic"]
        if not isinstance(k, dict) or not isinstance(k.get("name"), str):
            raise ValueError('"kinematic" is null or {"name", "type"}')
        k.setdefault("type", "")
    if not isinstance(out.get("extra", {}), dict):
        raise ValueError('"extra" must be an object')
    out.setdefault("extra", {})
    meshes = out.setdefault("meshes", {})
    if not isinstance(meshes, dict):
        raise ValueError('"meshes" must be an object')
    files = set()
    for mid, m in meshes.items():
        if not isinstance(m, dict):
            raise ValueError(f"mesh {mid!r} must be an object")
        check_mesh_file(m.get("file"))
        if m["file"].lower() in files:
            raise ValueError(f"mesh file {m['file']!r} is used twice")
        files.add(m["file"].lower())
        m["unit"] = m.get("unit", "mm")
        if m["unit"] not in UNITS:
            raise ValueError(f"mesh {mid!r}: the unit is one of {', '.join(UNITS)}")
        pl = m.setdefault("placement", {})
        pl["position"] = _vec(pl.get("position", [0, 0, 0]), f"mesh {mid!r} position")
        pl["rotation"] = _vec(pl.get("rotation", [0, 0, 0]), f"mesh {mid!r} rotation")
    ids, names = set(), set()

    def attrs_of(n, key, what):
        v = n.setdefault(key, {})
        if not isinstance(v, dict) or any(not isinstance(k, str) or not isinstance(x, str) for k, x in v.items()):
            raise ValueError(f"{what}: {key!r} must be an object of text values")
        return v

    def extras_of(n, what):
        v = n.setdefault("xml_extra", [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            raise ValueError(f"{what}: 'xml_extra' must be a list of XML texts")

    def matrix_of(n, what, required=False):
        if n.get("matrix") is None:
            if required:
                n["matrix"] = list(IDENTITY)
            else:
                n.pop("matrix", None)
            return
        n["matrix"] = _vec(n["matrix"], f"{what} matrix", 16)

    def children_of(n, depth):
        kids = n.setdefault("children", [])
        if not isinstance(kids, list):
            raise ValueError("children must be a list")
        for c in kids:
            node(c, depth + 1)

    def node(n, depth):
        if not isinstance(n, dict) or n.get("kind") not in KINDS:
            raise ValueError("every tree node has a kind: part, axis, tool or frame")
        if depth > 60:
            raise ValueError("the tree is too deep")
        nid = n.get("id")
        if not isinstance(nid, str) or not nid or nid in ids:
            raise ValueError(f"node ids must be unique text ({nid!r})")
        ids.add(nid)
        nm = n.get("name")
        if not isinstance(nm, str) or not nm.strip():
            raise ValueError("every node needs a name")
        kind = n["kind"]
        src = bool(n.get("src"))
        if src:
            n["src"] = True
        else:
            n.pop("src", None)
        attrs_of(n, "xattrs", nm)
        extras_of(n, nm)
        if kind in ("part", "frame"):
            # Display ID (customdata "displayid(<id>)"): a node read from a file gets it from its customdata attribute
            if n.get("display_id") is None:
                n["display_id"] = customdata.parse(n["xattrs"].get("customdata"))
            try:
                n["display_id"] = customdata.check_id(n["display_id"])
            except ValueError as e:
                raise ValueError(f"{nm!r}: {e}") from None
            n["xattrs"] = customdata.attrs_with(n["xattrs"], n["display_id"])     # the stored customdata text follows the Display ID
        else:
            n.pop("display_id", None)
        if kind == "axis":
            if nm in names:
                raise ValueError(f"axis name {nm!r} is used twice (model axis names must be unique)")
            names.add(nm)
            if n.get("type") not in AXIS_TYPES:
                raise ValueError(f"axis {nm!r}: the type is rotation or translation")
            n["direction"] = _vec(n.get("direction", [0, 0, 1]), f"axis {nm!r} direction")
            if not any(n["direction"]):
                raise ValueError(f"axis {nm!r}: the direction must not be (0, 0, 0)")
            n["pivot"] = _vec(n.get("pivot", [0, 0, 0]), f"axis {nm!r} pivot")
            n["range"] = _vec(n.get("range", [-1000, 1000]), f"axis {nm!r} range", 2)
            if n["range"][0] > n["range"][1]:
                raise ValueError(f"axis {nm!r}: min is above max")
            n["initial"] = _number(n.get("initial", 0), f"axis {nm!r} initial")
            n["offset"] = _number(n.get("offset", 0), f"axis {nm!r} offset")
            n["invert"] = bool(n.get("invert", False))
            n["binding"] = n.get("binding") or ""
            if not isinstance(n["binding"], str):
                raise ValueError(f"axis {nm!r}: the binding is a MOTION axis name or empty")
            n["formula"] = "value" if n.get("formula") is None else n["formula"]
            try:
                check_formula(n["formula"])
            except ValueError as e:
                raise ValueError(f"axis {nm!r}: {e}") from None
            if n.get("binding_extra") is not None and not isinstance(n["binding_extra"], dict):
                raise ValueError(f"axis {nm!r}: 'binding_extra' must be an object")
            if n.get("mcs_origin") is not None:
                n["mcs_origin"] = _vec(n["mcs_origin"], f"axis {nm!r} mcs_origin")
            children_of(n, depth)
        elif kind == "frame":
            matrix_of(n, f"frame {nm!r}", required=True)
            children_of(n, depth)
        elif kind == "part":
            if n.get("mesh") not in meshes and not (src and not n.get("mesh")):
                raise ValueError(f"part {nm!r}: mesh {n.get('mesh')!r} is not in the project")
            if n.get("colour") is None and src:
                n["colour"] = None
            else:
                n["colour"] = _vec(n.get("colour", [0.6, 0.6, 0.6]), f"part {nm!r} colour")
                if not src and any(c < 0 or c > 1 for c in n["colour"]):
                    raise ValueError(f"part {nm!r}: colour values are 0 to 1")
            if n.get("alpha") is None and src:
                n["alpha"] = None
            else:
                n["alpha"] = _number(n.get("alpha", 0), f"part {nm!r} alpha")
            matrix_of(n, f"part {nm!r}")
            n["bare"] = bool(n.get("bare", False))
            if n.get("tattrs") is not None:
                attrs_of(n, "tattrs", nm)
        else:
            matrix_of(n, f"tool {nm!r}")
            if n.get("matrix"):
                n["position"] = [n["matrix"][3], n["matrix"][7], n["matrix"][11]]
            else:
                n["position"] = _vec(n.get("position", [0, 0, 0]), f"tool {nm!r} position")
            n["bare"] = bool(n.get("bare", False))
            if n.get("tattrs") is not None:
                attrs_of(n, "tattrs", nm)

    for key in ("xml_prolog", "xml_extra", "orphan_bindings"):
        v = out.get(key)
        if v is not None and not isinstance(v, list):
            raise ValueError(f"{key!r} must be a list")
    for key in ("machine_data", "machine_attrs", "configuration_extra"):
        v = out.get(key)
        if v is not None and not isinstance(v, dict):
            raise ValueError(f"{key!r} must be an object")
    if out.get("root") not in (None, "mounting", "none"):
        raise ValueError('"root" is "mounting" or "none"')
    if out.get("viewer_name") is not None:
        check_name(out["viewer_name"])

    tree = out.setdefault("tree", [])
    if not isinstance(tree, list):
        raise ValueError('"tree" must be a list')
    for n in tree:
        node(n, 0)
    # part and tool names are geometry names: unique among themselves is not needed by the viewer, but keep them readable
    return out
