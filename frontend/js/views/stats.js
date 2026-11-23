/* STATS tab: Library Overview, Analytics, Artists Explorer, Blacklist Manager, and Hardware. */

import { api } from "../api.js";
import { emit, on } from "../state.js";
import { camelotBadge, el, renderKv, trackRow } from "../ui.js";
import { fmtMemory, fmtNumber } from "../format.js";

let mounted = false;
let artistPage = 1;
const ARTIST_PAGE_SIZE = 15;
let seedsPage = 1;
const SEEDS_PAGE_SIZE = 20;
let artistsSearchTimer = null;
let seedsSearchTimer = null;
let blacklistSearchTimer = null;
let similarSearchTimer = null;
let openFetchModalFn = null;
let artistsLikedOnlyActive = false;
let likedArtistsSet = new Set();
let cachedAnalytics = null;
const selectedArtists = new Set();
let currentPageArtists = [];
let cleanupPreviewTimer = null;
let currentCleanupPreview = null;

async function refreshLikedArtists() {
  try {
    const res = await api.likedArtists();
    const list = res?.liked_artists ?? (Array.isArray(res) ? res : []);
    likedArtistsSet = new Set(
      list.map((a) => (a.artist_name || a.artist || "").toLowerCase())
    );
  } catch {
    // ignore
  }
}

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
    cachedAnalytics = analytics;

    const embeddedPct = analytics.total_tracks
      ? Math.round((analytics.total_embedded / analytics.total_tracks) * 100)
      : 0;

    const cards = [
      card(analytics.total_tracks, "Total Tracks"),
      card(analytics.total_embedded, "Embedded", `${embeddedPct}% ready`),
      card(analytics.total_artists, "Total Artists"),
      card(analytics.total_local, "Local Files"),
      card(analytics.total_itunes, "iTunes Tracks"),
      card(statsData.sets.total, "DJ Sets Analyzed"),
      card(statsData.seeds.total, "Seed Artists", `${statsData.seeds.pending} pending`),
    ];
    if (analytics.local_taste_count > 0) {
      cards.push(
        card(analytics.local_taste_count, "Taste Profile", "local tracks active")
      );
    }
    cardsTarget.replaceChildren(...cards);

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
          camelotBadge(
            k.camelot_key,
            "key-pill",
            el("span", { class: "dim", text: ` (${fmtNumber(k.track_count)})` })
          )
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
  tbody.replaceChildren(el("tr", {}, [el("td", { colspan: 9, class: "empty", text: "Loading artists…" })]));

  const q = $("artists-search").value.trim();
  const source = $("artists-source-filter").value;
  const genre = $("artists-genre-filter") ? $("artists-genre-filter").value : "";
  const minYearVal = $("artists-min-year") ? $("artists-min-year").value.trim() : "";
  const minYear = minYearVal ? Number(minYearVal) : undefined;
  const sort = $("artists-sort").value;
  const tasteMode = $("artists-taste-mode-select") ? $("artists-taste-mode-select").value : "both";
  const likedOnly = artistsLikedOnlyActive;
  const offset = (artistPage - 1) * ARTIST_PAGE_SIZE;

  try {
    const data = await api.artistsSummary({
      q: q || undefined,
      source: source || undefined,
      genre: genre || undefined,
      min_year: minYear,
      sort,
      limit: ARTIST_PAGE_SIZE,
      offset,
      taste_mode: tasteMode,
      liked_only: likedOnly,
    });

    const total = data.total;
    const artists = data.artists;
    currentPageArtists = artists || [];

    const totalPages = Math.max(1, Math.ceil(total / ARTIST_PAGE_SIZE));
    $("artists-page-info").textContent = `Page ${artistPage} of ${totalPages} (${total} artists)`;
    $("artists-prev").disabled = artistPage <= 1;
    $("artists-next").disabled = artistPage >= totalPages;

    if (artists.length === 0) {
      tbody.replaceChildren(
        el("tr", {}, [el("td", { colspan: 9, class: "empty", text: "No matching artists found." })])
      );
      updateMasterCheckbox();
      updateArtistsBulkBar();
      return;
    }

    tbody.replaceChildren(
      ...artists.map((artist) => {
        const isLiked = artist.is_liked || likedArtistsSet.has(artist.artist.toLowerCase());
        if (artist.is_liked) likedArtistsSet.add(artist.artist.toLowerCase());

        const selectCheckbox = el("input", {
          class: "artist-select-checkbox",
          type: "checkbox",
          checked: selectedArtists.has(artist.artist),
          title: `Select ${artist.artist}`,
        });
        selectCheckbox.addEventListener("change", () => {
          if (selectCheckbox.checked) {
            selectedArtists.add(artist.artist);
          } else {
            selectedArtists.delete(artist.artist);
          }
          updateArtistsBulkBar();
          updateMasterCheckbox();
        });
        const selectTd = el("td", { class: "select-col" }, [selectCheckbox]);

        const heartBtn = el("button", {
          class: `heart-btn${isLiked ? " liked" : ""}`,
          type: "button",
          title: isLiked ? "Unlike artist" : "Like artist",
          text: isLiked ? "♥" : "♡",
        });
        heartBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const wasLiked = heartBtn.classList.contains("liked");
          heartBtn.disabled = true;
          try {
            if (wasLiked) {
              await api.unlikeArtist(artist.artist);
              likedArtistsSet.delete(artist.artist.toLowerCase());
              heartBtn.classList.remove("liked");
              heartBtn.textContent = "♡";
              heartBtn.title = "Like artist";
              emit("toast", `Unliked "${artist.artist}"`);
              emit("artist:liked", { artist: artist.artist, liked: false });
              if (artistsLikedOnlyActive) {
                await loadArtists(artistPage);
              }
            } else {
              await api.likeArtist(artist.artist);
              likedArtistsSet.add(artist.artist.toLowerCase());
              heartBtn.classList.add("liked");
              heartBtn.textContent = "♥";
              heartBtn.title = "Unlike artist";
              emit("toast", `Liked "${artist.artist}"`);
              emit("artist:liked", { artist: artist.artist, liked: true });
            }
          } catch (err) {
            emit("toast", err.message);
          } finally {
            heartBtn.disabled = false;
          }
        });

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
        tracksBtn.addEventListener("click", () => openArtistTracksModal(artist.artist));

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
            selectedArtists.delete(artist.artist);
            updateArtistsBulkBar();
            emit("toast", `Deleted artist "${artist.artist}"${alsoBlacklist ? " (blacklisted)" : ""}`);
            await Promise.all([loadAnalytics(), loadArtists(artistPage)]);
          } catch (err) {
            emit("toast", err.message);
            delBtn.disabled = false;
          }
        });

        let yearsText = "—";
        if (artist.year_min && artist.year_max) {
          yearsText =
            artist.year_min === artist.year_max
              ? String(artist.year_min)
              : `${artist.year_min}–${artist.year_max}`;
        } else if (artist.year_min || artist.year_max) {
          yearsText = String(artist.year_min || artist.year_max);
        }

        let tasteEl;
        if (
          artist.taste_match_percent !== null &&
          artist.taste_match_percent !== undefined
        ) {
          const score = Math.round(artist.taste_match_percent);
          const tier =
            score >= 80 ? "taste-high" : score >= 65 ? "taste-mid" : "taste-low";
          tasteEl = el("span", { class: `chip ${tier}`, text: `${score}%` });
        } else {
          tasteEl = el("span", { class: "dim", text: "—" });
        }

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
          selectTd,
          el("td", { class: "artist-name-cell" }, [
            el("div", { class: "artist-name-group" }, [
              heartBtn,
              el("strong", { text: artist.artist }),
            ]),
          ]),
          el("td", { class: "mono", text: fmtNumber(artist.track_count) }),
          el("td", { class: "mono" }, [
            el("span", { text: `${fmtNumber(artist.embedded_count)} ` }),
            el("span", { class: "dim", text: `(${embPct}%)` }),
          ]),
          el("td", { class: "mono dim", text: yearsText }),
          el("td", {}, [el("div", { class: "cell-badges" }, genreChips)]),
          el("td", {}, [tasteEl]),
          el("td", {}, [el("div", { class: "cell-badges" }, sourcesList)]),
          el("td", {}, [el("div", { class: "cell-actions" }, [fetchBtn, tracksBtn, delBtn])]),
        ]);
      })
    );
    updateMasterCheckbox();
    updateArtistsBulkBar();
  } catch (error) {
    tbody.replaceChildren(el("tr", {}, [el("td", { colspan: 9, class: "empty", text: error.message })]));
    updateMasterCheckbox();
    updateArtistsBulkBar();
  }
}

