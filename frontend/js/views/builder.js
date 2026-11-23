/* BUILDER tab: DJ Set Helper interactive workbench with transition scoring, energy curve, and 2-opt auto-sequencing. */

import { api } from "../api.js";
import { currentTrack, isAudioPlaying, playTrack } from "../player.js";
import { emit, on } from "../state.js";
import { artwork, camelotBadge, el } from "../ui.js";
import { fmtBpm, fmtNumber } from "../format.js";

let mounted = false;

// State
let setTracks = [];
let currentSetId = null;
let currentSetName = "My DJ Set Plan";
let selectedTrackIdx = null;
let activeFlow = "steady";
let localOnly = false;
let bridgePair = null; // { a: Track, b: Track, idxA: number, idxB: number }
let activeMode = "next"; // "next" | "bridge"
let currentTransitions = [];
let catalogSearchTimer = null;

function $(id) {
  return document.getElementById(id);
}

function formatDuration(totalSeconds) {
  const secs = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) {
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function mount() {
  if (mounted) return;
  mounted = true;

  // Name input
  const nameInput = $("builder-set-name");
  if (nameInput) {
    nameInput.value = currentSetName;
    nameInput.addEventListener("input", () => {
      currentSetName = nameInput.value.trim() || "My DJ Set Plan";
    });
  }

  // Saved sets selector
  $("builder-saved-sets")?.addEventListener("change", async (e) => {
    const setId = e.target.value;
    if (!setId) return;
    await loadSavedSet(Number(setId));
  });

  // Action buttons
  $("builder-save-btn")?.addEventListener("click", saveCurrentSet);
  $("builder-clear-btn")?.addEventListener("click", clearCurrentSet);
  $("builder-export-btn")?.addEventListener("click", exportM3U8);
  $("builder-download-missing-btn")?.addEventListener("click", downloadMissingTracks);

  // Auto-sequence dropdown
  const autoSeqBtn = $("builder-auto-seq-btn");
  const autoSeqMenu = $("builder-auto-seq-menu");
  autoSeqBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    autoSeqMenu?.classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    if (autoSeqMenu && !autoSeqMenu.contains(e.target) && e.target !== autoSeqBtn) {
      autoSeqMenu.classList.add("hidden");
    }
  });
  autoSeqMenu?.addEventListener("click", async (e) => {
    const item = e.target.closest(".popup-item");
    if (!item) return;
    autoSeqMenu.classList.add("hidden");
    const flow = item.dataset.flow || "ramp_up";
    await autoSequenceSet(flow);
  });

  // Mode switcher (Next Track vs Find Bridge)
  $("builder-mode-next-btn")?.addEventListener("click", () => switchMode("next"));
  $("builder-mode-bridge-btn")?.addEventListener("click", () => switchMode("bridge"));

  // Local only checkbox
  $("builder-local-only")?.addEventListener("change", (e) => {
    localOnly = e.target.checked;
    refreshRecommendations();
  });

  // Flow preset pills
  $("builder-flow-presets")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".flow-btn");
    if (!btn) return;
    for (const b of $("builder-flow-presets").querySelectorAll(".flow-btn")) {
      b.classList.toggle("active", b === btn);
    }
    activeFlow = btn.dataset.flow || "steady";
    evaluateAndRenderCurve();
    refreshRecommendations();
  });

  // Catalog search input
  $("builder-catalog-search")?.addEventListener("input", () => {
    clearTimeout(catalogSearchTimer);
    catalogSearchTimer = setTimeout(() => searchCatalogToAdd(), 300);
  });

  // Sync play/pause icons with global audio player state
  on("player:state", () => {
    syncAllPlayButtons();
  });

  loadSavedSetsList();
  renderTracklist();
  evaluateAndRenderCurve();
  refreshRecommendations();
}

function syncAllPlayButtons() {
  const current = currentTrack();
  const playing = isAudioPlaying();

  for (const btn of document.querySelectorAll(".builder-play-btn")) {
    const tid = btn.dataset.trackId;
    const isThisPlaying = current?.id === tid && playing;
    btn.classList.toggle("playing", isThisPlaying);
    btn.textContent = isThisPlaying ? "❚❚" : "▶";
    btn.title = isThisPlaying ? "Pause preview" : "Play preview";
  }
}

