/* Metrological Analysis — web client of the server API (see server/app.py and webapp/handler.py).
   No framework, no build step. All text reaches the page through textContent, never as HTML. */
"use strict";

// ---------------------------------------------------------------- constants (mirror of common/params.py)
const SPECIES_RE = /^[A-Z][a-z]{2,}( [a-z]{2,}){1,2}$/;
const SPECIES_EXAMPLE = "Pinna nobilis";
const KIND_AREA = { photos: "photos", stereo: "stereo", video: "videos", stereo_video: "stereo_videos", model: "models", dataset: "datasets" };
const KIND_LABEL = { photos: "Photos", stereo: "Stereo photos", video: "Videos", stereo_video: "Stereo videos", model: "YOLO models", dataset: "Training datasets" };
const KINDS = ["photos", "stereo", "video", "stereo_video", "model", "dataset"];
const IMAGE_EXT = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"];
const VIDEO_EXT = [".mp4", ".avi", ".mov", ".mkv"];
const MODEL_EXT = [".pt", ".onnx"];
// a .pt can run code when loaded: the server loads it only from the library (approved); elsewhere only .onnx
const modelOk = (area, name) => (area === "models" && !String(name).startsWith("_pending/") ? MODEL_EXT : [".onnx"]).includes(ext(name));
const STEREO_SIDES = ["lx", "rx"];
const PENDING = "_pending";
const LANG_NAMES = { en: "English", it: "Italiano", es: "Español", de: "Deutsch", fr: "Français", zh: "中文", ja: "日本語" };
const ROLE_ADMIN = "server";

// ---------------------------------------------------------------- state
const store = {   // per-browser conveniences only (session token, last choices); private windows may refuse it
  get(k) { try { return localStorage.getItem("am." + k); } catch (e) { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem("am." + k) : localStorage.setItem("am." + k, v); } catch (e) { /* private mode */ } },
};
const S = {
  token: store.get("token"),
  user: null,
  health: null,
  lang: store.get("lang") || (navigator.language || "en").slice(0, 2),
  strings: {},
  urls: [],                 // blob: URLs of the current view (revoked when it changes)
  timers: [],               // intervals of the current view
  view: 0,                  // increases at every navigation: late answers of an old view are ignored
};
if (!LANG_NAMES[S.lang]) S.lang = "en";


// ---------------------------------------------------------------- translation
function t(text, params) {
  let s = S.strings[text] || text;
  if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m));
  return s;
}
async function loadLanguage(lang) {
  S.lang = lang; store.set("lang", lang);
  document.documentElement.lang = lang;
  S.strings = {};
  if (lang !== "en") {
    try { S.strings = (await api("GET", "/api/i18n", { query: { lang }, anon: true })).strings || {}; } catch (e) { /* English */ }
  }
  document.querySelectorAll("[data-t]").forEach((n) => { n.dataset.en = n.dataset.en || n.textContent; n.textContent = t(n.dataset.en); });
  document.title = t("Metrological Analysis");
}

// ---------------------------------------------------------------- API
class ApiError extends Error {
  constructor(status, payload) {
    const p = payload || {};
    super(p.key ? t(p.key, p.params) : (p.error || t("Connection to the server failed.")));
    this.status = status; this.payload = p;
  }
}
async function api(method, path, opt = {}) {
  const q = opt.query ? "?" + new URLSearchParams(Object.entries(opt.query).filter(([, v]) => v != null && v !== "")) : "";
  const headers = {};
  if (S.token && !opt.anon) headers.Authorization = "Bearer " + S.token;
  let body;
  if (opt.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opt.json); }
  let res;
  try { res = await fetch(path + q, { method, headers, body, cache: "no-store" }); }
  catch (e) { throw new ApiError(0, null); }
  if (opt.blob && res.ok) return res.blob();
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
  if (!res.ok) {
    if (res.status === 401 && !opt.anon && S.token) { signOut(true); }
    throw new ApiError(res.status, data);
  }
  return data;
}
function uploadFile(area, rel, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", "/api/files/upload?" + new URLSearchParams({ area, path: rel }));
    xhr.setRequestHeader("Authorization", "Bearer " + S.token);
    xhr.upload.onprogress = (e) => onProgress && onProgress(e.loaded);
    xhr.onload = () => {
      let data = null; try { data = JSON.parse(xhr.responseText); } catch (e) { /* empty */ }
      xhr.status >= 200 && xhr.status < 300 ? resolve(data) : reject(new ApiError(xhr.status, data));
    };
    xhr.onerror = () => reject(new ApiError(0, null));
    xhr.send(file);
  });
}
async function fileBlobUrl(area, path) {
  const blob = await api("GET", "/api/files/download", { query: { area, path }, blob: true });
  const url = URL.createObjectURL(blob); S.urls.push(url); return url;
}
async function saveBlob(blobPromise, name) {
  const blob = await blobPromise;
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// ---------------------------------------------------------------- DOM helpers
function h(tag, attrs, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k in n && typeof v !== "string") n[k] = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) n.append(c instanceof Node ? c : String(c));
  return n;
}
const $ = (sel, root = document) => root.querySelector(sel);
function toast(msg, bad) {
  const m = h("div", { class: "msg" + (bad ? " bad" : ""), text: msg });
  $("#toast").append(m); setTimeout(() => m.remove(), bad ? 6000 : 3000);
}
function fail(e) { console.error(e); toast(e.message || String(e), true); }
function fmtBytes(n) {
  if (n == null) return "";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(1) : n) + " " + u[i];
}
function fmtDate(ts) { return ts ? new Date(ts * 1000).toLocaleString(S.lang) : "—"; }
function fmtNum(v, d = 1) { return v == null ? "—" : Number(v).toFixed(d); }
function ext(name) { const i = name.lastIndexOf("."); return i < 0 ? "" : name.slice(i).toLowerCase(); }
function isImage(name) { return IMAGE_EXT.includes(ext(name)); }
function joinPath(a, b) { return a ? a + "/" + b : b; }
function parentPath(p) { const i = p.lastIndexOf("/"); return i < 0 ? "" : p.slice(0, i); }
function baseName(p) { return p.slice(p.lastIndexOf("/") + 1); }
function isAdmin() { return S.user && S.user.role === ROLE_ADMIN; }
function statusBadge(st) {
  const cls = { approved: "ok", done: "ok", pending: "warn", queued: "warn", running: "info", rejected: "bad", error: "bad", cancelled: "" }[st] || "";
  return h("span", { class: "badge " + cls, text: t(st) });
}
// who can see an approved item: everyone, the uploader and one work group, or the uploader only
function visLabel(r) {
  if (r.visibility === "private") return t("Only {name}", { name: r.uploader || r.username || t("me") });
  if (r.visibility === "group") return t("Group {name}", { name: r.vis_group || "?" });
  return t("All users");
}
function visBadge(r) { return h("span", { class: "badge " + (r.visibility === "public" || !r.visibility ? "" : "info"), text: visLabel(r) }); }
function visSelect(groups, current) {
  const s = h("select", {}, h("option", { value: "public", text: t("All users") }), h("option", { value: "private", text: t("Only me") }),
    groups.map((g) => h("option", { value: "group:" + g.name, text: t("Me and group {name}", { name: g.name }) })));
  if (current) s.value = current.visibility === "group" ? "group:" + current.vis_group : current.visibility || "public";
  return s;
}
function parseVis(v) { return v.startsWith("group:") ? { visibility: "group", vis_group: v.slice(6) } : { visibility: v, vis_group: "" }; }
async function myGroups() { return api("GET", "/api/groups").then((r) => r.groups.filter((g) => g.mine)).catch(() => []); }

function table(columns, rows, opt = {}) {
  if (!rows.length) return h("div", { class: "card empty", text: opt.empty || t("Nothing here yet.") });
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, columns.map((c) => h("th", { class: c.num ? "num" : "", text: c.title })))),
    h("tbody", {}, rows.map((r) => {
      const tr = h("tr", { class: opt.onrow ? "clickable" : "" }, columns.map((c) => {
        const v = c.render ? c.render(r) : r[c.key];
        return h("td", { class: c.num ? "num" : "" }, v == null ? "—" : v);
      }));
      if (opt.onrow) tr.addEventListener("click", (e) => { if (!e.target.closest("button,a,input,select")) opt.onrow(r, tr); });
      return tr;
    }))));
}
function dialog(title, content, opt = {}) {
  const d = h("dialog", {},
    h("div", { class: "head" }, h("strong", { text: title }), h("div", { class: "row" }, opt.actions || [], h("button", { class: "small", type: "button", onclick: () => d.close(), text: t("Close") }))),
    h("div", { class: "body" }, content));
  d.addEventListener("close", () => { d.remove(); opt.onclose && opt.onclose(); });
  document.body.append(d); d.showModal(); return d;
}
function field(label, input, hint) { return h("div", {}, h("label", { text: label }), input, hint ? h("div", { class: "hint", text: hint }) : null); }
function busy(button, promise) {
  button.disabled = true;
  return Promise.resolve(promise).finally(() => { button.disabled = false; });
}

// ---------------------------------------------------------------- router
const ROUTES = {};
function route(name, render, opt = {}) { ROUTES[name] = { render, ...opt }; }
function go(hash) { if (location.hash === hash) render(); else location.hash = hash; }
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, qs] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  return { name: parts[0] || "", args: parts.slice(1), q: Object.fromEntries(new URLSearchParams(qs || "")) };
}
function link(hash, text, cls) { return h("a", { href: hash, class: cls, text }); }
function hashFor(name, args = [], q) {
  const p = "#/" + [name, ...args.map(encodeURIComponent)].join("/");
  return q ? p + "?" + new URLSearchParams(q) : p;
}

