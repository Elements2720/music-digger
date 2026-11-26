import { create } from "zustand";
import { api, registerHeardObserver, type HeardTrackPayload } from "../api/client";

/** Tracks marked heard in this session, synced across views and SQLite. */
interface LikesState {
  heardIds: Set<string>;
  pendingIds: Set<string>;
  error: string | null;
  clearError: () => void;
  toggleHeard: (id: string, next: boolean) => Promise<boolean>;
  bulkHeard: (ids: string[], next?: boolean) => Promise<boolean>;
  syncTracks: (items: ReadonlyArray<HeardTrackPayload>) => void;
  removeTrack: (id: string) => void;
}

export const useLikesStore = create<LikesState>()((set, get) => ({
  heardIds: new Set<string>(),
  pendingIds: new Set<string>(),
  error: null,
  clearError: () => set({ error: null }),

  toggleHeard: async (id, next) => {
    const had = get().heardIds.has(id);
    set((state) => {
      const heardIds = new Set(state.heardIds);
      const pendingIds = new Set(state.pendingIds);
      if (next) heardIds.add(id);
      else heardIds.delete(id);
      pendingIds.add(id);
      return { heardIds, pendingIds, error: null };
    });
    try {
      const res = await api.setHeard(id, next);
      set((state) => {
        const heardIds = new Set(state.heardIds);
        const pendingIds = new Set(state.pendingIds);
        if (res.is_heard) heardIds.add(id);
        else heardIds.delete(id);
        pendingIds.delete(id);
        return { heardIds, pendingIds };
      });
      return true;
    } catch (err) {
      set((state) => {
        const heardIds = new Set(state.heardIds);
        const pendingIds = new Set(state.pendingIds);
        if (had) heardIds.add(id);
        else heardIds.delete(id);
        pendingIds.delete(id);
        return {
          heardIds,
          pendingIds,
          error: err instanceof Error ? err.message : "Could not update heard state",
        };
      });
      return false;
    }
  },

  bulkHeard: async (ids, next = true) => {
    if (ids.length === 0) return true;
    const prevSnapshot = new Map(ids.map((id) => [id, get().heardIds.has(id)]));
    const toUpdate = ids.filter((id) => prevSnapshot.get(id) !== next);
    if (toUpdate.length === 0) return true;

    set((state) => {
      const heardIds = new Set(state.heardIds);
      const pendingIds = new Set(state.pendingIds);
      for (const id of toUpdate) {
        if (next) heardIds.add(id);
        else heardIds.delete(id);
        pendingIds.add(id);
      }
      return { heardIds, pendingIds, error: null };
    });

    const results = await Promise.allSettled(
      toUpdate.map((id) => api.setHeard(id, next).then((res) => ({ id, res }))),
    );
    let allOk = true;
    set((state) => {
      const heardIds = new Set(state.heardIds);
      const pendingIds = new Set(state.pendingIds);
      results.forEach((outcome, index) => {
        const id = toUpdate[index];
        pendingIds.delete(id);
        if (outcome.status === "fulfilled") {
          if (outcome.value.res.is_heard) heardIds.add(id);
          else heardIds.delete(id);
        } else {
          allOk = false;
          if (prevSnapshot.get(id)) heardIds.add(id);
          else heardIds.delete(id);
        }
      });
      return {
        heardIds,
        pendingIds,
        ...(allOk ? {} : { error: "Some tracks failed to update heard state" }),
      };
    });
    return allOk;
  },

  syncTracks: (items) => {
    if (items.length === 0) return;
    set((state) => {
      let changed = false;
      const heardIds = new Set(state.heardIds);
      for (const item of items) {
        if (typeof item.is_heard !== "boolean" || state.pendingIds.has(item.id)) {
          continue;
        }
        const has = heardIds.has(item.id);
        if (item.is_heard && !has) {
          heardIds.add(item.id);
          changed = true;
        } else if (!item.is_heard && has) {
          heardIds.delete(item.id);
          changed = true;
        }
      }
      return changed ? { heardIds } : state;
    });
  },

  removeTrack: (id) =>
    set((state) => {
      if (!state.heardIds.has(id) && !state.pendingIds.has(id)) return state;
      const heardIds = new Set(state.heardIds);
      const pendingIds = new Set(state.pendingIds);
      heardIds.delete(id);
      pendingIds.delete(id);
      return { heardIds, pendingIds };
    }),
}));

registerHeardObserver((items) => useLikesStore.getState().syncTracks(items));
