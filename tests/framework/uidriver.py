# SPDX-License-Identifier: MIT

"""Headless Firefox over plain WebDriver (geckodriver), for the apps' tests/ui/ui_check.py. No selenium needed.

    b = Browser(screenshots=sys.argv[1] if len(sys.argv) > 1 else None)
    try:
        b.open("http://127.0.0.1:12345/my-app/?token=dev")
        b.check(b.until("$('state').textContent !== '-'"), "state is shown")   # $(id): document.getElementById
        b.click("#save"); b.set_value("#name", "x"); b.text("#banner")
        b.shot("main")
    finally:
        b.close()
    sys.exit(b.finish())          # prints ALL OK or FAILED: ...; 0 or 1

geckodriver: /snap/bin/firefox.geckodriver --port 4444 (Ubuntu's Firefox snap; screenshots then must go to a folder
under ~/snap/firefox/common). Run the app against a FRESH fake backend each time.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request


class Browser:

    def __init__(self, webdriver="http://127.0.0.1:4444", screenshots=None, width=1300, height=800):
        self.wd, self.out, self.failures = webdriver, screenshots, []
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        caps = {"browserName": "firefox", "moz:firefoxOptions": {"args": ["-headless", f"--width={width}",
                                                                          f"--height={height}"]}}
        self.session = "/session/" + self.call("POST", "/session", {"capabilities": {"alwaysMatch": caps}})["sessionId"]

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.wd + path, method=method, headers={"Content-Type": "application/json"},
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with self.opener.open(req, timeout=60) as r:
                return json.loads(r.read())["value"]
        except urllib.error.HTTPError as e:
            try:
                v = json.loads(e.read())["value"]
                detail = f"{v.get('error')}: {v.get('message')}"
            except (ValueError, KeyError, AttributeError):
                detail = str(e)
            raise RuntimeError(f"WebDriver {method} {path}: {detail}") from None

    def open(self, url):
        self.call("POST", self.session + "/url", {"url": url})

    def js(self, script, *args):
        """Run script in the page. $(id) is document.getElementById (WebDriver scripts don't see the page's own
        top-level const/let, e.g. ctrlx.js's $)."""
        script = "const $ = (id) => document.getElementById(id);\n" + script
        return self.call("POST", self.session + "/execute/sync", {"script": script, "args": list(args)})

    def until(self, expr, timeout=8) -> bool:
        """Wait until the JavaScript expression is true."""
        end = time.time() + timeout
        while time.time() < end:
            if self.js("return (" + expr + ")"):
                return True
            time.sleep(0.2)
        return False

    def click(self, selector):
        self.js("document.querySelector(arguments[0]).click()", selector)

    def set_value(self, selector, value):
        """Set an input's value as typing would (input and change events)."""
        self.js("const e = document.querySelector(arguments[0]); e.value = arguments[1];"
                "e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true}));",
                selector, value)

    def text(self, selector) -> str:
        return self.js("const e = document.querySelector(arguments[0]); return e ? e.textContent.trim() : null", selector)

    def check(self, cond, text):
        print(("ok   " if cond else "FAIL ") + text, flush=True)
        if not cond:
            self.failures.append(text)

    def shot(self, name):
        if self.out:
            os.makedirs(self.out, exist_ok=True)
            with open(os.path.join(self.out, name + ".png"), "wb") as f:
                f.write(base64.b64decode(self.call("GET", self.session + "/screenshot")))

    def close(self):
        try:
            self.call("DELETE", self.session)
        except Exception:
            pass

    def finish(self) -> int:
        print("FAILED: " + "; ".join(self.failures) if self.failures else "ALL OK", flush=True)
        return 1 if self.failures else 0
