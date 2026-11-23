/* Mini deck: persistent bottom player with transport, seek, volume, cue state,
 * artwork, LOCAL/PREVIEW chip, Camelot badge, + Set and download buttons.
 * The deck listens on the event bus; any view can call `loadTrack`. */

import { api } from "./api.js";
import { emit, on } from "./events.js";
import { esc, toast } from "./ui.js";
import { iconPlay, iconPause, iconPrev, iconNext, iconDownload } from "./icons.js";

const audio = new Audio();
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
  audio.play().catch(() => {
    el("deck-play").innerHTML = iconPlay();
    toast("Playback blocked or failed — press play", "error");
  });
  el("deck-play").innerHTML = iconPause();
  emit("deck:track", track);
}

export function setupPlayer() {
  const playBtn = el("deck-play");
  const seek = el("deck-seek");
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
    seek.value = String((audio.currentTime / audio.duration) * 100);
  });
  seek.addEventListener("input", () => {
    if (Number.isFinite(audio.duration) && audio.duration > 0) {
      audio.currentTime = (Number(seek.value) / 100) * audio.duration;
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

  // Views can refresh the deck chip after a download completes elsewhere.
  on("track:downloaded", () => {
    if (currentTrack) {
      currentTrack.has_local_file = true;
      renderDeck();
    }
  });
}