async function loadSavedSetsList() {
  const select = $("builder-saved-sets");
  if (!select) return;
  try {
    const sets = await api.setHelperListSets();
    select.replaceChildren(el("option", { value: "", text: "-- Load Saved Set --" }));
    for (const s of sets || []) {
      const opt = el("option", {
        value: String(s.id),
        text: `${s.name} (${s.track_count} tracks)`,
      });
      if (currentSetId === s.id) opt.selected = true;
      select.append(opt);
    }
  } catch (err) {
    console.error("Failed to list planned sets", err);
  }
}

async function loadSavedSet(setId) {
  try {
    const data = await api.setHelperGetSet(setId);
    if (!data) return;
    currentSetId = data.id;
    currentSetName = data.name;
    const nameInput = $("builder-set-name");
    if (nameInput) nameInput.value = data.name;

    // Use full track objects returned by API
    setTracks = (data.tracks || []).slice();
    selectedTrackIdx = setTracks.length > 0 ? setTracks.length - 1 : null;
    emit("toast", `Loaded set "${data.name}" (${setTracks.length} tracks)`);

    renderTracklist();
    await evaluateAndRenderCurve();
    refreshRecommendations();
  } catch (err) {
    emit("toast", `Failed to load set: ${err.message}`);
  }
}

async function saveCurrentSet() {
  const nameInput = $("builder-set-name");
  const name = nameInput ? nameInput.value.trim() : currentSetName;
  if (!name) {
    emit("toast", "Please enter a set name first");
    return;
  }
  const trackIds = setTracks.map((t) => t.id);

  try {
    let saved;
    if (currentSetId !== null) {
      saved = await api.setHelperUpdateSet(currentSetId, {
        name,
        track_ids: trackIds,
      });
      emit("toast", `Updated set "${name}"`);
    } else {
      saved = await api.setHelperCreateSet({
        name,
        track_ids: trackIds,
      });
      currentSetId = saved.id;
      emit("toast", `Saved new set "${name}"`);
    }
    await loadSavedSetsList();
  } catch (err) {
    emit("toast", `Save failed: ${err.message}`);
  }
}

function clearCurrentSet() {
  if (setTracks.length > 0 && !window.confirm("Clear all tracks from the current set?")) {
    return;
  }
  setTracks = [];
  currentSetId = null;
  currentSetName = "My DJ Set Plan";
  selectedTrackIdx = null;
  bridgePair = null;
  const nameInput = $("builder-set-name");
  if (nameInput) nameInput.value = currentSetName;
  const select = $("builder-saved-sets");
  if (select) select.value = "";

  renderTracklist();
  evaluateAndRenderCurve();
  switchMode("next");
  refreshRecommendations();
}

