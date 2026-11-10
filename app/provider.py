# SPDX-License-Identifier: MIT

"""Data Layer nodes of model-builder:

  model-builder/state     JSON text: number of projects, uptime (read-only)

Node types, command nodes and per-kinematic groups: app/framework/provider.py.
"""


def register(registry, core):
    registry.add("state", "App state (JSON)", "json", core.state)