async function render() {
  S.urls.forEach((u) => URL.revokeObjectURL(u)); S.urls = [];
  S.timers.forEach(clearInterval); S.timers = [];
  const view = ++S.view;
  const { name, args, q } = parseHash();
  if (!S.user && name !== "login") return go("#/login");
  const r = ROUTES[name] || (S.user ? null : ROUTES.login);
  if (!r) return go("#/library");
  if (r.admin && !isAdmin()) return go("#/library");
  renderNav(name);
  $("#nav").classList.remove("open");
  const main = $("#view");
  main.replaceChildren(h("p", { class: "muted", text: t("Loading...") }));
  try {
    const content = await r.render(args, q, () => view === S.view);
    if (view !== S.view) return;
    main.replaceChildren(...[content].flat().filter(Boolean));
  } catch (e) {
    if (view !== S.view) return;
    main.replaceChildren(h("div", { class: "notice bad", text: e.message || String(e) }));
  }
}
function renderNav(active) {
  const top = $("#topbar");
  top.hidden = !S.user;
  if (!S.user) return;
  const items = [["library", "Library"], ["analysis", "Analysis"], ["enhance", "Enhance"], ["uploads", "Uploads"], ["mine", "My folder"], ["groups", "Groups"]];
  const admin = [["review", "Review"], ["users", "Users"], ["server", "Server"]];
  const nav = $("#nav");
  nav.replaceChildren(...items.map(([k, l]) => link("#/" + k, t(l), k === active ? "active" : "")));
  if (isAdmin()) nav.append(h("span", { class: "sep" }), ...admin.map(([k, l]) => link("#/" + k, t(l), k === active ? "active" : "")));
  $("#me").textContent = S.user.full_name || S.user.username;
}

// ---------------------------------------------------------------- session
async function signIn(token, user) {
  S.token = token; S.user = user; store.set("token", token);
  go(sessionStorage.getItem("am.next") || "#/library");
  sessionStorage.removeItem("am.next");
}
function signOut(expired) {
  if (S.token && !expired) api("POST", "/api/logout").catch(() => {});
  S.token = null; S.user = null; store.set("token", null);
  if (expired) { toast(t("Your session has expired: sign in again."), true); if (location.hash && !location.hash.startsWith("#/login")) sessionStorage.setItem("am.next", location.hash); }
  go("#/login");
}

// ================================================================= views
// ---------------------------------------------------------------- login
route("login", async () => {
  if (S.user) { setTimeout(() => go("#/library")); return []; }
  const health = S.health || {};
  let mode = "login";
  const user = h("input", { name: "username", autocomplete: "username", required: true });
  const pass = h("input", { name: "password", type: "password", autocomplete: "current-password", required: true });
  const pass2 = h("input", { type: "password", autocomplete: "new-password" });
  const email = h("input", { type: "email", autocomplete: "email" });
  const key = h("input", { type: "password", autocomplete: "off" });
  const keyRow = h("div", { hidden: true }, field(t("Access key"), key, t("Optional: only to become an administrator.")));
  const regRows = h("div", { hidden: true, class: "stack" }, field(t("Repeat the password"), pass2), field(t("E-mail (optional)"), email));
  const submit = h("button", { class: "primary", type: "submit", text: t("Sign in") });
  const err = h("div", { class: "notice bad", hidden: true });
  const switcher = h("button", { type: "button", class: "link", text: t("Create an account") });
  const form = h("form", { class: "card stack" },
    field(t("Username"), user), field(t("Password"), pass), regRows, keyRow, err,
    h("div", { class: "row spread" }, submit, h("button", { type: "button", class: "link", text: t("Access key"), onclick: () => { keyRow.hidden = !keyRow.hidden; } })));
  function setMode(m) {
    mode = m;
    regRows.hidden = m !== "register";
    pass.autocomplete = m === "register" ? "new-password" : "current-password";
    submit.textContent = t(m === "register" ? "Create account" : "Sign in");
    switcher.textContent = t(m === "register" ? "I already have an account" : "Create an account");
  }
  switcher.addEventListener("click", () => setMode(mode === "login" ? "register" : "login"));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault(); err.hidden = true; err.className = "notice bad";
    try {
      await busy(submit, (async () => {
        if (mode === "register") {
          if (pass.value !== pass2.value) throw new Error(t("The two passwords are different."));
          const r = await api("POST", "/api/register", { json: { username: user.value, password: pass.value, email: email.value, key: key.value }, anon: true });
          if (r.user && r.user.pending) {          // the server wants an administrator to enable new accounts
            setMode("login"); pass.value = ""; pass2.value = "";
            err.className = "notice info"; err.textContent = t("Account created. An administrator must approve it before you can sign in."); err.hidden = false;
            return;
          }
        }
        const r = await api("POST", "/api/login", { json: { username: user.value, password: pass.value, key: key.value }, anon: true });
        await signIn(r.token, r.user);
      })());
    } catch (e) { err.textContent = e.message; err.hidden = false; }
  });
  return h("div", { class: "login" },
    h("div", { class: "brand" }, h("img", { src: "icon.svg", alt: "", width: 32, height: 32 }), h("span", { text: t("Metrological Analysis") })),
    form,
    health.register !== false ? h("p", { class: "muted small" }, switcher) : h("p", { class: "muted small", text: t("Registration is disabled: ask an administrator for an account.") }),
    health.ok ? null : h("div", { class: "notice warn", text: t("The server is unreachable.") }));
});

// ---------------------------------------------------------------- library (catalog)
route("library", async (args) => {
  const kind = KINDS.includes(args[0]) ? args[0] : "stereo";
  const items = (await api("GET", "/api/catalog", { query: { kind } })).items;
  const area = KIND_AREA[kind];
  const tabs = h("div", { class: "tabs" }, KINDS.map((k) => h("button", { class: k === kind ? "active" : "", text: t(KIND_LABEL[k]), onclick: () => go("#/library/" + k) })));
  const cols = [
    { title: kind === "dataset" ? t("Dataset") : t("Species"), render: (r) => h("em", { text: kind === "dataset" ? baseName(r.path) : r.species }) },
    { title: t("Uploaded by"), key: "uploader" },
    { title: t("Approved by"), key: "approved_by" },
    { title: t("Date"), key: "date" },
  ];
  if (kind === "dataset") cols.push({ title: t("Classes"), render: (r) => (r.classes || []).join(", ") || "—" });
  if (kind !== "model") cols.push({ title: kind === "dataset" ? t("Images") : t("Files"), key: "items", num: true });
  cols.push({ title: t("Visible to"), render: (r) => visBadge(r) });
  cols.push({
    title: "", render: (r) => h("div", { class: "actions" },
      kind === "stereo" ? h("a", { class: "button small", href: hashFor("analysis", [], { sarea: area, spath: r.path }), text: t("Analyse") }) : null,
      kind === "model" ? h("a", { class: "button small", href: hashFor("analysis", [], { marea: area, mpath: r.path }), text: t("Use for analysis") }) : null,
      kind === "model" ? h("button", { class: "small", text: t("Download"), onclick: () => saveBlob(api("GET", "/api/files/download", { query: { area, path: r.path }, blob: true }), baseName(r.path)).catch(fail) }) : null),
  });
  return [
    h("div", { class: "row spread" }, h("div", {}, h("h1", { text: t("Library") }), h("p", { class: "muted", text: t("Approved material shared by everyone on the server.") })),
      h("a", { class: "button", href: hashFor("browse", [area]), text: t("Browse folders") })),
    tabs,
    table(cols, items, { empty: t("No approved items of this kind yet."), onrow: (r) => go(hashFor("browse", [area], { path: kind === "model" ? parentPath(r.path) : r.path })) }),
  ];
});

// ---------------------------------------------------------------- folder browser (any area, also "mine")
async function thumbLoader(container, area) {
  // loads the images that become visible, four at a time
  const queue = []; let running = 0;
  const pump = () => {
    while (running < 4 && queue.length) {
      const { img, path } = queue.shift(); running++;
      fileBlobUrl(area, path).then((u) => { img.replaceChildren(h("img", { src: u, alt: "" })); })
        .catch(() => { img.textContent = "×"; }).finally(() => { running--; pump(); });
    }
  };
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { io.unobserve(e.target); queue.push({ img: e.target, path: e.target.dataset.path }); }
    pump();
  }, { rootMargin: "200px" });
  container.querySelectorAll(".img[data-path]").forEach((n) => io.observe(n));
}
function showImage(area, path, names, index) {
  const img = h("div", { class: "viewer" }, h("div", { class: "placeholder", text: t("Loading...") }));
  let i = index; let url = null;
  const cap = h("span", { class: "muted small" });
  const load = async () => {
    cap.textContent = `${names[i]} (${i + 1}/${names.length})`;
    if (url) URL.revokeObjectURL(url);
    try {
      const blob = await api("GET", "/api/files/download", { query: { area, path: joinPath(path, names[i]) }, blob: true });
      url = URL.createObjectURL(blob); img.replaceChildren(h("img", { src: url, alt: names[i] }));
    } catch (e) { img.replaceChildren(h("div", { class: "placeholder", text: e.message })); }
  };
  const prev = h("button", { class: "small", text: "←", onclick: () => { i = (i - 1 + names.length) % names.length; load(); } });
  const next = h("button", { class: "small", text: "→", onclick: () => { i = (i + 1) % names.length; load(); } });
  const enh = h("button", { class: "small", text: t("Enhance"), onclick: () => { d.close(); go(hashFor("enhance", [], { area, path: joinPath(path, names[i]) })); } });
  const d = dialog(names[i], h("div", { class: "stack" }, img, h("div", { class: "row spread" }, prev, cap, next)), { onclose: () => url && URL.revokeObjectURL(url), actions: [enh] });
  d.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft") prev.click(); if (e.key === "ArrowRight") next.click(); });
  load();
}
async function showText(area, path) {
  const blob = await api("GET", "/api/files/download", { query: { area, path }, blob: true });
  const text = await blob.slice(0, 200000).text();
  dialog(baseName(path), h("pre", { text }));
}

