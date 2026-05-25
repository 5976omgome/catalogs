// Catalog Audit -- browser UI

const $ = (id) => document.getElementById(id);

const dropzone = $("dropzone");
const fileInput = $("file-input");
const browseBtn = $("browse-btn");
const queueEl = $("queue");
const runBtn = $("run-btn");
const clearBtn = $("clear-btn");
const openOutputBtn = $("open-output-btn");
const cacheClearBtn = $("cache-clear-btn");
const logEl = $("log");
const progressFill = $("progress-fill");
const processedLine = $("processed-line");
const processedPct = $("processed-pct");
const cleanLine = $("clean-line");
const cleanPct = $("clean-pct");
const progressLine = $("progress-line");
const aiPill = $("ai-pill");
const discogsPill = $("discogs-pill");
const itunesPill = $("itunes-pill");
const runPill = $("run-pill");
const outputDirEl = $("output-dir");
const ctClean = $("ct-clean");
const ctFlagged = $("ct-flagged");
const filterToggle = $("filter-flagged-only");

const state = {
  jobs: new Map(),
  totals: { clean: 0, flagged: 0, processed: 0, total: 0 },
  running: false,
  filterFlaggedOnly: false,
};

// --- helpers --------------------------------------------------------------

// We build a lightweight "pending" buffer so toggling the filter doesn't
// lose history.
const logBuffer = [];

function appendLogNode(text, cls, isFlagged) {
  const span = document.createElement("span");
  span.className = "ln" + (cls ? " " + cls : "");
  span.textContent = text;
  span.dataset.flagged = isFlagged ? "1" : "0";
  logEl.appendChild(span);
  // Cap to last 4000 lines
  while (logEl.childElementCount > 4000) logEl.removeChild(logEl.firstChild);
}

function logLine(text, cls = "", isFlagged = false) {
  logBuffer.push({ text, cls, isFlagged });
  if (logBuffer.length > 4000) logBuffer.shift();
  if (state.filterFlaggedOnly && !isFlagged) return;
  appendLogNode(text, cls, isFlagged);
  logEl.scrollTop = logEl.scrollHeight;
}

function rerenderLog() {
  logEl.innerHTML = "";
  for (const { text, cls, isFlagged } of logBuffer) {
    if (state.filterFlaggedOnly && !isFlagged) continue;
    appendLogNode(text, cls, isFlagged);
  }
  logEl.scrollTop = logEl.scrollHeight;
}

function setRunPill(text, cls) {
  runPill.textContent = text;
  runPill.className = "pill " + (cls || "");
}

function renderQueue() {
  queueEl.innerHTML = "";
  for (const job of state.jobs.values()) {
    const li = document.createElement("li");

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = job.name;
    li.appendChild(name);

    const stateEl = document.createElement("span");
    stateEl.className = "state " + job.status;
    stateEl.textContent = labelFor(job);
    li.appendChild(stateEl);

    if (job.status === "done") {
      if (job.output_path) {
        const dl = document.createElement("a");
        dl.className = "link-btn";
        dl.style.fontSize = "11px";
        dl.textContent = "full";
        dl.href = `/api/download/${job.job_id}`;
        li.appendChild(dl);
      }
      if (job.clean_output_path) {
        const dl = document.createElement("a");
        dl.className = "link-btn";
        dl.style.fontSize = "11px";
        dl.textContent = "clean-only";
        dl.href = `/api/download-clean/${job.job_id}`;
        li.appendChild(dl);
      }
    }

    if (job.status === "queued") {
      const x = document.createElement("button");
      x.className = "x";
      x.textContent = "x";
      x.title = "remove from queue";
      x.onclick = () => removeJob(job.job_id);
      li.appendChild(x);
    }

    queueEl.appendChild(li);
  }
}

function labelFor(job) {
  if (job.status === "queued") return "queued";
  if (job.status === "running") return `${job.processed}/${job.total}`;
  if (job.status === "done") return `done · ${job.clean} clean / ${job.total}`;
  if (job.status === "error") return "error";
  return job.status;
}

