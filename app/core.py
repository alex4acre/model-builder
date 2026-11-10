# SPDX-License-Identifier: MIT

"""The app's state: the configuration (config.json in the app data of the active configuration) and a cyclic worker.

Replace the example (a counter and a setpoint) with the app's own logic. The file handling (atomic writes, files
replaced from outside) is in app/framework/appdata.py.
"""

import os
import threading
import time

from app.framework.appdata import JsonFile

DEFAULTS = {"setpoint": 0.0, "cycle_s": 1.0, "note": ""}


class ConfigError(ValueError):
    pass


def validate(cfg: dict) -> dict:
    """The complete configuration from a (partial) one; ConfigError if a value is wrong."""
    out = dict(DEFAULTS)
    for key, value in cfg.items():
        if key not in DEFAULTS:
            raise ConfigError(f"unknown setting {key!r}")
        out[key] = value
    if isinstance(out["setpoint"], bool) or not isinstance(out["setpoint"], (int, float)):
        raise ConfigError('"setpoint" must be a number')
    out["setpoint"] = float(out["setpoint"])
    if isinstance(out["cycle_s"], bool) or not isinstance(out["cycle_s"], (int, float)) or not 0.05 <= out["cycle_s"] <= 60:
        raise ConfigError('"cycle_s" must be a number from 0.05 to 60')
    if not isinstance(out["note"], str):
        raise ConfigError('"note" must be text')
    return out


class Core:

    def __init__(self, data_dir: str, bus, log=print):
        self.bus = bus
        self.log = log
        self.lock = threading.RLock()
        self.settings = JsonFile(os.path.join(data_dir, "config.json"), validate, log)
        self.counter = 0
        self.started = time.time()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="worker", daemon=True)

    @property
    def config(self) -> dict:
        return self.settings.data

    # --- API used by web.py and provider.py -----------------------------------------------------------

    def update_config(self, changes: dict) -> dict:
        return self.settings.update(changes)

    def set_setpoint(self, value: float) -> float:
        return self.update_config({"setpoint": value})["setpoint"]

    def state(self) -> dict:
        with self.lock:
            return {"counter": self.counter, "setpoint": self.config["setpoint"],
                    "uptime_s": round(time.time() - self.started, 1), "connected": self.bus.is_connected()}

    # --- worker ------------------------------------------------------------------------------------

    def start(self):
        self._thread.start()

    def _run(self):
        while not self._stop.wait(self.config["cycle_s"]):
            with self.lock:
                self.counter += 1

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(5)
