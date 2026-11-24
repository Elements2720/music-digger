/* Set Crate drawer: a live view of the Set Builder working playlist, reachable
 * from any workspace. Renders from `set:changed` snapshots emitted by the
 * builder; removal requested here, applied by the builder. */

import { on } from "./events.js";
import { esc } from "./ui.js";
import { iconClose } from "./icons.js";

let snapshot = [];

function el(id) {
  return document.getElementById(id);
}

function render() {
  const body = el("crate-body");
  const badge = el("crate-count-badge");
  badge.textContent = String(snapshot.length);

  if (!snapshot.length) {
    body.innerHTML = `<p class="crate-empty">The crate is empty — dig a track and press <span class="mono">+ Set</span>, or compose in the Set Builder.</p>`;
    return;
  }
  body.innerHTML = snapshot
    .map(
      (t, i) => `
  <div class="crate-row">
    <span class="t-meta">${i + 1}</span>
    <img class="crate-art" src="${esc(t.artwork_url ?? "")}" alt="" loading="lazy" ${t.artwork_url ? "" : "hidden"}>
    <div class="t-main">
      <div class="t-title">${esc(t.title)}</div>
      <div class="t-artist">${esc(t.artist)} · ${t.bpm != null ? t.bpm + " bpm" : "—"} ${t.key ? "· " + esc(t.key) : ""}</div>
    </div>
    <button class="icon-btn" data-crate-remove="${i}" aria-label="Remove ${esc(t.title)} from crate">${iconClose()}</button>
  </div>`,
    )
    .join("");
  body.querySelectorAll("[data-crate-remove]").forEach((b) =>
    b.addEventListener("click", () => {
      const removed = snapshot[Number(b.dataset.crateRemove)];
      if (removed) document.dispatchEvent(new CustomEvent("builder:remove-track", { detail: removed }));
    }),
  );
}

function open() {
  el("crate").classList.add("open");
  el("crate").setAttribute("aria-hidden", "false");
  el("crate-toggle").setAttribute("aria-expanded", "true");
}

function close() {
  el("crate").classList.remove("open");
  el("crate").setAttribute("aria-hidden", "true");
  el("crate-toggle").setAttribute("aria-expanded", "false");
}

export function setupCrate() {
  el("crate-close").innerHTML = iconClose();

  el("crate-toggle").addEventListener("click", () => {
    el("crate").classList.contains("open") ? close() : open();
  });
  el("crate-close").addEventListener("click", close);
  el("crate").querySelector("[data-close-crate]").addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && el("crate").classList.contains("open")) close();
  });
  el("crate-open-builder").addEventListener("click", () => {
    close();
    document.querySelector('[data-tab="builder"]').click();
  });

  on("set:changed", (tracks) => {
    snapshot = Array.isArray(tracks) ? tracks : [];
    render();
  });

  render();
  return () => {};
}
