# SPDX-License-Identifier: MIT

"""Data Layer nodes of model-builder (for the PLC, HMIs and other apps):

  model-builder/counter      uint64, counts the worker's cycles (read-only)
  model-builder/setpoint     float64, writable; kept in config.json
  model-builder/state        the app state as JSON text (read-only)

Node types, command nodes and per-kinematic groups: app/framework/provider.py.
"""


def register(registry, core):
    registry.add("counter", "Worker cycles since the app started", "uint64", lambda: core.state()["counter"])
    registry.add("setpoint", "Example setpoint (kept in config.json)", "float64",
                 lambda: core.config["setpoint"], write=core.set_setpoint)
    registry.add("state", "App state (JSON)", "json", core.state)
