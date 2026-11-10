#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

"""End-to-end UI check in headless Firefox (tests/framework/uidriver.py), against the simulated ctrlX.

    MODEL_BUILDER_FAKE=1 MODEL_BUILDER_DATA=<a folder that doesn't exist yet> MODEL_BUILDER_COMMON=<another new folder> python3 -m app.main
    /snap/bin/firefox.geckodriver --port 4444
    python3 tests/ui/ui_check.py <screenshot folder>    # with the Firefox snap: a folder under ~/snap/firefox/common

Stop the backend and geckodriver by PID afterwards.
"""

import base64
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app  # noqa: E402
from app.fake import demo_stl  # noqa: E402
from tests.framework.uidriver import Browser  # noqa: E402

PORT = int(os.environ.get(app.ENV + "_PORT", app.PORT))
URL = f"http://127.0.0.1:{PORT}/{app.NAME}/"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(path):
    req = urllib.request.Request(URL + "api/v1" + path, headers={"Authorization": "Bearer dev"})
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read())


def hint_check(where):
    missing = b.js("""return [...document.querySelectorAll('button, input, select, textarea, .chip, th, canvas')]
        .filter(e => e.offsetParent !== null && !e.closest('[title]') && e.type !== 'hidden')
        .map(e => e.tagName + '#' + e.id + '.' + e.className + ' ' + (e.textContent || '').slice(0, 20))""")
    b.check(not missing, f"every visible button, field, header and status has a hint ({where}) " + (str(missing) if missing else ""))