function updateArtistsBulkBar() {
  const bar = $("artists-bulk-bar");
  const countBadge = $("artists-selected-count");
  const delBtn = $("artists-bulk-delete-btn");
  const alsoBlacklist = $("bulk-select-blacklist")?.checked;
  if (!bar) return;

  if (selectedArtists.size === 0) {
    bar.classList.add("hidden");
    return;
  }

  bar.classList.remove("hidden");
  if (countBadge) {
    countBadge.textContent = `${selectedArtists.size} artist${selectedArtists.size === 1 ? "" : "s"} selected`;
  }
  if (delBtn) {
    delBtn.textContent = alsoBlacklist
      ? `DELETE & BLOCK SELECTED (${selectedArtists.size})`
      : `DELETE SELECTED (${selectedArtists.size})`;
  }
}

function updateMasterCheckbox() {
  const master = $("artists-select-all");
  if (!master) return;
  if (!currentPageArtists || currentPageArtists.length === 0) {
    master.checked = false;
    master.indeterminate = false;
    return;
  }
  const selectedOnPage = currentPageArtists.filter((a) => selectedArtists.has(a.artist)).length;
  if (selectedOnPage === currentPageArtists.length) {
    master.checked = true;
    master.indeterminate = false;
  } else if (selectedOnPage > 0) {
    master.checked = false;
    master.indeterminate = true;
  } else {
    master.checked = false;
    master.indeterminate = false;
  }
}

function openBulkDeleteConfirmModal() {
  if (selectedArtists.size === 0) return;
  const modal = $("modal-bulk-delete-confirm");
  const countSpan = $("bulk-delete-confirm-count");
  const notice = $("bulk-delete-blacklist-notice");
  const confirmBtn = $("modal-bulk-delete-confirm-btn");
  const alsoBlacklist = $("bulk-select-blacklist")?.checked;

  if (countSpan) countSpan.textContent = String(selectedArtists.size);
  if (notice) notice.classList.toggle("hidden", !alsoBlacklist);
  if (confirmBtn) {
    confirmBtn.textContent = alsoBlacklist
      ? `DELETE & BLOCK ${selectedArtists.size} ARTISTS`
      : `DELETE ${selectedArtists.size} ARTISTS`;
  }
  if (modal) modal.classList.remove("hidden");
}

function closeBulkDeleteConfirmModal() {
  const modal = $("modal-bulk-delete-confirm");
  if (modal) modal.classList.add("hidden");
}

function openBulkCleanupModal() {
  const modal = $("modal-bulk-cleanup");
  if (!modal) return;

  // Populate genres dropdown from current analytics
  const genreSelect = $("bulk-cleanup-genre");
  if (genreSelect && cachedAnalytics?.genres) {
    const curVal = genreSelect.value;
    genreSelect.replaceChildren(
      el("option", { value: "", text: "Any Genre" }),
      ...cachedAnalytics.genres.map((g) =>
        el("option", { value: g.genre, text: `${g.genre} (${g.track_count} tracks)` })
      )
    );
    if (curVal) genreSelect.value = curVal;
  }

  // Pre-sync with current explorer genre if filtered
  const explorerGenre = $("artists-genre-filter")?.value;
  if (explorerGenre && genreSelect && !genreSelect.value) {
    genreSelect.value = explorerGenre;
  }

  modal.classList.remove("hidden");
  scheduleCleanupPreview(0);
}

function closeBulkCleanupModal() {
  const modal = $("modal-bulk-cleanup");
  if (modal) modal.classList.add("hidden");
}

