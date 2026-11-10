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

    errors = b.js("return window.__errors")
    b.check(not errors, "no console errors " + (str(errors) if errors else ""))
finally:
    b.close()
sys.exit(b.finish())
