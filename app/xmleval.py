# SPDX-License-Identifier: MIT

"""Forward kinematics of a machine_definition XML, the way the 3D viewer builds its scene (finding R1: rzx/rzy/rzz and
x/y/z are in the local frame of the enclosing node; an axis moves its object by direction*value, a rotation turns it
about the pivot). Used by the zone check and by the tests. Stdlib only.
"""

import xml.etree.ElementTree as ET

from app import geom


def _floats(text):
    return [float(v) for v in str(text).split(",")]


def evaluate(xml_text: str, values: dict = None) -> dict:
    """values: {axis name: value as the viewer applies it (after the ExpressionScript)}; missing = 0.
    Returns {"axes": {name: {"parent": 4x4 of the enclosing node, "world": 4x4 of the axis object, "dir": the XML
    direction normalised, "type": ...}}, "geometry": [{"name", "objtype", "geo", "matrix"}]} (world matrices,
    row-major lists)."""
    values = values or {}
    root = ET.fromstring(xml_text)
    axes, geometry = {}, []

    def visit(el, parent_m):
        for child in el:
            if child.tag == "transform":
                m = geom.mul(parent_m, _floats(child.get("initialvalue")))
                visit(child, m)
            elif child.tag == "axis":
                name, kind = child.get("name"), child.get("type")
                pivot = None
                d = geom.unit([float(child.get(k)) for k in ("x", "y", "z")])
                u = float(values.get(name, 0.0))
                if kind == "rotation":
                    pivot = [float(child.get(k) or 0) for k in ("rzx", "rzy", "rzz")]
                    m = geom.mul(parent_m, geom.rotation_about(d, u, pivot))
                else:
                    m = geom.mul(parent_m, geom.translation([c * u for c in d]))
                axes[name] = {"parent": parent_m, "world": m, "dir": d, "type": kind,
                              "pivot": pivot if kind == "rotation" else None}
                visit(child, m)
            elif child.tag == "geometry":
                geometry.append({"name": child.get("name"), "objtype": child.get("objtype"), "geo": child.get("geo"),
                                 "matrix": parent_m})

    visit(root, geom.IDENTITY)
    return {"axes": axes, "geometry": geometry}


def tool_point(ev: dict):
    for g in ev["geometry"]:
        if g["objtype"] == "tool":
            return geom.origin(g["matrix"])
    return None
