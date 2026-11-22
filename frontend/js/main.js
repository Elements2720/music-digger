/* Mission Control bootstrap: tabs, health badge, toasts, view lifecycle. */

import { api } from "./api.js";
import { on, state } from "./state.js";
import { setupPlayer } from "./player.js";
import { toast } from "./ui.js";
import * as runView from "./views/run.js";
import * as digView from "./views/dig.js";
import * as setsView from "./views/sets.js";
import * as builderView from "./views/builder.js";
import * as statsView from "./views/stats.js";

const VIEWS = {
  run: runView,
  dig: digView,
  sets: setsView,
  builder: builderView,
  stats: statsView,
};

let currentTab = null;

function showTab(name) {
  if (!VIEWS[name] || name === currentTab) return;
  currentTab = name;
  state.tab = name;
  for (const button of document.querySelectorAll(".tab")) {
    button.classList.toggle("active", button.dataset.tab === name);
  }
  for (const panel of document.querySelectorAll(".tab-panel")) {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  }
  VIEWS[name].mount();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function checkHealth() {
  const dot = document.getElementById("health-dot");
  const label = document.getElementById("health-label");
  try {
    await api.health();
    dot.className = "status-dot ok";
    label.textContent = "local";
  } catch {
    dot.className = "status-dot bad";
    label.textContent = "offline";
  }
}

function bind() {
  for (const button of document.querySelectorAll(".tab")) {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  }

  on("tab:show", (name) => showTab(name));
  on("toast", (message) => toast(message));
  on("dig:track", (track) => {
    showTab("dig");
    digView.selectTrack(track);
  });
  on("builder:add-track", (track) => {
    showTab("builder");
    builderView.addTrackToSet(track);
  });

  // A finished job can change counts or add a set: refresh whatever is open.
  on("job:finished", (job) => {
    if (!job || job.status !== "done") return;
    if (job.kind === "index" || job.kind === "fetch-metadata") {
      statsView.loadStats();
    }
    if (job.kind === "analyze-set") {
      setsView.loadSets();
    }
  });

  setupPlayer();
  showTab("run");
  checkHealth();
  setInterval(checkHealth, 10000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bind, { once: true });
} else {
  bind();
}
