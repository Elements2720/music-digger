/* STATS tab: Library Overview, Analytics, Artists Explorer, Blacklist Manager, and Hardware. */

import { api } from "../api.js";
import { emit, on } from "../state.js";
import { el, renderKv, trackRow } from "../ui.js";
import { fmtMemory, fmtNumber } from "../format.js";

let mounted = false;
let artistPage = 1;
const ARTIST_PAGE_SIZE = 15;
let artistsSearchTimer = null;
let blacklistSearchTimer = null;
let openFetchModalFn = null;

function $(id) {
  return document.getElementById(id);
}

function card(value, label, extra = "") {
  const displayVal = typeof value === "number" ? fmtNumber(value) : String(value);
  return el("div", { class: "stat-card" }, [
    el("div", { class: "stat-value", text: displayVal }),
    el("div", { class: "stat-label", text: label }),
    extra ? el("div", { class: "stat-extra dim", text: extra }) : null,
  ]);
}

async function loadAnalytics() {
  const cardsTarget = $("stats-cards");
  const chartGenres = $("chart-genres");
  const chartBpm = $("chart-bpm");
  const chartKeys = $("chart-keys");

  try {
    const [statsData, analytics] = await Promise.all([
      api.stats(),
      api.catalogAnalytics(),
    ]);

    const embeddedPct = analytics.total_tracks
      ? Math.round((analytics.total_embedded / analytics.total_tracks) * 100)
      : 0;

    cardsTarget.replaceChildren(
      card(analytics.total_tracks, "Total Tracks"),
      card(analytics.total_embedded, "Embedded", `${embeddedPct}% ready`),
      card(analytics.total_artists, "Total Artists"),
      card(analytics.total_local, "Local Files"),
      card(analytics.total_itunes, "iTunes Tracks"),
      card(statsData.sets.total, "DJ Sets Analyzed"),
      card(statsData.seeds.total, "Seed Artists", `${statsData.seeds.pending} pending`)
    );

    // 1. Genres chart
    if (!analytics.genres || analytics.genres.length === 0) {
      chartGenres.replaceChildren(el("div", { class: "empty", text: "No genre data yet." }));
    } else {
      const maxGenre = Math.max(...analytics.genres.map((g) => g.track_count), 1);
      chartGenres.replaceChildren(
        ...analytics.genres.slice(0, 8).map((g) => {
          const pct = Math.round((g.track_count / maxGenre) * 100);
          return el("div", { class: "chart-bar-row" }, [
            el("div", { class: "chart-bar-label", text: g.genre }),
            el("div", { class: "chart-bar-track" }, [
              el("div", { class: "chart-bar-fill", style: `width: ${pct}%` }),
            ]),
            el("div", { class: "chart-bar-val mono", text: fmtNumber(g.track_count) }),
          ]);
        })
      );
    }

    // 2. BPM Distribution chart
    if (!analytics.bpm_buckets || analytics.bpm_buckets.length === 0) {
      chartBpm.replaceChildren(el("div", { class: "empty", text: "No BPM data yet." }));
    } else {
      const maxBpm = Math.max(...analytics.bpm_buckets.map((b) => b.track_count), 1);
      chartBpm.replaceChildren(
        ...analytics.bpm_buckets.map((b) => {
          const pct = Math.round((b.track_count / maxBpm) * 100);
          return el("div", { class: "chart-bar-row" }, [
            el("div", { class: "chart-bar-label", text: b.label }),
            el("div", { class: "chart-bar-track" }, [
              el("div", { class: "chart-bar-fill bpm-fill", style: `width: ${pct}%` }),
            ]),
            el("div", { class: "chart-bar-val mono", text: fmtNumber(b.track_count) }),
          ]);
        })
      );
    }

    // 3. Top Camelot Keys
    if (!analytics.top_keys || analytics.top_keys.length === 0) {
      chartKeys.replaceChildren(el("div", { class: "empty", text: "No harmonic keys yet." }));
    } else {
      chartKeys.replaceChildren(
        ...analytics.top_keys.slice(0, 16).map((k) =>
          el("span", { class: "chip key-pill" }, [
            el("strong", { text: k.camelot_key }),
            el("span", { class: "dim", text: ` (${fmtNumber(k.track_count)})` }),
          ])
        )
      );
    }
  } catch (error) {
    cardsTarget.replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

async function loadArtists(page = 1) {
  artistPage = Math.max(1, page);
  const tbody = $("artists-tbody");
  tbody.replaceChildren(el("tr", {}, [el("td", { colspan: 6, class: "empty", text: "Loading artists…" })]));

  const q = $("artists-search").value.trim();
  const source = $("artists-source-filter").value;
  const sort = $("artists-sort").value;
  const offset = (artistPage - 1) * ARTIST_PAGE_SIZE;

  try {
    const data = await api.artistsSummary({
      q: q || undefined,
      source: source || undefined,
      sort,
      limit: ARTIST_PAGE_SIZE,
      offset,
    });

    const total = data.total;
    const artists = data.artists;

    const totalPages = Math.max(1, Math.ceil(total / ARTIST_PAGE_SIZE));
    $("artists-page-info").textContent = `Page ${artistPage} of ${totalPages} (${total} artists)`;
    $("artists-prev").disabled = artistPage <= 1;
    $("artists-next").disabled = artistPage >= totalPages;

    if (artists.length === 0) {
      tbody.replaceChildren(
        el("tr", {}, [el("td", { colspan: 6, class: "empty", text: "No matching artists found." })])
      );
      return;
    }

    tbody.replaceChildren(
      ...artists.map((artist) => {
        const fetchBtn = el("button", {
          class: "btn tiny primary",
          type: "button",
          text: "FETCH",
        });
        fetchBtn.addEventListener("click", () => {
          if (openFetchModalFn) openFetchModalFn(artist.artist);
        });

        const tracksBtn = el("button", {
          class: "btn tiny ghost",
          type: "button",
          text: "TRACKS",
        });
        tracksBtn.addEventListener("click", () => openArtistDrawer(artist.artist));

        const delBtn = el("button", {
          class: "btn tiny danger",
          type: "button",
          text: "DELETE",
        });
        delBtn.addEventListener("click", async () => {
          const confirmed = window.confirm(
            `Delete artist "${artist.artist}" and all ${artist.track_count} tracks from catalog?`
          );
          if (!confirmed) return;
          const alsoBlacklist = window.confirm(
            `Also BLACKLIST "${artist.artist}" to prevent re-crawling in the future?`
          );
          delBtn.disabled = true;
          try {
            await api.deleteArtist(artist.artist, alsoBlacklist);
            emit("toast", `Deleted artist "${artist.artist}"${alsoBlacklist ? " (blacklisted)" : ""}`);
            await Promise.all([loadAnalytics(), loadArtists(artistPage)]);
          } catch (err) {
            emit("toast", err.message);
            delBtn.disabled = false;
          }
        });

        const rawGenres = artist.genres || [];
        const genreChips = rawGenres.slice(0, 3).map((g) =>
          el("span", { class: "chip genre-chip", text: g })
        );
        if (rawGenres.length > 3) {
          genreChips.push(
            el("span", { class: "chip more-chip", text: `+${rawGenres.length - 3}` })
          );
        }

        const sourcesList = (artist.sources || []).map((s) =>
          el("span", { class: `chip ${s === "local" ? "local" : "source"}`, text: s.toUpperCase() })
        );

        const embPct = artist.track_count
          ? Math.round((artist.embedded_count / artist.track_count) * 100)
          : 0;

        return el("tr", {}, [
          el("td", { class: "artist-name-cell" }, [
            el("strong", { text: artist.artist }),
          ]),
          el("td", { class: "mono", text: fmtNumber(artist.track_count) }),
          el("td", { class: "mono" }, [
            el("span", { text: `${fmtNumber(artist.embedded_count)} ` }),
            el("span", { class: "dim", text: `(${embPct}%)` }),
          ]),
          el("td", {}, [el("div", { class: "cell-badges" }, genreChips)]),
          el("td", {}, [el("div", { class: "cell-badges" }, sourcesList)]),
          el("td", {}, [el("div", { class: "cell-actions" }, [fetchBtn, tracksBtn, delBtn])]),
        ]);
      })
    );
  } catch (error) {
    tbody.replaceChildren(el("tr", {}, [el("td", { colspan: 6, class: "empty", text: error.message })]));
  }
}

async function openArtistDrawer(artistName) {
  const drawer = $("artist-tracks-drawer");
  const list = $("drawer-tracks-list");
  $("drawer-artist-name").textContent = artistName;
  drawer.classList.remove("hidden");
  list.replaceChildren(el("div", { class: "empty", text: "Loading tracks…" }));

  try {
    const data = await api.artistTracks(artistName, { limit: 200 });
    const tracks = data.tracks || [];
    if (tracks.length === 0) {
      list.replaceChildren(el("div", { class: "empty", text: "No tracks found for this artist." }));
      return;
    }
    list.replaceChildren(
      ...tracks.map((t, idx) => trackRow(t, { rank: idx + 1 }))
    );
  } catch (error) {
    list.replaceChildren(el("div", { class: "empty", text: error.message }));
  }
}

function closeArtistDrawer() {
  const drawer = $("artist-tracks-drawer");
  drawer.classList.add("hidden");
  $("drawer-tracks-list").replaceChildren();
}

async function loadBlacklist() {
  const tbody = $("blacklist-tbody");
  tbody.replaceChildren(el("tr", {}, [el("td", { colspan: 5, class: "empty", text: "Loading blacklist…" })]));

  const kind = $("blacklist-kind-filter").value || undefined;
  const q = $("blacklist-search").value.trim() || undefined;

  try {
    const data = await api.blacklist({ kind, q, limit: 100 });
    const entries = data.entries || [];
    if (entries.length === 0) {
      tbody.replaceChildren(
        el("tr", {}, [el("td", { colspan: 5, class: "empty", text: "No blacklisted items." })])
      );
      return;
    }

    tbody.replaceChildren(
      ...entries.map((entry) => {
        const unblockBtn = el("button", {
          class: "btn tiny ghost",
          type: "button",
          text: "UNBLOCK",
        });
        unblockBtn.addEventListener("click", async () => {
          if (!window.confirm(`Unblock "${entry.display_name}"?`)) return;
          unblockBtn.disabled = true;
          try {
            await api.removeBlacklist(entry.id);
            emit("toast", `Unblocked "${entry.display_name}"`);
            loadBlacklist();
          } catch (err) {
            emit("toast", err.message);
            unblockBtn.disabled = false;
          }
        });

        return el("tr", {}, [
          el("td", {}, [
            el("span", {
              class: `chip ${entry.kind === "artist" ? "key" : "local"}`,
              text: entry.kind.toUpperCase(),
            }),
          ]),
          el("td", { class: "artist-name-cell" }, [
            el("strong", { text: entry.display_name }),
          ]),
          el("td", { class: "mono dim", text: entry.normalized_key }),
          el("td", { text: entry.reason || "—" }),
          el("td", { class: "actions-cell" }, [unblockBtn]),
        ]);
      })
    );
  } catch (error) {
    tbody.replaceChildren(el("tr", {}, [el("td", { colspan: 5, class: "empty", text: error.message })]));
  }
}

async function promptAddBlacklist() {
  const kind = window.prompt("Block artist or track? (type 'artist' or 'track')", "artist");
  if (!kind || !["artist", "track"].includes(kind.trim().toLowerCase())) return;

  const cleanKind = kind.trim().toLowerCase();
  const name = window.prompt(cleanKind === "artist" ? "Artist name to block:" : "Artist name of the track:");
  if (!name || !name.trim()) return;

  let trackTitle = null;
  if (cleanKind === "track") {
    trackTitle = window.prompt("Track title to block:");
    if (!trackTitle || !trackTitle.trim()) return;
  }

  const reason = window.prompt("Reason (optional):", "User blocked");

  try {
    await api.addBlacklist({
      kind: cleanKind,
      name: name.trim(),
      track_title: trackTitle ? trackTitle.trim() : null,
      reason: reason ? reason.trim() : null,
    });
    emit("toast", `Blacklisted ${cleanKind} "${name}"`);
    loadBlacklist();
  } catch (err) {
    emit("toast", err.message);
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
    await loadAnalytics();
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
    loadAnalytics();
    loadArtists(artistPage);
    loadBlacklist();
    loadHardware();
  });
  $("reset-embeddings").addEventListener("click", resetEmbeddings);

  // Artists explorer listeners
  $("artists-search").addEventListener("input", () => {
    clearTimeout(artistsSearchTimer);
    artistsSearchTimer = setTimeout(() => loadArtists(1), 300);
  });
  $("artists-source-filter").addEventListener("change", () => loadArtists(1));
  $("artists-sort").addEventListener("change", () => loadArtists(1));
  $("artists-prev").addEventListener("click", () => loadArtists(artistPage - 1));
  $("artists-next").addEventListener("click", () => loadArtists(artistPage + 1));
  $("drawer-close").addEventListener("click", closeArtistDrawer);

  // Blacklist manager listeners
  $("blacklist-kind-filter").addEventListener("change", () => loadBlacklist());
  $("blacklist-search").addEventListener("input", () => {
    clearTimeout(blacklistSearchTimer);
    blacklistSearchTimer = setTimeout(() => loadBlacklist(), 300);
  });
  $("blacklist-add-btn").addEventListener("click", promptAddBlacklist);

  // Fetch artist modal wiring
  const fetchModal = $("modal-fetch-artist");
  const fetchInput = $("fetch-artist-input");
  const fetchCount = $("fetch-artist-count");
  const fetchPresets = $("fetch-artist-presets");
  const fetchAutoIndex = $("fetch-artist-auto-index");
  const fetchDiscover = $("fetch-artist-discover");
  const fetchForm = $("form-fetch-artist");

  function openFetchArtistModal(artistName = "") {
    if (!fetchModal) return;
    fetchInput.value = artistName;
    fetchCount.value = "50";
    if (fetchAutoIndex) fetchAutoIndex.checked = true;
    if (fetchDiscover) fetchDiscover.checked = false;
    if (fetchPresets) {
      for (const btn of fetchPresets.querySelectorAll(".preset-btn")) {
        btn.classList.toggle("active", btn.dataset.count === "50");
      }
    }
    fetchModal.classList.remove("hidden");
    if (artistName) {
      fetchCount.focus();
    } else {
      fetchInput.focus();
    }
  }

  function closeFetchArtistModal() {
    if (!fetchModal) return;
    fetchModal.classList.add("hidden");
  }

  openFetchModalFn = openFetchArtistModal;

  $("artists-fetch-btn")?.addEventListener("click", () => openFetchArtistModal(""));
  $("modal-fetch-artist-close")?.addEventListener("click", closeFetchArtistModal);
  $("modal-fetch-artist-cancel")?.addEventListener("click", closeFetchArtistModal);

  fetchModal?.addEventListener("click", (e) => {
    if (e.target === fetchModal) closeFetchArtistModal();
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && fetchModal && !fetchModal.classList.contains("hidden")) {
      closeFetchArtistModal();
    }
  });

  fetchPresets?.addEventListener("click", (e) => {
    const btn = e.target.closest(".preset-btn");
    if (!btn) return;
    const count = btn.dataset.count;
    fetchCount.value = count;
    for (const b of fetchPresets.querySelectorAll(".preset-btn")) {
      b.classList.toggle("active", b === btn);
    }
  });

  fetchCount?.addEventListener("input", () => {
    const val = fetchCount.value;
    if (fetchPresets) {
      for (const b of fetchPresets.querySelectorAll(".preset-btn")) {
        b.classList.toggle("active", b.dataset.count === val);
      }
    }
  });

  fetchForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const artist = fetchInput.value.trim();
    if (!artist) return;
    const count = parseInt(fetchCount.value, 10) || 50;
    const autoIndex = fetchAutoIndex ? fetchAutoIndex.checked : true;
    const discoverRelated = fetchDiscover ? fetchDiscover.checked : false;

    closeFetchArtistModal();
    try {
      await api.startJob("fetch-artist", {
        artist,
        tracks_per_artist: count,
        auto_index: autoIndex,
        discover_related: discoverRelated,
        related_limit: 10,
      });
      emit("toast", `Started fetch for "${artist}"`);
      emit("tab:show", "run");
    } catch (err) {
      emit("toast", err.message);
    }
  });

  // Refresh upon track deletion
  on("track:deleted", () => {
    loadAnalytics();
    loadArtists(artistPage);
  });

  loadAnalytics();
  loadArtists(1);
  loadBlacklist();
  loadHardware();
}

export { loadAnalytics, loadArtists, loadBlacklist, loadHardware };
