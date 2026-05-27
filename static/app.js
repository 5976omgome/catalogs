const $ = (id) => document.getElementById(id);

const state = {
  filterFlagged: false,
  buffer: [],
  total: 0,
  processed: 0,
  clean: 0,
};

async function fetchStatus() {
  try {
    const r = await fetch("/api/status");
    const j = await r.json();
    setPill("pill-discogs", j.discogs ? "Discogs: ready" : "Discogs: no token", j.discogs);
    const aiOn = j.groq || j.gemini;
    let aiText = "AI: rule-based";
    if (j.groq && j.gemini) aiText = "AI: Groq + Gemini";
    else if (j.groq) aiText = "AI: Groq";
    else if (j.gemini) aiText = "AI: Gemini";
    setPill("pill-ai", aiText, aiOn);
    setPill("pill-itunes", "iTunes: ready", true);
    setPill("pill-deezer", "Deezer: ready", true);
  } catch (e) {}
}

function setPill(id, text, on) {
  const el = $(id);
  el.textContent = text;
  el.classList.toggle("on", !!on);
  el.classList.toggle("off", on === false);
}

function logLine(text, cls = "line-info") {
  state.buffer.push({ text, cls });
  renderLog();
}

function renderLog() {
  const log = $("log");
  const visible = state.buffer.filter((l) => {
    if (!state.filterFlagged) return true;
    return l.cls === "line-flagged" || l.cls.startsWith("line-pline") || l.cls.startsWith("line-meta");
  });
  log.innerHTML = visible.map((l) => `<span class="${l.cls}">${escapeHtml(l.text)}</span>`).join("\n");
  log.scrollTop = log.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function renderQueue(items) {
  const ul = $("queue");
  ul.innerHTML = "";
  for (const it of items) {
    const li = document.createElement("li");
    li.classList.add(it.status);
    const head = document.createElement("div");
    head.className = "qitem-head";
    let txt = it.filename;
    if (it.status === "running") {
      txt += `  ${it.processed || 0}/${it.total || 0}`;
    }
    if (it.status === "done" || it.status === "stopped") {
      const counts = [];
      if (typeof it.keep === "number")  counts.push(`${it.keep} keep`);
      if (typeof it.review === "number") counts.push(`${it.review} review`);
      if (typeof it.drop === "number")  counts.push(`${it.drop} drop`);
      const tail = counts.length ? counts.join(" / ") : `${it.clean || 0}/${it.total || 0} clean`;
      const mark = it.status === "stopped" ? "■" : "✓";
      txt += `  ${mark}  ${tail}`;
    }
    if (it.status === "error") txt += `  ✕  ${it.error || ""}`;
    head.textContent = txt;
    li.appendChild(head);

    if ((it.status === "done" || it.status === "stopped") && it.output_path) {
      const tools = document.createElement("div");
      tools.className = "qitem-tools";
      tools.appendChild(makeExportLink(it, "keep",   "export keep"));
      tools.appendChild(makeExportLink(it, "review", "export review"));
      tools.appendChild(makeExportLink(it, "drop",   "export drops"));
      tools.appendChild(makeExportLink(it, "all",    "export all"));
      tools.appendChild(makeDownloadLink(it));
      li.appendChild(tools);
    }

    ul.appendChild(li);
  }
}

function makeExportLink(item, kind, label) {
  const a = document.createElement("a");
  a.href = `/api/export/${item.item_id}?filter=${encodeURIComponent(kind)}`;
  a.textContent = label;
  a.className = "qitem-link";
  a.addEventListener("click", async (e) => {
    // Probe first so we can tell the user when there are zero rows for
    // that filter, instead of silently downloading an error JSON.
    e.preventDefault();
    const r = await fetch(a.href, { method: "HEAD" }).catch(() => null);
    if (!r || !r.ok) {
      // HEAD may not be supported by every WSGI route; just let the
      // browser navigate and any 404 will surface inline.
    }
    window.location = a.href;
  });
  return a;
}

function makeDownloadLink(item) {
  const a = document.createElement("a");
  a.href = `/api/download/${item.item_id}`;
  a.textContent = "full xlsx";
  a.className = "qitem-link";
  return a;
}

function updateProgress(processed, total, clean) {
  $("processed-label").textContent = `${processed} of ${total} processed`;
  const ppct = total > 0 ? Math.floor((processed / total) * 100) : 0;
  $("processed-pct").textContent = `${ppct}%`;
  $("bar-fill").style.width = `${ppct}%`;

  $("clean-label").textContent = `${clean} of ${processed} clean`;
  if (processed > 0) {
    const cpct = Math.floor((clean / processed) * 100);
    $("clean-pct").textContent = `${cpct}%`;
  } else {
    $("clean-pct").textContent = "—";
  }
}

const queueItems = new Map();

function setItem(item) {
  queueItems.set(item.item_id, item);
  renderQueue(Array.from(queueItems.values()));
}

function patchItem(item_id, patch) {
  const cur = queueItems.get(item_id);
  if (!cur) return;
  Object.assign(cur, patch);
  renderQueue(Array.from(queueItems.values()));
}

function aggregate() {
  let total = 0, processed = 0, clean = 0;
  for (const it of queueItems.values()) {
    total += it.total || 0;
    processed += it.processed || 0;
    clean += it.clean || 0;
  }
  state.total = total;
  state.processed = processed;
  state.clean = clean;
  updateProgress(processed, total, clean);
}

function handleEvent(ev) {
  switch (ev.type) {
    case "snapshot":
      queueItems.clear();
      for (const it of ev.items) queueItems.set(it.item_id, it);
      renderQueue(ev.items);
      aggregate();
      break;
    case "item_added":
      setItem(ev.item);
      aggregate();
      break;
    case "item_removed":
      queueItems.delete(ev.item_id);
      renderQueue(Array.from(queueItems.values()));
      aggregate();
      break;
    case "queue_cleared":
      queueItems.clear();
      renderQueue([]);
      aggregate();
      break;
    case "item_status":
      patchItem(ev.item_id, { status: ev.status });
      break;
    case "item_total":
      patchItem(ev.item_id, { total: ev.total });
      aggregate();
      break;
    case "item_done":
      patchItem(ev.item_id, {
        status: "done",
        output_path: ev.output_path,
        total: ev.total,
        clean: ev.clean,
        flagged: ev.flagged,
        keep: ev.keep,
        review: ev.review,
        drop: ev.drop,
      });
      logLine(`[DONE] keep=${ev.keep ?? "?"} review=${ev.review ?? "?"} drop=${ev.drop ?? "?"} -> ${ev.output_path}`, "line-clean");
      aggregate();
      break;
    case "item_stopped":
      patchItem(ev.item_id, {
        status: "stopped",
        output_path: ev.output_path,
        total: ev.total,
        processed: ev.processed,
        clean: ev.clean,
        flagged: ev.flagged,
        keep: ev.keep,
        review: ev.review,
        drop: ev.drop,
      });
      logLine(`[STOPPED] processed ${ev.processed}/${ev.total} -> ${ev.output_path}`, "line-flagged");
      aggregate();
      break;
    case "queue_stop_requested":
      logLine(`[STOP requested - finishing current artist...]`, "line-flagged");
      break;
    case "item_error":
      patchItem(ev.item_id, { status: "error", error: ev.error });
      logLine(`[ERROR] ${ev.error}`, "line-flagged");
      break;
    case "artist_start":
      logLine(`[${ev.index}] ${ev.artist}`, "line-info");
      break;
    case "artist_done":
      patchItem(ev.item_id, {
        processed: ev.processed,
        total: ev.total,
        clean: ev.clean,
        flagged: ev.flagged,
      });
      const cls = ev.verdict === "CLEAN" ? "line-clean" : "line-flagged";
      logLine(`  -> ${ev.verdict}${ev.earliest_year ? "  (earliest " + ev.earliest_year + ")" : ""}`, cls);
      if (ev.pline) logLine(`     P: ${ev.pline}`, "line-pline");
      if (ev.flag_reasons && ev.flag_reasons.length > 0) {
        for (const r of ev.flag_reasons) logLine(`     ! ${r}`, "line-meta");
      }
      aggregate();
      break;
    case "queue_done":
      logLine(`[QUEUE DONE]`, "line-clean");
      break;
  }
}

function startSSE() {
  const es = new EventSource("/api/stream");
  es.onmessage = (e) => {
    try {
      const ev = JSON.parse(e.data);
      handleEvent(ev);
    } catch (err) {
      console.error("bad event", err);
    }
  };
  es.onerror = () => {
    // EventSource auto-reconnects
  };
}

async function uploadFiles(files) {
  if (!files || !files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  await fetch("/api/upload", { method: "POST", body: fd });
}

// ---------- Settings (API keys) ----------

const SETTINGS_FIELDS = [
  { key: "discogs_token", inputId: "settings-discogs", statusId: "settings-discogs-status" },
  { key: "groq_api_key",  inputId: "settings-groq",    statusId: "settings-groq-status"    },
  { key: "gemini_api_key",inputId: "settings-gemini",  statusId: "settings-gemini-status"  },
];

function renderSettings(payload) {
  if (!payload || !payload.keys) return;
  for (const f of SETTINGS_FIELDS) {
    const info = payload.keys[f.key] || { set: false, source: "unset", preview: "" };
    const statusEl = $(f.statusId);
    const inputEl  = $(f.inputId);
    statusEl.classList.remove("set", "env");
    if (info.set && info.source === "file") {
      statusEl.textContent = info.preview;
      statusEl.classList.add("set");
      inputEl.placeholder = "leave blank to keep";
    } else if (info.set && info.source === "env") {
      statusEl.textContent = `${info.preview} (env)`;
      statusEl.classList.add("env");
      inputEl.placeholder = "leave blank to keep env value";
    } else {
      statusEl.textContent = "unset";
      inputEl.placeholder = "paste token / key";
    }
    // Never refill the input from the server response.
    inputEl.value = "";
  }
  if (payload.storage_path) {
    $("settings-storage-hint").textContent = `stored at ${payload.storage_path}`;
  }
}

function setFeedback(msg, kind) {
  const el = $("settings-feedback");
  el.textContent = msg || "";
  el.classList.remove("ok", "err");
  if (kind) el.classList.add(kind);
  if (msg) {
    setTimeout(() => {
      if (el.textContent === msg) {
        el.textContent = "";
        el.classList.remove("ok", "err");
      }
    }, 3500);
  }
}

async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    if (!r.ok) return;
    renderSettings(await r.json());
  } catch (e) {
    /* network errors are non-fatal here */
  }
}

