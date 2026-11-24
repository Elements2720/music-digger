/* Mission Control bootstrap: tabs, health badge, keyboard shortcuts, view lifecycle. */

import { api } from "./api.js";
import { hydrateLikedArtists } from "./components.js";
import { setupDashboard } from "./views/dashboard.js";
import { setupDig } from "./views/dig.js";
import { setupBuilder } from "./views/builder.js";
import { setupMix } from "./views/mix.js";
import { setupLibrary } from "./views/library.js";
import { setupPipeline } from "./views/pipeline.js";
import { setupPlayer } from "./player.js";
import { setupCrate } from "./crate.js";

const teardowns = [];

function activate(tabId) {
  document.querySelectorAll("[data-tab]").forEach((btn) => {
    const active = btn.dataset.tab === tabId;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll(".workspace").forEach((section) => {
    section.hidden = section.id !== `ws-${tabId}`;
  });
}

function currentTab() {
  const active = document.querySelector("[data-tab].active");
  return active ? active.dataset.tab : "dashboard";
}

function drawHealth(ok, detail) {
  const label = document.getElementById("health-label");
  const dot = document.getElementById("health-dot");
  if (label) label.textContent = detail;
  if (dot) dot.classList.toggle("ok", ok), dot.classList.toggle("bad", !ok);
}

async function refreshHealth() {
  try {
    await api.health();
    drawHealth(true, "API online");
  } catch {
    drawHealth(false, "API offline");
  }
}

async function refreshStats() {
  try {
    const stats = await api.stats();
    const tracks = document.getElementById("stat-tracks");
    const artists = document.getElementById("stat-artists");
    if (tracks) tracks.textContent = String(stats.tracks ?? 0);
    if (artists) artists.textContent = String(stats.artists ?? 0);
  } catch {
    /* stats are decorative; the badge shows connectivity */
  }
}

function setupTabs() {
  document.querySelectorAll("[data-tab]").forEach((btn) =>
    btn.addEventListener("click", () => activate(btn.dataset.tab)),
  );
  document.addEventListener("keydown", (e) => {
    if (e.altKey && e.key >= "1" && e.key <= "9") {
      const tabs = [...document.querySelectorAll("[data-tab]")];
      const tab = tabs[Number(e.key) - 1];
      if (tab) activate(tab.dataset.tab);
    }
  });
}

async function main() {
  setupTabs();
  await hydrateLikedArtists();
  const loadDashboard = setupDashboard();
  teardowns.push(loadDashboard);
  loadDashboard();
  teardowns.push(setupDig());
  teardowns.push(setupBuilder());
  teardowns.push(setupMix());
  teardowns.push(setupLibrary());
  teardowns.push(setupPipeline());
  setupPlayer();
  setupCrate();
  // Boot default only: never clobber a tab the user already clicked while
  // the boot fetches above were still in flight.
  if (currentTab() === "dashboard") activate("dashboard");
  await Promise.all([refreshHealth(), refreshStats()]);
  setInterval(refreshHealth, 30000);
}

main().catch((err) => {
  console.error("bootstrap failed", err);
  document.body?.insertAdjacentHTML(
    "afterbegin",
    `<div class="toast error" style="position:fixed;top:1rem;left:50%;transform:translateX(-50%);z-index:999">Bootstrap failed: ${err.message}</div>`,
  );
});
