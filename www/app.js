// SPDX-License-Identifier: MIT
// 3D Model Builder UI. TOKEN, api(), banner(), $() and every() come from framework/ctrlx.js; UI (tables, edit fields)
// from framework/ui.js. Every change is saved at once (mutate), the preview is built from the XML the server generates.

import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { createPreview } from "./preview.js";

const h = UI.h;
const enc = encodeURIComponent;
const MB = 1024 * 1024;
const WARN_BYTES = 30 * MB, MAX_BYTES = 100 * MB;

// ---------------------------------------------------------------- icons (24x24 paths, Material style)
const PATHS = {
  edit: "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
  copy: "M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z",
  move: "M20 6h-8l-2-2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2zm-8 11v-3H8v-2h4V9l4 4-4 4z",
  rotation: "M12 6v3l4-4-4-4v3a8 8 0 0 0-8 8c0 1.57.46 3.03 1.24 4.26L6.7 14.8A5.87 5.87 0 0 1 6 12a6 6 0 0 1 6-6zm6.76 1.74L17.3 9.2c.44.84.7 1.79.7 2.8a6 6 0 0 1-6 6v-3l-4 4 4 4v-3a8 8 0 0 0 8-8c0-1.57-.46-3.03-1.24-4.26z",
  translation: "M6.99 11 3 15l3.99 4v-3H14v-2H6.99v-3zM21 9l-3.99-4v3H10v2h7.01v3L21 9z",
  part: "M12 2 3 7v10l9 5 9-5V7l-9-5zm0 2.3L18.5 8 12 11.7 5.5 8 12 4.3zM5 9.7l6 3.4v6.6l-6-3.4V9.7zm8 10v-6.6l6-3.4v6.6l-6 3.4z",
  tool: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm8.94 3A8.994 8.994 0 0 0 13 3.06V1h-2v2.06A8.994 8.994 0 0 0 3.06 11H1v2h2.06A8.994 8.994 0 0 0 11 20.94V23h2v-2.06A8.994 8.994 0 0 0 20.94 13H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z",
  up: "M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z",
  down: "M20 12l-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8 8-8z",
  into: "M19 15l-6 6-1.42-1.42L15.17 16H4V4h2v10h9.17l-3.59-3.58L13 9l6 6z",
  out: "M11 9l1.42 1.42L8.83 14H18V4h2v12H8.83l3.59 3.58L11 21l-6-6 6-6z",
  check: "M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
  fit: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM5 15H3v4a2 2 0 0 0 2 2h4v-2H5v-4zM5 5h4V3H5a2 2 0 0 0-2 2v4h2V5zm14-2h-4v2h4v4h2V5a2 2 0 0 0-2-2zm0 16h-4v2h4a2 2 0 0 0 2-2v-4h-2v4z",
  kin: "M22 11V3h-7v3H9V3H2v8h7V8h2v10h4v3h7v-8h-7v3h-2V8h2v3h7zM7 9H4V5h3v4zm10 6h3v4h-3v-4zm0-10h3v4h-3V5z",
  add: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
  delete: "M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
  upload: "M5 20h14v-2H5v2zm0-10h4v6h6v-6h4l-7-7-7 7z",
  download: "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
  save: "M17 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7l-4-4zm-5 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm3-10H5V5h10v4z",
  eye: "M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17a5 5 0 1 1 0-10 5 5 0 0 1 0 10zm0-8a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  refresh: "M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z",
  close: "M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
  frame: "M3 21V3h2v16h16v2H3zm5-6V8l5 3.5L8 15zm6-2 5-3.5V17l-5-4z",
  reset: "M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62A7.95 7.95 0 0 1 12.5 10c3.54 0 6.55 2.31 7.6 5.5l2.37-.78A10.02 10.02 0 0 0 12.5 8z",
};
function ico(name) {
  return h("span", { class: "ui-icon", "aria-hidden": "true", html: `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="${PATHS[name] || ""}"/></svg>` });
}
function tool(icon, title, onclick, extra = {}) {
  return h("button", { class: "tool", title, "aria-label": title, onclick, ...extra }, ico(icon));
}
function wide(icon, label, title, onclick, extra = {}) {
  return h("button", { class: "wide-btn" + (extra.primary ? " primary" : ""), title, onclick, disabled: extra.disabled, id: extra.id }, ico(icon), label);
}

// ---------------------------------------------------------------- state
const S = {
  projects: [], generation: -1,
  project: null, selection: null,          // {kind: "node" | "mesh", id}
  values: {},                              // preview joint values (never saved)
  zone: null, sizes: {}, storage: null,
  axes: [], kins: [], motionError: "",
  unit: "mm", stamps: {}, cache: new Map(),
  info: null,
  vlist: { projects: [], error: "", loaded: false },       // the 3D viewer's projects
  view: null,                                               // the read-only view of a viewer project (see openView)
};
let preview = null;

const fmt = (n) => String(+Number(n).toFixed(4));
const vecText = (v) => (v || []).map(fmt).join(", ");
const fmtSize = (b) => (b >= MB ? (b / MB).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " kB");
const nowText = () => new Date().toLocaleTimeString();

function toNumber(text) {
  const v = Number(String(text).trim().replace(",", "."));
  if (String(text).trim() === "" || !Number.isFinite(v)) throw new Error("a number is expected");
  return v;
}
function toVec(text, n = 3) {
  const parts = String(text).split(/[\s,;]+/).filter(Boolean).map(Number);
  if (parts.length !== n || parts.some((v) => !Number.isFinite(v))) throw new Error(`${n} numbers are expected, separated by commas`);
  return parts;
}
const uid = () => "n" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

function* walk(nodes, parent = null) {
  for (const n of nodes || []) { yield [n, parent]; if (n.kind === "axis") yield* walk(n.children, n); }
}
function locate(tree, id) {
  const find = (list, parent) => {
    for (let i = 0; i < list.length; i++) {
      if (list[i].id === id) return { node: list[i], list, index: i, parent };
      if (list[i].kind === "axis") { const r = find(list[i].children || [], list[i]); if (r) return r; }
    }
    return null;
  };
  return find(tree, null);
}
const nodeById = (id) => S.project && locate(S.project.tree, id) && locate(S.project.tree, id).node;
const axisNodes = () => (S.project ? [...walk(S.project.tree)].map(([n]) => n).filter((n) => n.kind === "axis") : []);
function currentNode() {
  return S.selection && S.selection.kind === "node" && S.project ? nodeById(S.selection.id) : null;
}

// ---------------------------------------------------------------- saving
async function mutate(fn) {
  const draft = structuredClone(S.project);
  fn(draft);
  S.project = await api("PUT", `/projects/${enc(S.project.name)}`, draft);
  $("save-chip").textContent = "Saved " + nowText();
  $("save-chip").className = "chip ok";
  await refreshModel();
  renderAll();
}
async function guard(fn) {
  banner("");
  try { await fn(); } catch (e) { banner(e.message); renderAll(); }
}

async function fetchText(path) {
  const r = await api("GET", path, undefined, { raw: true });
  return r.text();
}

async function refreshModel() {
  if (!S.project) return;
  const name = enc(S.project.name);
  try {
    const [xml, zone] = await Promise.all([fetchText(`/projects/${name}/xml`), api("GET", `/projects/${name}/zone-check`)]);
    S.zone = zone;
    S.modelError = "";
    preview.setXml(xml).catch((e) => { S.modelError = e.message; banner(e.message); });
    syncPreview();
    preview.setValues(S.values);
  } catch (e) {
    S.zone = null;
    S.modelError = e.message;
    banner("The preview cannot be built: " + e.message);
  }
}

// ---------------------------------------------------------------- meshes for the preview
async function loadMesh(file) {
  if (S.view) {                     // a viewer project: the cache route matches names in any case
    const key = `view/${S.view.seq}/${file}`;
    if (!S.cache.has(key)) {
      S.cache.set(key, (async () => {
        const r = await fetch(`${API}/viewer/cache/${enc(file)}`, { headers: { Authorization: "Bearer " + TOKEN } });
        if (!r.ok) throw new Error("HTTP " + r.status + " (the file is not in the project)");
        return new STLLoader().parse(await r.arrayBuffer());
      })());
    }
    return S.cache.get(key);
  }
  const name = S.project.name;
  const key = `${name}/${file}/${S.stamps[file] || 0}`;
  if (!S.cache.has(key)) {
    S.cache.set(key, (async () => {
      const r = await fetch(`${API}/projects/${enc(name)}/meshes/${enc(file)}`, { headers: { Authorization: "Bearer " + TOKEN } });
      if (!r.ok) throw new Error("HTTP " + r.status);
      return new STLLoader().parse(await r.arrayBuffer());
    })());
  }
  return S.cache.get(key);
}

