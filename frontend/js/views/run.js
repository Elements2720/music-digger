/* RUN tab: launch any CLI-equivalent job and watch live SSE progress. */

import { api, subscribeJob } from "../api.js";
import { emit } from "../state.js";
import { el, renderKv } from "../ui.js";
import { fmtMemory } from "../format.js";

const FIELDS = {
  index: [
    { key: "limit", label: "Limit (0 = all)", type: "number", value: 500, min: 0 },
    { key: "batch_size", label: "GPU batch size (max 48)", type: "number", value: 16, min: 1, max: 48 },
    { key: "turbo", label: "Turbo mode — 10 workers · batch 48 · 24 downloads", type: "checkbox" },
    { key: "reindex", label: "Reindex already-embedded tracks", type: "checkbox" },
    { key: "retry_failed", label: "Retry previously failed tracks", type: "checkbox" },
  ],
  "import-local": [
    { key: "folder_path", label: "Folder path", type: "text", placeholder: "D:\\Music\\Techno or /home/user/music", required: true },
    { key: "recursive", label: "Include subfolders", type: "checkbox", value: true },
    { key: "seed_artists", label: "Seed artists for discovery", type: "checkbox", value: true },
    { key: "batch_size", label: "GPU batch size (max 48)", type: "number", value: 16, min: 1, max: 48 },
    { key: "reindex", label: "Reindex existing", type: "checkbox", value: false },
  ],
  "seed-crawl": [
    { key: "electronic_limit", label: "Electronic seeds", type: "number", value: 1000, min: 0 },
    { key: "general_limit", label: "General seeds", type: "number", value: 300, min: 0 },
    { key: "max_depth", label: "Deezer related-artist depth", type: "number", value: 2, min: 0, max: 5 },
    { key: "use_local_seeds", label: "Use my local library artists as roots", type: "checkbox", value: false },
    { key: "use_liked_seeds", label: "Use my Liked Artists as priority roots", type: "checkbox", value: false },
  ],
  "seed-llm": [
    { key: "genre", label: "Genre focus", type: "text", value: "Melodic Techno & Afro House", placeholder: "comma-separated genres" },
    { key: "count", label: "Artists to request", type: "number", value: 100, min: 1, max: 1000 },
  ],
  "seed-itunes": [
    { key: "terms", label: "Keywords / labels (comma-separated, blank = built-in techno list)", type: "text", placeholder: "hypnotic techno, Drumcode, PoleGroup..." },
    { key: "tracks_per_term", label: "Tracks per term (max 200)", type: "number", value: 200, min: 1, max: 200 },
    { key: "min_year", label: "Minimum release year (e.g. 2018)", type: "number", min: 1900, max: 2100 },
    { key: "electronic_only", label: "Electronic only (filter pop/rock/jazz)", type: "checkbox", value: true },
    { key: "expand_compilations", label: "Expand VA compilations", type: "checkbox", value: true },
    { key: "save_tracks", label: "Save tracks immediately (ready for index)", type: "checkbox", value: true },
  ],
  "fetch-metadata": [
    { key: "artists_limit", label: "Artists this run", type: "number", value: 50, min: 1 },
    { key: "tracks_per_artist", label: "Tracks per artist (max 200)", type: "number", value: 200, min: 1, max: 200 },
    { key: "min_year", label: "Minimum release year (e.g. 2018)", type: "number", min: 1900, max: 2100 },
    { key: "electronic_only", label: "Electronic only (filter pop/rock/jazz)", type: "checkbox", value: false },
    { key: "retry_failed", label: "Retry seeds marked failed", type: "checkbox" },
  ],
  "fetch-artist": [
    { key: "artist", label: "Artist name", type: "text", placeholder: "e.g. Enrico Sangiuliano or Adam Beyer", required: true },
    { key: "tracks_per_artist", label: "Tracks to fetch (max 200)", type: "number", value: 50, min: 1, max: 200 },
    { key: "min_year", label: "Minimum release year (e.g. 2018)", type: "number", min: 1900, max: 2100 },
    { key: "electronic_only", label: "Electronic only (filter pop/rock/jazz)", type: "checkbox", value: false },
    { key: "auto_index", label: "Auto-index audio embeddings immediately", type: "checkbox", value: true },
    { key: "discover_related", label: "Discover related artists (Deezer graph)", type: "checkbox", value: false },
    { key: "related_limit", label: "Related artists limit", type: "number", value: 10, min: 1, max: 50 },
  ],
  "analyze-set": [
    { key: "source", label: "Set URL or local audio file", type: "text", placeholder: "https://youtube.com/watch?v=… or D:\\sets\\set.mp3", required: true },
    { key: "shazam", label: "Shazam unidentified passages", type: "checkbox", value: true },
    { key: "comments", label: "Parse tracklist from comments", type: "checkbox", value: true },
    { key: "keep_audio", label: "Keep downloaded audio in cache", type: "checkbox" },
    { key: "cookies_file", label: "cookies.txt (optional)", type: "text", placeholder: "C:\\path\\cookies.txt" },
    { key: "cookies_from_browser", label: "Cookies from browser (optional)", type: "text", placeholder: "firefox, edge, chrome…" },
  ],
};