async function exportM3U8() {
  if (setTracks.length === 0) {
    emit("toast", "Add tracks to the set before exporting");
    return;
  }
  // If already saved to DB, use direct download route
  if (currentSetId !== null) {
    const url = `/api/set-helper/sets/${currentSetId}/export.m3u8`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentSetName}.m3u8`;
    document.body.append(a);
    a.click();
    a.remove();
    emit("toast", `Exported "${currentSetName}.m3u8"`);
    return;
  }

  // Otherwise generate client-side M3U8 blob
  const lines = ["#EXTM3U", `#PLAYLIST:${currentSetName}`];
  for (const t of setTracks) {
    const dur = t.duration_seconds ? Math.round(t.duration_seconds) : 30;
    lines.push(`#EXTINF:${dur},${t.artist} - ${t.title}`);
    lines.push(t.local_path || t.preview_url || `track:${t.id}`);
  }
  const blob = new Blob([lines.join("\n") + "\n"], { type: "application/x-mpegurl" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${currentSetName}.m3u8`;
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  emit("toast", `Exported "${currentSetName}.m3u8"`);
}

async function autoSequenceSet(flow = "ramp_up") {
  if (setTracks.length < 3) {
    emit("toast", "Need at least 3 tracks to auto-sequence");
    return;
  }
  const trackIds = setTracks.map((t) => t.id);
  try {
    const res = await api.setHelperAutoSequence({
      track_ids: trackIds,
      flow,
      lock_first: false,
    });
    const idMap = new Map(setTracks.map((t) => [t.id, t]));
    setTracks = res.ordered_track_ids.map((id) => idMap.get(id)).filter(Boolean);
    selectedTrackIdx = setTracks.length - 1;

    emit("toast", `Auto-sequenced (${flow})! Avg flow score: ${res.average_score}%`);
    renderTracklist();
    await evaluateAndRenderCurve();
    refreshRecommendations();
  } catch (err) {
    emit("toast", `Auto-sequence failed: ${err.message}`);
  }
}

export function addTrackToSet(track) {
  if (!track || !track.id) return;
  // If track already exists, allow but warn
  setTracks.push(track);
  selectedTrackIdx = setTracks.length - 1;

  renderTracklist();
  evaluateAndRenderCurve();
  refreshRecommendations();
}

function removeTrackFromSet(index) {
  if (index < 0 || index >= setTracks.length) return;
  setTracks.splice(index, 1);
  if (selectedTrackIdx !== null) {
    if (selectedTrackIdx >= setTracks.length) {
      selectedTrackIdx = setTracks.length > 0 ? setTracks.length - 1 : null;
    }
  }
  renderTracklist();
  evaluateAndRenderCurve();
  refreshRecommendations();
}

function moveTrack(fromIdx, toIdx) {
  if (toIdx < 0 || toIdx >= setTracks.length) return;
  const [item] = setTracks.splice(fromIdx, 1);
  setTracks.splice(toIdx, 0, item);
  selectedTrackIdx = toIdx;

  renderTracklist();
  evaluateAndRenderCurve();
  refreshRecommendations();
}

function switchMode(mode) {
  activeMode = mode;
  $("builder-mode-next-btn")?.classList.toggle("active", mode === "next");
  $("builder-mode-bridge-btn")?.classList.toggle("active", mode === "bridge");
  $("builder-panel-next")?.classList.toggle("hidden", mode !== "next");
  $("builder-panel-bridge")?.classList.toggle("hidden", mode !== "bridge");
}

function renderTracklist() {
  const container = $("builder-tracklist");
  if (!container) return;

  if (setTracks.length === 0) {
    container.replaceChildren(
      el("div", {
        class: "empty",
        id: "builder-tracklist-empty",
        text: "Set is currently empty. Pick recommendations from the right or click '+ SET' while digging.",
      })
    );
    updateSummary();
    return;
  }

  const items = [];
  for (let i = 0; i < setTracks.length; i++) {
    const t = setTracks[i];
    const isSelected = selectedTrackIdx === i;

    // Track card
    const row = buildTrackRow(t, i, isSelected);
    items.push(row);

    // Connector pill if not last track
    if (i < setTracks.length - 1) {
      const nextT = setTracks[i + 1];
      const ev = currentTransitions[i];
      const pill = buildTransitionPill(t, nextT, i, ev);
      items.push(pill);
    }
  }

  container.replaceChildren(...items);
  syncAllPlayButtons();
  updateSummary();
}

function buildTrackRow(track, index, isSelected) {
  const isPlaying = currentTrack()?.id === track.id && isAudioPlaying();

  const playBtn = el("button", {
    class: `icon-btn builder-play-btn${isPlaying ? " playing" : ""}`,
    type: "button",
    dataset: { trackId: track.id },
    title: isPlaying ? "Pause preview" : "Play preview",
    text: isPlaying ? "❚❚" : "▶",
  });
  playBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    playTrack(track);
  });

  const upBtn = el("button", {
    class: "icon-btn move-btn",
    type: "button",
    disabled: index === 0,
    title: "Move track up",
    text: "↑",
  });
  upBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    moveTrack(index, index - 1);
  });

  const downBtn = el("button", {
    class: "icon-btn move-btn",
    type: "button",
    disabled: index === setTracks.length - 1,
    title: "Move track down",
    text: "↓",
  });
  downBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    moveTrack(index, index + 1);
  });

  const removeBtn = el("button", {
    class: "icon-btn delete-btn",
    type: "button",
    title: "Remove from set",
    text: "✕",
  });
  removeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    removeTrackFromSet(index);
  });

  const bpmText = fmtBpm(track.bpm) || "—";

  const row = el(
    "div",
    {
      class: `builder-track-row${isSelected ? " selected" : ""}`,
      dataset: { index: String(index) },
    },
    [
      el("div", { class: "builder-track-idx mono", text: String(index + 1) }),
      playBtn,
      artwork(track.artwork_url, "builder-art"),
      el("div", { class: "builder-track-info" }, [
        el("div", { class: "builder-title", text: track.title }),
        el("div", { class: "builder-artist dim", text: track.artist }),
      ]),
      el("div", { class: "track-meta builder-meta" }, [
        track.local_path || track.has_local_file || track.source === "local"
          ? el("span", { class: "chip local", text: "LOCAL" })
          : null,
        el("span", { class: "chip bpm", text: bpmText }),
        camelotBadge(track.key, "chip"),
      ]),
      el("div", { class: "builder-track-controls" }, [upBtn, downBtn, removeBtn]),
    ]
  );

  row.addEventListener("click", () => {
    selectedTrackIdx = index;
    renderTracklist();
    refreshRecommendations();
  });

  return row;
}

function buildTransitionPill(trackA, trackB, indexA, ev) {
  let scorePill;
  let harmonicChildren = ["Calculating…"];
  let bpmDeltaLabel = "";

  if (ev) {
    const score = Math.round(ev.score);
    const tier = score >= 80 ? "taste-high" : score >= 65 ? "taste-mid" : "taste-low";
    scorePill = el("span", { class: `chip ${tier}`, text: `${score}%` });

    const moveMap = {
      same: "Same Key",
      "+1": "Smooth +1",
      "-1": "Smooth -1",
      relative: "Relative A/B",
      "+2": "Energy +2",
      "-2": "Energy -2",
      "+7": "Modulation +7",
      clash: "Clash",
      unknown: "Key Unknown",
    };
    const moveName = moveMap[ev.camelot_move] || ev.camelot_move;
    if (trackA.key && trackB.key) {
      harmonicChildren = [
        moveName,
        " (",
        camelotBadge(trackA.key),
        " → ",
        camelotBadge(trackB.key),
        ")",
      ];
    } else {
      harmonicChildren = [moveName];
    }

    const delta = ev.bpm_delta;
    if (delta === 0) {
      bpmDeltaLabel = "Steady (0.0 BPM)";
    } else if (delta > 0) {
      bpmDeltaLabel = `+${delta.toFixed(1)} BPM`;
    } else {
      bpmDeltaLabel = `${delta.toFixed(1)} BPM`;
    }
  } else {
    scorePill = el("span", { class: "chip taste-mid", text: "—" });
    harmonicChildren = ["—"];
  }

  const bridgeBtn = el("button", {
    class: "btn tiny ghost bridge-pill-btn",
    type: "button",
    title: "Find bridge tracks between these two tracks",
    text: "+ BRIDGE",
  });
  bridgeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    openBridgeMode(trackA, trackB, indexA);
  });

  return el("div", { class: "transition-connector" }, [
    el("div", { class: "transition-line" }),
    el("div", { class: "transition-badge" }, [
      scorePill,
      el("span", { class: "transition-harmonic dim" }, harmonicChildren),
      bpmDeltaLabel ? el("span", { class: "transition-bpm mono dim", text: bpmDeltaLabel }) : null,
      bridgeBtn,
    ]),
    el("div", { class: "transition-line" }),
  ]);
}

function updateSummary() {
  const countEl = $("builder-track-count");
  const timeEl = $("builder-total-time");
  const scoreEl = $("builder-avg-score");

  if (countEl) {
    countEl.textContent = `${setTracks.length} track${setTracks.length === 1 ? "" : "s"}`;
  }

  let totalDuration = 0;
  for (const t of setTracks) {
    totalDuration += t.duration_seconds ? t.duration_seconds : 180; // Default 3 min if unknown
  }
  if (timeEl) {
    timeEl.textContent = formatDuration(totalDuration);
  }

  if (scoreEl) {
    if (currentTransitions.length > 0) {
      const avg = Math.round(
        currentTransitions.reduce((acc, ev) => acc + (ev?.score || 0), 0) /
          currentTransitions.length
      );
      const tier = avg >= 80 ? "taste-high" : avg >= 65 ? "taste-mid" : "taste-low";
      scoreEl.className = `chip ${tier}`;
      scoreEl.textContent = `Avg Flow: ${avg}%`;
    } else {
      scoreEl.className = "chip taste-mid";
      scoreEl.textContent = "Avg Flow: —";
    }
  }

  const dlBtn = $("builder-download-missing-btn");
  if (dlBtn) {
    const missing = setTracks.filter(
      (t) => !t.local_path && !t.has_local_file && t.source !== "local"
    );
    if (missing.length > 0) {
      dlBtn.disabled = false;
      dlBtn.textContent = `DOWNLOAD MISSING (${missing.length})`;
      dlBtn.className = "btn tiny primary";
      dlBtn.title = `Download ${missing.length} missing track(s) as .m4a`;
    } else {
      dlBtn.disabled = true;
      dlBtn.textContent = "DOWNLOAD MISSING (0)";
      dlBtn.className = "btn tiny ghost";
      dlBtn.title = "All tracks in this set are downloaded locally";
    }
  }
}

async function downloadMissingTracks() {
  const missing = setTracks.filter(
    (t) => !t.local_path && !t.has_local_file && t.source !== "local"
  );
  if (missing.length === 0) {
    emit("toast", "All tracks in this set are already downloaded locally");
    return;
  }
  const trackIds = missing.map((t) => t.id);
  try {
    await api.startJob("download-tracks", { track_ids: trackIds });
    emit("toast", `Started download for ${missing.length} track(s)`);
    emit("tab:show", "run");
  } catch (err) {
    emit("toast", `Failed to start download job: ${err.message}`);
  }
}

async function evaluateAndRenderCurve() {
  if (setTracks.length < 2) {
    currentTransitions = [];
    drawEmptyCurve();
    updateSummary();
    return;
  }

  const trackIds = setTracks.map((t) => t.id);
  try {
    const res = await api.setHelperEvaluate({
      track_ids: trackIds,
      flow: activeFlow,
    });
    currentTransitions = res.transitions || [];
    renderTracklist();
    drawEnergyCurve();
    updateSummary();
  } catch (err) {
    console.error("Evaluation failed", err);
  }
}

function drawEmptyCurve() {
  const svg = $("builder-energy-curve");
  const range = $("builder-curve-range");
  if (!svg) return;
  svg.replaceChildren(
    el("text", {
      x: "300",
      y: "45",
      "text-anchor": "middle",
      fill: "#666",
      "font-size": "12",
      text: "Add 2+ tracks to see the BPM and energy progression",
    })
  );
  if (range) range.textContent = "—";
}

function drawEnergyCurve() {
  const svg = $("builder-energy-curve");
  const range = $("builder-curve-range");
  if (!svg || setTracks.length < 2) return;

  const bpms = setTracks.map((t) => (t.bpm ? t.bpm.value : 126.0));
  const minBpm = Math.min(...bpms);
  const maxBpm = Math.max(...bpms);

  if (range) {
    range.textContent =
      minBpm === maxBpm ? `${minBpm.toFixed(1)} BPM` : `${minBpm.toFixed(1)} – ${maxBpm.toFixed(1)} BPM`;
  }

  const w = 600;
  const h = 80;
  const padX = 35;
  const padY = 16;
  const plotW = w - padX * 2;
  const plotH = h - padY * 2;

  const bpmSpan = Math.max(1.0, maxBpm - minBpm);
  const stepX = plotW / (setTracks.length - 1);

  const points = bpms.map((bpm, idx) => {
    const x = padX + idx * stepX;
    const y = padY + plotH - ((bpm - minBpm) / bpmSpan) * plotH;
    return { x, y, bpm, track: setTracks[idx] };
  });

  const polylineCoords = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  // Generate SVG elements
  const elements = [];

  // Gradient area fill
  const areaCoords = `${points[0].x.toFixed(1)},${h} ${polylineCoords} ${points[points.length - 1].x.toFixed(1)},${h}`;
  elements.push(
    el("polygon", {
      points: areaCoords,
      fill: "rgba(255, 77, 26, 0.08)",
    })
  );

  // Line
  elements.push(
    el("polyline", {
      points: polylineCoords,
      fill: "none",
      stroke: "var(--accent)",
      "stroke-width": "2.5",
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    })
  );

  // Circles and track labels
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    elements.push(
      el("circle", {
        cx: p.x.toFixed(1),
        cy: p.y.toFixed(1),
        r: "4.5",
        fill: "#0b0b0c",
        stroke: "var(--accent)",
        "stroke-width": "2",
      })
    );

    // BPM text
    elements.push(
      el("text", {
        x: p.x.toFixed(1),
        y: (p.y - 8).toFixed(1),
        "text-anchor": "middle",
        fill: "#a1a1aa",
        "font-size": "9",
        "font-family": "var(--mono)",
        text: `${Math.round(p.bpm)}`,
      })
    );

    // Key text under point
    const key = p.track.key || "";
    if (key) {
      elements.push(
        el("text", {
          x: p.x.toFixed(1),
          y: (p.y + 16).toFixed(1),
          "text-anchor": "middle",
          fill: "#ff8c66",
          "font-size": "9",
          "font-family": "var(--mono)",
          "font-weight": "bold",
          text: key,
        })
      );
    }
  }

  svg.replaceChildren(...elements);
}

async function refreshRecommendations() {
  if (activeMode === "bridge") {
    if (bridgePair) {
      await loadBridgeSuggestions(bridgePair.a, bridgePair.b, bridgePair.idxA);
    }
    return;
  }

  const container = $("builder-next-results");
  const banner = $("builder-next-ref-title");
  if (!container) return;

  if (setTracks.length === 0) {
    container.replaceChildren(
      el("div", {
        class: "empty",
        text: "Add tracks to the set on the left to see intelligent next-track recommendations.",
      })
    );
    if (banner) banner.textContent = "Pick or add a track first";
    return;
  }

  const refIdx =
    selectedTrackIdx !== null && selectedTrackIdx < setTracks.length
      ? selectedTrackIdx
      : setTracks.length - 1;
  const refTrack = setTracks[refIdx];

  if (banner) {
    banner.textContent = `#${refIdx + 1}: ${refTrack.artist} — ${refTrack.title} (${refTrack.key || "no key"}, ${fmtBpm(refTrack.bpm)})`;
  }

  container.replaceChildren(el("div", { class: "empty", text: "Finding harmonic recommendations…" }));

  try {
    const res = await api.setHelperSuggestNext({
      from_track_id: refTrack.id,
      flow: activeFlow,
      local_only: localOnly,
      limit: 15,
      bpm_max_delta: 6.0,
    });

    const suggestions = res.suggestions || [];
    if (suggestions.length === 0) {
      container.replaceChildren(
        el("div", { class: "empty", text: "No matching candidate tracks found in catalog." })
      );
      return;
    }

    container.replaceChildren(
      ...suggestions.map((sug) => buildSuggestionCard(sug, refTrack))
    );
    syncAllPlayButtons();
  } catch (err) {
    container.replaceChildren(el("div", { class: "empty", text: err.message }));
  }
}

function buildSuggestionCard(suggestion, fromTrack) {
  const track = suggestion.track;
  const ev = suggestion.evaluation;
  const isPlaying = currentTrack()?.id === track.id && isAudioPlaying();

  const playBtn = el("button", {
    class: `icon-btn builder-play-btn${isPlaying ? " playing" : ""}`,
    type: "button",
    dataset: { trackId: track.id },
    title: isPlaying ? "Pause preview" : "Play preview",
    text: isPlaying ? "❚❚" : "▶",
  });
  playBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    playTrack(track);
  });

  const addBtn = el("button", {
    class: "btn tiny primary",
    type: "button",
    text: "+ ADD TO SET",
  });
  addBtn.addEventListener("click", () => {
    addTrackToSet(track);
    emit("toast", `Added "${track.title}" to set`);
  });

  const score = Math.round(ev.score);
  const tier = score >= 80 ? "taste-high" : score >= 65 ? "taste-mid" : "taste-low";
  const scorePill = el("span", { class: `chip ${tier}`, text: `${score}% Match` });

  const moveMap = {
    same: "Same Key",
    "+1": "Smooth +1",
    "-1": "Smooth -1",
    relative: "Relative A/B",
    "+2": "Energy +2",
    "-2": "Energy -2",
    "+7": "Modulation +7",
    clash: "Clash",
    unknown: "Key Unknown",
  };
  const moveName = moveMap[ev.camelot_move] || ev.camelot_move;
  const deltaText =
    ev.bpm_delta === 0
      ? "Steady"
      : ev.bpm_delta > 0
        ? `+${ev.bpm_delta.toFixed(1)} BPM`
        : `${ev.bpm_delta.toFixed(1)} BPM`;

  return el("div", { class: "builder-card" }, [
    el("div", { class: "builder-card-left" }, [
      playBtn,
      artwork(track.artwork_url, "builder-card-art"),
      el("div", { class: "builder-card-info" }, [
        el("div", { class: "builder-card-title", text: track.title }),
        el("div", { class: "builder-card-artist dim", text: track.artist }),
        el("div", { class: "track-meta builder-card-meta" }, [
          track.local_path || track.source === "local"
            ? el("span", { class: "chip local", text: "LOCAL" })
            : null,
          el("span", { class: "chip bpm", text: fmtBpm(track.bpm) }),
          camelotBadge(track.key, "chip"),
          scorePill,
        ]),
        el(
          "div",
          { class: "builder-card-move dim mono" },
          [document.createTextNode(`${moveName} · ${deltaText}`)]
        ),
      ]),
    ]),
    el("div", { class: "builder-card-actions" }, [addBtn]),
  ]);
}