// ---------------------------------------------------------------- projects
async function loadList(force) {
  const r = await api("GET", "/projects");
  const same = JSON.stringify(r.projects) === JSON.stringify(S.projects);
  const regen = r.generation !== S.generation;
  S.projects = r.projects;
  S.generation = r.generation;
  if (S.project && !S.projects.some((p) => p.name === S.project.name)) { closeProject(); return renderAll(); }
  if (S.project && regen && !force && S.openedGeneration !== undefined && S.openedGeneration !== r.generation) {
    // a configuration was loaded: the files may have changed under us
    await openProject(S.project.name, true);
    return;
  }
  if ((!same || force) && (force || !UI.busy(document.body))) renderAll();
}
function closeProject(keepLast) {
  S.project = null; S.selection = null; S.zone = null; S.sizes = {}; S.values = {}; S.cache.clear();
  preview.reset();
  if (!keepLast) localSet("last", "");
}
async function openProject(name, keepSelection) {
  const p = await api("GET", `/projects/${enc(name)}`);
  if (S.view) { leaveView(); keepSelection = false; }
  if (!keepSelection) { S.selection = null; S.values = {}; S.cache.clear(); preview.reset(); }
  S.project = p;
  S.openedGeneration = S.generation;
  localSet("last", name);
  S.sizes = (await api("GET", `/projects/${enc(name)}/meshes`)).sizes;
  await refreshModel();
  renderAll();
}
function localSet(k, v) { try { localStorage.setItem("model-builder." + k, v); } catch (e) { /* not remembered */ } }
function localGet(k) { try { return localStorage.getItem("model-builder." + k) || ""; } catch (e) { return ""; } }

function dialog(title, body, ok, valid) {
  return new Promise((resolve) => {
    const d = h("dialog", { title });
    const okb = h("button", { class: "primary", title: ok === "Delete" ? "Delete it" : ok }, ok);
    const cancel = h("button", { title: "Close without changing anything" }, "Cancel");
    d.append(h("h3", {}, title), body, h("div", { class: "actions" }, okb, cancel));
    let result = false;
    okb.onclick = () => {
      const problem = valid ? valid() : "";
      if (problem) { banner(problem); return; }
      result = true; d.close();
    };
    cancel.onclick = () => d.close();
    d.addEventListener("close", () => { d.remove(); resolve(result); });
    document.body.appendChild(d);
    d.showModal();
    const first = d.querySelector("input[type=text]");
    if (first) first.focus();
  });
}
function storageTable(initial) {
  let value = initial || "config";
  const opt = (id, title, backup, note) => {
    const r = h("input", { type: "radio", name: "loc", value: id, checked: id === value, title: `Store the project in: ${title}`, onchange: () => { value = id; } });
    return [r, title, backup, note];
  };
  const rows = [
    opt("config", "Active configuration", "yes", "Saved with ctrlX configurations and backups, so it survives a restore. Large models make every backup larger."),
    opt("common", "This app only", "no", "Stays on this device in the app's own folder. It is not in a configuration or a backup and is gone after a restore on another device."),
  ];
  const t = UI.table([
    { label: "Use", hint: "Pick where the project is kept", get: (r) => r[0] },
    { label: "Location", hint: "Where the files are kept", get: (r) => r[1] },
    { label: "In backups", hint: "Whether ctrlX configurations and backups contain the project", get: (r) => r[2] },
    { label: "Note", hint: "What the choice means", get: (r) => r[3], cls: "ui-note ui-wrap" },
  ], rows, { cls: "storage-table" });
  return { el: t, get value() { return value; } };
}
function nameInput(initial) {
  return h("input", { type: "text", value: initial || "", maxlength: 64, title: "Project name: letters, digits, spaces, _ - . (1 to 64), unique in both locations", spellcheck: "false" });
}

async function newProject() {
  const name = nameInput(""), st = storageTable("config");
  const body = h("div", {}, UI.settings([["Name", name, "Becomes the project name in the 3D viewer too (letters, digits, space, _ - .)"]]), h("p", { class: "hint" }, "Storage"), st.el);
  if (await dialog("New project", body, "Create", () => (name.value.trim() ? "" : "Enter a project name"))) {
    await guard(async () => {
      const p = await api("POST", "/projects", { name: name.value.trim(), location: st.value });
      await loadList(true);
      await openProject(p.name);
    });
  }
}
async function renameProject() {
  const name = nameInput(S.project.name);
  if (await dialog("Rename project", UI.settings([["New name", name, "Does not rename a project that is already in the 3D viewer"]]), "Rename", () => (name.value.trim() ? "" : "Enter a name"))) {
    await guard(async () => { const p = await api("POST", `/projects/${enc(S.project.name)}/rename`, { name: name.value.trim() }); await loadList(true); await openProject(p.name, true); });
  }
}
async function duplicateProject() {
  const name = nameInput(S.project.name + "_copy"), st = storageTable(S.project.location);
  const body = h("div", {}, UI.settings([["Name of the copy", name, "A new project with the same meshes and tree"]]), h("p", { class: "hint" }, "Storage of the copy"), st.el);
  if (await dialog("Duplicate project", body, "Duplicate", () => (name.value.trim() ? "" : "Enter a name"))) {
    await guard(async () => {
      const p = await api("POST", `/projects/${enc(S.project.name)}/duplicate`, { name: name.value.trim(), location: st.value });
      await loadList(true); await openProject(p.name);
    });
  }
}
async function moveProject() {
  const other = S.project.location === "config" ? "common" : "config";
  const st = storageTable(other);
  if (await dialog(`Move ${S.project.name}`, st.el, "Move")) {
    await guard(async () => { await api("POST", `/projects/${enc(S.project.name)}/move`, { location: st.value }); await loadList(true); await openProject(S.project.name, true); });
  }
}
async function deleteProject() {
  if (!confirm(`Delete the project ${S.project.name} and its meshes?\n\nThis cannot be undone. A copy in the 3D viewer is not touched.`)) return;
  await guard(async () => { const n = S.project.name; await api("DELETE", `/projects/${enc(n)}`); closeProject(); await loadList(true); });
}

// ---------------------------------------------------------------- meshes
async function uploadMesh(file) {
  if (!/\.stl$/i.test(file.name)) { banner("Only STL files are supported (binary or ASCII)"); return; }
  if (file.size > MAX_BYTES) { banner(`${file.name} is ${fmtSize(file.size)}; the limit is 100 MB`); return; }
  if (file.size > WARN_BYTES && !confirm(`${file.name} is ${fmtSize(file.size)}.\n\nLarge meshes load slowly in the browser and in the 3D viewer. Upload it anyway?`)) return;
  await guard(async () => {
    banner(`Uploading ${file.name} (${fmtSize(file.size)}) ...`, true);
    const r = await api("PUT", `/projects/${enc(S.project.name)}/meshes/${enc(file.name)}?unit=${S.unit}`, file, { raw: true });
    S.project = await r.json();
    S.stamps[file.name] = (S.stamps[file.name] || 0) + 1;
    S.sizes = (await api("GET", `/projects/${enc(S.project.name)}/meshes`)).sizes;
    banner(`${file.name} uploaded`, true);
    await refreshModel();
    renderAll();
    loadList(true);
  });
}
async function deleteMesh(mid) {
  const m = S.project.meshes[mid];
  if (!confirm(`Delete the mesh ${m.file}?`)) return;
  await guard(async () => {
    S.project = await api("DELETE", `/projects/${enc(S.project.name)}/meshes/${enc(m.file)}`);
    S.sizes = (await api("GET", `/projects/${enc(S.project.name)}/meshes`)).sizes;
    if (S.selection && S.selection.kind === "mesh" && S.selection.id === mid) S.selection = null;
    await refreshModel(); renderAll(); loadList(true);
  });
}

// ---------------------------------------------------------------- tree operations
function insertionTarget(draft) {
  const sel = S.selection && S.selection.kind === "node" ? locate(draft.tree, S.selection.id) : null;
  if (sel && sel.node.kind === "axis") return sel.node.children;
  if (sel && sel.parent) return sel.parent.children;
  return draft.tree;
}
function uniqueName(draft, base) {
  const names = new Set([...walk(draft.tree)].map(([n]) => n.name));
  let i = 1;
  while (names.has(`${base}${i}`)) i++;
  return `${base}${i}`;
}
async function addNode(make) {
  const id = uid();
  await guard(async () => {
    await mutate((d) => { const list = insertionTarget(d); const n = make(d); n.id = id; list.push(n); });
    S.selection = { kind: "node", id };
    renderAll(); syncPreview();
  });
}
const addAxis = (type) => addNode((d) => ({
  kind: "axis", name: uniqueName(d, type === "rotation" ? "Rot" : "Lin"), type, direction: type === "rotation" ? [0, 0, 1] : [1, 0, 0],
  pivot: [0, 0, 0], range: type === "rotation" ? [-360, 360] : [-1000, 1000], initial: 0, offset: 0, invert: false, binding: "", children: [] }));
