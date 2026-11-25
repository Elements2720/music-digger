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
      set({ job: res.job, active: res.active });
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
    return api.streamJobs((event: JobEvent) => {
      if (event.type === "progress") {
        set({
          job: event.job,
          active: event.job?.status === "running",
          speed: event.speed ?? null,
          memory: event.memory ?? get().memory,
        });
      } else if (event.type === "state") {
        set({ job: event.job, active: event.job?.status === "running" });
      } else if (event.type === "done" || event.type === "cancelled") {
        set({ job: event.job, active: false, speed: null });
      } else if (event.type === "error") {
        set({
          job: event.job,
          active: false,
          speed: null,
          error: event.message ?? event.job?.error ?? "Job failed",
        });
      }
    });
  },
}));
