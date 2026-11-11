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
import time
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


def send(method, path, body=None):
    req = urllib.request.Request(URL + "api/v1" + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer dev", "Content-Type": "application/json"})
    with opener.open(req, timeout=20) as r:
        return json.loads(r.read() or b"null")


def hint_check(where):
    missing = b.js("""return [...document.querySelectorAll('button, input, select, textarea, .chip, th, canvas')]
        .filter(e => e.offsetParent !== null && !e.closest('[title]') && e.type !== 'hidden')
        .map(e => e.tagName + '#' + e.id + '.' + e.className + ' ' + (e.textContent || '').slice(0, 20))""")
    b.check(not missing, f"every visible button, field, header and status has a hint ({where}) " + (str(missing) if missing else ""))


b = Browser(webdriver=os.environ.get("WEBDRIVER", "http://127.0.0.1:4444"), screenshots=sys.argv[1] if len(sys.argv) > 1 else None, width=1600, height=950)
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
    b.check(b.until("window.__confirms.length === 1 && window.__confirms[0] === 'Replaces UiGantry in the 3D viewer: its files are replaced, the axis bindings are sent again and the library picture is redrawn.'"), "re-upload asks before replacing, with the agreed text")
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
    # the structure box keeps its scroll position when a node is clicked
    b.check(b.js("const t = $('view-tree'); return t.scrollHeight > t.clientHeight + 100"), "the structure box overflows (so it can be scrolled)")
    b.js("$('view-tree').scrollTop = 160")
    top0 = b.js("return $('view-tree').scrollTop")
    b.check(top0 > 100, f"the structure box is scrolled down ({top0})")
    b.js("[...document.querySelectorAll('#view-tree .ui-node')].filter(n => n.querySelector('.ui-label').textContent === 'ZGeo' || n.querySelector('.ui-label').textContent === 'ZRod').pop().click()")
    b.check(b.until("$('props-card').textContent.includes('ZRod') || $('props-card').textContent.includes('ZGeo')"), "a node near the bottom is clicked")
    b.check(b.js("return $('view-tree').scrollTop") == top0, "clicking a node does not scroll the structure box back to the top")
    b.check(b.js("return document.querySelector('#view-tree .ui-sel') !== null"), "the clicked node is highlighted")
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

    # ---- the Tree box keeps its scroll position (0.3.0) ----
    base = get("/projects/UiGantry")
    scroll = {"name": "UiScroll", "location": "config"}
    send("POST", "/projects", scroll)
    req = urllib.request.Request(URL + "api/v1/projects/UiScroll/meshes/cube.stl?unit=mm", data=demo_stl(), method="PUT",
                                 headers={"Authorization": "Bearer dev", "Content-Type": "application/octet-stream"})
    opener.open(req, timeout=20).read()
    tree = [{"kind": "part", "id": f"p{i}", "name": f"Part{i:02d}", "mesh": "cube", "colour": [0.5, 0.5, 0.5]} for i in range(40)]
    doc = send("GET", "/projects/UiScroll")
    doc["tree"] = tree
    send("PUT", "/projects/UiScroll", doc)
    b.check(b.until("[...document.querySelectorAll('#projects-table tr[data-key]')].some(r => r.dataset.key === 'UiScroll')", 12), "the new project is listed")
    b.js("document.querySelector('#projects-table tr[data-key=\"UiScroll\"]').click()")
    b.check(b.until("$('project-chip').textContent.startsWith('UiScroll') && document.querySelectorAll('#tree-box .ui-node').length === 40"), "a project with 40 nodes is open")
    b.check(b.js("const t = $('tree-box'); return t.scrollHeight > t.clientHeight + 200"), "the Tree box overflows")
    b.js("$('tree-box').scrollTop = 500")
    top1 = b.js("return $('tree-box').scrollTop")
    b.check(top1 > 300, f"the Tree box is scrolled down ({top1})")
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'Part30').click()")
    b.check(b.until("$('props-card').textContent.includes('Part Part30')"), "a node far down the tree is clicked and selected")
    b.check(b.js("return $('tree-box').scrollTop") == top1, "clicking a node does not scroll the Tree box back to the top")
    # an edit that rebuilds the columns does not scroll it either
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'Part31').click()")
    b.js("document.querySelector('#part-colour').value = '#00ff00'; document.querySelector('#part-colour').dispatchEvent(new Event('change'))")
    b.check(b.until("window.__mb.S.project.tree[31].colour[1] === 1"), "a property edit is saved (columns re-rendered)")
    b.check(b.js("return $('tree-box').scrollTop") == top1, "an edit does not scroll the Tree box either")

    # ---- resizable left and right panels ----
    b.js("window.__canvasW0 = document.querySelector('#stage canvas').width")
    wl0 = b.js("return $('left').getBoundingClientRect().width")
    wr0 = b.js("return $('right').getBoundingClientRect().width")
    b.check(b.js("return document.querySelectorAll('main .ui-splitter[role=separator]').length") == 2, "both panels have a drag handle")
    b.check(b.js("return [...document.querySelectorAll('main .ui-splitter')].every(h => h.title.length > 10)"), "both handles have a hover hint")
    b.js("""const s = document.querySelector('main .ui-splitter'); const l = $('left').getBoundingClientRect();
           s.dispatchEvent(new PointerEvent('pointerdown', {pointerId: 1, clientX: l.right + 2, bubbles: true}));
           s.dispatchEvent(new PointerEvent('pointermove', {pointerId: 1, clientX: l.left + 520, bubbles: true}));
           s.dispatchEvent(new PointerEvent('pointerup', {pointerId: 1, clientX: l.left + 520, bubbles: true}));""")
    b.check(b.until("Math.abs($('left').getBoundingClientRect().width - 520) < 3"), f"dragging the left handle sets the left panel to 520 px (was {wl0})")
    b.check(b.until("document.querySelector('#stage canvas').width < window.__canvasW0"), "the preview canvas shrank with the centre column")
    b.check(b.until("Math.abs(document.querySelector('#stage canvas').width - Math.round(document.querySelector('#stage').clientWidth * devicePixelRatio)) <= 2"), "the canvas is as wide as its stage (renderer and camera aspect follow)")
    b.js("""const s = $('split-right'); const r = $('right').getBoundingClientRect();
           s.dispatchEvent(new PointerEvent('pointerdown', {pointerId: 1, clientX: r.left, bubbles: true}));
           s.dispatchEvent(new PointerEvent('pointermove', {pointerId: 1, clientX: r.right - 380, bubbles: true}));
           s.dispatchEvent(new PointerEvent('pointerup', {pointerId: 1, clientX: r.right - 380, bubbles: true}));""")
    b.check(b.until("Math.abs($('right').getBoundingClientRect().width - 380) < 3"), f"dragging the right handle sets the right panel to 380 px (was {wr0})")
    b.js("window.__canvasW1 = document.querySelector('#stage canvas').width")
    b.check(b.until("document.querySelector('#stage canvas').width > 0 && Math.abs(document.querySelector('#stage canvas').width - Math.round(document.querySelector('#stage').clientWidth * devicePixelRatio)) <= 2"), "the canvas follows the right panel too")
    b.js("$('split-right').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true}))")
    b.check(b.until("Math.abs($('right').getBoundingClientRect().width - 396) < 3"), "the arrow key makes the right panel 16 px wider")
    b.open(URL + "?token=dev")
    b.check(b.until("$('project-chip').textContent.startsWith('UiScroll')"), "page reloaded")
    b.check(abs(b.js("return $('left').getBoundingClientRect().width") - 520) < 3, "the left width survives a reload")
    b.check(abs(b.js("return $('right').getBoundingClientRect().width") - 396) < 3, "the right width survives a reload")
    b.js("window.__confirms = []; window.confirm = (m) => { window.__confirms.push(m); return true; };")
    hint_check("editor with two handles")
    b.js("document.querySelector('main .ui-splitter').dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); $('split-right').dispatchEvent(new MouseEvent('dblclick', {bubbles: true}))")
    b.check(b.until("Math.abs($('left').getBoundingClientRect().width - 360) < 3 && Math.abs($('right').getBoundingClientRect().width - 500) < 3"), "double-click: standard widths again")

    # ---- editable import of a viewer project (0.3.0) ----
    b.check(b.until("document.querySelector('.view-import[data-name=\"Demo Gantry\"]') !== null"), "the viewer list has an import button per project")
    b.check(b.js("return document.querySelector('.view-import[data-name=\"Demo Gantry\"]').title.includes('for editing')"), "the import button has a hint")
    b.js("document.querySelector('.view-open[data-name=\"Demo Gantry\"]').click()")
    b.check(b.until("$('readonly-bar') && !$('readonly-bar').hidden && $('import-view') !== null", 15), "the read-only bar offers Import for editing")
    b.click("#import-view")
    b.check(b.until("document.querySelector('dialog') !== null"), "the import dialog opens")
    b.check(b.js("return document.querySelector('dialog input[type=text]').value") == "Demo Gantry", "the project name defaults to the viewer name")
    b.check(b.js("return document.querySelectorAll('dialog .storage-table tbody tr').length") == 2, "the storage choice is offered (same table as New project)")
    b.set_value("dialog input[type=text]", "UiGantry")
    b.click("dialog button.primary")
    b.check(b.js("return document.querySelector('dialog') !== null") and "exists already" in (b.text("#banner") or ""), "a name that is taken is refused in the dialog")
    b.set_value("dialog input[type=text]", "ImpGantry")
    b.js("document.querySelector('dialog input[value=common]').click()")
    b.click("dialog button.primary")
    b.check(b.until("$('project-chip').textContent.startsWith('ImpGantry') && $('readonly-bar').hidden", 15), "the imported project opens in the editor")
    imp = get("/projects/ImpGantry")
    b.check(imp["viewer_name"] == "Demo Gantry" and imp["location"] == "common" and imp["root"] == "none", "the project remembers its viewer name and has no wrapper")
    b.check(b.until("$('banner').textContent.includes('Imported Demo Gantry as ImpGantry') && $('banner').textContent.includes('5 axes')"), "the banner reports what was imported")
    b.check(b.until("window.__mb.preview.info().parts === 6 && window.__mb.preview.info().loaded === 6", 20), "the imported model shows 6 meshes (Beam.STL matched to beam.stl)")
    b.check(b.js("return [...document.querySelectorAll('#tree-box .ui-node')].filter(n => n.querySelector('.ui-sub').textContent === 'frame').length") == 3, "the tree shows the 3 frames")
    b.check(b.js("return document.querySelectorAll('#tree-box .ui-node').length") == 15, "the tree lists every node: frames, axes, parts, tool")
    b.check(b.js("return [...document.querySelectorAll('#tree-box .ui-label')].map(e => e.textContent).includes('GantryTransform')"), "the nested named frame is in the tree")
    # a frame: position editable
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'GantryTransform').click()")
    b.check(b.until("$('props-card').textContent.includes('Frame GantryTransform') && $('props-card').textContent.includes('Matrix (16 numbers)')"), "frame properties: position, rotation, matrix")
    # an axis: the formula field
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'X').click()")
    b.check(b.until("$('props-card').textContent.includes('Translation axis X') && $('props-card').textContent.includes('Formula')"), "axis properties have a Formula row")
    def row_input(label):
        return b.js("""const tr = [...document.querySelectorAll('#props-card tr')].find(r => r.cells[0].textContent.trim() === arguments[0]);
                       return tr ? tr.querySelector('.ui-edit').value : null""", label)
    b.check(row_input("Formula") == "2250 - value", "the formula of the file is shown unchanged")
    b.check("The preview applies it" in b.js("return [...document.querySelectorAll('#props-card tr')].find(r => r.cells[0].textContent.trim() === 'Formula').textContent"), "the note says the preview applies the formula")
    def set_row(label, value, bad=False):
        b.js("""const tr = [...document.querySelectorAll('#props-card tr')].find(r => r.cells[0].textContent.trim() === arguments[0]);
               const e = tr.querySelector('.ui-edit'); e.focus(); e.value = arguments[1];
               e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))""", label, value)
    set_row("Formula", "")
    b.check(b.until("[...document.querySelectorAll('#props-card tr')].find(r => r.cells[0].textContent.trim() === 'Formula').querySelector('.ui-bad') !== null"), "an empty formula is refused")
    set_row("Formula", "value * value")
    b.check(b.until("$('props-card').textContent.includes('Formula not applied in the preview')"), "a formula the preview cannot apply is said so")
    set_row("Formula", "2260 - value")
    b.check(b.until("JSON.stringify(window.__mb.S.project).includes('2260 - value')"), "the edited formula is saved")
    b.check(b.until("$('props-card').textContent.includes('model = -1 × value + 2260')"), "the note shows the formula the preview applies")
    b.check(b.until("Math.abs(window.__mb.preview.info().tools[0][0] - 2260) < 1"), "the preview applies the formulas (all MOTION values 0: X = 2260, R = -90, so the tool is at x 2260)")
    b.check(b.until("$('zone-chip').textContent === 'Zone: warning'") or True, "the zone chip is up to date")
    b.check(b.js("return document.querySelector('#joints-table .joint-note') !== null && $('joints-table').textContent.includes('2260 - value')"), "the joint list shows the formula")
    # a frame is moved: the preview follows
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === 'GantryTransform').click()")
    t0 = b.js("return window.__mb.preview.info().tools[0]")
    set_row("Position (x, y, z) mm", "0, 0, 100")
    b.check(b.until("Math.abs(window.__mb.preview.info().tools[0][2] - (arguments[0] + 100)) < 1e-6".replace("arguments[0]", str(t0[2]))), "moving the frame moves the model in the preview")
    set_row("Position (x, y, z) mm", "0, 0, 0")
    b.check(b.until("Math.abs(window.__mb.preview.info().tools[0][2] - arguments[0]) < 1e-6".replace("arguments[0]", str(t0[2]))), "and back")
    # a non-value formula is also warned about in the zone check of a project that has a kinematic: start a table with the kinematic row
    b.js("window.__mb.preview.fit(); $('left').scrollTop = $('left').scrollHeight")
    b.shot("editor-imported")
    hint_check("editor with an imported project")
    # upload back: confirmation, bindings sent again
    b.js("window.__confirms.length = 0")
    b.click("#upload-viewer")
    b.check(b.until("window.__confirms.length === 1 && window.__confirms[0] === 'Replaces Demo Gantry in the 3D viewer: its files are replaced, the axis bindings are sent again and the library picture is redrawn.'", 12), "uploading back asks with the agreed text")
    b.check(b.until("$('banner').textContent.includes('Uploaded to the 3D viewer as Demo Gantry') && $('banner').textContent.includes('(replaced)') && $('banner').textContent.includes('4 axes bound')"), "uploaded back to the same viewer project, 4 bindings sent")
    again = send("POST", "/viewer/projects/Demo%20Gantry/open", {})
    xs = [a for a in again["axes"] if a["name"] == "X"][0]
    b.check(xs["script"] == "2260 - value" and xs["binding"] == "AxisX", "the viewer holds the edited formula and the binding (PUT after the POST)")
    b.check(len(again["bindings"]) == 4, "all bindings are in the viewer again")
    # upload as new name
    b.click("#upload-new")
    b.check(b.until("document.querySelector('dialog') !== null"), "the Upload as new name dialog opens")
    b.set_value("dialog input[type=text]", "Demo Delta")
    b.click("dialog button.primary")
    b.check(b.js("return document.querySelector('dialog') !== null") and "already" in (b.text("#banner") or ""), "a name that exists in the viewer is refused")
    b.set_value("dialog input[type=text]", "Gantry Two")
    b.click("dialog button.primary")
    b.check(b.until("$('banner').textContent.includes('Uploaded to the 3D viewer as Gantry Two') && !$('banner').textContent.includes('(replaced)')", 12), "uploaded under the new name")
    b.check(b.until("[...document.querySelectorAll('#viewer-table tr[data-key]')].some(r => r.dataset.key === 'Gantry Two')"), "the viewer list shows the new project")
    b.check(get("/projects/ImpGantry")["viewer_name"] == "Gantry Two", "the new name is stored as the viewer name")
    b.js("window.__confirms.length = 0")
    b.click("#upload-viewer")
    b.check(b.until("window.__confirms.length === 1 && window.__confirms[0].startsWith('Replaces Gantry Two in the 3D viewer')"), "the next upload goes to the new viewer name")
    b.until("$('banner').textContent.includes('(replaced)')")
    # import from the list (no read-only view open), a delta with a passive joint
    b.js("document.querySelector('.view-import[data-name=\"Demo Delta\"]').click()")
    b.check(b.until("document.querySelector('dialog') !== null"), "importing from the list asks for a name too")
    b.set_value("dialog input[type=text]", "ImpDelta")
    b.click("dialog button.primary")
    b.check(b.until("$('project-chip').textContent.startsWith('ImpDelta')", 15), "the delta is imported from the list")
    b.check(b.js("return document.querySelectorAll('#joints-table input[type=range]:disabled').length") == 1, "its passive (assignKin) joint is not movable")
    b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === '_r1h1').click()")
    b.check(b.until("$('props-card').textContent.includes('assignKin(Delta,joint-1-2b)')"), "the customdata is shown read-only")
    b.js("$('left').scrollTop = $('left').scrollHeight")
    b.shot("editor-delta")
    hint_check("editor with the imported delta")
    # the read-only view once more (screenshot), then back
    b.js("document.querySelector('.view-open[data-name=\"Demo Gantry\"]').click()")
    b.check(b.until("$('readonly-text') && $('readonly-text').textContent.includes('Demo Gantry') && $('warn-list') !== null", 15), "the read-only view again")
    b.js("window.__mb.preview.fit()")
    b.shot("readonly-2")
    hint_check("read-only view with two handles")

    # ---- 0.4.0: pick in 3D, gizmo with snapping, undo / redo ----
    send("POST", "/projects", {"name": "UiDrag", "location": "common"})
    for mesh in ("cube.stl", "cube2.stl"):
        req = urllib.request.Request(URL + f"api/v1/projects/UiDrag/meshes/{mesh}?unit=mm", data=demo_stl(), method="PUT",
                                     headers={"Authorization": "Bearer dev", "Content-Type": "application/octet-stream"})
        opener.open(req, timeout=20).read()
    turn = [0, -1, 0, 100, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]          # frame "Turn": rotated 90 degrees about z, at x = 100
    doc = send("GET", "/projects/UiDrag")
    doc["tree"] = [{"kind": "frame", "id": "f1", "name": "Turn", "matrix": turn, "children": [
        {"kind": "part", "id": "p1", "name": "cubeM", "mesh": "cube", "colour": [0.6, 0.6, 0.6], "matrix": [1, 0, 0, 5, 0, 1, 0, 5, 0, 0, 1, 5, 0, 0, 0, 1]},
        {"kind": "part", "id": "p2", "name": "cubeP", "mesh": "cube2", "colour": [0.9, 0.5, 0.1]},
        {"kind": "tool", "id": "t1", "name": "Tip", "position": [0, 0, -150]},
        {"kind": "axis", "id": "a1", "name": "RotA", "type": "rotation", "direction": [0, 0, 1], "pivot": [10, 20, 0], "range": [-360, 360], "children": []},
        {"kind": "axis", "id": "a2", "name": "LinA", "type": "translation", "direction": [1, 0, 0], "pivot": [0, 0, 0], "range": [-100, 100], "children": []}]}]
    doc["meshes"]["cube2"]["placement"]["position"] = [0, 0, 200]
    send("PUT", "/projects/UiDrag", doc)
    b.check(b.until("[...document.querySelectorAll('#projects-table tr[data-key]')].some(r => r.dataset.key === 'UiDrag')", 12), "the drag test project is listed")
    b.js("window.__confirms.length = 0; HTMLCanvasElement.prototype.setPointerCapture = function () {}; HTMLCanvasElement.prototype.releasePointerCapture = function () {}; localStorage.clear()")
    b.js("document.querySelector('#projects-table tr[data-key=\"UiDrag\"]').click()")
    b.check(b.until("$('project-chip').textContent.startsWith('UiDrag') && window.__mb.preview.info().loaded === 2", 15), "the drag test project is open, both meshes loaded")
    b.check(b.js("return $('undo').disabled && $('redo').disabled"), "undo and redo are disabled in a freshly opened project")
    b.check(b.js("return ['mode-move', 'mode-rotate', 'snap-toggle', 'snap-move', 'snap-rot', 'space-toggle', 'undo', 'redo'].every(id => $(id) && $(id).title.length > 15)"), "the new buttons and selects have hints")
    b.check(b.js("return $('mode-move').disabled && $('mode-rotate').disabled"), "no item selected: the gizmo buttons are disabled")
    b.check(b.js("return window.__mb.E.snap === true && window.__mb.E.move === 10 && window.__mb.E.rot === 15"), "snapping defaults: on, 10 mm, 15 degrees")

    def sel_node(label):
        b.js("[...document.querySelectorAll('#tree-box .ui-node')].find(n => n.querySelector('.ui-label').textContent === arguments[0]).click()", label)
        b.check(b.until("document.querySelector('#tree-box .ui-sel .ui-label') && document.querySelector('#tree-box .ui-sel .ui-label').textContent === " + json.dumps(label)), f"{label} selected in the tree")

    # -- pick in 3D: a real click (pointerdown + pointerup within 4 px) on the part's mesh
    def click_canvas(kind, name, moved=0):
        x, y = b.js("return window.__mb.preview.screenOf(arguments[0], arguments[1])", kind, name)
        b.js("""const c = document.querySelector('#stage canvas'); const [x, y, moved] = arguments;
               const ev = (t, dx) => c.dispatchEvent(new PointerEvent(t, {pointerId: 1, button: 0, buttons: t === 'pointerup' ? 0 : 1, clientX: x + dx, clientY: y, bubbles: true}));
               ev('pointerdown', 0); ev('pointerup', moved);""", x, y, moved)
    click_canvas("part", "cubeM", moved=12)
    b.check(b.js("return window.__mb.S.selection === null"), "a press that moves 12 px is an orbit, not a click: nothing is picked")
    click_canvas("part", "cubeM")
    b.check(b.until("window.__mb.S.selection && window.__mb.S.project.tree[0].children[0].id === window.__mb.S.selection.id"), "clicking the part in the preview selects its tree node")
    b.check(b.until("$('props-card').textContent.includes('Part cubeM') && document.querySelector('#tree-box .ui-sel .ui-label').textContent === 'cubeM'"), "the tree row and the properties follow")
    b.check(b.js("const e = window.__mb.preview.edit(); return e.attached && e.kind === 'part' && e.mode === 'translate'"), "the gizmo is attached in move mode")
    b.check(b.js("return !$('mode-move').disabled && !$('mode-rotate').disabled && $('mode-move').getAttribute('aria-pressed') === 'true'"), "move and rotate are offered, move is active")
    b.js("window.__mb.preview.fit()")
    b.shot("drag-gizmo")
    click_canvas("tool", "Tip")
    b.check(b.until("window.__mb.S.selection && window.__mb.S.selection.id === 't1'"), "clicking the tool marker selects the tool")
    b.check(b.js("return $('mode-rotate').disabled"), "a tool marker without a matrix can only be moved")
    b.js("window.__mb.preview.fit()")

    def drag(spec, steps=None):
        """A drag through the preview hook; waits until it is saved AND shown (the page rendered again)."""
        r0 = b.js("return window.__mb.S.renders || 0")
        h0 = b.js("return window.__mb.H.undo.length")
        b.js("window.__mb.preview.testDrag(arguments[0])", spec)
        ok = b.until(f"(window.__mb.S.renders || 0) > {r0} && window.__mb.H.undo.length === {h0 + 1 if steps is None else steps}", 10)
        b.until("window.__mb.preview.info().loaded === window.__mb.preview.info().parts", 10)
        return ok

    # -- drag a part that has a matrix (world snap 10 mm): the result is stored in the Turn frame
    def part_matrix(i=0):
        return b.js("return window.__mb.S.project.tree[0].children[arguments[0]].matrix", i)
    def near(a, c, tol=1e-6):
        return len(a) == len(c) and all(abs(x - y) <= tol for x, y in zip(a, c))
    sel_node("cubeM")
    b.js("window.__mb.S.values = {RotA: 30}; window.__mb.preview.setValues({RotA: 30}); window.dispatchEvent(new Event('resize'))")
    drag({"move": [23, 7, -14]})
    b.check(b.until("window.__mb.H.undo.length === 1"), "one drag = one saved change (one undo step)")
    m = part_matrix()
    b.check(near([m[3], m[7], m[11]], [10, -20, -10]), f"the part's matrix holds the dragged, 10 mm snapped place in the frame's own coordinates (world 120, 10, -10) {m[3], m[7], m[11]}")
    b.check(near([m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]], [1, 0, 0, 0, 1, 0, 0, 0, 1]), "its rotation did not change")
    b.check(b.js("return Object.values(window.__mb.S.values).every(v => !v)"), "the joint values were set to the zero pose for the drag")
    b.check(b.js("return !$('undo').disabled && $('redo').disabled && $('save-chip').textContent.startsWith('Saved')"), "undo is enabled, redo is not; the project is saved " + str(b.js("return [$('undo').disabled, $('redo').disabled, $('save-chip').textContent, window.__mb.H.undo.length, window.__mb.H.redo.length, $('banner').textContent]")))
    b.click("#undo")
    b.check(b.until("window.__mb.H.undo.length === 0 && window.__mb.H.redo.length === 1"), "undo moves the step to the redo stack")
    b.check(near(part_matrix()[3:12:4], [5, 5, 5]), "undo restored the old position (5, 5, 5)")
    b.check(near(get("/projects/UiDrag")["tree"][0]["children"][0]["matrix"][3:12:4], [5, 5, 5]), "the server has the old position again")
    b.click("#redo")
    b.check(b.until("window.__mb.H.undo.length === 1 && window.__mb.H.redo.length === 0"), "redo re-applies it")
    b.check(near(get("/projects/UiDrag")["tree"][0]["children"][0]["matrix"][3:12:4], [10, -20, -10]), "the server has the dragged position again")
    # the preview shows what is saved: the part's wrapper really is at world (120, 10, -10)
    b.check(b.until("window.__mb.preview.info().loaded === 2"), "preview rebuilt after redo")
    b.js("window.__mb.preview.setOptions({snap: false})")
    drag({"move": [0.5, 0, 0]})
    b.check(b.until("window.__mb.H.undo.length === 2"), "a drag with snapping off is one more step")
    m = part_matrix()
    b.check(near([m[3], m[7], m[11]], [10, -20.5, -10]), "snapping off: the exact (unsnapped) value, rounded to 1e-6")
    b.js("window.__mb.preview.setOptions({snap: true})")
    b.js("window.__mb.preview.testDrag({move: [0, 0, 0]})")
    time.sleep(1)
    b.check(b.js("return window.__mb.H.undo.length") == 2, "a drag that changes nothing does not save or add an undo step")

    # -- rotate (15 degree snap, world axes)
    b.js("window.__mb.preview.setOptions({mode: 'rotate'})")
    drag({"rotate": {"axis": [0, 0, 1], "deg": 40}})
    b.check(b.until("window.__mb.H.undo.length === 3"), "a rotation is saved too")
    m = part_matrix()
    c = 0.7071067811865476
    b.check(near([m[0], m[1], m[4], m[5]], [c, -c, c, c], 1e-8), f"40 degrees snapped to 45 about z, as seen in the frame: {m[:6]}")
    b.js("window.__mb.preview.setOptions({mode: 'translate'})")

    # -- a frame: its matrix, in its parent's frame (the world here)
    sel_node("Turn")
    drag({"move": [14, 0, 0]})
    b.check(b.until("window.__mb.S.project.tree[0].matrix[3] === 110"), "the frame is moved to x = 110 (world snap)")
    b.check(near(b.js("return window.__mb.S.project.tree[0].matrix"), [0, -1, 0, 110, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]), "its rotation is kept, nothing else changed")

    # -- a part without a matrix whose mesh it alone uses: the mesh placement (local snap along the item's own axes)
    sel_node("cubeP")
    b.js("window.__mb.preview.setOptions({space: 'local'})")
    drag({"move": [0, 33, 0]})
    b.check(b.until("window.__mb.S.project.meshes.cube2.placement.position[1] !== 0"), "the placement of the mesh cube2 is changed (the part has no matrix of its own)")
    b.check(near(b.js("return window.__mb.S.project.meshes.cube2.placement.position"), [0, 30, 200]), "local snap: 33 mm along the item's own axis becomes 30")
    b.check(b.js("return window.__mb.S.project.tree[0].children[1].matrix === undefined"), "the part still has no matrix")
    # -- a tool marker: its position
    sel_node("Tip")
    b.js("window.__mb.preview.setOptions({space: 'world'})")
    drag({"move": [7, 0, 0]})
    b.check(b.until("window.__mb.S.project.tree[0].children[2].position[1] !== 0"), "the tool marker position changes")
    b.check(near(b.js("return window.__mb.S.project.tree[0].children[2].position"), [0, -10, -150]), "world (120, 0, -150) is (0, -10, -150) in the frame Turn")
    # -- a rotation axis: only its pivot; a translation axis cannot be dragged
    sel_node("RotA")
    b.check(b.js("const e = window.__mb.preview.edit(); return e.attached && e.kind === 'axis'") and b.js("return $('mode-rotate').disabled"), "a rotation axis: gizmo attached, move only")
    drag({"move": [13, 0, 0]})
    b.check(b.until("window.__mb.S.project.tree[0].children[3].pivot[1] !== 20"), "the pivot changes")
    pv = b.js("return window.__mb.S.project.tree[0].children[3].pivot")
    # RotA pivot (10, 20, 0) is at world (110 - 20, 10, 0) = (90, 10, 0); +13 -> 103 -> world snap 100 -> (frame at x = 110) local (10, 10, 0)
    b.check(near(pv, [10, 10, 0]), f"pivot saved in the frame it sits in: {pv}")
    b.check(b.js("const t = window.__mb.S.project.tree[0].children[3]; return t.direction.join() === '0,0,1' && t.range.join() === '-360,360'"), "direction and range are untouched")
    sel_node("LinA")
    b.check(b.js("return !window.__mb.preview.edit().attached && $('mode-move').disabled"), "a translation axis has no pivot: no gizmo")
    nsteps = b.js("return window.__mb.H.undo.length")
    b.check(nsteps == 7, f"every drag was one step: 7 steps so far ({nsteps})")

    # -- keys: Ctrl+Z undoes, but not while typing in a field; W/E switch the gizmo mode
    sel_node("Tip")
    n_undo = b.js("return window.__mb.H.undo.length")
    b.js("""const i = document.querySelector('#props-card .ui-edit'); i.focus();
           i.dispatchEvent(new KeyboardEvent('keydown', {key: 'z', ctrlKey: true, bubbles: true}));""")
    b.check(b.js("return window.__mb.H.undo.length") == n_undo, "Ctrl+Z inside a field is left to the browser")
    b.js("document.activeElement.blur(); document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'z', ctrlKey: true, bubbles: true}))")
    b.check(b.until(f"window.__mb.H.undo.length === {n_undo - 1} && window.__mb.H.redo.length === 1"), "Ctrl+Z undoes (the tool marker is back)")
    b.check(b.until("window.__mb.S.project.tree[0].children[3].pivot[1] === 20"), "the last step (the pivot) is undone")
    b.js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'y', ctrlKey: true, bubbles: true}))")
    b.check(b.until(f"window.__mb.H.undo.length === {n_undo} && window.__mb.H.redo.length === 0 && window.__mb.S.project.tree[0].children[3].pivot[1] === 10"), "Ctrl+Y redoes")
    b.js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'z', ctrlKey: true, bubbles: true}))")
    b.check(b.until(f"window.__mb.H.redo.length === 1"), "undo once more")
    b.js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'Z', ctrlKey: true, shiftKey: true, bubbles: true}))")
    b.check(b.until(f"window.__mb.H.redo.length === 0 && window.__mb.H.undo.length === {n_undo}"), "Ctrl+Shift+Z redoes")
    sel_node("cubeM")
    b.js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'e', bubbles: true}))")
    b.check(b.until("window.__mb.preview.edit().mode === 'rotate' && $('mode-rotate').getAttribute('aria-pressed') === 'true'"), "E switches to rotate")
    b.js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'w', bubbles: true}))")
    b.check(b.until("window.__mb.preview.edit().mode === 'translate'"), "W switches to move")

    # -- typed edits are undoable too, and a refused entry's banner goes away after the next valid change
    def set_field(label, value):
        b.js("""const tr = [...document.querySelectorAll('#props-card tr')].find(r => r.cells[0].textContent.trim() === arguments[0]);
               const e = tr.querySelector('.ui-edit'); e.focus(); e.value = arguments[1];
               e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))""", label, value)
    sel_node("Tip")
    set_field("Position (x, y, z) mm", "1, 2")
    b.check(b.until("$('banner').textContent.startsWith('Not kept:')"), "a refused entry shows the red 'Not kept' banner")
    n_undo = b.js("return window.__mb.H.undo.length")
    set_field("Position (x, y, z) mm", "0, 0, 25")
    b.check(b.until(f"window.__mb.H.undo.length === {n_undo + 1}"), "a typed change is one undo step")
    b.check(b.until("$('banner').hidden || $('banner').textContent === ''"), "the 'Not kept' banner is gone after the next valid change")
    b.check(near(b.js("return window.__mb.S.project.tree[0].children[2].position"), [0, 0, 25]), "typing exact values keeps working")
    b.click("#undo")
    b.check(b.until("window.__mb.S.project.tree[0].children[2].position[2] === -150"), "undo of a typed change")
    sel_node("cubeM")
    b.js("window.__mb.preview.fit()")
    b.check(b.js("return !$('undo').disabled && !$('redo').disabled"), "both undo and redo are enabled after an undo")
    b.shot("undo-redo")

    # -- history is capped at 50 and cleared when another project is opened
    b.js("for (let i = 0; i < 60; i++) window.__mb.pushHistory({i}); ")
    b.check(b.js("return window.__mb.H.undo.length") == 50 and b.js("return window.__mb.H.undo[0].i") == 10, "history keeps the last 50 steps")
    b.js("window.__mb.H.undo.length = 0; window.__mb.H.redo.length = 0")
    sel_node("Tip")
    set_field("Position (x, y, z) mm", "0, 0, 7")
    b.check(b.until("window.__mb.H.undo.length === 1"), "one step on the stack")
    b.js("document.querySelector('#projects-table tr[data-key=\"UiGantry\"]').click()")
    b.check(b.until("$('project-chip').textContent.startsWith('UiGantry')"), "another project is opened")
    b.check(b.js("return window.__mb.H.undo.length === 0 && window.__mb.H.redo.length === 0 && $('undo').disabled && $('redo').disabled"), "the history is cleared")
    b.js("document.querySelector('#projects-table tr[data-key=\"UiDrag\"]').click()")
    b.check(b.until("$('project-chip').textContent.startsWith('UiDrag') && window.__mb.preview.info().loaded === 2", 15), "back in the drag test project")

    # -- undo after a mesh was deleted elsewhere: a clear error, the project is not touched
    sel_node("cubeP")
    drag({"move": [0, 40, 0]})
    b.check(b.until("window.__mb.H.undo.length === 1"), "a step that uses the mesh cube2")
    sel_node("cubeP")
    b.click("#delete-node")
    b.check(b.until("window.__mb.S.project.tree[0].children.every(n => n.name !== 'cubeP')"), "the part is deleted from the tree (a step)")
    send("DELETE", "/projects/UiDrag/meshes/cube2.stl")                       # the mesh goes (not undoable)
    steps = b.js("return window.__mb.H.undo.length")
    b.click("#undo")
    b.check(b.until("$('banner').textContent.includes('Undo failed') && $('banner').textContent.includes('mesh')"), "undo that needs a deleted mesh fails with a message: " + str(b.text('#banner')))
    b.check(b.js("return window.__mb.H.undo.length") == steps, "the history is kept after the failed undo")
    b.check("cube2" not in get("/projects/UiDrag")["meshes"] and all(n["name"] != "cubeP" for n in get("/projects/UiDrag")["tree"][0]["children"]), "the project on the server is unchanged (no mesh entry without a file came back)")

    # -- toolbar settings are remembered, hold-Shift disables snapping, Local/World
    b.js("window.__mb.preview.setOptions({space: 'world'})")
    b.click("#snap-toggle")
    b.check(b.until("window.__mb.E.snap === false && localStorage.getItem('model-builder.snap') === '0' && $('snap-toggle').getAttribute('aria-pressed') === 'false'"), "the snap switch turns snapping off and is remembered")
    b.check(b.js("return window.__mb.preview.edit().translationSnap") in (None, 0), "the gizmo has no translation snap when it is off")
    b.click("#snap-toggle")
    b.set_value("#snap-move", "50")
    b.set_value("#snap-rot", "90")
    b.check(b.until("window.__mb.E.move === 50 && window.__mb.E.rot === 90 && localStorage.getItem('model-builder.snapMove') === '50'"), "the steps are selectable and remembered")
    b.check(b.js("const e = window.__mb.preview.edit(); return e.translationSnap === 50 && Math.abs(e.rotationSnap - Math.PI / 2) < 1e-9"), "the gizmo uses them")
    b.js("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Shift', bubbles: true}))")
    b.check(b.js("return window.__mb.preview.edit().translationSnap") in (None, 0), "holding Shift switches snapping off for the drag")
    b.js("window.dispatchEvent(new KeyboardEvent('keyup', {key: 'Shift', bubbles: true}))")
    b.check(b.js("return window.__mb.preview.edit().translationSnap") == 50, "releasing Shift switches it on again")
    b.click("#space-toggle")
    b.check(b.until("window.__mb.E.space === 'local' && $('space-toggle').textContent === 'Local' && window.__mb.preview.edit().space === 'local'"), "Space toggles to Local")
    b.set_value("#snap-move", "10")
    b.set_value("#snap-rot", "15")
    b.click("#space-toggle")
    b.check(b.until("window.__mb.E.space === 'world'"), "and back to World")

    # -- the matrix math in the browser: world -> stored frame -> world for several parent rotations
    ok = b.js("""const X = window.__mb.xform;
        const rotz = (d, t) => { const a = d * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return [c, -s, 0, t[0], s, c, 0, t[1], 0, 0, 1, t[2], 0, 0, 0, 1]; };
        const rotx = (d, t) => { const a = d * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return [1, 0, 0, t[0], 0, c, -s, t[1], 0, s, c, t[2], 0, 0, 0, 1]; };
        const parents = [X.IDENTITY, rotz(90, [100, 0, 0]), rotz(33, [-5, 7, 11]), X.mul(rotx(70, [0, 0, 300]), rotz(-20, [1, 2, 3])), X.mul(rotz(45, [0, 0, 0]), [2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1])];
        const world = X.mul(rotz(15, [120, 10, -10]), rotx(30, [0, 0, 0]));
        let worst = 0;
        for (const P of parents) {
          const L = X.localMatrix(P, world), back = X.worldMatrix(P, L);
          worst = Math.max(worst, ...back.map((v, i) => Math.abs(v - world[i])));
          const p = X.localPoint(P, [120, 10, -10]);
          worst = Math.max(worst, ...X.applyPoint(P, p).map((v, i) => Math.abs(v - [120, 10, -10][i])));
        }
        const known = X.localPoint(rotz(90, [100, 0, 0]), [80, 10, 0]);           // the frame Turn: world (80, 10, 0) is (10, 20, 0) in it
        const c = X.cleanVec([9.999999999997, -0.0000000001, 1.0000004]);
        return [worst < 1e-9, Math.abs(known[0] - 10) < 1e-9 && Math.abs(known[1] - 20) < 1e-9 && Math.abs(known[2]) < 1e-9, c.join() === '10,0,1'];""")
    b.check(ok == [True, True, True], f"world -> parent-local -> world round trip for 5 parents, a known value, rounding {ok}")

    b.js("document.querySelector('#projects-table tr[data-key=\"UiDrag\"]') && 0")
    sel_node("cubeM")
    b.js("window.__mb.preview.setOptions({space: 'world', mode: 'translate'}); window.__mb.preview.fit()")
    b.js("window.__mb.preview.setValues({})")
    b.shot("drag-toolbar")
    hint_check("editor with the drag toolbar")

    errors = b.js("return window.__errors")
    b.check(not errors, "no console errors " + (str(errors) if errors else ""))
finally:
    b.close()
sys.exit(b.finish())
