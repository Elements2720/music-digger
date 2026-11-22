/* STATS tab: library counts, hardware probe, and the reset action. */

import { api } from "../api.js";
import { emit } from "../state.js";
import { el, renderKv } from "../ui.js";
import { fmtMemory } from "../format.js";

let mounted = false;

function $(id) {
  return document.getElementById(id);
}

function card(value, label) {
  return el("div", { class: "stat-card" }, [
    el("div", { class: "stat-value", text: String(value) }),
    el("div", { class: "stat-label", text: label }),
  ]);
}

async function loadStats() {
  const target = $("stats-cards");
  try {
    const body = await api.stats();
    target.replaceChildren(
      card(body.tracks.total, "tracks"),
      card(body.tracks.embedded, "embedded"),
      card(body.tracks.total - body.tracks.embedded, "pending embeddings"),
      card(body.seeds.total, "seed artists"),
      card(body.seeds.pending, "seeds pending"),
      card(body.seeds.fetched, "seeds fetched"),
      card(body.seeds.failed, "seeds failed"),
      card(body.seeds.electronic, "electronic seeds"),
      card(body.seeds.general, "general seeds"),
      card(body.sets.total, "dj sets")
    );
  } catch (error) {
    target.replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

async function loadHardware() {
  const target = $("hardware-table");
  try {
    const body = await api.hardware();
    renderKv(target, [
      ["Torch", body.torch_version],
      ["CUDA", body.cuda_available ? body.cuda_version || "yes" : "not available"],
      ["GPU", body.gpu_name],
      ["VRAM", `${fmtMemory(body.vram_free_mb)} free of ${fmtMemory(body.vram_total_mb)}`],
      ["RAM", `${fmtMemory(body.ram_free_mb)} free of ${fmtMemory(body.ram_total_mb)}`],
      ["FFmpeg", body.has_ffmpeg ? body.ffmpeg_path : "missing"],
      ["FFmpeg version", body.ffmpeg_version],
      ["GPU ready", body.gpu_ready ? "yes" : "no"],
    ]);
  } catch (error) {
    target.replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

async function resetEmbeddings() {
  if (!window.confirm("Drop every stored embedding? Metadata is kept.")) return;
  const button = $("reset-embeddings");
  button.disabled = true;
  try {
    const body = await api.resetEmbeddings();
    emit("toast", `Cleared ${body.cleared} embeddings`);
    await loadStats();
  } catch (error) {
    emit("toast", error.message);
  } finally {
    button.disabled = false;
  }
}

export function mount() {
  if (mounted) return;
  mounted = true;

  $("stats-refresh").addEventListener("click", () => {
    loadStats();
    loadHardware();
  });
  $("reset-embeddings").addEventListener("click", resetEmbeddings);

  loadStats();
  loadHardware();
}

export { loadStats, loadHardware };
