/* Mini deck: persistent bottom player with transport, seek, volume, cue state,
 * artwork, LOCAL/PREVIEW chip, Camelot badge, + Set and download buttons.
 * The deck listens on the event bus; any view can call `loadTrack`. */

import { api } from "./api.js";
import { emit, on } from "./events.js";
import { esc, toast } from "./ui.js";
import { iconPlay, iconPause, iconPrev, iconNext, iconDownload } from "./icons.js";

const audio = document.getElementById("deck-audio") || new Audio();
let queue = [];
let queueIndex = -1;
let currentTrack = null;

const el = (id) => document.getElementById(id);

/** Playback clock as M:SS (e.g. 0:24) — never raw decimal seconds. */
function fmt(sec) {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
}

function renderDeck() {
  const t = currentTrack;
  if (!t) return;

  const art = el("deck-art");
  if (t.artwork_url) {
    art.src = t.artwork_url;
    art.hidden = false;
  } else {
    art.hidden = true;
  }

  el("np-title").textContent = t.title;
  el("np-title").classList.remove("placeholder");
  el("np-artist").textContent = t.artist;
  el("np-artist").classList.remove("placeholder");

  const chip = el("np-chip");
  chip.hidden = false;
  if (t.has_local_file) {
    chip.textContent = "LOCAL";
    chip.className = "chip chip-ok";
  } else {
    chip.textContent = "PREVIEW";
    chip.className = "chip";
  }

  const bpm = Number(t.bpm);
  el("cue-bpm").textContent =
    t.bpm != null && Number.isFinite(bpm) ? String(bpm) : "—";
  el("cue-key").textContent = t.key || "—";

  const dl = el("deck-download");
  dl.hidden = t.has_local_file;
  dl.dataset.id = t.id;

  const add = el("deck-add-set");
  add.hidden = false;
  add.dataset.id = t.id;
}

/* Seeded pseudo-waveform: deterministic per src, so a track always shows the
 * same bar silhouette. Purely decorative — seeking is by time, not samples. */
function seedWave(src) {
  let seed = 0;
  for (let i = 0; i < src.length; i++) seed = (seed * 31 + src.charCodeAt(i)) >>> 0;
  const bars = 60;
  const heights = [];
  for (let i = 0; i < bars; i++) {
    seed = (seed * 1103515245 + 12345) >>> 0;
    const t = i / bars;
    // Soft envelope so the bar breathes in the middle, like a real set.
    const env = 0.35 + 0.65 * Math.sin(Math.PI * Math.min(1, Math.max(0, t)));
    heights.push(Math.max(0.12, env * (0.35 + ((seed >>> 16) % 1000) / 1000)));
  }
  return heights;
}

function renderWave() {
  const svg = el("deck-wave-svg");
  if (!svg) return;
  const h = seedWave(audio.src || currentTrack?.id || "empty");
  const bw = 240 / h.length;
  svg.innerHTML = h
    .map((v, i) => `<rect x="${(i * bw).toFixed(2)}" y="${(((1 - v) * 36) / 2).toFixed(2)}" width="${(bw * 0.7).toFixed(2)}" height="${(v * 36).toFixed(2)}" rx="1"/>`)
    .join("");
}

function playIndex(i) {
  if (i < 0 || i >= queue.length) return;
  queueIndex = i;
  loadTrack(queue[i], queue);
}

export function loadTrack(track, queueTracks = null) {
  currentTrack = track;
  if (Array.isArray(queueTracks) && queueTracks.length) queue = queueTracks;
  queueIndex = queue.findIndex((t) => t.id === track.id);

  const url = track.local_path
    ? `/api/catalog/tracks/${encodeURIComponent(track.id)}/audio`
    : track.preview_url;
  if (!url) {
    toast("No preview or local file for this track", "error");
    return;
  }

  renderDeck();
  audio.src = url;
  renderWave();
  el("deck-wave-progress").style.width = "0%";
  audio.play().catch(() => {
    el("deck-play").innerHTML = iconPlay();
    toast("Playback blocked or failed — press play", "error");
  });
  el("deck-play").innerHTML = iconPause();
  emit("deck:track", track);
}

