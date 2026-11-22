/* DIG tab: pick a reference track, then similarity-dig or vibe-search. */

import { api } from "../api.js";
import { state } from "../state.js";
import { artwork, chips, el, renderMatches } from "../ui.js";

let mounted = false;
let searchTimer = null;
let pickerTracks = [];
let activeId = null;

function $(id) {
  return document.getElementById(id);
}

function pickerItem(track) {
  const item = el("button", {
    class: `picker-item${track.id === activeId ? " active" : ""}`,
    type: "button",
  }, [
    artwork(track.artwork_url, "picker-art"),
    el("div", { class: "picker-copy" }, [
      el("div", { class: "picker-title", text: track.title }),
      el("div", { class: "picker-artist", text: track.artist }),
    ]),
    el("div", { class: "picker-badges" }, [
      track.source === "local" || track.local_path
        ? el("span", { class: "chip local", text: "LOCAL" })
        : null,
      track.bpm !== null
        ? el("span", { class: "chip bpm", text: String(Math.round(track.bpm)) })
        : null,
      track.key ? el("span", { class: "chip key", text: track.key }) : null,
    ]),
  ]);
  item.addEventListener("click", () => selectTrack(track));
  return item;
}

function renderPicker() {
  const list = $("track-results");
  list.replaceChildren();
  if (pickerTracks.length === 0) {
    list.append(el("div", { class: "empty", text: "No tracks found." }));
    return;
  }
  for (const track of pickerTracks) list.append(pickerItem(track));
}

function renderReference(track) {
  const card = $("reference-card");
  if (!track) {
    card.classList.add("hidden");
    card.replaceChildren();
    $("dig-hint").textContent = "pick a reference first";
    return;
  }
  card.classList.remove("hidden");
  card.replaceChildren(
    el("div", { class: "track-main" }, [
      artwork(track.artwork_url, "row-art"),
      el("div", { class: "picker-copy" }, [
        el("div", { class: "row-title", text: track.title }),
        el("div", { class: "row-artist", text: track.artist }),
      ]),
    ]),
    chips(track)
  );
  $("dig-hint").textContent = "digging from this track";
}

export function selectTrack(track) {
  if (!track) return;
  state.reference = track;
  activeId = track.id;
  renderPicker();
  renderReference(track);
  runDig();
}

async function runDig() {
  const reference = state.reference;
  if (!reference) return;
  const results = $("dig-results");
  results.replaceChildren(el("div", { class: "empty", text: "Digging…" }));

  const tolerance = $("dig-bpm-tolerance").value.trim();
  const filters = {
    limit: Number($("dig-limit").value) || 20,
    harmonic: $("dig-harmonic").checked,
    exclude_heard: $("dig-exclude-heard").checked,
  };
  if (tolerance) filters.bpm_tolerance = Number(tolerance);
  const genre = $("dig-genre").value.trim();
  if (genre) filters.genre = genre;

  try {
    const body = await api.dig(reference.id, filters);
    if (body.reference) {
      state.reference = body.reference;
      renderReference(body.reference);
    }
    renderMatches(results, body.matches, "No similar tracks yet.");
  } catch (error) {
    results.replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

async function runVibe(event) {
  event?.preventDefault();
  const query = $("vibe-query").value.trim();
  if (!query) return;
  const results = $("vibe-results");
  results.replaceChildren(el("div", { class: "empty", text: "Listening…" }));

  const payload = {
    query,
    limit: Number($("vibe-limit").value) || 20,
    exclude_heard: $("vibe-exclude-heard").checked,
  };
  const genre = $("vibe-genre").value.trim();
  if (genre) payload.genre = genre;

  try {
    const body = await api.vibeSearch(payload);
    renderMatches(results, body.matches, "Nothing matched that description.");
  } catch (error) {
    results.replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

async function loadRecent() {
  try {
    const body = await api.recentTracks(30);
    pickerTracks = body.tracks;
    renderPicker();
  } catch (error) {
    $("track-results").replaceChildren(
      el("div", { class: "empty", text: error.message })
    );
  }
}

async function search(query) {
  if (!query.trim()) {
    await loadRecent();
    return;
  }
  try {
    const body = await api.searchTracks(query, 30);
    pickerTracks = body.tracks;
    renderPicker();
  } catch (error) {
    $("track-results").replaceChildren(
      el("div", { class: "empty", text: error.message })
    );
  }
}

export function mount() {
  if (mounted) return;
  mounted = true;

  $("track-search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    const value = event.target.value;
    searchTimer = setTimeout(() => search(value), 220);
  });

  $("dig-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runDig();
  });
  $("vibe-form").addEventListener("submit", runVibe);

  loadRecent();
}

export { runDig };
