#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""UI check of the framework components (www/framework/ui.js, ui.css) on tests/framework/ui_page.html in headless Firefox.
Run it from an app folder or from ctrlx-baseline/framework:

    /snap/bin/firefox.geckodriver --port 4444
    python3 tests/framework/ui_components_check.py <screenshot folder under ~/snap/firefox/common>

The page and the framework files are copied into the screenshot folder (the Firefox snap only reads files there).
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
from tests.framework.uidriver import Browser  # noqa: E402

shots = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/snap/firefox/common/ui-components"))
site = os.path.join(shots, "site")
shutil.rmtree(site, ignore_errors=True)
shutil.copytree(os.path.join(ROOT, "www", "framework"), os.path.join(site, "www", "framework"))
os.makedirs(os.path.join(site, "tests", "framework"))
shutil.copy(os.path.join(HERE, "ui_page.html"), os.path.join(site, "tests", "framework"))

b = Browser(screenshots=shots)


def key_on(css, key):
    b.js("const e = document.querySelector(arguments[0]); e.dispatchEvent(new KeyboardEvent('keydown', {key: arguments[1], bubbles: true}))", css, key)


def type_in(css, value, key="Enter"):
    b.js("const e = document.querySelector(arguments[0]); e.focus(); e.value = arguments[1]; e.dispatchEvent(new Event('input', {bubbles: true}))", css, value)
    if key:
        key_on(css, key)


def pick(css, value):
    b.js("const s = document.querySelector(arguments[0]); s.value = arguments[1]; s.dispatchEvent(new Event('change', {bubbles: true}))", css, value)