function setProgress(processed, total) {
  state.totals.processed = processed;
  state.totals.total = total;
  const pct = total ? Math.floor((processed / total) * 100) : 0;
  progressFill.style.width = pct + "%";
  processedLine.textContent = `${processed} of ${total} processed`;
  processedPct.textContent = pct + "%";
}

function updateCounters() {
  ctClean.textContent = state.totals.clean;
  ctFlagged.textContent = state.totals.flagged;
  const done = state.totals.clean + state.totals.flagged;
  if (done <= 0) {
    cleanLine.textContent = "— of — clean";
    cleanPct.textContent = "—";
    return;
  }
  const cleanPctVal = Math.floor((state.totals.clean / done) * 100);
  cleanLine.textContent = `${state.totals.clean} of ${done} clean`;
  cleanPct.textContent = cleanPctVal + "%";
}

// --- API ------------------------------------------------------------------

async function refreshStatus() {
  const r = await fetch("/api/status");
  const data = await r.json();

  if (data.ai_configured) {
    aiPill.textContent = `ai: ${data.ai_provider}`;
    aiPill.className = "pill ok";
  } else {
    aiPill.textContent = "ai: rule-based (deterministic)";
    aiPill.className = "pill ok";
  }
  if (data.discogs_configured) {
    discogsPill.textContent = "discogs: ok";
    discogsPill.className = "pill ok";
  } else {
    discogsPill.textContent = "discogs: missing token";
    discogsPill.className = "pill warn";
  }
  if (itunesPill) {
    itunesPill.textContent = "apple p-line: ok";
    itunesPill.className = "pill ok";
  }
  outputDirEl.textContent = "outputs: " + data.output_dir;

  state.jobs.clear();
  for (const j of data.jobs) state.jobs.set(j.job_id, j);
  renderQueue();
}

async function uploadFiles(files) {
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const r = await fetch("/api/upload", { method: "POST", body: fd });
  const data = await r.json();
  for (const j of data.added || []) {
    state.jobs.set(j.job_id, j);
    logLine(`+ queued: ${j.name}`, "info");
  }
  renderQueue();
}

async function removeJob(jobId) {
  await fetch(`/api/jobs/${jobId}/remove`, { method: "POST" });
}

async function startQueue() {
  if (state.running) return;
  // Reset rolling totals for a fresh run
  state.totals.clean = 0;
  state.totals.flagged = 0;
  state.totals.processed = 0;
  state.totals.total = 0;
  setProgress(0, 0);
  updateCounters();
  const r = await fetch("/api/run", { method: "POST" });
  const data = await r.json();
  if (!data.started) {
    logLine("(queue already running)", "dim");
  }
}

async function clearFinished() {
  await fetch("/api/jobs/clear-finished", { method: "POST" });
}

async function openOutput() {
  await fetch("/api/open-output", { method: "POST" });
}

async function clearCache() {
  const r = await fetch("/api/cache/clear", { method: "POST" });
  const data = await r.json();
  logLine(`cache cleared: ${data.cleared} entries`, "info");
}

// --- SSE ------------------------------------------------------------------

function connectStream() {
  const es = new EventSource("/api/stream");
  es.onmessage = (msg) => {
    let ev;
    try { ev = JSON.parse(msg.data); } catch { return; }
    handleEvent(ev);
  };
  es.onerror = () => {
    setRunPill("disconnected", "err");
    setTimeout(connectStream, 2000);
  };
}

function truncate(s, n) {
  if (!s) return "";
  s = String(s);
  return s.length > n ? s.slice(0, n - 1) + "\u2026" : s;
}

