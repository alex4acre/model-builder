# SPDX-License-Identifier: MIT

"""3D Model Builder: Build 3D viewer models from STL files and bind them to ctrlX MOTION axes

In the snap: UI at https://<ctrlx>/model-builder, projects in the app data of the active configuration
(model-builder/projects/<name>/) or in $SNAP_COMMON/projects, Data Layer node model-builder/state.

Development with a simulated ctrlX:  MODEL_BUILDER_FAKE=1 python3 -m app.main
                                     -> http://127.0.0.1:12521/model-builder/?token=dev
Development against a real ctrlX:    MODEL_BUILDER_CTRLX=https://192.168.1.1 DATALAYER_CONNECTION=... python3 -m app.main
(more settings in app/framework/runtime.py)
"""

import os

import app
from app import web
from app.core import Core
from app.fake import FakeBus
from app.framework.runtime import Runtime
from app.framework.rest import RestBus
from app.storage import ProjectStore
from app.viewer import FakeViewer, RestViewer

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def factories(rt, dl):
    """(token -> bus for motion/..., token -> 3D viewer client): the caller's token against the core's REST API."""
    if rt.fake:
        fake_viewer = FakeViewer()
        return (lambda token: dl.bus), (lambda token: fake_viewer)
    url = "https://localhost" if rt.in_snap else rt.env("CTRLX", "https://localhost:8443")
    return (lambda token: RestBus(url, token)), (lambda token: RestViewer(url, token))


def main():
    rt = Runtime(app.NAME, env=app.ENV, port=app.PORT, src=SRC)
    data_dir = rt.data_dir()
    if not data_dir:
        return                                   # stopped while waiting for the active configuration
    dl = rt.start_datalayer(fake=FakeBus)
    rt.at_stop(dl.close)

    import os.path as p
    store = ProjectStore(p.join(data_dir, "projects"), rt.common_dir("projects"))
    motion_factory, viewer_factory = factories(rt, dl)
    core = Core(store, motion_factory, viewer_factory, log=rt.log)
    if dl.provider is not None:
        from app.framework.provider import NodeRegistry
        from app.provider import register
        registry = NodeRegistry(dl.provider, app.NAME, log=rt.log)
        register(registry, core)
        rt.at_stop(registry.clear)
    rt.log(f"Projects: {store.roots['config']} (active configuration), {store.roots['common']} (not in backups)")

    web.core = core
    web.RequestHandler.www_dir = rt.bundled("www")
    rt.serve(web.RequestHandler)
    rt.run()


if __name__ == "__main__":
    main()
