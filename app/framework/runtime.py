# SPDX-License-Identifier: MIT

"""Start-up and shutdown of a ctrlX app, in the snap and on a development machine.

    rt = Runtime("my-app", env="MY_APP", port=12345, src=SRC)    # in app/main.py
    data_dir = rt.data_dir()            # <active configuration>/my-app (waits for it on boot)
    dl = rt.start_datalayer(fake=FakeBus)
    ...
    rt.serve(RequestHandler)            # unix socket for the proxy in the snap, TCP 127.0.0.1:<port> otherwise
    rt.every(5, settings.reload_if_changed)
    rt.at_stop(core.stop)
    rt.run()                            # until SIGTERM/SIGINT; then the at_stop functions, last added first

In the snap (SNAP_NAME is the app's name):  Data Layer over ipc://, web server on the proxy's unix socket.
On a development machine, with the app's environment prefix (env="MY_APP"):
    MY_APP_FAKE=1           simulated Data Layer (app.fake.FakeBus)
    DATALAYER_CONNECTION    else: a real ctrlX, e.g. tcp://boschrexroth:boschrexroth@192.168.1.1?sslport=443
                            (the library needs Ubuntu 24.04)
    MY_APP_PORT             TCP port of the web server (default: port)
    MY_APP_DATA             app data folder (default: <src>/data)
    MY_APP_COMMON           folder for data outside the configuration (default: <src>/data/common)
"""

import os
import signal
import threading
import time


class DataLayer:
    """The Data Layer system, the app's provider (None without one) and its client bus."""

    def __init__(self, system=None, provider=None, bus=None, connection=None):
        self.system, self.provider, self.bus, self.connection = system, provider, bus, connection
        self._clients = [bus] if bus is not None else []

    @property
    def fake(self) -> bool:
        return self.system is None

    def client(self):
        """Another client of the same system (e.g. one for background work that never gets a user token)."""
        if self.system is None:
            return self.bus
        from app.framework.bus import DatalayerBus
        bus = DatalayerBus(self.system, self.connection)
        self._clients.append(bus)
        return bus

    def close(self):
        if self.provider is not None:
            self.provider.stop()
            self.provider.close()
        for bus in self._clients:
            if hasattr(bus, "close"):
                bus.close()
        if self.system is not None:
            self.system.stop(False)


