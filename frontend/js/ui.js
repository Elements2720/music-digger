/* Small DOM helpers plus the shared track/set row renderers. */

import { api } from "./api.js";
import { emit } from "./state.js";
import { playTrack } from "./player.js";
import { PLACEHOLDER, fmtBpm } from "./format.js";

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child !== null && child !== undefined) node.append(child);
  }
  return node;
}

export function artwork(url, className = "row-art") {
  const image = el("img", {
    class: className,
    alt: "",
    loading: "lazy",
    src: url || PLACEHOLDER,
  });
  image.addEventListener(
    "error",
    () => {
      image.src = PLACEHOLDER;
    },
    { once: true }
  );
  return image;
}

export function chips(track, { exact = false } = {}) {
  const wrap = el("div", { class: "track-meta" });
  if (track.source === "local" || track.local_path) {
    wrap.append(el("span", { class: "chip local", text: "LOCAL" }));
  }
  const bpm = fmtBpm(track.bpm);
  if (bpm) wrap.append(el("span", { class: "chip bpm", text: bpm }));
  if (track.key) wrap.append(el("span", { class: "chip key", text: track.key }));
  if (exact) wrap.append(el("span", { class: "chip", text: "ID" }));
  return wrap;
}

async function toggleHeard(track, button) {
  const next = !track.is_heard;
  button.disabled = true;
  try {
    await api.setHeard(track.id, next);
    track.is_heard = next;
    button.textContent = next ? "✓" : "○";
    button.title = next ? "Heard — click to undo" : "Mark as heard";
    button.classList.toggle("heard", next);
    emit("heard:changed", { track, heard: next });
  } catch (error) {
    emit("toast", error.message);
  } finally {
    button.disabled = false;
  }
}

export function trackRow(
  track,
  { rank = null, similarity = null, exact = false } = {}
) {
  const play = el("button", {
    class: "icon-btn",
    type: "button",
    title: "Play 30 s preview",
    text: "▶",
  });
  play.addEventListener("click", () => playTrack(track));

  const heard = el("button", {
    class: `icon-btn${track.is_heard ? " heard" : ""}`,
    type: "button",
    title: track.is_heard ? "Heard — click to undo" : "Mark as heard",
    text: track.is_heard ? "✓" : "○",
  });
  heard.addEventListener("click", () => toggleHeard(track, heard));

  const dig = el("button", { class: "dig-btn", type: "button", text: "DIG >" });
  dig.addEventListener("click", () => emit("dig:track", track));

  const addSet = el("button", {
    class: "btn tiny ghost add-set-btn",
    type: "button",
    title: "Add to Set Builder",
    text: "+ SET",
  });
  addSet.addEventListener("click", () => {
    emit("builder:add-track", track);
    emit("toast", `Added "${track.title}" to set plan`);
  });

  const del = el("button", {
    class: "icon-btn delete-btn",
    type: "button",
    title: "Delete from catalog",
    text: "✕",
  });

  const main = el("div", { class: "track-main" }, [
    artwork(track.artwork_url),
    el("div", { class: "picker-copy" }, [
      el("div", { class: "row-title", text: track.title }),
      el("div", { class: "row-artist", text: track.artist }),
    ]),
  ]);

  const row = el("div", { class: "track-row", "data-track-id": track.id }, [
    el("div", { class: "track-rank", text: rank === null ? "•" : String(rank) }),
    main,
    chips(track, { exact }),
    el("div", {
      class: "track-score",
      text: similarity === null ? "" : `${Number(similarity).toFixed(1)}%`,
    }),
    el("div", { class: "track-actions" }, [play, heard, dig, addSet, del]),
  ]);

  del.addEventListener("click", async (e) => {
    e.stopPropagation();
    const confirmed = window.confirm(
      `Delete "${track.artist} - ${track.title}" from catalog?`
    );
    if (!confirmed) return;
    const alsoBlacklist = window.confirm(
      `Also BLACKLIST "${track.artist} - ${track.title}" to prevent re-importing?`
    );
    del.disabled = true;
    try {
      await api.deleteTrack(track.id, alsoBlacklist);
      emit("toast", `Deleted track${alsoBlacklist ? " (blacklisted)" : ""}`);
      emit("track:deleted", { trackId: track.id });
      row.remove();
    } catch (err) {
      emit("toast", err.message);
      del.disabled = false;
    }
  });

  return row;
}

export function renderMatches(container, matches, emptyText) {
  container.replaceChildren();
  if (!matches || matches.length === 0) {
    container.append(el("div", { class: "empty", text: emptyText }));
    return;
  }
  container.append(
    el("div", { class: "result-head" }, [
      el("span", { text: "#" }),
      el("span", { text: "TRACK" }),
      el("span", { text: "BPM / KEY" }),
      el("span", { text: "MATCH" }),
      el("span", { text: "" }),
    ])
  );
  matches.forEach((match, index) => {
    container.append(
      trackRow(match.track, {
        rank: index + 1,
        similarity: match.similarity,
        exact: match.is_exact_id,
      })
    );
  });
}

export function setRow(djSet, { similarity = null, onOpen } = {}) {
  const bpm =
    djSet.bpm_min !== null && djSet.bpm_max !== null
      ? `${Number(djSet.bpm_min).toFixed(0)}–${Number(djSet.bpm_max).toFixed(0)} BPM`
      : "BPM n/a";
  const sub = [
    djSet.artist || "unknown artist",
    `${djSet.passage_count} passages`,
    bpm,
  ].join(" · ");

  const row = el("button", { class: "set-row", type: "button" }, [
    artwork(djSet.thumbnail_url),
    el("div", { class: "set-copy" }, [
      el("div", { class: "set-name", text: djSet.title }),
      el("div", { class: "set-sub", text: sub }),
    ]),
    el("div", {
      class: "set-score",
      text: similarity === null ? "→" : `${Number(similarity).toFixed(1)}%`,
    }),
  ]);
  row.addEventListener("click", () => onOpen?.(djSet));
  return row;
}

export function renderKv(container, rows) {
  const table = el("table", { class: "kv" });
  for (const [label, value] of rows) {
    table.append(
      el("tr", {}, [
        el("td", { text: label }),
        el("td", { text: value === null || value === undefined ? "—" : String(value) }),
      ])
    );
  }
  container.replaceChildren(table);
}

export function toast(message) {
  let node = document.getElementById("toast");
  if (!node) {
    node = el("div", { class: "toast", id: "toast" });
    document.body.append(node);
  }
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("visible"), 3800);
}
