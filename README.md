# 3D Model Builder

Build 3D viewer models from STL files and bind them to ctrlX MOTION axes

A ctrlX CORE app (snap, core24, Python 3.12 in the snap), made from ctrlx-baseline (version in `.baseline`).

- **Web UI / REST:** `https://<ctrlx>/model-builder` (sidebar entry "3D Model Builder"); REST under `/model-builder/api/v1`, protected by the ctrlX proxy (bearer token).
- **Projects:** a folder `<root>/<name>/` with `project.json` and `meshes/*.stl`; root = `model-builder/projects` in the app data of the active configuration (in ctrlX backups) or `$SNAP_COMMON/projects` (not in backups), chosen per project.
- **Data Layer:** `model-builder/state` (JSON string: number of projects).
- **View existing viewer projects (0.2.0, read only):** the left column lists the 3D viewer app's projects; the eye opens one read-only (download of the zip + configuration into `$SNAP_COMMON/viewer-cache/<name>/`, one project at a time). The page shows the model with the XML colours, the structure tree, a details table per node, the bindings (model axis, MOTION axis, formula, status), joints sliders in MOTION units (the preview applies simple linear formulas `a*value+b`; passive `assignKin` joints are disabled), warnings and the Cartesian zone check against a MOTION kinematic. Nothing is written to the viewer or saved; editing an imported project is a later version. REST: `GET /viewer/projects`, `POST /viewer/projects/<name>/open`, `GET /viewer/cache/<file>` (case-insensitive), `POST /viewer/zone`.
- **3D viewer:** uploads go to the 3D viewer app's REST API with the caller's token; its axis bindings are always sent again after an upload.

## Layout

| Path | What |
| --- | --- |
| `app/__init__.py` | the app's identity: name, title, environment prefix, development port |
| `app/main.py` | start-up: app data folder, Data Layer (or the fake), nodes, web server |
| `app/core.py` | generated model, zone check, upload to the 3D viewer |
| `app/storage.py`, `app/project.py` | project folders (two roots, unique names) and the project document (validation) |
| `app/xmlgen.py`, `app/xmleval.py`, `app/zone.py` | machine_definition XML, forward kinematics of it, Cartesian zone check |
| `app/viewcache.py`, `app/viewanalysis.py`, `app/demos.py` | read-only view: safe zip extraction + cache, structure/axes/warnings/formula parser/zone check of a viewer project, demo viewer projects for the fake backend (and the shared-folder examples when readable) |
| `app/motion.py`, `app/viewer.py` | MOTION reads (axes, kinematics), 3D viewer client |
| `app/provider.py` | the app's own Data Layer nodes |
| `app/fake.py` | the simulated ctrlX: MOTION axes, kinematics Gantry and Scara, a demo STL |
| `app/web.py` | REST routes |
| `app/framework/`, `www/framework/`, `tests/framework/` | **ctrlx-baseline framework: don't edit here** (change ctrlx-baseline, then `check.py --sync-framework`) |
| `www/` | the UI (plain HTML/JS/CSS, no build step); `www/vendor/three/` is three.js 0.160.0 (MIT), no CDN at runtime |
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
