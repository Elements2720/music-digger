/* SETS tab: analyze a set, list stored sets, inspect tracklist / digs. */

import { api } from "../api.js";
import { emit } from "../state.js";
import { camelotBadge, el, renderMatches, setRow } from "../ui.js";
import { fmtClock, fmtRange, fmtBpm } from "../format.js";
import { launch } from "./run.js";

let mounted = false;
let sets = [];
let currentSet = null;
let currentView = "tracklist";

function $(id) {
  return document.getElementById(id);
}

function passageRow(passage) {
  const label = passage.exact_id_match
    ? passage.exact_id_display_name || "identified"
    : passage.exact_id_display_name || "unidentified";

  const head = el("div", { class: "passage-head" }, [
    el("span", { class: "passage-time mono", text: fmtRange(passage.start_seconds, passage.end_seconds) }),
    el("span", {
      class: `passage-id${passage.exact_id_match ? "" : " closest"}`,
      text: label,
    }),
    chipsFor(passage),
  ]);

  const matches = passage.matches ?? [];
  if (matches.length === 0) {
    return el("div", { class: "passage" }, [head]);
  }

  const details = el("details", { class: "passage-matches" });
  details.append(
    el("summary", { text: `${matches.length} closest match${matches.length === 1 ? "" : "es"}` })
  );
  const results = el("div", { class: "results" });
  renderMatches(results, matches, "No matches");
  details.append(results);

  return el("div", { class: "passage" }, [head, details]);
}

function chipsFor(passage) {
  const wrap = el("div", { class: "track-meta" });
  const bpm = fmtBpm(passage.bpm);
  if (bpm) wrap.append(el("span", { class: "chip bpm", text: bpm }));
  if (passage.key) wrap.append(camelotBadge(passage.key, "chip"));
  if (passage.exact_id_source) {
    wrap.append(el("span", { class: "chip", text: passage.exact_id_source }));
  }
  return wrap;
}

function renderSets() {
  const list = $("sets-list");
  list.replaceChildren();
  if (sets.length === 0) {
    list.append(el("div", { class: "empty", text: "No sets stored yet." }));
    return;
  }
  for (const djSet of sets) {
    list.append(setRow(djSet, { onOpen: (value) => openSet(value.id) }));
  }
}

async function loadSets() {
  try {
    const body = await api.sets(50);
    sets = body.sets;
    renderSets();
  } catch (error) {
    $("sets-list").replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

async function openSet(setId) {
  $("set-detail").classList.remove("hidden");
  $("set-detail").scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const body = await api.setDetail(setId, "tracklist");
    currentSet = body.set;
    currentView = "tracklist";
    $("set-title").textContent = body.set.title;
    $("set-meta").textContent = [
      body.set.artist || "unknown artist",
      `${body.set.passage_count} passages`,
      body.set.duration_seconds ? fmtClock(body.set.duration_seconds) : null,
      body.set.bpm_min !== null && body.set.bpm_max !== null
        ? `${Math.round(body.set.bpm_min)}–${Math.round(body.set.bpm_max)} BPM`
        : null,
    ]
      .filter(Boolean)
      .join(" · ");
    renderSetView("tracklist", body);
  } catch (error) {
    $("set-detail-body").replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

function renderSetView(view, body) {
  const target = $("set-detail-body");
  target.replaceChildren();
  if (view === "tracklist") {
    if (!body.passages || body.passages.length === 0) {
      target.append(el("div", { class: "empty", text: "This set has no passages." }));
      return;
    }
    for (const passage of body.passages) target.append(passageRow(passage));
    return;
  }
  if (view === "tracks") {
    renderMatches(target, body.matches, "No similar tracks found.");
    return;
  }
  if (!body.sets || body.sets.length === 0) {
    target.append(el("div", { class: "empty", text: "No similar sets yet." }));
    return;
  }
  for (const match of body.sets) {
    target.append(
      setRow(match.set, {
        similarity: match.similarity,
        onOpen: (value) => openSet(value.id),
      })
    );
  }
}

async function switchView(view, force = false) {
  if (!currentSet || (view === currentView && !force)) return;
  currentView = view;
  for (const button of $("set-subtabs").querySelectorAll(".subtab")) {
    button.classList.toggle("active", button.dataset.view === view);
  }
  $("set-track-filters").classList.toggle("hidden", view !== "tracks");
  const target = $("set-detail-body");
  target.replaceChildren(el("div", { class: "empty", text: "Loading…" }));

  const filters = {};
  if (view === "tracks") {
    filters.limit = Number($("set-track-limit").value) || 30;
    const tolerance = $("set-bpm-tolerance").value.trim();
    if (tolerance) filters.bpm_tolerance = Number(tolerance);
    const genre = $("set-track-genre").value.trim();
    if (genre) filters.genre = genre;
    filters.exclude_heard = $("set-exclude-heard").checked;
  }
  try {
    const body = await api.setDetail(currentSet.id, view, filters);
    renderSetView(view, body);
  } catch (error) {
    target.replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

export function mount() {
  if (mounted) return;
  mounted = true;

  $("sets-refresh").addEventListener("click", loadSets);
  $("set-back").addEventListener("click", () => {
    $("set-detail").classList.add("hidden");
    currentSet = null;
  });

  for (const button of $("set-subtabs").querySelectorAll(".subtab")) {
    button.addEventListener("click", () => switchView(button.dataset.view));
  }
  $("set-track-apply").addEventListener("click", () => {
    const active = $("set-subtabs").querySelector(".subtab.active");
    switchView(active?.dataset.view ?? "tracks", true);
  });

  $("analyze-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const source = $("set-source").value.trim();
    if (!source) return;
    const params = {
      source,
      shazam: $("set-shazam").checked,
      comments: $("set-comments").checked,
      keep_audio: $("set-keep-audio").checked,
    };
    const cookiesFile = $("set-cookies-file").value.trim();
    if (cookiesFile) params.cookies_file = cookiesFile;
    const browser = $("set-cookies-browser").value.trim();
    if (browser) params.cookies_from_browser = browser;

    emit("tab:show", "run");
    await launch("analyze-set", params);
  });

  loadSets();
}

export { loadSets, openSet };
