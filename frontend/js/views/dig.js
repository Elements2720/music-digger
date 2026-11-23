/* Dig workspace: three strictly isolated tabs sharing one results renderer.
 * - match: visual track picker -> GET /api/dig/{id}
 * - foryou: taste ranking -> GET /api/tracks/recent + filters
 * - vibe: CLAP text search -> POST /api/vibe-search
 */

import { api } from "../api.js";
import { emptyHTML, errorHTML, bindRetries, esc, toast } from "../ui.js";
import { trackRowHTML, bindTrackRows, isArtistLiked } from "../components.js";

let currentMode = "match";
let selectedTrack = null;
let pickerCache = [];

function modePanels() {
  return document.querySelectorAll("[data-dig-panel]");
}

function selectMode(mode) {
  currentMode = mode;
  document.querySelectorAll("#dig-modes .mode").forEach((btn) => {
    const active = btn.dataset.mode === mode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  modePanels().forEach((panel) => {
    panel.hidden = panel.dataset.digPanel !== mode;
  });
}

/* ---------- Match a Track ---------- */

function renderPicker(tracks) {
  pickerCache = tracks;
  const el = document.getElementById("dig-match-picker");
  if (!tracks.length) {
    el.innerHTML = emptyHTML("No tracks found", "Try a different search.");
    return;
  }
  el.innerHTML = `<div class="track-list">${tracks
    .map(
      (t) => `
  <button class="track-row picker-row" data-pick="${esc(t.id)}">
    <span class="t-meta primary">${t.taste_match_percent ?? 0}%</span>
    <div style="min-width:0; flex:1; text-align:left">
      <div class="t-title">${esc(t.title)}</div>
      <div class="t-artist">${esc(t.artist)}</div>
    </div>
    <span class="t-meta primary">${t.bpm != null ? t.bpm + " bpm" : "—"}</span>
  </button>`,
    )
    .join("")}</div>`;
  el.querySelectorAll("[data-pick]").forEach((btn) =>
    btn.addEventListener("click", () => {
      selectedTrack = pickerCache.find((t) => t.id === btn.dataset.pick);
      if (selectedTrack) runMatch();
    }),
  );
}

function renderSelected() {
  const wrap = document.getElementById("dig-match-source");
  const el = document.getElementById("dig-match-selected");
  if (!selectedTrack) {
    wrap.hidden = true;
    el.innerHTML = "";
    return;
  }
  wrap.hidden = false;
  el.innerHTML = `
  <h3 class="panel-title">Digging around</h3>
  ${trackRowHTML(selectedTrack)}`;
  bindTrackRows(el, [selectedTrack]);
}

async function runMatch() {
  if (!selectedTrack) {
    toast("Pick a track first", "error");
    return;
  }
  renderSelected();
  const el = document.getElementById("dig-match-results");
  try {
    el.innerHTML = emptyHTML("searching…", "");
    const params = { limit: Number(document.getElementById("dig-limit").value) };
    const tol = document.getElementById("dig-bpm-tol").value;
    if (tol) params.bpm_tolerance = Number(tol);
    params.harmonic = document.getElementById("dig-harmonic").value === "true";
    const data = await api.dig(selectedTrack.id, params);
    const matches = data.matches ?? [];
    if (!matches.length) {
      el.innerHTML = emptyHTML("No matches", "The index returned nothing for this track.");
      return;
    }
    const flatMatches = matches.map((m) => m.track ?? m);
    el.innerHTML = `<div class="track-list">${flatMatches.map((t, i) => trackRowHTML(t, { similarity: matches[i].similarity })).join("")}</div>`;
    bindTrackRows(el, flatMatches);
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "dig-match-retry");
    bindRetries(el, runMatch);
  }
}

/* ---------- For You ---------- */

async function runForYou() {
  const el = document.getElementById("dig-foryou-results");
  try {
    el.innerHTML = emptyHTML("ranking…", "");
    const limit = Number(document.getElementById("dig-foryou-limit").value);
    const genre = document.getElementById("dig-foryou-genre").value.trim();
    const [data, artistData] = await Promise.all([
      api.recentTracks(limit),
      api.artists({ limit: 500 }),
    ]);
    const tasteByArtist = new Map(
      (artistData.artists ?? artistData.results ?? [])
        .filter((a) => a.taste_match_percent != null)
        .map((a) => [String(a.artist ?? "").toLowerCase(), a.taste_match_percent]),
    );
    let tracks = (data.tracks ?? []).map((t) => ({
      ...t,
      is_liked: isArtistLiked(t.artist),
      taste_match_percent: t.taste_match_percent ?? tasteByArtist.get(String(t.artist ?? "").toLowerCase()) ?? null,
    }));
    if (genre) {
      const needle = genre.toLowerCase();
      tracks = tracks.filter((t) => String(t.genre ?? "").toLowerCase().includes(needle));
    }
    const source = document.getElementById("dig-foryou-source").value;
    if (source === "local") tracks = tracks.filter((t) => t.has_local_file);
    else if (source === "liked") tracks = tracks.filter((t) => t.is_liked);
    tracks.sort((a, b) => (b.taste_match_percent ?? 0) - (a.taste_match_percent ?? 0));
    if (!tracks.length) {
      el.innerHTML = emptyHTML("Nothing to rank", "Widen the filters or run the pipeline first.");
      return;
    }
    el.innerHTML = `<div class="track-list">${tracks.map((t) => trackRowHTML(t)).join("")}</div>`;
    bindTrackRows(el, tracks);
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "dig-foryou-retry");
    bindRetries(el, runForYou);
  }
}

