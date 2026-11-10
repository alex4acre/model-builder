# SPDX-License-Identifier: MIT

"""Demo projects of the simulated 3D viewer (MODEL_BUILDER_FAKE=1): two small ones made here, and, when the shared folder
is readable, the user's Scara Sort, Delta_Ori_Sort and L10409A_Gantry. catalog() -> {name: loader}; a loader returns
{"files": {name: bytes}, "configuration": dict}. Nothing is read until a project is opened."""

import io
import json
import os
import zipfile

from app.fake import demo_stl

SHARED = os.environ.get("MODEL_BUILDER_SHARED", "/media/sf_Claude_TEest")
I = "1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1"


def _m(x=0, y=0, z=0, sx=1, sy=1, sz=1):
    return f"{sx},0,0,{x},0,{sy},0,{y},0,0,{sz},{z},0,0,0,1"


def _geo(name, geo, rgb=(0.7, 0.7, 0.75), alpha=0):
    return f'<geometry name="{name}" objtype="geometry" alpha="{alpha}" clrr="{rgb[0]}" clrg="{rgb[1]}" clrb="{rgb[2]}" geo="{geo}" />'


TOOL = ('<geometry name="Tool" objtype="tool" alpha="0" cuttr="1" cuttg="0.84" cuttb="0" noncuttr="0.46" noncuttg="0.53" '
        'noncuttb="0.6" arborr="0.43" arborg="0.5" arborb="0.56" holderr="0.18" holderg="0.31" holderb="0.31" />')


def gantry_demo() -> dict:
    """Gantry-like: nested named transforms, X = 2250 - value, Z = value - 100, R = value - 90, a mesh named in another
    case than its file (Beam.STL / beam.stl) and an unbound axis (Camera_Z)."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<machine_definition>
  <machine_data version="1.9" name="Demo Gantry" units="metric"><view_transform initialvalue="{I}" /></machine_data>
  <transform name="ViewTransform" initialvalue="{I}">
    <transform name="FloorGeo" initialvalue="{_m(1250, 750, -25, 28, 17, 0.5)}">
      {_geo("Floor", "floor.stl", (0.82, 0.84, 0.86))}
    </transform>
    <transform name="GantryTransform" initialvalue="{I}">
      <axis name="X" type="translation" x="1" y="0" z="0" channelId="0" minvalue="-100" maxvalue="2500" initial_value="2250">
        <transform name="BeamGeo" initialvalue="{_m(0, 750, 700, 1, 17, 1)}">
          {_geo("XBeam", "Beam.STL", (0.72, 0.72, 0.79))}
        </transform>
        <axis name="Y" type="translation" x="0" y="1" z="0" channelId="0" minvalue="0" maxvalue="1500" initial_value="750">
          <transform name="CarriageGeo" initialvalue="{_m(0, 0, 700, 1.6, 1.6, 1.2)}">
            {_geo("Carriage", "cube.stl", (0.2, 0.55, 0.8))}
          </transform>
          <axis name="Z" type="translation" x="0" y="0" z="-1" channelId="0" minvalue="0" maxvalue="600" initial_value="100">
            <transform name="ZGeo" initialvalue="{_m(0, 0, 450, 0.4, 0.4, 5)}">
              {_geo("ZRod", "cube.stl", (0.55, 0.55, 0.6))}
            </transform>
            <axis name="R" type="rotation" x="0" y="0" z="1" channelId="0" minvalue="-270" maxvalue="450" initial_value="0" rotationAxisRolloverEnabled="False" rzx="0" rzy="0" rzz="0">
              <transform name="HeadGeo" initialvalue="{_m(120, 0, 180, 3, 0.6, 0.6)}">
                {_geo("Head", "cube.stl", (0.97, 0.56, 0.27))}
              </transform>
              <transform name="ToolTransform" initialvalue="{_m(240, 0, 150)}">
                {TOOL}
              </transform>
            </axis>
          </axis>
        </axis>
        <transform name="CameraGeo" initialvalue="{_m(300, 100, 900)}">
          <axis name="Camera_Z" type="translation" x="0" y="0" z="-1" channelId="0" minvalue="0" maxvalue="500" initial_value="0">
            {_geo("Camera", "cube.stl", (0.9, 0.3, 0.3))}
          </axis>
        </transform>
      </axis>
    </transform>
  </transform>
</machine_definition>
"""
    cfg = {"ConfiguredAxis": [
        {"ModelAxisName": "X", "ConnectionType": "datalayerAxes", "DatalayerNode": "AxisX", "ExpressionScript": "2250 - value"},
        {"ModelAxisName": "Y", "ConnectionType": "datalayerAxes", "DatalayerNode": "AxisY", "ExpressionScript": "value"},
        {"ModelAxisName": "Z", "ConnectionType": "datalayerAxes", "DatalayerNode": "AxisZ", "ExpressionScript": "value"},
        {"ModelAxisName": "R", "ConnectionType": "datalayerAxes", "DatalayerNode": "ScaraRot3", "ExpressionScript": "value - 90"}],
        "ToolNodes": {"deletion": {"useDataLayerNode": False}}, "TrackId": "00000000-0000-4000-8000-000000000001",
        "IsDemoModelDeleted": False, "IsBackgroundEnabled": False}
    # the file is stored as beam.stl but the XML says Beam.STL
    return {"files": {"Demo Gantry.xml": xml.encode(), "beam.stl": demo_stl(), "cube.stl": demo_stl(), "floor.stl": demo_stl()},
            "configuration": cfg}


