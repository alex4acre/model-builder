# SPDX-License-Identifier: MIT

"""The Data Layer through the ctrlX REST API (/automation/api/v2/nodes), with the same interface as
framework.bus.DatalayerBus. Use it where an app works with the calling user's token and needs no client
library, or from a development machine against a real ctrlX (the library needs Ubuntu 24.04).

    bus = RestBus("https://localhost", token)        # in the snap: the core itself
    with bus.session(token) as b: b.read(...)        # the same with another user's token

Failures raise BusError with a Data Layer code, taken from the answer's problem details where it has one.
"""

import contextlib
import json
import ssl
import urllib.error
import urllib.request
from urllib.parse import quote

from app.framework.bus import BusError

NODES = "/automation/api/v2/nodes/"
STATUS_CODES = {400: "DL_INVALID_VALUE", 401: "DL_PERMISSION_DENIED", 403: "DL_PERMISSION_DENIED",
                404: "DL_INVALID_ADDRESS", 405: "DL_UNSUPPORTED", 408: "DL_TIMEOUT", 504: "DL_TIMEOUT"}


def core_opener():
    """An opener for the core's own self-signed certificate, never through a proxy (e.g. a company proxy
    set in the environment of a development machine)."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))


def problem(raw: bytes, status: int):
    """(text, code) of a REST error answer (RFC 7807 problem details as ctrlX sends them)."""
    try:
        p = json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")[:300] or f"HTTP {status}", STATUS_CODES.get(status, "DL_FAILED")
    if not isinstance(p, dict):
        return str(p)[:300], STATUS_CODES.get(status, "DL_FAILED")
    title = str(p.get("title") or "")
    code = title if title.startswith("DL_") else STATUS_CODES.get(status, "DL_FAILED")
    parts = [str(p[k]) for k in ("title", "detail", "dynamicDescription") if p.get(k)]
    return " - ".join(parts) or f"HTTP {status}", code


def rest_type(value) -> str:
    """The REST type for a Python value written without reading the node first (create)."""
    if isinstance(value, bool):
        return "bool8"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "float64"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
        return "arstring"
    if isinstance(value, list) and value and all(isinstance(x, bool) for x in value):
        return "arbool8"
    if isinstance(value, list) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value):
        return "arfloat64"
    return "object"


class RestBus:

    def __init__(self, base_url: str, token: str = "", timeout: float = 15.0):
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.opener = core_opener()

    def is_connected(self) -> bool:
        return True

    def close(self):
        pass

    @contextlib.contextmanager
    def session(self, token: str = ""):
        """The same calls with another user's token (a new bus, so concurrent sessions don't mix)."""
        yield RestBus(self.base, token or self.token, self.timeout) if token else self

    def call(self, method: str, path: str, body=None, query: str = ""):
        """Any ctrlX REST call (path from the host on, e.g. /automation/api/v2/nodes/...); the answer as JSON."""
        req = urllib.request.Request(self.base + path + query, method=method,
                                     data=None if body is None else json.dumps(body).encode("utf-8"))
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            text, code = problem(e.read(), e.code)
            raise BusError(f"{method} {path}: {text}", code) from None
        except (urllib.error.URLError, OSError) as e:
            raise BusError(f"Cannot reach the ctrlX CORE: {e}", "DL_CLIENT_NOT_CONNECTED") from None
        return json.loads(raw) if raw else None

    def _node(self, method, address, body=None, query=""):
        return self.call(method, NODES + quote(address.strip("/"), safe="/"), body, query)

    # --- the DatalayerBus interface -------------------------------------------------------------

    def browse(self, address: str) -> list:
        return list((self._node("GET", address, query="?type=browse") or {}).get("value") or [])

    def metadata(self, address: str) -> dict:
        doc = self._node("GET", address, query="?type=metadata") or {}
        if isinstance(doc.get("value"), dict):
            doc = doc["value"]
        refs = {r.get("type", ""): r.get("targetAddress", "") for r in doc.get("references") or []}
        return {"nodeClass": doc.get("nodeClass", ""), "operations": doc.get("operations") or {},
                "description": doc.get("description", ""), "references": refs}

    def read(self, address: str):
        return (self._node("GET", address) or {}).get("value")

    def read_typed(self, address: str):
        """(type, value), the type named as DatalayerBus names it ("int16", "array_float64", "flatbuffers")."""
        doc = self._node("GET", address) or {}
        t = str(doc.get("type", ""))
        if t == "object":
            t = "flatbuffers"
        elif t.startswith("ar"):
            t = "array_" + t[2:]
        return t, doc.get("value")

    def read_args(self, address: str, args: dict):
        # how the REST API takes read arguments is not verified on a device yet: refuse rather than guess
        raise BusError(f"read {address} with arguments: not supported over REST, use DatalayerBus", "DL_UNSUPPORTED")

    def write(self, address: str, value):
        """Writes in the node's current type (read first, as DatalayerBus does)."""
        t = (self._node("GET", address) or {}).get("type") or rest_type(value)
        self._node("PUT", address, {"type": t, "value": value})

    def write_json(self, address: str, value):
        self._node("PUT", address, {"type": "object", "value": value})

    def create(self, address: str, value):
        body = None if value is None else {"type": rest_type(value), "value": value}
        doc = self._node("POST", address, body)
        value = doc.get("value") if isinstance(doc, dict) and "value" in doc else doc
        if isinstance(value, dict) and set(value) == {"value"}:
            return value["value"]
        return value

    def remove(self, address: str):
        self._node("DELETE", address)