route("browse", async (args, q) => {
  const area = args[0] || "stereo";
  const path = q.path || "";
  const listing = await api("GET", "/api/files", { query: { area, path } });
  const entries = listing.entries;
  const mine = area === "mine";
  const group = area === "groups";
  const own = mine || (group && path !== "");             // personal folder, or inside one of my group folders
  const canEdit = own || isAdmin();
  const here = (p) => hashFor(mine ? "mine" : "browse", mine ? [] : [area], p ? { path: p } : null);

  const crumbs = h("div", { class: "crumbs" }, link(here(""), mine ? t("My folder") : group ? t("Group folders") : t(KIND_LABEL[Object.keys(KIND_AREA).find((k) => KIND_AREA[k] === area)] || area)));
  let acc = "";
  for (const part of path.split("/").filter(Boolean)) {
    acc = joinPath(acc, part);
    crumbs.append(h("span", { class: "sep", text: "/" }), link(here(acc), part === PENDING ? t("Waiting for review") : part));
  }
  const dirs = entries.filter((e) => e.type === "dir");
  const files = entries.filter((e) => e.type === "file");
  const images = files.filter((f) => isImage(f.name));
  const others = files.filter((f) => !isImage(f.name));
  const names = new Set(dirs.map((d) => d.name.toLowerCase()));
  const stereo = STEREO_SIDES.every((s) => names.has(s));

  const toolbar = h("div", { class: "row" });
  if (stereo) toolbar.append(h("a", { class: "button primary", href: hashFor("analysis", [], { sarea: area, spath: path }), text: t("Analyse this stereo folder") }));
  const hasMedia = stereo || files.some((f) => isImage(f.name) || VIDEO_EXT.includes(ext(f.name)));
  if (hasMedia && path && !(group && !path.includes("/"))) toolbar.append(h("a", { class: "button", href: hashFor("enhance", [], { area, path }), text: t("Enhance this folder") }));
  if (own) {
    const input = h("input", { type: "file", multiple: true, hidden: true, onchange: () => uploadInto(area, path, [...input.files]) });
    const folderInput = h("input", { type: "file", multiple: true, hidden: true, webkitdirectory: true, onchange: () => uploadInto(area, path, [...folderInput.files], true) });
    toolbar.append(input, folderInput,
      h("button", { text: t("Upload files"), onclick: () => input.click() }),
      h("button", { text: t("Upload a folder"), onclick: () => folderInput.click() }),
      h("button", { text: t("New folder"), onclick: async () => {
        const name = prompt(t("Folder name"));
        if (!name) return;
        try { await api("POST", "/api/files/mkdir", { query: { area, path: joinPath(path, name) } }); render(); } catch (e) { fail(e); }
      } }));
  }
  const del = (e) => async () => {
    if (!confirm(t("Delete {name}?", { name: e.name }))) return;
    try { await api("DELETE", "/api/files", { query: { area, path: joinPath(path, e.name) } }); toast(t("Deleted.")); render(); } catch (err) { fail(err); }
  };

  const out = [h("div", { class: "row spread" }, h("h1", { text: mine ? t("My folder") : t("Server folders") }), toolbar), crumbs];
  if (mine) {
    const u = await api("GET", "/api/usage").catch(() => null);
    if (u) {
      const bar = h("div", { class: "progress" }, h("div", {})); bar.firstChild.style.width = Math.min(100, (100 * u.used) / Math.max(1, u.quota)) + "%";
      out.push(h("div", { class: "card" }, h("div", { class: "row spread small" }, h("span", { text: t("Space used") }), h("span", { text: `${fmtBytes(u.used)} / ${fmtBytes(u.quota)}` })), bar,
        h("p", { class: "hint", text: t("Your private space on the server. To analyse your own stereo captures, upload a folder with lx and rx subfolders here.") })));
    }
  }
  if (group && !path) out.push(h("p", { class: "muted", text: t("A shared folder for each of your work groups: every member can read and upload, and what the members send waits for an administrator of the group.") }));
  if (!entries.length) out.push(h("div", { class: "card empty", text: group && !path ? t("You are not in any group yet.") : t("This folder is empty.") }));
  if (dirs.length) out.push(table([
    { title: t("Folder"), render: (e) => link(here(joinPath(path, e.name)), e.name === PENDING ? t("Waiting for review") : e.name) },
    { title: t("Modified"), render: (e) => (e.mtime ? fmtDate(e.mtime) : "—") },
    { title: "", render: (e) => h("div", { class: "actions" }, canEdit && e.name !== PENDING && !(group && !path) ? h("button", { class: "small danger", text: t("Delete"), onclick: del(e) }) : null) },
  ], dirs, { onrow: (e) => go(here(joinPath(path, e.name))) }));
  if (images.length) {
    const grid = h("div", { class: "thumbs" }, images.map((f, i) => h("button", { class: "thumb", type: "button", onclick: () => showImage(area, path, images.map((x) => x.name), i) },
      h("div", { class: "img", "data-path": joinPath(path, f.name), text: "…" }), h("div", { class: "cap", text: f.name }))));
    out.push(h("h2", { text: t("Images") + ` (${images.length})` }), grid);
    setTimeout(() => thumbLoader(grid, area));
  }
  if (others.length) out.push(h("h2", { text: t("Files") }), table([
    { title: t("Name"), key: "name" },
    { title: t("Size"), render: (e) => fmtBytes(e.size), num: true },
    { title: t("Modified"), render: (e) => fmtDate(e.mtime) },
    { title: "", render: (e) => h("div", { class: "actions" },
      modelOk(area, joinPath(path, e.name)) ? h("a", { class: "button small", href: hashFor("analysis", [], { marea: area, mpath: joinPath(path, e.name) }), text: t("Use for analysis") }) : null,
      VIDEO_EXT.includes(ext(e.name)) ? h("a", { class: "button small", href: hashFor("enhance", [], { area, path: joinPath(path, e.name) }), text: t("Enhance") }) : null,
      [".txt", ".yaml", ".yml", ".json", ".csv", ".md"].includes(ext(e.name)) && e.size < 2e6 ? h("button", { class: "small", text: t("View"), onclick: () => showText(area, joinPath(path, e.name)).catch(fail) }) : null,
      h("button", { class: "small", text: t("Download"), onclick: () => saveBlob(api("GET", "/api/files/download", { query: { area, path: joinPath(path, e.name) }, blob: true }), e.name).catch(fail) }),
      canEdit ? h("button", { class: "small danger", text: t("Delete"), onclick: del(e) }) : null) },
  ], others));
  return out;
});
route("mine", (args, q, alive) => ROUTES.browse.render(["mine"], q, alive));

async function uploadInto(area, path, files, keepFolders) {
  const plan = files.map((f) => ({ file: f, rel: joinPath(path, keepFolders && f.webkitRelativePath ? f.webkitRelativePath : f.name) }));
  try { await runUploads(area, plan); toast(t("Upload complete.")); } catch (e) { fail(e); }
  render();
}
async function runUploads(area, plan, bar, label) {
  // one file after the other, with a progress bar (a toast when none is given)
  const total = plan.reduce((s, p) => s + p.file.size, 0) || 1;
  let done = 0;
  let own = null;
  if (!bar) {
    own = h("div", { class: "msg" }, h("div", { text: t("Uploading...") }), h("div", { class: "progress" }, h("div", {})));
    $("#toast").append(own); bar = own.querySelector(".progress > div"); label = own.firstChild;
  }
  try {
    for (const [i, p] of plan.entries()) {
      if (label) label.textContent = t("Uploading {i} of {n}: {name}", { i: i + 1, n: plan.length, name: p.file.name });
      await uploadFile(area, p.rel, p.file, (loaded) => { bar.style.width = (100 * (done + loaded)) / total + "%"; });
      done += p.file.size; bar.style.width = (100 * done) / total + "%";
    }
  } finally { if (own) own.remove(); }
}

