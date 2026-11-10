# SPDX-License-Identifier: MIT

"""Upload of a generated model to the ctrlX 3D viewer app through the core's REST API (/3dviewer/api/v2). Copied from
robot-configurator/app/viewer_upload.py (device-tested there). Requests carry the calling user's token.

Measured on an X3 (2026-11-10, spike S2): a POST to an existing project name replaces its files and clears its axis
bindings and library picture, so the configuration is ALWAYS sent again after every create.
"""

import json
import urllib.error
import urllib.request
import uuid
from urllib.parse import quote

from app.framework.rest import core_opener, problem


class ViewerError(Exception):
    def __init__(self, message: str, path: str = "", status: int = 0):
        super().__init__(message)
        self.path, self.status = path, status


class ViewerNotInstalled(ViewerError):
    pass


NOT_INSTALLED = "The 3D viewer app is not installed on this ctrlX CORE (install it from the ctrlX app store or the 3D Viewer .app)"


def encode_multipart(files: dict):
    """(body, content type) of a multipart/form-data body with one form field "file" per file."""
    boundary = "----modelbuilder" + uuid.uuid4().hex
    body = bytearray()
    for name, data in files.items():
        kind = "text/xml" if name.endswith(".xml") else "application/octet-stream"
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                 f'Content-Type: {kind}\r\n\r\n').encode("utf-8") + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), "multipart/form-data; boundary=" + boundary


class RestViewer:

    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        self.base = base_url.rstrip("/") + "/3dviewer/api/v2"
        self.token = token
        self.timeout = timeout
        self.opener = core_opener()

    def _request(self, method: str, path: str, data=None, content_type="application/json") -> bytes:
        req = urllib.request.Request(self.base + path, method=method, data=data)
        req.add_header("Authorization", "Bearer " + self.token)
        if data is not None:
            req.add_header("Content-Type", content_type)
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            if e.code == 404 and path == "/projects":
                raise ViewerNotInstalled(NOT_INSTALLED, path, 404) from None
            raise ViewerError(problem(raw, e.code)[0], path, e.code) from None
        except (urllib.error.URLError, OSError) as e:
            raise ViewerError(f"Cannot reach the 3D viewer: {e}", path) from None

    def projects(self) -> list:
        raw = self._request("GET", "/projects")
        try:
            names = json.loads(raw)
        except ValueError:
            names = None
        if not isinstance(names, list):
            raise ViewerNotInstalled(NOT_INSTALLED, "/projects")
        return names

    def create(self, name: str, files: dict):
        body, content_type = encode_multipart(files)
        self._request("POST", "/projects", body, content_type)    # 201

    def configure(self, name: str, configuration: dict):
        self._request("PUT", f"/projects/{quote(name)}/configuration", json.dumps(configuration).encode())

    def delete(self, name: str):
        self._request("DELETE", f"/projects/{quote(name)}")


class FakeViewer:
    """In-memory 3D viewer for tests and development. installed=False behaves like a missing app."""

    def __init__(self, installed: bool = True):
        self.installed = installed
        self.store = {}          # project name -> {"files": {...}, "configuration": dict or None}
        self.log = []

    def projects(self) -> list:
        if not self.installed:
            raise ViewerNotInstalled(NOT_INSTALLED, "/projects", 404)
        return list(self.store)

    def create(self, name: str, files: dict):
        body, _ = encode_multipart(files)      # exercise the encoder
        # like the real viewer: an existing project is overwritten and its axis binding is reset
        self.store[name] = {"files": dict(files), "configuration": None, "body": body}
        self.log.append(("create", name))

    def configure(self, name: str, configuration: dict):
        if name not in self.store:
            raise ViewerError("Unknown project", f"/projects/{name}/configuration", 404)
        self.store[name]["configuration"] = json.loads(json.dumps(configuration))
        self.log.append(("configure", name))

    def delete(self, name: str):
        if name not in self.store:
            raise ViewerError("Unknown project", f"/projects/{name}", 404)
        del self.store[name]
        self.log.append(("delete", name))
