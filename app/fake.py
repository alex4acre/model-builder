# SPDX-License-Identifier: MIT

"""The simulated ctrlX of model-builder (MODEL_BUILDER_FAKE=1 and the unit tests): MOTION axes and two kinematics
(Cartesian gantry "Gantry" with AxisX/Y/Z, 4-axis Scara "Scara"), as the device gives them (kin cfg from kin-config.txt)."""

import struct

from app.framework import fakebus


def _axis(unit, lo, hi):
    return {"objectType": "Axis", "limits": {"posMin": lo, "posMax": hi, "posMinUnit": unit, "posMaxUnit": unit}}


def _kin(axes, trafo):
    return {"objectType": "Kinematics",
            "axsCfg": [{"axsName": n, "axsMeaning": m, "axsDir": "+", "acsIndex": i} for i, (n, m) in enumerate(axes)],
            "mcs": {"axsTrafoSets": [{"name": "t", "jntTrafo": trafo}]}}


NODES = {
    "motion/state/opstate": "Running",
    "motion/axs/AxisX/cfg": _axis("mm", 0.0, 2500.0),
    "motion/axs/AxisY/cfg": _axis("mm", 0.0, 1500.0),
    "motion/axs/AxisZ/cfg": _axis("mm", 0.0, 800.0),
    "motion/axs/ScaraRot1/cfg": _axis("deg", -150.0, 150.0),
    "motion/axs/ScaraRot2/cfg": _axis("deg", -140.0, 140.0),
    "motion/axs/ScaraLin1/cfg": _axis("mm", 0.0, 200.0),
    "motion/axs/ScaraRot3/cfg": _axis("deg", -360.0, 360.0),
    "motion/kin/Gantry/cfg": _kin([("AxisX", "MAIN_AXIS_X"), ("AxisY", "MAIN_AXIS_Y"), ("AxisZ", "MAIN_AXIS_Z")], "Cartesian_XYZ"),
    "motion/kin/Scara/cfg": _kin([("ScaraRot1", "MAIN_AXIS_X"), ("ScaraRot2", "MAIN_AXIS_Y"), ("ScaraRot3", "MAIN_AXIS_Z"),
                                  ("ScaraLin1", "MAIN_AXIS_A")], "Scara_LinearAxisFlange"),
}


def demo_stl() -> bytes:
    """A binary STL of a 100 mm cube centred on the origin (so the UI check can build a model without a CAD file)."""
    v = [(-50, -50, -50), (50, -50, -50), (50, 50, -50), (-50, 50, -50), (-50, -50, 50), (50, -50, 50), (50, 50, 50), (-50, 50, 50)]
    quads = [((0, 3, 2, 1), (0, 0, -1)), ((4, 5, 6, 7), (0, 0, 1)), ((0, 1, 5, 4), (0, -1, 0)),
             ((2, 3, 7, 6), (0, 1, 0)), ((1, 2, 6, 5), (1, 0, 0)), ((0, 4, 7, 3), (-1, 0, 0))]
    tris = []
    for idx, n in quads:
        for t in ((idx[0], idx[1], idx[2]), (idx[0], idx[2], idx[3])):
            tris.append(struct.pack("<12fH", *n, *v[t[0]], *v[t[1]], *v[t[2]], 0))
    return b"model-builder demo cube".ljust(80, b" ") + struct.pack("<I", len(tris)) + b"".join(tris)


class FakeBus(fakebus.FakeBus):

    def __init__(self, nodes: dict = None):
        super().__init__(NODES if nodes is None else nodes)
