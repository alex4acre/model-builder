# SPDX-License-Identifier: MIT

"""3D Model Builder: Build 3D viewer models from STL files and bind them to ctrlX MOTION axes

In the snap: UI at https://<ctrlx>/model-builder, configuration in the app data of the active
configuration (model-builder/config.json), Data Layer nodes under model-builder/...

Development with a simulated ctrlX:  MODEL_BUILDER_FAKE=1 python3 -m app.main
                                     -> http://127.0.0.1:12521/model-builder/?token=dev
(more settings in app/framework/runtime.py)
"""

import os

import app
from app import web
from app.core import Core
from app.fake import FakeBus
from app.framework.runtime import Runtime

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    rt = Runtime(app.NAME, env=app.ENV, port=app.PORT, src=SRC)
    data_dir = rt.data_dir()
    if not data_dir:
        return                                   # stopped while waiting for the active configuration
    dl = rt.start_datalayer(fake=FakeBus)
    rt.at_stop(dl.close)

    core = Core(data_dir, dl.bus, log=rt.log)
    rt.at_stop(core.stop)
    if dl.provider is not None:
        from app.framework.provider import NodeRegistry
        from app.provider import register
        registry = NodeRegistry(dl.provider, app.NAME, log=rt.log)
        register(registry, core)
        rt.at_stop(registry.clear)
    core.start()
    rt.log(f"Configuration: {core.settings.path}")

    web.core = core
    web.RequestHandler.www_dir = rt.bundled("www")
    rt.serve(web.RequestHandler)
    rt.every(5, core.settings.reload_if_changed)
    rt.run()


if __name__ == "__main__":
    main()
