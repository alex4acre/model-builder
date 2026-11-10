#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

"""Checks the app's Data Layer nodes (app/provider.py) against the REAL ctrlX Data Layer library with a local broker
(no ctrlX needed). Needs Ubuntu 24.04 (the library needs GLIBCXX_3.4.31):

    ctrlx-baseline/tools/dl_container.sh check <app folder>       (runs tests/framework/dl_check.py first)

or by hand:  apt install ./ctrlx-datalayer-*.deb;  python3 -m venv v;  v/bin/pip install ctrlx-datalayer ctrlx-fbs
             v/bin/python tests/integration/dl_check.py
"""

import json
import os
import sys
import tempfile
import time

import ctrlxdatalayer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app  # noqa: E402
from app.core import Core  # noqa: E402
from app.framework.bus import BusError, DatalayerBus  # noqa: E402
from app.framework.provider import NodeRegistry  # noqa: E402
from app.provider import register  # noqa: E402

R = app.NAME
failures = []


def check(cond, text):
    print(("ok   " if cond else "FAIL ") + text, flush=True)
    if not cond:
        failures.append(text)


def main():
    system = ctrlxdatalayer.system.System("")
    system.start(True)                         # with a broker: this is the local Data Layer
    provider = system.factory().create_provider("ipc://")
    check(provider.start() == ctrlxdatalayer.variant.Result.OK, "provider started with a local broker")
    bus = DatalayerBus(system, "ipc://")
    tmp = tempfile.TemporaryDirectory()
    core = Core(tmp.name, bus, log=print)
    registry = NodeRegistry(provider, R, log=print)
    register(registry, core)
    core.start()
    time.sleep(0.5)
    try:
        check(bus.is_connected(), "client connected")
        children = bus.browse(R)
        check(sorted(children) == ["counter", "setpoint", "state"], f"browse {R} -> {children}")
        check(isinstance(bus.read(f"{R}/counter"), int), "read counter (uint64)")
        check(bus.read(f"{R}/setpoint") == 0.0, "read setpoint (float64)")
        bus.write(f"{R}/setpoint", 4.25)
        check(core.config["setpoint"] == 4.25 and bus.read(f"{R}/setpoint") == 4.25, "write setpoint through the Data Layer")
        state = json.loads(bus.read(f"{R}/state"))
        check(state.get("setpoint") == 4.25, f"read state (JSON string) -> {state}")
        try:
            bus.write(f"{R}/counter", 5)
            check(False, "writing the read-only counter is refused")
        except BusError as e:
            check(e.code == "DL_PERMISSION_DENIED", f"writing the read-only counter is refused ({e.code})")
    finally:
        registry.clear()
        core.stop()
        bus.close()
        provider.stop()
        provider.close()
        system.stop(True)
        tmp.cleanup()
    print("FAILED: " + "; ".join(failures) if failures else "ALL OK", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