// ---------------------------------------------------------------- uploads (send material for review)
route("uploads", async () => {
  const kind = h("select", {}, KINDS.map((k) => h("option", { value: k, text: t(KIND_LABEL[k]) })));
  kind.value = store.get("upload.kind") || "stereo";
  const species = h("input", { placeholder: SPECIES_EXAMPLE, autocomplete: "off" });
  const dsName = h("input", { placeholder: "my_dataset", autocomplete: "off" });
  const files = h("input", { type: "file", multiple: true });
  const help = h("div", { class: "notice info" });
  const summary = h("p", { class: "muted small" });
  const send = h("button", { class: "primary", type: "submit", text: t("Upload and send for review") });
  const bar = h("div", { class: "progress", hidden: true }, h("div", {}));
  const status = h("div", { class: "small muted" });
  const speciesRow = field(t("Species (scientific name)"), species, t("Genus species, for example {example}.", { example: SPECIES_EXAMPLE }));
  const nameRow = field(t("Dataset name"), dsName, t("Letters, numbers, - and _."));
  const groups = await myGroups();
  const vis = visSelect(groups, null);
  vis.value = store.get("upload.vis") || "public";
  if (!vis.value) vis.value = "public";
  vis.addEventListener("change", () => store.set("upload.vis", vis.value));
  let plan = [];

  function configure() {
    const k = kind.value; store.set("upload.kind", k);
    const folder = ["stereo", "stereo_video", "dataset"].includes(k);
    files.webkitdirectory = folder; files.multiple = k !== "model"; files.value = "";
    files.accept = k === "model" ? MODEL_EXT.concat([".json"]).join(",") : k === "photos" ? IMAGE_EXT.concat([".txt"]).join(",") : k === "video" ? VIDEO_EXT.concat([".txt"]).join(",") : "";
    speciesRow.hidden = k === "dataset"; nameRow.hidden = k !== "dataset";
    help.textContent = {
      photos: t("Choose the photos (and, if you have them, their YOLO .txt labels and classes.txt)."),
      video: t("Choose the videos (and, if you have them, their .txt labels)."),
      stereo: t("Choose a folder that contains the lx and rx subfolders, with photos of the same names in both."),
      stereo_video: t("Choose a folder that contains the lx and rx subfolders, each with its video."),
      model: t("Choose the YOLO model (.pt or .onnx). You may add a .json file with the same name describing it."),
      dataset: t("Choose the dataset folder: images, labels and data.yaml."),
    }[k];
    plan = []; summary.textContent = "";
  }
  function build() {
    const k = kind.value; const sp = species.value.trim(); const name = dsName.value.trim();
    const list = [...files.files]; const out = []; let skipped = 0;
    for (const f of list) {
      const parts = (f.webkitRelativePath || f.name).split("/");
      if (k === "stereo" || k === "stereo_video") {
        const i = parts.findIndex((p) => STEREO_SIDES.includes(p.toLowerCase()));
        if (i < 0 || i !== parts.length - 2) { skipped++; continue; }
        out.push({ file: f, rel: `${sp}/${parts[i].toLowerCase()}/${f.name}` });
      } else if (k === "dataset") {
        out.push({ file: f, rel: `${name}/${parts.slice(1).join("/")}` });
      } else {
        out.push({ file: f, rel: `${sp}/${f.name}` });
      }
    }
    return { out, skipped };
  }
  function refresh() {
    const { out, skipped } = build(); plan = out;
    summary.textContent = out.length ? t("{n} files, {size}", { n: out.length, size: fmtBytes(out.reduce((s, p) => s + p.file.size, 0)) }) + (skipped ? " · " + t("{n} files outside lx/rx are ignored", { n: skipped }) : "") : "";
  }
  kind.addEventListener("change", configure); files.addEventListener("change", refresh);
  species.addEventListener("input", refresh); dsName.addEventListener("input", refresh);
  configure();

  const form = h("form", { class: "card stack" }, h("div", { class: "grid" }, field(t("What are you sending?"), kind), speciesRow, nameRow, field(t("Who can see it once approved"), vis)), help,
    field(t("Files"), files), summary, bar, status, h("div", {}, send));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const k = kind.value; const sp = species.value.trim(); const name = dsName.value.trim();
    refresh();
    if (k !== "dataset" && !SPECIES_RE.test(sp)) return fail(new Error(t("Genus species, for example {example}.", { example: SPECIES_EXAMPLE })));
    if (k === "dataset" && !/^[A-Za-z0-9][A-Za-z0-9 _.-]{0,80}$/.test(name)) return fail(new Error(t("Letters, numbers, - and _.")));
    if (!plan.length) return fail(new Error(t("Choose the files to send.")));
    const models = plan.filter((p) => MODEL_EXT.includes(ext(p.file.name)));
    if (k === "model" && models.length !== 1) return fail(new Error(t("Choose the YOLO model (.pt or .onnx). You may add a .json file with the same name describing it.")));
    bar.hidden = false;
    try {
      await busy(send, (async () => {
        await runUploads(KIND_AREA[k], plan, bar.firstChild, status);
        status.textContent = t("Sending for review...");
        let r; const share = parseVis(vis.value);
        if (k === "dataset") r = await api("POST", "/api/datasets/submit", { json: { name, ...share } });
        else if (k === "model") r = await api("POST", "/api/models/submit", { json: { species: sp, file: models[0].file.name, ...share } });
        else r = await api("POST", "/api/species/submit", { json: { species: sp, kind: k, ...share } });
        toast(r.pending ? t("Sent: an administrator will review it.") : t("Published."));
        render();
      })());
    } catch (e) { status.textContent = ""; fail(e); }
  });

  const scope = store.get("upload.scope") === "groups" && groups.length ? "groups" : "mine";
  const subs = (await api("GET", "/api/species/submissions", { query: { include: scope === "groups" ? "groups" : null } })).submissions;
  const scopeSel = h("select", { onchange: (e) => { store.set("upload.scope", e.target.value); render(); } },
    h("option", { value: "mine", text: t("Mine") }), h("option", { value: "groups", text: t("Mine and my groups'") }));
  scopeSel.value = scope; scopeSel.style.width = "auto";
  const visCell = (r) => {
    if (r.username !== S.user.username && !isAdmin()) return visBadge(r);
    const sel = visSelect(groups, r);
    if (r.visibility === "group" && ![...sel.options].some((o) => o.value === "group:" + r.vis_group))
      sel.append(h("option", { value: "group:" + r.vis_group, text: t("Me and group {name}", { name: r.vis_group || "?" }) }));
    sel.value = r.visibility === "group" ? "group:" + r.vis_group : r.visibility;
    sel.style.width = "auto";
    sel.addEventListener("change", async () => {
      try { await api("PATCH", `/api/species/submissions/${r.id}`, { json: parseVis(sel.value) }); toast(t("Saved.")); } catch (e) { fail(e); render(); }
    });
    return sel;
  };
  return [
    h("h1", { text: t("Uploads") }),
    h("p", { class: "muted", text: t("Send photos, videos, models or datasets to the library. An administrator approves them first; then they are visible to whoever you chose: everyone, one of your groups, or only you.") }),
    form,
    h("div", { class: "row spread" }, h("h2", { text: t("Submissions") }), groups.length ? scopeSel : null),
    table([
      scope === "groups" || isAdmin() ? { title: t("Uploaded by"), key: "username" } : null,
      { title: t("Kind"), render: (r) => t(KIND_LABEL[r.kind] || r.kind) },
      { title: t("Species") + " / " + t("Name"), render: (r) => h("em", { text: r.species }) },
      { title: t("Files"), key: "photos", num: true },
      { title: t("Sent"), render: (r) => fmtDate(r.created) },
      { title: t("Status"), render: (r) => statusBadge(r.status) },
      { title: t("Reviewed by"), render: (r) => r.reviewed_by || "—" },
      { title: t("Visible to"), render: visCell },
    ].filter(Boolean), subs, { empty: t("You have not sent anything yet.") }),
  ];
});

// ---------------------------------------------------------------- analysis
route("analysis", async (args, q, alive) => {
  const status = await api("GET", "/api/analysis/status");
  const defaults = status.defaults || { baseline_mm: 60, focal_length_px: 1400 };
  const out = [h("h1", { text: t("Stereo analysis") }),
    h("p", { class: "muted", text: t("YOLO segmentation and stereo matching on the server: depth and size (length × width) of each subject, in mm.") })];
  if (!status.available) out.push(h("div", { class: "notice warn", text: t("The analysis is not available on this server ({reason}).", { reason: status.reason }) }));

  // ---- choices
  const saved = (k) => store.get("analysis." + k);
  const sel = {
    source: q.sarea ? { area: q.sarea, path: q.spath || "" } : JSON.parse(saved("source") || "null"),
    model: q.marea ? { area: q.marea, path: q.mpath || "" } : JSON.parse(saved("model") || "null"),
  };
  const groups = await myGroups();
  const groupRoots = await Promise.all(groups.map((g) => api("GET", "/api/files", { query: { area: "groups", path: g.name } }).then((r) => r.entries).catch(() => [])));
  const [stereoItems, modelItems, mineRoot] = await Promise.all([
    api("GET", "/api/catalog", { query: { kind: "stereo" } }).then((r) => r.items).catch(() => []),
    api("GET", "/api/catalog", { query: { kind: "model" } }).then((r) => r.items).catch(() => []),
    api("GET", "/api/files", { query: { area: "mine", path: "" } }).then((r) => r.entries).catch(() => []),
  ]);
  const key = (s) => (s ? s.area + ":" + s.path : "");
  const sourceSel = h("select", {}, h("option", { value: "", text: t("Choose a stereo folder...") }));
  const addOpt = (selEl, group, items) => { if (items.length) selEl.append(h("optgroup", { label: group }, items.map(([v, txt]) => h("option", { value: v, text: txt })))); };
  addOpt(sourceSel, t("Library"), stereoItems.map((i) => [key({ area: "stereo", path: i.path }), `${i.species} — ${i.uploader}, ${i.date} (${i.items})`]));
  addOpt(sourceSel, t("My folder"), mineRoot.filter((e) => e.type === "dir").map((e) => [key({ area: "mine", path: e.name }), e.name]));
  groups.forEach((g, i) => addOpt(sourceSel, t("Group {name}", { name: g.name }), groupRoots[i].filter((e) => e.type === "dir").map((e) => [key({ area: "groups", path: `${g.name}/${e.name}` }), e.name])));
  const modelSel = h("select", {}, h("option", { value: "", text: t("Choose a YOLO model...") }));
  addOpt(modelSel, t("Library"), modelItems.map((i) => [key({ area: "models", path: i.path }), `${i.species} — ${baseName(i.path)}`]));
  addOpt(modelSel, t("My folder"), mineRoot.filter((e) => e.type === "file" && modelOk("mine", e.name)).map((e) => [key({ area: "mine", path: e.name }), e.name]));
  groups.forEach((g, i) => addOpt(modelSel, t("Group {name}", { name: g.name }), groupRoots[i].filter((e) => e.type === "file" && modelOk("groups", e.name)).map((e) => [key({ area: "groups", path: `${g.name}/${e.name}` }), e.name])));
  const ensure = (selEl, s) => { if (s && ![...selEl.options].some((o) => o.value === key(s))) selEl.append(h("option", { value: key(s), text: `${s.area}: ${s.path}` })); if (s) selEl.value = key(s); };
  ensure(sourceSel, sel.source); ensure(modelSel, sel.model);
  const parseKey = (v) => { if (!v) return null; const i = v.indexOf(":"); return { area: v.slice(0, i), path: v.slice(i + 1) }; };

  const labelSel = h("select", {}, h("option", { value: "", text: t("All objects") }));
  const labelHint = h("div", { class: "hint" });
  const baseline = h("input", { type: "number", step: "0.1", min: "1", value: saved("baseline_mm") || defaults.baseline_mm });
  const focal = h("input", { type: "number", step: "1", min: "10", value: saved("focal_length_px") || defaults.focal_length_px });
  const right = h("input", { type: "checkbox", checked: saved("detect_right") !== "0" });
  const enhStatus = await api("GET", "/api/enhance/status").catch(() => ({ available: false, methods: [] }));
  const enhSel = h("select", {}, h("option", { value: "", text: t("No enhancement") }),
    (enhStatus.methods || []).filter((m) => m.available).map((m) => h("option", { value: m.id, text: t(m.name) })));
  enhSel.value = (enhStatus.methods || []).some((m) => m.id === saved("enhance")) ? saved("enhance") : "";
  const share = h("select", {}, h("option", { value: "", text: t("Only me") }), groups.map((g) => h("option", { value: g.name, text: t("Me and group {name}", { name: g.name }) })));
  share.value = groups.some((g) => g.name === saved("group")) ? saved("group") : "";
  const start = h("button", { class: "primary", type: "submit", text: t("Start analysis"), disabled: !status.available });

  async function loadClasses() {
    const m = parseKey(modelSel.value);
    labelSel.replaceChildren(h("option", { value: "", text: t("All objects") }));
    labelHint.textContent = "";
    if (!m || !status.available) return;
    labelHint.textContent = t("Reading the classes of the model...");
    try {
      const { classes } = await api("GET", "/api/analysis/classes", { query: m });
      if (!alive()) return;
      labelSel.append(...classes.map((c) => h("option", { value: c, text: c })));
      const last = saved("label"); if (last && classes.includes(last)) labelSel.value = last;
      labelHint.textContent = t("{n} classes", { n: classes.length });
    } catch (e) { labelHint.textContent = e.message; }
  }
  modelSel.addEventListener("change", loadClasses);
  loadClasses();

  const form = h("form", { class: "card stack" },
    field(t("Stereo folder (lx / rx)"), sourceSel, t("From the library, or a folder with lx and rx subfolders in My folder.")),
    field(t("YOLO model"), modelSel),
    h("div", {}, h("label", { text: t("Object to measure") }), labelSel, labelHint),
    h("div", { class: "grid" }, field(t("Baseline (mm)"), baseline, t("Distance between the two cameras.")), field(t("Focal length (px)"), focal)),
    h("label", { class: "check" }, right, t("Also detect on the right camera (depth even where stereo matching fails)")),
    enhStatus.available ? field(t("Enhance before measuring"), enhSel, t("The same underwater colour correction on both cameras, with the settings chosen in Enhance.")) : null,
    groups.length ? field(t("Who can see the results"), share) : null,
    h("div", { class: "row" }, start, h("a", { href: "#/mine", class: "small", text: t("Upload your own captures") })));

  const results = h("div", {});
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const source = parseKey(sourceSel.value); const model = parseKey(modelSel.value);
    if (!source || !model) return fail(new Error(t("Choose a folder and a model.")));
    store.set("analysis.source", JSON.stringify(source)); store.set("analysis.model", JSON.stringify(model));
    store.set("analysis.baseline_mm", baseline.value); store.set("analysis.focal_length_px", focal.value);
    store.set("analysis.detect_right", right.checked ? "1" : "0"); store.set("analysis.label", labelSel.value); store.set("analysis.group", share.value); store.set("analysis.enhance", enhSel.value);
    try {
      const { job } = await busy(start, api("POST", "/api/analysis/jobs", { json: {
        source, model, label: labelSel.value || null, baseline_mm: Number(baseline.value), focal_length_px: Number(focal.value), detect_right: right.checked, group: share.value || null,
        enhance: enhSel.value ? { method: enhSel.value, params: enhanceSettings(enhSel.value) } : null } }));
      go(hashFor("analysis", [job.id]));
    } catch (e) { fail(e); }
  });

  // ---- a job: given in the address, else the running one
  const jobs = (await api("GET", "/api/analysis/jobs")).jobs;
  const jobId = args[0] || (jobs.find((j) => j.status === "running" || j.status === "queued") || jobs[0] || {}).id;
  const history = h("div", {});
  const drawHistory = (list) => history.replaceChildren(...(list.length ? [h("h2", { text: t("Recent analyses") }), table([
    { title: t("Started"), render: (j) => fmtDate(j.created) },
    { title: t("By"), render: (j) => h("span", {}, j.owner, j.group ? h("div", { class: "small muted", text: t("Group {name}", { name: j.group }) }) : null) },
    { title: t("Folder"), render: (j) => (j.source ? j.source.path || j.source.area : "—") },
    { title: t("Model"), render: (j) => (j.model ? baseName(j.model.path) : "—") },
    { title: t("Pairs"), render: (j) => `${j.done}/${j.total || "?"}`, num: true },
    { title: t("Status"), render: (j) => statusBadge(j.status) },
    { title: "", render: (j) => h("div", { class: "actions" }, j.owner === S.user.username || isAdmin() ? h("button", { class: "small danger", text: t("Delete"), onclick: async () => {
      try { await api("DELETE", `/api/analysis/jobs/${j.id}`); go("#/analysis"); render(); } catch (e) { fail(e); } } }) : null) },
  ], list, { onrow: (j) => go(hashFor("analysis", [j.id])) })] : []));
  drawHistory(jobs);
  const refreshHistory = () => api("GET", "/api/analysis/jobs").then((r) => alive() && drawHistory(r.jobs)).catch(() => {});
  if (jobId) showJob(jobId, results, alive, refreshHistory).catch((e) => results.replaceChildren(h("div", { class: "notice bad", text: e.message })));
  else results.append(h("div", { class: "card empty", text: t("Choose a stereo folder and a model, then start the analysis.") }));

  out.push(h("div", { class: "analysis" }, h("div", {}, form, history), results));
  return out;
});