function scheduleCleanupPreview(delay = 250) {
  clearTimeout(cleanupPreviewTimer);
  cleanupPreviewTimer = setTimeout(runCleanupPreview, delay);
}

async function runCleanupPreview() {
  const tasteInput = $("bulk-cleanup-taste");
  const genreSelect = $("bulk-cleanup-genre");
  const protectLiked = $("bulk-cleanup-protect-liked")?.checked ?? true;
  const protectLocal = $("bulk-cleanup-protect-local")?.checked ?? true;
  const alsoBlacklist = $("bulk-cleanup-blacklist")?.checked ?? true;
  const banner = $("bulk-cleanup-banner");
  const list = $("bulk-cleanup-preview-list");
  const submitBtn = $("modal-bulk-cleanup-submit");
  const tasteMode = $("artists-taste-mode-select")?.value || "both";

  const tasteVal = tasteInput?.value?.trim();
  const genreVal = genreSelect?.value?.trim();

  if (!tasteVal && !genreVal) {
    currentCleanupPreview = null;
    if (banner) {
      banner.textContent = "Set a Taste % threshold or pick a Genre to preview";
      banner.classList.remove("active");
    }
    if (list) {
      list.replaceChildren(el("div", { class: "empty", text: "No criteria specified yet." }));
    }
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = alsoBlacklist ? "DELETE & BLOCK 0 ARTISTS" : "DELETE 0 ARTISTS";
    }
    return;
  }

  if (banner) {
    banner.textContent = "Loading preview…";
    banner.classList.remove("active");
  }

  try {
    const criteria = {
      max_taste_percent: tasteVal ? Number(tasteVal) : null,
      taste_mode: tasteMode,
      genre: genreVal || null,
      protect_liked: protectLiked,
      protect_local: protectLocal,
    };
    const data = await api.previewBulkCleanup(criteria);
    currentCleanupPreview = data;

    if (banner) {
      banner.textContent = `Will remove ${data.artist_count} artists (${data.track_count} tracks)`;
      banner.classList.toggle("active", data.artist_count > 0);
    }

    if (submitBtn) {
      submitBtn.disabled = data.artist_count === 0;
      submitBtn.textContent = data.artist_count === 0
        ? "NO MATCHING ARTISTS"
        : `${alsoBlacklist ? "DELETE & BLOCK" : "DELETE"} ${data.artist_count} ARTISTS`;
    }

    if (list) {
      if (!data.sample_artists || data.sample_artists.length === 0) {
        list.replaceChildren(el("div", { class: "empty", text: "No artists match the specified criteria." }));
      } else {
        list.replaceChildren(
          ...data.sample_artists.map((a) => {
            const leftEl = el("div", { class: "cleanup-preview-row-left" }, [
              el("strong", { text: a.artist }),
              el("span", { class: "dim mono", text: `${a.track_count} trk${a.track_count === 1 ? "" : "s"}` }),
            ]);

            const rightChips = [];
            if (a.genres && a.genres.length > 0) {
              rightChips.push(el("span", { class: "chip genre-chip", text: a.genres[0] }));
            }
            if (a.taste_match_percent !== null && a.taste_match_percent !== undefined) {
              const score = Math.round(a.taste_match_percent);
              const tier = score >= 80 ? "taste-high" : score >= 65 ? "taste-mid" : "taste-low";
              rightChips.push(el("span", { class: `chip ${tier}`, text: `${score}%` }));
            }
            const rightEl = el("div", { class: "cleanup-preview-row-right" }, rightChips);

            return el("div", { class: "cleanup-preview-row" }, [leftEl, rightEl]);
          })
        );
      }
    }
  } catch (err) {
    if (banner) {
      banner.textContent = `Preview error: ${err.message}`;
      banner.classList.remove("active");
    }
  }
}

async function executeBulkCleanup() {
  const tasteInput = $("bulk-cleanup-taste");
  const genreSelect = $("bulk-cleanup-genre");
  const protectLiked = $("bulk-cleanup-protect-liked")?.checked ?? true;
  const protectLocal = $("bulk-cleanup-protect-local")?.checked ?? true;
  const alsoBlacklist = $("bulk-cleanup-blacklist")?.checked ?? true;
  const reasonInput = $("bulk-cleanup-reason");
  const submitBtn = $("modal-bulk-cleanup-submit");
  const tasteMode = $("artists-taste-mode-select")?.value || "both";

  const tasteVal = tasteInput?.value?.trim();
  const genreVal = genreSelect?.value?.trim();
  const reasonVal = reasonInput?.value?.trim();

  if (!tasteVal && !genreVal) return;
  if (!currentCleanupPreview || currentCleanupPreview.artist_count === 0) return;

  submitBtn.disabled = true;
  try {
    const payload = {
      max_taste_percent: tasteVal ? Number(tasteVal) : null,
      taste_mode: tasteMode,
      genre: genreVal || null,
      protect_liked: protectLiked,
      protect_local: protectLocal,
      blacklist: alsoBlacklist,
      reason: reasonVal || null,
    };
    const res = await api.executeBulkCleanup(payload);
    closeBulkCleanupModal();
    emit("toast", `Bulk cleanup: deleted ${res.artists_deleted} artists (${res.tracks_deleted} tracks)${res.blacklisted_count ? ` [${res.blacklisted_count} blacklisted]` : ""}${res.skipped_protected ? ` [${res.skipped_protected} protected]` : ""}`);
    selectedArtists.clear();
    updateArtistsBulkBar();
    updateMasterCheckbox();
    await Promise.all([loadAnalytics(), loadArtists(1), loadSeeds(1), loadBlacklist()]);
  } catch (err) {
    emit("toast", err.message);
  } finally {
    submitBtn.disabled = false;
  }
}

let currentArtistTracks = [];
let currentArtistName = "";

