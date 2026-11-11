# 3D Model Builder

Build 3D viewer models from STL files and bind them to ctrlX MOTION axes

A ctrlX CORE app (snap, core24, Python 3.12 in the snap), made from ctrlx-baseline (version in `.baseline`).

- **Web UI / REST:** `https://<ctrlx>/model-builder` (sidebar entry "3D Model Builder"); REST under `/model-builder/api/v1`, protected by the ctrlX proxy (bearer token).
- **Projects:** a folder `<root>/<name>/` with `project.json` and `meshes/*.stl`; root = `model-builder/projects` in the app data of the active configuration (in ctrlX backups) or `$SNAP_COMMON/projects` (not in backups), chosen per project.
- **Data Layer:** `model-builder/state` (JSON string: number of projects).
- **View existing viewer projects (0.2.0, read only):** the left column lists the 3D viewer app's projects; the eye opens one read-only (download of the zip + configuration into `$SNAP_COMMON/viewer-cache/<name>/`, one project at a time). The page shows the model with the XML colours, the structure tree, a details table per node, the bindings (model axis, MOTION axis, formula, status), joints sliders in MOTION units (the preview applies simple linear formulas `a*value+b`; passive `assignKin` joints are disabled), warnings and the Cartesian zone check against a MOTION kinematic. Nothing is written to the viewer or saved. REST: `GET /viewer/projects`, `POST /viewer/projects/<name>/open`, `GET /viewer/cache/<file>` (case-insensitive), `POST /viewer/zone`.
- **Editable import (0.3.0):** "Import for editing" (read-only bar and the viewer list) asks for a project name (unique) and the storage location and makes a normal project from the viewer project: transforms with one geometry become parts (with their matrix), other transforms become `frame` nodes, axes keep pivot/direction in the local frame, every attribute and unknown XML element the editor does not model is kept and written back unchanged (shown read-only in the properties), the ExpressionScripts become each axis' editable **Formula** (default `value`, written unchanged; the preview applies simple linear ones). No wrapper transform is added to an imported model. REST: `POST /viewer/projects/<name>/import {name, location, confirm}` (409 `DROPS` lists what cannot be kept).
- **Upload back (0.3.0):** goes to the project's viewer name (default the project name), after a confirmation when it exists ("Replaces <name> in the 3D viewer: ..."); "Upload as new name..." (`?as=<name>`) needs a free name and remembers it. The configuration is always sent again after the files.
- **Viewer settings kept on re-upload (0.5.0):** when the target viewer project exists, its current configuration is read BEFORE the upload (if that fails nothing is uploaded) and merged: axes bound here get the app's entry; any other axis of the model keeps the viewer's entry (e.g. a Data Layer variable binding made in the viewer), unless it is exactly what this app sent last time (you cleared the binding here: `extra.sent_bindings`); entries for axes that no longer exist are dropped and reported; all other keys (Visual Effects, safe zones, tool nodes ...) are kept; the TrackId is never sent. `GET /projects/<name>/viewer-state` shows what the viewer has for unbound axes (shown read-only in the axis properties).
- **Display ID and always visible (0.5.0):** parts and frames have a Display ID (written as `customdata="displayid(<ID>)"`, other customdata entries are kept, joined with `,;`); parts have Always visible (by name: contains `alwaysvisible` or `active`, as the viewer's Hide housing decides). The preview has a Hide housing toggle and lightly highlights parts sharing the selected part's Display ID.
- **Panels (0.3.0):** the left and the right column have drag handles (arrow keys, double-click = standard width); the widths are remembered in the browser.
- **Drag in the preview (0.4.0):** click a part or tool marker in the preview to select its tree node (a press that moves 4 px or more is an orbit; a click on empty space clears the selection); a gizmo (three.js TransformControls) moves (W) or rotates (E) the selected frame, part, tool marker or rotation axis (pivot only). One drag = one save, made at the zero pose (the joints are set to 0 first), in the frame of the node it sits in (the world result is converted with the inverse of the parent's world matrix): frame -> `matrix`; part -> its `matrix`, or the mesh placement (position + rotation) when it has none and is the mesh's only part; tool -> `position` (or `matrix`); rotation axis -> `pivot` (minus an MCS_Origin shift). Translation axes, bare parts/tools and directions/ranges are not dragged. Snapping defaults to ON, 10 mm and 15 degrees (steps 1/5/10/50/100 mm, 1/5/15/45/90 degrees), Shift while dragging snaps off for that drag, Local/World chooses the gizmo's and the snap's axes; all remembered in the browser.
- **Undo / redo (0.4.0):** the last 50 changes made through the editor (drags and typed edits) can be undone (Ctrl+Z) and redone (Ctrl+Y, Ctrl+Shift+Z; not while typing in a field) with the two buttons in the header. The history is in the browser only and is cleared when a project is opened, closed, renamed, moved or deleted. Mesh uploads and deletes are not undoable; a snapshot that needs a mesh that was deleted since is refused with a message and nothing changes.
- **3D viewer:** uploads go to the 3D viewer app's REST API with the caller's token; its axis bindings are always sent again after an upload.

## Layout

| Path | What |
| --- | --- |
| `app/__init__.py` | the app's identity: name, title, environment prefix, development port |
| `app/main.py` | start-up: app data folder, Data Layer (or the fake), nodes, web server |
| `app/core.py` | generated model, zone check, upload to the 3D viewer |
| `app/storage.py`, `app/project.py` | project folders (two roots, unique names) and the project document (validation) |
| `app/xmlgen.py`, `app/xmleval.py`, `app/zone.py` | machine_definition XML, forward kinematics of it, Cartesian zone check |
| `app/xmlimport.py`, `app/formula.py` | viewer project -> editable project (mapping, kept attributes, report), formula parser and validation |
| `app/viewcache.py`, `app/viewanalysis.py`, `app/demos.py` | read-only view: safe zip extraction + cache, structure/axes/warnings/formula parser/zone check of a viewer project, demo viewer projects for the fake backend (and the shared-folder examples when readable) |
| `app/motion.py`, `app/viewer.py` | MOTION reads (axes, kinematics), 3D viewer client |
| `app/provider.py` | the app's own Data Layer nodes |
| `app/fake.py` | the simulated ctrlX: MOTION axes, kinematics Gantry and Scara, a demo STL |
| `app/web.py` | REST routes |
| `app/framework/`, `www/framework/`, `tests/framework/` | **ctrlx-baseline framework: don't edit here** (change ctrlx-baseline, then `check.py --sync-framework`). `www/framework/ui.js` and `ui.css` are the versions of baseline `proposal/ui-splitter` (1.1.1, awaiting the reviewer): `check.py` reports them as "local change" until it is released |
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