export function setupPlayer() {
  const playBtn = el("deck-play");
  const wave = el("deck-wave");
  const vol = el("deck-vol");
  vol.value = String(audio.volume * 100);

  playBtn.addEventListener("click", () => {
    if (!audio.src) return toast("Load a track first — dig one in the Dig tab", "error");
    if (audio.paused) {
      audio.play().catch(() => toast("Playback failed", "error"));
      playBtn.innerHTML = iconPause();
    } else {
      audio.pause();
      playBtn.innerHTML = iconPlay();
    }
  });

  el("deck-prev").innerHTML = iconPrev();
  el("deck-next").innerHTML = iconNext();
  el("deck-play").innerHTML = iconPlay();
  el("deck-download").innerHTML = iconDownload();

  el("deck-prev").addEventListener("click", () => playIndex(queueIndex - 1));
  el("deck-next").addEventListener("click", () => playIndex(queueIndex + 1));

  audio.addEventListener("timeupdate", () => {
    if (!Number.isFinite(audio.duration) || audio.duration === 0) return;
    el("deck-time").textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
    const pct = (audio.currentTime / audio.duration) * 100;
    el("deck-wave-progress").style.width = `${pct}%`;
    wave.setAttribute("aria-valuenow", String(Math.round(pct)));
  });
  const seekTo = (clientX) => {
    if (!Number.isFinite(audio.duration) || audio.duration === 0) return;
    const rect = wave.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    audio.currentTime = frac * audio.duration;
  };
  wave.addEventListener("pointerdown", (e) => {
    wave.setPointerCapture(e.pointerId);
    seekTo(e.clientX);
    const move = (ev) => seekTo(ev.clientX);
    const up = () => {
      wave.removeEventListener("pointermove", move);
      wave.removeEventListener("pointerup", up);
    };
    wave.addEventListener("pointermove", move);
    wave.addEventListener("pointerup", up);
  });
  wave.addEventListener("keydown", (e) => {
    if (!Number.isFinite(audio.duration) || audio.duration === 0) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const step = e.key === "ArrowLeft" ? -10 : 10;
      audio.currentTime = Math.min(audio.duration, Math.max(0, audio.currentTime + step));
    }
  });
  vol.addEventListener("input", () => {
    audio.volume = Number(vol.value) / 100;
  });
  audio.addEventListener("ended", () => playIndex(queueIndex + 1));
  audio.addEventListener("error", () => {
    if (audio.src) toast("Audio stream failed", "error");
  });

  el("deck-download").addEventListener("click", async (e) => {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    e.currentTarget.disabled = true;
    try {
      await api.downloadTrack(id);
      if (currentTrack && currentTrack.id === id) {
        currentTrack.has_local_file = true;
        renderDeck();
      }
      toast("Downloaded to local storage", "ok");
    } catch (err) {
      toast(err.message, "error", 8000);
    } finally {
      e.currentTarget.disabled = false;
    }
  });

  el("deck-add-set").addEventListener("click", (e) => {
    const id = e.currentTarget.dataset.id;
    const track = currentTrack && currentTrack.id === id ? currentTrack : queue.find((t) => t.id === id);
    if (track) {
      emit("set:add-track", track);
      toast(`Added "${track.title}" to Set Builder playlist`);
    }
  });

  // Global transport shortcuts — ignored while typing in any form control.
  document.addEventListener("keydown", (e) => {
    const target = e.target;
    if (target instanceof HTMLElement && target.closest("input, textarea, select, [contenteditable], [contenteditable] *")) return;
    if (e.code === "Space") {
      e.preventDefault();
      playBtn.click();
    } else if (e.code === "KeyM") {
      audio.muted = !audio.muted;
    } else if (e.code === "ArrowLeft" && Number.isFinite(audio.duration) && audio.duration > 0) {
      e.preventDefault();
      audio.currentTime = Math.max(0, audio.currentTime - 10);
    } else if (e.code === "ArrowRight" && Number.isFinite(audio.duration) && audio.duration > 0) {
      e.preventDefault();
      audio.currentTime = Math.min(audio.duration, audio.currentTime + 10);
    }
  });

  // Views can refresh the deck chip after a download completes elsewhere.
  on("track:downloaded", () => {
    if (currentTrack) {
      currentTrack.has_local_file = true;
      renderDeck();
    }
  });
}
