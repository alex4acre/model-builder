// SPDX-License-Identifier: MIT
// 3D preview. The scene is built by PARSING the machine_definition XML the server generates (the file the 3D viewer
// receives), the same way the viewer builds its own scene (finding R1: rzx/rzy/rzz and x/y/z are in the local frame of
// the enclosing node; a rotation turns a pivot node at rz about the axis, its content sits at -rz inside it; a
// translation moves its object by direction * value). The parser is reused for importing projects in Phase 2.

import * as THREE from "three";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const loader = new STLLoader();
const ACCENT = 0x007bc0, HIGHLIGHT = 0xff8c00;

export function parseNumbers(text) {
  return String(text).split(",").map(Number);
}

// Parses the XML into a plain tree: [{tag: "transform"|"axis"|"geometry", ...attrs, children: [...]}]
export function parseMachineXml(text) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  if (doc.querySelector("parsererror")) throw new Error("The generated XML cannot be parsed");
  const read = (el) => {
    const n = { tag: el.tagName, attrs: Object.fromEntries([...el.attributes].map((a) => [a.name, a.value])), children: [] };
    for (const c of el.children) if (["transform", "axis", "geometry"].includes(c.tagName)) n.children.push(read(c));
    return n;
  };
  return [...doc.documentElement.children].filter((c) => ["transform", "axis", "geometry"].includes(c.tagName)).map(read);
}

