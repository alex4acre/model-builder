#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

"""End-to-end UI check in headless Firefox (tests/framework/uidriver.py), against the simulated ctrlX.

    MODEL_BUILDER_FAKE=1 MODEL_BUILDER_DATA=<a folder that doesn't exist yet> python3 -m app.main   # a FRESH backend each run
    /snap/bin/firefox.geckodriver --port 4444
    python3 tests/ui/ui_check.py <screenshot folder>    # with the Firefox snap: a folder under ~/snap/firefox/common

Stop the backend and geckodriver by PID afterwards.
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app  # noqa: E402
from tests.framework.uidriver import Browser  # noqa: E402

PORT = int(os.environ.get(app.ENV + "_PORT", app.PORT))
URL = f"http://127.0.0.1:{PORT}/{app.NAME}/"

b = Browser(screenshots=sys.argv[1] if len(sys.argv) > 1 else None)
try:
    b.open(URL + "?token=dev")
    b.check(b.until("$('counter').textContent !== '-'"), "state is shown")
    b.check(b.until("$('conn').classList.contains('ok')"), "connection chip is green")
    b.check(b.until("document.querySelector('#settings .ui-edit') !== null"), "setpoint is an edit field (framework/ui.js)")
    b.js("const e = document.querySelector('#settings .ui-edit'); e.focus(); e.value = 'abc'; e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))")
    b.check(b.until("document.querySelector('#settings .ui-edit.ui-bad') !== null"), "a wrong setpoint is refused")
    b.js("const e = document.querySelector('#settings .ui-edit'); e.value = '12.5'; e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))")
    b.check(b.until("$('banner').textContent === 'Setpoint 12.5 saved'"), "setpoint saved on Enter")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(URL + "api/v1/config", timeout=5) as r:
        b.check(json.loads(r.read())["setpoint"] == 12.5, "the backend has the new setpoint")
    b.set_value("#path", "demo/flag")
    b.click("#read")
    b.check(b.until("$('result').textContent.trim() === 'false'"), "Data Layer read")
    b.set_value("#value", "true")
    b.click("#write")
    b.check(b.until("$('result').textContent.trim() === 'true'"), "Data Layer write")
    b.set_value("#path", "no/such/node")
    b.click("#read")
    b.check(b.until("!$('banner').hidden && $('banner').textContent.includes('INVALID_ADDRESS')"),
            "error shown in the banner")
    b.shot("main")
finally:
    b.close()
sys.exit(b.finish())