class Runtime:

    def __init__(self, name: str, env: str, port: int, src: str, log=None):
        self.name, self.env_prefix, self.src = name, env, src
        self.in_snap = os.environ.get("SNAP_NAME") == name
        self.port = int(self.env("PORT", port))
        self.stopping = threading.Event()
        self.log = log or (lambda message: print(message, flush=True))
        self._tasks = []              # [interval_s, function, next time]
        self._stops = []
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._signal)
            signal.signal(signal.SIGTERM, self._signal)

    def _signal(self, signum, frame):
        self.stopping.set()

    def env(self, key: str, default=None):
        """A development setting <ENV>_<key> (never used in the snap)."""
        if self.in_snap:
            return default
        return os.environ.get(f"{self.env_prefix}_{key}", default)

    @property
    def fake(self) -> bool:
        return bool(self.env("FAKE"))

    # --- folders -----------------------------------------------------------------------------------

    def data_dir(self) -> str:
        """The app data folder in the active configuration ("" if stopped while waiting for it on boot)."""
        if not self.in_snap:
            path = self.env("DATA", os.path.join(self.src, "data"))
        else:
            # the active configuration appears a little after the app starts on boot
            active = os.path.join(os.environ["SNAP_COMMON"], "solutions", "activeConfiguration")
            waited = 0
            while not os.path.isdir(active):
                if waited % 10 == 0:
                    self.log(f"Waiting for the active configuration {active}")
                if self.stopping.wait(1.0):
                    return ""
                waited += 1
            path = os.path.join(active, self.name)
        os.makedirs(path, exist_ok=True)
        return path

    def common_dir(self, sub: str = "") -> str:
        """For data that is not part of the configuration (large libraries, caches): $SNAP_COMMON/<sub>."""
        base = os.environ["SNAP_COMMON"] if self.in_snap else self.env("COMMON", os.path.join(self.src, "data", "common"))
        path = os.path.join(base, sub) if sub else base
        os.makedirs(path, exist_ok=True)
        return path

    def bundled(self, rel: str) -> str:
        """A file or folder shipped with the app (read-only in the snap): $SNAP/<rel>."""
        return os.path.join(os.environ["SNAP"] if self.in_snap else self.src, rel)

    # --- Data Layer --------------------------------------------------------------------------------

    def start_datalayer(self, fake=None, provider=True, provider_attempts=0) -> DataLayer:
        """The Data Layer: fake() in development mode (<ENV>_FAKE), else the library over ipc:// (snap) or
        DATALAYER_CONNECTION. The provider is retried every 5 s, at most provider_attempts times (0: until it
        starts; an app that works without its nodes should give up and run without them)."""
        if self.fake:
            if fake is None:
                raise SystemExit(f"{self.env_prefix}_FAKE is set, but the app has no simulated Data Layer")
            self.log("Using a simulated ctrlX (development mode)")
            return DataLayer(bus=fake())
        connection = "ipc://" if self.in_snap else os.environ.get("DATALAYER_CONNECTION")
        if not connection:
            raise SystemExit(f"Set {self.env_prefix}_FAKE=1 (simulated ctrlX) or DATALAYER_CONNECTION")
        import ctrlxdatalayer
        from app.framework.bus import DatalayerBus
        system = ctrlxdatalayer.system.System("")
        system.start(False)
        dl = DataLayer(system, None, DatalayerBus(system, connection), connection)
        attempt = 0
        while provider and not self.stopping.is_set():
            p = system.factory().create_provider(connection)
            if p.start() == ctrlxdatalayer.variant.Result.OK:
                dl.provider = p
                break
            p.close()
            attempt += 1
            if provider_attempts and attempt >= provider_attempts:
                self.log("Starting the Data Layer provider failed; running without the app's nodes")
                break
            self.log("Starting the Data Layer provider failed, retrying in 5 s")
            self.stopping.wait(5)
        return dl

    # --- web server --------------------------------------------------------------------------------

    def serve(self, handler_class):
        """Serve handler_class in a thread; it is shut down when the app stops."""
        from app.framework import web
        if self.in_snap:
            # the ctrlX reverse proxy forwards /<app> to this socket (package-manifest.json, proxyMapping)
            sock_dir = os.path.join(os.environ["SNAP_DATA"], "package-run", self.name)
            os.makedirs(sock_dir, exist_ok=True)
            sock_file = os.path.join(sock_dir, "web.sock")
            try:
                os.unlink(sock_file)
            except OSError:
                pass
            server = web.UnixSocketServer(sock_file, handler_class)
            self.log(f"Listening on {sock_file}")
        else:
            server = web.TcpServer(("127.0.0.1", self.port), handler_class)
            self.log(f"Listening on http://127.0.0.1:{self.port}{handler_class.BASE}/?token=dev")
        threading.Thread(target=server.serve_forever, name="web", daemon=True).start()

        def stop():
            server.shutdown()
            server.server_close()
        self.at_stop(stop)
        return server

    # --- main loop ---------------------------------------------------------------------------------

    def every(self, interval_s: float, function):
        """Call function every interval_s seconds from the main loop (an exception is logged, not fatal)."""
        self._tasks.append([interval_s, function, time.monotonic() + interval_s])

    def at_stop(self, function):
        """Call function when the app stops (the last added is called first)."""
        self._stops.append(function)

    def run(self):
        while True:
            due = min((task[2] for task in self._tasks), default=time.monotonic() + 0.5)
            if self.stopping.wait(max(0.0, min(0.5, due - time.monotonic()))):
                break
            now = time.monotonic()
            for task in self._tasks:
                if now >= task[2]:
                    task[2] = now + task[0]
                    try:
                        task[1]()
                    except Exception as e:
                        self.log(f"{getattr(task[1], '__qualname__', task[1])}: {e}")
        self.shutdown()

    def shutdown(self):
        while self._stops:
            function = self._stops.pop()
            try:
                function()
            except Exception as e:
                self.log(f"Stopping: {e}")
        self.log("Stopped")
