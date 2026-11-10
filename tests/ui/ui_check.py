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

    # every visible control has a hover hint
    missing = b.js("""return [...document.querySelectorAll('button, input, select, textarea, .chip, th, canvas')]
        .filter(e => e.offsetParent !== null && !e.closest('[title]') && e.type !== 'hidden')
        .map(e => e.tagName + '#' + e.id + '.' + e.className + ' ' + (e.textContent || '').slice(0, 20))""")
    b.check(not missing, "every visible button, field, header and status has a hint " + (str(missing) if missing else ""))
    errors = b.js("return window.__errors")
    b.check(not errors, "no console errors " + (str(errors) if errors else ""))
finally:
    b.close()
sys.exit(b.finish())
