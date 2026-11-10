# SPDX-License-Identifier: MIT

"""The app's logic: projects (storage), generated models, zone check and the upload to the 3D viewer."""

import os
import shutil
import threading
import time

from app import motion, storage, viewanalysis, viewcache, xmlgen, zone
from app.framework.bus import BusError
from app.framework.web import HttpError
from app.viewer import ViewerNotInstalled


class Core:

    def __init__(self, store: storage.ProjectStore, motion_factory, viewer_factory, log=print, cache_root: str = None):
        self.store = store
        # one 3D viewer project at a time is kept (read-only view): $SNAP_COMMON/viewer-cache/<safe name>/
        self.cache_root = cache_root or os.path.join(os.path.dirname(store.roots["common"].rstrip(os.sep)), "viewer-cache")
        self.view = None                            # the opened viewer project (see viewcache.open_project)
        self.view_lock = threading.Lock()
        self.motion_factory = motion_factory        # token -> bus (browse/read of motion/...)
        self.viewer_factory = viewer_factory        # token -> RestViewer / FakeViewer
        self.log = log
        self.started = time.time()

    # --- generated model --------------------------------------------------------------------------

    def generate(self, name: str) -> dict:
        p = self.store.get(name)
        return xmlgen.generate(p, lambda f: self.store.read_mesh(name, f))

    def xml(self, name: str) -> str:
        return xmlgen.build_xml(self.store.get(name))

    def package(self, name: str) -> bytes:
        return xmlgen.package_zip(self.generate(name))

    # --- zone check -------------------------------------------------------------------------------

    def zone_check(self, name: str) -> dict:
        return zone.check(self.store.get(name))

    def zone_fix(self, name: str) -> dict:
        p = self.store.get(name)
        fixed = zone.fix(p)
        self.store.put(name, fixed)
        return {"project": self.store.get(name), "check": zone.check(self.store.get(name))}

    # --- MOTION -----------------------------------------------------------------------------------

    def from_kinematic(self, name: str, kinematic: str, token: str) -> dict:
        self.store.find(name)
        return motion.tree_from_kinematic(self.motion_factory(token), kinematic)

    # --- 3D viewer --------------------------------------------------------------------------------

    def upload(self, name: str, token: str, replace: bool) -> dict:
        gen = self.generate(name)
        viewer = self.viewer_factory(token)
        exists = name in viewer.projects()
        if exists and not replace:
            raise HttpError(409, f"The 3D viewer has a project named {name!r}. Uploading replaces its files, its axis "
                                 "bindings and its library picture.", "EXISTS")
        viewer.create(name, gen["files"])
        viewer.configure(name, gen["configuration"])         # always: a (re-)upload clears the bindings
        p = self.store.get(name)
        p.setdefault("extra", {})["uploaded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.store.put(name, p)
        bound = len(gen["configuration"]["ConfiguredAxis"])
        return {"name": name, "replaced": exists, "files": len(gen["files"]), "bound_axes": bound,
                "uploaded_at": p["extra"]["uploaded_at"]}

    # --- read-only view of existing 3D viewer projects ---------------------------------------------

    def viewer_projects(self, token: str) -> list:
        return sorted(str(n) for n in self.viewer_factory(token).projects())

    def viewer_open(self, name: str, token: str) -> dict:
        viewer = self.viewer_factory(token)
        if name not in [str(n) for n in viewer.projects()]:
            raise HttpError(404, f"The 3D viewer has no project named {name!r}")
        with self.view_lock:
            self.view = None
            try:
                v = viewcache.open_project(viewer, name, self.cache_root)
            except (viewcache.ExtractError, ValueError) as e:
                shutil.rmtree(self.cache_root, ignore_errors=True)
                raise HttpError(422, f"The project {name!r} cannot be shown: {e}", "VIEW_FAILED") from None
            self.view = v
        self.log(f"3D viewer project {name!r} opened read-only: {len(v['files'])} files")
        return {k: v[k] for k in v if k != "dir"}

    def viewer_file(self, file: str):
        v = self.view
        path = viewcache.find_file(v["dir"], file) if v else None
        if not path:
            raise HttpError(404, f"{file!r} is not in the opened viewer project")
        return path

    def viewer_zone(self, d: dict, token: str) -> dict:
        v = self.view
        if not v:
            raise HttpError(409, "No 3D viewer project is open", "NO_VIEW")
        if d.get("kinematic"):
            try:
                k = motion.kinematic_config(self.motion_factory(token), str(d["kinematic"]))
            except BusError as e:
                raise HttpError(404, f"The kinematic {d['kinematic']!r} cannot be read: {e}") from None
            axes = [(a["name"], -1.0 if a["dir"] == "-" else 1.0) for a in sorted(k["axes"], key=lambda a: a["index"])]
            kin_type = k["type"]
        else:
            axes = [(str(a["name"]), -1.0 if a.get("dir") == "-" else 1.0) for a in d.get("axes") or [] if isinstance(a, dict) and a.get("name")]
            kin_type = d.get("type") or {3: "Cartesian_XYZ", 2: "Cartesian_XY"}.get(len(axes), "")
            if not axes:
                raise HttpError(400, '{"kinematic": <name>} or {"axes": [{"name", "dir"}]} is needed')
        return viewanalysis.zone_check(v["xml"], v["configuration"], kin_type, axes)

    # --- state ------------------------------------------------------------------------------------

    def state(self) -> dict:
        return {"projects": len(self.store.list()), "generation": self.store.generation,
                "uptime_s": round(time.time() - self.started, 1)}

    def configuration_loaded(self):
        self.store.refresh()


def error_types():
    from app.viewer import ViewerError
    return ((storage.Conflict, 409), (ViewerNotInstalled, 503), (ViewerError, 502))
