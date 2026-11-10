# SPDX-License-Identifier: MIT

"""Files in the app data of the active configuration (<active configuration>/<app>/...).

ctrlX saves, loads and backs up this folder with the configuration, so:
- write atomically (name.tmp, then rename). *.tmp is an appPrivateFile in the package manifest, so a half-written
  file never ends up in a saved configuration;
- a file can be replaced from outside at any time (Manage app data, loading a configuration or a backup): notice it
  (changed()) and reload, never overwrite it with the old state.

    settings = JsonFile(os.path.join(data_dir, "config.json"), validate, log)
    settings.data                 # the validated content (validate(partial dict) -> complete dict)
    settings.update({"x": 1})     # validate, then write
    settings.reload_if_changed()  # call it now and then (the runtime's main loop does it for registered files)
"""

import json
import os
import threading


def atomic_write(path: str, data: bytes):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def file_id(path: str):
    """Changes whenever the file is written or replaced (None: it doesn't exist)."""
    try:
        st = os.stat(path)
        return st.st_ino, st.st_mtime_ns, st.st_size
    except FileNotFoundError:
        return None


class FileWatch:
    """Notices when a file was written by someone else than the app (for files the app reads itself, e.g. SQLite)."""

    def __init__(self, path: str):
        self.path = path
        self.seen = file_id(path)

    def changed(self) -> bool:
        now = file_id(self.path)
        if now == self.seen:
            return False
        self.seen = now
        return True

    def mark_written(self):
        """Call after the app wrote the file itself."""
        self.seen = file_id(self.path)


class JsonFile:
    """A JSON file with validated content: validate(dict) returns the complete content or raises ValueError.
    A missing or broken file gives validate({}) (the defaults) and a log line; it is not written until update()."""

    def __init__(self, path: str, validate=lambda d: d, log=print, indent=2):
        self.path, self.validate, self.log, self.indent = path, validate, log, indent
        self.lock = threading.RLock()
        self.watch = FileWatch(path)
        self.data = self._load()
        self.listeners = []           # called with the new data after a reload from outside

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                return self.validate(json.load(f))
        except FileNotFoundError:
            return self.validate({})
        except (ValueError, OSError) as e:
            self.log(f"{self.path}: {e}; using the defaults")
            return self.validate({})

    def save(self):
        with self.lock:
            atomic_write(self.path, json.dumps(self.data, indent=self.indent).encode("utf-8"))
            self.watch.mark_written()

    def update(self, changes: dict) -> dict:
        """Validate the merged content, write it, return a copy."""
        with self.lock:
            self.data = self.validate({**self.data, **changes})
            self.save()
            return dict(self.data)

    def replace(self, data: dict) -> dict:
        with self.lock:
            self.data = self.validate(dict(data))
            self.save()
            return dict(self.data)

    def reload_if_changed(self) -> bool:
        with self.lock:
            if not self.watch.changed():
                return False
            self.log(f"{os.path.basename(self.path)} changed, reloading")
            self.data = self._load()
            data = dict(self.data)
        for listener in self.listeners:
            listener(data)
        return True
