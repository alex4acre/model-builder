# 3D Model Builder: plan (2026-11-06, decisions completed 2026-11-10)

A ctrlX app for building 3D viewer models from your own CAD files: upload the meshes, arrange
them into moving links, define the joints, bind them to MOTION axes and upload the result to the
ctrlX 3D viewer. Today that means writing `machine_definition` XML by hand.

Name `model-builder`, title "3D Model Builder". It is a new app made with `new_app.py` on
baseline 1.1.0 (shared UI components `ui.js`/`ui.css`, STANDARD.md §6 UI1-UI3). This file moves to `model-builder/docs/plan.md` when
the app is created.

## What the app does

1. Create a project and upload the files. Phase 1 takes STL (binary or ASCII). Phase 3 adds
   STEP.
2. Arrange the parts in a tree. A joint (rotation or translation axis) carries everything under
   it, so the tree is the kinematic chain: base → A1 → link 1 → A2 → link 2 …
3. Set each joint's direction, pivot point and limits, and check it in a live 3D preview with
   one slider per joint.
4. Bind each joint to a ctrlX MOTION axis, picked from a list of `motion/axs`.
5. Upload to the 3D viewer: the model plus its axis bindings, so it moves at once without setup
   in the viewer. You can also download it as a package zip.

All 3D work runs in the browser on your PC. The core only stores files and forwards them to the
viewer, so an X3 handles it as well as an X7.

## Reused, already verified

| What | Where | Status |
| --- | --- | --- |
| XML generator (nested transforms, axes, pivots, limits, TCP marker, colours) | `robot-configurator/app/viewer3d.py` `build_xml` | device-tested |
| Viewer REST: list / POST multipart / PUT configuration / DELETE / GET zip | `robot-configurator/app/viewer_upload.py` (`RestViewer`, `FakeViewer`) | device-tested |
| `ConfiguredAxis` binding JSON | `viewer3d.configuration` | device-tested |
| Format reference + examples | skill `ctrlx-3d-viewer-models`; Scara Sort, Delta_Ori_Sort, `Model/Delta Sort.xml` | |
| STEP coaxial-cylinder finder (stdlib) | `robot-configurator/tools/step-measure/shared_axes.py` | worked on Autonox files |
| Vendored JS library in `www/vendor/` | `flow-editor` (Blockly) | precedent |

These are copied into the new app, not imported across apps, so the apps stay independent.

## Project data

