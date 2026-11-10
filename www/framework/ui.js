// SPDX-License-Identifier: MIT
// ctrlx-baseline framework: the UI pieces every app uses, so they work the same in every app (STANDARD.md §6).
// Load after ctrlx.js and before the app's own script; style in ui.css:
//   <link rel="stylesheet" href="framework/base.css"><link rel="stylesheet" href="framework/ui.css"><link rel="stylesheet" href="style.css">
//   <script src="framework/ctrlx.js"></script><script src="framework/ui.js"></script><script src="app.js"></script>
//
//   UI.h(tag, attrs, ...children)      build elements          UI.icon(name)                   inline SVG icon
//   UI.field(value, commit, opts)      one edit field          UI.table(columns, rows, opts)   table (filter, paging)
//   UI.settings(rows)                  Setting | Value | Note  UI.paramTable(rows, opts)       parameter table
//   UI.section(title, body, opts)      folding box             UI.expandAll(root) / UI.collapseAll(root)
//   UI.tree(host, opts)                side panel tree         UI.nav(opts)                    back button + page title
//   UI.search(input, opts)             search box              UI.searchCard(opts)             the search box element
//   UI.changes(opts)                   changes kept before a commit (list, undo, count badge)
//   UI.confirmWrite(what, consequence) the one question before something changes a device
//
// Every element gets a hover hint (title). Class names start with "ui-" so an app's own CSS can't style them by accident.

"use strict";