async function showJob(id, box, alive, onFinish) {
  let job = null; const pairs = []; let current = -1; let followLatest = true;
  const bar = h("div", { class: "progress" }, h("div", {}));
  const head = h("div", { class: "row spread" });
  const statsBox = h("div", { class: "stats" });
  const viewer = h("div", { class: "viewer" }, h("div", { class: "placeholder", text: t("Waiting for the first result...") }));
  const caption = h("div", { class: "row spread small" });
  const detBox = h("div", {});
  const summaryBox = h("div", {});
  const pairList = h("div", {});
  box.replaceChildren(h("div", { class: "card stack" }, head, bar, statsBox), h("div", { class: "card stack" }, viewer, caption, detBox), summaryBox, pairList);
  const urls = new Map();

  async function showPair(i) {
    current = i; const p = pairs[i]; if (!p) return;
    const prev = h("button", { class: "small", text: "←", disabled: i === 0, onclick: () => { followLatest = false; showPair(i - 1); } });
    const next = h("button", { class: "small", text: "→", disabled: i >= pairs.length - 1, onclick: () => { followLatest = i + 1 >= pairs.length - 1; showPair(i + 1); } });
    caption.replaceChildren(prev, h("span", { text: `${p.timestamp} · ${i + 1}/${pairs.length}` }), next);
    detBox.replaceChildren(table([
      { title: t("ID"), render: (d) => d.track_id || "—" },
      { title: t("Class"), key: "label" },
      { title: t("Conf."), render: (d) => fmtNum(d.confidence * 100, 0) + "%", num: true },
      { title: t("Length (mm)"), render: (d) => fmtNum(d.length_mm), num: true },
      { title: t("Width (mm)"), render: (d) => fmtNum(d.width_mm), num: true },
      { title: t("Depth (mm)"), render: (d) => fmtNum(d.depth_mm, 0), num: true },
    ], p.detections, { empty: t("No subject detected in this pair.") }));
    if (!p.overlay) { viewer.replaceChildren(h("div", { class: "placeholder", text: "—" })); return; }
    try {
      if (!urls.has(i)) {
        const blob = await api("GET", `/api/analysis/jobs/${id}/overlay/${i}`, { blob: true });
        const u = URL.createObjectURL(blob); S.urls.push(u); urls.set(i, u);
      }
      if (current === i) viewer.replaceChildren(h("img", { src: urls.get(i), alt: p.timestamp }));
    } catch (e) { viewer.replaceChildren(h("div", { class: "placeholder", text: e.message })); }
  }
  function drawSummary() {
    const groups = new Map();
    for (const p of pairs) for (const d of p.detections) {
      const k = (d.track_id || "N/D") + "\u0000" + d.label;
      if (!groups.has(k)) groups.set(k, { id: d.track_id || "N/D", label: d.label, n: 0, L: [], W: [], C: [] });
      const g = groups.get(k); g.n++; g.C.push(d.confidence);
      if (d.length_mm != null) g.L.push(d.length_mm); if (d.width_mm != null) g.W.push(d.width_mm);
    }
    const mean = (a) => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : null);
    const rows = [...groups.values()].sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
    summaryBox.replaceChildren(h("h2", { text: t("Per subject (mean over the pairs)") }), table([
      { title: t("ID"), key: "id" }, { title: t("Class"), key: "label" }, { title: t("Appearances"), key: "n", num: true },
      { title: t("Length (mm)"), render: (g) => fmtNum(mean(g.L)), num: true }, { title: t("Width (mm)"), render: (g) => fmtNum(mean(g.W)), num: true },
      { title: t("Conf."), render: (g) => fmtNum(mean(g.C) * 100, 0) + "%", num: true },
    ], rows, { empty: t("No subject detected yet.") }));
    const measured = pairs.flatMap((p) => p.detections).filter((d) => d.length_mm != null).length;
    const all = pairs.reduce((s, p) => s + p.detections.length, 0);
    statsBox.replaceChildren(
      h("div", { class: "stat" }, h("div", { class: "v", text: `${job.done}/${job.total || "?"}` }), h("div", { class: "k", text: t("Pairs") })),
      h("div", { class: "stat" }, h("div", { class: "v", text: String(all) }), h("div", { class: "k", text: t("Detections") })),
      h("div", { class: "stat" }, h("div", { class: "v", text: String(measured) }), h("div", { class: "k", text: t("Measured") })),
      h("div", { class: "stat" }, h("div", { class: "v", text: String(job.tracked) }), h("div", { class: "k", text: t("Subjects") })));
  }
  function drawHead() {
    const active = job.status === "running" || job.status === "queued";
    head.replaceChildren(
      h("div", {}, h("h2", { text: (job.source && (job.source.path || job.source.area)) || t("Analysis") }),
        h("div", { class: "small muted", text: `${baseName(job.model.path)} · ${job.label || t("All objects")} · B ${job.baseline_mm} mm · f ${job.focal_length_px} px` + (job.enhance ? ` · ${t("enhanced")}: ${job.enhance.method}` : "") + (job.owner !== S.user.username ? ` · ${job.owner}` : "") + (job.group ? ` · ${t("Group {name}", { name: job.group })}` : "") })),
      h("div", { class: "row" }, statusBadge(job.status),
        job.status === "queued" && job.queue ? h("span", { class: "small muted", text: t("{n} before yours", { n: job.queue }) }) : null,
        active && (job.owner === S.user.username || isAdmin()) ? h("button", { class: "small danger", text: t("Stop"), onclick: () => api("POST", `/api/analysis/jobs/${id}/cancel`).then(poll).catch(fail) }) : null,
        pairs.length ? h("button", { class: "small", text: t("Export CSV"), onclick: () => saveBlob(api("GET", `/api/analysis/jobs/${id}/csv`, { blob: true }), "analysis.csv").catch(fail) }) : null));
    bar.firstChild.style.width = (job.total ? (100 * job.done) / job.total : active ? 0 : 100) + "%";
    if (job.status === "error") head.append(h("div", { class: "notice bad", text: job.error }));
  }
  async function poll() {
    if (!alive()) return;
    const r = (await api("GET", `/api/analysis/jobs/${id}`, { query: { since: pairs.length } })).job;
    if (!alive()) return;
    job = r; const before = pairs.length;
    pairs.push(...r.results);
    drawHead();
    if (pairs.length !== before || !summaryBox.childNodes.length) {
      drawSummary();
      if (followLatest || current < 0) showPair(pairs.length - 1);
    }
    if (r.status !== "running" && r.status !== "queued" && S.timers.length) { S.timers.forEach(clearInterval); S.timers = []; onFinish && onFinish(); }
  }
  await poll();
  if (job.status === "running" || job.status === "queued") S.timers.push(setInterval(() => poll().catch(() => {}), 1500));
}