async function saveSettings() {
  // Only send fields the user actually typed in. Empty input means
  // "leave it alone" (we omit it from the request).
  const body = {};
  let anyTouched = false;
  for (const f of SETTINGS_FIELDS) {
    const raw = $(f.inputId).value;
    if (raw === "") continue; // leave unchanged
    body[f.key] = raw.trim() === "" ? "" : raw.trim();
    anyTouched = true;
  }
  if (!anyTouched) {
    setFeedback("nothing to save", "err");
    return;
  }
  setFeedback("saving…");
  try {
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      setFeedback(`error ${r.status}`, "err");
      return;
    }
    const data = await r.json();
    renderSettings(data);
    setFeedback(`saved (${(data.updated || []).length})`, "ok");
    // Pills depend on /api/status; refresh them so they go green immediately.
    fetchStatus();
  } catch (e) {
    setFeedback("network error", "err");
  }
}

async function clearAllSettings() {
  if (!confirm("Clear all saved API keys on this machine?")) return;
  setFeedback("clearing…");
  try {
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        discogs_token: "", groq_api_key: "", gemini_api_key: "",
      }),
    });
    if (!r.ok) { setFeedback(`error ${r.status}`, "err"); return; }
    renderSettings(await r.json());
    setFeedback("cleared", "ok");
    fetchStatus();
  } catch (e) {
    setFeedback("network error", "err");
  }
}

