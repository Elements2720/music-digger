/* Set Builder: compose a set from search results, evaluate transitions,
 * auto-sequence, suggest next, save planned sets, export .m3u8.
 * Wired to /api/set-helper/* and the set-helper playlist event bus.
 */

import { api } from "../api.js";
import { on } from "../events.js";
import { emptyHTML, errorHTML, bindRetries, esc, toast } from "../ui.js";
import { trackRowHTML, bindTrackRows } from "../components.js";
import { iconUp, iconDown, iconClose } from "../icons.js";

let playlist = []; // ordered tracks in the working set
let savedSets = [];
let lastEvals = [];

/* ---------- working playlist ---------- */

function renderPlaylist() {
  const el = document.getElementById("builder-tracks");
  if (!playlist.length) {
    el.innerHTML = emptyHTML("Empty set", "Search on the right and click a track to add it.");
    return;
  }
  el.innerHTML = playlist
    .map((t, i) => {
      const ev = lastEvals[i - 1];
      const badge =
        ev != null
          ? `<button class="connector-badge ${ev.score >= 0.66 ? "good" : ev.score >= 0.33 ? "mid" : "bad"}" data-ev="${i - 1}" title="harmonic ${ev.harmonic_score * 100}% · bpm ${ev.bpm_score * 100}% · ${esc(ev.camelot_move ?? "")} ${ev.bpm_delta != null ? ev.bpm_delta : ""}">${ev.score * 100}%</button>`
          : `<span class="connector-dot" aria-hidden="true"></span>`;
      return `
  ${i > 0 ? `<div class="connector">${badge}</div>` : ""}
  <div class="track-row">
    <span class="t-meta">${i + 1}</span>
    <div class="t-main">
      <div class="t-title">${esc(t.title)}</div>
      <div class="t-artist">${esc(t.artist)} · ${t.bpm != null ? t.bpm + " bpm" : "—"} ${t.key ? "· " + esc(t.key) : ""}</div>
    </div>
    <button class="icon-btn" data-up="${i}" ${i === 0 ? "disabled" : ""} aria-label="Move up">${iconUp()}</button>
    <button class="icon-btn" data-down="${i}" ${i === playlist.length - 1 ? "disabled" : ""} aria-label="Move down">${iconDown()}</button>
    <button class="icon-btn" data-remove="${i}" aria-label="Remove">${iconClose()}</button>
  </div>`;
    })
    .join("");

  el.querySelectorAll("[data-up]").forEach((b) =>
    b.addEventListener("click", () => move(Number(b.dataset.up), -1)),
  );
  el.querySelectorAll("[data-down]").forEach((b) =>
    b.addEventListener("click", () => move(Number(b.dataset.down), 1)),
  );
  el.querySelectorAll("[data-remove]").forEach((b) =>
    b.addEventListener("click", () => {
      playlist.splice(Number(b.dataset.remove), 1);
      lastEvals = [];
      renderPlaylist();
    }),
  );
  el.querySelectorAll("[data-ev]").forEach((b) =>
    b.addEventListener("click", () => showEval(Number(b.dataset.ev))),
  );
}

function move(index, delta) {
  const j = index + delta;
  if (j < 0 || j >= playlist.length) return;
  [playlist[index], playlist[j]] = [playlist[j], playlist[index]];
  lastEvals = [];
  renderPlaylist();
}

/* ---------- search pool ---------- */

async function searchPool() {
  const q = document.getElementById("builder-search").value.trim();
  const el = document.getElementById("builder-pool");
  if (q.length < 2) return;
  try {
    const params = new URLSearchParams({ q, limit: "12" });
    const data = await api.searchTracks(params);
    const tracks = data.results ?? [];
    if (!tracks.length) {
      el.innerHTML = emptyHTML("No matches", "Try another query.");
      return;
    }
    el.innerHTML = `<div class="track-list">${tracks
      .map(
        (t) => `
    <button class="track-row" data-add="${esc(t.id)}">
      <span class="icon-btn" aria-hidden="true">+</span>
      <div style="min-width:0; flex:1; text-align:left">
        <div class="t-title">${esc(t.title)}</div>
        <div class="t-artist">${esc(t.artist)} · ${t.bpm != null ? t.bpm + " bpm" : "—"} ${t.key ? "· " + esc(t.key) : ""}</div>
      </div>
    </button>`,
      )
      .join("")}</div>`;
    el.querySelectorAll("[data-add]").forEach((b) =>
      b.addEventListener("click", () => {
        const t = tracks.find((x) => x.id === b.dataset.add);
        if (t && !playlist.some((p) => p.id === t.id)) {
          playlist.push(t);
          lastEvals = [];
          renderPlaylist();
        }
      }),
    );
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "pool-retry");
    bindRetries(el, searchPool);
  }
}

