/* Persistent bottom audio player: iTunes preview_url streams directly. */

import { emit } from "./state.js";
import { PLACEHOLDER, fmtTime } from "./format.js";

const audio = new Audio();
audio.preload = "none";
audio.volume = 0.9;

let current = null;
let ready = false;

function $(id) {
  return document.getElementById(id);
}

function setArtwork(url) {
  const art = $("player-art");
  if (!art) return;
  art.onerror = () => {
    art.onerror = null;
    art.src = PLACEHOLDER;
  };
  art.src = url || PLACEHOLDER;
}

function syncToggle() {
  const toggle = $("player-toggle");
  if (toggle) toggle.textContent = audio.paused ? "▶" : "❚❚";
}

function syncSeek() {
  const seek = $("player-seek");
  const currentLabel = $("player-current");
  const durationLabel = $("player-duration");
  if (!seek) return;
  const duration = Number.isFinite(audio.duration) ? audio.duration : 30;
  seek.max = String(duration);
  if (!seek.matches(":active")) seek.value = String(audio.currentTime || 0);
  if (currentLabel) currentLabel.textContent = fmtTime(audio.currentTime);
  if (durationLabel) durationLabel.textContent = fmtTime(duration);
}

export function setupPlayer() {
  if (ready) return;
  ready = true;

  $("player-toggle")?.addEventListener("click", () => {
    if (!current) return;
    if (audio.paused) {
      audio.play().catch(() => emit("toast", "Preview could not play"));
    } else {
      audio.pause();
    }
  });

  $("player-seek")?.addEventListener("input", (event) => {
    audio.currentTime = Number(event.target.value);
    syncSeek();
  });

  $("player-volume")?.addEventListener("input", (event) => {
    audio.volume = Number(event.target.value);
  });

  $("player-dig")?.addEventListener("click", () => {
    if (current) emit("dig:track", current);
  });

  audio.addEventListener("play", () => {
    syncToggle();
    emit("player:state", { track: current, playing: true });
  });
  audio.addEventListener("pause", () => {
    syncToggle();
    emit("player:state", { track: current, playing: false });
  });
  audio.addEventListener("error", () => {
    const err = audio.error;
    let detail = "Playback error";
    if (err) {
      switch (err.code) {
        case 1: // MEDIA_ERR_ABORTED
          detail = "Audio playback aborted";
          break;
        case 2: // MEDIA_ERR_NETWORK
          detail = "Network error loading audio";
          break;
        case 3: // MEDIA_ERR_DECODE
          detail = "Audio decode failed (file corrupted or unsupported format)";
          break;
        case 4: // MEDIA_ERR_SRC_NOT_SUPPORTED
          detail = "Audio format or source not supported";
          break;
        default:
          detail = err.message ? `Playback error: ${err.message}` : "Playback error";
      }
    }
    emit("toast", detail);
    syncToggle();
    syncSeek();
    emit("player:state", { track: current, playing: false });
  });
  audio.addEventListener("timeupdate", syncSeek);
  audio.addEventListener("durationchange", syncSeek);
  audio.addEventListener("ended", () => {
    audio.currentTime = 0;
    syncToggle();
    syncSeek();
    emit("player:state", { track: current, playing: false });
  });

  syncToggle();
  syncSeek();
}

export function playTrack(track) {
  setupPlayer();
  if (!track?.preview_url) {
    emit("toast", "No preview URL for this track");
    return;
  }
  if (current?.id === track.id) {
    if (audio.paused) {
      audio.play().catch((err) => {
        if (err.name !== "AbortError") {
          emit("toast", `Playback failed: ${err.message || "cannot play"}`);
        }
      });
    } else {
      audio.pause();
    }
    return;
  }

  current = track;
  $("player")?.classList.remove("hidden");
  setArtwork(track.artwork_url);
  $("player-title").textContent = track.title;
  $("player-artist").textContent = track.artist;

  const store = $("player-store");
  if (store) {
    store.href = track.store_url || "#";
    store.classList.toggle("hidden", !track.store_url);
  }

  audio.src = track.preview_url;
  audio.currentTime = 0;
  audio.load();
  audio
    .play()
    .catch((error) => {
      if (error.name !== "AbortError") {
        emit("toast", `Playback failed: ${error.message || "cannot play"}`);
      }
    });
  emit("player:play", track);
}

export function currentTrack() {
  return current;
}

export function isAudioPlaying() {
  return !!(current && !audio.paused && !audio.ended);
}
