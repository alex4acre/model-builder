// SPDX-License-Identifier: MIT
// 3D Model Builder UI.

"use strict";
// TOKEN, api(), banner(), $() and every() come from framework/ctrlx.js; UI (tables, edit fields, tree, search, ...)
// from framework/ui.js. The setpoint is written on Enter (STANDARD.md §6: direct write).

async function poll() {
  try {
    const s = await api("GET", "/state");
    $("counter").textContent = s.counter;
    $("uptime").textContent = s.uptime_s + " s";
    $("conn").textContent = s.connected ? "Data Layer connected" : "Data Layer offline";
    $("conn").className = "chip " + (s.connected ? "ok" : "bad");
  } catch (e) {
    $("conn").textContent = "App not reachable";
    $("conn").className = "chip bad";
  }
}

async function loadConfig() {
  const c = await api("GET", "/config");
  $("settings").replaceChildren(UI.settings([
    ["Setpoint", UI.field(c.setpoint, async (text) => {
      const v = Number(text);
      if (text.trim() === "" || !Number.isFinite(v)) throw new Error("a number is expected");
      const n = await api("PATCH", "/config", { setpoint: v });
      banner(`Setpoint ${n.setpoint} saved`, true);
    }, { hint: "Setpoint of the app" }), "Kept in the app data; also the Data Layer node model-builder/setpoint"],
  ]));
}

$("read").onclick = async () => {
  try {
    const r = await api("GET", "/node?path=" + encodeURIComponent($("path").value.trim()));
    $("result").textContent = JSON.stringify(r.value, null, 2);
    banner("");
  } catch (e) {
    $("result").textContent = "";
    banner(e.message);
  }
};

$("write").onclick = async () => {
  let value;
  try {
    value = JSON.parse($("value").value);
  } catch (e) {
    banner("The value must be JSON: true, 1.5, \"text\", [1, 2]");
    return;
  }
  try {
    const r = await api("PUT", "/node?path=" + encodeURIComponent($("path").value.trim()), { value });
    $("result").textContent = JSON.stringify(r.value, null, 2);
    banner("Written", true);
  } catch (e) {
    banner(e.message);
  }
};

loadConfig().catch((e) => banner(e.message));
every(1000, poll);