function renderArtistTracksModalList() {
  const list = $("modal-artist-tracks-list");
  const filterInput = $("modal-artist-tracks-filter");
  const countLabel = $("modal-artist-tracks-count");
  if (!list) return;

  const q = (filterInput?.value || "").trim().toLowerCase();
  const filtered = q
    ? currentArtistTracks.filter((t) => {
        const title = (t.title || "").toLowerCase();
        const genre = (t.genre || "").toLowerCase();
        const key = (t.key || "").toLowerCase();
        const year = String(t.release_year || "");
        return (
          title.includes(q) ||
          genre.includes(q) ||
          key.includes(q) ||
          year.includes(q)
        );
      })
    : currentArtistTracks;

  if (countLabel) {
    countLabel.textContent = q
      ? `${filtered.length} of ${currentArtistTracks.length} tracks`
      : `${currentArtistTracks.length} track${currentArtistTracks.length === 1 ? "" : "s"}`;
  }

  if (filtered.length === 0) {
    list.replaceChildren(
      el("div", {
        class: "empty",
        text: q ? "No matching tracks found." : "No tracks found for this artist.",
      })
    );
    return;
  }

  list.replaceChildren(
    ...filtered.map((t, idx) => trackRow(t, { rank: idx + 1 }))
  );
}

async function openArtistTracksModal(artistName) {
  currentArtistName = artistName;
  currentArtistTracks = [];

  const modal = $("modal-artist-tracks");
  const title = $("modal-artist-tracks-title");
  const countLabel = $("modal-artist-tracks-count");
  const filterInput = $("modal-artist-tracks-filter");
  const list = $("modal-artist-tracks-list");

  if (title) title.textContent = artistName;
  if (countLabel) countLabel.textContent = "Loading…";
  if (filterInput) filterInput.value = "";
  if (list) list.replaceChildren(el("div", { class: "empty", text: "Loading tracks…" }));

  const isLiked = likedArtistsSet.has(artistName.toLowerCase());
  const likeBtn = $("modal-artist-tracks-like");
  if (likeBtn) {
    likeBtn.classList.toggle("liked", isLiked);
    likeBtn.textContent = isLiked ? "♥" : "♡";
    likeBtn.title = isLiked ? "Unlike artist" : "Like artist";
  }

  modal?.classList.remove("hidden");
  document.body.style.overflow = "hidden";

  try {
    const data = await api.artistTracks(artistName, { limit: 200 });
    currentArtistTracks = data.tracks || [];
    renderArtistTracksModalList();
  } catch (error) {
    if (list) list.replaceChildren(el("div", { class: "empty", text: error.message }));
    if (countLabel) countLabel.textContent = "0 tracks";
  }
}

function closeArtistTracksModal() {
  const modal = $("modal-artist-tracks");
  if (!modal || modal.classList.contains("hidden")) return;
  modal.classList.add("hidden");
  document.body.style.overflow = "";
  currentArtistTracks = [];
  currentArtistName = "";
  $("modal-artist-tracks-list")?.replaceChildren();
}

async function openSimilarArtistsModal() {
  const modal = $("modal-similar-artists");
  if (!modal) return;
  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  await loadSimilarArtists();
}

function closeSimilarArtistsModal() {
  const modal = $("modal-similar-artists");
  if (!modal || modal.classList.contains("hidden")) return;
  modal.classList.add("hidden");
  document.body.style.overflow = "";
}

async function loadSimilarArtists() {
  const tbody = $("similar-artists-tbody");
  if (!tbody) return;
  tbody.replaceChildren(
    el("tr", {}, [
      el("td", {
        colspan: 7,
        class: "empty",
        text: "Computing similarity to liked artists…",
      }),
    ])
  );
  const minYearVal = $("similar-artists-min-year")
    ? $("similar-artists-min-year").value.trim()
    : "";
  const minYear = minYearVal ? Number(minYearVal) : undefined;

  try {
    const data = await api.similarLikedArtists({ min_year: minYear, limit: 30 });
    const items = data.items || [];
    const seedCount = (data.seed_artists || []).length;
    const countLabel = $("modal-similar-artists-count");
    if (countLabel) {
      countLabel.textContent = `Based on ${seedCount} liked artist${seedCount === 1 ? "" : "s"} (${data.seed_tracks_used || 0} reference tracks)`;
    }

    if (items.length === 0) {
      tbody.replaceChildren(
        el("tr", {}, [
          el("td", {
            colspan: 7,
            class: "empty",
            text:
              seedCount === 0
                ? "No liked artists yet! Click the heart ♥ on your favorite artists in the Artists Explorer to get recommendations."
                : "No similar artists found in catalog.",
          }),
        ])
      );
      return;
    }

    tbody.replaceChildren(
      ...items.map((item) => {
        const isLiked =
          item.is_liked || likedArtistsSet.has(item.artist.toLowerCase());
        if (item.is_liked) likedArtistsSet.add(item.artist.toLowerCase());

        const heartBtn = el("button", {
          class: `heart-btn${isLiked ? " liked" : ""}`,
          type: "button",
          title: isLiked ? "Unlike artist" : "Like artist",
          text: isLiked ? "♥" : "♡",
        });
        heartBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const wasLiked = heartBtn.classList.contains("liked");
          heartBtn.disabled = true;
          try {
            if (wasLiked) {
              await api.unlikeArtist(item.artist);
              likedArtistsSet.delete(item.artist.toLowerCase());
              heartBtn.classList.remove("liked");
              heartBtn.textContent = "♡";
              heartBtn.title = "Like artist";
              emit("toast", `Unliked "${item.artist}"`);
              emit("artist:liked", { artist: item.artist, liked: false });
            } else {
              await api.likeArtist(item.artist);
              likedArtistsSet.add(item.artist.toLowerCase());
              heartBtn.classList.add("liked");
              heartBtn.textContent = "♥";
              heartBtn.title = "Unlike artist";
              emit("toast", `Liked "${item.artist}"`);
              emit("artist:liked", { artist: item.artist, liked: true });
            }
          } catch (err) {
            emit("toast", err.message);
          } finally {
            heartBtn.disabled = false;
          }
        });

        const fetchBtn = el("button", {
          class: "btn tiny primary",
          type: "button",
          text: "FETCH",
        });
        fetchBtn.addEventListener("click", () => {
          closeSimilarArtistsModal();
          if (openFetchModalFn) openFetchModalFn(item.artist);
        });

        const tracksBtn = el("button", {
          class: "btn tiny ghost",
          type: "button",
          text: "TRACKS",
        });
        tracksBtn.addEventListener("click", () => {
          closeSimilarArtistsModal();
          openArtistTracksModal(item.artist);
        });

        const score = Math.round(item.similarity_percent || 0);
        const tier =
          score >= 80 ? "taste-high" : score >= 65 ? "taste-mid" : "taste-low";
        const matchEl = el("span", { class: `chip ${tier}`, text: `${score}%` });

        const bpmText =
          item.bpm_min && item.bpm_max
            ? item.bpm_min === item.bpm_max
              ? `${Math.round(item.bpm_min)}`
              : `${Math.round(item.bpm_min)}–${Math.round(item.bpm_max)}`
            : "—";

        const yearText =
          item.year_min && item.year_max
            ? item.year_min === item.year_max
              ? `${item.year_min}`
              : `${item.year_min}–${item.year_max}`
            : "—";

        const rawGenres = item.genres || [];
        const genreChips = rawGenres
          .slice(0, 3)
          .map((g) => el("span", { class: "chip genre-chip", text: g }));

        return el("tr", {}, [
          el("td", { class: "artist-name-cell" }, [
            el("div", { class: "artist-name-group" }, [
              heartBtn,
              el("strong", { text: item.artist }),
            ]),
          ]),
          el("td", {}, [matchEl]),
          el("td", { class: "mono" }, [
            el("span", { text: `${fmtNumber(item.track_count)} ` }),
            el("span", {
              class: "dim",
              text: `(${fmtNumber(item.embedded_count)} emb)`,
            }),
          ]),
          el("td", { class: "mono dim", text: bpmText }),
          el("td", { class: "mono dim", text: yearText }),
          el("td", {}, [el("div", { class: "cell-badges" }, genreChips)]),
          el("td", {}, [
            el("div", { class: "cell-actions" }, [fetchBtn, tracksBtn]),
          ]),
        ]);
      })
    );
  } catch (error) {
    tbody.replaceChildren(
      el("tr", {}, [
        el("td", { colspan: 7, class: "empty", text: error.message }),
      ])
    );
  }
}