function addTool() {
  return addNode((d) => ({ kind: "tool", name: uniqueName(d, "Tool"), position: [0, 0, 0] }));
}
function addPart() {
  const ids = Object.keys(S.project.meshes);
  if (!ids.length) { banner("Upload an STL file first (Meshes)"); return; }
  const mid = S.selection && S.selection.kind === "mesh" ? S.selection.id : ids.length === 1 ? ids[0] : null;
  if (!mid) { banner("Select a mesh in the Meshes table first, then add the part"); return; }
  return addPartOf(mid);
}
function addPartOf(mid) {
  return addNode((d) => ({ kind: "part", name: uniqueName(d, mid.replace(/[^A-Za-z0-9_-]/g, "_") + "_"), mesh: mid, colour: [0.6, 0.6, 0.6] }));
}
async function deleteNode() {
  const n = currentNode();
  if (!n) { banner("Select a node in the tree first"); return; }
  const kids = n.kind === "axis" ? [...walk(n.children)].length : 0;
  if (kids && !confirm(`Delete ${n.name} and the ${kids} nodes under it?`)) return;
  await guard(async () => { await mutate((d) => { const r = locate(d.tree, n.id); r.list.splice(r.index, 1); }); S.selection = null; renderAll(); syncPreview(); });
}
async function moveNode(how) {
  const n = currentNode();
  if (!n) { banner("Select a node in the tree first"); return; }
  await guard(async () => {
    await mutate((d) => {
      const r = locate(d.tree, n.id);
      const { list, index } = r;
      if (how === "up" && index > 0) [list[index - 1], list[index]] = [list[index], list[index - 1]];
      else if (how === "down" && index < list.length - 1) [list[index + 1], list[index]] = [list[index], list[index + 1]];
      else if (how === "into") {
        const above = [...list.slice(0, index)].reverse().find((x) => x.kind === "axis");
        if (!above) throw new Error("There is no axis above this node to move it into");
        list.splice(index, 1);
        above.children.push(r.node);
      } else if (how === "out") {
        if (!r.parent) throw new Error("The node is at the top level already");
        const up = locate(d.tree, r.parent.id);
        list.splice(index, 1);
        up.list.splice(up.index + 1, 0, r.node);
      }
    });
  });
}
async function dropNode(dragId, targetId, mode) {
  await guard(async () => {
    await mutate((d) => {
      const src = locate(d.tree, dragId);
      if (!src) return;
      if (targetId && [...walk([src.node])].some(([x]) => x.id === targetId)) throw new Error("A node cannot be moved into itself");
      src.list.splice(src.index, 1);
      if (!targetId) { d.tree.push(src.node); return; }
      const t = locate(d.tree, targetId);
      if (mode === "into" && t.node.kind === "axis") t.node.children.push(src.node);
      else t.list.splice(t.list.indexOf(t.node), 0, src.node);
    });
  });
}
async function startFromKinematic(name) {
  if (!name) { banner("Pick a kinematic first"); return; }
  if (S.project.tree.length && !confirm("Replace the tree with the axes of the kinematic?\n\nThe parts and axes you made are removed from the tree (the meshes stay).")) return;
  await guard(async () => {
    const r = await api("POST", `/projects/${enc(S.project.name)}/from-kinematic`, { kinematic: name });
    await mutate((d) => { d.tree = r.tree; d.kinematic = r.kinematic; });
    S.selection = null;
    renderAll();
  });
}

// ---------------------------------------------------------------- the left column
function projectsCard() {
  const has = !!S.project;
  const table = UI.table([
    { label: "Name", hint: "Project name; click to open it", get: (p) => p.name },
    { label: "Where", hint: "Where the project is kept: the active configuration (in backups) or this app only (not in backups)", get: (p) => h("span", { class: "chip loc-" + p.location, title: p.location === "config" ? "In the active configuration: saved with ctrlX configurations and backups" : "App only: not part of a configuration or backup" }, p.location === "config" ? "Config" : "App only") },
    { label: "Size", hint: "Disk space of the project's files", get: (p) => fmtSize(p.size), num: true },
    { label: "Viewer", hint: "When the project was last uploaded to the 3D viewer", get: (p) => (p.uploaded_at ? p.uploaded_at.slice(0, 10) : "-") },
  ], S.projects, { key: (p) => p.name, empty: "No projects yet: create one with the + button", id: "projects-table", cls: "projects-table" });
  table.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-key]");
    if (tr && (S.view || !S.project || S.project.name !== tr.dataset.key)) guard(() => openProject(tr.dataset.key));
  });
  table.querySelectorAll("tr[data-key]").forEach((tr) => { if (S.project && tr.dataset.key === S.project.name) tr.classList.add("cur"); });
  return h("section", { class: "card", id: "projects-card" },
    h("h2", {}, "Projects"),
    h("div", { class: "tools", id: "project-tools" },
      tool("add", S.view ? "New project (not while a viewer project is open read-only)" : "New project: choose its name and where it is stored", newProject, { id: "new-project", disabled: !!S.view }),
      tool("edit", "Rename the open project", renameProject, { disabled: !has }),
      tool("copy", "Duplicate the open project", duplicateProject, { disabled: !has }),
      tool("move", "Move the open project to the other storage location", moveProject, { disabled: !has }),
      tool("delete", "Delete the open project", deleteProject, { disabled: !has })),
    table);
}

function meshesCard() {
  const p = S.project;
  const used = (mid) => [...walk(p.tree)].filter(([n]) => n.kind === "part" && n.mesh === mid).length;
  const input = $("file-input");
  const unit = h("select", { title: "Unit the next STL file was exported in: it is scaled to mm", onchange: (e) => { S.unit = e.target.value; } },
    ["mm", "m", "inch"].map((u) => h("option", { value: u, selected: u === S.unit }, u)));
  const rows = Object.entries(p.meshes).map(([id, m]) => ({ id, ...m }));
  const table = UI.table([
    { label: "Mesh", hint: "Mesh file name; click for its unit and placement", get: (m) => m.file },
    { label: "Unit", hint: "Unit the file was exported in", get: (m) => m.unit },
    { label: "Size", hint: "File size", get: (m) => fmtSize(S.sizes[m.file] || 0), num: true },
    { label: "Used", hint: "Number of parts that use this mesh", get: (m) => used(m.id), num: true },
    { label: "", hint: "Actions", get: (m) => h("span", { class: "tools", style: "margin:0;flex-wrap:nowrap" },
      tool("add", "Add a part with this mesh to the tree", (ev) => { ev.stopPropagation(); addPartOf(m.id); }, { class: "tool mesh-add" }),
      tool("delete", "Delete this mesh file (not possible while parts use it)", (ev) => { ev.stopPropagation(); deleteMesh(m.id); })) },
  ], rows, { key: (m) => m.id, empty: "No meshes yet: upload an STL file", id: "meshes-table", cls: "projects-table" });
  table.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-key]");
    if (!tr) return;
    S.selection = { kind: "mesh", id: tr.dataset.key };
    renderAll(); syncPreview();
  });
  table.querySelectorAll("tr[data-key]").forEach((tr) => { if (S.selection && S.selection.kind === "mesh" && S.selection.id === tr.dataset.key) tr.classList.add("cur"); });
  return h("section", { class: "card", id: "meshes-card" },
    h("h2", {}, "Meshes"),
    h("div", { class: "tools" }, h("span", { class: "lbl" }, "File unit"), unit,
      tool("upload", "Upload an STL file (binary or ASCII, up to 100 MB; a warning above 30 MB)", () => { input.value = ""; input.click(); }, { id: "upload-mesh" })),
    table);
}

