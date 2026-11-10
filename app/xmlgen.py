# SPDX-License-Identifier: MIT

"""machine_definition XML, viewer configuration and package of a model-builder project.

Same output style as robot-configurator/app/viewer3d.py (build_xml, num, mat_str, part_matrix, TOOL_ATTRS,
configuration, zip_bytes are copied from there).

Frames (finding R1 in docs/plan.md): the 3D viewer reads rzx/rzy/rzz and x/y/z in the LOCAL frame of the enclosing
node. The project stores everything in the assembly frame at the model's zero pose; every node that the generator
adds around an axis is an identity at that pose, except MCS_Origin (the axis's own pivot is then converted).

Offsets and inversions are built into the XML (never into the ExpressionScript, which is the axis' formula, "value" by default):
    model value = offset + s * value,  s = -1 if invert else 1
  - a fixed transform <axis>_Offset around the axis (translation offset*direction, or rotation by offset degrees
    about the direction through the pivot),
  - the axis direction negated when inverted,
  - minvalue / maxvalue / initial_value stay in the MOTION axis' units.
An axis with "mcs_origin": [x, y, z] gets a transform MCS_Origin T(x, y, z) as its parent and a transform
MCS_Origin_Inverse T(-x, -y, -z) inside it, so the geometry stays where it was and only the origin of the parent
frame (where the viewer draws MCS zones) moves.
"""

import io
import json
import math
import zipfile
from xml.sax.saxutils import quoteattr

from app import geom

UNIT_SCALE = {"mm": 1.0, "m": 1000.0, "inch": 25.4}
TOOL_ATTRS = ('alpha="0" cuttr="1" cuttg="0.8392157" cuttb="0" noncuttr="0.4627451" '
              'noncuttg="0.5294118" noncuttb="0.6" arborr="0.435294122" arborg="0.5019608" '
              'arborb="0.5647059" holderr="0.180392161" holderg="0.309803933" holderb="0.309803933"')


def num(v):
    s = "%.7g" % v
    return "0" if s in ("-0", "0") else s


def mat_str(m):
    return ",".join(num(v) for v in m)


