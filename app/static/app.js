"use strict";

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Status pills
// ---------------------------------------------------------------------------
async function refreshStatus() {
  try {
    const r = await fetch("/api/status");
    const s = await r.json();
    const setPill = (el, label, ok) => {
      el.textContent = `${label}: ${ok ? "set" : "not set"}`;
      el.classList.toggle("ok", ok);
      el.classList.toggle("bad", !ok);
    };
    setPill($("pill-discogs"), "discogs", s.discogs_set);
    const aiOk = s.groq_set || s.gemini_set;
    let aiText = "ai: rule-based";
    if (s.groq_set && s.gemini_set) aiText = "ai: groq+gemini";
    else if (s.groq_set) aiText = "ai: groq";
    else if (s.gemini_set) aiText = "ai: gemini";
    $("pill-ai").textContent = aiText;
    $("pill-ai").classList.toggle("ok", aiOk);
    $("pill-ai").classList.toggle("bad", !aiOk);
  } catch (e) {
    console.error("status fetch failed", e);
  }
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    const s = await r.json();
    const setPrev = (id, info) => {
      const el = $(id);
      el.textContent = info.set ? `current: ${info.preview}` : "not set";
    };
    setPrev("prev-discogs", s.discogs_token);
    setPrev("prev-groq", s.groq_api_key);
    setPrev("prev-gemini", s.gemini_api_key);
  } catch (e) {
    console.error("settings load failed", e);
  }
}

async function saveKeys() {
  const body = {};
  const d = $("key-discogs").value.trim();
  const g = $("key-groq").value.trim();
  const m = $("key-gemini").value.trim();
  if (d) body.discogs_token = d;
  if (g) body.groq_api_key = g;
  if (m) body.gemini_api_key = m;
  if (Object.keys(body).length === 0) {
    $("keys-msg").textContent = "No new values entered.";
    return;
  }
  $("keys-msg").textContent = "Saving…";
  const r = await fetch("/api/settings", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  if (r.ok) {
    $("keys-msg").textContent = "Saved.";
    $("key-discogs").value = "";
    $("key-groq").value = "";
    $("key-gemini").value = "";
    loadSettings();
    refreshStatus();
  } else {
    const e = await r.json();
    $("keys-msg").textContent = "Error: " + (e.error || "save failed");
  }
}

async function clearKeys() {
  if (!confirm("Clear ALL stored API keys?")) return;
  await fetch("/api/settings/clear", {method: "POST"});
  $("keys-msg").textContent = "Cleared.";
  loadSettings();
  refreshStatus();
}

// ---------------------------------------------------------------------------
// Queue
// ---------------------------------------------------------------------------
const queueState = {};  // id -> dom element

function renderItem(item) {
  const existing = queueState[item.id];
  if (existing) {
    existing.remove();
    delete queueState[item.id];
  }
  const li = document.createElement("li");
  li.dataset.id = item.id;
  if (item.status === "done") li.classList.add("done");
  else if (item.status === "stopped") li.classList.add("stopped");
  else if (item.status === "error") li.classList.add("error");

  const head = document.createElement("div");
  head.className = "qhead";
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = item.filename;
  const stat = document.createElement("span");
  stat.className = "stat";
  stat.textContent = item.status.toUpperCase();
  head.appendChild(name);
  head.appendChild(stat);
  li.appendChild(head);

  if (item.total > 0) {
    const bar = document.createElement("div");
    bar.className = "qbar";
    const fill = document.createElement("span");
    const pct = item.total ? Math.floor(100 * item.processed / item.total) : 0;
    fill.style.width = pct + "%";
    bar.appendChild(fill);
    li.appendChild(bar);

    const counts = document.createElement("div");
    counts.className = "qcounts";
    const cleanPct = item.processed ? Math.floor(100 * item.keep / item.processed) : 0;
    counts.innerHTML =
      `<div>${item.processed} of ${item.total} processed (${pct}%)</div>` +
      `<div>${item.keep} of ${item.processed} keep (${cleanPct}%) · ${item.review} review · ${item.drop} drop</div>`;
    li.appendChild(counts);
  }

  if (item.has_output) {
    const exp = document.createElement("div");
    exp.className = "qexports";
    const mk = (label, cls, href, suggestedName) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = label;
      if (cls) btn.className = cls;
      btn.addEventListener("click", () => downloadFromUrl(btn, href, suggestedName));
      return btn;
    };
    const stem = item.filename.replace(/\.(csv|tsv)$/i, "");
    exp.appendChild(mk("Download KEEP",   "btn-export keep",   `/api/export/${item.id}/keep`,   `${stem}-keep.xlsx`));
    exp.appendChild(mk("Download REVIEW", "btn-export review", `/api/export/${item.id}/review`, `${stem}-review.xlsx`));
    exp.appendChild(mk("Download DROPS",  "btn-export drops",  `/api/export/${item.id}/drops`,  `${stem}-drops.xlsx`));
    exp.appendChild(mk("Download ALL",    "btn-export all",    `/api/export/${item.id}/all`,    `${stem}-all.xlsx`));
    exp.appendChild(mk("Download FULL",   "btn-export full",   `/api/download/${item.id}`,      `${stem}Output.xlsx`));
    li.appendChild(exp);
  }

  $("queue").appendChild(li);
  queueState[item.id] = li;
}

