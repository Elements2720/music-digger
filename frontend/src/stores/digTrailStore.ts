import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Track } from "../types/apiTypes";

export type SeedSource = "recent" | "local" | "taste";

const MAX_SEEDS = 30;

interface DigTrailState {
  /** Newest first, de-duplicated by track id. */
  seeds: Track[];
  activeId: string | null;
  source: SeedSource;
  push: (track: Track) => void;
  remove: (id: string) => void;
  setActive: (id: string | null) => void;
  setSource: (source: SeedSource) => void;
}

/**
 * The Dig Trail: every seed the DJ has dug from, kept across tab switches
 * for the whole session (sessionStorage only — never written to disk).
 */
export const useDigTrailStore = create<DigTrailState>()(
  persist(
    (set) => ({
      seeds: [],
      activeId: null,
      source: "recent",

      push: (track) =>
        set((state) => ({
          seeds: [track, ...state.seeds.filter((t) => t.id !== track.id)].slice(
            0,
            MAX_SEEDS,
          ),
          activeId: track.id,
        })),

      remove: (id) =>
        set((state) => {
          const seeds = state.seeds.filter((t) => t.id !== id);
          const activeId =
            state.activeId === id ? (seeds[0]?.id ?? null) : state.activeId;
          return { seeds, activeId };
        }),

      setActive: (id) => set({ activeId: id }),
      setSource: (source) => set({ source }),
    }),
    {
      name: "dig-trail",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        seeds: state.seeds,
        activeId: state.activeId,
        source: state.source,
      }),
    },
  ),
);