export function createPreview(host, { loadMesh, onInfo }) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  host.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf4f6f8);
  const camera = new THREE.PerspectiveCamera(40, 1, 1, 100000);
  camera.up.set(0, 0, 1);
  camera.position.set(1500, -1800, 1200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.addEventListener("change", () => invalidate());
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f96, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  scene.add(sun, sun.target);

  const content = new THREE.Group();          // the model (root of the parsed XML)
  const overlay = new THREE.Group();          // grid, world axes, the selected axis arrow
  scene.add(content, overlay);

  let axes = {};                              // name -> {type, dir, obj, pivot, min, max, initial}
  let parts = [];                             // {name, mesh, owner axes}
  let tools = [];
  let values = {};
  let selected = { axis: null, part: null };
  let raf = 0, token = 0, sceneSize = 1000, arrow = null, fitted = false, loading = 0;

  function invalidate() {
    if (raf) return;
    raf = requestAnimationFrame(() => { raf = 0; draw(); });
  }
  function draw() {
    sun.position.copy(camera.position);
    renderer.render(scene, camera);
  }
  function resize() {
    const w = host.clientWidth || 300, h = host.clientHeight || 300;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    invalidate();
  }
  new ResizeObserver(resize).observe(host);

  function clear(group) {
    for (const o of [...group.children]) {
      group.remove(o);
      o.traverse((c) => { if (c.isMesh && c.material) c.material.dispose(); if (c.geometry && c.userData.own) c.geometry.dispose(); });
    }
  }

  // ---- XML -> scene ----
  function build(nodes, parent, ctx) {
    for (const n of nodes) {
      const a = n.attrs;
      if (n.tag === "transform") {
        const g = new THREE.Group();
        g.name = a.name;
        const nums = a.initialvalue ? parseNumbers(a.initialvalue) : [];
        const m = new THREE.Matrix4();
        if (nums.length === 16 && nums.every(Number.isFinite)) m.fromArray(nums).transpose();
        m.decompose(g.position, g.quaternion, g.scale);
        parent.add(g);
        build(n.children, g, ctx);
      } else if (n.tag === "axis") {
        const n0 = (v) => (Number.isFinite(+v) ? +v : 0);
        const dir = new THREE.Vector3(n0(a.x), n0(a.y), n0(a.z)).normalize();
        const info = { name: a.name, type: a.type, dir, min: n0(a.minvalue), max: n0(a.maxvalue), initial: n0(a.initial_value) };
        const obj = new THREE.Group();
        obj.name = a.name;
        if (a.type === "rotation") {
          const rz = new THREE.Vector3(n0(a.rzx), n0(a.rzy), n0(a.rzz));
          const pivot = new THREE.Group();
          pivot.name = "rzv_" + a.name;
          pivot.position.copy(rz);
          obj.position.copy(rz).negate();
          pivot.add(obj);
          parent.add(pivot);
          Object.assign(info, { obj, pivot, rz });
        } else {
          parent.add(obj);
          Object.assign(info, { obj, pivot: null });
        }
        ctx.axes[a.name] = info;
        build(n.children, obj, ctx);
      } else if (n.tag === "geometry") {
        if (a.objtype === "tool") {
          const marker = new THREE.Group();
          const cone = new THREE.Mesh(new THREE.ConeGeometry(12, 40, 16), new THREE.MeshBasicMaterial({ color: ACCENT }));
          cone.rotation.x = -Math.PI / 2;                // a cone points along +y: turn it so its tip is at the tool point
          cone.position.z = 20;                          // and its body above
          cone.userData.own = true;
          marker.add(cone);
          marker.name = a.name;
          marker.userData.tool = true;
          parent.add(marker);
          ctx.tools.push(marker);
        } else if (a.geo) {
          // alpha is a transparency in the viewer's files (0 = opaque; every example has alpha="0")
          const alpha = Math.min(0.95, Math.max(0, Number.isFinite(+a.alpha) ? +a.alpha : 0));
          const mesh = new THREE.Mesh(new THREE.BufferGeometry(),
            new THREE.MeshStandardMaterial({ color: new THREE.Color(Number.isFinite(+a.clrr) ? +a.clrr : 0.6, Number.isFinite(+a.clrg) ? +a.clrg : 0.6, Number.isFinite(+a.clrb) ? +a.clrb : 0.6),
              metalness: 0.15, roughness: 0.7, side: THREE.DoubleSide, emissive: 0x000000, transparent: alpha > 0, opacity: 1 - alpha }));
          mesh.name = a.name;
          mesh.userData.file = a.geo;
          parent.add(mesh);
          ctx.parts.push(mesh);
          ctx.pending.push(loadMesh(a.geo).then((geo) => { if (ctx.token === token) { mesh.geometry = geo; invalidate(); } }, (e) => { ctx.errors.push(`${a.geo}: ${e.message}`); }));
        }
      }
    }
  }

  async function setXml(text) {
    const my = ++token;
    const ctx = { axes: {}, parts: [], tools: [], pending: [], errors: [], token: my };
    const nodes = parseMachineXml(text);
    clear(content);
    build(nodes, content, ctx);
    axes = ctx.axes; parts = ctx.parts; tools = ctx.tools;
    for (const [name, v] of Object.entries(values)) if (axes[name]) setValue(name, v, true);
    refreshHighlight();
    invalidate();
    loading = ctx.pending.length;
    note();
    await Promise.all(ctx.pending);
    if (my !== token) return;
    loading = 0;
    if (!fitted && parts.length) { fit(); fitted = true; }
    else { updateOverlay(); }
    note(ctx.errors);
    invalidate();
  }

  function note(errors) {
    if (onInfo) onInfo({ axes: Object.keys(axes).length, parts: parts.length, tools: tools.length, loading, errors: errors || [] });
  }

  function setValue(name, v, quiet) {
    const a = axes[name];
    values[name] = v;
    if (!a) return;
    if (a.type === "rotation") a.pivot.quaternion.setFromAxisAngle(a.dir, THREE.MathUtils.degToRad(v));
    else a.obj.position.copy(a.dir).multiplyScalar(v);
    if (!quiet) { content.updateMatrixWorld(true); updateOverlay(); invalidate(); }
  }
  function setValues(map) {
    for (const [k, v] of Object.entries(map)) setValue(k, v, true);
    content.updateMatrixWorld(true);
    updateOverlay();
    invalidate();
  }

  // ---- selection ----
  function select(sel) {
    selected = { axis: sel && sel.axis || null, part: sel && sel.part || null };
    refreshHighlight();
    updateOverlay();
    invalidate();
  }
  function refreshHighlight() {
    const moving = new Set();
    const a = selected.axis && axes[selected.axis];
    if (a) a.obj.traverse((c) => { if (c.isMesh && c.userData.file) moving.add(c); });
    for (const m of parts) {
      const on = moving.has(m) || (selected.part && m.name === selected.part);
      m.material.emissive.setHex(on ? 0x6a3a00 : 0x000000);
    }
  }
  function bounds() {
    content.updateMatrixWorld(true);
    const box = new THREE.Box3();
    for (const m of parts) if (m.geometry.attributes.position) box.expandByObject(m);
    for (const t of tools) box.expandByPoint(t.getWorldPosition(new THREE.Vector3()));
    return box;
  }
  function updateOverlay() {
    if (arrow) { overlay.remove(arrow); arrow = null; }
    const a = selected.axis && axes[selected.axis];
    if (!a) return;
    content.updateMatrixWorld(true);
    const parentM = (a.pivot || a.obj).parent.matrixWorld;
    const dir = a.dir.clone().transformDirection(parentM).normalize();
    let origin;
    if (a.type === "rotation") origin = a.pivot.getWorldPosition(new THREE.Vector3());
    else {
      const box = new THREE.Box3();
      a.obj.traverse((c) => { if (c.isMesh && c.geometry.attributes.position) box.expandByObject(c); });
      origin = box.isEmpty() ? a.obj.getWorldPosition(new THREE.Vector3()) : box.getCenter(new THREE.Vector3());
    }
    const len = sceneSize * 0.35;
    arrow = new THREE.Group();
    const color = a.type === "rotation" ? 0xd62828 : 0x00884a;
    const start = origin.clone().addScaledVector(dir, -len / 2);
    arrow.add(new THREE.ArrowHelper(dir, start, len, color, len * 0.12, len * 0.06));
    const ball = new THREE.Mesh(new THREE.SphereGeometry(sceneSize * 0.012, 12, 12), new THREE.MeshBasicMaterial({ color }));
    ball.position.copy(origin);
    arrow.add(ball);
    arrow.traverse((o) => { o.renderOrder = 10; if (o.material) { o.material.depthTest = false; o.material.transparent = true; } });
    overlay.add(arrow);
  }

  // ---- view ----
  function fit() {
    const box = bounds();
    if (box.isEmpty()) { box.set(new THREE.Vector3(-500, -500, -500), new THREE.Vector3(500, 500, 500)); }
    const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
    sceneSize = Math.max(size.x, size.y, size.z, 100);
    controls.target.copy(center);
    const dist = sceneSize * 1.6;
    camera.position.copy(center).add(new THREE.Vector3(0.8, -1, 0.7).normalize().multiplyScalar(dist));
    camera.near = sceneSize / 200;
    camera.far = sceneSize * 40;
    camera.updateProjectionMatrix();
    controls.update();
    // grid in the XY plane at the lowest point, world axes at the origin
    clear(overlay);
    const grid = new THREE.GridHelper(Math.ceil(sceneSize * 3 / 100) * 100, 30, 0x9aa5b1, 0xd5dbe0);
    grid.rotation.x = Math.PI / 2;
    grid.position.set(center.x, center.y, box.min.z);
    const axesHelper = new THREE.AxesHelper(sceneSize * 0.25);
    overlay.add(grid, axesHelper);
    arrow = null;
    updateOverlay();
    invalidate();
  }

  function reset() { values = {}; fitted = false; token++; clear(content); axes = {}; parts = []; tools = []; invalidate(); }

  resize();
  controls.update();
  return {
    setXml, setValue, setValues, select, fit, reset,
    // for tests and the status line
    info() {
      content.updateMatrixWorld(true);
      return { axes: Object.keys(axes), parts: parts.length, loaded: parts.filter((m) => m.geometry.attributes.position).length,
               tools: tools.map((t) => t.getWorldPosition(new THREE.Vector3()).toArray()), highlighted: parts.filter((m) => m.material.emissive.getHex() !== 0).length,
               arrow: !!arrow };
    },
    axisWorld(name) {
      content.updateMatrixWorld(true);
      const a = axes[name];
      return a ? (a.pivot || a.obj).getWorldPosition(new THREE.Vector3()).toArray() : null;
    },
    dispose() { renderer.dispose(); },
  };
}