function wireUI() {
  $("pick").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", (e) => {
    uploadFiles(e.target.files);
    e.target.value = "";
  });

  const dz = $("dropzone");
  dz.addEventListener("dragover", (e) => {
    e.preventDefault();
    dz.classList.add("over");
  });
  dz.addEventListener("dragleave", () => dz.classList.remove("over"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("over");
    uploadFiles(e.dataTransfer.files);
  });

  $("run").addEventListener("click", async () => {
    await fetch("/api/queue/start", { method: "POST" });
  });
  $("stop").addEventListener("click", async () => {
    await fetch("/api/queue/stop", { method: "POST" });
  });
  $("clear").addEventListener("click", async () => {
    await fetch("/api/queue/clear", { method: "POST" });
    state.buffer = [];
    renderLog();
  });
  $("filter-flagged").addEventListener("change", (e) => {
    state.filterFlagged = e.target.checked;
    renderLog();
  });

  $("settings-save").addEventListener("click", saveSettings);
  $("settings-clear").addEventListener("click", clearAllSettings);
  // Submit on Enter from any of the three password inputs
  for (const f of SETTINGS_FIELDS) {
    $(f.inputId).addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        saveSettings();
      }
    });
  }
}

wireUI();
fetchStatus();
loadSettings();
startSSE();
