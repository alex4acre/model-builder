# SPDX-License-Identifier: MIT

"""Import of a 3D viewer project (machine_definition XML + axis-binding configuration) as an editable project.

The mapping (decision D8, 0.3.0):
  * a <transform> whose only child is one <geometry> becomes a part (objtype geometry) or a tool (objtype tool) with the
    transform's matrix and name; every other <transform> becomes a "frame" node {name, matrix, children};
  * a <geometry> that sits directly in another element becomes a part/tool with "bare": true (no wrapper transform);
  * an <axis> becomes an axis node; pivot and direction stay as in the XML, in the LOCAL frame of the enclosing node
    (finding R1);
  * every attribute the editor does not model is kept on the node as "xattrs" (axis: customdata, channelId,
    rotationAxisRolloverEnabled, supports_spinning, ...; geometry: objtype extras, cuttr..., unknown; transform extras as
    "tattrs"), and written back unchanged;
  * unknown elements and comments are kept as XML text in "xml_extra" of the node they were in (the project for the
    root, "machine_data" for its children);
  * the machine_data attributes (version, name, units) and its children (view_transform) are kept;
  * the configuration's ExpressionScript becomes the axis' "formula"; other keys of an entry and entries that name no axis
    are kept ("binding_extra", "orphan_bindings", "configuration_extra").
Nodes read here carry "src": true: they are written with 12 significant digits and in their original order, without the
Mounting wrapper of an own project. convert() returns a report; "dropped" lists what cannot be kept (the user must confirm).
Stdlib only.
"""

import math
import re
import xml.etree.ElementTree as ET

from app import project as proj
from app.formula import check_formula

MODELLED_AXIS = {"name", "type", "x", "y", "z", "minvalue", "maxvalue", "initial_value", "rzx", "rzy", "rzz"}


class ImportProblem(ValueError):
    """The XML cannot be imported (and nothing is dropped silently: the reason is told)."""


def _num(text):
    try:
        v = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _raw(el):
    el.tail = None
    return ET.tostring(el, encoding="unicode").strip()


def _is_element(c):
    return isinstance(c.tag, str)


def _label(el):
    return f'<{el.tag}{" " + chr(34) + el.get("name") + chr(34) if el.get("name") else ""}>'


