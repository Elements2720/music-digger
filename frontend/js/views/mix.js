/* Mix Analyzer: analyze a DJ mix (URL or local file) via the analyze-set job.
 * Shows the passage timeline plus per-passage candidate matches.
 */

import { api, subscribeJob } from "../api.js";
import { emptyHTML, errorHTML, bindRetries, esc, toast } from "../ui.js";
import { trackRowHTML, bindTrackRows } from "../components.js";

let source = null;
let analyzeParams = null;

function fmtClock(sec) {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
}

function setProgress(done, total, message, status = "running") {
  const fill = document.getElementById("mix-fill");
  const statusEl = document.getElementById("mix-status");
  const cancel = document.getElementById("mix-cancel");
  const pct = total > 0 ? (done / total) * 100 : 0;
  fill.style.width = `${pct}%`;
  fill.parentElement.setAttribute("aria-valuenow", String(pct));
  statusEl.textContent = message ?? `${status} — ${pct}%`;
  cancel.disabled = status !== "running";
}

function timelineHTML(passages) {
  if (!passages.length) return emptyHTML("No passages", "The mix produced no segments.");
  const total = passages[passages.length - 1].end_seconds || 1;
  let out = `<div class="timeline">`;
  for (const p of passages) {
    const left = (p.start_seconds / total) * 100;
    const width = Math.max(1.5, ((p.end_seconds - p.start_seconds) / total) * 100);
    const cls = p.exact_id_match ? "seg exact" : "seg";
    out += `<button class="${cls}" style="left:${left}%;width:${width}%" data-seg="${esc(JSON.stringify(p))}" title="${esc(p.exact_id_display_name ?? "unknown")} — ${fmtClock(p.start_seconds)}">`;
    if (p.bpm) out += `<span class="seg-bpm">${p.bpm}</span>`;
    out += `</button>`;
  }
  out += `</div><p class="mono">${passages.length} passages · click one to inspect its matches</p>`;
  return out;
}

function passageDetailHTML(p) {
  const rows = (p.matches ?? []).map((m) => ({ ...m.track, similarity: m.similarity }));
  const head = `
  <div class="passage-head">
    <span class="t-meta primary">${fmtClock(p.start_seconds)} → ${fmtClock(p.end_seconds)}</span>
    <span class="t-meta">${p.bpm != null ? p.bpm + " bpm" : "bpm —"}</span>
    ${p.key ? `<span class="key-badge">${esc(p.key)}</span>` : ""}
    ${p.exact_id_match ? `<span class="chip chip-ok">EXACT: ${esc(p.exact_id_display_name ?? "")}</span>` : `<span class="chip">no exact id</span>`}
  </div>`;
  if (!rows.length) return `${head}${emptyHTML("No candidate matches", "Widen the catalog or run Index.")}`;
  return `${head}<div class="track-list">${rows.map((t) => trackRowHTML(t, { similarity: t.similarity })).join("")}</div>`;
}

function renderResult(detail) {
  const timeline = document.getElementById("mix-timeline");
  const list = document.getElementById("mix-passages");
  const passages = detail?.passages ?? [];
  timeline.innerHTML = timelineHTML(passages);
  timeline.querySelectorAll("[data-seg]").forEach((btn) =>
    btn.addEventListener("click", () => {
      let p;
      try {
        p = JSON.parse(btn.dataset.seg);
      } catch {
        return;
      }
      list.innerHTML = passageDetailHTML(p);
      bindTrackRows(list, (p.matches ?? []).map((m) => ({ ...m.track, similarity: m.similarity })));
    }),
  );
  // auto-show first passage
  const first = passages[0];
  if (first) {
    list.innerHTML = passageDetailHTML(first);
    bindTrackRows(list, (first.matches ?? []).map((m) => ({ ...m.track, similarity: m.similarity })));
  } else {
    list.innerHTML = emptyHTML("No passages", "");
  }
}

function bindJobEvents(handle) {
  handle.addEventListener("progress", (event) => {
    const job = event.detail?.job ?? {};
    setProgress(job.processed ?? 0, job.total ?? 0, job.message ?? null, job.status ?? "running");
  });
  handle.addEventListener("state", (event) => {
    const job = event.detail?.job ?? {};
    if (["done", "failed", "cancelled"].includes(job.status)) {
      setProgress(job.processed ?? 1, job.total ?? 1, job.message ?? `Job ${job.status}`, job.status);
      if (job.status === "failed") toast(job.message ?? "Analysis failed", "error", 8000);
    }
  });
  handle.addEventListener("error", (event) => {
    toast(event.detail?.message ?? "SSE error", "error", 8000);
  });
}

export function setupMix() {
  const run = document.getElementById("mix-run");
  const cancel = document.getElementById("mix-cancel");

  cancel.addEventListener("click", async () => {
    if (!source) return;
    try {
      await api.cancelJob();
      toast("Cancellation requested");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  run.addEventListener("click", async () => {
    const src = document.getElementById("mix-source").value.trim();
    if (!src) {
      toast("Enter a mix URL or local file path", "error");
      return;
    }
    analyzeParams = { source: src };
    const cookies = document.getElementById("mix-cookies").value;
    if (cookies) analyzeParams.cookies_from_browser = cookies;

    try {
      source = await api.startJob("analyze-set", analyzeParams);
      setProgress(0, 0, "job queued", "running");
      const handle = subscribeJob();
      bindJobEvents(handle);
    } catch (err) {
      toast(err.message, "error", 8000);
    }
  });

  // Poll stored sets so a finished analysis shows up; the backend persists
  // analyzed sets, so the latest one is the freshest result.
  const loadLatest = async () => {
    const timeline = document.getElementById("mix-timeline");
    const list = document.getElementById("mix-passages");
    try {
      const data = await api.listSets(1);
      const latest = (data.sets ?? [])[0];
      if (!latest) {
        timeline.innerHTML = emptyHTML("No analyzed sets yet", "Run a mix analysis above.");
        list.innerHTML = "";
        return;
      }
      const detail = await api.getSet(latest.id);
      renderResult(detail);
    } catch (err) {
      timeline.innerHTML = errorHTML(err.message, "mix-latest-retry");
      bindRetries(timeline, loadLatest);
      list.innerHTML = "";
    }
  };
  loadLatest();

  return () => {};
}