def delta_demo() -> dict:
    """Delta-like: one driven arm, a passive joint solved by assignKin, an orientation axis and a tool."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<machine_definition>
  <machine_data name="Demo Delta" units="metric" />
  <transform name="BaseTransform" initialvalue="{I}">
    <transform name="BaseGeo" initialvalue="{_m(0, 0, 400, 3, 3, 0.4)}">
      {_geo("Base", "cube.stl", (0.6, 0.6, 0.65))}
    </transform>
    <axis name="DeltaRot1" type="rotation" x="0" y="1" z="0" channelId="0" minvalue="-90" maxvalue="90" initial_value="20" rotationAxisRolloverEnabled="False" rzx="100" rzy="0" rzz="400">
      <transform name="UpperGeo" initialvalue="{_m(235, 0, 400, 2.7, 0.2, 0.2)}">
        {_geo("UpperArm", "cube.stl", (0.2, 0.55, 0.8))}
      </transform>
      <axis name="_r1h1" customdata="assignKin(Delta,joint-1-2b)" type="rotation" x="0" y="-1" z="0" channelId="0" minvalue="-170" maxvalue="170" initial_value="110" rotationAxisRolloverEnabled="False" rzx="370" rzy="0" rzz="400">
        <transform name="LowerGeo" initialvalue="{_m(370, 0, 200, 0.15, 0.15, 4)}">
          {_geo("LowerArm", "cube.stl", (0.75, 0.75, 0.8))}
        </transform>
        <axis name="OriRot1" type="rotation" x="0" y="0" z="1" channelId="0" minvalue="-360" maxvalue="360" initial_value="0" rzx="370" rzy="0" rzz="0">
          <transform name="GripGeo" initialvalue="{_m(370, 0, 20, 0.6, 0.6, 0.4)}">
            {_geo("Gripper", "cube.stl", (0.97, 0.56, 0.27))}
          </transform>
          <transform name="ToolTransform" initialvalue="{_m(370, 0, -20)}">
            {TOOL}
          </transform>
        </axis>
      </axis>
    </axis>
  </transform>
</machine_definition>
"""
    cfg = {"ConfiguredAxis": [
        {"ModelAxisName": "DeltaRot1", "ConnectionType": "datalayerAxes", "DatalayerNode": "ScaraRot1", "ExpressionScript": "value"},
        {"ModelAxisName": "OriRot1", "ConnectionType": "datalayerAxes", "DatalayerNode": "ScaraRot3", "ExpressionScript": "value"}],
        "ToolNodes": {"deletion": {"useDataLayerNode": False}}, "TrackId": "00000000-0000-4000-8000-000000000002",
        "IsDemoModelDeleted": False, "IsBackgroundEnabled": False}
    return {"files": {"Demo Delta.xml": xml.encode(), "cube.stl": demo_stl()}, "configuration": cfg}


def _zip_files(path: str) -> dict:
    with zipfile.ZipFile(path) as z:
        return {os.path.basename(i.filename): z.read(i) for i in z.infolist() if not i.is_dir()}


def _json(path: str):
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8-sig"))
    except (OSError, ValueError):
        return None


def _shared(zip_rel: str, json_rel: str):
    zip_path, json_path = os.path.join(SHARED, zip_rel), os.path.join(SHARED, json_rel)
    if not (os.path.isfile(zip_path) and os.path.isfile(json_path)):
        return None
    return lambda: {"files": _zip_files(zip_path), "configuration": _json(json_path)}


def catalog() -> dict:
    out = {"Demo Gantry": gantry_demo, "Demo Delta": delta_demo}
    for name, zip_rel, json_rel in (
            ("Scara Sort", "Scara Sort/Model.zip", "Scara Sort/Scara Sort.json"),
            ("Delta_Ori_Sort", "Delta_Ori_Sort/Model.zip", "Delta_Ori_Sort/Delta_Ori_Sort.json"),
            ("L10409A_Gantry", "Robot Problem/Model.zip", "Robot Problem/Model/L10409A_Gantry.json")):
        try:
            loader = _shared(zip_rel, json_rel)
        except OSError:
            loader = None
        if loader:
            out[name] = loader
    return out
