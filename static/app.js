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
    let txt = it.filename;
    if (it.status === "running") txt += `  ${it.processed}/${it.total}`;
    if (it.status === "done") {
      txt += `  ✓  ${it.clean}/${it.total} clean`;
    }
    if (it.status === "error") txt += `  ✕  ${it.error}`;
    li.textContent = txt;
    if (it.status === "done" && it.output_path) {
      const a = document.createElement("a");
      a.href = `/api/download/${it.item_id}`;
      a.textContent = "download";
      a.style.color = "#00ff41";
      a.style.fontSize = "10px";
      a.style.marginLeft = "12px";
      li.appendChild(a);
    }
    ul.appendChild(li);
  }
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
      });
      logLine(`[DONE] ${ev.clean}/${ev.total} clean -> ${ev.output_path}`, "line-clean");
      aggregate();
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
  $("clear").addEventListener("click", async () => {
    await fetch("/api/queue/clear", { method: "POST" });
    state.buffer = [];
    renderLog();
  });
  $("filter-flagged").addEventListener("change", (e) => {
    state.filterFlagged = e.target.checked;
    renderLog();
  });
}

wireUI();
fetchStatus();
startSSE();