function treeCard() {
  const p = S.project;
  const kinSel = h("select", { id: "kin-select", title: "A kinematic from ctrlX MOTION: one axis per kinematic axis, bound to it" },
    h("option", { value: "" }, S.kins.length ? "Pick a kinematic ..." : (S.motionError || "No kinematics found")),
    S.kins.map((k) => h("option", { value: k.name, selected: p.kinematic && p.kinematic.name === k.name }, `${k.name} (${k.type || "?"})`)));
  const box = h("div", { class: "tree-box", id: "tree-box", title: "The model tree: an axis carries everything under it. Drag a node onto an axis to move it there." });
  const draw = (nodes) => h("ul", {}, nodes.map((n) => {
    const sel = S.selection && S.selection.kind === "node" && S.selection.id === n.id;
    const sub = n.kind === "axis" ? (n.binding || "not bound") : n.kind === "part" ? (p.meshes[n.mesh] ? p.meshes[n.mesh].file : "missing mesh") : "TCP";
    const hint = n.kind === "axis" ? `${n.type} axis ${n.name}, bound to ${n.binding || "no MOTION axis"}` : n.kind === "part" ? `Part ${n.name} (mesh ${sub})` : `Tool marker ${n.name}`;
    const row = h("div", { class: "ui-node" + (sel ? " ui-sel" : ""), "data-id": n.id, title: hint, draggable: "true", style: "padding-left:8px" },
      h("span", { class: "kind", title: n.kind }, ico(n.kind === "axis" ? n.type : n.kind)),
      h("span", { class: "ui-label" }, n.name), h("span", { class: "ui-sub" }, sub));
    row.addEventListener("click", () => { S.selection = { kind: "node", id: n.id }; renderAll(); syncPreview(); });
    row.addEventListener("dragstart", (ev) => { ev.dataTransfer.setData("text/plain", n.id); ev.dataTransfer.effectAllowed = "move"; });
    row.addEventListener("dragover", (ev) => { ev.preventDefault(); const into = n.kind === "axis"; row.classList.toggle("drop-into", into); row.classList.toggle("drop-before", !into); });
    row.addEventListener("dragleave", () => row.classList.remove("drop-into", "drop-before"));
    row.addEventListener("drop", (ev) => { ev.preventDefault(); ev.stopPropagation(); row.classList.remove("drop-into", "drop-before"); const id = ev.dataTransfer.getData("text/plain"); if (id && id !== n.id) dropNode(id, n.id, n.kind === "axis" ? "into" : "before"); });
    const li = h("li", {}, row);
    if (n.kind === "axis" && n.children && n.children.length) {
      const ul = draw(n.children);
      ul.style.paddingLeft = "16px";
      li.appendChild(ul);
    }
    return li;
  }));
  if (p.tree.length) box.appendChild(draw(p.tree)); else box.appendChild(h("div", { class: "tree-empty" }, "The tree is empty: add an axis, a part or a tool marker, or start from a kinematic"));
  const root = h("div", { class: "drop-root", title: "Drop a node here to move it to the top level" }, "Drop here for the top level");
  root.addEventListener("dragover", (ev) => { ev.preventDefault(); root.classList.add("drop-into"); });
  root.addEventListener("dragleave", () => root.classList.remove("drop-into"));
  root.addEventListener("drop", (ev) => { ev.preventDefault(); root.classList.remove("drop-into"); const id = ev.dataTransfer.getData("text/plain"); if (id) dropNode(id, null); });
  box.appendChild(root);
  return h("section", { class: "card", id: "tree-card" },
    h("h2", {}, "Tree"),
    h("div", { class: "tools", id: "tree-tools" },
      tool("rotation", "Add a rotation axis (under the selected axis, else at the top level)", () => addAxis("rotation"), { id: "add-rot" }),
      tool("translation", "Add a translation axis (under the selected axis, else at the top level)", () => addAxis("translation"), { id: "add-lin" }),
      tool("part", "Add a part from the selected mesh (or the only mesh)", addPart, { id: "add-part" }),
      tool("tool", "Add a tool marker (the tool centre point, TCP)", addTool, { id: "add-tool" }),
      h("span", { class: "sep" }),
      tool("up", "Move the selected node up among its siblings", () => moveNode("up")),
      tool("down", "Move the selected node down among its siblings", () => moveNode("down")),
      tool("into", "Move the selected node into the axis above it", () => moveNode("into")),
      tool("out", "Move the selected node out of its axis, behind it", () => moveNode("out")),
      h("span", { class: "sep" }),
      tool("delete", "Delete the selected node (and the nodes under it)", deleteNode, { id: "delete-node" })),
    box,
    h("div", { class: "tools", style: "margin-top:8px" }, h("span", { class: "lbl" }, "Start from"), kinSel,
      tool("kin", "Build the tree from the selected kinematic (replaces the tree)", () => startFromKinematic(kinSel.value), { id: "from-kin" })));
}

// ---------------------------------------------------------------- the right column
function bindingSelect(n) {
  const names = S.axes.map((a) => a.name);
  const sel = h("select", { class: "ui-edit", id: "binding-select", title: "The ctrlX MOTION axis this model axis follows (read from motion/axs with your token)" },
    h("option", { value: "" }, "(not bound)"),
    (n.binding && !names.includes(n.binding) ? [n.binding] : []).concat(names).map((a) => h("option", { value: a }, a + (names.includes(a) ? "" : " (not found in MOTION)"))));
  sel.value = n.binding || "";
  sel.addEventListener("change", () => guard(() => mutate((d) => { locate(d.tree, n.id).node.binding = sel.value; })));
  return sel;
}
function dirName(d) {
  const t = { "1,0,0": "+X", "-1,0,0": "-X", "0,1,0": "+Y", "0,-1,0": "-Y", "0,0,1": "+Z", "0,0,-1": "-Z" };
  return t[d.map((v) => +v.toFixed(9)).join(",")] || "custom";
}
const PRESETS = { "+X": [1, 0, 0], "-X": [-1, 0, 0], "+Y": [0, 1, 0], "-Y": [0, -1, 0], "+Z": [0, 0, 1], "-Z": [0, 0, -1] };

function nodeField(id, value, apply, opts) {
  return UI.field(value, (text) => mutate((d) => apply(locate(d.tree, id).node, text, d)), opts);
}

function axisRows(n) {
  const id = n.id;
  const moAxis = S.axes.find((a) => a.name === n.binding);
  const typeMismatch = moAxis && moAxis.type && moAxis.type !== n.type ? ` The MOTION axis is ${moAxis.type}, this model axis is ${n.type}.` : "";
  const unit = n.type === "rotation" ? "deg" : "mm";
  const rows = [
    ["Name", nodeField(id, n.name, (x, t) => { if (!t.trim()) throw new Error("a name is expected"); x.name = t.trim(); }, { hint: "Model axis name" }), "Axis name in the XML; must be unique in the project"],
    ["Type", nodeField(id, n.type, (x, t) => { x.type = t; }, { choices: ["rotation", "translation"], hint: "Axis type" }), "A rotation turns about the pivot, a translation slides along the direction"],
    ["Direction preset", nodeField(id, dirName(n.direction), (x, t) => { if (t !== "custom") x.direction = PRESETS[t].slice(); }, { choices: ["+X", "-X", "+Y", "-Y", "+Z", "-Z", "custom"], hint: "Axis direction preset" }), "Direction in the assembly frame at the zero pose"],
    ["Direction (x, y, z)", nodeField(id, n.direction, (x, t) => { x.direction = toVec(t); }, { hint: "Direction vector" }), "Any vector (not 0, 0, 0); the viewer normalises it"],
  ];
  if (n.type === "rotation") rows.push(["Pivot (x, y, z) mm", nodeField(id, n.pivot, (x, t) => { x.pivot = toVec(t); }, { hint: "A point on the rotation axis, in mm" }), "A point on the axis in the assembly frame at the zero pose (written in the frame the axis element is in)"]);
  rows.push(
    ["Minimum", nodeField(id, n.range[0], (x, t) => { x.range[0] = toNumber(t); }, { hint: `Lowest value in ${unit} (MOTION axis units)` }), `${unit}, in the MOTION axis' units`],
    ["Maximum", nodeField(id, n.range[1], (x, t) => { x.range[1] = toNumber(t); }, { hint: `Highest value in ${unit} (MOTION axis units)` }), `${unit}, in the MOTION axis' units`],
    ["Initial value", nodeField(id, n.initial, (x, t) => { x.initial = toNumber(t); }, { hint: "Value shown before the axis sends one" }), `${unit}, in the MOTION axis' units`],
    ["MOTION axis", bindingSelect(n), "The viewer sets this model axis from the MOTION axis (expression: value)." + typeMismatch],
    ["Offset", nodeField(id, n.offset, (x, t) => { x.offset = toNumber(t); }, { hint: `Offset in ${unit}` }), `${unit}. Model value = offset + (±1) × MOTION value; built into the XML, never into the expression`],
    ["Invert", nodeField(id, !!n.invert, (x, t) => { x.invert = t === "true"; }, { hint: "Invert the direction" }), "The model moves the other way: the direction is negated in the XML"]);
  if (n.mcs_origin) rows.push(["Zone frame shift (x, y, z)", nodeField(id, n.mcs_origin, (x, t) => { const v = toVec(t); x.mcs_origin = v.some(Boolean) ? v : null; }, { hint: "MCS_Origin transform around this axis; 0, 0, 0 removes it" }), "From the zone check fix: an MCS_Origin parent that moves the zone frame; the geometry stays where it was"]);
  return rows;
}