/* ---------- helper actions ---------- */

function showEval(index) {
  const ev = lastEvals[index];
  if (!ev) return;
  const el = document.getElementById("builder-eval");
  const from = playlist[index];
  const to = playlist[index + 1];
  el.innerHTML = `
  <h3 class="panel-title">Transition ${index + 1} → ${index + 2}</h3>
  <p class="mono">${esc(from?.title ?? "")} → ${esc(to?.title ?? "")}</p>
  <div class="grid-3">
    <div class="stat-card"><span class="stat-value">${ev.score * 100}%</span><span class="stat-label">overall</span></div>
    <div class="stat-card"><span class="stat-value">${ev.harmonic_score * 100}%</span><span class="stat-label">harmonic</span></div>
    <div class="stat-card"><span class="stat-value">${ev.bpm_delta != null ? ev.bpm_delta : "—"}</span><span class="stat-label">bpm delta</span></div>
  </div>
  <p class="mono">camelot move: ${esc(ev.camelot_move ?? "—")}</p>`;
}

async function evaluate() {
  if (playlist.length < 2) {
    toast("Add at least two tracks", "error");
    return;
  }
  const el = document.getElementById("builder-eval");
  try {
    const data = await api.evaluateSequence(playlist.map((t) => t.id));
    lastEvals = data.transitions ?? [];
    renderPlaylist();
    const avg = lastEvals.reduce((s, e) => s + e.score, 0) / Math.max(1, lastEvals.length);
    el.innerHTML = `<p class="mono">Evaluated ${lastEvals.length} transitions — average ${avg * 100}%. Click a connector badge for detail.</p>`;
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "eval-retry");
    bindRetries(el, evaluate);
  }
}

async function autoSequence() {
  if (playlist.length < 2) {
    toast("Add at least two tracks", "error");
    return;
  }
  try {
    const data = await api.autoSequence(playlist.map((t) => t.id));
    const byId = new Map(playlist.map((t) => [t.id, t]));
    playlist = (data.ordered_track_ids ?? []).map((id) => byId.get(id)).filter(Boolean);
    lastEvals = [];
    renderPlaylist();
    toast(`Auto-sequenced — average score ${data.average_score * 100}%`, "ok");
  } catch (err) {
    toast(err.message, "error", 8000);
  }
}

async function suggestNext() {
  if (!playlist.length) {
    toast("Add a track first", "error");
    return;
  }
  const from = playlist[playlist.length - 1];
  const el = document.getElementById("builder-eval");
  try {
    const data = await api.suggestNext(from.id);
    const suggestions = (data.suggestions ?? []).map((s) => ({
      ...s.track,
      similarity: s.evaluation.score * 100,
    }));
    el.innerHTML = `
    <h3 class="panel-title">Next after ${esc(from.title)}</h3>
    ${suggestions.length ? `<div class="track-list">${suggestions.map((t) => trackRowHTML(t, { similarity: t.similarity })).join("")}</div>` : emptyHTML("No suggestions", "")}`;
    bindTrackRows(el, suggestions);
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "sugg-retry");
    bindRetries(el, suggestNext);
  }
}

async function findBridge() {
  if (playlist.length < 2) {
    toast("Add at least two tracks — the bridge goes between the last two", "error");
    return;
  }
  const a = playlist[playlist.length - 2];
  const b = playlist[playlist.length - 1];
  const el = document.getElementById("builder-eval");
  try {
    const data = await api.findBridge(a.id, b.id);
    const rows = (data.bridges ?? []).map((br) => ({
      ...br.bridge_track,
      similarity: br.combined_score * 100,
    }));
    el.innerHTML = `
    <h3 class="panel-title">Bridges: ${esc(a.title)} → ${esc(b.title)}</h3>
    ${rows.length ? `<div class="track-list">${rows.map((t) => trackRowHTML(t, { similarity: t.similarity })).join("")}</div>` : emptyHTML("No bridges found", "")}`;
    bindTrackRows(el, rows);
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "bridge-retry");
    bindRetries(el, findBridge);
  }
}

