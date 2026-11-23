/* DIG tab: pick a reference track, then similarity-dig or vibe-search. */

import { api } from "../api.js";
import { currentTrack, isAudioPlaying, playTrack } from "../player.js";
import { emit, on, state } from "../state.js";
import { artwork, camelotBadge, chips, el, renderMatches } from "../ui.js";

let mounted = false;
let searchTimer = null;
let pickerTracks = [];
let activeId = null;

function $(id) {
  return document.getElementById(id);
}

function pickerItem(track) {
  const isPlaying = currentTrack()?.id === track.id && isAudioPlaying();
  const playBtn = el("button", {
    class: `icon-btn picker-play-btn${isPlaying ? " playing" : ""}`,
    type: "button",
    title: isPlaying ? "Pause preview" : "Play preview",
    text: isPlaying ? "❚❚" : "▶",
  });
  playBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    playTrack(track);
  });

  const item = el(
    "button",
    {
      class: `picker-item${track.id === activeId ? " active" : ""}`,
      type: "button",
      "data-track-id": track.id,
    },
    [
      artwork(track.artwork_url, "picker-art"),
      el("div", { class: "picker-copy" }, [
        el("div", { class: "picker-title", text: track.title }),
        el("div", { class: "picker-artist", text: track.artist }),
      ]),
      el("div", { class: "picker-badges" }, [
        playBtn,
        track.source === "local" || track.local_path
          ? el("span", { class: "chip local", text: "LOCAL" })
          : null,
        track.bpm !== null
          ? el("span", { class: "chip bpm", text: String(Math.round(track.bpm)) })
          : null,
        track.key ? camelotBadge(track.key, "chip") : null,
      ]),
    ]
  );
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
  const isPlaying = currentTrack()?.id === track.id && isAudioPlaying();
  const playBtn = el("button", {
    class: `icon-btn reference-play-btn${isPlaying ? " playing" : ""}`,
    type: "button",
    title: isPlaying ? "Pause preview" : "Play preview",
    text: isPlaying ? "❚❚" : "▶",
  });
  playBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    playTrack(track);
  });

  const heartBtn = el("button", {
    class: "heart-btn",
    type: "button",
    title: "Like artist",
    text: "♡",
  });
  api
    .likedArtists()
    .then((res) => {
      const list = res?.liked_artists ?? (Array.isArray(res) ? res : []);
      const isLiked = list.some(
        (a) =>
          (a.artist_name || a.artist || "").toLowerCase() ===
          (track.artist || "").toLowerCase()
      );
      heartBtn.classList.toggle("liked", isLiked);
      heartBtn.textContent = isLiked ? "♥" : "♡";
      heartBtn.title = isLiked ? "Unlike artist" : "Like artist";
    })
    .catch(() => {});

  heartBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const wasLiked = heartBtn.classList.contains("liked");
    heartBtn.disabled = true;
    try {
      if (wasLiked) {
        await api.unlikeArtist(track.artist);
        heartBtn.classList.remove("liked");
        heartBtn.textContent = "♡";
        heartBtn.title = "Like artist";
        emit("toast", `Unliked "${track.artist}"`);
        emit("artist:liked", { artist: track.artist, liked: false });
      } else {
        await api.likeArtist(track.artist);
        heartBtn.classList.add("liked");
        heartBtn.textContent = "♥";
        heartBtn.title = "Unlike artist";
        emit("toast", `Liked "${track.artist}"`);
        emit("artist:liked", { artist: track.artist, liked: true });
      }
    } catch (err) {
      emit("toast", err.message);
    } finally {
      heartBtn.disabled = false;
    }
  });

  card.replaceChildren(
    el("div", { class: "reference-main" }, [
      playBtn,
      el("div", { class: "track-main" }, [
        artwork(track.artwork_url, "row-art"),
        el("div", { class: "picker-copy" }, [
          el("div", { class: "row-title", text: track.title }),
          el(
            "div",
            {
              class: "row-artist",
              style: "display: flex; align-items: center; gap: 4px;",
            },
            [el("span", { text: track.artist }), heartBtn]
          ),
        ]),
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
  const minYear = $("dig-min-year") ? $("dig-min-year").value.trim() : "";
  if (minYear) filters.min_year = Number(minYear);

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

  on("player:state", () => {
    if (state.reference) {
      renderReference(state.reference);
    }
    const list = $("track-results");
    if (list) {
      for (const btn of list.querySelectorAll(".picker-play-btn")) {
        const item = btn.closest(".picker-item");
        const trackId = item?.dataset.trackId;
        const isPlaying = trackId && currentTrack()?.id === trackId && isAudioPlaying();
        btn.textContent = isPlaying ? "❚❚" : "▶";
        btn.classList.toggle("playing", isPlaying);
        btn.title = isPlaying ? "Pause preview" : "Play preview";
      }
    }
  });

  loadRecent();
}

export { runDig };