function handleEvent(ev) {
  switch (ev.event) {
    case "snapshot":
      state.jobs.clear();
      for (const j of ev.jobs) state.jobs.set(j.job_id, j);
      renderQueue();
      break;

    case "job_added":
      state.jobs.set(ev.job.job_id, ev.job);
      renderQueue();
      break;

    case "job_removed":
      state.jobs.delete(ev.job_id);
      renderQueue();
      break;

    case "queue_cleared":
      for (const [k, j] of [...state.jobs.entries()]) {
        if (j.status === "done" || j.status === "error") state.jobs.delete(k);
      }
      renderQueue();
      break;

    case "job_started": {
      state.jobs.set(ev.job.job_id, ev.job);
      state.running = true;
      setRunPill("running", "ok");
      logLine(`\n>> ${ev.job.name}`, "head", true);
      progressLine.textContent = `running: ${ev.job.name}`;
      setProgress(0, 0);
      renderQueue();
      break;
    }

    case "job_total":
      progressLine.textContent = `${ev.total} artists to scan`;
      setProgress(0, ev.total);
      break;

    case "artist_start":
      progressLine.textContent = `[${ev.index}/${ev.total}] ${ev.artist}`;
      logLine(`  [scan] ${ev.artist}`, "dim", false);
      break;

    case "artist_done": {
      setProgress(ev.index, ev.total);
      const tag = ev.verdict || "FLAGGED";
      const isClean = tag === "CLEAN";
      const cls = isClean ? "clean" : "flag";
      if (isClean) state.totals.clean++; else state.totals.flagged++;

      logLine(
        `  [${tag.padEnd(7)}] ${ev.artist} \u2014 ${truncate(ev.reason, 140)}`,
        cls, !isClean
      );
      if (ev.pline && ev.pline !== "not found" && ev.pline !== "error") {
        logLine(`             pline: ${truncate(ev.pline, 140)}`, "dim", !isClean);
      }
      if (ev.licensee) {
        logLine(`             licensed-to: ${ev.licensee}`, "flag", true);
      }
      if (ev.earliest_year) {
        logLine(`             first release: ${ev.earliest_year}`, "dim", !isClean);
      }
      if (ev.self_imprint === "YES") {
        logLine(`             self-imprint suspected (manual review)`, "flag", true);
      }
      if (ev.flag) {
        logLine(`             flag: ${truncate(ev.flag, 140)}`, "dim", !isClean);
      }

      const job = state.jobs.get(ev.job_id);
      if (job) {
        job.processed = ev.index;
        job.total = ev.total;
        job.flagged = ev.running_flagged;
        job.clean = ev.running_clean;
        renderQueue();
      }
      updateCounters();
      break;
    }

    case "artist_error":
      logLine(`  [ERROR] ${ev.artist}: ${ev.error}`, "err", true);
      break;

    case "job_done": {
      state.jobs.set(ev.job.job_id, ev.job);
      const j = ev.job;
      logLine(
        `  [done] ${j.name} \u2014 ${j.clean} clean / ${j.total} total ` +
        `(${j.flagged} flagged)`,
        "info", true
      );
      renderQueue();
      break;
    }

    case "job_error":
      state.jobs.set(ev.job.job_id, ev.job);
      logLine(`  [job error] ${ev.job.name}: ${ev.job.error}`, "err", true);
      renderQueue();
      break;

    case "queue_done":
      state.running = false;
      setRunPill("done", "ok");
      progressLine.textContent = "queue complete";
      logLine("\n== queue complete ==", "head", true);
      break;
  }
}

// --- wiring ---------------------------------------------------------------

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("drag");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag");
  const files = [...e.dataTransfer.files].filter(f => f.name.toLowerCase().endsWith(".csv"));
  uploadFiles(files);
});

browseBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => uploadFiles([...fileInput.files]));

runBtn.addEventListener("click", startQueue);
clearBtn.addEventListener("click", clearFinished);
openOutputBtn.addEventListener("click", openOutput);
cacheClearBtn.addEventListener("click", clearCache);

if (filterToggle) {
  filterToggle.addEventListener("change", () => {
    state.filterFlaggedOnly = filterToggle.checked;
    rerenderLog();
  });
}

// init
refreshStatus();
connectStream();
logLine("ready. drop a chartmetric csv to begin.", "info", true);