try:
    b.open("file://" + os.path.join(site, "tests", "framework", "ui_page.html"))
    b.js("localStorage.clear()")
    b.open("file://" + os.path.join(site, "tests", "framework", "ui_page.html"))
    b.check(b.until("window.T && $('title').textContent === 'Settings'"), "page opens on Settings")
    b.js("window.confirm = () => true")
    errs = b.js("return [...document.querySelectorAll('button, input, select, th, .ui-node, summary, .ui-search')].filter(e => !e.title && !e.closest('[title]')).map(e => e.outerHTML.slice(0, 60))")
    b.check(not errs, "every control has a hover hint " + str(errs[:3]))

    # tree
    b.check(b.js("return document.querySelectorAll('#tree .ui-node').length") == 3, "tree: 3 top nodes, Drive folded")
    b.click('#tree .ui-node[data-id="drive"]')
    b.check(b.until("document.querySelector('#tree .ui-node[data-id=\"params\"]') !== null"), "tree: a folder node unfolds on click")
    b.check(b.text('#title') == "Settings", "tree: a folder with select:false only folds")
    b.click('#tree .ui-node[data-id="lazy"] .ui-twisty')
    b.check(b.until("document.querySelector('#tree .ui-node[data-id=\"lazy-b\"] .ui-sub') !== null"), "tree: lazy children filled on unfold")
    b.click('#tree .ui-node[data-id="params"]')
    b.check(b.until("$('title').textContent === 'Parameters'"), "tree: a node opens its page")
    b.check(b.js("return document.querySelector('#tree .ui-node.ui-sel').dataset.id") == "params", "tree: selected node marked")

    # parameter table
    b.check(b.js("return document.querySelectorAll('#params tbody tr').length") == 100, "parameter table: 100 rows per page")
    b.check("1–100 of 150" in b.text(".ui-pager"), "parameter table: pager shows the range")
    b.check(b.js("return document.querySelector('tr[data-key=\"S-0-0002.0.0\"] .ui-edit') === null && document.querySelector('tr[data-key=\"S-0-0002.0.0\"] .ui-ro') !== null"), "read-only parameter is text")
    b.check(b.js("return document.querySelector('tr[data-key=\"S-0-0003.0.0\"] .ui-lock') !== null"), "locked parameter shows the lock")
    b.check("not readable" in b.text('tr[data-key="S-0-0004.0.0"]'), "a parameter error is shown in the value cell")
    b.click('tr[data-key="S-0-0005.0.0"] button')
    b.check(b.until("T.ran === 'S-0-0005.0.0'"), "command parameter: Run button")
    cell = 'tr[data-key="S-0-0001.0.0"] .ui-edit'
    type_in(cell, "77", key=None)
    b.check(b.js("return document.querySelector(arguments[0]).classList.contains('ui-dirty')", cell), "typing marks the field changed (yellow)")
    key_on(cell, "Escape")
    b.check(b.js("return document.querySelector(arguments[0]).value", cell) == "10", "Esc undoes the typed value")
    type_in(cell, "9999")
    b.check(b.until("document.querySelector(arguments[0]).classList.contains('ui-bad')".replace("arguments[0]", repr(cell))), "a refused value turns red")
    b.check("outside 0" in b.js("return document.querySelector(arguments[0]).title", cell), "the reason is in the hint")
    b.check(not b.js("return T.writes.length"), "nothing written for a refused value")
    type_in(cell, "42")
    b.check(b.until("T.writes.length === 1"), "Enter writes a good value")
    b.check(b.until(f"document.querySelector('tr[data-key=\"S-0-0001.0.0\"]').classList.contains('ui-flash-ok')"), "the kept row flashes green")
    type_in('tr[data-key="S-0-0006.0.0"] .ui-edit', "61", key=None)
    b.js("T.paramEl.uiUpdate('S-0-0006.0.0', {value: 999})")
    b.check(b.js("return document.querySelector('tr[data-key=\"S-0-0006.0.0\"] .ui-edit').value") == "61", "a refresh doesn't overwrite a field being edited")
    b.js("T.paramEl.uiUpdate('S-0-0007.0.0', {value: 555})")
    b.check(b.js("return document.querySelector('tr[data-key=\"S-0-0007.0.0\"] .ui-edit').value") == "555", "a refresh updates other rows")
    type_in(".ui-filter input", "Parameter 14", key="Enter")
    b.check(b.until("document.querySelectorAll('#params tbody tr').length === 11"), "filter box narrows the rows (14, 140-149)")
    key_on(".ui-filter input", "Escape")
    b.check(b.until("document.querySelectorAll('#params tbody tr').length === 100"), "Esc clears the filter")
    b.shot("ui-params")

    # search + back + focus
    type_in("#search", "Parameter 120", key="Enter")
    b.check(b.until("$('title').textContent.startsWith('Search')"), "search opens results")
    b.click("#page .linkbtn")
    b.check(b.until("$('title').textContent === 'Parameters' && document.querySelector('tr[data-key=\"S-0-0120.0.0\"]') !== null"), "a result opens its page on the right rows page")
    b.check(b.until("document.querySelector('tr[data-key=\"S-0-0120.0.0\"]').classList.contains('ui-flash')"), "the found row is highlighted")
    b.click("#back")
    b.check(b.until("$('title').textContent.startsWith('Search')"), "Back returns to the search results")
    key_on("#search", "Escape")
    b.check(b.until("$('title').textContent === 'Parameters'"), "clearing the search returns to the page before")

    # settings, choices, changes
    b.click('#tree .ui-node[data-id="settings"]')
    b.until("$('title').textContent === 'Settings'")
    b.check(b.js("return [...document.querySelectorAll('select.ui-edit')[0].options].map(o => o.value).join()") == "LINEAR,ROTARY", "a list of allowed values is a dropdown")
    b.check(b.js("return [...document.querySelectorAll('select.ui-edit')[1].options].map(o => o.textContent).join()") == "yes,no", "true/false is a yes/no dropdown")
    b.check(b.js("return [...document.querySelectorAll('th')].map(t => t.textContent).join()").startswith("Setting,Value,Note"), "settings table: Setting | Value | Note")
    pick("select.ui-edit", "ROTARY")
    b.check(b.until("T.changes.count === 1"), "picking a value keeps it")
    type_in('tr[data-key="Speed"] .ui-edit', "-5")
    b.check(b.until("document.querySelector('tr[data-key=\"Speed\"] .ui-edit.ui-bad') !== null"), "settings: refused value red")
    type_in('tr[data-key="Speed"] .ui-edit', "250")
    b.check(b.until("T.changes.count === 2"), "settings: second change kept")
    b.check(b.text("#badge") == "2", "commit button shows the count")
    b.check(b.js("return document.querySelector('#tree .ui-node[data-id=\"changes\"] .ui-flag-edited') !== null"), "tree flags the changes")
    # folding
    b.click("#collapse")
    b.check(b.js("return [...document.querySelectorAll('details.ui-sec')].every(d => !d.open)"), "Collapse all folds every section")
    b.open("file://" + os.path.join(site, "tests", "framework", "ui_page.html"))
    b.until("window.T && $('title').textContent === 'Settings'")
    b.check(b.js("return [...document.querySelectorAll('details.ui-sec')].every(d => !d.open)"), "folded sections stay folded after reloading")
    b.click("#expand")
    b.check(b.js("return [...document.querySelectorAll('details.ui-sec')].every(d => d.open)"), "Expand all unfolds them")
    b.check(b.js("return document.querySelector('#tree .ui-node[data-id=\"lazy\"]') !== null"), "unfolded tree nodes are remembered")
    # changes again (the reload lost them): undo of an earlier change also undoes the later ones of its group
    b.js("window.confirm = () => true")
    pick("select.ui-edit", "ROTARY")
    type_in('tr[data-key="Speed"] .ui-edit', "250")
    b.until("T.changes.count === 2")
    b.click('#tree .ui-node[data-id="changes"]')
    b.check(b.until("document.querySelectorAll('#page tbody tr').length === 2"), "Changes page lists the changes")
    b.click("#page tbody tr:first-child .ui-icon-btn")
    b.check(b.until("T.changes.count === 0 && T.drive.mode === 'LINEAR' && T.drive.speed === 100"), "undo of the first change also undoes the later one of the same group")
    b.click('#tree .ui-node[data-id="settings"]')
    b.until("$('title').textContent === 'Settings'")
    pick("select.ui-edit", "ROTARY")
    b.until("T.changes.count === 1")
    b.click("#commit")
    b.check(b.until("T.committed === 1 && T.changes.count === 0 && $('commit').disabled"), "commit asks, then clears the list")
    b.shot("ui-settings")
finally:
    b.close()
sys.exit(b.finish())
