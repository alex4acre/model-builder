# SPDX-License-Identifier: MIT

"""A simulated ctrlX Data Layer with the same interface as framework.bus.DatalayerBus, for development and
tests on a machine without the Data Layer library (it needs Ubuntu 24.04) and without a ctrlX.

An app's app/fake.py subclasses FakeBus: it seeds the nodes the app uses, with values as a real ctrlX gives
them (copied from a read-only dump of the device), and overrides what the device does differently
(answers of creates, errors, lag). Where the device surprised you, simulate the surprise there.

Node values are plain Python like DatalayerBus returns them; a dict is a flatbuffers object. A callable
value is a "Method" node: read_args(address, args) calls it with the arguments.
"""

import contextlib
import threading

from app.framework.bus import BusError


def value_type(value) -> str:
    """The type name DatalayerBus.read_typed would give a value of this Python type."""
    if isinstance(value, bool):
        return "bool8"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "float64"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        if value and all(isinstance(x, bool) for x in value):
            return "array_bool8"
        if value and all(isinstance(x, str) for x in value):
            return "array_string"
        return "array_float64" if any(isinstance(x, float) for x in value) else "array_int64"
    return "flatbuffers"


class FakeBus:

    def __init__(self, nodes: dict = None):
        self.lock = threading.RLock()
        self.nodes = dict(nodes or {})
        self.readonly = set()        # addresses whose writes fail with DL_PERMISSION_DENIED
        self.denied = set()          # tokens that may do nothing (a user without permissions)
        self.token = ""              # the token of the running session()
        self.created = []            # (address, value) of each create, for tests
        self.connected = True

    def is_connected(self) -> bool:
        return self.connected

    def close(self):
        pass

    @contextlib.contextmanager
    def session(self, token: str = ""):
        with self.lock:
            previous, self.token = self.token, token or self.token
            try:
                yield self
            finally:
                self.token = previous

    def _allowed(self, what):
        if self.token and self.token in self.denied:
            raise BusError(f"{what}: DL_PERMISSION_DENIED", "DL_PERMISSION_DENIED")

    def _node(self, what, address):
        self._allowed(f"{what} {address}")
        if address not in self.nodes:
            raise BusError(f"{what} {address}: DL_INVALID_ADDRESS", "DL_INVALID_ADDRESS")
        return self.nodes[address]

    # --- the DatalayerBus interface -------------------------------------------------------------

    def browse(self, address: str) -> list:
        address = address.strip("/")
        prefix = address + "/" if address else ""
        with self.lock:
            self._allowed(f"browse {address}")
            children = {p[len(prefix):].split("/")[0] for p in self.nodes if p.startswith(prefix)}
            if not children and address and address not in self.nodes:
                raise BusError(f"browse {address}: DL_INVALID_ADDRESS", "DL_INVALID_ADDRESS")
        return sorted(children)

    def metadata(self, address: str) -> dict:
        with self.lock:
            self._allowed(f"metadata {address}")
            leaf = address in self.nodes
        return {"nodeClass": "Variable" if leaf else "Folder",
                "operations": {"read": leaf, "write": leaf and address not in self.readonly, "create": False,
                               "delete": False, "browse": True},
                "description": "", "references": {}}

    def read(self, address: str):
        with self.lock:
            value = self._node("read", address)
            if callable(value):
                raise BusError(f"read {address}: DL_INVALID_VALUE (the node needs arguments)", "DL_INVALID_VALUE")
            return value

    def read_typed(self, address: str):
        value = self.read(address)
        return value_type(value), value

    def read_args(self, address: str, args: dict):
        with self.lock:
            value = self._node("read", address)
            return value(args) if callable(value) else value

    def write(self, address: str, value):
        with self.lock:
            old = self._node("write", address)
            if address in self.readonly:
                raise BusError(f"write {address}: DL_PERMISSION_DENIED", "DL_PERMISSION_DENIED")
            if type(old) is not type(value) and not (isinstance(old, float) and isinstance(value, int)
                                                     and not isinstance(value, bool)):
                raise BusError(f"write {address}: DL_TYPE_MISMATCH", "DL_TYPE_MISMATCH")
            self.nodes[address] = float(value) if isinstance(old, float) else value

    def write_json(self, address: str, value):
        with self.lock:
            self._node("write", address)
            self.nodes[address] = value

    def create(self, address: str, value):
        with self.lock:
            self._allowed(f"create {address}")
            self.created.append((address, value))
        return None

    def remove(self, address: str):
        with self.lock:
            self._node("remove", address)
            del self.nodes[address]
