# SPDX-License-Identifier: MIT

"""The app's own Data Layer nodes (for the PLC, HMIs and other apps), all under the app's root (its snap name).

Each node's value comes from a function, so nodes never hold a copy that can go stale. A node is writable
when it has a write function; that validates (ValueError -> DL_INVALID_VALUE) and returns the stored value.

    registry = NodeRegistry(provider, "my-app", log)
    registry.add("counter", "Worker cycles", "uint64", lambda: core.counter)
    registry.add("setpoint", "Setpoint in mm", "float64", lambda: core.setpoint, write=core.set_setpoint)
    registry.add("state", "App state", "json", core.state)                  # JSON text, for structures
    registry.add_command("activate", "Write a name to activate it", core.activate)
    registry.sync(kinematics, lambda kin: registry.add(f"kin/{kin}/state", ..., group=kin))

Types: bool8, int64, uint64, float64, string, json (published as a string), array-of-<bool8|int64|float64|string>.
"""

import json
import threading

from comm.datalayer import NodeClass
from ctrlxdatalayer.metadata_utils import AllowedOperation, MetadataBuilder, ReferenceType
from ctrlxdatalayer.provider_node import NodeCallback, ProviderNode, ProviderNodeCallbacks
from ctrlxdatalayer.variant import Result, Variant, VariantType

TYPES = {"bool8", "int64", "uint64", "float64", "string", "json",
         "array-of-bool8", "array-of-int64", "array-of-float64", "array-of-string"}
INVALID_VALUE = getattr(Result, "INVALID_VALUE", Result.FAILED)


def metadata(description: str, type_name: str, writable=False) -> Variant:
    ops = AllowedOperation.READ | AllowedOperation.BROWSE
    if writable:
        ops |= AllowedOperation.WRITE
    published = "string" if type_name == "json" else type_name
    builder = MetadataBuilder(allowed=ops, description=description)
    builder.set_node_class(NodeClass.NodeClass.Variable)
    builder.add_reference(ReferenceType.read(), f"types/datalayer/{published}")
    if writable:
        builder.add_reference(ReferenceType.write(), f"types/datalayer/{published}")
    return builder.build()


def fill(v: Variant, type_name: str, value):
    """Put a Python value into a Variant as type_name."""
    if type_name == "json":
        v.set_string(json.dumps(value))
    elif type_name == "string":
        v.set_string(value if isinstance(value, str) else json.dumps(value))
    elif type_name == "bool8":
        v.set_bool8(bool(value))
    elif type_name in ("int64", "uint64"):
        getattr(v, "set_" + type_name)(int(value))
    elif type_name == "float64":
        v.set_float64(float(value))
    elif type_name.startswith("array-of-"):
        element = type_name[len("array-of-"):]
        conv = {"bool8": bool, "int64": int, "float64": float, "string": str}[element]
        getattr(v, "set_array_" + element)([conv(x) for x in value])
    else:
        raise ValueError(f"unknown node type {type_name}")


def written(v: Variant, type_name: str):
    """The Python value of a write to a type_name node. TypeError if the Variant's type doesn't fit (any number
    width fits a number node: the web UI and PLCs send different ones), ValueError if the value doesn't."""
    t = v.get_type()
    name = t.name if t is not None else ""
    number = name.startswith(("INT", "UINT", "FLOAT"))
    if type_name in ("string", "json"):
        if t != VariantType.STRING:
            raise TypeError(name)
        text = v.get_string()
        if type_name == "string":
            return text
        try:
            return json.loads(text)
        except ValueError as e:
            raise ValueError(f"invalid JSON: {e}") from e
    if type_name == "bool8":
        if t != VariantType.BOOL8:
            raise TypeError(name)
        return v.get_bool8()
    if type_name in ("int64", "uint64", "float64"):
        if not number:
            raise TypeError(name)
        value = getattr(v, "get_" + name.lower())()
        if type_name == "float64":
            return float(value)
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{value} is not a whole number")
        if type_name == "uint64" and value < 0:
            raise ValueError(f"{value} is negative")
        return int(value)
    if type_name.startswith("array-of-"):
        if not name.startswith("ARRAY_"):
            raise TypeError(name)
        items = list(getattr(v, "get_" + name.lower())())
        element = type_name[len("array-of-"):]
        if element == "string" and name != "ARRAY_STRING" or element == "bool8" and name != "ARRAY_BOOL8":
            raise TypeError(name)
        if element in ("int64", "float64") and name in ("ARRAY_STRING", "ARRAY_BOOL8"):
            raise TypeError(name)
        return [{"bool8": bool, "int64": int, "float64": float, "string": str}[element](x) for x in items]
    raise TypeError(name)