/* ---------- Vibe & Catalog ---------- */

async function runVibe(queryOverride = null) {
  const input = document.getElementById("dig-vibe-text");
  const errEl = document.getElementById("dig-vibe-error");
  const el = document.getElementById("dig-vibe-results");
  errEl.textContent = "";
  const query = (queryOverride ?? input.value).trim();
  if (!query) {
    errEl.textContent = "Describe the vibe first.";
    return;
  }
  if (queryOverride != null) input.value = queryOverride;
  try {
    const data = await api.vibeSearch({
      query,
      limit: Number(document.getElementById("dig-vibe-limit").value),
    });
    const vibeTracks = data.matches ?? [];
    if (!vibeTracks.length) {
      el.innerHTML = emptyHTML("No vibe matches", "Try different words.");
      return;
    }
    const flatMatches = vibeTracks.map((m) => m.track ?? m);
    el.innerHTML = `<div class="track-list">${flatMatches.map((t, i) => trackRowHTML(t, { similarity: vibeTracks[i].similarity })).join("")}</div>`;
    bindTrackRows(el, flatMatches);
  } catch (err) {
    errEl.textContent = err.message;
    el.innerHTML = errorHTML(err.message, "dig-vibe-retry");
    bindRetries(el, () => runVibe(query));
  }
}

/* Exact-metadata catalog filter. Deep links from the Camelot wheel / BPM
 * histogram land here — CLAP text search is never used for key/BPM queries. */

function numOrNull(value) {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

async function runCatalogFilter(preset = {}) {
  const errEl = document.getElementById("dig-cat-error");
  const el = document.getElementById("dig-cat-results");
  errEl.textContent = "";
  if (preset.key) document.getElementById("dig-cat-key").value = preset.key;
  if (preset.bpm_min != null) document.getElementById("dig-cat-bpm-min").value = preset.bpm_min;
  if (preset.bpm_max != null) document.getElementById("dig-cat-bpm-max").value = preset.bpm_max;
  const params = {
    q: document.getElementById("dig-cat-q").value.trim() || undefined,
    key: document.getElementById("dig-cat-key").value || undefined,
    bpm_min: numOrNull(document.getElementById("dig-cat-bpm-min").value) ?? undefined,
    bpm_max: numOrNull(document.getElementById("dig-cat-bpm-max").value) ?? undefined,
    source: document.getElementById("dig-cat-source").value || undefined,
    limit: 100,
  };
  if (!params.q && !params.key && params.bpm_min == null && params.bpm_max == null && !params.source) {
    errEl.textContent = "Set at least one filter (text, key, BPM or source).";
    return;
  }
  try {
    el.innerHTML = emptyHTML("filtering…", "");
    const data = await api.catalogFilter(params);
    const tracks = data.tracks ?? [];
    if (!tracks.length) {
      el.innerHTML = emptyHTML("No tracks match", "Loosen the filters and try again.");
      return;
    }
    el.innerHTML = `<div class="track-list">${tracks.map((t) => trackRowHTML(t)).join("")}</div>`;
    bindTrackRows(el, tracks);
  } catch (err) {
    errEl.textContent = err.message;
    el.innerHTML = errorHTML(err.message, "dig-cat-retry");
    bindRetries(el, () => runCatalogFilter(preset));
  }
}

/** Deep link from the dashboard: switch to the catalog panel and apply the
 * exact filter — never feed "tracks in key 12" to CLAP vibe search. */
function openCatalogWith(preset) {
  selectMode("vibe");
  runCatalogFilter(preset).then(() => {
    document.getElementById("dig-cat-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

/* ---------- setup ---------- */

export function setupDig() {
  document.querySelectorAll("#dig-modes .mode").forEach((btn) =>
    btn.addEventListener("click", () => selectMode(btn.dataset.mode)),
  );

  let searchTimer = null;
  document.getElementById("dig-match-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim();
    if (q.length < 2) return;
    searchTimer = setTimeout(async () => {
      try {
        const data = await api.searchTracks(q, 8);
        renderPicker(data.tracks ?? []);
      } catch (err) {
        toast(err.message, "error");
      }
    }, 250);
  });

  document.getElementById("dig-foryou-run").addEventListener("click", runForYou);
  document.getElementById("dig-vibe-run").addEventListener("click", () => runVibe());
  document.getElementById("dig-vibe-text").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runVibe();
  });

  document.getElementById("dig-cat-run").addEventListener("click", () => runCatalogFilter());
  document.getElementById("dig-cat-reset").addEventListener("click", () => {
    document.getElementById("dig-cat-q").value = "";
    document.getElementById("dig-cat-key").value = "";
    document.getElementById("dig-cat-bpm-min").value = "";
    document.getElementById("dig-cat-bpm-max").value = "";
    document.getElementById("dig-cat-source").value = "";
    document.getElementById("dig-cat-results").innerHTML = "";
  });

  // Camelot key dropdown: 1A..12A / 1B..12B
  const keySelect = document.getElementById("dig-cat-key");
  for (let n = 1; n <= 12; n++) {
    for (const letter of ["A", "B"]) {
      const opt = document.createElement("option");
      opt.value = `${n}${letter}`;
      opt.textContent = `${n}${letter}`;
      keySelect.appendChild(opt);
    }
  }

  import("../events.js").then(({ on }) => {
    on("catalog:filter", (detail) => openCatalogWith(detail ?? {}));
  });

  selectMode("match");
  return () => {};
}
