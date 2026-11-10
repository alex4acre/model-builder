# SPDX-License-Identifier: MIT

"""Read-only analysis of a 3D viewer project (machine_definition XML + axis-binding configuration JSON): the structure
tree, the axes with their bindings and formulas, warnings, and the zone check on the viewer's own model.
Nothing here changes a project. Stdlib only.
"""

import math
import re
import xml.etree.ElementTree as ET

from app import zone

_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_FORMS = [
    (re.compile(r"value"), lambda: (1.0, 0.0)),
    (re.compile(r"-\s*value"), lambda: (-1.0, 0.0)),
    (re.compile(rf"({_NUM})\s*-\s*value"), lambda k: (-1.0, k)),
    (re.compile(rf"({_NUM})\s*\+\s*value"), lambda k: (1.0, k)),
    (re.compile(rf"value\s*\+\s*({_NUM})"), lambda k: (1.0, k)),
    (re.compile(rf"value\s*-\s*({_NUM})"), lambda k: (1.0, -k)),
    (re.compile(rf"({_NUM})\s*\*\s*value"), lambda k: (k, 0.0)),
    (re.compile(rf"value\s*\*\s*({_NUM})"), lambda k: (k, 0.0)),
    (re.compile(rf"value\s*/\s*({_NUM})"), lambda k: (1.0 / k, 0.0) if k else None),
]


def parse_formula(script):
    """(a, b) with model value = a * value + b for the simple linear forms the viewer's ExpressionScripts use in practice
    (value, -value, k - value, value + k, value - k, k * value, value * k, value / k, k + value), else None ("not
    understood"). Never evaluates anything: only these patterns, with numeric k, are accepted."""
    if script is None:
        return (1.0, 0.0)
    text = str(script).strip()
    if text == "":
        return (1.0, 0.0)
    for pattern, make in _FORMS:
        m = pattern.fullmatch(text)
        if m:
            try:
                r = make(*[float(g) for g in m.groups()])
            except (ValueError, OverflowError):
                return None
            if r is None or not all(math.isfinite(c) for c in r):
                return None
            return r
    return None


def _floats(text):
    return [float(v) for v in str(text).replace(";", ",").split(",") if v.strip() != ""]


def _num(value, default=0.0):
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def decompose(m):
    """(position mm, rotation degrees as Rz*Ry*Rx, scale) of a row-major 4x4 matrix (16 numbers)."""
    pos = [m[3], m[7], m[11]]
    scale = [math.sqrt(m[0 + c] ** 2 + m[4 + c] ** 2 + m[8 + c] ** 2) for c in range(3)]
    r = [[(m[r_ * 4 + c] / scale[c]) if scale[c] > 1e-12 else 0.0 for c in range(3)] for r_ in range(3)]
    ry = math.asin(max(-1.0, min(1.0, -r[2][0])))
    if abs(math.cos(ry)) > 1e-9:
        rx, rz = math.atan2(r[2][1], r[2][2]), math.atan2(r[1][0], r[0][0])
    else:
        rx, rz = math.atan2(-r[1][2], r[1][1]), 0.0
    rnd = lambda v: round(v, 6) + 0.0
    return [rnd(c) for c in pos], [rnd(math.degrees(a)) for a in (rx, ry, rz)], [rnd(c) for c in scale]


def _warn(code, text, axis=None, level="warning"):
    return {"code": code, "level": level, "axis": axis, "text": text}


def _bindings(configuration):
    """{model axis name: {"node": MOTION axis, "script": text}} from ConfiguredAxis (the first entry of a name wins)."""
    out = {}
    for e in (configuration or {}).get("ConfiguredAxis") or []:
        if not isinstance(e, dict) or not e.get("ModelAxisName"):
            continue
        out.setdefault(str(e["ModelAxisName"]), {"node": str(e.get("DatalayerNode") or ""),
                                                  "script": e.get("ExpressionScript")})
    return out


