import { create } from "zustand";
import type { Track } from "../types/apiTypes";

/** The Set Crate: the working, ordered track list shared by every workspace. */
interface CrateState {
  tracks: Track[];
  open: boolean;
  toggle: () => void;
  setOpen: (open: boolean) => void;
  add: (track: Track) => void;
  remove: (id: string) => void;
  move: (id: string, toIndex: number) => void;
  clear: () => void;
  replaceAll: (tracks: Track[], name?: string) => void;
  has: (id: string) => boolean;
}

export const useCrateStore = create<CrateState>()((set, get) => ({
  tracks: [],
  open: false,
  toggle: () => set((s) => ({ open: !s.open })),
  setOpen: (open) => set({ open }),
  add: (track) =>
    set((s) =>
      s.tracks.some((t) => t.id === track.id)
        ? s
        : { tracks: [...s.tracks, track] },
    ),
  remove: (id) => set((s) => ({ tracks: s.tracks.filter((t) => t.id !== id) })),
  move: (id, toIndex) =>
    set((s) => {
      const from = s.tracks.findIndex((t) => t.id === id);
      if (from === -1 || toIndex < 0 || toIndex >= s.tracks.length) return s;
      const tracks = [...s.tracks];
      const [item] = tracks.splice(from, 1);
      tracks.splice(toIndex, 0, item);
      return { tracks };
    }),
  clear: () => set({ tracks: [] }),
  replaceAll: (tracks) => set({ tracks }),
  has: (id) => get().tracks.some((t) => t.id === id),
}));