class _Import:

    def __init__(self, files, configuration):
        self.files = set(files)
        self.have = {f.lower(): f for f in files}
        self.counter = 0
        self.meshes = {}                       # real file name -> mesh id
        self.kept, self.dropped, self.notes, self.missing = [], [], [], []
        self.kept_count = {}
        self.binds = {}                        # model axis name -> entry (first one)
        self.used_binds = set()
        self.configuration = configuration

    def nid(self):
        self.counter += 1
        return f"i{self.counter}"

    def keep(self, what):
        self.kept_count[what] = self.kept_count.get(what, 0) + 1

    # --- helpers ----------------------------------------------------------------------------------

    def text_check(self, el):
        if el.text and el.text.strip():
            self.dropped.append(f"Text inside {_label(el)}: {el.text.strip()[:60]!r}")
        for c in el:
            if c.tail and c.tail.strip():
                self.dropped.append(f"Text after {_label(c) if _is_element(c) else 'a comment'}: {c.tail.strip()[:60]!r}")

    def matrix(self, el):
        raw = el.get("initialvalue")
        try:
            m = [float(v) for v in str(raw).split(",")]
            if len(m) != 16 or not all(math.isfinite(v) for v in m):
                raise ValueError
        except (TypeError, ValueError):
            raise ImportProblem(f'The transform "{el.get("name")}" has no valid initialvalue (16 numbers), so it cannot be edited here') from None
        return m

    def mesh_id(self, geo):
        real = self.have.get(geo.lower())
        file = real or geo
        if real is None:
            self.missing.append(geo)
        if file not in self.meshes:
            base = re.sub(r"\.stl$", "", file, flags=re.I)
            mid, i = base, 2
            while mid in self.meshes.values():
                mid, i = f"{base}_{i}", i + 1
            self.meshes[file] = mid
        return self.meshes[file]

    # --- elements ---------------------------------------------------------------------------------

    def children(self, el):
        """(nodes, extras) of the element's children."""
        self.text_check(el)
        nodes, extras = [], []
        for c in el:
            if not _is_element(c):
                extras.append(_raw(c))
                self.keep("comments or processing instructions")
            elif c.tag == "transform":
                nodes.append(self.transform(c))
            elif c.tag == "axis":
                nodes.append(self.axis(c))
            elif c.tag == "geometry":
                nodes.append(self.geometry(c, None))
            else:
                extras.append(_raw(c))
                self.keep(f"<{c.tag}> elements")
        return nodes, extras

    def transform(self, el):
        m = self.matrix(el)
        name = el.get("name") or ""
        kids = list(el)
        self.text_check(el)
        if len(kids) == 1 and _is_element(kids[0]) and kids[0].tag == "geometry" and not (el.text and el.text.strip()):
            tattrs = {k: v for k, v in el.attrib.items() if k not in ("name", "initialvalue")}
            return self.geometry(kids[0], {"matrix": m, "transform_name": name, "tattrs": tattrs})
        nodes, extras = self.children(el)
        return {"id": self.nid(), "kind": "frame", "name": name or "(unnamed)", "src": True, "matrix": m,
                "xattrs": {k: v for k, v in el.attrib.items() if k not in ("name", "initialvalue")},
                "xml_extra": extras, "children": nodes}

    def geometry(self, el, wrapper):
        self.text_check(el)
        extras = []
        for c in el:
            extras.append(_raw(c))
            self.keep("comments or processing instructions" if not _is_element(c) else f"<{c.tag}> elements")
        name = el.get("name") or ""
        objtype = el.get("objtype") or "geometry"
        n = {"id": self.nid(), "name": name or "(unnamed)", "src": True, "xml_extra": extras}
        if wrapper:
            n.update(wrapper)
            if not n["tattrs"]:
                del n["tattrs"]
        else:
            n["bare"] = True
        rest = {k: v for k, v in el.attrib.items() if k not in ("name", "objtype")}
        if objtype == "tool":
            n.update(kind="tool", xattrs=rest, position=[0.0, 0.0, 0.0])
            if wrapper:
                n["position"] = [wrapper["matrix"][3], wrapper["matrix"][7], wrapper["matrix"][11]]
            return n
        n["kind"] = "part"
        if objtype != "geometry":
            n["objtype"] = objtype
        geo = rest.pop("geo", None)
        colours = [_num(rest.get(k)) for k in ("clrr", "clrg", "clrb")]
        if all(c is not None for c in colours):
            n["colour"] = colours
            for k in ("clrr", "clrg", "clrb"):
                del rest[k]
        else:
            n["colour"] = None
        alpha = _num(rest.get("alpha")) if "alpha" in rest else None
        if alpha is not None:
            n["alpha"] = alpha
            del rest["alpha"]
        else:
            n["alpha"] = None
        n["xattrs"] = rest
        n["mesh"] = self.mesh_id(geo) if geo else None
        return n

    def axis(self, el):
        name = el.get("name") or ""
        kind = el.get("type")
        if kind not in proj.AXIS_TYPES:
            raise ImportProblem(f'The axis "{name}" has type {kind!r}: only rotation and translation axes can be edited here')
        d = [_num(el.get(k)) for k in ("x", "y", "z")]
        d = [0.0 if v is None else v for v in d]
        if not any(d):
            raise ImportProblem(f'The axis "{name}" has the direction (0, 0, 0)')
        rest = {k: v for k, v in el.attrib.items() if k not in MODELLED_AXIS or (k in ("rzx", "rzy", "rzz") and kind != "rotation")}
        pivot = [_num(el.get(k)) or 0.0 for k in ("rzx", "rzy", "rzz")] if kind == "rotation" else [0.0, 0.0, 0.0]
        lo, hi, ini = _num(el.get("minvalue")), _num(el.get("maxvalue")), _num(el.get("initial_value"))
        nodes, extras = self.children(el)
        n = {"id": self.nid(), "kind": "axis", "name": name or "(unnamed)", "src": True, "type": kind, "direction": d, "pivot": pivot,
             "range": [-1000.0 if lo is None else lo, 1000.0 if hi is None else hi], "initial": 0.0 if ini is None else ini,
             "offset": 0, "invert": False, "binding": "", "formula": "value", "xattrs": rest, "xml_extra": extras, "children": nodes}
        b = self.binds.get(n["name"])
        if b is not None and str(b.get("DatalayerNode") or ""):
            self.used_binds.add(id(b))
            n["binding"] = str(b["DatalayerNode"])
            if b.get("ExpressionScript") is not None:
                try:
                    n["formula"] = check_formula(str(b["ExpressionScript"]))
                except ValueError as e:
                    raise ImportProblem(f'The ExpressionScript of the axis "{name}" cannot be kept: {e}') from None
            extra = {k: v for k, v in b.items() if k not in ("ModelAxisName", "DatalayerNode", "ExpressionScript")}
            if extra:
                n["binding_extra"] = extra
        return n