function hexOf(c) { return "#" + c.map((v) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, "0")).join(""); }
function colourOf(hex) { return [1, 3, 5].map((i) => +(parseInt(hex.slice(i, i + 2), 16) / 255).toFixed(7)); }

function propertiesCard() {
  const p = S.project;
  const n = currentNode();
  let title = "Project", rows;
  if (n && n.kind === "axis") { title = `${n.type === "rotation" ? "Rotation" : "Translation"} axis ${n.name}`; rows = axisRows(n); }
  else if (n && n.kind === "part") {
    title = `Part ${n.name}`;
    const colour = h("input", { type: "color", id: "part-colour", value: hexOf(n.colour), title: "Colour of the part in the viewer" });
    colour.addEventListener("change", () => guard(() => mutate((d) => { locate(d.tree, n.id).node.colour = colourOf(colour.value); })));
    rows = [
      ["Name", nodeField(n.id, n.name, (x, t) => { if (!t.trim()) throw new Error("a name is expected"); x.name = t.trim(); }, { hint: "Part name" }), "Geometry name in the XML"],
      ["Mesh", nodeField(n.id, n.mesh, (x, t) => { x.mesh = t; }, { choices: Object.keys(p.meshes), hint: "Mesh of the part" }), "An uploaded STL; its placement is set under Meshes"],
      ["Colour", colour, "Colour in the viewer (the preview uses it too)"],
    ];
  } else if (n && n.kind === "tool") {
    title = `Tool marker ${n.name}`;
    rows = [
      ["Name", nodeField(n.id, n.name, (x, t) => { if (!t.trim()) throw new Error("a name is expected"); x.name = t.trim(); }, { hint: "Tool marker name" }), "Geometry name in the XML"],
      ["Position (x, y, z) mm", nodeField(n.id, n.position, (x, t) => { x.position = toVec(t); }, { hint: "Tool centre point in mm" }), "Where the TCP is at the zero pose, in the assembly frame"],
    ];
  } else if (S.selection && S.selection.kind === "mesh" && p.meshes[S.selection.id]) {
    const mid = S.selection.id, m = p.meshes[mid];
    title = `Mesh ${m.file}`;
    const set = (fn) => (text) => mutate((d) => fn(d.meshes[mid], text));
    rows = [
      ["File", UI.field(m.file, () => {}, { readonly: true, hint: "File name" }), "Stored in the project's meshes folder"],
      ["Unit", UI.field(m.unit, set((x, t) => { x.unit = t; }), { choices: ["mm", "m", "inch"], hint: "Unit the file was exported in" }), "Scaled to mm in the model"],
      ["Position (x, y, z) mm", UI.field(m.placement.position, set((x, t) => { x.placement.position = toVec(t); }), { hint: "Placement of the mesh in the assembly frame, mm" }), "Only for files not exported in the common assembly frame"],
      ["Rotation (rx, ry, rz) deg", UI.field(m.placement.rotation, set((x, t) => { x.placement.rotation = toVec(t); }), { hint: "Placement rotation in degrees: Rz × Ry × Rx" }), "Applied before the position"],
      ["Size", UI.field(fmtSize(S.sizes[m.file] || 0), () => {}, { readonly: true, hint: "File size" }), ""],
    ];
  } else {
    const k = p.kinematic;
    rows = [
      ["Name", UI.field(p.name, () => {}, { readonly: true, hint: "Project name" }), "Rename it with the pencil button under Projects"],
      ["Stored in", UI.field(p.location === "config" ? "Active configuration (in backups)" : "This app only (not in backups)", () => {}, { readonly: true, hint: "Storage location" }), "Move it with the folder button under Projects"],
      ["Kinematic", UI.field(k ? `${k.name} (${k.type || "?"})` : "none", () => {}, { readonly: true, hint: "Kinematic the tree was started from" }), "Set by Start from kinematic"],
      ["Uploaded to viewer", UI.field((p.extra && p.extra.uploaded_at) || "never", () => {}, { readonly: true, hint: "Last upload to the 3D viewer" }), ""],
    ];
  }
  return h("section", { class: "card", id: "props-card" }, h("h2", {}, title), UI.settings(rows));
}

function jointsCard() {
  const axes = axisNodes();
  const rows = axes.map((n) => {
    const lo = n.range[0], hi = n.range[1];
    const span = hi > lo ? hi - lo : 1000;
    const v = S.values[n.name] ?? 0;
    const num = h("input", { type: "number", class: "joint-num", value: v, step: "any", title: `${n.name} value for the preview (${n.type === "rotation" ? "deg" : "mm"}); only moves the preview` });
    const rng = h("input", { type: "range", class: "joint-range", min: hi > lo ? lo : -1000, max: hi > lo ? hi : 1000, step: span / 400, value: v, title: `Drag to move ${n.name} in the preview` });
    const set = (val) => { S.values[n.name] = val; preview.setValue(n.name, val); };
    rng.addEventListener("input", () => { num.value = fmt(rng.value); set(+rng.value); });
    num.addEventListener("input", () => { if (num.value !== "" && Number.isFinite(+num.value)) { rng.value = num.value; set(+num.value); } });
    return { n, num, rng };
  });
  const t = UI.table([
    { label: "Axis", hint: "Model axis; click to select it", get: (r) => r.n.name },
    { label: "Slider", hint: "Moves the axis in the preview only", get: (r) => r.rng },
    { label: "Value", hint: "Axis value in the preview, deg or mm", get: (r) => r.num },
  ], rows, { key: (r) => r.n.id, empty: "No axes yet", cls: "joint-table", id: "joints-table" });
  t.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-key]");
    if (tr && !ev.target.closest("input")) { S.selection = { kind: "node", id: tr.dataset.key }; renderAll(); syncPreview(); }
  });
  t.querySelectorAll("tr[data-key]").forEach((tr) => { if (S.selection && S.selection.id === tr.dataset.key) tr.classList.add("cur"); });
  return h("section", { class: "card", id: "joints-card" },
    h("h2", {}, h("span", { class: "grow" }, "Joints (preview only)"),
      tool("reset", "Set all joints to 0 in the preview", () => { S.values = {}; preview.setValues(Object.fromEntries(axes.map((n) => [n.name, 0]))); renderAll(); }, { id: "zero-joints" })),
    t);
}

function zoneCard() {
  const z = S.zone;
  let body;
  if (!z) body = h("p", { class: "hint" }, S.modelError ? "The zone check needs a valid model: " + S.modelError : "No result yet.");
  else if (!z.checked) body = h("p", { class: "hint", id: "zone-note" }, z.note);
  else {
    body = UI.table([
      { label: "Check", hint: "What is checked", get: (r) => r.name },
      { label: "Result", hint: "OK or a warning", get: (r) => h("span", { class: "chip res " + (r.ok ? "ok" : "warn"), title: r.ok ? "Passed" : "Needs attention" }, r.ok ? "OK" : "Warning") },
      { label: "Note", hint: "Values and what they mean", get: (r) => h("span", {}, r.note, h("br"), h("span", { class: "dim" }, r.value)), cls: "ui-wrap ui-note" },
    ], z.rows, { cls: "zone-table", id: "zone-table" });
  }
  const canFix = z && z.checked && !z.ok && z.shift && z.rows.length && !z.rows[0].ok && z.rows[0].name === "Origin = tool point";
  return h("section", { class: "card", id: "zone-card" },
    h("h2", {}, h("span", { class: "grow" }, "Zone check")), body,
    canFix ? h("div", { class: "zone-fix" }, wide("check", "Fix origin", "Insert an MCS_Origin transform that moves the zone frame's origin to the tool point; the geometry stays where it is", () => guard(async () => {
      const r = await api("POST", `/projects/${enc(S.project.name)}/zone-fix`);
      S.project = r.project; await refreshModel(); renderAll(); banner("MCS_Origin inserted; the geometry did not move", true);
    }), { id: "zone-fix" })) : null);
}

