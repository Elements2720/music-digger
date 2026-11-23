/* Library & Cleanup: three sub-tabs — Artists Hub (centered modal),
 * rule-based Tracks Cleanup wizard, Seeds & Blacklist explorer.
 */

import { api } from "../api.js";
import { emptyHTML, errorHTML, bindRetries, esc, toast } from "../ui.js";
import {
  artistRowHTML,
  trackRowHTML,
  bindTrackRows,
  trackArtHTML,
  pctLabel,
  likeBtnHTML,
  toggleArtistLike,
} from "../components.js";
import { iconClose, iconTrash } from "../icons.js";
/* ---------- sub-tab switching ---------- */

function selectLibMode(mode) {
  document.querySelectorAll("#lib-modes .mode").forEach((btn) => {
    const active = btn.dataset.libmode === mode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("[data-lib-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.libPanel !== mode;
  });
  if (mode === "tracks" && !document.getElementById("lib-tracks").children.length) loadTracks();
  if (mode === "seeds") {
    loadBlacklist();
    loadSeeds();
  }
}

/* ---------- Artists Hub ---------- */

async function loadArtists() {
  const el = document.getElementById("lib-artists");
  try {
    const params = new URLSearchParams({ limit: "100" });
    const q = document.getElementById("lib-artist-search").value.trim();
    if (q) params.set("q", q);
    const data = await api.artists(params);
    const artists = data.artists ?? [];
    if (!artists.length) {
      el.innerHTML = emptyHTML("No artists", "Run seed-crawl and fetch-metadata first.");
      return;
    }
    el.innerHTML = `<div class="track-list">${artists.map((a) => artistRowHTML(a)).join("")}</div>`;
    el.querySelectorAll("[data-like]").forEach((btn) =>
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleArtistLike(btn);
      }),
    );
    el.querySelectorAll("[data-artist-dig]").forEach((btn) =>
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        openArtistModal(btn.dataset.artistDig);
      }),
    );
    // Clicking the artist name/subtitle opens the modal (never triggers play).
    el.querySelectorAll(".artist-row .t-main").forEach((cell) =>
      cell.addEventListener("click", (e) => {
        e.stopPropagation();
        const name = cell.querySelector(".t-title")?.textContent;
        if (name) openArtistModal(name);
      }),
    );
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "lib-retry");
    bindRetries(el, loadArtists);
  }
}

/* ---------- Artist centered modal ---------- */

function closeArtistModal() {
  const modal = document.getElementById("artist-modal");
  modal.hidden = true;
  document.removeEventListener("keydown", escListener);
}

function escListener(e) {
  if (e.key === "Escape") closeArtistModal();
}

async function openArtistModal(artistName) {
  const modal = document.getElementById("artist-modal");
  const art = document.getElementById("artist-modal-art");
  const info = document.getElementById("artist-modal-info");
  const likeSlot = document.getElementById("modal-like-slot");
  const fetchBtn = document.getElementById("modal-fetch");
  const body = document.getElementById("artist-modal-body");
  modal.hidden = false;
  art.textContent = artistName.charAt(0).toUpperCase();
  info.innerHTML = `<h3 class="modal-title">${esc(artistName)}</h3>`;
  likeSlot.innerHTML = likeBtnHTML(artistName);
  fetchBtn.hidden = false;
  body.innerHTML = emptyHTML("loading…", "");
  document.getElementById("artist-modal-close").focus();
  document.addEventListener("keydown", escListener);
  try {
    const tracksRes = await api.artistTracks(artistName, new URLSearchParams({ limit: "100" }));
    const tracks = tracksRes.tracks ?? [];
    // Representative artwork: most recent track with cover art.
    const cover = tracks.find((t) => t.artwork_url)?.artwork_url;
    const pct = tracks.find((t) => t.taste_match_percent != null)?.taste_match_percent;
    art.textContent = "";
    art.style.backgroundImage = cover ? `url("${cover}")` : "";
    art.classList.toggle("t-art-img", Boolean(cover));
    info.innerHTML = `
      <h3 class="modal-title">${esc(artistName)}</h3>
      <span class="modal-sub">${tracks.length} tracks in catalog${pct != null ? ` · taste ${pctLabel(pct) ?? ""}` : ""}</span>`;
    likeSlot.innerHTML = likeBtnHTML(artistName);
    fetchBtn.onclick = async () => {
      try {
        await api.fetchArtist(artistName);
        toast(`Fetching ${artistName} — check Pipeline for progress`);
        openArtistModal(artistName);
      } catch (err) {
        toast(err.message, "error");
      }
    };

    body.innerHTML = tracks.length
      ? `<div class="track-list">${tracks.map((t) => trackRowHTML(t)).join("")}</div>`
      : emptyHTML("No tracks", "Use Fetch Artist to backfill the discography.");
    bindTrackRows(body, tracks);
  } catch (err) {
    body.innerHTML = errorHTML(err.message, "modal-retry");
    bindRetries(body, () => openArtistModal(artistName));
  }
}