function openBridgeMode(trackA, trackB, indexA) {
  bridgePair = { a: trackA, b: trackB, idxA: indexA, idxB: indexA + 1 };
  switchMode("bridge");

  const nodeA = $("bridge-node-a");
  const nodeB = $("bridge-node-b");
  if (nodeA) nodeA.textContent = `${trackA.artist} — ${trackA.title} (${trackA.key || "no key"}, ${fmtBpm(trackA.bpm)})`;
  if (nodeB) nodeB.textContent = `${trackB.artist} — ${trackB.title} (${trackB.key || "no key"}, ${fmtBpm(trackB.bpm)})`;

  loadBridgeSuggestions(trackA, trackB, indexA);
}

async function loadBridgeSuggestions(trackA, trackB, insertIdx) {
  const container = $("builder-bridge-results");
  if (!container) return;
  container.replaceChildren(
    el("div", { class: "empty", text: "Finding bridge stepping-stone tracks…" })
  );

  try {
    const res = await api.setHelperBridge({
      track_a_id: trackA.id,
      track_b_id: trackB.id,
      limit: 12,
      local_only: localOnly,
    });

    const bridges = res.bridges || [];
    if (bridges.length === 0) {
      container.replaceChildren(
        el("div", {
          class: "empty",
          text: "No bridge tracks found in catalog bridging these tempos and keys.",
        })
      );
      return;
    }

    container.replaceChildren(
      ...bridges.map((b) => buildBridgeCard(b, insertIdx))
    );
    syncAllPlayButtons();
  } catch (err) {
    container.replaceChildren(el("div", { class: "empty", text: err.message }));
  }
}