b = Browser(screenshots=sys.argv[1] if len(sys.argv) > 1 else None, width=1600, height=950)
try:
    b.open(URL + "?token=dev")
    b.check(b.until("$('new-project') !== null && $('project-chip').textContent === 'No project open'"), "page loads, no project open")
    b.js("window.__confirms = []; window.confirm = (m) => { window.__confirms.push(m); return true; };")

    # create a project in the app-only storage
    b.click("#new-project")
    b.check(b.until("document.querySelector('dialog') !== null"), "new project dialog opens")
    b.set_value("dialog input[type=text]", "UiGantry")
    b.js("document.querySelector('dialog input[value=common]').click()")
    b.check(b.js("return document.querySelectorAll('dialog .storage-table tbody tr').length") == 2, "storage choice table has the two options")
    b.click("dialog button.primary")
    b.check(b.until("$('project-chip').textContent.startsWith('UiGantry') && $('project-chip').textContent.includes('not in backups')"), "project created in 'This app only'")
    b.check(get("/projects")["projects"][0]["location"] == "common", "the backend has it in the common location")

    # upload the demo STL
    data = base64.b64encode(demo_stl()).decode()
    b.js("""const bin = Uint8Array.from(atob(arguments[0]), c => c.charCodeAt(0));
           const dt = new DataTransfer(); dt.items.add(new File([bin], 'cube.stl'));
           const inp = $('file-input'); inp.files = dt.files; inp.dispatchEvent(new Event('change', {bubbles: true}));""", data)
    b.check(b.until("document.querySelectorAll('#meshes-table tbody tr[data-key]').length === 1"), "mesh uploaded and listed")

    # start from the Gantry kinematic
    b.check(b.until("[...$('kin-select').options].some(o => o.value === 'Gantry')"), "kinematics listed from motion/kin")
    b.js("$('kin-select').value = 'Gantry'")
    b.click("#from-kin")
    b.check(b.until("document.querySelectorAll('#tree-box .ui-node').length === 4"), "tree built from the kinematic: 3 axes and a tool marker")
    b.check(b.text("#tree-box .ui-node .ui-label") == "AxisX", "first node is AxisX (kinematic order)")

    # a part under AxisZ
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'AxisZ').click()")
    b.click("#add-part")
    b.check(b.until("document.querySelectorAll('#tree-box .ui-node').length === 5 && $('props-card').textContent.includes('Part cube_1')"), "part added under AxisZ and selected")
    b.js("document.querySelector('#part-colour').value = '#ff8c00'; document.querySelector('#part-colour').dispatchEvent(new Event('change'))")
    b.check(b.until("window.__mb.S.project.tree[0].children[0].children[0].children.find(n => n.kind === 'part').colour[0] === 1"), "part colour saved")

    # preview from the generated XML
    b.check(b.until("window.__mb.preview.info().loaded === 1 && window.__mb.preview.info().tools.length === 1", 12), "preview built from the XML, STL loaded")
    # slider: move AxisX; the tool marker follows along +X
    b.js("const n = document.querySelector('#joints-table input[type=number]'); n.value = '300'; n.dispatchEvent(new Event('input', {bubbles: true}))")
    b.check(b.until("Math.abs(window.__mb.preview.info().tools[0][0] - 300) < 1e-6"), "joint value 300 moves the tool marker by 300 mm in X")
    b.check(b.js("return document.querySelector('#joints-table input[type=range]').value") == "300", "slider follows the number")
    b.js("const r = document.querySelectorAll('#joints-table input[type=range]')[2]; r.value = '120'; r.dispatchEvent(new Event('input', {bubbles: true}))")
    b.check(b.until("Math.abs(window.__mb.preview.info().tools[0][2] - 120) < 1.0"), "slider on AxisZ moves the tool in Z")

    # selecting an axis draws the arrow and highlights the moving parts
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'AxisX').click()")
    b.check(b.until("window.__mb.preview.info().arrow && window.__mb.preview.info().highlighted === 1"), "axis arrow drawn, the part that moves with AxisX is highlighted")

    # zone check
    b.check(b.until("$('zone-chip').textContent === 'Zone: OK'"), "zone check: OK with the tool at the origin")
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'Tool1' || n.querySelector('.ui-label').textContent === 'Tool').click()")
    b.check(b.until("$('props-card').textContent.includes('Tool marker')"), "tool marker selected")
    b.js("""const e = [...document.querySelectorAll('#props-card .ui-edit')][1]; e.focus(); e.value = '0, 0, -100';
           e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))""")
    b.check(b.until("$('zone-chip').textContent === 'Zone: warning' && $('zone-fix') !== null"), "zone check warns when the tool is below the origin; Fix is offered")
    b.click("#zone-fix")
    b.check(b.until("$('zone-chip').textContent === 'Zone: OK' && window.__mb.S.project.tree[0].mcs_origin !== undefined"), "Fix inserts MCS_Origin and the check passes")
    b.check(b.js("return Math.abs(window.__mb.preview.info().tools[0][2] - (-100 + 120)) < 1.0 && Math.abs(window.__mb.preview.info().tools[0][0] - 300) < 1e-6"),
            "the geometry did not move because of the fix (tool still at 300 / 120 - 100)")

    # binding dropdown
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'AxisY').click()")
    b.check(b.until("$('binding-select') !== null && $('binding-select').value === 'AxisY'"), "binding dropdown shows the MOTION axis")
    b.check(b.js("return [...$('binding-select').options].map(o => o.value).includes('ScaraRot1')"), "binding dropdown lists the MOTION axes")

    # upload to the (fake) viewer, then again with the replace question
    b.click("#upload-viewer")
    b.check(b.until("$('banner').textContent.includes('Uploaded to the 3D viewer') && $('banner').textContent.includes('3 axes bound')"), "upload to the viewer: 3 axes bound")
    b.js("window.__confirms.length = 0")
    b.click("#upload-viewer")
    b.check(b.until("window.__confirms.length === 1 && window.__confirms[0].includes('replaces its files, its axis bindings and its library picture')"), "re-upload asks before replacing")
    b.check(b.until("$('banner').textContent.includes('(replaced)')"), "re-upload done after the confirmation")

    # move to the other location and rename
    b.js("document.querySelector('#project-tools button[title^=\"Move\"]').click()")
    b.check(b.until("document.querySelector('dialog') !== null"), "move dialog opens")
    b.click("dialog button.primary")
    b.check(b.until("$('project-chip').textContent.includes('in backups') && !$('project-chip').textContent.includes('not in')"), "project moved to the active configuration")
    b.check(b.until("window.__mb.preview.info().loaded === 1"), "preview reloaded after the move")

    b.js("window.__mb.preview.fit()")
    b.shot("main")
    hint_check("editor")

    # ---- read-only view of 3D viewer projects ----
    b.check(b.until("document.querySelectorAll('#viewer-table tbody tr[data-key]').length >= 2"), "the 3D viewer projects are listed")
    names = b.js("return [...document.querySelectorAll('#viewer-table tbody tr[data-key]')].map(r => r.dataset.key)")
    b.check("Demo Gantry" in names and "Demo Delta" in names, "the list has the demo gantry and the demo delta " + str(names))
    b.check(b.js("return document.querySelector('#viewer-refresh').title.length > 0"), "the refresh button has a hint")
    b.js("document.querySelector('.view-open[data-name=\"Demo Gantry\"]').click()")
    b.check(b.until("$('readonly-bar') && !$('readonly-bar').hidden && $('readonly-text').textContent === 'Read only: Demo Gantry from the 3D viewer. Nothing is changed.'", 15),
            "the read-only banner is shown")
    b.check(b.js("return $('close-view') !== null"), "the banner has a close button")
    b.check(b.js("return ['save', 'download-zip', 'upload-viewer', 'new-project'].every(id => $(id).disabled)"), "save, download, upload and new project are disabled")
    b.check(b.js("return !$('tree-tools') && !$('upload-mesh') && !$('add-part') && !$('meshes-card') && !$('zone-fix')"), "no editing controls in the read-only view")
    b.check(b.until("window.__mb.preview.info().parts === 6 && window.__mb.preview.info().loaded === 6", 20), "the preview loaded all 6 meshes (Beam.STL found as beam.stl)")
    b.check(b.js("return window.__mb.preview.info().tools.length === 1 && Math.abs(window.__mb.preview.info().tools[0][0] - 2490) < 1"), "the model starts at its initial values (tool at x 2490)")
    # structure tree
    b.check(b.js("return document.querySelectorAll('#view-tree .ui-node').length") >= 14, "the structure tree lists transforms, axes, parts and the tool")
    b.check(b.js("return [...document.querySelectorAll('#view-tree .ui-label')].map(e => e.textContent).includes('ToolTransform')"), "nested named transforms are in the tree")
    def pick(label):
        b.js("[...document.querySelectorAll('#view-tree .ui-node')].find(n => n.querySelector('.ui-label').textContent === arguments[0]).click()", label)
    pick("X")
    b.check(b.until("$('props-card').textContent.includes('Translation axis X') && $('props-card').textContent.includes('2250 - value') && $('props-card').textContent.includes('model = -1 × value + 2250')"), "axis details show type, binding, formula")
    pick("ToolTransform")
    b.check(b.until("$('props-card').textContent.includes('Position (x, y, z) mm') && $('props-card').textContent.includes('240, 0, 150') && $('props-card').textContent.includes('Raw initialvalue')"), "transform details: position, rotation, raw matrix")
    pick("XBeam")
    b.check(b.until("$('props-card').textContent.includes('Beam.STL') && $('props-card').textContent.includes('Found as beam.stl') && $('props-card').textContent.includes('Colour')"), "part details: file (case differs), colour")
    pick("Tool")
    b.check(b.until("$('props-card').textContent.includes('Tool Tool')"), "tool details")
    # bindings
    b.check(b.js("return document.querySelectorAll('#bindings-table tbody tr[data-key]').length") == 5, "bindings table: one row per model axis")
    b.check(b.js("return $('bindings-table').textContent.includes('2250 - value') && $('bindings-table').textContent.includes('AxisX') && $('bindings-table').textContent.includes('Not bound')"), "bindings show MOTION axis, formula and the unbound axis")
    # joints: slider in MOTION units, the formula is applied
    b.check(b.js("return $('joints-table').textContent.includes('model = 2250 - value')"), "the formula is shown next to the joint")
    b.js("const n = document.querySelector('#joints-table input[type=number]'); n.value = '250'; n.dispatchEvent(new Event('input', {bubbles: true}))")
    b.check(b.until("Math.abs(window.__mb.preview.info().tools[0][0] - 2240) < 1"), "MOTION value 250 with 2250 - value moves the tool from x 2490 to 2240")
    b.check(b.js("return document.querySelector('#joints-table .joint-model').textContent") == "2000", "the model value shown is 2000")
    b.js("const r = document.querySelectorAll('#joints-table input[type=range]')[1]; r.value = '300'; r.dispatchEvent(new Event('input', {bubbles: true}))")
    b.check(b.until("Math.abs(window.__mb.preview.info().tools[0][1] - 300) < 1"), "the Y slider moves the tool in Y")
    # warnings
    codes = b.js("return [...document.querySelectorAll('#warn-list li')].map(l => l.dataset.code)")
    b.check("expression" in codes and "unbound" in codes, "warnings list the formula and the unbound axis " + str(codes))
    b.check(b.js("return $('warnings-card').textContent.includes('Camera_Z') && $('warnings-card').textContent.includes('ExpressionScript')"), "the warnings name the axis and the script")
    # zone check: result only
    b.check(b.until("[...$('view-kin').options].some(o => o.value === 'Gantry')"), "kinematics offered for the zone check")
    b.js("$('view-kin').value = 'Gantry'; $('view-kin').dispatchEvent(new Event('change'))")
    b.click("#view-zone-check")
    b.check(b.until("$('zone-table') !== null && $('zone-chip').textContent === 'Zone: warning'"), "zone check result: warning (the tool is not at the parent of X with the formulas applied)")
    b.check(b.js("return $('zone-fix') === null"), "no Fix in the read-only view")
    b.js("window.__mb.preview.fit()")
    b.shot("readonly")
    hint_check("read-only view")
    # a delta: passive joint
    b.js("document.querySelector('.view-open[data-name=\"Demo Delta\"]').click()")
    b.check(b.until("$('readonly-text') && $('readonly-text').textContent.includes('Demo Delta') && $('warn-list') !== null", 15), "opened the demo delta")
    b.check(b.js("return [...document.querySelectorAll('#warn-list li')].some(l => l.dataset.code === 'assignkin')"), "assignKin warning for the passive joint")
    b.check(b.js("return document.querySelectorAll('#joints-table input[type=range]:disabled').length") == 1, "the passive joint's slider is disabled")
    b.check(b.js("return $('joints-table').textContent.includes('passive')"), "the passive joint carries a note")
    b.check(b.until("window.__mb.preview.info().loaded === window.__mb.preview.info().parts && window.__mb.preview.info().parts === 4", 15), "delta meshes loaded")
    # close: back to the editor with the project that was open
    b.click("#close-view")
    b.check(b.until("$('readonly-bar').hidden && $('project-chip').textContent.startsWith('UiGantry') && $('tree-box') !== null"), "closing the view returns to the editor (UiGantry)")
    b.check(b.until("window.__mb.preview.info().loaded === 1 && !$('save').disabled"), "the editor's preview and buttons are back")
    errors = b.js("return window.__errors")
    b.check(not errors, "no console errors " + (str(errors) if errors else ""))
finally:
    b.close()
sys.exit(b.finish())