def convert(xml_text: str, configuration, files) -> dict:
    """{"project": a project document without name/location ("root": "none", nodes with "src"), "mesh_files": [file names to
    copy], "report": {"kept": [...], "dropped": [...], "notes": [...], "missing_meshes": [...], "counts": {...}}}.
    files: the file names of the viewer project (STLs are matched to the geo attributes in any upper/lower case).
    Raises ImportProblem for XML that cannot be imported."""
    if re.search(r"<!(DOCTYPE|ENTITY)", xml_text, re.I):
        raise ImportProblem("The model XML has a DOCTYPE or ENTITY declaration, which is not accepted")
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        parser.feed(xml_text)
        root = parser.close()
    except ET.ParseError as e:
        raise ImportProblem(f"The model XML cannot be parsed: {e}") from None
    if root.tag != "machine_definition":
        raise ImportProblem("The XML is not a machine_definition")
    im = _Import(files, configuration)
    cfg = configuration if isinstance(configuration, dict) else {}
    entries = [e for e in cfg.get("ConfiguredAxis") or [] if isinstance(e, dict) and e.get("ModelAxisName")]
    for e in entries:
        im.binds.setdefault(str(e["ModelAxisName"]), e)
    # the part of the document around the root: comments before and after are kept, anything else is reported
    idx = xml_text.find("<machine_definition")
    prolog_text = xml_text[:idx] if idx >= 0 else ""
    prolog = re.findall(r"<!--.*?-->", prolog_text, re.S)
    left = re.sub(r"<!--.*?-->", "", prolog_text, flags=re.S)
    left = re.sub(r"<\?xml[^>]*\?>", "", left).strip().lstrip("﻿").strip()
    if left:
        im.dropped.append(f"Text before the root element: {left[:60]!r}")
    end = xml_text.rfind("</machine_definition>")
    tail_text = xml_text[end + len("</machine_definition>"):] if end >= 0 else ""
    tail = re.findall(r"<!--.*?-->", tail_text, re.S)
    if re.sub(r"<!--.*?-->", "", tail_text, flags=re.S).strip():
        im.dropped.append("Text after the root element")
    if prolog:
        im.keep("comments before the root element")
    if tail:
        im.keep("comments after the root element (moved inside it)")

    im.text_check(root)
    machine, nodes, extras = None, [], []
    for c in root:
        if not _is_element(c):
            extras.append(_raw(c))
            im.keep("comments or processing instructions")
        elif c.tag == "machine_data" and machine is None:
            im.text_check(c)
            machine = {"attrs": dict(c.attrib), "xml_extra": [_raw(x) for x in c]}
            for x in c:
                im.keep("comments or processing instructions" if not _is_element(x) else f"<{x.tag}> elements (in machine_data)")
        elif c.tag == "transform":
            nodes.append(im.transform(c))
        elif c.tag == "axis":
            nodes.append(im.axis(c))
        elif c.tag == "geometry":
            nodes.append(im.geometry(c, None))
        else:
            extras.append(_raw(c))
            im.keep(f"<{c.tag}> elements")
    if machine is None:
        machine = {"absent": True}
        im.notes.append("The XML has no machine_data element; none is written.")
    orphans = [e for e in entries if id(e) not in im.used_binds]
    if orphans:
        im.notes.append("Bindings kept as they are, because no axis of the model matches them: "
                        + ", ".join(f'{e["ModelAxisName"]} -> {e.get("DatalayerNode") or "(none)"}' for e in orphans))
    meshes = {mid: {"file": file, "unit": "mm", "placement": {"position": [0, 0, 0], "rotation": [0, 0, 0]}}
              for file, mid in im.meshes.items()}
    if im.missing:
        im.notes.append("Meshes named in the XML but not in the project (kept as references; upload needs them): "
                        + ", ".join(sorted(set(im.missing))))
    for what, n in sorted(im.kept_count.items()):
        im.kept.append(f"{n} {what} kept unchanged")
    project = {"units": "mm", "kinematic": None, "meshes": meshes, "tree": nodes, "extra": {}, "root": "none",
               "machine_data": machine, "machine_attrs": dict(root.attrib), "xml_prolog": prolog, "xml_extra": extras + tail,
               "orphan_bindings": orphans,
               "configuration_extra": {k: v for k, v in cfg.items() if k not in ("ConfiguredAxis", "TrackId")}}
    count = {"axes": 0, "parts": 0, "tools": 0, "frames": 0}

    def walk(ns):
        for n in ns:
            count[{"axis": "axes", "part": "parts", "tool": "tools", "frame": "frames"}[n["kind"]]] += 1
            walk(n.get("children") or [])
    walk(nodes)
    return {"project": project, "mesh_files": sorted(f for f in im.meshes if f in im.files),
            "report": {"kept": im.kept, "dropped": im.dropped, "notes": im.notes,
                       "missing_meshes": sorted(set(im.missing)), "counts": count}}