/* ---------- Tracks cleanup wizard ---------- */

async function loadTracks() {
  const el = document.getElementById("lib-tracks");
  try {
    const params = new URLSearchParams({ limit: "60" });
    const q = document.getElementById("lib-track-search").value.trim();
    const data = q ? await api.searchTracks(q, 60) : await api.recentTracks(60);
    const tracks = data.results ?? data.tracks ?? [];
    if (!tracks.length) {
      el.innerHTML = emptyHTML("No tracks", "Adjust the filter.");
      return;
    }
    el.innerHTML = `<div class="track-list">${tracks
      .map(
        (t) => `
    <div class="track-row track-cleanup-row">
      <input type="checkbox" data-sel="${esc(t.id)}" aria-label="Select ${esc(t.title)}">
      ${trackArtHTML(t)}
      <div class="t-main">
        <div class="t-title">${esc(t.title)}</div>
        <div class="t-artist">${esc(t.artist)} · ${t.bpm != null ? t.bpm + " bpm" : "—"}</div>
      </div>
      ${t.has_local_file ? `<span class="chip chip-ok">LOCAL</span>` : `<span class="chip">preview</span>`}
      <button class="icon-btn danger" data-del-track="${esc(t.id)}" data-del-title="${esc(t.title)}" aria-label="Delete">${iconTrash()}</button>
    </div>`,
      )
      .join("")}</div>
    <div class="bulk-bar" id="lib-bulk-bar" hidden>
      <span class="mono" id="lib-bulk-count"></span>
      <button class="btn danger" id="lib-bulk-delete">Delete selected (blacklist)</button>
    </div>`;
    const bar = el.querySelector("#lib-bulk-bar");
    const count = el.querySelector("#lib-bulk-count");
    const syncBar = () => {
      const n = el.querySelectorAll("[data-sel]:checked").length;
      bar.hidden = n === 0;
      count.textContent = `${n} selected`;
    };
    el.querySelectorAll("[data-sel]").forEach((c) => c.addEventListener("change", syncBar));

    el.querySelectorAll("[data-del-track]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const title = btn.dataset.delTitle;
        if (confirm(`Delete "${title}" and blacklist it? Disk audio files are never touched.`)) {
          api
            .deleteTrack(btn.dataset.delTrack, true)
            .then(() => {
              toast("Track deleted + blacklisted");
              loadTracks();
            })
            .catch((err) => toast(err.message, "error"));
        }
      }),
    );
    el.querySelector("#lib-bulk-delete").addEventListener("click", () => {
      const ids = [...el.querySelectorAll("[data-sel]:checked")].map((c) => c.dataset.sel);
      if (!ids.length) {
        toast("Select tracks first", "error");
        return;
      }
      if (!confirm(`Delete ${ids.length} tracks and blacklist their artists? Disk audio files are never touched.`)) return;
      const names = [...new Set(tracks.filter((t) => ids.includes(t.id)).map((t) => t.artist))];
      api
        .bulkDeleteArtists(names, true)
        .then((res) => {
          toast(`Deleted ${res.artists_deleted ?? names.length} artists (blacklisted)`);
          loadTracks();
        })
        .catch((err) => toast(err.message, "error"));
    });
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "lib-tracks-retry");
    bindRetries(el, loadTracks);
  }
}

