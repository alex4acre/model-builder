# SPDX-License-Identifier: MIT

"""machine_definition XML, viewer configuration and package of a model-builder project.

Same output style as robot-configurator/app/viewer3d.py (build_xml, num, mat_str, part_matrix, TOOL_ATTRS,
configuration, zip_bytes are copied from there).

Frames (finding R1 in docs/plan.md): the 3D viewer reads rzx/rzy/rzz and x/y/z in the LOCAL frame of the enclosing
node. The project stores everything in the assembly frame at the model's zero pose; every node that the generator
adds around an axis is an identity at that pose, except MCS_Origin (the axis's own pivot is then converted).

Offsets and inversions are always built into the XML (never into an ExpressionScript):
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


def build_xml(project: dict) -> str:
    meshes = project.get("meshes") or {}
    ind = lambda n: "  " * n
    out = ['<machine_definition>', '  <machine_data name=%s units="metric" />' % quoteattr(project["name"]), ""]
    out.append('  <transform name="Mounting" initialvalue="%s">' % mat_str(geom.IDENTITY))

    def emit_part(p, lvl):
        if p["kind"] == "tool":
            m = geom.translation(p.get("position") or [0, 0, 0])
            out.append('%s<transform name=%s initialvalue="%s">' % (ind(lvl), quoteattr(p["name"] + "_Trafo"), mat_str(m)))
            out.append('%s<geometry name=%s objtype="tool" %s />' % (ind(lvl + 1), quoteattr(p["name"]), TOOL_ATTRS))
        else:
            mesh = meshes.get(p.get("mesh"))
            if mesh is None:
                raise ValueError(f"part {p['name']!r}: mesh {p.get('mesh')!r} is not in the project")
            c = p.get("colour") or [0.6, 0.6, 0.6]
            out.append('%s<transform name=%s initialvalue="%s">' % (ind(lvl), quoteattr(p["name"] + "_Trafo"),
                                                                    mat_str(mesh_matrix(mesh))))
            out.append('%s<geometry name=%s objtype="geometry" alpha="0" clrr="%s" clrg="%s" clrb="%s" geo=%s />'
                       % (ind(lvl + 1), quoteattr(p["name"]), num(c[0]), num(c[1]), num(c[2]), quoteattr(mesh["file"])))
        out.append('%s</transform>' % ind(lvl))

    def emit_level(nodes, lvl):
        for n in nodes:
            if n["kind"] in ("part", "tool"):
                emit_part(n, lvl)
        for n in nodes:
            if n["kind"] == "axis":
                emit_axis(n, lvl)

    def emit_axis(a, lvl):
        name, rotation = a["name"], a["type"] == "rotation"
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
        attrs = ('name=%s type=%s x="%s" y="%s" z="%s" channelId="0" minvalue="%s" maxvalue="%s" initial_value="%s"'
                 % (quoteattr(name), quoteattr(a["type"]), num(s * d[0]), num(s * d[1]), num(s * d[2]),
                    num(r[0]), num(r[1]), num(a.get("initial") or 0)))
        if rotation:
            attrs += (' rotationAxisRolloverEnabled="False" rzx="%s" rzy="%s" rzz="%s"'
                      % (num(pivot[0]), num(pivot[1]), num(pivot[2])))
        out.append("%s<axis %s>" % (ind(lvl), attrs))
        if has_mcs:
            out.append('%s<transform name="MCS_Origin_Inverse" initialvalue="%s">'
                       % (ind(lvl + 1), mat_str(geom.translation([-v for v in mcs]))))
            emit_level(a.get("children") or [], lvl + 2)
            out.append("%s</transform>" % ind(lvl + 1))
        else:
            emit_level(a.get("children") or [], lvl + 1)
        out.append("%s</axis>" % ind(lvl))
        for _ in range(closers):
            lvl -= 1
            out.append("%s</transform>" % ind(lvl))

    emit_level(project.get("tree") or [], 2)
    out += ["  </transform>", "</machine_definition>", ""]
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
    """Body for PUT /3dviewer/api/v2/projects/<name>/configuration: every bound model axis follows its ctrlX axis.
    The expression is always "value" (offsets and inversions are in the XML). Unbound axes are left out."""
    return {"ConfiguredAxis": [{"ModelAxisName": a["name"], "ConnectionType": "datalayerAxes",
                                "DatalayerNode": a["binding"], "ExpressionScript": "value"}
                               for a in axis_nodes(project) if a.get("binding")],
            "ToolNodes": {"deletion": {"useDataLayerNode": False}},
            "IsDemoModelDeleted": False, "IsBackgroundEnabled": False}


def generate(project: dict, read_mesh) -> dict:
    """{"name", "files": {file name: bytes} (XML + the STLs the parts use), "configuration"}.
    read_mesh(file name) -> bytes."""
    files = {project["name"] + ".xml": build_xml(project).encode("utf-8")}
    meshes = project.get("meshes") or {}
    for mid in used_meshes(project):
        f = meshes[mid]["file"]
        files[f] = read_mesh(f)
    return {"name": project["name"], "files": files, "configuration": configuration(project)}


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