// ---------------------------------------------------------------- toolbar, chips, assembly
function renderToolbar() {
  const has = !!S.project;
  $("toolbar").replaceChildren(
    wide("save", "Save", "Changes are saved as soon as they are made; this saves again and rebuilds the preview", () => guard(() => mutate(() => {})), { disabled: !has, id: "save" }),
    wide("download", "Download zip", "Download the viewer package (Model.zip with the XML and STLs, and the axis binding JSON)", () => guard(downloadZip), { disabled: !has, id: "download-zip" }),
    wide("upload", "Upload to viewer", "Send the model and its axis bindings to the ctrlX 3D viewer", () => guard(uploadToViewer), { disabled: !has, primary: true, id: "upload-viewer" }));
}
async function downloadZip() {
  const r = await api("GET", `/projects/${enc(S.project.name)}/package`, undefined, { raw: true });
  const url = URL.createObjectURL(await r.blob());
  const a = h("a", { href: url, download: S.project.name + ".zip" });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
async function uploadToViewer() {
  const name = enc(S.project.name);
  let r;
  try {
    r = await api("POST", `/projects/${name}/upload-to-viewer`, {});
  } catch (e) {
    if (e.code !== "EXISTS") throw e;
    if (!confirm(`${e.message}\n\nReplace the viewer's project ${S.project.name}?`)) return;
    r = await api("POST", `/projects/${name}/upload-to-viewer?replace=1`, {});
  }
  S.project = await api("GET", `/projects/${name}`);
  banner(`Uploaded to the 3D viewer: ${r.files} files${r.replaced ? " (replaced)" : ""}, ${r.bound_axes} axes bound`, true);
  loadList(true);
}

function renderChips() {
  $("project-chip").textContent = S.view ? `Viewing ${S.view.name} (read only)` : S.project ? `${S.project.name} (${S.project.location === "config" ? "in backups" : "not in backups"})` : "No project open";
  if (S.view) { $("save-chip").textContent = "Read only"; $("save-chip").className = "chip"; $("save-chip").title = "A viewer project is only read: nothing is saved or written"; }
  else if ($("save-chip").textContent === "Read only") { $("save-chip").textContent = "-"; $("save-chip").className = "chip"; $("save-chip").title = "Changes are saved as soon as they are made"; }
  const z = S.view ? S.view.zone : S.zone, chip = $("zone-chip");
  if (!(S.project || S.view) || !z) { chip.textContent = "Zone: -"; chip.className = "chip"; chip.title = "Result of the zone check for a Cartesian kinematic"; return; }
  if (!z.checked) { chip.textContent = "Zone: not checked"; chip.className = "chip"; chip.title = z.note; return; }
  chip.textContent = z.ok ? "Zone: OK" : "Zone: warning";
  chip.className = "chip " + (z.ok ? "ok" : "warn");
  chip.title = z.ok ? "The MCS zone frame of the 3D viewer matches the kinematic" : "The MCS zones would be drawn in the wrong place: see Zone check";
}

function renderStageBar() {
  const i = S.info;
  const text = !(S.project || S.view) ? "Open or create a project, or view one from the 3D viewer" : i ? `${i.axes} axes, ${i.parts} parts${i.loading ? " (loading ...)" : ""}, ${i.tools} tool markers${i.errors.length ? ". Error: " + i.errors[0] : ""}` : "";
  $("stage-bar").replaceChildren(
    h("span", { id: "stage-info", title: "What the preview shows" }, text),
    h("span", { style: "flex:1" }),
    tool("fit", "Fit the view to the model", () => preview.fit(), { id: "fit-view" }));
}

function syncPreview() {
  if (S.view) {
    const v = viewNode();
    preview.select(v && v.kind === "axis" ? { axis: v.name } : v && (v.kind === "geometry") ? { part: v.name } : null);
    return;
  }
  const n = currentNode();
  preview.select(n && n.kind === "axis" ? { axis: n.name } : n && n.kind === "part" ? { part: n.name } : null);
}

function renderAll() {
  const keep = [$("left").scrollTop, $("right").scrollTop];
  renderToolbar();
  renderChips();
  renderReadonlyBar();
  const left = [projectsCard(), viewerCard()];
  const right = [];
  if (S.view) { left.push(structureCard()); right.push(detailsCard(), bindingsCard(), viewJointsCard(), warningsCard(), viewZoneCard()); }
  else if (S.project) { left.push(meshesCard(), treeCard()); right.push(propertiesCard(), jointsCard(), zoneCard()); }
  else right.push(h("section", { class: "card" }, h("h2", {}, "Start"), h("p", { class: "hint" }, "Create a project (+ under Projects), upload your STL files, build the tree of axes and parts, bind the axes to MOTION axes and upload the model to the 3D viewer.")));
  $("left").replaceChildren(...left);
  $("right").replaceChildren(...right);
  $("left").scrollTop = keep[0];
  $("right").scrollTop = keep[1];
  renderStageBar();
}

// ---------------------------------------------------------------- 3D viewer projects: list and read-only view
async function loadViewerList() {
  try { S.vlist = { projects: (await api("GET", "/viewer/projects")).projects, error: "", loaded: true }; }
  catch (e) { S.vlist = { projects: [], error: e.message, loaded: true }; }
  if (!UI.busy(document.body)) renderAll();
}

function viewerCard() {
  const v = S.vlist;
  const table = UI.table([
    { label: "Name", hint: "Name of a project in the 3D viewer app", get: (n) => n },
    { label: "", hint: "Actions", get: (n) => h("span", { class: "tools", style: "margin:0;flex-wrap:nowrap" },
      tool("eye", `Open ${n} read-only: see the model, its axes, bindings and warnings. Nothing is changed.`, (ev) => { ev.stopPropagation(); guard(() => openView(n)); }, { class: "tool view-open", "data-name": n })) },
  ], v.projects, { key: (n) => n, empty: v.loaded ? (v.error ? "-" : "The 3D viewer has no projects") : "Loading ...", id: "viewer-table", cls: "projects-table" });
  table.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-key]");
    if (tr && !ev.target.closest("button") && !(S.view && S.view.name === tr.dataset.key)) guard(() => openView(tr.dataset.key));
  });
  table.querySelectorAll("tr[data-key]").forEach((tr) => { if (S.view && tr.dataset.key === S.view.name) tr.classList.add("cur"); });
  return h("section", { class: "card", id: "viewer-card" },
    h("h2", {}, h("span", { class: "grow" }, "3D viewer projects"),
      tool("refresh", "Read the project list of the 3D viewer app again", () => loadViewerList(), { id: "viewer-refresh" })),
    v.error ? h("p", { class: "hint", id: "viewer-error", title: "Why the list is empty" }, v.error) : null,
    table);
}

const inv = (f, model) => (f && f[0] !== 0 ? (model - f[1]) / f[0] : 0);       // MOTION value of a model value
function usedFormula(a) { return a.formula || [1, 0]; }
function modelValue(a) {
  if (a.passive) return a.initial;
  const f = usedFormula(a);
  return f[0] * (S.view.motion[a.name] ?? 0) + f[1];
}
function formulaText(a) {
  if (a.passive) return "solved by the viewer (assignKin)";
  if (!a.binding) return "not bound: no formula";
  return a.formula ? `model = ${a.script.trim() || "value"}` : "formula not applied";
}
function viewNode() { return S.view && S.selection && S.selection.kind === "vnode" ? S.view.byId[S.selection.id] || null : null; }

async function openView(name) {
  const previous = S.project ? S.project.name : S.view ? S.view.previous : "";
  banner(`Reading ${name} from the 3D viewer ...`, true);
  const d = await api("POST", `/viewer/projects/${enc(name)}/open`, {});
  if (S.project) closeProject(true);
  else if (S.view) leaveView();
  const byId = {}, parent = {};
  (function index(nodes, up) { for (const n of nodes) { byId[n.id] = n; parent[n.id] = up; if (n.children) index(n.children, n); } })(d.structure, null);
  S.view = { name, data: d, byId, parent, previous, seq: Date.now(), motion: {}, zone: null, kin: "" };
  for (const a of d.axes) S.view.motion[a.name] = a.passive ? 0 : inv(usedFormula(a), a.initial);       // the viewer starts at initial_value
  const cartesian = S.kins.find((k) => k.cartesian);
  S.view.kin = (cartesian || S.kins[0] || {}).name || "";
  S.selection = null; S.cache.clear(); S.zone = null; S.sizes = {};
  preview.reset();
  S.modelError = "";
  preview.setXml(d.xml).catch((e) => { S.modelError = e.message; banner(e.message); });
  preview.setValues(Object.fromEntries(d.axes.map((a) => [a.name, modelValue(a)])));
  banner(`${name} opened read only: ${d.axes.length} axes, ${d.warnings.length} warnings`, true);
  renderAll();
}
function leaveView() {
  S.view = null; S.selection = null; S.cache.clear(); S.zone = null; S.values = {};
  preview.reset();
}
async function closeView() {
  const prev = S.view.previous;
  leaveView();
  banner("");
  if (prev && S.projects.some((p) => p.name === prev)) await openProject(prev);
  else renderAll();
}