async function previewCleanup() {
  const result = document.getElementById("lib-cleanup-result");
  const genre = document.getElementById("lib-cleanup-genre").value;
  const tasteRaw = document.getElementById("lib-cleanup-taste").value.trim();
  const maxTaste = tasteRaw === "" ? null : Number(tasteRaw);
  if (!genre && maxTaste == null) {
    result.innerHTML = `<p class="error">Pick at least one rule (genre or taste %) first.</p>`;
    return;
  }
  const criteria = {
    max_taste_percent: maxTaste ?? undefined,
    genre: genre || undefined,
    protect_liked: document.getElementById("lib-cleanup-protect-liked").checked,
    protect_local: document.getElementById("lib-cleanup-protect-local").checked,
  };
  try {
    const data = await api.previewBulkCleanup(criteria);
    const artists = data.sample_artists ?? [];
    if (!data.artist_count) {
      result.innerHTML = emptyHTML("Nothing matches these rules", "");
      document.getElementById("lib-cleanup-run").disabled = true;
      return;
    }
    result.innerHTML = `
    <p class="mono">${data.artist_count} artists match (${data.track_count} tracks) — sample:</p>
    <div class="track-list">${artists.map((a) => artistRowHTML(a)).join("")}</div>
    <p class="hint">Confirm delete removes catalog/database rows only — disk audio files are never touched.</p>`;
    document.getElementById("lib-cleanup-run").disabled = false;
  } catch (err) {
    result.innerHTML = errorHTML(err.message, "cleanup-retry");
    bindRetries(result, previewCleanup);
  }
}

async function runCleanup() {
  const result = document.getElementById("lib-cleanup-result");
  const genre = document.getElementById("lib-cleanup-genre").value;
  const tasteRaw = document.getElementById("lib-cleanup-taste").value.trim();
  const maxTaste = tasteRaw === "" ? null : Number(tasteRaw);
  if (!confirm("Delete all matched artists and blacklist them? This cannot be undone. Disk audio files are never touched.")) return;
  try {
    const data = await api.executeBulkCleanup({
      max_taste_percent: maxTaste ?? undefined,
      genre: genre || undefined,
      protect_liked: document.getElementById("lib-cleanup-protect-liked").checked,
      protect_local: document.getElementById("lib-cleanup-protect-local").checked,
      blacklist: document.getElementById("lib-cleanup-blacklist").checked,
      reason: `cleanup: ${[genre && `genre=${genre}`, maxTaste != null && `taste<=${maxTaste}%`].filter(Boolean).join(" ") || "manual"}`,
    });
    result.innerHTML = `<p class="mono ok">Deleted ${data.artists_deleted ?? 0} artists · ${data.tracks_deleted ?? 0} tracks · ${data.seeds_removed ?? 0} seeds removed · ${data.skipped_protected ?? 0} protected skipped.</p>`;
    loadArtists();
  } catch (err) {
    result.innerHTML = errorHTML(err.message, "cleanup-run-retry");
    bindRetries(result, runCleanup);
  }
}

/* ---------- Seeds & Blacklist ---------- */

async function loadBlacklist() {
  const el = document.getElementById("lib-blacklist");
  try {
    const data = await api.blacklist({ limit: "200" });
    const entries = data.entries ?? [];
    if (!entries.length) {
      el.innerHTML = emptyHTML("Blacklist empty", "Add an artist above.");
      return;
    }
    el.innerHTML = `<div class="track-list">${entries
      .map(
        (e) => `
    <div class="track-row blacklist-row">
      <div class="t-main"><div class="t-title">${esc(e.artist_name ?? e.artist ?? e.value ?? "")}</div><div class="t-artist">${esc(e.reason ?? "")}</div></div>
      <button class="icon-btn" data-unblack="${esc(e.id ?? e.artist_name ?? "")}">Remove</button>
    </div>`,
      )
      .join("")}</div>`;
    el.querySelectorAll("[data-unblack]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        try {
          await api.removeBlacklist(btn.dataset.unblack);
          loadBlacklist();
          toast("Removed from blacklist");
        } catch (err) {
          toast(err.message, "error");
        }
      }),
    );
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "black-retry");
    bindRetries(el, loadBlacklist);
  }
}

async function addBlacklist() {
  const input = document.getElementById("lib-blacklist-add");
  const name = input.value.trim();
  if (!name) {
    toast("Type an artist name", "error");
    return;
  }
  try {
    await api.addBlacklist({ name, reason: "manual" });
    input.value = "";
    loadBlacklist();
    toast(`${name} blacklisted`);
  } catch (err) {
    toast(err.message, "error", 8000);
  }
}