// ---------------------------------------------------------------- enhance (underwater colour correction)
function enhanceSettings(id) {         // the settings chosen for a method on the Enhance page (this browser only)
  try { return JSON.parse(store.get("enhance.params." + id) || "{}"); } catch (e) { return {}; }
}
function paramControl(p, value, onchange) {
  if (p.type === "bool") {
    const c = h("input", { type: "checkbox", checked: !!value, onchange: () => onchange(c.checked) });
    return h("label", { class: "check" }, c, t(p.label));
  }
  if (p.type === "choice") {
    const sel = h("select", { onchange: () => onchange(sel.value) }, p.choices.map((c) => h("option", { value: c, text: t(c) })));
    sel.value = value;
    return field(t(p.label), sel, p.help ? t(p.help) : null);
  }
  const out = h("span", { class: "muted small", text: String(value) });
  const r = h("input", { type: "range", min: p.min, max: p.max, step: p.step || (p.type === "int" ? 1 : 0.01), value,
    oninput: () => { out.textContent = r.value; onchange(p.type === "int" ? parseInt(r.value, 10) : parseFloat(r.value)); } });
  return h("div", {}, h("div", { class: "row spread" }, h("label", { text: t(p.label) }), out), r, p.help ? h("div", { class: "hint", text: t(p.help) }) : null);
}

function compareViewer(original, results) {
  // A/B slider, side by side, or all in a grid; the images are the previews (data: URLs)
  const versions = [{ key: "original", label: t("Original"), image: original.image }, ...results.filter((r) => r.image).map((r) => ({ key: r.id, label: r.label, image: r.image }))];
  let mode = store.get("enhance.mode") || "slider";
  let a = "original", b = versions.length > 1 ? versions[1].key : "original";
  const box = h("div", { class: "stack" });
  const pick = (cur, set) => { const sel = h("select", { onchange: () => { set(sel.value); draw(); } }, versions.map((v) => h("option", { value: v.key, text: v.label }))); sel.value = cur; sel.style.width = "auto"; return sel; };
  const img = (k) => h("img", { src: versions.find((v) => v.key === k).image, alt: versions.find((v) => v.key === k).label });
  function draw() {
    const tabs = h("div", { class: "tabs" }, [["slider", "Slider"], ["side", "Side by side"], ["all", "All"]].map(([k, l]) =>
      h("button", { class: mode === k ? "active" : "", text: t(l), onclick: () => { mode = k; store.set("enhance.mode", k); draw(); } })));
    let body;
    if (mode === "slider") {
      const top = h("div", { class: "cmp-top" }, img(a));
      const range = h("input", { type: "range", min: 0, max: 100, value: 50, class: "cmp-range", "aria-label": t("Slider") });
      const line = h("div", { class: "cmp-line" });
      const set = () => { top.style.clipPath = `inset(0 ${100 - range.value}% 0 0)`; line.style.left = range.value + "%"; };
      range.addEventListener("input", set); set();
      body = [h("div", { class: "row" }, h("span", { class: "small muted", text: "A" }), pick(a, (v) => { a = v; }), h("span", { class: "small muted", text: "B" }), pick(b, (v) => { b = v; })),
        h("div", { class: "cmp" }, img(b), top, line, range), h("div", { class: "row spread small muted" }, h("span", { text: "A ←" }), h("span", { text: "→ B" }))];
    } else if (mode === "side") {
      body = [h("div", { class: "row" }, h("span", { class: "small muted", text: "A" }), pick(a, (v) => { a = v; }), h("span", { class: "small muted", text: "B" }), pick(b, (v) => { b = v; })),
        h("div", { class: "cmp-grid two" }, h("figure", {}, img(a), h("figcaption", { text: versions.find((v) => v.key === a).label })), h("figure", {}, img(b), h("figcaption", { text: versions.find((v) => v.key === b).label })))];
    } else {
      body = [h("div", { class: "cmp-grid" }, versions.map((v) => h("figure", {}, img(v.key), h("figcaption", { text: v.label }))))];
    }
    box.replaceChildren(tabs, ...body);
  }
  draw();
  return box;
}

route("enhance", async (args, q, alive) => {
  const status = await api("GET", "/api/enhance/status");
  const out = [h("h1", { text: t("Enhance") }),
    h("p", { class: "muted", text: t("Underwater colour correction: remove the green-blue cast and the haze. Try methods on a reduced copy, compare them, then process the full-size files.") })];
  if (!status.available) out.push(h("div", { class: "notice warn", text: t("Image enhancement is not available on this server ({reason}).", { reason: status.reason }) }));
  else out.push(h("p", { class: "small muted", text: status.gpu ? t("Running on the graphics card: {device}", { device: status.device }) : t("Running on the processor (slower): {device}", { device: status.device }) }));

  const source = q.area ? { area: q.area, path: q.path || "" } : null;
  const methods = (status.methods || []);
  const nameOf = (id) => t((methods.find((m) => m.id === id) || { name: id }).name);
  const jobsBox = h("div", {});

  async function drawJobs() {
    const jobs = (await api("GET", "/api/enhance/jobs").catch(() => ({ jobs: [] }))).jobs;
    if (!alive()) return;
    const outLink = (j) => {
      const o = j.output; const isFile = /\.[A-Za-z0-9]+$/.test(o.path);
      const folder = isFile ? parentPath(o.path) : o.path;
      return link(o.area === "mine" ? hashFor("mine", [], folder ? { path: folder } : null) : hashFor("browse", [o.area], { path: folder }), o.path);
    };
    jobsBox.replaceChildren(...(jobs.length ? [h("h2", { text: t("Enhancements") }), table([
      { title: t("Started"), render: (j) => fmtDate(j.created) },
      { title: t("Source"), render: (j) => j.source.path },
      { title: t("Method"), render: (j) => nameOf(j.method) },
      { title: t("Files"), render: (j) => `${j.done}/${j.total || "?"}` + (j.status === "running" && j.progress ? ` (${Math.round(j.progress * 100)}%)` : ""), num: true },
      { title: t("Status"), render: (j) => h("span", {}, statusBadge(j.status), j.error ? h("div", { class: "small", text: j.error }) : null) },
      { title: t("Saved in"), render: outLink },
      { title: "", render: (j) => h("div", { class: "actions" },
        (j.status === "running" || j.status === "queued") && j.owner === S.user.username ? h("button", { class: "small danger", text: t("Stop"), onclick: () => api("POST", `/api/enhance/jobs/${j.id}/cancel`).then(drawJobs).catch(fail) }) : null,
        j.status !== "running" && j.status !== "queued" && j.owner === S.user.username ? h("button", { class: "small", text: t("Remove from list"), onclick: () => api("DELETE", `/api/enhance/jobs/${j.id}`).then(drawJobs).catch(fail) }) : null) },
    ], jobs)] : []));
    const active = jobs.some((j) => j.status === "running" || j.status === "queued");
    if (active && !S.timers.length) S.timers.push(setInterval(() => drawJobs().catch(() => {}), 2000));
    if (!active && S.timers.length) { S.timers.forEach(clearInterval); S.timers = []; }
  }

  if (!source) {
    out.push(h("div", { class: "card empty", text: t("Open a photo, a video or a folder (Library, My folder or the folder of a group) and choose Enhance.") }), jobsBox);
    drawJobs();
    return out;
  }

  // ---- what is being enhanced: one file, or a folder (previews on one of its files)
  const isFile = /\.[A-Za-z0-9]+$/.test(source.path) && (isImage(source.path) || VIDEO_EXT.includes(ext(source.path)));
  let samples = [];
  if (isFile) samples = [source.path];
  else {
    const walk = async (p, depth) => {
      const r = await api("GET", "/api/files", { query: { area: source.area, path: p } });
      for (const e of r.entries) {
        const rel = joinPath(p, e.name);
        if (e.type === "file" && (isImage(e.name) || VIDEO_EXT.includes(ext(e.name)))) samples.push(rel);
        else if (e.type === "dir" && depth < 2 && e.name !== PENDING) await walk(rel, depth + 1);
        if (samples.length >= 300) return;
      }
    };
    await walk(source.path, 0);
    if (!samples.length) throw new Error(t("No photo or video to enhance here."));
  }
  const sampleSel = h("select", {}, samples.map((p) => h("option", { value: p, text: isFile ? baseName(p) : p.slice(source.path.length + 1) })));
  const writable = source.area === "mine" || source.area === "groups";
  const where = writable
    ? (isFile ? t("Saved next to the original, as {name}", { name: baseName(source.path).replace(/(\.[^.]+)$/, "_<method>$1") }) : t("Saved next to the original, in the folder {name}", { name: baseName(source.path) + "_<method>" }))
    : t("The library is read-only: the result is saved in My folder.");

  // ---- methods, with their settings (remembered in this browser)
  const ticked = new Set(JSON.parse(store.get("enhance.ticked") || "null") || methods.slice(0, 3).map((m) => m.id));
  const settings = Object.fromEntries(methods.map((m) => [m.id, Object.assign(Object.fromEntries(m.params.map((p) => [p.name, p.default])), enhanceSettings(m.id))]));
  const save = (id) => store.set("enhance.params." + id, JSON.stringify(settings[id]));
  const list = h("div", { class: "stack" }, methods.map((m) => {
    const box = h("input", { type: "checkbox", checked: ticked.has(m.id), disabled: !m.available,
      onchange: () => { box.checked ? ticked.add(m.id) : ticked.delete(m.id); store.set("enhance.ticked", JSON.stringify([...ticked])); } });
    const controls = h("div", { class: "stack" }, m.params.map((p) => paramControl(p, settings[m.id][p.name], (v) => { settings[m.id][p.name] = v; save(m.id); })));
    const reset = h("button", { type: "button", class: "small", text: t("Default settings"), onclick: () => {
      settings[m.id] = Object.fromEntries(m.params.map((p) => [p.name, p.default])); save(m.id); render(); } });
    return h("div", { class: "method" + (m.available ? "" : " off") },
      h("label", { class: "check" }, box, h("strong", { text: t(m.name) })),
      h("div", { class: "small muted", text: m.available ? t(m.description) : m.unavailable_reason }),
      m.params.length ? h("details", {}, h("summary", { text: t("Settings") }), controls, reset) : null);
  }));

  const seconds = h("input", { type: "range", min: 0, max: 0, step: 0.1, value: 0 });
  const secondsOut = h("span", { class: "small muted", text: "0 s" });
  seconds.addEventListener("input", () => { secondsOut.textContent = `${seconds.value} s`; });
  const timeRow = h("div", { hidden: true }, h("div", { class: "row spread" }, h("label", { text: t("Video frame") }), secondsOut), seconds);
  const previewBtn = h("button", { class: "primary", type: "button", text: t("Preview"), disabled: !status.available });
  const fullSel = h("select", {}, methods.filter((m) => m.available).map((m) => h("option", { value: m.id, text: t(m.name) })));
  fullSel.value = store.get("enhance.full") || (methods[0] || {}).id;
  fullSel.style.width = "auto";
  const fullBtn = h("button", { type: "button", text: isFile ? t("Process this file at full size") : t("Process the whole folder at full size"), disabled: !status.available });
  const viewer = h("div", { class: "card" }, h("div", { class: "empty", text: t("Tick one or more methods and press Preview.") }));

  const updateTime = () => { const v = VIDEO_EXT.includes(ext(sampleSel.value)); timeRow.hidden = !v; };
  sampleSel.addEventListener("change", updateTime); updateTime();
  previewBtn.addEventListener("click", async () => {
    const chosen = methods.filter((m) => ticked.has(m.id) && m.available);
    if (!chosen.length) return fail(new Error(t("Tick at least one method.")));
    viewer.replaceChildren(h("div", { class: "empty", text: t("Working on the preview...") }));
    try {
      const r = await busy(previewBtn, api("POST", "/api/enhance/preview", { json: {
        source: { area: source.area, path: sampleSel.value }, seconds: Number(seconds.value),
        methods: chosen.slice(0, 6).map((m) => ({ id: m.id, params: settings[m.id] })) } }));
      if (!alive()) return;
      if (r.duration) { seconds.max = Math.max(0, Math.floor(r.duration * 10) / 10 - 0.1); }
      const results = r.results.map((x) => ({ ...x, label: nameOf(x.id) }));
      const scores = table([
        { title: t("Version"), key: "label" },
        { title: t("Time (s)"), render: (x) => (x.seconds == null ? "—" : x.seconds.toFixed(2)), num: true },
        { title: "UIQM", render: (x) => (x.metrics ? x.metrics.uiqm.toFixed(2) : "—"), num: true },
        { title: "UCIQE", render: (x) => (x.metrics ? x.metrics.uciqe.toFixed(3) : "—"), num: true },
        { title: "", render: (x) => (x.error ? h("span", { class: "badge bad", text: x.error }) : null) },
      ], [{ label: t("Original"), metrics: r.original.metrics }, ...results]);
      viewer.replaceChildren(compareViewer(r.original, results), h("p", { class: "hint", text: t("Preview at {w}×{h} px reduced to 1280 px. UIQM and UCIQE: higher is better, but they are only a rough guide; trust your eyes.", { w: r.width, h: r.height }) }), scores);
    } catch (e) { viewer.replaceChildren(h("div", { class: "notice bad", text: e.message })); }
  });
  fullBtn.addEventListener("click", async () => {
    store.set("enhance.full", fullSel.value);
    try {
      const { job } = await busy(fullBtn, api("POST", "/api/enhance/jobs", { json: { source, method: fullSel.value, params: settings[fullSel.value] } }));
      toast(t("Started: the result will be saved in {path}.", { path: job.output.path }));
      drawJobs();
    } catch (e) { fail(e); }
  });

  const form = h("div", { class: "card stack" },
    h("div", {}, h("div", { class: "small muted", text: t(source.area === "mine" ? "My folder" : source.area === "groups" ? "Group folders" : "Library") }), h("strong", { text: source.path })),
    samples.length > 1 ? field(t("Preview on"), sampleSel) : null, timeRow,
    h("h3", { text: t("Methods") }), list,
    h("div", { class: "row" }, previewBtn),
    h("hr", {}),
    h("div", { class: "row" }, fullSel, fullBtn), h("p", { class: "hint", text: where }));
  out.push(h("div", { class: "analysis" }, h("div", {}, form), h("div", {}, viewer)), jobsBox);
  drawJobs();
  return out;
});

