// SPDX-License-Identifier: MIT
// ctrlx-baseline framework: what every app UI needs to talk to its REST API behind the ctrlX reverse proxy.
// Load it before the app's own script:  <script src="framework/ctrlx.js"></script>
//
// The ctrlX sidebar opens /<app>/?token=<bearer token>; the token is kept for the browser tab and sent back
// with every API call. API calls go to /<app>/api/v1, whichever page of the app is open (/<app>/tools, ...).

"use strict";

const APP_BASE = "/" + location.pathname.split("/")[1];
const API = APP_BASE + "/api/v1";
const TOKEN = (() => {
  const t = new URLSearchParams(location.search).get("token");
  try {
    if (t) sessionStorage.setItem("token", t);
    return t || sessionStorage.getItem("token") || "";
  } catch (e) {
    return t || "";
  }
})();

const $ = (id) => document.getElementById(id);

class ApiError extends Error {
  // status: HTTP status; code: the app's or the Data Layer's error code (e.g. "DL_PERMISSION_DENIED"), if any;
  // data: the whole answer (some errors carry more, e.g. a list of problems)
  constructor(message, status, code, data) {
    super(message);
    this.status = status;
    this.code = code || "";
    this.data = data;
  }
}

// api("GET", "/state"), api("PUT", "/items/a", {x: 1}), api("POST", "/upload", file, {raw: true})
// JSON in and out; with {raw: true} the body is sent as is and the Response is returned.
async function api(method, path, body, options = {}) {
  const opts = { method, headers: { Authorization: "Bearer " + TOKEN } };
  if (body !== undefined) {
    if (options.raw) {
      opts.body = body;
    } else {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
  }
  const r = await fetch(API + path, opts);
  if (options.raw && r.ok) return r;
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = { error: text }; }
  if (!r.ok) {
    const message = (data && data.error) || r.status + " " + r.statusText;
    throw new ApiError(message, r.status, data && data.code, data);
  }
  return data;
}

// A message line under the header: banner(text) for an error, banner(text, true) for a success, banner("") hides it.
function banner(text, ok) {
  const b = $("banner");
  if (!b) return;
  b.textContent = text || "";
  b.className = "banner" + (ok ? " ok" : "");
  b.hidden = !text;
}

// Call fn every ms milliseconds, one call at a time, paused while the tab is hidden. Returns a stop function.
function every(ms, fn) {
  let timer = null;
  let stopped = false;
  const tick = async () => {
    if (!document.hidden) {
      try { await fn(); } catch (e) { /* fn shows its own errors */ }
    }
    if (!stopped) timer = setTimeout(tick, ms);
  };
  tick();
  return () => { stopped = true; clearTimeout(timer); };
}