def analyse(xml_text: str, configuration: dict = None, files=None) -> dict:
    """{"structure": [node, ...], "axes": [...], "tools": n, "warnings": [...], "geometry_files": [...]}.
    files: the file names in the project (None = not known: no check for missing meshes)."""
    if re.search(r"<!(DOCTYPE|ENTITY)", xml_text, re.I):
        raise ValueError("The model XML has a DOCTYPE or ENTITY declaration, which is not accepted")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"The model XML cannot be parsed: {e}") from None
    if root.tag != "machine_definition":
        raise ValueError("The XML is not a machine_definition")
    binds = _bindings(configuration)
    have = None if files is None else {f.lower(): f for f in files}
    warnings, axes, geoms, seen_axes, counter = [], [], [], {}, [0]
    tools = 0
    if configuration is None:
        warnings.append(_warn("no_configuration", "The project has no axis binding configuration, so no model axis follows a MOTION axis.", level="info"))

    def nid():
        counter[0] += 1
        return f"n{counter[0]}"

    def visit(el, depth):
        nonlocal tools
        out = []
        for c in el:
            if c.tag == "transform":
                raw = c.get("initialvalue")
                try:
                    m = _floats(raw)
                    if len(m) != 16:
                        raise ValueError
                except (TypeError, ValueError):
                    warnings.append(_warn("bad_transform", f'Transform "{c.get("name")}" has no valid initialvalue (16 numbers); it is shown as identity.'))
                    m = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
                pos, rot, scale = decompose(m)
                out.append({"id": nid(), "kind": "transform", "name": c.get("name") or "", "matrix": m, "position": pos,
                            "rotation": rot, "scale": scale, "customdata": c.get("customdata") or "", "children": visit(c, depth + 1)})
            elif c.tag == "axis":
                name = c.get("name") or ""
                kind = c.get("type") or "translation"
                custom = c.get("customdata") or ""
                passive = custom.strip().lower().startswith("assignkin(")
                b = binds.get(name)
                script = b["script"] if b and b["script"] is not None else ("value" if b else "")
                formula = parse_formula(script) if b else (1.0, 0.0)
                a = {"id": nid(), "kind": "axis", "name": name, "type": kind,
                     "direction": [_num(c.get(k)) for k in ("x", "y", "z")],
                     "pivot": [_num(c.get(k)) for k in ("rzx", "rzy", "rzz")] if kind == "rotation" else None,
                     "min": _num(c.get("minvalue"), -1000.0), "max": _num(c.get("maxvalue"), 1000.0),
                     "initial": _num(c.get("initial_value")), "customdata": custom, "passive": passive,
                     "channel": c.get("channelId") or "",
                     "binding": b["node"] if b else "", "script": script, "formula": list(formula) if formula else None}
                axes.append(a)
                node = dict(a)
                node["children"] = visit(c, depth + 1)
                out.append(node)
                if name in seen_axes:
                    if seen_axes[name] == 1:
                        warnings.append(_warn("duplicate_axis", f'The axis name "{name}" is used more than once; a binding names only one of them.', name))
                    seen_axes[name] += 1
                else:
                    seen_axes[name] = 1
                if passive:
                    warnings.append(_warn("assignkin", f'Axis "{name}" is a passive joint ({custom.strip()}): the viewer solves it from the kinematic, so the preview cannot move it.', name, "info"))
                elif not b or not b["node"]:
                    warnings.append(_warn("unbound", f'The model axis "{name}" is not bound to a MOTION axis, so it does not move in the viewer.', name))
                elif script is not None and str(script).strip() != "value":
                    warnings.append(_warn("expression", f'Axis "{name}": the ExpressionScript is "{str(script).strip()}", not "value". The viewer ignores ExpressionScripts for the MCS zones of a Cartesian kinematic; build the offset or inversion into the model (axis offset and direction in the XML) and use "value".', name))
            elif c.tag == "geometry":
                objtype = c.get("objtype") or "geometry"
                geo = c.get("geo") or ""
                g = {"id": nid(), "kind": "tool" if objtype == "tool" else "geometry", "name": c.get("name") or "", "objtype": objtype,
                     "geo": geo, "colour": [_num(c.get(k)) for k in ("clrr", "clrg", "clrb")], "alpha": _num(c.get("alpha")),
                     "customdata": c.get("customdata") or "", "present": None, "file": ""}
                if objtype == "tool":
                    tools += 1
                elif geo:
                    geoms.append(geo)
                    if have is not None:
                        real = have.get(geo.lower())
                        g["present"] = real is not None
                        g["file"] = real or ""
                        if real is None:
                            warnings.append(_warn("missing_mesh", f'The mesh "{geo}" of "{g["name"]}" is not in the project.', None))
                out.append(g)
        return out

    structure = visit(root, 0)
    if tools == 0:
        warnings.append(_warn("no_tool", "The model has no tool marker (a geometry with objtype=\"tool\"): the tool point cannot be shown and the zone check has nothing to compare with."))
    for model, b in binds.items():
        if model not in seen_axes:
            warnings.append(_warn("binding_without_axis", f'The binding of "{b["node"]}" names the model axis "{model}", which is not in the XML.', model))
    return {"structure": structure, "axes": axes, "tools": tools, "warnings": warnings, "geometry_files": sorted(set(geoms)),
            "bindings": [{"model": m, "node": b["node"], "script": b["script"] if b["script"] is not None else "value",
                          "formula": (list(parse_formula(b["script"])) if parse_formula(b["script"]) else None),
                          "in_model": m in seen_axes} for m, b in binds.items()]}


def zero_values(configuration: dict) -> dict:
    """{model axis name: value at MOTION value 0}: what the viewer applies with every MOTION axis at 0 (b of a*value+b;
    0 where the formula is not understood)."""
    out = {}
    for model, b in _bindings(configuration).items():
        f = parse_formula(b["script"])
        out[model] = f[1] if f else 0.0
    return out


def zone_check(xml_text: str, configuration: dict, kin_type: str, kin_axes: list) -> dict:
    """The zone rule on a viewed model. kin_axes: [(MOTION axis name, direction sign)] in kinematic order. The model is
    evaluated with every MOTION axis at 0 and the ExpressionScripts applied (they decide where the tool point is at
    the zero pose), while the zone frame itself ignores them, like the viewer."""
    by_binding = {b["node"]: m for m, b in _bindings(configuration).items() if b["node"]}
    return zone.check_model(xml_text, kin_type, kin_axes, by_binding, zero_values(configuration))
