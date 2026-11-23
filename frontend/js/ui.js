/* Shared UI helpers: toasts, escaping, loading/empty/error state blocks. */

import { emit } from "./events.js";

export function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (ch) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[ch],
  );
}

export function toast(message, kind = "ok", ms = 4200) {
  const stack = document.getElementById("toasts");
  if (!stack) return;
  const el = document.createElement("div");
  el.className = `toast ${kind === "ok" ? "" : kind}`.trim();
  el.setAttribute("role", "status");
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

export function loadingHTML(label = "loading…") {
  return (
    `<div class="state-block" role="status"><div class="skeleton" style="width:80%"></div>` +
    `<div class="skeleton" style="width:60%"></div><div class="skeleton" style="width:70%"></div>` +
    `<span>${esc(label)}</span></div>`
  );
}

export function emptyHTML(title, nextStep = "") {
  return (
    `<div class="state-block"><div class="big">${esc(title)}</div>` +
    `<span>${esc(nextStep)}</span></div>`
  );
}

export function errorHTML(message, retryEvent = null) {
  return (
    `<div class="state-block error"><div class="big">Something failed</div>` +
    `<span>${esc(message)}</span>` +
    (retryEvent
      ? `<div style="margin-top:var(--s3)"><button class="btn" data-retry="${esc(retryEvent)}">Retry</button></div>`
      : "") +
    `</div>`
  );
}

/** Camelot → colour segment (1..12) for key badges. */
export function camelotSegment(notation) {
  const match = String(notation ?? "").match(/(\d+)/);
  if (!match) return null;
  const n = Number(match[1]);
  return n >= 1 && n <= 12 ? n : null;
}

export function keyBadge(notation) {
  if (!notation) return `<span class="key-badge" title="unknown key">—</span>`;
  const seg = camelotSegment(notation);
  return `<span class="key-badge"${seg ? ` data-segment="${seg}"` : ""}>${esc(notation)}</span>`;
}

/** Playback clock as M:SS (e.g. 0:24) — never raw decimal seconds. */
export function fmtDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

/** Bind a container's retry buttons to a loader callback. */
export function bindRetries(rootEl, retry) {
  rootEl.querySelectorAll("[data-retry]").forEach((btn) => {
    btn.addEventListener("click", retry);
  });
}

/** Guard helper: emit a domain event after a successful mutation. */
export function emitAfter(event, payload) {
  emit(event, payload);
}
