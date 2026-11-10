# SPDX-License-Identifier: MIT

"""REST API of model-builder under /model-builder/api/v1, and the UI from www/ (routing, errors, bodies, static files and the
active configuration's load/save hooks: app/framework/web.py).

Uploads: the whole body is read before any answer, also for errors (the ctrlX reverse proxy streams request bodies and
reuses connections); a body no handler wanted is drained in chunks."""

import app
from app.core import error_types
from app.framework.web import ApiHandler, HttpError

core = None          # set by main

MAX_MESH = 100 * 1024 * 1024
MAX_DRAIN = 600 * 1024 * 1024


def _flag(value: str) -> bool:
    return value.lower() in ("1", "true", "yes")


class RequestHandler(ApiHandler):
    BASE = "/" + app.NAME
    MAX_BODY = 8 * 1024 * 1024
    MAX_MESH = MAX_MESH
    ROUTES = [
        ("GET", r"/state", "get_state"),
        ("GET", r"/storage", "get_storage"),
        ("GET", r"/projects", "list_projects"),
        ("POST", r"/projects", "create_project"),
        ("GET", r"/projects/([^/]+)", "get_project"),
        ("PUT", r"/projects/([^/]+)", "put_project"),
        ("DELETE", r"/projects/([^/]+)", "delete_project"),
        ("POST", r"/projects/([^/]+)/rename", "rename_project"),
        ("POST", r"/projects/([^/]+)/duplicate", "duplicate_project"),
        ("POST", r"/projects/([^/]+)/move", "move_project"),
        ("GET", r"/projects/([^/]+)/meshes", "list_meshes"),
        ("PUT", r"/projects/([^/]+)/meshes/([^/]+)", "put_mesh"),
        ("GET", r"/projects/([^/]+)/meshes/([^/]+)", "get_mesh"),
        ("DELETE", r"/projects/([^/]+)/meshes/([^/]+)", "delete_mesh"),
        ("GET", r"/projects/([^/]+)/xml", "get_xml"),
        ("GET", r"/projects/([^/]+)/configuration", "get_configuration"),
        ("GET", r"/projects/([^/]+)/package", "get_package"),
        ("GET", r"/projects/([^/]+)/zone-check", "zone_check"),
        ("POST", r"/projects/([^/]+)/zone-fix", "zone_fix"),
        ("POST", r"/projects/([^/]+)/from-kinematic", "from_kinematic"),
        ("POST", r"/projects/([^/]+)/upload-to-viewer", "upload_to_viewer"),
        ("GET", r"/viewer/projects", "viewer_projects"),
        ("POST", r"/viewer/projects/([^/]+)/open", "viewer_open"),
        ("POST", r"/viewer/projects/([^/]+)/import", "viewer_import"),
        ("GET", r"/viewer/cache/([^/]+)", "viewer_cache"),
        ("POST", r"/viewer/zone", "viewer_zone"),
        ("GET", r"/motion/axes", "motion_axes"),
        ("GET", r"/motion/kinematics", "motion_kinematics"),
    ]

    # --- bodies -----------------------------------------------------------------------------------

    def drain_body(self):
        """Read (and drop) a body nobody used, in chunks; a body that is absurdly large closes the connection."""
        length = int(self.headers.get("Content-Length") or 0)
        if self._body_read or not length:
            return
        self._body_read = True
        if length > MAX_DRAIN:
            self.close_connection = True
            return
        left = length
        while left > 0:
            chunk = self.rfile.read(min(left, 1 << 20))
            if not chunk:
                self.close_connection = True
                break
            left -= len(chunk)

    def send_error_json(self, e):
        try:
            self.drain_body()                  # read the whole body BEFORE answering an error
        except OSError:
            self.close_connection = True
        super().send_error_json(e)

    # --- state / storage --------------------------------------------------------------------------

    def get_state(self):
        self.send_json(200, core.state())

    def get_storage(self):
        self.send_json(200, {"locations": [
            {"id": "config", "title": "Active configuration", "path": core.store.roots["config"], "in_backup": True,
             "note": "Part of ctrlX configurations and backups; large models make them large."},
            {"id": "common", "title": "This app only (not in backups)", "path": core.store.roots["common"], "in_backup": False,
             "note": "Stays on this device, is not saved with configurations or backups."}],
            "generation": core.store.generation})

    # --- projects ---------------------------------------------------------------------------------

    def list_projects(self):
        self.send_json(200, {"projects": core.store.list(), "generation": core.store.generation})

    def create_project(self):
        d = self.read_json()
        self.send_json(201, core.store.create(d.get("name"), d.get("location") or "config"))

    def get_project(self, name):
        self.send_json(200, core.store.get(name))

    def put_project(self, name):
        self.send_json(200, core.store.put(name, self.read_json()))

    def delete_project(self, name):
        core.store.delete(name)
        self.no_content()

    def rename_project(self, name):
        self.send_json(200, core.store.rename(name, self.read_json().get("name")))

    def duplicate_project(self, name):
        d = self.read_json()
        self.send_json(201, core.store.duplicate(name, d.get("name"), d.get("location")))

    def move_project(self, name):
        self.send_json(200, core.store.move(name, self.read_json().get("location")))

    # --- meshes -----------------------------------------------------------------------------------

    def list_meshes(self, name):
        self.send_json(200, {"sizes": core.store.mesh_sizes(name)})

    def put_mesh(self, name, file):
        core.store.find(name)
        data = self.read_body(self.MAX_MESH)
        self.send_json(200, core.store.put_mesh(name, file, data, self.q("unit", "mm")))

    def get_mesh(self, name, file):
        self.send_bytes(200, core.store.read_mesh(name, file), "model/stl")

    def delete_mesh(self, name, file):
        self.send_json(200, core.store.delete_mesh(name, file))

    # --- generated model --------------------------------------------------------------------------

    def get_xml(self, name):
        self.send_bytes(200, core.xml(name).encode("utf-8"), "text/xml; charset=utf-8")

    def get_configuration(self, name):
        self.send_json(200, core.generate(name)["configuration"])

    def get_package(self, name):
        self.send_file(core.package(name), name + ".zip", "application/zip")

    def zone_check(self, name):
        self.send_json(200, core.zone_check(name))

    def zone_fix(self, name):
        self.send_json(200, core.zone_fix(name))

    def from_kinematic(self, name):
        d = self.read_json()
        if not d.get("kinematic"):
            raise HttpError(400, '{"kinematic": <name>} is needed')
        self.send_json(200, core.from_kinematic(name, d["kinematic"], self.token()))

    def upload_to_viewer(self, name):
        replace = _flag(self.q("replace", "0"))
        as_name = self.q("as", "") or None     # upload under a new name (must be free)
        self.read_body()                       # an empty or {} body
        self.send_json(200, core.upload(name, self.token(), replace, as_name))

    # --- 3D viewer projects, read-only ------------------------------------------------------------

    def viewer_projects(self):
        self.send_json(200, {"projects": core.viewer_projects(self.token())})

    def viewer_open(self, name):
        self.read_body()
        self.send_json(200, core.viewer_open(name, self.token()))

    def viewer_import(self, name):
        d = self.read_json()
        self.send_json(201, core.import_viewer(name, d.get("name") or name, d.get("location") or "config",
                                               bool(d.get("confirm")), self.token()))

    def viewer_cache(self, file):
        path = core.viewer_file(file)
        with open(path, "rb") as f:
            self.send_bytes(200, f.read(), "model/stl" if path.lower().endswith(".stl") else "application/octet-stream")

    def viewer_zone(self):
        self.send_json(200, core.viewer_zone(self.read_json(), self.token()))

    # --- MOTION -----------------------------------------------------------------------------------

    def motion_axes(self):
        from app import motion
        self.send_json(200, {"axes": motion.axes(core.motion_factory(self.token()))})

    def motion_kinematics(self):
        from app import motion
        self.send_json(200, {"kinematics": motion.kinematics(core.motion_factory(self.token()))})

    # --- active configuration ---------------------------------------------------------------------

    def configuration_loaded(self):
        core.configuration_loaded()


RequestHandler.ERRORS = error_types()
