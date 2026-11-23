/* Dashboard: stat band, Camelot wheel, BPM histogram, recent tracks. */

import { api } from "../api.js";
import { on, emit } from "../events.js";
import { loadingHTML, emptyHTML, errorHTML, bindRetries, esc, toast } from "../ui.js";
import { bpmHistogram, camelotWheel } from "../charts.js";
import { trackRowHTML, bindTrackRows } from "../components.js";

let picks = { key: null, bucket: null };

function seeds_total(s) {
  const seeds = s.seeds ?? {};
  return seeds.total ?? 0;
}

function statBand(dash) {
  const s = dash.stats ?? {};
  const tracks = s.tracks ?? {};
  const seeds = seeds_total(s);
  const band = document.getElementById("dash-stats");
  const cells = [
    { label: "tracks", value: tracks.total ?? 0 },
    { label: "embedded", value: tracks.embedded ?? 0 },
    { label: "heard", value: tracks.heard ?? 0 },
    { label: "seeds", value: seeds },
    { label: "artists", value: dash.analytics?.total_artists ?? 0 },
    { label: "local files", value: dash.analytics?.total_local ?? 0 },
  ];
  band.innerHTML = cells
    .map(
      (c) =>
        `<div class="stat"><div class="value">${Number(c.value).toLocaleString()}</div><div class="label">${esc(c.label)}</div></div>`,
    )
    .join("");
}

function recentRows(tracks) {
  if (!tracks?.length) return emptyHTML("No tracks indexed yet", "Run Pipeline → Index catalog to build the embedding index.");
  return `<div class="track-list">${tracks.map((t) => trackRowHTML(t)).join("")}</div>`;
}

function renderRecent(dash) {
  const el = document.getElementById("dash-recent");
  el.innerHTML = recentRows(dash.recent_tracks);
  bindTrackRows(el, dash.recent_tracks ?? []);
}

function renderWheelAndHist(dash) {
  const wheelEl = document.getElementById("dash-wheel");
  const histEl = document.getElementById("dash-bpm");
  const keys = dash.analytics?.top_keys ?? [];
  const buckets = dash.analytics?.bpm_buckets ?? [];

  if (!keys.length) {
    wheelEl.innerHTML = emptyHTML("No key data yet", "Embed tracks to plot the harmony wheel.");
  } else {
    wheelEl.innerHTML = camelotWheel(keys, { size: 340 });
    wheelEl.querySelectorAll(".wheel-segment").forEach((seg) =>
      seg.addEventListener("click", () => {
        const notation = seg.dataset.key;
        if (!notation) return;
        emit("catalog:filter", { key: notation });
        const digTab = document.querySelector('[data-tab="dig"]');
        if (digTab) digTab.click();
      }),
    );
  }

  histEl.innerHTML = bpmHistogram(buckets);
  histEl.querySelectorAll(".bar[data-bpm-min]").forEach((bar) =>
    bar.addEventListener("click", () => {
      const bpmMin = Number(bar.dataset.bpmMin);
      const bpmMax = Number(bar.dataset.bpmMax);
      if (!Number.isFinite(bpmMin) || !Number.isFinite(bpmMax)) return;
      emit("catalog:filter", { bpm_min: bpmMin, bpm_max: bpmMax });
      const digTab = document.querySelector('[data-tab="dig"]');
      if (digTab) digTab.click();
    }),
  );
}

async function load() {
  const el = document.getElementById("dash-recent");
  try {
    el.innerHTML = loadingHTML("loading dashboard…");
    const dash = await api.dashboard();
    statBand(dash);
    renderWheelAndHist(dash);
    renderRecent(dash);
  } catch (err) {
    document.getElementById("dash-stats").innerHTML = "";
    el.innerHTML = errorHTML(err.message, "dash-retry");
    bindRetries(el, load);
  }
}

export function setupDashboard() {
  on("catalog:changed", load);
  on("track:downloaded", load);
  /* artists:changed is handled in-place by syncHeartButtons — a full reload
   * here wipes scroll position and looks like a page refresh. */
  return load;
}