One JSON per project. Coordinates are in the common assembly frame at the zero pose (the
viewer's own convention), so pivots are plain world points:

```json
{
  "name": "MyGantry", "units": "mm",
  "mounting": [16 numbers],
  "meshes": {"base": {"file": "base.stl", "scale": 1, "placement": [16 numbers]}},
  "tree": [
    {"kind": "part", "mesh": "base", "colour": [0.6,0.6,0.6], "alpha": 0},
    {"kind": "axis", "name": "X", "type": "translation", "direction": [1,0,0],
     "pivot": [0,0,0], "range": [0, 1200], "initial": 0,
     "binding": {"node": "AxisX", "expression": "value"},
     "children": [ {"kind": "part", "mesh": "carriage"} ]},
    {"kind": "tool", "at": [0,0,-150]}
  ],
  "extra": {}
}
```

`extra` keeps attributes the editor doesn't understand yet (for example `customdata="assignKin(...)"`)
so they survive a round trip unchanged.

## Phases

### Spikes first (scripts on the X3 at .22, viewer only, no axes moved, test projects deleted afterwards)
- **S1 Upload size:** POST 2 / 10 / 30 / 60 MB STLs to the viewer and time how long they take
  to open. The result sets the app's size warning and shows whether Phase 4 decimation is
  needed.
- **S2 Re-upload:** what happens on POST to an existing name (replace, or error so we must
  DELETE first), and whether the library picture is kept.
- **S3 Proxy body limit:** the largest upload the ctrlX reverse proxy passes to an app. This
  sets `MAX_BODY`.
- **S4 (before Phase 3):** load one Autonox STEP with `occt-import-js` in the VM's Firefox and
  record load time, body count, names and memory use.

### Phase 1 (0.1.x): STL editor, the usable minimum
- Project list: new, rename, duplicate, delete.
- STL upload with a unit choice (mm / m / inch). Optional per-mesh placement (move/rotate) for
  files not exported in the assembly frame.
- Tree editor: add a rotation or translation axis, drag parts under axes, add a TCP marker.
- Joint fields: direction (±X/±Y/±Z presets or custom), pivot (typed in), min/max, initial
  value.
- Preview (three.js, vendored): orbit/pan/zoom, grid, world axes, the selected joint's axis
  drawn as an arrow, one slider per joint, moving parts highlighted.
- Binding: dropdown of MOTION axes (read with your token). The expression is always `value`.
  Offsets and inversions are built into the XML (an `<name>_Offset` transform, negated
  direction, limits in raw units), never into the ExpressionScript (Gantry lesson, 2026-11-09).
- **Start from kinematic (optional, D7):** pick a kinematic from `motion/kin` (read only). The
  app creates the joint chain in axis order, with each joint's type (rotation/translation) and
  its MOTION axis binding. You still place the STLs and set the pivots/directions.
  - **Cartesian zone check:** the viewer draws MCS zones at the world origin of the parent of
    the first kinematic axis's model axis, with directions = the model axes' x/y/z vectors,
    and ignores ExpressionScripts. The app checks that this parent sits at the tool point for
    all axes at 0 and that the frame is right-handed. It warns if not, and offers to insert an
    `MCS_Origin` transform with compensated child geometry (the Gantry v3 method).
  - Scara, delta and six-axis kinematics: joints only, no zone check (their rules are not
    read yet).
- Upload to the viewer (asks before replacing an existing project) and download as a zip.
- Storage choice per project: active configuration (in backups) or `$SNAP_COMMON` (not in
  backups). The project list shows where each one is and can move it.
- Tests: unit tests (the XML matches robot-configurator's output for the same spec; the
  zone-frame rule checked against the Gantry v3 model), UI check with screenshot, then a device test: build a small 2-axis model and watch it follow jogged
  axes.

### Phase 2 (0.2.x): view, then picking and import
- **0.2.0 (done 2026-11-10): view existing viewer projects, read only.** List of the viewer's projects, eye = open into a
  cache (`$SNAP_COMMON/viewer-cache`, one project at a time, safe extraction: no absolute paths or `..`, only
  xml/stl/json/png/jpg, 500 MB total); structure tree, details per node, bindings, joints sliders in MOTION units with the
  linear formula applied (`a*value+b`, never evaluated), warnings (formula not `value`, unbound axis, binding without axis,
  assignKin passive joint, missing STL, no tool, duplicate axis name), Cartesian zone check against a MOTION kinematic (result
  only, no Fix). Nothing is written or saved. Tested on Scara Sort, Delta_Ori_Sort and the L10409A_Gantry (original and baked).
- **Later (0.3.x): editable import.** Importing a viewer project into a project of this app (XML to tree, including nested
  named transforms, scripts to offset/invert, assignKin joints) with a round-trip test.
- Pick pivots by clicking the mesh. Snap to vertex, edge midpoint or **circle centre** (a
  circle fitted to a hole or shaft edge loop). Take the direction from a face normal or the
  circle's axis.
- Import an existing viewer project as an editable project (the read-only view is 0.2.0). Round-trip test: Scara Sort
  and Delta_Ori_Sort come back out with the same structure.
- Colours and transparency per part.

### Phase 3 (0.3.x): STEP import
- Vendored `occt-import-js` (OpenCascade compiled to WebAssembly, about 10 MB) turns STEP into
  meshes in the browser. A quality slider sets the tessellation.
- Body list with assembly names and a **grouping tool**: box select, select by colour,
  hide/isolate, "assign to link". This is most of the phase's work.
- Each link's bodies are merged into one binary STL in the browser before saving.
- **Pivot suggestions:** the server runs the stdlib cylinder finder on the STEP and lists
  shared axes between bodies in different links ("A2? shaft at x 250, direction y").
- Fallback message for files that fail to load: export STL from your CAD instead.

### Phase 4 (later, on request)
Closed loops (`assignKin` passive joints for deltas), mesh decimation for large files, the
viewer's stock definitions and background images.

## Effort (rough)
| Phase | Size |
| --- | --- |
| Spikes | one test script, one run |
| 1 | about palletizer 0.3: 3–4 build/test rounds |
| 2 | 2 rounds |
| 3 | 2–3 rounds, plus S4 |

## Risks and unknowns
- The viewer's size limit (S1) and the proxy's size limit (S3) are not measured.
- If your CAD exports each part in its own local frame, the placement step is needed for every
  part. That is tedious, and a reason to prefer STEP later.
- `occt-import-js`: not tried here yet, and its licence must be checked before vendoring
  (OpenCascade is LGPL).
- Robot-configurator also uploads viewer projects. Name clashes get a warning, and this app
  never touches a project it didn't create or import.
- Stacked tools showed wrong in the viewer (open issue in robot-configurator). Phase 1 has
  only a single TCP marker.

## Decisions
- **D1** (2026-11-06) Name `model-builder`, title "3D Model Builder".
- **D2** (2026-11-06, confirmed 2026-11-10) Storage is chosen per project: active configuration
  (included in backups) or `$SNAP_COMMON` (not in backups); projects can be moved.
- **D3** (2026-11-06) First build arm64 for the X3 at .22. Read `system/typeplate` first.
  Its palletizer and PLC stay as they are.
- **D4** (2026-11-06) Phase 3 keeps only the merged link STLs, not the original STEP.
- **D5** (2026-11-06) Spikes S1-S3 run on .22 (viewer only).
- **D6** (2026-11-10) Input order stays: STL first (Phase 1), STEP in Phase 3.
- **D7** (2026-11-10) "Start from kinematic" is in Phase 1, optional next to building by hand,
  with the Cartesian zone check. Offsets/inversions always built into the XML.
- **D8** (2026-11-10) Importing/editing existing viewer projects stays in Phase 2.

## Spike results (2026-11-10, X3 .22, COREX-C-X3-11, script in that session's scratchpad)
- **S1 upload size:** binary STL uploads of 2 / 10 / 30 / 60 MB all gave HTTP 201, in
  0.5 / 1.9 / 5.2 / 10.5 s. No size limit on the viewer up to 60 MB. The time a model takes
  to open in the viewer was NOT measured (needs a browser): check it in the Phase 1 device test.
- **S2 re-upload:** POST to an existing name gives 201 and REPLACES the files (the old STL is
  gone). It also CLEARS the axis bindings (ConfiguredAxis dropped, new TrackId) and the
  library picture (thumbnail 404 again). DELETE first is not needed. So the app must PUT the
  configuration after every upload. Bindings never survive a re-upload.
- **S3 proxy limit for app routes:** not settled. The proxy passes the request to the app
  before the body has arrived, so an app that answers early (404) makes the client stop
  sending; no 413 from the proxy was seen up to 20 MB, and the same proxy carried 60 MB to
  /3dviewer. Measure for real in Phase 1 with the app's own upload route, which reads the
  whole body before it answers (and must: urllib got an SSL EOF at 10 MB against a route that
  answered early).
- The user's L10409A_Gantry project was left untouched; all mb_spike_* projects were deleted.

## Findings (2026-11-10, Phase 1)

**R1: `rzx/rzy/rzz` (and the axis direction x/y/z) are in the LOCAL frame of the enclosing node, not in the world frame.**
Evidence: the viewer's web client, read from the 3D Viewer 4.6.2 app in the shared folder (`main-N4QXBF5R.js`, no device
access needed):
- `createObjects()` builds every rotation axis as two nested objects: a pivot node `rzv_<name>` that is a CHILD of the
  enclosing node, with `position = (rzx, rzy, rzz)`, and the axis object inside it with `position = -(rzx, rzy, rzz)`.
  Positions in three.js are relative to the parent, so the pivot is a point in the enclosing node's local frame.