/* ---------- saved sets ---------- */

async function loadSaved() {
  const el = document.getElementById("builder-saved");
  try {
    savedSets = await api.listPlannedSets();
    if (!savedSets.length) {
      el.innerHTML = emptyHTML("No saved sets", "Compose a set and press Save set.");
      return;
    }
    el.innerHTML = `<div class="track-list">${savedSets
      .map(
        (s) => `
    <div class="track-row saved-set-row">
      <div class="t-main">
        <div class="t-title">${esc(s.name)}</div>
        <div class="t-artist">${s.track_count} tracks</div>
      </div>
      <button class="icon-btn" data-load="${s.id}">Load</button>
      <button class="icon-btn" data-export="${s.id}">.m3u8</button>
      <button class="icon-btn" data-del="${s.id}" aria-label="Delete set">${iconClose()}</button>
    </div>`,
      )
      .join("")}</div>`;
    el.querySelectorAll("[data-load]").forEach((b) => b.addEventListener("click", () => loadSet(Number(b.dataset.load))));
    el.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", () => exportSet(Number(b.dataset.export))));
    el.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (!confirm("Delete this saved set?")) return;
        try {
          await api.deletePlannedSet(Number(b.dataset.del));
          loadSaved();
          toast("Set deleted");
        } catch (err) {
          toast(err.message, "error");
        }
      }),
    );
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "saved-retry");
    bindRetries(el, loadSaved);
  }
}

async function loadSet(id) {
  try {
    const detail = await api.getPlannedSet(id);
    playlist = detail.tracks ?? [];
    document.getElementById("builder-name").value = detail.name ?? "";
    lastEvals = [];
    renderPlaylist();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function exportSet(id) {
  try {
    const text = await api.exportPlannedSet(id);
    const name = (savedSets.find((s) => s.id === id)?.name ?? "set").replace(/[^\w-]+/g, "_");
    const blob = new Blob([text], { type: "audio/x-mpegurl" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.m3u8`;
    a.click();
    URL.revokeObjectURL(url);
    toast("Exported .m3u8", "ok");
  } catch (err) {
    toast(err.message, "error", 8000);
  }
}

async function saveSet() {
  const name = document.getElementById("builder-name").value.trim();
  if (!name) {
    toast("Give the set a name", "error");
    return;
  }
  if (!playlist.length) {
    toast("Add tracks first", "error");
    return;
  }
  try {
    await api.createPlannedSet(name, playlist.map((t) => t.id));
    toast("Set saved", "ok");
    loadSaved();
  } catch (err) {
    toast(err.message, "error", 8000);
  }
}

/* ---------- setup ---------- */

export function setupBuilder() {
  let timer = null;
  document.getElementById("builder-search").addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(searchPool, 250);
  });
  document.getElementById("builder-evaluate").addEventListener("click", evaluate);
  document.getElementById("builder-autoseq").addEventListener("click", autoSequence);
  document.getElementById("builder-suggest").addEventListener("click", suggestNext);
  document.getElementById("builder-bridge").addEventListener("click", findBridge);
  document.getElementById("builder-save").addEventListener("click", saveSet);
  document.getElementById("builder-export").addEventListener("click", () => {
    const name = document.getElementById("builder-name").value.trim() || "set";
    if (playlist.length) {
      saveSet().then(() => {
        const found = savedSets.find((s) => s.name === name);
        if (found) exportSet(found.id);
      });
    }
  });

  // Any view can add a track to the working set via the event bus.
  on("set:add-track", (track) => {
    if (track && !playlist.some((p) => p.id === track.id)) {
      playlist.push(track);
      lastEvals = [];
      renderPlaylist();
    }
  });

  renderPlaylist();
  loadSaved();
  return () => {};
}
