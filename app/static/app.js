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
const progressPct = $("progress-pct");
const progressLine = $("progress-line");
const aiPill = $("ai-pill");
const discogsPill = $("discogs-pill");
const runPill = $("run-pill");
const outputDirEl = $("output-dir");
const ctClean = $("ct-clean");
const ctCaution = $("ct-caution");
const ctFlagged = $("ct-flagged");

const state = {
  jobs: new Map(), // job_id -> jobObj
  totals: { clean: 0, caution: 0, flagged: 0 },
  running: false,
};

// --- helpers --------------------------------------------------------------

function logLine(text, cls = "") {
  const span = document.createElement("span");
  span.className = "ln" + (cls ? " " + cls : "");
  span.textContent = text;
  logEl.appendChild(span);
  logEl.scrollTop = logEl.scrollHeight;
  // cap log to last ~2000 lines
  while (logEl.childElementCount > 2000) logEl.removeChild(logEl.firstChild);
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

    const state_ = document.createElement("span");
    state_.className = "state " + job.status;
    state_.textContent = labelFor(job);
    li.appendChild(state_);

    if (job.status === "done" && job.output_path) {
      const dl = document.createElement("a");
      dl.className = "link-btn";
      dl.style.fontSize = "11px";
      dl.textContent = "download";
      dl.href = `/api/download/${job.job_id}`;
      li.appendChild(dl);
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
  if (job.status === "running") return `running ${job.processed}/${job.total}`;
  if (job.status === "done") return `done · ${job.flagged}F ${job.cautioned}C ${job.clean}OK`;
  if (job.status === "error") return "error";
  return job.status;
}

function setProgress(processed, total) {
  const pct = total ? Math.floor((processed / total) * 100) : 0;
  progressFill.style.width = pct + "%";
  progressPct.textContent = pct + "%";
}

function updateCounters() {
  ctClean.textContent = state.totals.clean;
  ctCaution.textContent = state.totals.caution;
  ctFlagged.textContent = state.totals.flagged;
}

// --- API ------------------------------------------------------------------

async function refreshStatus() {
  const r = await fetch("/api/status");
  const data = await r.json();

  if (data.ai_configured) {
    aiPill.textContent = `ai: ${data.ai_provider}`;
    aiPill.classList.add("ok");
  } else {
    aiPill.textContent = "ai: rule-based (no key)";
    aiPill.classList.add("warn");
  }
  if (data.discogs_configured) {
    discogsPill.textContent = "discogs: ok";
    discogsPill.classList.add("ok");
  } else {
    discogsPill.textContent = "discogs: missing token";
    discogsPill.classList.add("warn");
  }
  outputDirEl.textContent = "outputs: " + data.output_dir;
  const itunesPill = $("itunes-pill");
  if (itunesPill) {
    itunesPill.textContent = "apple p-line: ok";
    itunesPill.classList.add("ok");
  }

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
      logLine(`\n>> ${ev.job.name}`, "head");
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
      logLine(`  [scan] ${ev.artist}`, "dim");
      break;

    case "artist_done": {
      setProgress(ev.index, ev.total);
      const tag = ev.verdict || "CAUTION";
      let cls = "clean";
      if (tag === "FLAGGED") { cls = "flag"; state.totals.flagged++; }
      else if (tag === "CAUTION") { cls = "caution"; state.totals.caution++; }
      else { cls = "clean"; state.totals.clean++; }
      logLine(`  [${tag.padEnd(7)}] ${ev.artist} -- ${ev.reason || ""}`, cls);
      if (ev.pline && ev.pline !== "not found" && ev.pline !== "error") {
        logLine(`             pline: ${ev.pline}`, "dim");
      }
      if (ev.licensee) {
        logLine(`             licensed to: ${ev.licensee}`, "flag");
      }
      if (ev.flag) logLine(`             flag: ${ev.flag}`, "dim");
      const job = state.jobs.get(ev.job_id);
      if (job) {
        job.processed = ev.index;
        job.total = ev.total;
        if (tag === "FLAGGED") job.flagged = (job.flagged || 0) + 1;
        else if (tag === "CAUTION") job.cautioned = (job.cautioned || 0) + 1;
        else job.clean = (job.clean || 0) + 1;
        renderQueue();
      }
      updateCounters();
      break;
    }

    case "artist_error":
      logLine(`  [ERROR] ${ev.artist}: ${ev.error}`, "err");
      break;

    case "job_done": {
      state.jobs.set(ev.job.job_id, ev.job);
      logLine(
        `  [done] ${ev.job.name} -- ${ev.job.flagged} flagged, ${ev.job.cautioned} caution, ${ev.job.clean} clean`,
        "info"
      );
      renderQueue();
      break;
    }

    case "job_error":
      state.jobs.set(ev.job.job_id, ev.job);
      logLine(`  [job error] ${ev.job.name}: ${ev.job.error}`, "err");
      renderQueue();
      break;

    case "queue_done":
      state.running = false;
      setRunPill("done", "ok");
      progressLine.textContent = "queue complete";
      logLine("\n== queue complete ==", "head");
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

// init
refreshStatus();
connectStream();
logLine("ready. drop a chartmetric csv to begin.", "info");
