# SPDX-License-Identifier: MIT

"""Cartesian zone check of a project (decision D7).

The 3D viewer draws the MCS zones of a Cartesian kinematic in a frame whose ORIGIN is the world origin (at the zero
pose) of the parent node of the model axis bound to the kinematic's first axis, and whose DIRECTIONS are the model
axes' x/y/z direction vectors times the kinematic axis direction. ExpressionScripts are ignored. The frame must be
right-handed. Source: the 3D viewer app's web client (calculateMcs4... / moveAxis), read 2026-11-10.

check(project, xml, values) -> {"checked": bool, "ok": bool, "rows": [{"name", "ok", "value", "note"}], "shift": [..]}
fix(project) -> the project with "mcs_origin" set on the first axis (Gantry v3 method).
"""

import copy
import math

from app import geom, xmlgen, xmleval

CARTESIAN = {"Cartesian_XYZ": 3, "Cartesian_XY": 2, "Cartesian_XZ": 2, "Cartesian_YZ": 2}
TOLERANCE = 0.01          # mm


def _fmt(v):
    return "(" + ", ".join("%.3f" % c for c in v) + ")"


def kin_axes(project) -> list:
    """[(axis name, direction sign)] of the kinematic's axes in order."""
    kin = project.get("kinematic") or {}
    axes = kin.get("axes")
    if axes:
        return [(a["name"] if isinstance(a, dict) else a, -1.0 if isinstance(a, dict) and a.get("dir") == "-" else 1.0)
                for a in axes]
    return [(a["binding"], 1.0) for a in xmlgen.axis_nodes(project) if a.get("binding")]


def applicable(project) -> bool:
    return bool(project.get("kinematic")) and (project["kinematic"].get("type") in CARTESIAN)


def check(project: dict, xml: str = None, values: dict = None) -> dict:
    kin = project.get("kinematic")
    if not kin:
        return {"checked": False, "ok": True, "rows": [], "note": "No kinematic: the zone frame is not checked."}
    if kin.get("type") not in CARTESIAN:
        return {"checked": False, "ok": True, "rows": [],
                "note": f"Not checked for this kinematic type ({kin.get('type') or 'unknown'})."}
    xml = xml if xml is not None else xmlgen.build_xml(project)
    by_binding = {a["binding"]: a["name"] for a in xmlgen.axis_nodes(project) if a.get("binding")}
    return check_model(xml, kin["type"], kin_axes(project), by_binding, values)


def check_model(xml: str, kin_type: str, kin_axes_: list, by_binding: dict, values: dict = None) -> dict:
    """The zone rule on a machine_definition XML. kin_axes_: [(MOTION axis name, direction sign)] in kinematic order;
    by_binding: {MOTION axis name: model axis name}; values: {model axis name: value} (what the viewer applies)."""
    if kin_type not in CARTESIAN:
        return {"checked": False, "ok": True, "rows": [],
                "note": f"Not checked for this kinematic type ({kin_type or 'unknown'})."}
    ev = xmleval.evaluate(xml, values)
    count = CARTESIAN[kin_type]
    wanted = list(kin_axes_)[:count]
    rows = []

    def row(name, ok, value, note):
        rows.append({"name": name, "ok": ok, "value": value, "note": note})

    nodes = []
    for axname, sign in wanted:
        model = by_binding.get(axname)
        if model is None or model not in ev["axes"]:
            row(f"Axis {axname}", False, "not bound", "No model axis is bound to this kinematic axis.")
            model = None
        nodes.append((axname, sign, model))
    if len(nodes) < count or any(n is None for _, _, n in nodes):
        row("Zone frame", False, "unknown", "Bind a model axis to each of the kinematic's first axes, then check again.")
        return {"checked": True, "ok": False, "rows": rows, "shift": None}

    first = ev["axes"][nodes[0][2]]
    origin = geom.origin(first["parent"])
    tool = xmleval.tool_point(ev)
    shift = None
    if tool is None:
        row("Tool point", False, "none", "Add a tool marker; it defines where the zone frame must be.")
    else:
        diff = [tool[i] - origin[i] for i in range(3)]
        dist = math.sqrt(sum(c * c for c in diff))
        shift = diff
        row("Origin = tool point", dist <= TOLERANCE, f"parent {_fmt(origin)}, tool {_fmt(tool)}",
            "The zone frame's origin (parent of the first axis at the zero pose) must be the tool point with all axes 0."
            if dist > TOLERANCE else "The parent of the first axis sits at the tool point at the zero pose.")
    dirs = []
    for axname, sign, node in nodes:
        e = ev["axes"][node]
        dirs.append([sign * c for c in geom.apply_dir(e["parent"], e["dir"])])
    unit_ok = all(abs(math.sqrt(sum(c * c for c in d)) - 1) < 1e-6 for d in dirs)
    ortho_ok = all(abs(sum(dirs[i][k] * dirs[j][k] for k in range(3))) < 1e-6
                   for i in range(len(dirs)) for j in range(i + 1, len(dirs)))
    row("Directions orthogonal", unit_ok and ortho_ok, " ".join(_fmt(d) for d in dirs),
        "The axis directions (world, times the kinematic axis direction) must be perpendicular unit vectors.")
    if count == 3:
        a, b, c = dirs
        det = (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0]))
        row("Right-handed", det > 0, f"determinant {det:.3f}",
            "X, Y, Z must form a right-handed frame (the determinant is +1)." if det <= 0 else "Right-handed.")
    return {"checked": True, "ok": all(r["ok"] for r in rows), "rows": rows, "shift": shift}


def fix(project: dict, xml: str = None) -> dict:
    """The project with an MCS_Origin on the first Cartesian axis (the origin of its parent moved onto the tool point,
    geometry unchanged). Only the origin is fixed; directions and handedness are the user's to correct."""
    res = check(project, xml)
    if not res["checked"] or res.get("shift") is None:
        raise ValueError("The zone frame cannot be fixed: " + (res.get("note") or "bind the axes and add a tool marker first"))
    p = copy.deepcopy(project)
    first = kin_axes(p)[0][0]
    node = next(a for a in xmlgen.axis_nodes(p) if a.get("binding") == first)
    old = node.get("mcs_origin") or [0, 0, 0]
    node["mcs_origin"] = [round(old[i] + res["shift"][i], 6) for i in range(3)]
    return p