- `moveAxis()` rotates the pivot node with `quaternion.setFromAxisAngle(axis, angle)` and the axis vector is the XML's
  x/y/z, so the direction is in the same local frame. A translation sets `object.position = direction * value`, also local.
- The examples (Scara Sort, the Gantry files) cannot tell the two readings apart: their axes sit directly inside each other
  or inside rotation-only transforms with `rzx rzy rzz = 0`, so local and world coordinates agree.
Consequences: the app stores pivots in the assembly frame at the zero pose. Every node the generator wraps around an axis
(`<axis>_Offset`, `MCS_Origin_Inverse`) is an identity at that pose, so the stored pivots are written as they are. Only an
axis that sits inside an `MCS_Origin` gets its pivot converted (`pivot - mcs_origin`). `app/xmleval.py` (forward
kinematics used by the zone check and the tests) and `www/preview.js` follow the viewer's way; the tests check a rotation
axis behind an `MCS_Origin` against the same model without it (identical geometry for random poses).

**Zone frame (decision D7), read from the same client** (`calculateMcs4SixAxis` and the Cartesian variant): the origin is
`localToWorld` of the pivot / object of the first kinematic axis's model axis (the world origin of the parent node at the
zero pose), the directions are `axis * kinematic axis direction`, transformed to world with the parent's `matrixWorld`;
ExpressionScripts are not used. `app/zone.py` checks exactly that. Test on the user's files: Gantry v3 (`Model_baked`) passes
(parent of X at world (2250, 1500, 35), tool at the same point, directions -X, -Y, +Z right-handed); the original
(`Model`, scripts `2250 - value` ...) warns (parent at (0, 0, 2035), tool at (2250, 1500, 35); the suggested origin shift is
(2250, 1500, -2000), the MCS_Origin of Gantry v3).

