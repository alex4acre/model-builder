#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

"""Checks the framework's DatalayerBus and provider against the REAL ctrlX Data Layer library with a local broker
(no ctrlX needed). Needs Ubuntu 24.04 (the library needs GLIBCXX_3.4.31), e.g. the container of
ctrlx-baseline/tools/dl_container.sh, which runs this before the app's own tests/integration/dl_check.py.
"""

import os
import sys
import time

import ctrlxdatalayer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from app.framework.bus import BusError, DatalayerBus  # noqa: E402
from app.framework.provider import NodeRegistry  # noqa: E402

ROOT = "framework-check"
failures = []


def check(cond, text):
    print(("ok   " if cond else "FAIL ") + text, flush=True)
    if not cond:
        failures.append(text)


def refused(fn, code, text):
    try:
        fn()
        check(False, f"{text}: refused")
    except BusError as e:
        check(e.code == code, f"{text}: refused with {e.code} (expected {code})")


def main():
    system = ctrlxdatalayer.system.System("")
    system.start(True)                         # with a broker: this is the local Data Layer
    provider = system.factory().create_provider("ipc://")
    check(provider.start() == ctrlxdatalayer.variant.Result.OK, "provider started with a local broker")
    bus = DatalayerBus(system, "ipc://")
    reg = NodeRegistry(provider, ROOT, log=lambda m: None)
    store = {"bool8": False, "int64": -3, "uint64": 7, "float64": 1.5, "string": "a", "json": {"k": [1, 2]},
             "array-of-bool8": [True, False], "array-of-int64": [1, -2], "array-of-float64": [0.5, 2.0],
             "array-of-string": ["x", "y"]}

    def setter(t):
        def write(value):
            if t == "int64" and value > 1000:
                raise ValueError("too big")
            store[t] = value
            return value
        return write

    for t in store:
        reg.add(f"types/{t}", f"a {t} node", t, lambda t=t: store[t], write=setter(t))
    reg.add("readonly", "read-only", "uint64", lambda: 1)
    reg.add_command("command", "a command", lambda text: f"did {text}" if text != "bad" else 1 / 0)
    reg.sync(["k1", "k2"], lambda k: reg.add(f"kin/{k}/state", "state", "string", lambda k=k: f"state of {k}", group=k))
    time.sleep(0.5)
    try:
        check(sorted(bus.browse(ROOT)) == ["command", "kin", "readonly", "types"], f"browse {ROOT}")
        for t, value in store.items():
            got = bus.read(f"{ROOT}/types/{t}")
            expect = '{"k": [1, 2]}' if t == "json" else value
            check(got == expect, f"read {t} -> {got!r}")
            md = bus.metadata(f"{ROOT}/types/{t}")
            published = "string" if t == "json" else t
            check(md["references"].get("readType") == f"types/datalayer/{published}" and md["operations"].get("write"),
                  f"metadata {t} -> {md['references'].get('readType')}")
        news = {"bool8": True, "int64": 42, "uint64": 9, "float64": -2.25, "string": "b",
                "array-of-bool8": [False], "array-of-int64": [5, 6, 7], "array-of-float64": [1.25],
                "array-of-string": ["z"]}
        for t, value in news.items():
            bus.write(f"{ROOT}/types/{t}", value)
            check(store[t] == value and bus.read(f"{ROOT}/types/{t}") == value, f"write {t} {value!r}")
        bus.write(f"{ROOT}/types/json", '{"k": 3}')
        check(store["json"] == {"k": 3}, f"write json -> {store['json']!r}")
        check(bus.read_typed(f"{ROOT}/types/array-of-float64")[0] == "array_float64", "read_typed array")
        refused(lambda: bus.write(f"{ROOT}/types/int64", 5000), "DL_INVALID_VALUE", "a value the app refuses")
        refused(lambda: bus.write(f"{ROOT}/types/json", "{broken"), "DL_INVALID_VALUE", "invalid JSON")
        refused(lambda: bus.write(f"{ROOT}/readonly", 5), "DL_PERMISSION_DENIED", "writing a read-only node")
        refused(lambda: bus.read(f"{ROOT}/nothing"), "DL_INVALID_ADDRESS", "reading a missing node")
        bus.write(f"{ROOT}/command", "go")
        check(bus.read(f"{ROOT}/command") == "did go", "command node: result of the last write")
        refused(lambda: bus.write(f"{ROOT}/command", "bad"), "DL_INVALID_VALUE", "a failing command")
        check(bus.read(f"{ROOT}/command").startswith("error: "), "command node: error result")
        check(sorted(bus.browse(f"{ROOT}/kin")) == ["k1", "k2"], "groups k1, k2")
        reg.sync(["k2", "k3"], lambda k: reg.add(f"kin/{k}/state", "state", "string", lambda k=k: k, group=k))
        time.sleep(0.3)
        check(sorted(bus.browse(f"{ROOT}/kin")) == ["k2", "k3"], f"sync removed k1, added k3 -> {bus.browse(f'{ROOT}/kin')}")
    finally:
        reg.clear()
        bus.close()
        provider.stop()
        provider.close()
        system.stop(True)
    print("FAILED: " + "; ".join(failures) if failures else "ALL OK", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
