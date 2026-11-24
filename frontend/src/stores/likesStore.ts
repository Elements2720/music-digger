import { create } from "zustand";

/** Tracks marked heard/liked in this session, synced across every view. */
interface LikesState {
  heardIds: Set<string>;
  toggleHeard: (id: string, next: boolean) => void;
  bulkHeard: (ids: string[]) => void;
}

export const useLikesStore = create<LikesState>()((set) => ({
  heardIds: new Set<string>(),
  toggleHeard: (id, next) =>
    set((state) => {
      const heardIds = new Set(state.heardIds);
      if (next) heardIds.add(id);
      else heardIds.delete(id);
      return { heardIds };
    }),
  bulkHeard: (ids) =>
    set((state) => {
      const heardIds = new Set(state.heardIds);
      for (const id of ids) heardIds.add(id);
      return { heardIds };
    }),
}));