def part_matrix(p):
    """4x4 row-major matrix = T * R * S: 'rotation' (3x3), 'scale' [sx, sy, sz], 'position'."""
    rot = p.get("rotation", [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    scale = p.get("scale", [1, 1, 1])
    pos = p.get("position", [0, 0, 0])
    m = []
    for r in range(3):
        m += [rot[r][c] * scale[c] for c in range(3)] + [pos[r]]
    return m + [0, 0, 0, 1]


def mesh_matrix(mesh: dict):
    """The placement of a mesh: unit scale, then rotation (Rz*Ry*Rx, degrees), then position, in the assembly frame."""
    pl = mesh.get("placement") or {}
    s = UNIT_SCALE[mesh.get("unit", "mm")]
    return part_matrix({"position": pl.get("position", [0, 0, 0]),
                        "rotation": geom.euler(*(pl.get("rotation") or [0, 0, 0])), "scale": [s, s, s]})


def walk(tree):
    """All nodes of a tree, parents first."""
    for n in tree:
        yield n
        yield from walk(n.get("children") or [])


def axis_nodes(project):
    return [n for n in walk(project.get("tree") or []) if n.get("kind") == "axis"]


def numh(v):
    """A number of an imported node: 12 significant digits, so the values of the original file come back unchanged."""
    s = "%.12g" % v
    return "0" if s in ("-0", "0") else s


def _attr_text(d):
    return "".join(" %s=%s" % (k, quoteattr(v)) for k, v in (d or {}).items())


def build_xml(project: dict) -> str:
    """The machine_definition XML. An own project (0.1.0 style) gets the Mounting wrapper; an imported one ("root": "none")
    is written with the structure it was read with (its nodes carry "src": true and keep the attributes the editor does not
    model, see app/xmlimport.py)."""
    meshes = project.get("meshes") or {}
    ind = lambda n: "  " * n
    imported = project.get("root") == "none"
    out = list(project.get("xml_prolog") or [])

    def raw(items, lvl):
        for t in items or []:
            out.append(ind(lvl) + t.strip())

    if imported:
        out.append("<machine_definition%s>" % _attr_text(project.get("machine_attrs")))
        md = project.get("machine_data") or {}
        if not md.get("absent"):
            attrs = _attr_text(md.get("attrs"))
            if md.get("xml_extra"):
                out.append("  <machine_data%s>" % attrs)
                raw(md["xml_extra"], 2)
                out.append("  </machine_data>")
            else:
                out.append("  <machine_data%s />" % attrs)
        out.append("")
        base = 1
    else:
        out += ['<machine_definition>', '  <machine_data name=%s units="metric" />' % quoteattr(project["name"]), ""]
        out.append('  <transform name="Mounting" initialvalue="%s">' % mat_str(geom.IDENTITY))
        base = 2

    def emit_part(p, lvl):
        src = bool(p.get("src"))
        f = numh if src else num
        tool = p["kind"] == "tool"
        mesh = None if tool else meshes.get(p.get("mesh"))
        if not tool and mesh is None and not src:
            raise ValueError(f"part {p['name']!r}: mesh {p.get('mesh')!r} is not in the project")
        wrapped = not p.get("bare")
        if wrapped:
            if p.get("matrix"):
                m = p["matrix"]
            elif tool:
                m = geom.translation(p.get("position") or [0, 0, 0])
            else:
                m = mesh_matrix(mesh)
            out.append('%s<transform name=%s initialvalue="%s"%s>' % (
                ind(lvl), quoteattr(p.get("transform_name") or p["name"] + "_Trafo"),
                ",".join(f(v) for v in m), _attr_text(p.get("tattrs"))))
            lvl += 1
        if tool:
            attrs = 'name=%s objtype="tool"' % quoteattr(p["name"]) + (_attr_text(p.get("xattrs")) if src else " " + TOOL_ATTRS)
        else:
            c = p.get("colour")
            alpha = p.get("alpha")
            attrs = "name=%s objtype=%s" % (quoteattr(p["name"]), quoteattr(p.get("objtype") or "geometry"))
            if alpha is not None:
                attrs += ' alpha="%s"' % f(alpha)
            if c is not None:
                attrs += ' clrr="%s" clrg="%s" clrb="%s"' % (f(c[0]), f(c[1]), f(c[2]))
            if mesh is not None:
                attrs += " geo=%s" % quoteattr(mesh["file"])
            attrs += _attr_text(p.get("xattrs"))
        if p.get("xml_extra"):
            out.append("%s<geometry %s>" % (ind(lvl), attrs))
            raw(p["xml_extra"], lvl + 1)
            out.append("%s</geometry>" % ind(lvl))
        else:
            out.append("%s<geometry %s />" % (ind(lvl), attrs))
        if wrapped:
            out.append("%s</transform>" % ind(lvl - 1))

    def emit_frame(fr, lvl):
        f = numh if fr.get("src") else num
        out.append('%s<transform name=%s initialvalue="%s"%s>' % (
            ind(lvl), quoteattr(fr["name"]), ",".join(f(v) for v in fr["matrix"]), _attr_text(fr.get("xattrs"))))
        emit_level(fr.get("children") or [], lvl + 1)
        raw(fr.get("xml_extra"), lvl + 1)
        out.append("%s</transform>" % ind(lvl))

    def emit_node(n, lvl):
        if n["kind"] in ("part", "tool"):
            emit_part(n, lvl)
        elif n["kind"] == "frame":
            emit_frame(n, lvl)
        else:
            emit_axis(n, lvl)

    def emit_level(nodes, lvl):
        if imported:
            for n in nodes:
                emit_node(n, lvl)
            return
        for kinds in (("part", "tool"), ("frame",), ("axis",)):
            for n in nodes:
                if n["kind"] in kinds:
                    emit_node(n, lvl)

    def emit_axis(a, lvl):
        name, rotation = a["name"], a["type"] == "rotation"
        src = bool(a.get("src"))
        f = numh if src else num
        s = -1.0 if a.get("invert") else 1.0
        d = list(a["direction"])
        mcs = [float(v) for v in a.get("mcs_origin") or [0, 0, 0]]
        has_mcs = any(abs(v) > 1e-12 for v in mcs)
        pivot = [float(a["pivot"][i]) - mcs[i] for i in range(3)]      # in the frame the axis element is in
        offset = float(a.get("offset") or 0)
        closers = 0
        if has_mcs:
            out.append('%s<transform name="MCS_Origin" initialvalue="%s">' % (ind(lvl), mat_str(geom.translation(mcs))))
            lvl += 1
            closers += 1
        if offset:
            if rotation:
                m = geom.rotation_about(d, offset, pivot)
            else:
                u = geom.unit(d)
                m = geom.translation([offset * c for c in u])
            out.append('%s<transform name=%s initialvalue="%s">' % (ind(lvl), quoteattr(name + "_Offset"), mat_str(m)))
            lvl += 1
            closers += 1
        r = a.get("range") or [0, 0]
        if src:
            attrs = ('name=%s type=%s x="%s" y="%s" z="%s" minvalue="%s" maxvalue="%s" initial_value="%s"'
                     % (quoteattr(name), quoteattr(a["type"]), f(s * d[0]), f(s * d[1]), f(s * d[2]),
                        f(r[0]), f(r[1]), f(a.get("initial") or 0)))
            if rotation:
                attrs += ' rzx="%s" rzy="%s" rzz="%s"' % (f(pivot[0]), f(pivot[1]), f(pivot[2]))
            attrs += _attr_text(a.get("xattrs"))
        else:
            attrs = ('name=%s type=%s x="%s" y="%s" z="%s" channelId="0" minvalue="%s" maxvalue="%s" initial_value="%s"'
                     % (quoteattr(name), quoteattr(a["type"]), num(s * d[0]), num(s * d[1]), num(s * d[2]),
                        num(r[0]), num(r[1]), num(a.get("initial") or 0)))
            if rotation:
                attrs += (' rotationAxisRolloverEnabled="False" rzx="%s" rzy="%s" rzz="%s"'
                          % (num(pivot[0]), num(pivot[1]), num(pivot[2])))
            attrs += _attr_text(a.get("xattrs"))
        out.append("%s<axis %s>" % (ind(lvl), attrs))
        if has_mcs:
            out.append('%s<transform name="MCS_Origin_Inverse" initialvalue="%s">'
                       % (ind(lvl + 1), mat_str(geom.translation([-v for v in mcs]))))
            emit_level(a.get("children") or [], lvl + 2)
            raw(a.get("xml_extra"), lvl + 2)
            out.append("%s</transform>" % ind(lvl + 1))
        else:
            emit_level(a.get("children") or [], lvl + 1)
            raw(a.get("xml_extra"), lvl + 1)
        out.append("%s</axis>" % ind(lvl))
        for _ in range(closers):
            lvl -= 1
            out.append("%s</transform>" % ind(lvl))

    emit_level(project.get("tree") or [], base)
    if imported:
        raw(project.get("xml_extra"), 1)
    else:
        out.append("  </transform>")
        raw(project.get("xml_extra"), 1)
    out += ["</machine_definition>", ""]
    return "\n".join(out)


def used_meshes(project: dict) -> list:
    """The mesh entries (id order of first use) that parts of the tree refer to."""
    meshes = project.get("meshes") or {}
    seen = []
    for n in walk(project.get("tree") or []):
        if n.get("kind") == "part" and n.get("mesh") in meshes and n["mesh"] not in seen:
            seen.append(n["mesh"])
    return seen


def configuration(project: dict) -> dict:
    """Body for PUT /3dviewer/api/v2/projects/<name>/configuration: every bound model axis follows its ctrlX axis. The
    ExpressionScript is the axis' formula, written unchanged ("value" by default). Unbound axes are left out. An imported
    project also returns the entries it could not place on an axis and the settings it found in the viewer's own
    configuration (everything but the TrackId)."""
    entries, bound = [], set()
    for a in axis_nodes(project):
        if a.get("binding"):
            e = {"ModelAxisName": a["name"], "ConnectionType": "datalayerAxes", "DatalayerNode": a["binding"],
                 "ExpressionScript": a.get("formula") or "value"}
            for k, v in (a.get("binding_extra") or {}).items():
                if k not in ("ModelAxisName", "DatalayerNode", "ExpressionScript"):
                    e[k] = v
            entries.append(e)
            bound.add(a["name"])
    for e in project.get("orphan_bindings") or []:
        if isinstance(e, dict) and e.get("ModelAxisName") not in bound:
            entries.append(e)
    cfg = {"ConfiguredAxis": entries, "ToolNodes": {"deletion": {"useDataLayerNode": False}},
           "IsDemoModelDeleted": False, "IsBackgroundEnabled": False}
    for k, v in (project.get("configuration_extra") or {}).items():
        if k not in ("ConfiguredAxis", "TrackId"):
            cfg[k] = v
    return cfg


def generate(project: dict, read_mesh, name: str = None) -> dict:
    """{"name", "files": {file name: bytes} (XML + the STLs the parts use), "configuration", "missing": [mesh files]}.
    name = the project's name in the 3D viewer (default: the project's name). read_mesh(file name) -> bytes; a mesh file
    an imported project never had is left out and listed in "missing"."""
    name = name or project["name"]
    files = {name + ".xml": build_xml(project).encode("utf-8")}
    meshes = project.get("meshes") or {}
    missing = []
    for mid in used_meshes(project):
        f = meshes[mid]["file"]
        try:
            files[f] = read_mesh(f)
        except KeyError:
            if not project.get("root") == "none":
                raise
            missing.append(f)
    return {"name": name, "files": files, "configuration": configuration(project), "missing": missing}


def zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def package_zip(gen: dict) -> bytes:
    """The viewer package: Model.zip (XML + STLs) and <name>.json (the configuration)."""
    return zip_bytes({"Model.zip": zip_bytes(gen["files"]),
                      gen["name"] + ".json": json.dumps(gen["configuration"]).encode("utf-8")})