function renderReadonlyBar() {
  const bar = $("readonly-bar");
  bar.hidden = !S.view;
  if (!S.view) { bar.replaceChildren(); return; }
  bar.replaceChildren(ico("eye"),
    h("span", { class: "grow", id: "readonly-text", title: "This view only reads the project from the 3D viewer: it never writes to the viewer and never saves anything" },
      `Read only: ${S.view.name} from the 3D viewer. Nothing is changed.`),
    wide("close", "Close view", "Close the read-only view and go back to the editor", () => guard(closeView), { id: "close-view" }));
}

function structureCard() {
  const v = S.view;
  const box = h("div", { class: "tree-box", id: "view-tree", title: "The structure of the model: transforms, axes, parts and the tool. Click a node for its details." });
  const draw = (nodes) => h("ul", {}, nodes.map((n) => {
    const sel = S.selection && S.selection.id === n.id;
    const icon = n.kind === "axis" ? n.type : n.kind === "geometry" ? "part" : n.kind === "tool" ? "tool" : "frame";
    const sub = n.kind === "axis" ? (n.passive ? "passive" : n.binding || "not bound") : n.kind === "geometry" ? n.geo : n.kind === "tool" ? "TCP" : "";
    const row = h("div", { class: "ui-node" + (sel ? " ui-sel" : ""), "data-id": n.id, title: `${n.kind} ${n.name}${sub ? " (" + sub + ")" : ""}`, style: "padding-left:8px" },
      h("span", { class: "kind", title: n.kind }, ico(icon)), h("span", { class: "ui-label" }, n.name || "(no name)"), h("span", { class: "ui-sub" }, sub));
    row.addEventListener("click", () => { S.selection = { kind: "vnode", id: n.id }; renderAll(); syncPreview(); });
    const li = h("li", {}, row);
    if (n.children && n.children.length) { const ul = draw(n.children); ul.style.paddingLeft = "14px"; li.appendChild(ul); }
    return li;
  }));
  box.appendChild(draw(v.data.structure));
  return h("section", { class: "card", id: "structure-card" }, h("h2", {}, "Structure"), box);
}

function roField(value, hint) { return UI.field(value, () => {}, { readonly: true, hint }); }
function detailsCard() {
  const v = S.view, d = v.data, n = viewNode();
  let title = "Project", rows;
  const up = n ? v.parent[n.id] : null;
  const placement = (t) => t && t.kind === "transform" ? [
    ["Position (x, y, z) mm", roField(vecText(t.position), "Position from the initialvalue of the enclosing transform"), `From the transform "${t.name}", in the frame of the node it sits in`],
    ["Rotation (rx, ry, rz) deg", roField(vecText(t.rotation), "Rotation from the initialvalue of the enclosing transform, Rz x Ry x Rx"), "Rz × Ry × Rx"]] : [];
  if (n && n.kind === "transform") {
    title = `Transform ${n.name}`;
    rows = [["Name", roField(n.name, "Transform name"), ""],
      ["Position (x, y, z) mm", roField(vecText(n.position), "Position from the initialvalue"), "In the frame of the node it sits in"],
      ["Rotation (rx, ry, rz) deg", roField(vecText(n.rotation), "Rotation from the initialvalue, Rz x Ry x Rx"), "Rz × Ry × Rx"]];
    if (n.scale.some((x) => Math.abs(x - 1) > 1e-9)) rows.push(["Scale (x, y, z)", roField(vecText(n.scale), "Scale in the matrix"), "Lengths of the matrix columns"]);
    rows.push(["Raw initialvalue", roField(n.matrix.map(fmt).join(", "), "The 16 numbers of the 4 x 4 matrix, row by row"), "r11, r12, r13, tx, r21, ... , 0, 0, 0, 1"]);
  } else if (n && n.kind === "axis") {
    title = `${n.type === "rotation" ? "Rotation" : "Translation"} axis ${n.name}`;
    const unit = n.type === "rotation" ? "deg" : "mm";
    rows = [["Name", roField(n.name, "Model axis name"), ""],
      ["Type", roField(n.type, "Axis type"), "A rotation turns about the pivot, a translation slides along the direction"],
      ["Direction (x, y, z)", roField(vecText(n.direction), "Axis direction"), "In the frame of the enclosing node"]];
    if (n.pivot) rows.push(["Pivot (x, y, z) mm", roField(vecText(n.pivot), "Point on the rotation axis"), "In the frame of the enclosing node"]);
    rows.push(["Minimum", roField(fmt(n.min), `Lowest model value, ${unit}`), `${unit}, model units (after the formula)`],
      ["Maximum", roField(fmt(n.max), `Highest model value, ${unit}`), `${unit}, model units (after the formula)`],
      ["Initial value", roField(fmt(n.initial), `Model value the viewer starts at, ${unit}`), `${unit}, model units`],
      ["Custom data", roField(n.customdata || "-", "customdata attribute"), n.passive ? "assignKin: the viewer solves this joint from the kinematic" : ""],
      ["MOTION axis", roField(n.passive ? "(passive joint)" : n.binding || "not bound", "The MOTION axis this model axis follows"), "From the project's configuration JSON"],
      ["ExpressionScript", roField(n.script || "-", "ExpressionScript of the binding"), "Turns the MOTION value into the model value"],
      ["Formula", roField(n.passive || !n.binding ? "-" : n.formula ? `model = ${fmt(n.formula[0])} × value + ${fmt(n.formula[1])}` : "not understood", "The formula as the preview applies it"),
        n.passive || !n.binding ? "" : n.formula ? "The preview applies it" : "Not understood: the preview uses the value, formula not applied"]);
  } else if (n && (n.kind === "geometry" || n.kind === "tool")) {
    title = n.kind === "tool" ? `Tool ${n.name}` : `Part ${n.name}`;
    rows = [["Name", roField(n.name, "Geometry name"), ""], ["Object type", roField(n.objtype, "objtype attribute"), n.kind === "tool" ? "The tool centre point (TCP) marker" : ""]];
    if (n.kind === "geometry") {
      const colour = h("span", { class: "ui-ro", title: "Colour of the part, clrr / clrg / clrb (0 to 1)" },
        h("span", { class: "swatch", style: `background:${hexOf(n.colour.map((c) => Math.min(1, Math.max(0, c))))}` }), vecText(n.colour));
      rows.push(["Mesh file", roField(n.geo || "-", "STL file named by the geo attribute"),
        n.present === false ? "Not in the project" : n.file && n.file !== n.geo ? `Found as ${n.file} (different upper/lower case)` : ""],
        ["Colour (r, g, b)", colour, "0 to 1"], ["Alpha", roField(fmt(n.alpha), "alpha attribute"), "0 = opaque"]);
    }
    rows.push(...placement(up));
    if (n.customdata) rows.push(["Custom data", roField(n.customdata, "customdata attribute"), ""]);
  } else {
    const bound = d.axes.filter((a) => a.binding).length;
    rows = [["Name", roField(v.name, "Project name in the 3D viewer"), "Click a node in the structure for its details"],
      ["Files", roField(`${d.files.length} (${fmtSize(d.files.reduce((x, f) => x + f.size, 0))})`, "Files read from the project"), d.files.map((f) => f.name).slice(0, 6).join(", ") + (d.files.length > 6 ? ", ..." : "")],
      ["Axes", roField(`${d.axes.length}, ${bound} bound`, "Model axes and how many are bound to a MOTION axis"), ""],
      ["Tool markers", roField(d.tools, "Number of tool markers"), ""],
      ["Warnings", roField(d.warnings.length, "Number of warnings, see Warnings"), ""]];
  }
  return h("section", { class: "card", id: "props-card" }, h("h2", {}, title), UI.settings(rows));
}

function axisWarnings(name) { return S.view.data.warnings.filter((w) => w.axis === name); }
const SHORT = { expression: "Formula ignored for MCS zones", unbound: "Not bound", assignkin: "Passive joint (assignKin)", binding_without_axis: "Not in the model", duplicate_axis: "Duplicate axis name" };