// ---------------------------------------------------------------- work groups
route("groups", async () => {
  const admin = isAdmin();
  const groups = (await api("GET", "/api/groups", { query: { all: admin ? "1" : null } })).groups;
  const roleName = (r) => (r === "admin" ? t("Administrator") : t("Member"));
  const act = (p) => p.then(() => { toast(t("Saved.")); render(); }).catch(fail);
  const out = [h("h1", { text: t("Groups") }),
    h("p", { class: "muted", text: t("The members of a work group share a folder and their analyses, and see the uploads shared with the group. Anybody can create a group and is then its administrator: the administrators of a group add the members, promote them and approve what the others send.") })];

  const users = admin ? (await api("GET", "/api/users").catch(() => ({ users: [] }))).users : [];
  const list = h("datalist", { id: "usernames" }, users.map((u) => h("option", { value: u.username })));
  const name = h("input", { autocomplete: "off", placeholder: "Lab A" });
  const form = h("form", { class: "card" }, list, h("div", { class: "grid" },
    field(t("Group name"), name, t("2-40 letters, numbers, spaces, - and _.")),
    h("div", { class: "row" }, h("button", { class: "primary", type: "submit", text: t("Create group") }))));
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    if (name.value.trim()) act(api("POST", "/api/groups", { json: { name: name.value.trim() } }));
  });
  out.push(form);
  if (!groups.length) out.push(h("div", { class: "card empty", text: t("No group yet: create the first one above.") }));

  for (const g of groups) {
    const looksAfter = admin || g.role === "admin";
    const bar = h("div", { class: "progress" }, h("div", {}));
    bar.firstChild.style.width = Math.min(100, (100 * g.usage) / Math.max(1, g.quota_mb * 1048576)) + "%";
    const members = table([
      { title: t("Username"), render: (m) => h("strong", { text: m.username }) },
      { title: t("Role"), render: (m) => {
        if (!looksAfter) return h("span", { class: "badge " + (m.role === "admin" ? "info" : ""), text: roleName(m.role) });
        const sel = h("select", {}, h("option", { value: "member", text: t("Member") }), h("option", { value: "admin", text: t("Administrator") }));
        sel.value = m.role; sel.style.width = "auto";
        sel.addEventListener("change", () => act(api("POST", "/api/groups/role", { json: { group: g.name, username: m.username, role: sel.value } })));
        return sel;
      } },
      { title: t("Added"), render: (m) => fmtDate(m.added) },
      { title: "", render: (m) => {
        const self = m.username === S.user.username;
        if (!(self || looksAfter)) return null;
        return h("div", { class: "actions" }, h("button", { class: "small danger", text: self ? t("Leave") : t("Remove"), onclick: () => {
          if (!confirm(self ? t("Leave the group {name}?", { name: g.name }) : t("Remove {user} from {name}?", { user: m.username, name: g.name }))) return;
          act(self ? api("POST", "/api/groups/leave", { json: { name: g.name } })
                   : api("POST", "/api/groups/members", { json: { group: g.name, username: m.username, member: false } }));
        } }));
      } },
    ], g.members, { empty: t("No members yet.") });

    let addForm = null;
    if (looksAfter) {
      const who = h("input", { autocomplete: "off", placeholder: t("Username"), list: admin ? "usernames" : null });
      const role = h("select", {}, h("option", { value: "member", text: t("Member") }), h("option", { value: "admin", text: t("Administrator") }));
      role.style.width = "auto";
      addForm = h("form", { class: "row" }, who, role, h("button", { type: "submit", text: t("Add member") }));
      who.style.flex = "1"; who.style.minWidth = "10rem"; who.style.width = "auto";
      addForm.addEventListener("submit", (ev) => {
        ev.preventDefault();
        if (who.value.trim()) act(api("POST", "/api/groups/members", { json: { group: g.name, username: who.value.trim(), role: role.value } }));
      });
    }
    const tools = h("div", { class: "row" },
      looksAfter ? h("button", { class: "small", text: t("Free upload"), onclick: () =>
        act(api("POST", "/api/groups/settings", { json: { name: g.name, free_upload: !g.free_upload } })) }) : null,
      admin ? h("button", { class: "small", text: t("Quota"), onclick: () => {
        const v = prompt(t("Quota of {name} in MB", { name: g.name }), g.quota_mb);
        if (v !== null && v !== "") act(api("POST", "/api/groups/quota", { json: { name: g.name, quota_mb: Number(v) } }));
      } }) : null,
      looksAfter ? h("button", { class: "small danger", text: t("Delete group"), onclick: () => {
        if (!confirm(t("Delete the group {name}? Uploads shared only with it stay visible to their uploader only.", { name: g.name }))) return;
        const files = confirm(t("Delete the folder of {name} and all its files as well?", { name: g.name }));
        act(api("POST", "/api/groups/delete", { json: { name: g.name, files } }));
      } }) : null);

    out.push(h("div", { class: "card stack" },
      h("div", { class: "row spread" },
        h("div", {}, h("h2", { text: g.name }),
          h("div", { class: "small muted", text: g.role ? t("You are: {role}", { role: roleName(g.role) }) : t("You are not a member (administrator view).") }),
          g.description ? h("div", { class: "small muted", text: g.description }) : null),
        h("div", { class: "row" }, g.role ? h("a", { class: "button", href: hashFor("browse", ["groups"], { path: g.name }), text: t("Open group folder") }) : null, tools)),
      h("div", {}, h("div", { class: "row spread small" }, h("span", { text: g.free_upload ? t("Group folder (the members write directly)") : t("Group folder (what the members send waits for approval)") }), h("span", { text: `${fmtBytes(g.usage)} / ${fmtBytes(g.quota_mb * 1048576)}` })), bar),
      members, addForm));
  }
  return out;
});