async function loadSeeds() {
  const el = document.getElementById("lib-seeds");
  const summary = document.getElementById("lib-seed-summary");
  try {
    const params = new URLSearchParams({ limit: "100" });
    const status = document.getElementById("lib-seed-status").value;
    if (status) params.set("status", status);
    const q = document.getElementById("lib-seed-search").value.trim();
    if (q) params.set("q", q);
    const data = await api.seeds(params);
    const seeds = data.seeds ?? [];
    const b = data.breakdown ?? {};
    summary.textContent = `${data.total ?? seeds.length} seeds · pending ${b.pending ?? 0} · fetched ${b.fetched ?? 0} · failed ${b.failed ?? 0}`;
    if (!seeds.length) {
      el.innerHTML = emptyHTML("No seeds here", "Adjust status or filter.");
      return;
    }
    el.innerHTML = `<div class="track-list">${seeds
      .map(
        (s) => `
    <div class="track-row blacklist-row">
      <div class="t-main">
        <div class="t-title">${esc(s.name ?? s.artist_name ?? "")}</div>
        <div class="t-artist">${esc(s.category ?? "")} · ${esc(s.source ?? "")}</div>
      </div>
      <span class="chip${s.status === "fetched" ? " chip-ok" : ""}">${esc(s.status ?? "")}</span>
      <button class="icon-btn" data-del-seed="${esc(s.name ?? s.artist_name ?? "")}" aria-label="Delete seed">${iconTrash()}</button>
    </div>`,
      )
      .join("")}</div>`;
    el.querySelectorAll("[data-del-seed]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        try {
          await api.deleteSeed(btn.dataset.delSeed);
          loadSeeds();
          toast("Seed deleted");
        } catch (err) {
          toast(err.message, "error");
        }
      }),
    );
  } catch (err) {
    el.innerHTML = errorHTML(err.message, "seeds-retry");
    bindRetries(el, loadSeeds);
  }
}

async function purgePending() {
  if (!confirm("Purge ALL pending seeds? Fetched and failed seeds are kept.")) return;
  try {
    const res = await api.purgeSeeds({ status: "pending" });
    toast(`Purged ${res.purged ?? 0} pending seeds`);
    loadSeeds();
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- setup ---------- */

export function setupLibrary() {
  document.querySelectorAll("#lib-modes .mode").forEach((btn) =>
    btn.addEventListener("click", () => selectLibMode(btn.dataset.libmode)),
  );

  let artistTimer = null;
  document.getElementById("lib-artist-search").addEventListener("input", () => {
    clearTimeout(artistTimer);
    artistTimer = setTimeout(loadArtists, 250);
  });
  let trackTimer = null;
  document.getElementById("lib-track-search").addEventListener("input", () => {
    clearTimeout(trackTimer);
    trackTimer = setTimeout(loadTracks, 250);
  });
  let seedTimer = null;
  document.getElementById("lib-seed-search").addEventListener("input", () => {
    clearTimeout(seedTimer);
    seedTimer = setTimeout(loadSeeds, 250);
  });
  document.getElementById("lib-seed-status").addEventListener("change", loadSeeds);

  document.getElementById("lib-cleanup-preview").addEventListener("click", previewCleanup);
  document.getElementById("lib-cleanup-run").addEventListener("click", runCleanup);
  document.getElementById("lib-blacklist-add-btn").addEventListener("click", addBlacklist);
  document.getElementById("lib-seed-purge").addEventListener("click", purgePending);

  document.getElementById("artist-modal-close").innerHTML = iconClose();
  document.getElementById("artist-modal-close").addEventListener("click", closeArtistModal);
  document.querySelector("#artist-modal .modal-scrim").addEventListener("click", closeArtistModal);
  // Like buttons in the modal header are re-rendered on every open — delegate.
  document.getElementById("artist-modal-head").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-like]");
    if (btn) toggleArtistLike(btn);
  });

  selectLibMode("artists");
  loadArtists();
  loadTracks();
  /* artists:changed is handled in-place by syncHeartButtons (shared liked set
   * in components.js) — reloading the Hub here wipes scroll position. */
  return () => {};
}