let mounted = false;
let source = null;
let lastStatus = null;
let currentJobId = null;
let recentMessages = [];

function $(id) {
  return document.getElementById(id);
}

function updateJobLog(job) {
  const logEl = $("job-log");
  if (!logEl) return;
  if (!job || job.status === "idle") {
    currentJobId = null;
    recentMessages = [];
    logEl.replaceChildren();
    return;
  }
  if (job.id && job.id !== currentJobId) {
    currentJobId = job.id;
    recentMessages = [];
    logEl.replaceChildren();
  }
  const msg = job.message ? job.message.trim() : "";
  if (msg && (!recentMessages.length || recentMessages[recentMessages.length - 1] !== msg)) {
    recentMessages.push(msg);
    if (recentMessages.length > 10) {
      recentMessages.shift();
    }
    logEl.replaceChildren(
      ...recentMessages.map((m) => el("div", { class: "job-log-item", text: m }))
    );
    logEl.scrollTop = logEl.scrollHeight;
  }
}

async function renderParams(kind) {
  const wrap = $("job-params");
  wrap.replaceChildren();
  for (const field of FIELDS[kind] ?? []) {
    if (field.type === "checkbox") {
      const input = el("input", { type: "checkbox", id: `job-${field.key}` });
      input.checked = Boolean(field.value);
      wrap.append(
        el("label", { class: "check" }, [input, document.createTextNode(` ${field.label}`)])
      );
      continue;
    }
    const input = el("input", {
      class: `input${field.type === "number" ? " mono" : ""}`,
      type: field.type,
      id: `job-${field.key}`,
      placeholder: field.placeholder,
      value: field.value ?? "",
      min: field.min,
      max: field.max,
      required: field.required,
    });
    wrap.append(
      el("label", { class: "field" }, [el("span", { text: field.label }), input])
    );
  }

  if (kind === "seed-itunes") {
    try {
      const data = await api.genrePresets();
      if (data && data.presets && data.presets.length > 0) {
        const chipsContainer = el("div", { class: "preset-chips-wrap", style: "margin-top: 8px;" }, [
          el("div", { class: "dim", style: "font-size: 11px; margin-bottom: 4px;", text: "Quick Techno Presets (click to add):" }),
        ]);
        const chipsList = el("div", { class: "cell-badges", style: "display: flex; flex-wrap: wrap; gap: 4px;" });
        for (const preset of data.presets.slice(0, 16)) {
          const chip = el("button", {
            type: "button",
            class: "chip preset-chip",
            style: "cursor: pointer; border: 1px solid #2a2a2e; background: #18181b;",
            text: `+ ${preset}`,
          });
          chip.addEventListener("click", () => {
            const input = $("job-terms");
            if (!input) return;
            const current = input.value.trim();
            if (!current) {
              input.value = preset;
            } else {
              const parts = current.split(",").map((s) => s.trim().toLowerCase());
              if (!parts.includes(preset.toLowerCase())) {
                input.value = `${current}, ${preset}`;
              }
            }
          });
          chipsList.append(chip);
        }
        chipsContainer.append(chipsList);
        wrap.append(chipsContainer);
      }
    } catch {
      // ignore
    }
  }
}

function collect(kind) {
  const params = {};
  for (const field of FIELDS[kind] ?? []) {
    const input = $(`job-${field.key}`);
    if (!input) continue;
    if (field.type === "checkbox") params[field.key] = input.checked;
    else if (field.type === "number") params[field.key] = Number(input.value);
    else {
      const value = input.value.trim();
      if (value) params[field.key] = value;
    }
  }
  return params;
}