class Node:
    """One node: read() gives its value; write(value), if given, stores a written value and returns it
    (None: the node is read again)."""

    def __init__(self, provider, address, description, type_name, read, write=None, log=print):
        if type_name not in TYPES:
            raise ValueError(f"{address}: unknown node type {type_name}")
        self.provider, self.address, self.description = provider, address, description
        self.type_name, self.read, self.write, self.log = type_name, read, write, log
        self.meta = metadata(description, type_name, writable=write is not None)
        self.node = ProviderNode(ProviderNodeCallbacks(self.on_create, self.on_remove, self.on_browse,
                                                       self.on_read, self.on_write, self.on_metadata))

    def register(self):
        return self.provider.register_node(self.address, self.node)

    def unregister(self):
        self.provider.unregister_node(self.address)

    def on_read(self, userdata, address, data, cb: NodeCallback):
        try:
            value = self.read()
            if value is None:
                raise ValueError("no value")
            with Variant() as v:
                fill(v, self.type_name, value)
                cb(Result.OK, v)
        except Exception as e:
            self.log(f"{address}: read failed: {e}")
            cb(Result.FAILED, None)

    def on_write(self, userdata, address, data: Variant, cb: NodeCallback):
        if self.write is None:
            cb(Result.PERMISSION_DENIED, None)
            return
        try:
            value = written(data, self.type_name)
        except TypeError:
            cb(Result.TYPE_MISMATCH, None)
            return
        except ValueError as e:
            self.log(f"{address}: write refused: {e}")
            cb(INVALID_VALUE, None)
            return
        try:
            stored = self.write(value)
            if stored is None:
                stored = self.read()
        except PermissionError as e:
            self.log(f"{address}: write refused: {e}")
            cb(Result.PERMISSION_DENIED, None)
            return
        except ValueError as e:
            self.log(f"{address}: write refused: {e}")
            cb(INVALID_VALUE, None)
            return
        except Exception as e:
            self.log(f"{address}: write failed: {e}")
            cb(Result.FAILED, None)
            return
        with Variant() as v:
            fill(v, self.type_name, stored)
            cb(Result.OK, v)

    def on_metadata(self, userdata, address, cb: NodeCallback):
        cb(Result.OK, self.meta)

    def on_browse(self, userdata, address, cb: NodeCallback):
        with Variant() as v:
            v.set_array_string([])
            cb(Result.OK, v)

    def on_create(self, userdata, address, data, cb):
        cb(Result.UNSUPPORTED, None)

    def on_remove(self, userdata, address, cb):
        cb(Result.UNSUPPORTED, None)


class NodeRegistry:
    """The app's nodes under root. Nodes added with a group (e.g. a kinematic's name) can be removed together;
    sync() keeps the groups in line with a list (nodes for new kinematics, none for vanished ones).
    Call clear() before the provider stops."""

    def __init__(self, provider, root: str, log=print):
        self.provider, self.root, self.log = provider, root.strip("/"), log
        self.lock = threading.RLock()
        self.nodes = {}               # address -> Node
        self.group_of = {}            # address -> group or None
        self.results = {}             # address -> last result text of a command node

    def address(self, path: str) -> str:
        return f"{self.root}/{path.strip('/')}"

    def add(self, path, description, type_name, read, write=None, group=None) -> Node:
        """Add a node at root/path (nothing happens if it's there already)."""
        address = self.address(path)
        with self.lock:
            if address in self.nodes:
                return self.nodes[address]
            node = Node(self.provider, address, description, type_name, read, write, log=self.log)
            if node.register() != Result.OK:
                self.log(f"Registering {address} failed")
            self.nodes[address] = node
            self.group_of[address] = group
            return node

    def add_command(self, path, description, run, group=None) -> Node:
        """A string node to write a command to: run(text) does it and returns a result text (None: "ok"); an
        exception refuses the write (DL_INVALID_VALUE) and gives "error: <text>". Reading gives the last result."""
        address = self.address(path)

        def write(text):
            try:
                result = run(text)
            except Exception as e:
                self.results[address] = f"error: {e}"
                self.log(f"{address}: {text!r} refused: {e}")
                raise ValueError(str(e)) from e
            self.results[address] = "ok" if result is None else str(result)
            return self.results[address]

        return self.add(path, description, "string", lambda: self.results.get(address, ""), write=write, group=group)

    def remove_group(self, group):
        with self.lock:
            for address in [a for a, g in self.group_of.items() if g == group]:
                self.nodes.pop(address).unregister()
                del self.group_of[address]
                self.results.pop(address, None)

    def groups(self) -> set:
        with self.lock:
            return {g for g in self.group_of.values() if g is not None}

    def sync(self, keys, build):
        """Remove the groups not in keys; call build(key) for each key that has no nodes yet."""
        keys = list(keys)
        with self.lock:
            for group in self.groups() - set(keys):
                self.remove_group(group)
            present = self.groups()
            for key in keys:
                if key not in present:
                    build(key)

    def clear(self):
        with self.lock:
            for node in self.nodes.values():
                node.unregister()
            self.nodes, self.group_of, self.results = {}, {}, {}
