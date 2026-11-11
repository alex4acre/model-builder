# SPDX-License-Identifier: MIT

"""The app's logic: projects (storage), generated models, zone check and the upload to the 3D viewer."""

import os
import shutil
import threading
import time

from app import merge, motion, project as proj, storage, viewanalysis, viewcache, xmlgen, xmlimport, zone
from app.framework.bus import BusError
from app.framework.web import HttpError
from app.viewer import ViewerError, ViewerNotInstalled


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

    def generate(self, name: str, viewer_name: str = None) -> dict:
        p = self.store.get(name)
        return xmlgen.generate(p, lambda f: self.store.read_mesh(name, f), viewer_name)

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

    def upload(self, name: str, token: str, replace: bool, as_name: str = None) -> dict:
        """Send the project to the 3D viewer under its viewer name (default: the project's name). as_name: a new name that
        must be free; it becomes the project's viewer name."""
        p = self.store.get(name)
        viewer = self.viewer_factory(token)
        if as_name is not None:
            proj.check_name(as_name)
            target = as_name
        else:
            target = p.get("viewer_name") or name
        exists = target in [str(n) for n in viewer.projects()]
        if as_name is not None and exists:
            raise HttpError(409, f"The 3D viewer has a project named {target!r} already; choose another name.", "NAME_TAKEN")
        if exists and not replace:
            raise HttpError(409, f"Replaces {target} in the 3D viewer: its files are replaced. The viewer's own bindings (Data Layer "
                                 "values on axes this app leaves unbound) and its visual effects, safe zones and other settings are "
                                 "kept; the axes bound here are sent again and the library picture is redrawn.", "EXISTS")
        gen = self.generate(name, target)
        current = None
        if exists:
            # read what the viewer has BEFORE the upload clears it; if that fails nothing is changed
            try:
                current = viewer.project_configuration(target)
            except ViewerNotInstalled:
                raise
            except ViewerError as e:
                raise ViewerError(f"The settings the 3D viewer has for {target!r} cannot be read ({e}); nothing was uploaded, so "
                                  "they are not lost", e.path, e.status) from None
        cfg = gen["configuration"]
        bound_names = {a["name"] for a in xmlgen.axis_nodes(p) if a.get("binding")}
        sent_all = (p.get("extra") or {}).get("sent_bindings") or {}
        report = None
        if exists and current is not None:
            cfg, report = merge.merge_configuration(cfg, current, [a["name"] for a in xmlgen.axis_nodes(p)], bound_names,
                                                    sent_all.get(target) or {})
        viewer.create(target, gen["files"])
        viewer.configure(target, cfg)         # always: a (re-)upload clears the bindings
        p = self.store.get(name)
        p["viewer_name"] = target
        extra = p.setdefault("extra", {})
        extra["uploaded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # what this app sent per axis: a viewer entry that is still exactly that after the user cleared the binding here is dropped
        sent = {e["ModelAxisName"]: e for e in cfg["ConfiguredAxis"] if e["ModelAxisName"] in bound_names}
        extra["sent_bindings"] = {**{k: v for k, v in (extra.get("sent_bindings") or {}).items() if k != target}, target: sent}
        self.store.put(name, p)
        bound = len(sent)
        res = {"name": name, "viewer_name": target, "replaced": exists, "files": len(gen["files"]), "bound_axes": bound,
               "missing_meshes": gen["missing"], "uploaded_at": extra["uploaded_at"],
               "kept_bindings": [], "cleared_bindings": [], "dropped_bindings": [], "kept_settings": []}
        if report:
            res.update(kept_bindings=report["kept_bindings"], cleared_bindings=report["cleared"],
                       dropped_bindings=report["dropped"], kept_settings=report["kept_settings"])
        return res

    def viewer_state(self, name: str, token: str) -> dict:
        """What the 3D viewer currently has for the unbound axes of the project's viewer project (read only)."""
        p = self.store.get(name)
        target = p.get("viewer_name") or name
        viewer = self.viewer_factory(token)
        if target not in [str(n) for n in viewer.projects()]:
            return {"viewer_name": target, "exists": False, "bindings": {}}
        cfg = viewer.project_configuration(target) or {}
        bound = {a["name"] for a in xmlgen.axis_nodes(p) if a.get("binding")}
        names = {a["name"] for a in xmlgen.axis_nodes(p)}
        out = {}
        for e in cfg.get("ConfiguredAxis") or []:
            n = e.get("ModelAxisName") if isinstance(e, dict) else None
            if n in names and n not in bound and (e.get("DatalayerNode") or e.get("DatalayerVariable")):
                out[n] = {"type": e.get("ConnectionType") or "", "node": e.get("DatalayerNode") or "",
                          "variable": e.get("DatalayerVariable") or "", "script": e.get("ExpressionScript") or ""}
        return {"viewer_name": target, "exists": True, "bindings": out}

    # --- import of a viewer project as an editable project ------------------------------------------

    def import_viewer(self, viewer_name: str, name: str, location: str, confirm: bool, token: str) -> dict:
        """Download the viewer project into a temporary folder (the read-only view's cache is not touched), convert it and
        create the project. If the conversion has to drop something, nothing is created until confirm is true."""
        name = (name or viewer_name).strip()
        proj.check_name(name)
        if location not in storage.LOCATIONS:
            raise HttpError(400, "The location is 'config' or 'common'")
        self.store._new_name(name)                       # Conflict (409) before anything is downloaded
        viewer = self.viewer_factory(token)
        if viewer_name not in [str(n) for n in viewer.projects()]:
            raise HttpError(404, f"The 3D viewer has no project named {viewer_name!r}")
        tmp = os.path.join(os.path.dirname(self.cache_root.rstrip(os.sep)), "import-tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            try:
                v = viewcache.open_project(viewer, viewer_name, tmp)
                conv = xmlimport.convert(v["xml"], v["configuration"], [f["name"] for f in v["files"]])
            except (viewcache.ExtractError, xmlimport.ImportProblem) as e:
                raise HttpError(422, f"The project {viewer_name!r} cannot be imported: {e}", "IMPORT_FAILED") from None
            report = conv["report"]
            if report["dropped"] and not confirm:
                raise HttpError(409, "Importing would drop: " + "; ".join(report["dropped"]), "DROPS")
            p = conv["project"]
            p["viewer_name"] = viewer_name
            p["extra"] = {"imported_from": viewer_name}
            try:
                created = self.store.import_project(name, location, p, {f: os.path.join(v["dir"], f) for f in conv["mesh_files"]})
            except ValueError as e:
                raise HttpError(422, f"The project {viewer_name!r} cannot be imported: {e}", "IMPORT_FAILED") from None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.log(f"3D viewer project {viewer_name!r} imported as {name!r}: {report['counts']}")
        return {"project": created, "report": report}

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
