# SPDX-License-Identifier: MIT

"""The simulated ctrlX of model-builder (MODEL_BUILDER_FAKE=1 and the unit tests).

Seed the nodes the app uses with values as a real ctrlX gives them (copy them from a read-only dump of the
device) and override what the device does differently. The interface is app/framework/fakebus.py.
"""

from app.framework import fakebus

NODES = {
    "framework/metrics/system/cpu-utilisation-percent": 12.5,
    "framework/metrics/system/memavailable-mb": 1450.0,
    "motion/state/opstate": "Running",
    "scheduler/admin/state": "OPERATING",
    "demo/flag": False,
    "demo/position": [0.0, 0.0, 0.0],
}


class FakeBus(fakebus.FakeBus):

    def __init__(self, nodes: dict = None):
        super().__init__(NODES if nodes is None else nodes)