async function loadSeeds(page = 1) {
  seedsPage = Math.max(1, page);
  const tbody = $("seeds-tbody");
  if (!tbody) return;
  tbody.replaceChildren(
    el("tr", {}, [el("td", { colspan: 6, class: "empty", text: "Loading seeds…" })])
  );

  const q = $("seeds-search") ? $("seeds-search").value.trim() : "";
  const status = $("seeds-status-filter") ? $("seeds-status-filter").value : "";
  const source = $("seeds-source-filter") ? $("seeds-source-filter").value : "";
  const category = $("seeds-category-filter") ? $("seeds-category-filter").value : "";
  const offset = (seedsPage - 1) * SEEDS_PAGE_SIZE;

  try {
    const data = await api.seeds({
      q: q || undefined,
      status: status || undefined,
      source: source || undefined,
      category: category || undefined,
      limit: SEEDS_PAGE_SIZE,
      offset,
    });

    const seeds = data.seeds || [];
    const total = data.total || 0;
    const breakdown = data.breakdown;

    // Render source breakdown pills
    const pillsTarget = $("seeds-source-pills");
    if (pillsTarget && breakdown) {
      const pills = [
        el("span", {
          class: "chip key-pill",
          text: `All: ${breakdown.total} (${breakdown.pending} pend)`,
        }),
      ];
      if (breakdown.by_source) {
        for (const s of breakdown.by_source) {
          pills.push(
            el("span", {
              class: "chip key-pill",
              text: `${s.source}: ${s.total} (${s.pending} pend)`,
            })
          );
        }
      }
      pillsTarget.replaceChildren(...pills);

      // Populate source filter dropdown if not populated
      const sourceSelect = $("seeds-source-filter");
      if (sourceSelect && !sourceSelect.dataset.populated && breakdown.by_source) {
        sourceSelect.dataset.populated = "true";
        for (const s of breakdown.by_source) {
          sourceSelect.append(el("option", { value: s.source, text: s.source }));
        }
      }
    }

    const totalPages = Math.max(1, Math.ceil(total / SEEDS_PAGE_SIZE));
    if ($("seeds-page-info")) {
      $("seeds-page-info").textContent = `Page ${seedsPage} of ${totalPages} (${total} seeds)`;
    }
    if ($("seeds-prev")) $("seeds-prev").disabled = seedsPage <= 1;
    if ($("seeds-next")) $("seeds-next").disabled = seedsPage >= totalPages;

    if (seeds.length === 0) {
      tbody.replaceChildren(
        el("tr", {}, [el("td", { colspan: 6, class: "empty", text: "No matching seeds found." })])
      );
      return;
    }

    tbody.replaceChildren(
      ...seeds.map((s) => {
        const fetchBtn = el("button", {
          class: "btn tiny primary",
          type: "button",
          text: "FETCH",
        });
        fetchBtn.addEventListener("click", () => {
          if (openFetchModalFn) openFetchModalFn(s.name);
        });

        const removeBtn = el("button", {
          class: "btn tiny ghost",
          type: "button",
          text: "REMOVE",
        });
        removeBtn.addEventListener("click", async () => {
          if (!window.confirm(`Remove seed "${s.name}" from queue?`)) return;
          removeBtn.disabled = true;
          try {
            await api.deleteSeed(s.name);
            emit("toast", `Removed seed "${s.name}"`);
            await loadSeeds(seedsPage);
          } catch (err) {
            emit("toast", err.message);
            removeBtn.disabled = false;
          }
        });

        const blockBtn = el("button", {
          class: "btn tiny danger",
          type: "button",
          text: "BLOCK",
        });
        blockBtn.addEventListener("click", async () => {
          if (!window.confirm(`Block "${s.name}" and remove from seeds queue?`)) return;
          blockBtn.disabled = true;
          try {
            await api.addBlacklist({
              kind: "artist",
              name: s.name,
              reason: "Blocked from seeds queue",
            });
            await api.deleteSeed(s.name);
            emit("toast", `Blocked "${s.name}" and removed from seeds`);
            await loadSeeds(seedsPage);
          } catch (err) {
            emit("toast", err.message);
            blockBtn.disabled = false;
          }
        });

        const statusClass =
          s.status === "fetched"
            ? "chip taste-high"
            : s.status === "failed"
            ? "chip taste-low"
            : "chip taste-mid";

        return el("tr", {}, [
          el("td", { class: "artist-name-cell" }, [
            el("strong", { text: s.name }),
          ]),
          el("td", {}, [
            el("span", {
              class: `chip ${s.category === "electronic" ? "key" : "local"}`,
              text: s.category.toUpperCase(),
            }),
          ]),
          el("td", {}, [
            el("span", { class: "chip source", text: (s.source || "unknown").toUpperCase() }),
          ]),
          el("td", { class: "mono" }, [
            el("span", { text: Number(s.priority_score || 0).toFixed(2) }),
          ]),
          el("td", {}, [
            el("span", { class: statusClass, text: s.status.toUpperCase() }),
          ]),
          el("td", {}, [
            el("div", { class: "cell-actions" }, [fetchBtn, removeBtn, blockBtn]),
          ]),
        ]);
      })
    );
  } catch (error) {
    tbody.replaceChildren(
      el("tr", {}, [el("td", { colspan: 6, class: "empty", text: error.message })])
    );
  }
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

async function populateGenreFilter() {
  const select = $("artists-genre-filter");
  if (!select || select.dataset.loaded) return;
  try {
    const data = await api.genrePresets();
    if (data && data.presets) {
      select.dataset.loaded = "true";
      for (const preset of data.presets) {
        select.append(el("option", { value: preset, text: preset }));
      }
    }
  } catch {
    // ignore
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
    loadSeeds(seedsPage);
    loadBlacklist();
    loadHardware();
  });
  $("reset-embeddings").addEventListener("click", resetEmbeddings);

  // Subtabs switcher
  const subtabsWrap = $("stats-subtabs");
  if (subtabsWrap) {
    subtabsWrap.addEventListener("click", (e) => {
      const btn = e.target.closest(".subtab");
      if (!btn) return;
      const subtab = btn.dataset.subtab;
      for (const b of subtabsWrap.querySelectorAll(".subtab")) {
        b.classList.toggle("active", b === btn);
      }
      $("panel-artists")?.classList.toggle("hidden", subtab !== "artists");
      $("panel-seeds")?.classList.toggle("hidden", subtab !== "seeds");
      $("panel-blacklist")?.classList.toggle("hidden", subtab !== "blacklist");

      if (subtab === "artists") loadArtists(artistPage);
      else if (subtab === "seeds") loadSeeds(seedsPage);
      else if (subtab === "blacklist") loadBlacklist();
    });
  }

  // Artists explorer listeners
  $("artists-search").addEventListener("input", () => {
    clearTimeout(artistsSearchTimer);
    artistsSearchTimer = setTimeout(() => loadArtists(1), 300);
  });
  $("artists-source-filter").addEventListener("change", () => loadArtists(1));
  $("artists-genre-filter")?.addEventListener("change", () => loadArtists(1));
  $("artists-min-year")?.addEventListener("input", () => {
    clearTimeout(artistsSearchTimer);
    artistsSearchTimer = setTimeout(() => loadArtists(1), 300);
  });
  $("artists-sort").addEventListener("change", () => loadArtists(1));
  $("artists-taste-mode-select")?.addEventListener("change", () => loadArtists(1));
  $("artists-liked-only-btn")?.addEventListener("click", () => {
    artistsLikedOnlyActive = !artistsLikedOnlyActive;
    $("artists-liked-only-btn")?.classList.toggle("active-filter", artistsLikedOnlyActive);
    loadArtists(1);
  });
  $("artists-similar-liked-btn")?.addEventListener("click", () => openSimilarArtistsModal());
  $("artists-prev").addEventListener("click", () => loadArtists(artistPage - 1));
  $("artists-next").addEventListener("click", () => loadArtists(artistPage + 1));

  populateGenreFilter();

  // Bulk selection bar listeners
  $("artists-select-all")?.addEventListener("change", (e) => {
    const isChecked = e.target.checked;
    for (const a of currentPageArtists) {
      if (isChecked) {
        selectedArtists.add(a.artist);
      } else {
        selectedArtists.delete(a.artist);
      }
    }
    for (const cb of document.querySelectorAll(".artist-select-checkbox")) {
      cb.checked = isChecked;
    }
    updateArtistsBulkBar();
    updateMasterCheckbox();
  });

  $("artists-clear-selection-btn")?.addEventListener("click", () => {
    selectedArtists.clear();
    for (const cb of document.querySelectorAll(".artist-select-checkbox")) {
      cb.checked = false;
    }
    updateArtistsBulkBar();
    updateMasterCheckbox();
  });

  $("bulk-select-blacklist")?.addEventListener("change", () => {
    updateArtistsBulkBar();
  });

  $("artists-bulk-delete-btn")?.addEventListener("click", openBulkDeleteConfirmModal);

  // Bulk delete confirmation modal wiring
  const bulkDeleteModal = $("modal-bulk-delete-confirm");
  $("modal-bulk-delete-close")?.addEventListener("click", closeBulkDeleteConfirmModal);
  $("modal-bulk-delete-cancel")?.addEventListener("click", closeBulkDeleteConfirmModal);
  bulkDeleteModal?.addEventListener("click", (e) => {
    if (e.target === bulkDeleteModal) closeBulkDeleteConfirmModal();
  });

  $("modal-bulk-delete-confirm-btn")?.addEventListener("click", async () => {
    if (selectedArtists.size === 0) return;
    const alsoBlacklist = $("bulk-select-blacklist")?.checked ?? false;
    const confirmBtn = $("modal-bulk-delete-confirm-btn");
    if (confirmBtn) confirmBtn.disabled = true;
    try {
      const res = await api.bulkDeleteArtists(Array.from(selectedArtists), alsoBlacklist);
      closeBulkDeleteConfirmModal();
      selectedArtists.clear();
      updateArtistsBulkBar();
      updateMasterCheckbox();
      emit("toast", `Deleted ${res.artists_deleted} artists (${res.tracks_deleted} tracks)${res.blacklisted_count ? ` [${res.blacklisted_count} blacklisted]` : ""}${res.skipped_protected ? ` [${res.skipped_protected} protected]` : ""}`);
      await Promise.all([loadAnalytics(), loadArtists(artistPage), loadSeeds(1), loadBlacklist()]);
    } catch (err) {
      emit("toast", err.message);
    } finally {
      if (confirmBtn) confirmBtn.disabled = false;
    }
  });

  // Bulk cleanup modal wiring
  const bulkCleanupModal = $("modal-bulk-cleanup");
  $("artists-bulk-cleanup-btn")?.addEventListener("click", openBulkCleanupModal);
  $("modal-bulk-cleanup-close")?.addEventListener("click", closeBulkCleanupModal);
  $("modal-bulk-cleanup-cancel")?.addEventListener("click", closeBulkCleanupModal);
  bulkCleanupModal?.addEventListener("click", (e) => {
    if (e.target === bulkCleanupModal) closeBulkCleanupModal();
  });

  $("bulk-cleanup-genre")?.addEventListener("change", () => scheduleCleanupPreview(50));
  $("bulk-cleanup-taste")?.addEventListener("input", () => {
    const val = $("bulk-cleanup-taste").value;
    const presets = $("bulk-cleanup-taste-presets");
    if (presets) {
      for (const b of presets.querySelectorAll(".preset-btn")) {
        b.classList.toggle("active", b.dataset.val === val);
      }
    }
    scheduleCleanupPreview(250);
  });
  $("bulk-cleanup-taste-presets")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".preset-btn");
    if (!btn) return;
    const val = btn.dataset.val;
    const input = $("bulk-cleanup-taste");
    if (input) input.value = val;
    const presets = $("bulk-cleanup-taste-presets");
    if (presets) {
      for (const b of presets.querySelectorAll(".preset-btn")) {
        b.classList.toggle("active", b === btn);
      }
    }
    scheduleCleanupPreview(0);
  });
  $("bulk-cleanup-protect-liked")?.addEventListener("change", () => scheduleCleanupPreview(50));
  $("bulk-cleanup-protect-local")?.addEventListener("change", () => scheduleCleanupPreview(50));
  $("bulk-cleanup-blacklist")?.addEventListener("change", () => {
    const alsoBlacklist = $("bulk-cleanup-blacklist")?.checked ?? true;
    const submitBtn = $("modal-bulk-cleanup-submit");
    if (submitBtn && currentCleanupPreview) {
      submitBtn.textContent = currentCleanupPreview.artist_count === 0
        ? "NO MATCHING ARTISTS"
        : `${alsoBlacklist ? "DELETE & BLOCK" : "DELETE"} ${currentCleanupPreview.artist_count} ARTISTS`;
    }
  });
  $("modal-bulk-cleanup-submit")?.addEventListener("click", executeBulkCleanup);

  function updateSeedsPurgeFilteredBtn() {
    const btn = $("seeds-purge-filtered-btn");
    if (!btn) return;
    const source = $("seeds-source-filter")?.value || "";
    const category = $("seeds-category-filter")?.value || "";
    const hasFilter = !!(source || category);
    btn.disabled = !hasFilter;
    if (hasFilter) {
      const parts = [];
      if (source) parts.push(`source '${source}'`);
      if (category) parts.push(`category '${category}'`);
      btn.title = `Purge seeds matching ${parts.join(" and ")}`;
    } else {
      btn.title = "Select a source or category filter first";
    }
  }

  // Seeds queue listeners
  $("seeds-search")?.addEventListener("input", () => {
    clearTimeout(seedsSearchTimer);
    seedsSearchTimer = setTimeout(() => loadSeeds(1), 300);
  });
  $("seeds-status-filter")?.addEventListener("change", () => loadSeeds(1));
  $("seeds-source-filter")?.addEventListener("change", () => {
    updateSeedsPurgeFilteredBtn();
    loadSeeds(1);
  });
  $("seeds-category-filter")?.addEventListener("change", () => {
    updateSeedsPurgeFilteredBtn();
    loadSeeds(1);
  });
  $("seeds-prev")?.addEventListener("click", () => loadSeeds(seedsPage - 1));
  $("seeds-next")?.addEventListener("click", () => loadSeeds(seedsPage + 1));

  // Purge buttons
  $("seeds-keep-core-btn")?.addEventListener("click", async () => {
    if (
      !window.confirm(
        "Delete all pending seeds EXCEPT core sources (local-library, itunes-crawl, manual-artist, dj-set, liked-artist)?"
      )
    )
      return;
    try {
      const res = await api.purgeSeeds({
        status: "pending",
        exclude_sources: ["local-library", "itunes-crawl", "manual-artist", "dj-set", "liked-artist"],
      });
      emit("toast", `Purged ${res.purged} non-core pending seeds`);
      await Promise.all([loadAnalytics(), loadSeeds(1)]);
    } catch (err) {
      emit("toast", err.message);
    }
  });

  $("seeds-purge-general-btn")?.addEventListener("click", async () => {
    if (!window.confirm("Purge all pending seeds in category 'general'?")) return;
    try {
      const res = await api.purgeSeeds({ status: "pending", category: "general" });
      emit("toast", `Purged ${res.purged} general seeds`);
      await Promise.all([loadAnalytics(), loadSeeds(1)]);
    } catch (err) {
      emit("toast", err.message);
    }
  });

  $("seeds-purge-filtered-btn")?.addEventListener("click", async () => {
    const source = $("seeds-source-filter")?.value || "";
    const category = $("seeds-category-filter")?.value || "";
    const status = $("seeds-status-filter")?.value || "pending";
    if (!source && !category) return;
    const parts = [`status '${status}'`];
    if (source) parts.push(`source '${source}'`);
    if (category) parts.push(`category '${category}'`);
    if (!window.confirm(`Purge seeds matching ${parts.join(" and ")}?`)) return;
    try {
      const res = await api.purgeSeeds({
        status,
        source: source || undefined,
        category: category || undefined,
      });
      emit("toast", `Purged ${res.purged} filtered seeds`);
      await Promise.all([loadAnalytics(), loadSeeds(1)]);
    } catch (err) {
      emit("toast", err.message);
    }
  });

  $("seeds-purge-failed-btn")?.addEventListener("click", async () => {
    if (!window.confirm("Purge ALL failed seeds from the queue?")) return;
    try {
      const res = await api.purgeSeeds({ status: "failed" });
      emit("toast", `Purged ${res.purged} failed seeds`);
      await Promise.all([loadAnalytics(), loadSeeds(1)]);
    } catch (err) {
      emit("toast", err.message);
    }
  });

  $("seeds-clear-all-pending-btn")?.addEventListener("click", async () => {
    if (!window.confirm("WARNING: Are you sure you want to delete ALL pending seeds in the entire queue?"))
      return;
    try {
      const res = await api.purgeSeeds({ status: "pending" });
      emit("toast", `Cleared ${res.purged} pending seeds`);
      await Promise.all([loadAnalytics(), loadSeeds(1)]);
    } catch (err) {
      emit("toast", err.message);
    }
  });

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

  // Artist tracks modal wiring
  const tracksModal = $("modal-artist-tracks");
  $("modal-artist-tracks-close")?.addEventListener("click", closeArtistTracksModal);
  tracksModal?.addEventListener("click", (e) => {
    if (e.target === tracksModal) closeArtistTracksModal();
  });
  $("modal-artist-tracks-filter")?.addEventListener("input", renderArtistTracksModalList);
  $("modal-artist-tracks-fetch")?.addEventListener("click", () => {
    const artist = currentArtistName;
    closeArtistTracksModal();
    if (openFetchModalFn) openFetchModalFn(artist);
  });
  $("modal-artist-tracks-like")?.addEventListener("click", async () => {
    if (!currentArtistName) return;
    const likeBtn = $("modal-artist-tracks-like");
    const wasLiked = likeBtn?.classList.contains("liked");
    if (likeBtn) likeBtn.disabled = true;
    try {
      if (wasLiked) {
        await api.unlikeArtist(currentArtistName);
        likedArtistsSet.delete(currentArtistName.toLowerCase());
        if (likeBtn) {
          likeBtn.classList.remove("liked");
          likeBtn.textContent = "♡";
          likeBtn.title = "Like artist";
        }
        emit("toast", `Unliked "${currentArtistName}"`);
        emit("artist:liked", { artist: currentArtistName, liked: false });
      } else {
        await api.likeArtist(currentArtistName);
        likedArtistsSet.add(currentArtistName.toLowerCase());
        if (likeBtn) {
          likeBtn.classList.add("liked");
          likeBtn.textContent = "♥";
          likeBtn.title = "Unlike artist";
        }
        emit("toast", `Liked "${currentArtistName}"`);
        emit("artist:liked", { artist: currentArtistName, liked: true });
      }
      loadArtists(artistPage);
    } catch (err) {
      emit("toast", err.message);
    } finally {
      if (likeBtn) likeBtn.disabled = false;
    }
  });

  // Similar artists modal wiring
  const similarModal = $("modal-similar-artists");
  $("modal-similar-artists-close")?.addEventListener("click", closeSimilarArtistsModal);
  similarModal?.addEventListener("click", (e) => {
    if (e.target === similarModal) closeSimilarArtistsModal();
  });
  $("similar-artists-refresh-btn")?.addEventListener("click", () => loadSimilarArtists());
  $("similar-artists-min-year")?.addEventListener("input", () => {
    clearTimeout(similarSearchTimer);
    similarSearchTimer = setTimeout(() => loadSimilarArtists(), 300);
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (fetchModal && !fetchModal.classList.contains("hidden")) {
        closeFetchArtistModal();
        return;
      }
      if (tracksModal && !tracksModal.classList.contains("hidden")) {
        closeArtistTracksModal();
        return;
      }
      if (similarModal && !similarModal.classList.contains("hidden")) {
        closeSimilarArtistsModal();
        return;
      }
      if (bulkDeleteModal && !bulkDeleteModal.classList.contains("hidden")) {
        closeBulkDeleteConfirmModal();
        return;
      }
      if (bulkCleanupModal && !bulkCleanupModal.classList.contains("hidden")) {
        closeBulkCleanupModal();
        return;
      }
    }
  });

  on("artist:liked", ({ artist, liked }) => {
    if (liked) {
      likedArtistsSet.add((artist || "").toLowerCase());
    } else {
      likedArtistsSet.delete((artist || "").toLowerCase());
    }
  });

  // Close tracks modal when navigating to dig from inside it
  on("dig:track", () => {
    closeArtistTracksModal();
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
    const minYearInput = $("fetch-artist-min-year");
    const electronicOnlyInput = $("fetch-artist-electronic-only");
    const minYearVal = minYearInput ? minYearInput.value.trim() : "";
    const minYear = minYearVal ? Number(minYearVal) : undefined;
    const electronicOnly = electronicOnlyInput ? electronicOnlyInput.checked : false;

    closeFetchArtistModal();
    try {
      await api.startJob("fetch-artist", {
        artist,
        tracks_per_artist: count,
        auto_index: autoIndex,
        discover_related: discoverRelated,
        related_limit: 10,
        min_year: minYear,
        electronic_only: electronicOnly,
      });
      emit("toast", `Started fetch for "${artist}"`);
      emit("tab:show", "run");
    } catch (err) {
      emit("toast", err.message);
    }
  });

  // Refresh upon track deletion
  on("track:deleted", (payload) => {
    loadAnalytics();
    loadArtists(artistPage);
    const tm = $("modal-artist-tracks");
    if (tm && !tm.classList.contains("hidden")) {
      const trackId = payload?.trackId;
      if (trackId) {
        currentArtistTracks = currentArtistTracks.filter((t) => t.id !== trackId);
      }
      renderArtistTracksModalList();
    }
  });

  loadAnalytics();
  refreshLikedArtists().then(() => loadArtists(1));
  loadSeeds(1);
  loadBlacklist();
  loadHardware();
}

export { loadAnalytics, loadArtists, loadSeeds, loadBlacklist, loadHardware };