function buildBridgeCard(bridge, insertIdx) {
  const track = bridge.bridge_track;
  const isPlaying = currentTrack()?.id === track.id && isAudioPlaying();

  const playBtn = el("button", {
    class: `icon-btn builder-play-btn${isPlaying ? " playing" : ""}`,
    type: "button",
    dataset: { trackId: track.id },
    title: isPlaying ? "Pause preview" : "Play preview",
    text: isPlaying ? "❚❚" : "▶",
  });
  playBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    playTrack(track);
  });

  const insertBtn = el("button", {
    class: "btn tiny primary",
    type: "button",
    text: "INSERT BETWEEN",
  });
  insertBtn.addEventListener("click", () => {
    // Splicing bridge track between A and B
    setTracks.splice(insertIdx + 1, 0, track);
    selectedTrackIdx = insertIdx + 1;
    emit("toast", `Inserted "${track.title}" as bridge`);
    renderTracklist();
    evaluateAndRenderCurve();
    switchMode("next");
    refreshRecommendations();
  });

  const score = Math.round(bridge.combined_score);
  const tier = score >= 80 ? "taste-high" : score >= 65 ? "taste-mid" : "taste-low";
  const scorePill = el("span", { class: `chip ${tier}`, text: `${score}% Bridge` });

  return el("div", { class: "builder-card" }, [
    el("div", { class: "builder-card-left" }, [
      playBtn,
      artwork(track.artwork_url, "builder-card-art"),
      el("div", { class: "builder-card-info" }, [
        el("div", { class: "builder-card-title", text: track.title }),
        el("div", { class: "builder-card-artist dim", text: track.artist }),
        el("div", { class: "track-meta builder-card-meta" }, [
          track.local_path || track.source === "local"
            ? el("span", { class: "chip local", text: "LOCAL" })
            : null,
          el("span", { class: "chip bpm", text: fmtBpm(track.bpm) }),
          camelotBadge(track.key, "chip"),
          scorePill,
        ]),
        el(
          "div",
          { class: "builder-card-move dim mono" },
          [
            document.createTextNode(
              `A ➔ Bridge: ${bridge.eval_from_a.camelot_move} (${Math.round(bridge.eval_from_a.score)}%) | Bridge ➔ B: ${bridge.eval_to_b.camelot_move} (${Math.round(bridge.eval_to_b.score)}%)`
            ),
          ]
        ),
      ]),
    ]),
    el("div", { class: "builder-card-actions" }, [insertBtn]),
  ]);
}

