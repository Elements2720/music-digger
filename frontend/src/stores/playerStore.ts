import { create } from "zustand";
import type { Track } from "../types/apiTypes";

type RepeatMode = "off" | "one" | "all";

interface PlayerState {
  audio: HTMLAudioElement | null;
  current: Track | null;
  queue: Track[];
  playing: boolean;
  currentTime: number;
  duration: number;
  muted: boolean;
  volume: number;
  repeat: RepeatMode;

  attach: (audio: HTMLAudioElement) => void;
  play: (track: Track, queue?: Track[]) => void;
  toggle: () => void;
  stop: () => void;
  seek: (seconds: number) => void;
  nudge: (seconds: number) => void;
  next: () => void;
  previous: () => void;
  setVolume: (v: number) => void;
  toggleMute: () => void;
  cycleRepeat: () => void;
  _onTimeUpdate: (t: number, d: number) => void;
  _onEnded: () => void;
}

function previewSrc(track: Track): string | null {
  if (track.local_path) return `/api/catalog/tracks/${track.id}/audio`;
  return track.preview_url ?? null;
}

export const usePlayerStore = create<PlayerState>()((set, get) => ({
  audio: null,
  current: null,
  queue: [],
  playing: false,
  currentTime: 0,
  duration: 0,
  muted: false,
  volume: 0.9,
  repeat: "off" as RepeatMode,

  attach: (audio) => set({ audio }),

  play: (track, queue) => {
    const { audio, current } = get();
    if (!audio) return;
    const src = previewSrc(track);
    if (!src) return;
    const changed = current?.id !== track.id;
    set({
      current: track,
      playing: true,
      queue: queue ?? (current ? get().queue : []),
      ...(changed ? { currentTime: 0, duration: track.duration_seconds ?? 0 } : {}),
    });
    if (changed) {
      audio.src = src;
      audio.currentTime = 0;
    }
    void audio.play().catch(() => set({ playing: false }));
  },

  toggle: () => {
    const { audio, playing, current } = get();
    if (!audio || !current) return;
    if (playing) {
      audio.pause();
      set({ playing: false });
    } else {
      void audio.play().catch(() => set({ playing: false }));
    }
  },

  stop: () => {
    const { audio } = get();
    if (!audio) return;
    audio.pause();
    audio.removeAttribute("src");
    set({ current: null, playing: false, currentTime: 0, duration: 0 });
  },

  seek: (seconds) => {
    const { audio } = get();
    if (!audio) return;
    audio.currentTime = seconds;
    set({ currentTime: seconds });
  },

  nudge: (seconds) => {
    const { audio, currentTime, duration } = get();
    if (!audio) return;
    const target = Math.min(Math.max(0, currentTime + seconds), duration || Infinity);
    audio.currentTime = target;
    set({ currentTime: target });
  },

  next: () => {
    const { current, queue, repeat } = get();
    if (!current || queue.length === 0) return;
    const idx = queue.findIndex((t) => t.id === current.id);
    const nextTrack = queue[idx + 1];
    if (nextTrack) get().play(nextTrack, queue);
    else if (repeat === "all") get().play(queue[0], queue);
    else set({ playing: false });
  },

  previous: () => {
    const { current, queue, currentTime } = get();
    if (!current || queue.length === 0) return;
    if (currentTime > 3) {
      get().seek(0);
      return;
    }
    const idx = queue.findIndex((t) => t.id === current.id);
    const prev = queue[idx - 1];
    if (prev) get().play(prev, queue);
    else get().seek(0);
  },

  setVolume: (v) => {
    const { audio } = get();
    const clamped = Math.min(1, Math.max(0, v));
    if (audio) audio.volume = clamped;
    set({ volume: clamped, muted: clamped === 0 });
  },

  toggleMute: () => {
    const { audio, muted, volume } = get();
    if (!audio) return;
    const next = !muted;
    audio.muted = next;
    audio.volume = next ? 0 : volume || 0.9;
    set({ muted: next });
  },

  cycleRepeat: () =>
    set((s) => ({
      repeat: s.repeat === "off" ? "all" : s.repeat === "all" ? "one" : "off",
    })),

  _onTimeUpdate: (t, d) => set({ currentTime: t, duration: d }),
  _onEnded: () => {
    const { repeat } = get();
    if (repeat === "one") {
      get().seek(0);
      const { audio, current } = get();
      if (audio && current) void audio.play().catch(() => undefined);
      return;
    }
    get().next();
  },
}));
