import { create } from "zustand";
import { api } from "../api/client";
import type { JobEvent, JobSnapshot } from "../types/apiTypes";

interface JobsState {
  job: JobSnapshot | null;
  active: boolean;
  logLines: string[];
  error: string | null;
  speed: number | null;
  memory: Record<string, number | null> | null;
  refresh: () => Promise<void>;
  start: (kind: string, params: Record<string, unknown>) => Promise<void>;
  cancel: () => Promise<void>;
  connect: () => () => void;
}

let connected = false;

function formatJobLog(event: JobEvent): string | null {
  const stamp = new Date().toLocaleTimeString("en-GB", { hour12: false });
  const j = event.job;
  if (!j) return null;
  if (event.type === "progress") {
    const count =
      j.total != null
        ? `${j.processed}/${j.total}`
        : j.processed > 0
          ? String(j.processed)
          : "";
    const detail = [j.stage, count, j.message].filter(Boolean).join(" · ");
    return detail ? `[${stamp}] [${j.kind}] ${detail}` : null;
  }
  if (event.type === "state") {
    if (j.status === "idle") return null;
    const detail = [j.status.toUpperCase(), j.stage, j.message]
      .filter(Boolean)
      .join(" · ");
    return `[${stamp}] [${j.kind}] ${detail}`;
  }
  const msg = event.message ?? j.error ?? j.message ?? event.type.toUpperCase();
  return `[${stamp}] [${j.kind}] ${event.type.toUpperCase()}: ${msg}`;
}

function appendLog(lines: string[], entry: string | null): string[] {
  if (!entry) return lines;
  const stripTime = (s: string) => s.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, "");
  const last = lines[lines.length - 1];
  if (last && stripTime(last) === stripTime(entry)) return lines;
  return [...lines.slice(-199), entry];
}

export const useJobsStore = create<JobsState>()((set, get) => ({
  job: null,
  active: false,
  logLines: [],
  error: null,
  speed: null,
  memory: null,

  refresh: async () => {
    try {
      const res = await api.currentJob();
      set({ job: res.job, active: res.active, error: res.job?.error ?? null });
    } catch {
      /* backend offline — dashboard shows the offline dot already */
    }
  },

  start: async (kind, params) => {
    set({ logLines: [], error: null, speed: null, memory: null });
    const res = await api.startJob(kind, params);
    set({ job: res.job, active: res.job.status === "running" });
  },

  cancel: async () => {
    await api.cancelJob();
    await get().refresh();
  },

  connect: () => {
    if (connected) return () => undefined;
    connected = true;
    return api.streamJobs(
      (event: JobEvent) => {
        const nextLog = appendLog(get().logLines, formatJobLog(event));
        if (event.type === "progress") {
          set({
            job: event.job,
            active: event.job?.status === "running",
            speed: event.speed ?? null,
            memory: event.memory ?? get().memory,
            error: null,
            logLines: nextLog,
          });
        } else if (event.type === "state") {
          set({
            job: event.job,
            active: event.job?.status === "running",
            error: event.job?.error ?? null,
            logLines: nextLog,
          });
        } else if (event.type === "done" || event.type === "cancelled") {
          set({ job: event.job, active: false, speed: null, logLines: nextLog });
        } else if (event.type === "error") {
          set({
            job: event.job,
            active: false,
            speed: null,
            error: event.message ?? event.job?.error ?? "Job failed",
            logLines: nextLog,
          });
        }
      },
      () => {
        if (get().active) {
          set({ error: "Live job stream paused — reconnecting…" });
        }
      },
    );
  },
}));
