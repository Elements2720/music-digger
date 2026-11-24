/* Pipeline: action cards for every job kind, SSE progress with live log.
 * Terminal states (done/failed/cancelled) always clear the running state.
 */

import { api, subscribeJob } from "../api.js";
import { esc, toast } from "../ui.js";

const JOB_PARAMS = {
  index: () => ({ limit: 500, batch_size: 16 }),
  "seed-crawl": () => ({ electronic_limit: 1000, general_limit: 300 }),
  "seed-llm": () => ({ genre: "Melodic Techno & Afro House", count: 100 }),
  "seed-itunes": () => ({ tracks_per_term: 200 }),
  "fetch-metadata": () => ({ artists_limit: 50 }),
  "fetch-artist": () => ({ artist: "" }),
  "download-tracks": () => ({ track_ids: [] }),
  "import-local": () => ({ folder_path: "" }),
  "analyze-set": () => ({ source: "" }),
};

let running = false;

function el(id) {
  return document.getElementById(id);
}

function setRunning(active) {
  running = active;
  el("job-cancel").disabled = !active;
  document
    .querySelectorAll(".action-card")
    .forEach((card) => (card.disabled = active));
}

function setProgress(done, total, message, status = "running") {
  const fill = el("job-fill");
  const pct = total > 0 ? (done / total) * 100 : 0;
  fill.style.width = `${pct}%`;
  fill.parentElement.setAttribute("aria-valuenow", String(pct));
  el("job-status").textContent = message ?? `${status} — ${done}/${total} (${pct}%)`;
}

function logLine(event) {
  const log = el("job-log");
  const cls = event.type === "error" ? "line-err" : event.type === "done" ? "line-ok" : "";
  const line = document.createElement("div");
  line.className = `log-line ${cls}`;
  const processed = event.job?.processed;
  const total = event.job?.total;
  const where = processed != null && total != null ? ` ${processed}/${total}` : "";
  line.textContent = `[${event.type}]${where} ${event.message ?? event.job?.message ?? ""}`;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function bindJob(handle) {
  handle.addEventListener("progress", (event) => {
    const job = event.detail?.job ?? {};
    setProgress(job.processed ?? 0, job.total ?? 0, job.message ?? null);
    logLine({ type: "progress", message: job.message, job });
  });
  const finish = (event) => {
    const detail = event.detail ?? {};
    const status = detail.type ?? detail.job?.status ?? "done";
    const job = detail.job ?? {};
    setProgress(job.processed ?? 1, job.total ?? 1, detail.message ?? job.message ?? `Job ${status}`, status);
    logLine({ type: status, message: detail.message ?? job.message, job });
    setRunning(false);
    handle.close();
  };
  handle.addEventListener("done", finish);
  handle.addEventListener("cancelled", finish);
  handle.addEventListener("error", (event) => {
    const detail = event.detail ?? {};
    logLine({ type: "error", message: detail.message ?? "job failed", job: detail.job ?? {} });
    toast(detail.message ?? "Job failed", "error", 8000);
    setProgress(0, 0, "failed", "failed");
    setRunning(false);
    handle.close();
  });
}

export function setupPipeline() {
  document.querySelectorAll(".action-card").forEach((card) =>
    card.addEventListener("click", async () => {
      if (running) {
        toast("A job is already running — cancel it first", "error");
        return;
      }
      const kind = card.dataset.job;
      const params = (JOB_PARAMS[kind] ?? (() => ({})))();
      if (kind === "download-tracks") {
        // Real contract: explicit track id list; empty list is a no-op, not a 400.
        toast("Pick tracks via a view first — download-tracks takes explicit track IDs", "error", 8000);
        return;
      }
      if (kind === "import-local" && params.folder_path === "") {
        toast("import-local needs a folder_path — enter it in the log panel first", "error", 8000);
        return;
      }
      if (Object.values(params).some((v) => v === "")) {
        toast(`This job needs parameters (${Object.keys(params).join(", ")}) — edit pipeline defaults first`, "error", 8000);
        return;
      }
      try {
        el("job-log").innerHTML = "";
        setRunning(true);
        setProgress(0, 0, "job queued — waiting for events", "queued");
        await api.startJob(kind, params);
        bindJob(subscribeJob());
      } catch (err) {
        setRunning(false);
        setProgress(0, 0, `could not start: ${err.message}`, "error");
        toast(err.message, "error", 8000);
      }
    }),
  );

  el("job-cancel").addEventListener("click", async () => {
    try {
      await api.cancelJob();
      el("job-status").textContent = "cancellation requested…";
    } catch (err) {
      toast(err.message, "error");
    }
  });

  // Show any job already in flight when the page loads.
  (async () => {
    try {
      const data = await api.currentJob();
      const job = data?.job ?? null;
      if (job && !["done", "failed", "cancelled"].includes(job.status)) {
        setRunning(true);
        setProgress(job.processed ?? 0, job.total ?? 0, job.message ?? "resumed running job");
        bindJob(subscribeJob());
      }
    } catch {
      /* no current job — fine */
    }
  })();

  return () => {};
}