export function mount() {
  if (mounted) return;
  mounted = true;

  const select = $("job-kind");
  renderParams(select.value);
  select.addEventListener("change", () => renderParams(select.value));

  $("job-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await launch(select.value, collect(select.value));
  });

  $("job-cancel").addEventListener("click", async () => {
    try {
      const { cancelled } = await api.cancelJob();
      if (!cancelled) emit("toast", "No job is running");
    } catch (error) {
      emit("toast", error.message);
    }
  });

  refreshCurrent();
}

export async function launch(kind, params) {
  const select = $("job-kind");
  if (select.value !== kind) {
    select.value = kind;
    renderParams(kind);
  }
  $("job-error").textContent = "";
  try {
    const { job } = await api.startJob(kind, params);
    renderJob(job);
    connect();
  } catch (error) {
    $("job-error").textContent = error.message;
    emit("toast", error.message);
  }
}

function connect() {
  source?.close();
  source = subscribeJob(handleEvent, () => {
    source = null;
  });
}

function handleEvent(event) {
  if (event.type === "state") {
    if (event.job) renderJob(event.job);
    return;
  }
  if (event.type === "progress") {
    renderJob(event.job);
    renderTelemetry(event.speed, event.memory, event.job);
    return;
  }
  renderJob(event.job);
  renderResult(event.job);
  source = null;
  emit("job:finished", event.job);
}

function renderJob(job) {
  if (!job) {
    $("job-idle").classList.remove("hidden");
    $("job-live").classList.add("hidden");
    $("job-cancel").classList.add("hidden");
    updateJobLog(null);
    return;
  }

  $("job-idle").classList.add("hidden");
  $("job-live").classList.remove("hidden");
  $("job-kind-label").textContent = job.kind;
  $("job-status-badge").textContent = job.status;
  $("job-status-badge").className = `badge ${job.status}`;
  $("job-stage").textContent = job.stage || "—";
  $("job-processed").textContent = job.total
    ? `${job.processed} / ${job.total}`
    : String(job.processed);
  $("job-failed").textContent = String(job.failed ?? 0);
  $("job-message").textContent = job.message || "";
  $("job-cancel").classList.toggle("hidden", job.status !== "running");
  updateJobLog(job);

  const fill = $("job-progress");
  if (job.status === "running" && (!job.total || job.total <= 0)) {
    fill.classList.add("indeterminate");
    fill.style.width = "";
  } else {
    fill.classList.remove("indeterminate");
    const percent = job.total ? Math.min(100, (job.processed / job.total) * 100) : job.status === "done" ? 100 : 0;
    fill.style.width = `${percent}%`;
  }

  if (job.status !== "running" && lastStatus === "running") {
    renderResult(job);
  }
  lastStatus = job.status;
}

function renderTelemetry(speed, memory, job) {
  const unit = job?.kind === "analyze-set" ? "passages/s" : "tracks/s";
  $("job-speed").textContent =
    speed === null || speed === undefined ? "—" : `${speed} ${unit}`;
  if (!memory) return;
  $("job-vram").textContent =
    memory.vram_total_mb === null || memory.vram_total_mb === undefined
      ? "—"
      : `${fmtMemory(memory.vram_free_mb)} free`;
  $("job-ram").textContent =
    memory.ram_total_mb === null || memory.ram_total_mb === undefined
      ? "—"
      : `${fmtMemory(memory.ram_free_mb)} free`;
}

function renderResult(job) {
  const panel = $("job-result-panel");
  const body = $("job-result");
  panel.classList.remove("hidden");
  if (!job) return;
  if (job.status === "error") {
    body.replaceChildren(el("div", { class: "empty", text: job.error || "Job failed" }));
    return;
  }
  if (job.status === "cancelled") {
    body.replaceChildren(el("div", { class: "empty", text: "Job cancelled." }));
    return;
  }
  const rows = [];
  for (const [key, value] of Object.entries(job.result ?? {})) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      for (const [innerKey, innerValue] of Object.entries(value)) {
        rows.push([`${key}.${innerKey}`, innerValue]);
      }
    } else {
      rows.push([key, value]);
    }
  }
  if (rows.length === 0) {
    body.replaceChildren(el("div", { class: "empty", text: "Finished with no result payload." }));
    return;
  }
  renderKv(body, rows);
}

async function refreshCurrent() {
  try {
    const { job } = await api.currentJob();
    if (!job) return;
    renderJob(job);
    if (job.status === "running") connect();
    else renderResult(job);
  } catch {
    /* the health badge already reports a dead backend */
  }
}
