# SPDX-License-Identifier: MIT

"""REST API of model-builder under /model-builder/api/v1, and the UI from www/ (routing, errors, bodies, static files and the
active configuration's load/save hooks: app/framework/web.py)."""

import app
from app.framework.web import ApiHandler, HttpError

core = None          # set by main


class RequestHandler(ApiHandler):
    BASE = "/" + app.NAME
    ROUTES = [
        ("GET", r"/state", "get_state"),
        ("GET", r"/config", "get_config"),
        ("PATCH", r"/config", "patch_config"),
        ("GET", r"/browse", "browse"),
        ("GET", r"/node", "read_node"),
        ("PUT", r"/node", "write_node"),
    ]

    def get_state(self):
        self.send_json(200, core.state())

    def get_config(self):
        self.send_json(200, core.config)

    def patch_config(self):
        self.send_json(200, core.update_config(self.read_json()))

    # --- Data Layer access (an example of using the client bus) ---------------------------------

    def browse(self):
        path = self.q("path")
        self.send_json(200, {"path": path, "children": core.bus.browse(path)})

    def read_node(self):
        path = self.q("path")
        if not path:
            raise HttpError(400, "path is missing")
        self.send_json(200, {"path": path, "value": core.bus.read(path)})

    def write_node(self):
        path = self.q("path")
        d = self.read_json()
        if not path or "value" not in d:
            raise HttpError(400, 'path and {"value": ...} are needed')
        core.bus.write(path, d["value"])
        self.send_json(200, {"path": path, "value": core.bus.read(path)})

    # --- active configuration --------------------------------------------------------------------

    def configuration_loaded(self):
        core.settings.reload_if_changed()