async function searchCatalogToAdd() {
  const input = $("builder-catalog-search");
  const container = $("builder-next-results");
  if (!input || !container) return;
  const q = input.value.trim();
  if (!q) {
    refreshRecommendations();
    return;
  }

  container.replaceChildren(el("div", { class: "empty", text: "Searching catalog…" }));
  try {
    const res = await api.searchTracks(q, 15);
    const tracks = res.tracks || [];
    if (tracks.length === 0) {
      container.replaceChildren(
        el("div", { class: "empty", text: `No tracks matching "${q}"` })
      );
      return;
    }

    container.replaceChildren(
      ...tracks.map((t) => {
        const isPlaying = currentTrack()?.id === t.id && isAudioPlaying();
        const playBtn = el("button", {
          class: `icon-btn builder-play-btn${isPlaying ? " playing" : ""}`,
          type: "button",
          dataset: { trackId: t.id },
          text: isPlaying ? "❚❚" : "▶",
        });
        playBtn.addEventListener("click", () => playTrack(t));

        const addBtn = el("button", {
          class: "btn tiny primary",
          type: "button",
          text: "+ ADD",
        });
        addBtn.addEventListener("click", () => {
          addTrackToSet(t);
          emit("toast", `Added "${t.title}" to set`);
        });

        return el("div", { class: "builder-card" }, [
          el("div", { class: "builder-card-left" }, [
            playBtn,
            artwork(t.artwork_url, "builder-card-art"),
            el("div", { class: "builder-card-info" }, [
              el("div", { class: "builder-card-title", text: t.title }),
              el("div", { class: "builder-card-artist dim", text: t.artist }),
              el("div", { class: "track-meta builder-card-meta" }, [
                t.local_path || t.source === "local"
                  ? el("span", { class: "chip local", text: "LOCAL" })
                  : null,
                el("span", { class: "chip bpm", text: fmtBpm(t.bpm) }),
                camelotBadge(t.key, "chip"),
              ]),
            ]),
          ]),
          el("div", { class: "builder-card-actions" }, [addBtn]),
        ]);
      })
    );
    syncAllPlayButtons();
  } catch (err) {
    container.replaceChildren(el("div", { class: "empty", text: err.message }));
  }
}
