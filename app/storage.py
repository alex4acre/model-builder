# SPDX-License-Identifier: MIT

"""Project storage (decision D2). A project is a folder <root>/<name>/ with project.json and meshes/*.stl.

Two roots:
  "config"  the app data of the active configuration (saved with ctrlX configurations and backups)
  "common"  $SNAP_COMMON/projects (not part of a backup)
Names are unique across both roots (case-insensitive). The lists are read from disk on every call, so a configuration
that was loaded or a folder replaced from outside shows at once.
"""

import json
import os
import shutil
import threading

from app import project as proj
from app.framework.appdata import atomic_write

LOCATIONS = ("config", "common")


class Conflict(Exception):
    """A name is taken."""


def folder_size(path: str) -> int:
    total = 0
    for base, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total


class ProjectStore:

    def __init__(self, config_root: str, common_root: str):
        self.roots = {"config": config_root, "common": common_root}
        for r in self.roots.values():
            os.makedirs(r, exist_ok=True)
        self.lock = threading.RLock()
        self.generation = 0

    def refresh(self):
        """The active configuration changed: nothing is cached, only the generation number tells clients to reload."""
        self.generation += 1

    # --- lookup -----------------------------------------------------------------------------------

    def _names(self):
        for loc, root in self.roots.items():
            try:
                entries = sorted(os.listdir(root))
            except OSError:
                entries = []
            for n in entries:
                if os.path.isfile(os.path.join(root, n, "project.json")):
                    yield n, loc

    def find(self, name: str) -> str:
        """The location of the project; KeyError if there is none."""
        proj.check_name(name)
        for n, loc in self._names():
            if n == name:
                return loc
        raise KeyError(f"Project {name!r} not found")

    def folder(self, name: str, location: str = None) -> str:
        proj.check_name(name)
        return os.path.join(self.roots[location or self.find(name)], name)

    def _taken(self, name: str) -> bool:
        low = name.lower()
        return any(n.lower() == low for n, _ in self._names())

    def _new_name(self, name: str) -> str:
        proj.check_name(name)
        if self._taken(name):
            raise Conflict(f"A project named {name!r} exists already (names are unique in both locations)")
        return name

    @staticmethod
    def _check_location(location) -> str:
        if location not in LOCATIONS:
            raise ValueError("The location is 'config' (active configuration, in backups) or 'common' (not in backups)")
        return location

    # --- list / read ------------------------------------------------------------------------------

    def list(self) -> list:
        out = []
        for n, loc in self._names():
            d = os.path.join(self.roots[loc], n)
            try:
                with open(os.path.join(d, "project.json"), encoding="utf-8") as f:
                    p = json.load(f)
            except (OSError, ValueError):
                p = {}
            out.append({"name": n, "location": loc, "size": folder_size(d), "meshes": len(p.get("meshes") or {}),
                        "kinematic": (p.get("kinematic") or {}).get("name") if isinstance(p.get("kinematic"), dict) else None,
                        "uploaded_at": (p.get("extra") or {}).get("uploaded_at") if isinstance(p.get("extra"), dict) else None})
        return out

    def get(self, name: str) -> dict:
        with self.lock:
            loc = self.find(name)
            with open(os.path.join(self.folder(name, loc), "project.json"), encoding="utf-8") as f:
                p = json.load(f)
            p["name"] = name
            p["location"] = loc
            return p

    def _write(self, name: str, location: str, p: dict):
        p = dict(p)
        p.pop("location", None)             # derived from where the folder is
        atomic_write(os.path.join(self.roots[location], name, "project.json"),
                     json.dumps(p, indent=1).encode("utf-8"))

    # --- create / change --------------------------------------------------------------------------

    def create(self, name: str, location: str) -> dict:
        with self.lock:
            self._check_location(location)
            self._new_name(name)
            os.makedirs(os.path.join(self.roots[location], name, "meshes"))
            self._write(name, location, proj.new_project(name, location))
            return self.get(name)

    def put(self, name: str, p: dict) -> dict:
        """Save the project document (validated). The name and location come from the URL / the folder."""
        with self.lock:
            loc = self.find(name)
            p = dict(p)
            p["name"] = name
            checked = proj.validate(p)
            # the files must exist for the meshes the document names
            self._write(name, loc, checked)
            return self.get(name)

    def rename(self, name: str, new: str) -> dict:
        with self.lock:
            loc = self.find(name)
            if new.lower() != name.lower():
                self._new_name(new)
            else:
                proj.check_name(new)
            p = self.get(name)
            os.rename(self.folder(name, loc), os.path.join(self.roots[loc], new))
            p["name"] = new
            self._write(new, loc, p)
            return self.get(new)

    def duplicate(self, name: str, new: str, location: str = None) -> dict:
        with self.lock:
            src_loc = self.find(name)
            loc = self._check_location(location or src_loc)
            self._new_name(new)
            tmp = os.path.join(self.roots[loc], new + ".tmp-copy")
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(self.folder(name, src_loc), tmp)
            os.rename(tmp, os.path.join(self.roots[loc], new))
            p = self.get(new)
            p["name"] = new
            (p.setdefault("extra", {})).pop("uploaded_at", None)
            self._write(new, loc, p)
            return self.get(new)

    def delete(self, name: str):
        with self.lock:
            shutil.rmtree(self.folder(name, self.find(name)))

    def move(self, name: str, location: str) -> dict:
        with self.lock:
            location = self._check_location(location)
            src = self.find(name)
            if src == location:
                return self.get(name)
            tmp = os.path.join(self.roots[location], name + ".tmp-copy")
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(self.folder(name, src), tmp)
            os.rename(tmp, os.path.join(self.roots[location], name))
            shutil.rmtree(self.folder(name, src))
            return self.get(name)

    # --- meshes -----------------------------------------------------------------------------------

    def mesh_path(self, name: str, file: str) -> str:
        proj.check_mesh_file(file)
        return os.path.join(self.folder(name), "meshes", file)

    def put_mesh(self, name: str, file: str, data: bytes, unit: str = "mm") -> dict:
        """Store an STL and make sure the project has a mesh entry for it."""
        with self.lock:
            if unit not in proj.UNITS:
                raise ValueError(f"The unit is one of {', '.join(proj.UNITS)}")
            check_stl(data)
            path = self.mesh_path(name, file)
            atomic_write(path, data)
            p = self.get(name)
            existing = next((m for m in p["meshes"].values() if m["file"].lower() == file.lower()), None)
            if existing is None:
                base = os.path.splitext(file)[0]
                mid, i = base, 2
                while mid in p["meshes"]:
                    mid, i = f"{base}_{i}", i + 1
                p["meshes"][mid] = {"file": file, "unit": unit, "placement": {"position": [0, 0, 0], "rotation": [0, 0, 0]}}
            else:
                existing["unit"] = unit
            self._write(name, self.find(name), proj.validate(p))
            return self.get(name)

    def read_mesh(self, name: str, file: str) -> bytes:
        path = self.mesh_path(name, file)
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise KeyError(f"Mesh {file!r} not found") from None

    def delete_mesh(self, name: str, file: str) -> dict:
        with self.lock:
            p = self.get(name)
            ids = [mid for mid, m in p["meshes"].items() if m["file"] == file]
            used = [n["name"] for n in _walk(p["tree"]) if n.get("kind") == "part" and n.get("mesh") in ids]
            if used:
                raise Conflict(f"The mesh is used by {', '.join(used)}: delete those parts first")
            for mid in ids:
                del p["meshes"][mid]
            try:
                os.remove(self.mesh_path(name, file))
            except FileNotFoundError:
                pass
            self._write(name, self.find(name), p)
            return self.get(name)

    def mesh_sizes(self, name: str) -> dict:
        d = os.path.join(self.folder(name), "meshes")
        try:
            return {f: os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)}
        except OSError:
            return {}


def _walk(tree):
    for n in tree:
        yield n
        yield from _walk(n.get("children") or [])


def check_stl(data: bytes):
    """ValueError unless data looks like an STL (binary: 80 byte header, triangle count, 50 bytes per triangle; or ASCII)."""
    if len(data) < 15:
        raise ValueError("The file is empty or too short for an STL")
    if len(data) >= 84:
        n = int.from_bytes(data[80:84], "little")
        if 84 + 50 * n == len(data) and n > 0:
            return
    head = data[:512].lstrip().lower()
    if head.startswith(b"solid") and b"facet" in data[:4096].lower():
        return
    raise ValueError("The file is not a valid STL (binary or ASCII)")