**Offsets and inversions** are baked into the XML (`<axis>_Offset` transform, negated direction); the ExpressionScript is
always `value`. Checked numerically against `offset + s * value` for random poses (the XML keeps 7 digits, so the tests
accept 0.01 mm).

**Decisions made in Phase 1:** `mcs_origin` is a key on the axis node of the project JSON (kept through load/save). The
kinematic in the project carries its axes (`{"name", "type", "axes": [{"name", "dir"}]}`) so the zone check needs no MOTION
read. A project is saved at once after every edit; the Save button saves again. A mesh used by a part cannot be deleted.
The package zip holds `Model.zip` and `<name>.json` (no thumbnail: the viewer's `thumbnail.png` is a data URL text it
renders itself on first open).

## Decisions made in 0.2.0
- `alpha` in the viewer XML is read as a transparency (0 = opaque; every example has alpha="0" and is opaque): opacity = 1 - alpha.
- Slider values are MOTION values; the preview shows each axis at its XML `initial_value` at first (as the viewer starts) and
  maps back through the formula. Zone check on a viewed model evaluates the XML with every MOTION axis at 0 and the formulas
  applied (the original Gantry then warns with the shift (2250, 1500, -2000), the baked v3 passes), as in the 0.1.0 test.
- Bindings: the viewer's own configuration; if it has none, the JSON in the package.

## Next step
Device test on the X3 at .22 by the user (build 2 axes, upload, jog); 0.2.0 view-only to be tried against real viewer projects
(amd64 build for the X7), then the editable import.