// ---------------------------------------------------------------------------
// Downloads — fetch as Blob, prompt Save As (with location picker on Chrome/Edge)
// ---------------------------------------------------------------------------
async function downloadFromUrl(btn, url, suggestedName) {
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Preparing…";
  try {
    const r = await fetch(url);
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`;
      try {
        const j = await r.json();
        if (j && j.error) msg = j.error;
      } catch { /* ignore */ }
      btn.textContent = originalLabel;
      btn.disabled = false;
      logLine(`[download error] ${suggestedName}: ${msg}`, "bad");
      alert(`Download failed: ${msg}`);
      return;
    }
    // Pull a sensible filename out of Content-Disposition if present
    const cd = r.headers.get("Content-Disposition") || "";
    const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd);
    const filename = (match && decodeURIComponent(match[1].replace(/"$/, ""))) || suggestedName;

    const blob = await r.blob();

    // Best path on Chrome/Edge: actual native Save dialog where the user
    // picks the folder. Falls through to <a download> on Safari/Firefox.
    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: filename,
          types: [{
            description: "Excel spreadsheet",
            accept: {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"]},
          }],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        btn.textContent = "Saved ✓";
        logLine(`[saved] ${filename}`, "ok");
        setTimeout(() => { btn.textContent = originalLabel; btn.disabled = false; }, 1500);
        return;
      } catch (e) {
        if (e && e.name === "AbortError") {
          // User cancelled the picker — restore button and bail silently.
          btn.textContent = originalLabel;
          btn.disabled = false;
          return;
        }
        // Any other error: fall through to the <a download> path
        console.warn("showSaveFilePicker failed, falling back:", e);
      }
    }

    // Fallback: <a download>. Browser uses its configured download
    // location, OR shows Save As if the user has "Always ask" enabled.
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);

    btn.textContent = "Downloaded ✓";
    logLine(`[downloaded] ${filename}`, "ok");
    setTimeout(() => { btn.textContent = originalLabel; btn.disabled = false; }, 1500);
  } catch (err) {
    console.error("download failed", err);
    btn.textContent = originalLabel;
    btn.disabled = false;
    logLine(`[download error] ${err.message || err}`, "bad");
    alert(`Download failed: ${err.message || err}`);
  }
}

// ---------------------------------------------------------------------------
// Log
// ---------------------------------------------------------------------------
function logLine(text, cls) {
  const log = $("log");
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = text + "\n";
  log.appendChild(span);
  log.scrollTop = log.scrollHeight;
}

// ---------------------------------------------------------------------------
// SSE
// ---------------------------------------------------------------------------
function startStream() {
  const es = new EventSource("/api/stream");
  es.onmessage = (msg) => {
    let data;
    try { data = JSON.parse(msg.data); }
    catch { return; }
    handleEvent(data);
  };
  es.onerror = () => {
    logLine("[stream] disconnected, retrying...", "bad");
    es.close();
    setTimeout(startStream, 2000);
  };
}

function handleEvent(ev) {
  if (ev.type === "snapshot") {
    $("queue").innerHTML = "";
    Object.keys(queueState).forEach(k => delete queueState[k]);
    (ev.items || []).forEach(renderItem);
  } else if (ev.type === "item_added") {
    renderItem(ev.item);
    logLine(`[+] ${ev.item.filename}`);
  } else if (ev.type === "item_started") {
    renderItem(ev.item);
    logLine(`[run] ${ev.item.filename}`);
  } else if (ev.type === "artist_done") {
    const cls = ev.status === "KEEP" ? "ok" : (ev.status === "REVIEW" ? "review" : "bad");
    logLine(`[${ev.status}] ${ev.artist} — ${ev.status_reason}`, cls);
    // partial-update progress bar
    const li = queueState[ev.item_id];
    if (li) {
      const fill = li.querySelector(".qbar > span");
      const pct = ev.total ? Math.floor(100 * ev.processed / ev.total) : 0;
      if (fill) fill.style.width = pct + "%";
      const counts = li.querySelector(".qcounts");
      if (counts) {
        const cleanPct = ev.processed ? Math.floor(100 * ev.keep / ev.processed) : 0;
        counts.innerHTML =
          `<div>${ev.processed} of ${ev.total} processed (${pct}%)</div>` +
          `<div>${ev.keep} of ${ev.processed} keep (${cleanPct}%) · ${ev.review} review · ${ev.drop} drop</div>`;
      }
    }
  } else if (ev.type === "item_done") {
    renderItem(ev.item);
    logLine(`[done] ${ev.item.filename}: keep=${ev.item.keep} review=${ev.item.review} drop=${ev.item.drop}`, "ok");
  } else if (ev.type === "item_stopped") {
    renderItem(ev.item);
    logLine(`[stopped] ${ev.item.filename}: ${ev.item.processed}/${ev.item.total} processed`, "review");
  } else if (ev.type === "item_error") {
    renderItem(ev.item);
    logLine(`[error] ${ev.item.filename}: ${ev.item.error}`, "bad");
  } else if (ev.type === "queue_done") {
    logLine("[queue done]", "ok");
  } else if (ev.type === "cleared") {
    // server says queue cleared; rebuild from a fresh status fetch
    fetch("/api/stream").then(() => {});
  }
}

// ---------------------------------------------------------------------------
// Wire-up
// ---------------------------------------------------------------------------
async function uploadFile() {
  const input = $("file-input");
  if (!input.files || !input.files.length) {
    alert("Pick a CSV first");
    return;
  }
  const fd = new FormData();
  fd.append("file", input.files[0]);
  const r = await fetch("/api/upload", {method: "POST", body: fd});
  if (!r.ok) {
    const e = await r.json();
    alert("Upload failed: " + (e.error || r.statusText));
    return;
  }
  input.value = "";
}

async function runQueue() {
  await fetch("/api/queue/start", {method: "POST"});
}

async function stopQueue() {
  await fetch("/api/queue/stop", {method: "POST"});
  logLine("[stop requested] finishing current artist…", "review");
}

async function clearQueue() {
  await fetch("/api/queue/clear", {method: "POST"});
  $("queue").innerHTML = "";
  Object.keys(queueState).forEach(k => delete queueState[k]);
}

document.addEventListener("DOMContentLoaded", () => {
  $("btn-upload").addEventListener("click", uploadFile);
  $("btn-run").addEventListener("click", runQueue);
  $("btn-stop").addEventListener("click", stopQueue);
  $("btn-clear").addEventListener("click", clearQueue);
  $("btn-save-keys").addEventListener("click", saveKeys);
  $("btn-clear-keys").addEventListener("click", clearKeys);
  refreshStatus();
  loadSettings();
  startStream();
});
