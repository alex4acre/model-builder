# 3D Model Builder

Build 3D viewer models from STL files and bind them to ctrlX MOTION axes

A ctrlX CORE app (snap, core24, Python 3.12 in the snap), made from ctrlx-baseline (version in `.baseline`).

- **Web UI / REST:** `https://<ctrlx>/model-builder` (sidebar entry "3D Model Builder"); REST under `/model-builder/api/v1`, protected by the ctrlX proxy (bearer token).
- **Data Layer:** `model-builder/counter` (uint64), `model-builder/setpoint` (float64, writable), `model-builder/state` (JSON string).
- **Configuration:** `model-builder/config.json` in the app data of the active configuration (Settings → Manage app data); saved with ctrlX configurations and backups.

## Layout

| Path | What |
| --- | --- |
| `app/__init__.py` | the app's identity: name, title, environment prefix, development port |
| `app/main.py` | start-up: app data folder, Data Layer (or the fake), nodes, web server |
| `app/core.py` | configuration and the worker: replace the example logic here |
| `app/provider.py` | the app's own Data Layer nodes |
| `app/fake.py` | the simulated ctrlX: the nodes the app uses, as the device gives them |
| `app/web.py` | REST routes |
| `app/framework/`, `www/framework/`, `tests/framework/` | **ctrlx-baseline framework: don't edit here** (change ctrlx-baseline, then `check.py --sync-framework`) |
| `www/` | the UI (plain HTML/JS/CSS, no build step) |
| `configs/package-assets/model-builder.package-manifest.json` | proxy mapping, sidebar menu, app data folder, configuration load/save hooks |
| `snap/snapcraft.yaml` | snap definition; `deps` part = third-party libraries only, so code-only rebuilds are fast |
| `deb/` | the ctrlx-datalayer .deb whose `libcomm_datalayer.so` is bundled |

## Develop

    MODEL_BUILDER_FAKE=1 python3 -m app.main          # http://127.0.0.1:12521/model-builder/?token=dev
    python3 -m unittest -q                       # unit tests against the fake (app + framework)
    python3 tests/ui/ui_check.py <folder>        # headless Firefox check (see the file for set-up)
    ctrlx-baseline/tools/dl_container.sh check . # real Data Layer library (Ubuntu 24.04 container)

## Check, build and install

    ctrlx-baseline/tools/check.py .              # against the baseline (build.sh runs it too)
    ctrlx-baseline/tools/build.sh amd64          # ctrlX COREvirtual; arm64 for ctrlX CORE X3/X5/X7 (foreground)

Bump `version` in `snap/snapcraft.yaml` and `pyproject.toml` for every build you install.
Install: ctrlX web UI → Settings → Apps → enable "Allow installation from unknown source" → Install from file.
Logs: `sudo snap logs -f model-builder` over SSH (app output does not always reach the web Logbook).