function bindingsCard() {
  const d = S.view.data;
  const rows = d.axes.map((a) => ({ model: a.name, node: a.passive ? "-" : a.binding || "not bound", script: a.passive ? "-" : a.binding ? a.script || "value" : "-", formula: a.formula, bound: !!a.binding, passive: a.passive, name: a.name }));
  for (const b of d.bindings) if (!b.in_model) rows.push({ model: b.model, node: b.node, script: b.script, formula: b.formula, bound: true, passive: false, name: b.model, orphan: true });
  const t = UI.table([
    { label: "Model axis", hint: "Axis name in the model (XML)", get: (r) => r.model },
    { label: "MOTION axis", hint: "The MOTION axis (Data Layer node) that drives the model axis", get: (r) => r.node },
    { label: "Formula", hint: "ExpressionScript: how the MOTION value becomes the model value", get: (r) => h("span", { title: r.formula ? `model = ${fmt(r.formula[0])} x value + ${fmt(r.formula[1])}` : r.bound && !r.passive ? "Not a simple linear formula: the preview cannot apply it" : "" }, r.script) },
    { label: "Status", hint: "Warnings for this axis; OK means none", cls: "ui-wrap", get: (r) => {
      const ws = axisWarnings(r.name);
      return h("span", { class: "status-chips" }, ws.length ? ws.map((w) => h("span", { class: "chip " + (w.level === "info" ? "" : "warn"), title: w.text }, SHORT[w.code] || w.code)) : h("span", { class: "chip ok", title: "No warning for this axis" }, "OK"));
    } },
  ], rows, { key: (r) => r.model + (r.orphan ? "!" : ""), empty: "The model has no axes", id: "bindings-table", cls: "bind-table" });
  return h("section", { class: "card", id: "bindings-card" }, h("h2", {}, "Bindings"), t);
}

function viewJointsCard() {
  const v = S.view, d = v.data;
  const outs = {};
  const rows = d.axes.map((a) => {
    const f = usedFormula(a);
    const mv = v.motion[a.name] ?? 0;
    let lo = inv(f, a.min), hi = inv(f, a.max);
    if (lo > hi) [lo, hi] = [hi, lo];
    if (!(hi > lo) || a.passive) { lo = a.type === "rotation" ? -360 : -1000; hi = -lo; }
    const unit = a.type === "rotation" ? "deg" : "mm";
    const off = !!a.passive;
    const num = h("input", { type: "number", class: "joint-num", value: fmt(mv), step: "any", disabled: off, title: off ? `${a.name} is a passive joint: the viewer solves it from the kinematic` : `${a.name} MOTION value for the preview (${unit}); only moves the preview` });
    const rng = h("input", { type: "range", class: "joint-range", min: lo, max: hi, step: (hi - lo) / 400, value: mv, disabled: off, title: off ? `${a.name} is a passive joint: the viewer solves it from the kinematic` : `Drag to move ${a.name} in the preview (MOTION value)` });
    const out = h("span", { class: "joint-model", title: "Model value the preview applies (after the formula)" }, fmt(modelValue(a)));
    const set = (val) => { v.motion[a.name] = val; out.textContent = fmt(modelValue(a)); preview.setValue(a.name, modelValue(a)); };
    rng.addEventListener("input", () => { num.value = fmt(rng.value); set(+rng.value); });
    num.addEventListener("input", () => { if (num.value !== "" && Number.isFinite(+num.value)) { rng.value = num.value; set(+num.value); } });
    const note = h("span", { class: "small dim joint-note", title: off ? "Passive joint: the preview shows it at its initial value" : a.formula ? "The formula the preview applies: model value from the MOTION value" : a.binding ? "The ExpressionScript is not a simple linear formula, so the preview uses the MOTION value as it is" : "Not bound: the preview uses the value as it is" },
      off ? "passive: solved by the kinematic" : a.binding && !a.formula ? `${a.script.trim()}: formula not applied` : a.binding ? `model = ${a.script.trim() || "value"}` : "not bound");
    outs[a.id] = out;
    return { a, num, rng, out, note };
  });
  const t = UI.table([
    { label: "Axis", hint: "Model axis; click to select it", get: (r) => h("span", {}, r.a.name, r.note) },
    { label: "Slider", hint: "Moves the axis in the preview only, in the units of the MOTION axis", get: (r) => r.rng },
    { label: "Value", hint: "MOTION axis value in the preview, deg or mm", get: (r) => r.num },
    { label: "Model", hint: "Model value after the formula (what the viewer would show)", get: (r) => r.out, num: true },
  ], rows, { key: (r) => r.a.id, empty: "No axes", cls: "joint-table", id: "joints-table" });
  t.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-key]");
    if (tr && !ev.target.closest("input")) { S.selection = { kind: "vnode", id: tr.dataset.key }; renderAll(); syncPreview(); }
  });
  t.querySelectorAll("tr[data-key]").forEach((tr) => { if (S.selection && S.selection.id === tr.dataset.key) tr.classList.add("cur"); });
  return h("section", { class: "card", id: "joints-card" },
    h("h2", {}, h("span", { class: "grow" }, "Joints (preview only)"),
      tool("reset", "Set all joints back to the initial values of the model", () => {
        for (const a of d.axes) if (!a.passive) v.motion[a.name] = inv(usedFormula(a), a.initial);
        preview.setValues(Object.fromEntries(d.axes.map((a) => [a.name, modelValue(a)]))); renderAll();
      }, { id: "zero-joints" })),
    t,
    h("p", { class: "hint", id: "joints-note", title: "How the sliders work" }, "The sliders are in MOTION axis units; the preview applies the formula. Passive (assignKin) joints are solved by the viewer from the kinematic and stay at their initial value here."));
}

function warningsCard() {
  const ws = S.view.data.warnings;
  return h("section", { class: "card", id: "warnings-card" }, h("h2", {}, `Warnings (${ws.length})`),
    ws.length ? h("ul", { class: "warn-list", id: "warn-list", title: "What may be wrong with this model" },
      ws.map((w) => h("li", { class: w.level, "data-code": w.code, title: w.text },
        h("span", { class: "chip " + (w.level === "info" ? "" : "warn"), title: w.level === "info" ? "Information" : "Warning" }, w.level === "info" ? "Info" : "Warning"), h("span", {}, w.text))))
      : h("p", { class: "hint", id: "warn-none" }, "No warnings."));
}

function zoneTable(z) {
  return UI.table([
    { label: "Check", hint: "What is checked", get: (r) => r.name },
    { label: "Result", hint: "OK or a warning", get: (r) => h("span", { class: "chip res " + (r.ok ? "ok" : "warn"), title: r.ok ? "Passed" : "Needs attention" }, r.ok ? "OK" : "Warning") },
    { label: "Note", hint: "Values and what they mean", get: (r) => h("span", {}, r.note, h("br"), h("span", { class: "dim" }, r.value)), cls: "ui-wrap ui-note" },
  ], z.rows, { cls: "zone-table", id: "zone-table" });
}
function viewZoneCard() {
  const v = S.view, z = v.zone;
  const sel = h("select", { id: "view-kin", title: "A kinematic from ctrlX MOTION whose first axes the zone check compares with the model (Cartesian kinematics only)", onchange: (e) => { v.kin = e.target.value; } },
    S.kins.length ? S.kins.map((k) => h("option", { value: k.name, selected: k.name === v.kin }, `${k.name} (${k.type || "?"})`)) : h("option", { value: "" }, S.motionError || "No kinematics found"));
  const run = () => guard(async () => {
    if (!v.kin) { banner("Pick a kinematic first"); return; }
    v.zone = await api("POST", "/viewer/zone", { kinematic: v.kin });
    renderAll();
  });
  let body = null;
  if (z && !z.checked) body = h("p", { class: "hint", id: "zone-note" }, z.note);
  else if (z) body = zoneTable(z);
  return h("section", { class: "card", id: "zone-card" },
    h("h2", {}, h("span", { class: "grow" }, "Zone check")),
    h("div", { class: "tools" }, h("span", { class: "lbl" }, "Kinematic"), sel,
      wide("check", "Check zone", "Compare the model with the selected Cartesian kinematic: where the MCS zone frame sits, with the ExpressionScripts applied", run, { id: "view-zone-check", disabled: !S.kins.length })),
    body,
    h("p", { class: "hint", title: "Why there is no Fix here" }, "Result only. The fix is for projects of this app; a viewer project is never changed."));
}

// ---------------------------------------------------------------- start
async function loadMotion() {
  try {
    S.axes = (await api("GET", "/motion/axes")).axes;
    S.kins = (await api("GET", "/motion/kinematics")).kinematics;
    S.motionError = "";
  } catch (e) {
    S.axes = []; S.kins = [];
    S.motionError = "MOTION not readable: " + e.message;
  }
}

preview = createPreview($("stage"), {
  loadMesh: (f) => loadMesh(f),
  onInfo: (info) => { S.info = info; renderStageBar(); },
});
window.__mb = { S, preview };

$("file-input").addEventListener("change", (ev) => { const f = ev.target.files[0]; if (f) uploadMesh(f); });

(async () => {
  try {
    await Promise.all([loadMotion(), loadList(true)]);
    const last = localGet("last");
    if (last && S.projects.some((p) => p.name === last)) await openProject(last);
    else if (S.projects.length === 1) await openProject(S.projects[0].name);
    else renderAll();
  } catch (e) {
    banner(e.message);
    renderAll();
  }
  loadViewerList();
  every(5000, () => loadList(false));
  every(30000, loadMotion);
})();
