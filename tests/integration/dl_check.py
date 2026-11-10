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
from app.storage import ProjectStore  # noqa: E402
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
    store = ProjectStore(os.path.join(tmp.name, "cfg"), os.path.join(tmp.name, "common"))
    store.create("DlCheck", "config")
    core = Core(store, lambda token: bus, lambda token: None, log=print)
    registry = NodeRegistry(provider, R, log=print)
    register(registry, core)
    time.sleep(0.5)
    try:
        check(bus.is_connected(), "client connected")
        children = bus.browse(R)
        check(children == ["state"], f"browse {R} -> {children}")
        state = json.loads(bus.read(f"{R}/state"))
        check(state.get("projects") == 1, f"read state (JSON string) -> {state}")
        try:
            bus.write(f"{R}/state", "x")
            check(False, "writing the read-only state is refused")
        except BusError as e:
            check(e.code == "DL_PERMISSION_DENIED", f"writing the read-only state is refused ({e.code})")
    finally:
        registry.clear()
        bus.close()
        provider.stop()
        provider.close()
        system.stop(True)
        tmp.cleanup()
    print("FAILED: " + "; ".join(failures) if failures else "ALL OK", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
