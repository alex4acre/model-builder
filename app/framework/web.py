# SPDX-License-Identifier: MIT

"""HTTP server for the web UI and REST API, behind the ctrlX reverse proxy at /<app>.

The app's app/web.py subclasses ApiHandler with its BASE ("/<app>"), ROUTES and handler methods:

    class RequestHandler(ApiHandler):
        BASE = "/my-app"
        ROUTES = [("GET", r"/state", "get_state"), ("PUT", r"/items/([^/]+)", "put_item")]
        ERRORS = ((ItemLocked, 409),)                # app exceptions -> HTTP status, checked first

        def put_item(self, name):                    # groups of the pattern come in URL-decoded
            self.send_json(200, core.put(name, self.read_json()))

Routes are matched below /<app>/api/v1. The proxy checks the bearer token for the "restricted" paths of the
package manifest (/<app>/api), so handlers only see authenticated requests; self.token() is the caller's token,
to call the ctrlX REST API or the Data Layer with the caller's permissions.

Errors answer {"error": text} (plus "code" where there is one, e.g. the Data Layer result):
HttpError -> its status; ERRORS; BusError -> 403 for DL_PERMISSION_DENIED, else 502; KeyError -> 404;
ValueError -> 400; anything else -> 500 with the traceback in the log.
"""

import http.server
import json
import mimetypes
import os
import re
import socketserver
import traceback
from urllib.parse import parse_qs, unquote, urlparse

from app.framework.bus import BusError

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")


class HttpError(Exception):
    def __init__(self, status: int, message: str, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


class ApiHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    BASE = ""                 # "/<app>", set by the app
    ROUTES = []               # (method, pattern below BASE/api/v1, handler method name)
    ERRORS = ()               # ((exception class, HTTP status), ...)
    VIEWS = ()                # more paths below BASE that serve index.html (e.g. "/tools" for a second sidebar entry)
    MAX_BODY = 1024 * 1024    # read_json limit; read_body(limit) for uploads
    www_dir = None            # set by the app's main

    # the active configuration's load/save hooks of the package manifest
    FRAMEWORK_ROUTES = [("POST", r"/admin/cfg/load", "cfg_load"), ("POST", r"/admin/cfg/save", "cfg_save")]

    def log_message(self, fmt, *args):
        pass  # keep the journal for app messages

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method: str):
        self._body_read = False
        url = urlparse(self.path)
        path = url.path
        self.query = parse_qs(url.query)
        api = self.BASE + "/api/v1"
        try:
            if path.startswith(api + "/") or path == api:
                return self.route(method, path[len(api):].rstrip("/"))
            if method == "GET" and (path == self.BASE or path.startswith(self.BASE + "/")):
                rel = path[len(self.BASE):]
                if rel in ("", "/") or rel in self.VIEWS:
                    return self.send_static("index.html")
                return self.send_static(rel.lstrip("/"))
            raise HttpError(404, "Not found")
        except Exception as e:
            self.send_error_json(e)
        finally:
            self.drain_body()

    def route(self, method: str, sub: str):
        matched = False
        for route_method, pattern, handler in list(self.ROUTES) + self.FRAMEWORK_ROUTES:
            m = re.fullmatch(pattern, sub)
            if m:
                matched = True
                if route_method == method:
                    return getattr(self, handler)(*[unquote(g) for g in m.groups()])
        raise HttpError(405 if matched else 404, "Method not allowed" if matched else "Not found")

    def send_error_json(self, e: Exception):
        for cls, status in self.ERRORS:
            if isinstance(e, cls):
                return self.send_json(status, self.error_body(e))
        if isinstance(e, HttpError):
            return self.send_json(e.status, self.error_body(e))
        if isinstance(e, BusError):
            return self.send_json(403 if e.code == "DL_PERMISSION_DENIED" else 502, self.error_body(e))
        if isinstance(e, KeyError):
            return self.send_json(404, {"error": str(e.args[0]) if e.args else "Not found"})
        if isinstance(e, ValueError):
            return self.send_json(400, self.error_body(e))
        traceback.print_exc()
        self.send_json(500, {"error": str(e) or type(e).__name__})

    @staticmethod
    def error_body(e: Exception) -> dict:
        body = {"error": str(e)}
        code = getattr(e, "code", "")
        if code:
            body["code"] = code
        return body

    def drain_body(self):
        """Read a request body the handler didn't use. The ctrlX reverse proxy reuses the connection, and a left-over
        body (e.g. the "{}" of a POST) would otherwise be read as the start of the next request ("501 {}GET")."""
        length = int(self.headers.get("Content-Length") or 0)
        if self._body_read or not length:
            return
        if length > 16 * self.MAX_BODY:
            self.close_connection = True
        else:
            self.rfile.read(length)

    # --- helpers ---------------------------------------------------------------------------------

    def q(self, name, default=""):
        """A query parameter."""
        return (self.query.get(name) or [default])[0]

    def token(self) -> str:
        """The caller's bearer token (the proxy has checked it for /<app>/api)."""
        auth = self.headers.get("Authorization") or ""
        if not auth.lower().startswith("bearer "):
            raise HttpError(401, "Missing bearer token")
        return auth[7:].strip()

    def read_body(self, limit=None) -> bytes:
        """The raw request body (uploads); 413 above limit (default MAX_BODY)."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > (limit or self.MAX_BODY):
            raise HttpError(413, "Request body too large")
        self._body_read = True
        return self.rfile.read(length) if length else b""

    def read_json(self, kind=dict):
        """The JSON body; 400 unless it is a kind (dict, list, or None for anything)."""
        raw = self.read_body()
        try:
            data = json.loads(raw or b"null")
        except ValueError as e:
            raise HttpError(400, f"Invalid JSON: {e}") from e
        if kind is not None and not isinstance(data, kind):
            raise HttpError(400, f"A JSON {'object' if kind is dict else kind.__name__} is expected")
        return data

    def send_bytes(self, status, body: bytes, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, obj):
        self.send_bytes(status, json.dumps(obj).encode("utf-8"), "application/json")

    def send_file(self, data: bytes, filename: str, content_type="application/octet-stream"):
        """A download (the browser saves it as filename)."""
        safe = re.sub(r'[^A-Za-z0-9._-]', "_", filename) or "download"
        self.send_bytes(200, data, content_type, {"Content-Disposition": f'attachment; filename="{safe}"'})

    def no_content(self):
        self.send_bytes(204, b"", "application/json")

    def send_static(self, rel):
        root = os.path.realpath(self.www_dir)
        full = os.path.realpath(os.path.join(root, rel))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            raise HttpError(404, "Not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self.send_bytes(200, f.read(), ctype)

    # --- active configuration (ctrlX calls these when a configuration is loaded or saved) ---------

    def configuration_loaded(self):
        """Override: pick up the app data of a configuration that was just loaded."""

    def configuration_saving(self):
        """Override: write pending state into the app data before ctrlX saves the configuration."""

    def cfg_load(self):
        data = self.read_json(kind=None) or {}
        if isinstance(data, dict) and data.get("phase") == "load":
            self.configuration_loaded()
        self.no_content()

    def cfg_save(self):
        self.read_json(kind=None)
        self.configuration_saving()
        self.no_content()


class UnixSocketServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def get_request(self):
        request, _ = super().get_request()
        return request, ("local", 0)


class TcpServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
