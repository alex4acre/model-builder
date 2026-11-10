# SPDX-License-Identifier: MIT

"""The app's logic: projects (storage), generated models, zone check and the upload to the 3D viewer."""

import time

from app import motion, storage, xmlgen, zone
from app.framework.web import HttpError
from app.viewer import ViewerNotInstalled


class Core:

    def __init__(self, store: storage.ProjectStore, motion_factory, viewer_factory, log=print):
        self.store = store
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

    # --- state ------------------------------------------------------------------------------------

    def state(self) -> dict:
        return {"projects": len(self.store.list()), "generation": self.store.generation,
                "uptime_s": round(time.time() - self.started, 1)}

    def configuration_loaded(self):
        self.store.refresh()


def error_types():
    from app.viewer import ViewerError
    return ((storage.Conflict, 409), (ViewerNotInstalled, 503), (ViewerError, 502))
