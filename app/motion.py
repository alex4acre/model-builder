# SPDX-License-Identifier: MIT

"""Read-only access to ctrlX MOTION (motion/axs, motion/kin) for the axis binding list and "start from kinematic".
`bus` is any object with the DatalayerBus interface (RestBus with the caller's token in the snap)."""

import itertools

from app.framework.bus import BusError
from app.zone import CARTESIAN

ROTARY_UNITS = ("deg", "rad", "°")


def axes(bus) -> list:
    """[{"name", "type": rotation|translation|"" , "range": [min, max]|None, "unit"}] of the MOTION axes."""
    out = []
    for name in sorted(bus.browse("motion/axs")):
        info = {"name": name, "type": "", "range": None, "unit": ""}
        try:
            lim = (bus.read(f"motion/axs/{name}/cfg") or {}).get("limits") or {}
            unit = str(lim.get("posMinUnit") or "")
            info["unit"] = unit
            info["type"] = "rotation" if unit in ROTARY_UNITS else ("translation" if unit else "")
            if isinstance(lim.get("posMin"), (int, float)) and isinstance(lim.get("posMax"), (int, float)):
                info["range"] = [float(lim["posMin"]), float(lim["posMax"])]
        except BusError:
            pass                                   # listed without details
        out.append(info)
    return out


def kinematic_config(bus, name: str) -> dict:
    cfg = bus.read(f"motion/kin/{name}/cfg") or {}
    sets = ((cfg.get("mcs") or {}).get("axsTrafoSets")) or []
    return {"name": name, "type": (sets[0].get("jntTrafo") if sets else "") or "",
            "axes": [{"name": a.get("axsName"), "dir": a.get("axsDir") or "+", "index": a.get("acsIndex", i)}
                     for i, a in enumerate(cfg.get("axsCfg") or [])]}


def kinematics(bus) -> list:
    out = []
    for name in sorted(bus.browse("motion/kin")):
        try:
            k = kinematic_config(bus, name)
            out.append({"name": name, "type": k["type"], "axes": [a["name"] for a in sorted(k["axes"], key=lambda a: a["index"])],
                        "cartesian": k["type"] in CARTESIAN})
        except BusError as e:
            out.append({"name": name, "type": "", "axes": [], "cartesian": False, "error": str(e)})
    return out


def tree_from_kinematic(bus, name: str) -> dict:
    """{"kinematic": {"name", "type", "axes"}, "tree": [...]}: one axis node per kinematic axis (by axis index), nested in
    that order, then a tool marker at the end. Types and ranges from the MOTION axes; directions and pivots are defaults."""
    k = kinematic_config(bus, name)
    ordered = sorted(k["axes"], key=lambda a: a["index"])
    if not ordered:
        raise ValueError(f"The kinematic {name!r} has no axes")
    known = {a["name"]: a for a in axes(bus)}
    counter = itertools.count(1)
    unit_dirs = itertools.cycle([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    root, leaf = [], None
    for a in ordered:
        info = known.get(a["name"]) or {}
        kind = info.get("type") or "translation"
        node = {"kind": "axis", "id": f"n{next(counter)}", "name": a["name"], "type": kind,
                "direction": [0, 0, 1] if kind == "rotation" else next(unit_dirs),
                "pivot": [0, 0, 0], "range": info.get("range") or ([-360, 360] if kind == "rotation" else [-1000, 1000]),
                "initial": 0, "offset": 0, "invert": False, "binding": a["name"], "children": []}
        (root if leaf is None else leaf["children"]).append(node)
        leaf = node
    leaf["children"].append({"kind": "tool", "id": f"n{next(counter)}", "name": "Tool", "position": [0, 0, 0]})
    return {"kinematic": {"name": name, "type": k["type"], "axes": [{"name": a["name"], "dir": a["dir"]} for a in ordered]},
            "tree": root}