// ---------------------------------------------------------------- profile
route("profile", async () => {
  const { user } = await api("GET", "/api/me");
  S.user = user;
  const fields = { full_name: "Full name", email: "E-mail", organization: "Organization", phone: "Phone", bio: "About me" };
  const inputs = {};
  const form = h("form", { class: "card stack" }, h("div", { class: "grid" }, Object.entries(fields).filter(([k]) => k !== "bio").map(([k, l]) => field(t(l), inputs[k] = h("input", { value: user[k] || "" })))),
    field(t(fields.bio), inputs.bio = h("textarea", { rows: 3, text: user.bio || "" })), h("div", {}, h("button", { class: "primary", type: "submit", text: t("Save") })));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try { const r = await api("PATCH", "/api/profile", { json: Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value])) }); S.user = r.user; renderNav("profile"); toast(t("Saved.")); } catch (e) { fail(e); }
  });
  const old = h("input", { type: "password", autocomplete: "current-password" });
  const nw = h("input", { type: "password", autocomplete: "new-password" });
  const nw2 = h("input", { type: "password", autocomplete: "new-password" });
  const pw = h("form", { class: "card stack" }, h("div", { class: "grid" }, field(t("Current password"), old), field(t("New password"), nw, t("At least 8 characters.")), field(t("Repeat the password"), nw2)),
    h("div", {}, h("button", { type: "submit", text: t("Change password") })));
  pw.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (nw.value !== nw2.value) return fail(new Error(t("The two passwords are different.")));
    try { await api("POST", "/api/password", { json: { old: old.value, new: nw.value } }); pw.reset(); toast(t("Password changed.")); } catch (e) { fail(e); }
  });
  return [h("h1", { text: user.username }), h("p", { class: "muted", text: (user.role === ROLE_ADMIN ? t("Administrator") : t("User")) + " · " + t("since {date}", { date: fmtDate(user.created) }) }),
    h("h2", { text: t("Profile") }), form, h("h2", { text: t("Password") }), pw];
});

// ---------------------------------------------------------------- admin: review
route("review", async (args) => {
  const kind = KINDS.includes(args[0]) ? args[0] : null;
  const subs = (await api("GET", "/api/species/submissions", { query: { status: "pending", kind } })).submissions;
  const counts = {}; for (const s of subs) counts[s.kind] = (counts[s.kind] || 0) + 1;
  const tabs = h("div", { class: "tabs" }, h("button", { class: kind ? "" : "active", text: t("All"), onclick: () => go("#/review") }),
    KINDS.map((k) => h("button", { class: k === kind ? "active" : "", text: t(KIND_LABEL[k]), onclick: () => go("#/review/" + k) })));
  const decide = (s, action) => async (ev) => {
    if (action === "reject" && !confirm(t("Reject and delete the files of {name}?", { name: s.species }))) return;
    try { await busy(ev.target, api("POST", `/api/species/submissions/${s.id}/${action}`)); toast(action === "approve" ? t("Approved.") : t("Rejected.")); render(); } catch (e) { fail(e); }
  };
  const previewHash = (s) => {
    const area = KIND_AREA[s.kind];
    return hashFor("browse", [area], { path: s.kind === "model" ? parentPath(s.path) : s.path });
  };
  return [h("h1", { text: t("Review") }), h("p", { class: "muted", text: t("Uploads waiting for approval. Approved items move to the library; rejected ones are deleted.") }), tabs,
    table([
      { title: t("Kind"), render: (s) => t(KIND_LABEL[s.kind] || s.kind) },
      { title: t("Species") + " / " + t("Name"), render: (s) => h("em", { text: s.species }) },
      { title: t("Uploaded by"), key: "username" },
      { title: t("Files"), key: "photos", num: true },
      { title: t("Sent"), render: (s) => fmtDate(s.created) },
      { title: "", render: (s) => h("div", { class: "actions" }, h("a", { class: "button small", href: previewHash(s), text: t("Open") }),
        h("button", { class: "small primary", text: t("Approve"), onclick: decide(s, "approve") }), h("button", { class: "small danger", text: t("Reject"), onclick: decide(s, "reject") })) },
    ], subs, { empty: t("Nothing is waiting for review.") })];
});

// ---------------------------------------------------------------- admin: users
route("users", async () => {
  const users = (await api("GET", "/api/users")).users;
  const patch = async (u, data, msg) => { try { await api("PATCH", `/api/users/${u.id}`, { json: data }); toast(msg || t("Saved.")); render(); } catch (e) { fail(e); } };
  const nu = h("input", { autocomplete: "off" }); const np = h("input", { type: "password", autocomplete: "new-password" });
  const nr = h("select", {}, h("option", { value: "user", text: t("User") }), h("option", { value: ROLE_ADMIN, text: t("Administrator") }));
  const create = h("form", { class: "card" }, h("div", { class: "grid" }, field(t("Username"), nu), field(t("Password"), np, t("At least 8 characters.")), field(t("Role"), nr),
    h("div", { class: "row" }, h("button", { class: "primary", type: "submit", text: t("Create account") }))));
  create.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try { await api("POST", "/api/users", { json: { username: nu.value, password: np.value, role: nr.value } }); toast(t("Account created.")); render(); } catch (e) { fail(e); }
  });
  return [h("h1", { text: t("Users") }), create, table([
    { title: t("Username"), render: (u) => h("span", {}, h("strong", { text: u.username }), u.full_name ? h("div", { class: "small muted", text: u.full_name }) : null) },
    { title: t("Role"), render: (u) => { const s = h("select", { disabled: u.id === S.user.id }, h("option", { value: "user", text: t("User") }), h("option", { value: ROLE_ADMIN, text: t("Administrator") })); s.value = u.role; s.addEventListener("change", () => patch(u, { role: s.value })); return s; } },
    { title: t("Quota (MB)"), render: (u) => { const i = h("input", { type: "number", min: "0", value: u.quota_mb, class: "small" }); i.style.width = "7rem"; i.addEventListener("change", () => patch(u, { quota_mb: Number(i.value) })); return i; } },
    { title: t("Last sign-in"), render: (u) => fmtDate(u.last_login) },
    { title: t("Status"), render: (u) => h("span", { class: "badge " + (u.active ? "ok" : u.pending ? "warn" : "bad"), text: u.active ? t("active") : u.pending ? t("awaiting approval") : t("disabled") }) },
    { title: "", render: (u) => h("div", { class: "actions" },
      u.pending ? h("button", { class: "small primary", text: t("Approve"), onclick: () => patch(u, { active: true }, t("Approved.")) })
        : u.id !== S.user.id ? h("button", { class: "small", text: u.active ? t("Disable") : t("Enable"), onclick: () => patch(u, { active: !u.active }) }) : null,
      h("button", { class: "small", text: t("New password"), onclick: () => { const p = prompt(t("New password for {name}", { name: u.username })); if (p) patch(u, { password: p }, t("Password changed.")); } }),
      u.id !== S.user.id ? h("button", { class: "small danger", text: t("Delete"), onclick: async () => {
        if (!confirm(t("Delete the account {name}?", { name: u.username }))) return;
        try { await api("DELETE", `/api/users/${u.id}`); toast(t("Deleted.")); render(); } catch (e) { fail(e); } } }) : null) },
  ], users)];
}, { admin: true });

// ---------------------------------------------------------------- admin: server
route("server", async () => {
  const [st, ev, an] = await Promise.all([api("GET", "/api/stats"), api("GET", "/api/events", { query: { limit: 100 } }), api("GET", "/api/analysis/status")]);
  const stat = (k, v) => h("div", { class: "stat" }, h("div", { class: "v", text: String(v) }), h("div", { class: "k", text: k }));
  const up = st.uptime == null ? "—" : st.uptime > 86400 ? `${Math.floor(st.uptime / 86400)} d` : `${Math.floor(st.uptime / 3600)} h`;
  return [h("h1", { text: t("Server") }),
    h("div", { class: "stats" }, stat(t("Users"), st.users), stat(t("Administrators"), st.admins), stat(t("Active sessions"), st.sessions),
      stat(t("Sign-ins (24 h)"), st.logins_24h), stat(t("Uptime"), up), stat(t("Free disk"), fmtBytes(st.disk_free)), stat(t("Waiting for review"), fmtBytes(st.pending_bytes))),
    h("div", { class: an.available ? "notice info" : "notice warn", text: an.available ? t("Analysis available on: {device}", { device: an.device }) : t("The analysis is not available on this server ({reason}).", { reason: an.reason }) }),
    h("h2", { text: t("Space by area") }),
    table([{ title: t("Area"), key: "area" }, { title: t("Size"), render: (r) => fmtBytes(r.size), num: true }], Object.entries(st.areas || {}).map(([area, size]) => ({ area, size }))),
    h("h2", { text: t("Recent events") }),
    table([{ title: t("When"), render: (e) => fmtDate(e.ts) }, { title: t("User"), key: "username" }, { title: t("Action"), key: "action" }, { title: t("Area"), key: "area" }, { title: t("Path"), key: "path" }], ev.events)];
}, { admin: true });

// ---------------------------------------------------------------- start
async function boot() {
  const lang = $("#lang");
  lang.append(...Object.entries(LANG_NAMES).map(([k, v]) => h("option", { value: k, text: v })));
  lang.value = S.lang;
  lang.addEventListener("change", async () => { await loadLanguage(lang.value); render(); });
  $("#logout").addEventListener("click", () => signOut(false));
  $("#menu-toggle").addEventListener("click", (e) => { const n = $("#nav"); n.classList.toggle("open"); e.currentTarget.setAttribute("aria-expanded", n.classList.contains("open")); });
  window.addEventListener("hashchange", render);
  S.health = await api("GET", "/api/health", { anon: true }).catch(() => ({ ok: false }));
  await loadLanguage(S.lang);
  if (S.token) {
    try { S.user = (await api("GET", "/api/me")).user; } catch (e) { S.token = null; store.set("token", null); }
  }
  render();
}
boot();