const UI = (() => {
  const APP = location.pathname.split("/")[1] || "app";

  // ---------- elements ----------

  // h("td", {class: "x", title: "...", onclick: fn, "data-key": "k"}, "text", node, [more], null)
  function h(tag, attrs, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
      else if (k === "class") e.className = v;
      else if (k === "value") e.value = v;
      else if (k === "html") e.innerHTML = v;            // only for fixed markup (icons), never for data
      else e.setAttribute(k, v === true ? "" : v);
    }
    const add = (c) => {
      if (c === null || c === undefined || c === false) return;
      if (Array.isArray(c)) c.forEach(add);
      else e.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
    };
    children.forEach(add);
    return e;
  }

  const ICONS = {
    search: "M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
    back: "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z",
    expand: "M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z",
    collapse: "M12 8l-6 6 1.41 1.41L12 10.83l4.59 4.58L18 14z",
    save: "M17 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7l-4-4zm-5 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm3-10H5V5h10v4z",
    folder: "M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2z",
    upload: "M5 20h14v-2H5v2zm0-10h4v6h6v-6h4l-7-7-7 7z",
    download: "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
    delete: "M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
    undo: "M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62A7.95 7.95 0 0 1 12.5 10c3.54 0 6.55 2.31 7.6 5.5l2.37-.78A10.02 10.02 0 0 0 12.5 8z",
    lock: "M18 8h-1V6a5 5 0 0 0-10 0v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2zM9 6a3 3 0 0 1 6 0v2H9V6zm3 11a2 2 0 1 1 0-4 2 2 0 0 1 0 4z",
    add: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
    close: "M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
    play: "M8 5v14l11-7z",
  };
  function icon(name) {
    return h("span", { class: "ui-icon", "aria-hidden": "true", html: `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="${ICONS[name] || ""}"/></svg>` });
  }

  const store = {
    get(k, d) { try { const v = localStorage.getItem(APP + ".ui." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(APP + ".ui." + k, JSON.stringify(v)); } catch (e) { /* private window: not remembered */ } },
  };

  // ---------- edit field ----------
  // field(value, async commit(text) -> throws to refuse, {hint, choices, readonly})
  //   text/number -> input; true/false and lists of allowed values (choices) -> select
  //   Enter (or picking from a select) commits, Esc undoes; .ui-dirty = changed, not kept yet (yellow),
  //   .ui-bad = refused, the reason is in the hint (red); after a commit the row with the same data-key flashes green
  //   on the next render (UI.kept), or the field itself when the page isn't rendered again.
  let kept = null;
  function field(value, commit, opts = {}) {
    const shown = Array.isArray(value) ? value.join(", ") : value === null || value === undefined ? "" : String(value);
    const hint = (opts.hint ? opts.hint + ". " : "") + (opts.readonly ? "Read-only" : opts.choices || typeof value === "boolean"
      ? "Pick a value to keep it." : "Edit and press Enter to keep the new value, Esc to undo.");
    if (opts.readonly) return h("span", { class: "ui-ro", title: hint }, shown);
    let inp;
    const reset = () => { inp.value = shown; inp.classList.remove("ui-dirty", "ui-bad"); inp.title = hint; };
    if (typeof value === "boolean" || opts.choices) {
      const list = typeof value === "boolean" ? [["true", "yes"], ["false", "no"]]
        : (opts.choices.includes(shown) ? opts.choices : [shown, ...opts.choices]).map((c) => [c, c === shown && !opts.choices.includes(c) ? `${c} (not an allowed value)` : c]);
      inp = h("select", { class: "ui-edit", title: hint }, list.map(([v, t]) => h("option", { value: v }, t)));
      inp.value = shown;
      inp.addEventListener("change", () => run());
      inp.addEventListener("keydown", (ev) => { if (ev.key === "Escape") reset(); });
    } else {
      inp = h("input", { class: "ui-edit" + (typeof value === "number" ? " ui-num" : ""), value: shown, title: hint, spellcheck: "false", autocomplete: "off" });
      inp.addEventListener("input", () => inp.classList.toggle("ui-dirty", inp.value !== shown));
      inp.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") run();
        if (ev.key === "Escape") reset();
      });
    }
    async function run() {
      if (inp.value === shown) { inp.classList.remove("ui-dirty"); return; }
      const row = inp.closest("[data-key]");
      inp.disabled = true;
      try {
        kept = row ? row.dataset.key : null;
        await commit(inp.value);
        if (inp.isConnected) {             // the page was not rendered again: show it on the field itself
          inp.disabled = false;
          inp.classList.remove("ui-dirty", "ui-bad");
          flash(row || inp);
        }
      } catch (e) {
        kept = null;
        inp.disabled = false;
        inp.classList.add("ui-bad");
        inp.title = "Not kept: " + e.message;
        if (typeof banner === "function") banner("Not kept: " + e.message);
      }
    }
    inp.uiBusy = () => document.activeElement === inp || inp.classList.contains("ui-dirty") || inp.classList.contains("ui-bad");
    return inp;
  }
  function flash(el, kind = "ok") {
    el.classList.remove("ui-flash-ok", "ui-flash");
    void el.offsetWidth;
    el.classList.add(kind === "ok" ? "ui-flash-ok" : "ui-flash");
  }
  // true while the user is typing in (or has an unkept value in) a field inside el: don't refresh it then
  const busy = (el) => [...(el ? el.querySelectorAll(".ui-edit") : [])].some((f) => f.uiBusy && f.uiBusy());

  // ---------- tables ----------
  // columns: [{label, hint, get(row) -> text | Node, cls, num}]
  // opts: {key(row) -> data-key (rows can then be found, focused and flashed), id, empty, page (rows per page),
  //        filter (hint text: shows a filter box over the rows' text), cls}
  function table(columns, rows, opts = {}) {
    const wrap = h("div", { class: "ui-table-wrap" });
    const head = h("thead", {}, h("tr", {}, columns.map((c) => h("th", { title: c.hint || c.label, class: c.num ? "ui-num" : null }, c.label))));
    const body = h("tbody");
    const tbl = h("table", { class: "ui-table" + (opts.cls ? " " + opts.cls : ""), id: opts.id }, head, body);
    const pager = h("div", { class: "ui-pager" });
    let shown = rows, page = 0;
    const size = opts.page || 0;
    function draw() {
      body.replaceChildren();
      const from = size ? page * size : 0;
      const part = size ? shown.slice(from, from + size) : shown;
      if (!part.length) body.appendChild(h("tr", { class: "ui-empty" }, h("td", { colspan: columns.length }, opts.empty || "Nothing to show")));
      for (const r of part) {
        const k = opts.key ? String(opts.key(r)) : null;
        const tr = h("tr", { "data-key": k }, columns.map((c) => {
          let v;
          try { v = c.get(r); } catch (e) { v = "?"; }
          return h("td", { class: [c.cls, c.num ? "ui-num" : null].filter(Boolean).join(" ") || null, title: typeof v === "string" || typeof v === "number" ? String(v) : null }, v);
        }));
        if (k !== null && k === kept) { flash(tr); kept = null; }
        body.appendChild(tr);
      }
      pager.replaceChildren();
      const pages = size ? Math.ceil(shown.length / size) : 1;
      pager.hidden = pages <= 1;
      if (pages > 1) {
        pager.append(
          h("button", { class: "ui-btn", disabled: page === 0, title: "Previous rows", onclick: () => { page--; draw(); } }, "‹"),
          h("span", { title: "Rows shown" }, `${from + 1}–${Math.min(from + size, shown.length)} of ${shown.length}`),
          h("button", { class: "ui-btn", disabled: page >= pages - 1, title: "Next rows", onclick: () => { page++; draw(); } }, "›"));
      }
    }
    if (opts.filter) {
      const card = searchCard({ placeholder: "Filter", hint: opts.filter, small: true });
      const inp = card.querySelector("input");
      search(inp, { delay: 150, onQuery: (q) => { const t = q.toLowerCase(); shown = rows.filter((r) => rowText(r).includes(t)); page = 0; draw(); }, onClear: () => { shown = rows; page = 0; draw(); } });
      wrap.appendChild(h("div", { class: "ui-filter" }, card));
    }
    const rowText = (r) => columns.map((c) => { try { const v = c.get(r); return v instanceof Node ? (v.value !== undefined ? v.value : v.textContent) : String(v ?? ""); } catch (e) { return ""; } }).join(" ").toLowerCase();
    wrap.append(h("div", { class: "ui-scroll" }, tbl), pager);
    draw();
    wrap.uiShowKey = (k) => {                           // go to the page holding the row with this key; returns the row
      if (size && opts.key) { const i = shown.findIndex((r) => String(opts.key(r)) === String(k)); if (i >= 0 && Math.floor(i / size) !== page) { page = Math.floor(i / size); draw(); } }
      return body.querySelector(`tr[data-key="${CSS.escape(String(k))}"]`);
    };
    return wrap;
  }

  // rows: [[setting, value (text | Node), note, hint]]
  function settings(rows) {
    return table([
      { label: "Setting", hint: "What is set", get: (r) => r[0], cls: "ui-setting" },
      { label: "Value", hint: "Its value", get: (r) => (r[1] === undefined || r[1] === null ? "" : r[1]), cls: "ui-value" },
      { label: "Note", hint: "What it means", get: (r) => r[2] || "", cls: "ui-note" },
    ], rows.filter(Boolean), { cls: "ui-settings", key: (r) => r[4] || r[0] });
  }

  // Parameter table. rows: [{idn, name, value, unit, min, max, readonly, locked, lockHint, error, compare, command}]
  // opts: {write(row, text) async -> the row's new values (throws to refuse), compareLabel, run(row) async (command
  //        parameters get a Run button), page (default 100), filter, id}
  // Returns the element; el.uiUpdate(idn, values) refreshes one row unless the user is editing it.
  function paramTable(rows, opts = {}) {
    const byIdn = new Map(rows.map((r) => [r.idn, r]));
    const cols = [
      { label: "IDN", hint: "Parameter (IDN)", get: (r) => r.idn, cls: "ui-mono" },
      { label: "Name", hint: "Parameter name", get: (r) => r.name || "", cls: "ui-wrap" },
      { label: "Value", hint: "Value: edit and press Enter to keep it", get: (r) => valueCell(r), cls: "ui-value" },
    ];
    if (opts.compareLabel) cols.push({ label: opts.compareLabel, hint: `Value in ${opts.compareLabel}`, get: (r) => r.compare === undefined ? "–" : String(r.compare), cls: "ui-mono ui-compare" });
    cols.push(
      { label: "Unit", hint: "Unit", get: (r) => r.unit || "" },
      { label: "Min", hint: "Smallest value accepted", get: (r) => r.min ?? "", num: true },
      { label: "Max", hint: "Largest value accepted", get: (r) => r.max ?? "", num: true },
      { label: "", hint: "Write protection", get: (r) => (r.locked ? h("span", { class: "ui-lock", title: r.lockHint || "Write-protected now" }, icon("lock")) : h("span", { title: r.lockHint || "Writable" })), cls: "ui-lockcol" });
    function valueCell(r) {
      if (r.error) return h("span", { class: "ui-err-text", title: r.error }, r.error);
      if (r.command && opts.run) {
        const b = h("button", { class: "ui-btn", title: `Run command ${r.name || r.idn}` }, icon("play"), "Run");
        b.onclick = async () => { b.disabled = true; try { await opts.run(r); } catch (e) { if (typeof banner === "function") banner(`${r.idn}: ${e.message}`); } finally { b.disabled = false; } };
        return h("span", {}, b, " ", h("span", { class: "ui-ro" }, String(r.value ?? "")));
      }
      return field(r.value, async (text) => {
        const nv = await opts.write(r, text);
        if (nv && typeof nv === "object") Object.assign(r, nv);
      }, { readonly: r.readonly || !opts.write, hint: r.idn + (r.unit ? ` in ${r.unit}` : "") + (r.min !== undefined && r.min !== "" ? `, ${r.min} … ${r.max}` : "") });
    }
    const el = table(cols, rows, { key: (r) => r.idn, page: opts.page === undefined ? 100 : opts.page, filter: opts.filter, id: opts.id, cls: "ui-params", empty: opts.empty });
    el.uiUpdate = (idn, values) => {
      const r = byIdn.get(idn);
      if (!r) return;
      const tr = el.querySelector(`tr[data-key="${CSS.escape(idn)}"]`);
      if (tr && busy(tr)) return;                      // don't overwrite what the user is typing
      Object.assign(r, values);
      if (!tr) return;
      const fresh = h("tr", { "data-key": idn }, cols.map((c) => h("td", { class: [c.cls, c.num ? "ui-num" : null].filter(Boolean).join(" ") || null }, c.get(r))));
      tr.replaceWith(fresh);
    };
    return el;
  }

  // ---------- folding sections ----------
  // section(title, body, {key (remembers open/closed), count, open (default true), buttons: [Node]})
  function section(title, body, opts = {}) {
    const key = opts.key || (typeof title === "string" ? title : null);
    const closed = new Set(store.get("closed", []));
    const d = h("details", { class: "ui-sec", "data-sec": key });
    d.open = key && closed.has(key) ? false : opts.open !== false;
    d.appendChild(h("summary", { title: "Click to fold or unfold" }, h("span", { class: "ui-sec-title" }, title),
      opts.count !== undefined ? h("span", { class: "ui-count" }, String(opts.count)) : null,
      opts.buttons ? h("span", { class: "ui-sec-btns", onclick: (ev) => ev.stopPropagation() }, opts.buttons) : null));
    d.appendChild(h("div", { class: "ui-sec-body" }, body));
    d.addEventListener("toggle", () => {
      if (!key) return;
      const s = new Set(store.get("closed", []));
      if (d.open) s.delete(key); else s.add(key);
      store.set("closed", [...s]);
    });
    return d;
  }
  const foldAll = (root, open) => (root || document).querySelectorAll("details.ui-sec").forEach((d) => { if (d.open !== open) d.open = open; });

  // ---------- side panel tree ----------
  // tree(host, {nodes, selected, onSelect(node), storeKey})
  //   node: {id, label, sub, count, hint, dot ("ok" | "warn" | "err"), flags: [{text, kind ("edited"|"warn"|"err"|""), hint}],
  //          children: [node] | fill: async () => [node], select: false (only folds)}
  // returns {render(nodes), select(id), open(id)}; open nodes are remembered
  function tree(host, opts) {
    const skey = "tree." + (opts.storeKey || "main");
    const open = new Set(store.get(skey, opts.defaultOpen || []));
    let nodes = opts.nodes || [], selected = opts.selected || null;
    const filled = new Map();
    host.classList.add("ui-tree");
    function save() { store.set(skey, [...open]); }
    function item(n, depth) {
      const kids = n.children || filled.get(n.id);
      const canOpen = !!(n.children && n.children.length) || !!n.fill;
      const isOpen = canOpen && open.has(n.id);
      const tw = h("span", { class: "ui-twisty", title: canOpen ? (isOpen ? "Fold" : "Unfold") : null }, canOpen ? (isOpen ? "▼" : "▶") : "");
      const row = h("div", { class: "ui-node" + (n.id === selected ? " ui-sel" : ""), title: n.hint || n.label, "data-id": n.id, style: `padding-left:${8 + 16 * depth}px` },
        tw,
        n.dot ? h("span", { class: "ui-dot ui-dot-" + n.dot, title: { ok: "OK", warn: "Warning", err: "Error" }[n.dot] || n.dot }) : null,
        h("span", { class: "ui-label" }, n.label),
        n.sub ? h("span", { class: "ui-sub" }, n.sub) : null,
        (n.flags || []).map((f) => h("span", { class: "ui-flag" + (f.kind ? " ui-flag-" + f.kind : ""), title: f.hint || f.text }, f.text)),
        n.count !== undefined && n.count !== null ? h("span", { class: "ui-count", title: "Number of items" }, String(n.count)) : null);
      tw.addEventListener("click", (ev) => { ev.stopPropagation(); toggle(n); });
      row.addEventListener("click", () => {
        if (n.select === false) toggle(n);
        else { if (canOpen && !isOpen) toggle(n, true); choose(n); }
      });
      const li = h("li", {}, row);
      if (isOpen && kids) li.appendChild(h("ul", {}, kids.map((c) => item(c, depth + 1))));
      return li;
    }
    async function toggle(n, force) {
      const want = force === undefined ? !open.has(n.id) : force;
      if (want && n.fill && !n.children && !filled.has(n.id)) {
        try { filled.set(n.id, await n.fill()); } catch (e) { filled.set(n.id, []); if (typeof banner === "function") banner(e.message); }
      }
      if (want) open.add(n.id); else open.delete(n.id);
      save();
      draw();
    }
    function choose(n) {
      selected = n.id;
      draw();
      if (opts.onSelect) opts.onSelect(n);
    }
    function draw() {
      const top = host.scrollTop;
      host.replaceChildren(h("ul", {}, nodes.map((n) => item(n, 0))));
      host.scrollTop = top;
    }
    const find = (list, id, path = []) => {
      for (const n of list || []) {
        if (n.id === id) return [...path, n];
        const r = find(n.children || filled.get(n.id), id, [...path, n]);
        if (r) return r;
      }
      return null;
    };
    draw();
    return {
      render(list) { nodes = list; draw(); },
      select(id, notify) {                     // mark a node (and unfold its parents) without or with onSelect
        const p = find(nodes, id);
        selected = id;
        if (p) for (const n of p.slice(0, -1)) open.add(n.id);
        save(); draw();
        const row = host.querySelector(`[data-id="${CSS.escape(String(id))}"]`);
        if (row) row.scrollIntoView({ block: "nearest" });
        if (notify && p && opts.onSelect) opts.onSelect(p[p.length - 1]);
      },
      open(id, state = true) { const p = find(nodes, id); if (p) toggle(p[p.length - 1], state); },
      get selected() { return selected; },
    };
  }

  // ---------- back button + page title ----------
  // nav({back: button, title: element, show(route) -> title (may be async)}); routes are plain objects
  function nav(opts) {
    const stack = [];
    let cur = null;
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    async function show(route) {
      cur = route;
      const t = await opts.show(route);
      if (opts.title && t !== undefined) { opts.title.textContent = t; opts.title.title = t; }
      if (opts.back) {
        opts.back.disabled = !stack.length;
        opts.back.title = stack.length ? "Back to the page before" : "Nothing opened before";
      }
    }
    if (opts.back) opts.back.addEventListener("click", () => n.back());
    const n = {
      go(route) { if (cur && !same(cur, route)) { stack.push(cur); if (stack.length > 100) stack.shift(); } return show(route); },
      replace(route) { return show(route); },             // same page with other details (focus, tab): no back step
      back() { if (stack.length) return show(stack.pop()); },
      reset() { stack.length = 0; },
      get current() { return cur; },
    };
    return n;
  }

  // ---------- search ----------
  // search(input, {onQuery(q) (async), onClear(), delay}): debounced; Esc clears; clearing calls onClear
  function search(input, opts) {
    let timer = null, last = "";
    const fire = async () => {
      const q = input.value.trim();
      if (q === last) return;
      last = q;
      if (!q) { if (opts.onClear) opts.onClear(); return; }
      try { await opts.onQuery(q); } catch (e) { if (typeof banner === "function") banner("Search: " + e.message); }
    };
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(fire, opts.delay === undefined ? 300 : opts.delay); });
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") { input.value = ""; clearTimeout(timer); fire(); }
      if (ev.key === "Enter") { clearTimeout(timer); fire(); }
    });
    return { clear() { input.value = ""; clearTimeout(timer); fire(); }, get query() { return last; } };
  }
  function searchCard(opts = {}) {
    return h("label", { class: "ui-search" + (opts.small ? " ui-search-small" : ""), title: opts.hint || "Search" },
      icon("search"), h("input", { type: "search", id: opts.id, placeholder: opts.placeholder || "Search", autocomplete: "off", spellcheck: "false" }));
  }

  // ---------- changes kept before one commit ----------
  // changes({button, badge, onChange(list), what: "change"}) -> {add({label, group, undo: async fn}), undo(id), discardAll(),
  //          table(), list, count, clear()}
  //   undoing a change also undoes the later changes of the same group (e.g. the same file), after asking
  function changes(opts = {}) {
    let list = [], seq = 0;
    function update() {
      const n = list.length;
      if (opts.badge) { opts.badge.textContent = n ? String(n) : ""; opts.badge.hidden = !n; }
      if (opts.button) opts.button.disabled = !n;
      if (opts.onChange) opts.onChange(list);
    }
    window.addEventListener("beforeunload", (ev) => { if (list.length) { ev.preventDefault(); ev.returnValue = ""; } });
    const api_ = {
      add(c) { const e = { id: ++seq, time: new Date(), ...c }; list.push(e); update(); return e; },
      async undo(id) {
        const i = list.findIndex((c) => c.id === id);
        if (i < 0) return false;
        const c = list[i];
        const later = list.filter((x, j) => j > i && c.group !== undefined && x.group === c.group);
        if (later.length && !confirm(`Undoing this also undoes ${later.length} later change${later.length === 1 ? "" : "s"} of ${c.group}. Go on?`)) return false;
        for (const x of [...later].reverse()) if (x.undo) await x.undo();
        if (c.undo) await c.undo();
        list = list.filter((x) => x !== c && !later.includes(x));
        update();
        return true;
      },
      async discardAll(ask = true) {
        if (!list.length || (ask && !confirm(`Throw away all ${list.length} changes?`))) return false;
        for (const x of [...list].reverse()) if (x.undo) await x.undo();
        list = []; update();
        return true;
      },
      clear() { list = []; update(); },                  // after a successful commit
      table() {
        return table([
          { label: "Change", hint: "What was changed", get: (c) => c.label, cls: "ui-wrap" },
          { label: "Group", hint: "Where (e.g. the file)", get: (c) => c.group || "" },
          { label: "Time", hint: "When it was kept", get: (c) => c.time.toLocaleTimeString() },
          { label: "", hint: "Undo", get: (c) => h("button", { class: "ui-icon-btn", title: "Undo this change", "aria-label": "Undo", onclick: () => api_.undo(c.id) }, icon("undo")) },
        ], list, { key: (c) => "c" + c.id, empty: "Nothing changed yet", id: opts.tableId });
      },
      get list() { return list.slice(); },
      get count() { return list.length; },
    };
    update();
    return api_;
  }

  // the one question before something changes a device: what is written and what happens then
  const confirmWrite = (what, consequence) => confirm(`${what}\n\n${consequence ? consequence + "\n\n" : ""}Write it now?`);

  return {
    h, icon, field, flash, busy, table, settings, paramTable, section, tree, nav, search, searchCard, changes, confirmWrite,
    expandAll: (root) => foldAll(root, true), collapseAll: (root) => foldAll(root, false),
    get kept() { return kept; }, set kept(k) { kept = k; },
  };
})();
