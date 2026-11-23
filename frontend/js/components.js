/* Shared track & artist row components: one visual language for every view. */

import { api } from "./api.js";
import { emit } from "./events.js";
import { keyBadge, esc, toast } from "./ui.js";
import { loadTrack } from "./player.js";
import { iconHeart, iconPlay, iconDownload, iconNote } from "./icons.js";

function chipLocal(t) {
  return t.has_local_file
    ? `<span class="chip chip-ok" title="Stored locally">LOCAL</span>`
    : `<button class="chip chip-action" data-download="${esc(t.id)}" title="Download preview to local storage">${iconDownload()} DL</button>`;
}

function chipSource(t) {
  const label = String(t.source ?? "").toUpperCase();
  return label ? `<span class="chip chip-source">${esc(label)}</span>` : "";
}

/** Artwork thumbnail, strictly 40x40, with a music-note placeholder when missing.
 * When `playId` is set, clicking the artwork plays that track. */
export function trackArtHTML(t, cls = "t-art", playId = null) {
  const click = playId ? ` data-play="${esc(playId)}" role="button" tabindex="0" title="Play ${esc(t.title)}"` : "";
  return t.artwork_url
    ? `<img class="${cls}${playId ? " t-click" : ""}" src="${esc(t.artwork_url)}" alt="" loading="lazy" width="40" height="40"${click}>`
    : `<span class="${cls} t-art-empty${playId ? " t-click" : ""}" aria-hidden="true"${click}>${iconNote()}</span>`;
}

/** Normalize a similarity/taste value to a clean 0-100 percentage string.
 * Backends may send 0-1 (0.48) or already-percent (48.48); never 4848%. */
export function pctLabel(val) {
  if (val == null || !Number.isFinite(Number(val))) return null;
  const n = Number(val);
  return `${Math.round(n <= 1 ? n * 100 : n)}%`;
}

/** BPM shown exactly as stored — no rounding or truncation. */
export function bpmLabel(t) {
  if (t.bpm == null || !Number.isFinite(Number(t.bpm))) return "&mdash;";
  return `${Number(t.bpm)} bpm`;
}

/* ---- Shared liked-artist state (single source of truth for every view) ---- */

const likedArtists = new Set();
const likeKey = (name) => String(name ?? "").trim().toLowerCase();

/** Hydrate the shared liked set once at app startup, before first render. */
export async function hydrateLikedArtists() {
  try {
    const res = await api.likedArtists();
    for (const entry of res.liked_artists ?? []) {
      const name = entry.artist_name ?? entry.artist ?? entry.name;
      if (name) likedArtists.add(likeKey(name));
    }
  } catch {
    /* hearts stay outline until the next successful sync */
  }
}

export function isArtistLiked(artistName) {
  return likedArtists.has(likeKey(artistName));
}

/** Flip every `[data-like]` heart for this artist, in place — no re-render. */
function syncHeartButtons(artist, liked) {
  const key = likeKey(artist);
  document.querySelectorAll("[data-like]").forEach((btn) => {
    if (likeKey(btn.dataset.like) !== key) return;
    btn.classList.toggle("liked", liked);
    btn.setAttribute("aria-pressed", liked ? "true" : "false");
    btn.setAttribute("aria-label", `${liked ? "Unlike" : "Like"} ${btn.dataset.like}`);
    btn.innerHTML = iconHeart(liked);
  });
}

/** Like button — solid heart when liked, outline when not. */
export function likeBtnHTML(artist, liked = isArtistLiked(artist)) {
  return `<button class="icon-btn like-btn${liked ? " liked" : ""}" data-like="${esc(artist)}" aria-pressed="${liked ? "true" : "false"}" aria-label="${liked ? "Unlike" : "Like"} ${esc(artist)}">${iconHeart(liked)}</button>`;
}

/** Toggle like/unlike and sync every matching heart in the DOM in place. */
export async function toggleArtistLike(btn) {
  const artist = btn.dataset.like;
  const liked = btn.classList.contains("liked");
  btn.disabled = true;
  try {
    if (liked) {
      await api.unlikeArtist(artist);
      likedArtists.delete(likeKey(artist));
      toast(`Removed ${artist} from liked artists`);
    } else {
      await api.likeArtist(artist);
      likedArtists.add(likeKey(artist));
      toast(`Liked ${artist}`);
    }
    syncHeartButtons(artist, !liked);
    emit("artists:changed", { artist, liked: !liked });
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

/** Standard Pro Track Row — play, artwork, title/artist, BPM, Camelot badge,
 * optional similarity/taste %, LOCAL/DL chip, heart, + Set.
 * Play button, artwork AND title all start playback. */
export function trackRowHTML(t, { similarity = null } = {}) {
  const pct = pctLabel(similarity ?? t.taste_match_percent);
  return `
  <div class="track-row" data-id="${esc(t.id)}">
    <button class="icon-btn" data-play="${esc(t.id)}" aria-label="Play ${esc(t.title)}">${iconPlay()}</button>
    ${trackArtHTML(t, "t-art", t.id)}
    <div class="t-main t-click" data-play="${esc(t.id)}" role="button" tabindex="0" title="Play ${esc(t.title)}">
      <div class="t-title">${esc(t.title)}</div>
      <div class="t-artist">${esc(t.artist)}</div>
    </div>
    ${pct ? `<span class="t-meta primary">${pct}</span>` : ""}
    <span class="t-meta primary">${bpmLabel(t)}</span>
    <span>${keyBadge(t.key)}</span>
    <div class="right-cluster">
      ${chipLocal(t)}${chipSource(t)}
      ${likeBtnHTML(t.artist)}
      <button class="icon-btn" data-add-set="${esc(t.id)}" title="Add to Set Builder playlist">+ Set</button>
    </div>
  </div>`;
}

/** Bind play / like / download / add-to-set for every `.track-row` under `root`. */
export function bindTrackRows(root, tracks) {
  const find = (id) => tracks.find((t) => t.id === id);
  root.querySelectorAll("[data-play]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const track = find(btn.dataset.play);
      if (track) loadTrack(track, tracks);
    }),
  );
  root.querySelectorAll("[data-like]").forEach((btn) =>
    btn.addEventListener("click", () => toggleArtistLike(btn)),
  );
  root.querySelectorAll("[data-download]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await api.downloadTrack(btn.dataset.download);
        btn.innerHTML = `${iconDownload()} LOCAL`;
        btn.classList.add("chip-ok");
        btn.classList.remove("chip-action");
        btn.disabled = false;
        emit("track:downloaded");
        toast("Downloaded to local storage");
      } catch (err) {
        btn.disabled = false;
        toast(err.message, "error");
      }
    }),
  );
  root.querySelectorAll("[data-add-set]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const track = find(btn.dataset.addSet);
      if (track) {
        emit("set:add-track", track);
        toast(`Added "${track.title}" to Set Builder playlist`);
      }
    }),
  );
}

/** Artist summary row for the Library hub. */
export function artistRowHTML(a) {
  const thumb = a.artwork_url
    ? `<img class="t-art" src="${esc(a.artwork_url)}" alt="" loading="lazy" width="40" height="40">`
    : `<span class="t-art t-art-empty t-art-mono" aria-hidden="true">${esc(String(a.artist ?? "?").trim().charAt(0).toUpperCase() || "?")}</span>`;
  const pct = pctLabel(a.taste_match_percent);
  return `
  <div class="track-row artist-row" data-artist="${esc(a.artist)}">
    <button class="icon-btn" data-artist-dig="${esc(a.artist)}" aria-label="Dig ${esc(a.artist)}">DIG</button>
    ${thumb}
    <div class="t-main">
      <div class="t-title">${esc(a.artist)}</div>
      <div class="t-artist">${esc((a.genres ?? []).slice(0, 2).join(" / ") || "—")}</div>
    </div>
    <span class="t-meta">${a.track_count ?? 0} tracks</span>
    <span class="t-meta">${a.year_min ?? "—"}–${a.year_max ?? "—"}</span>
    ${pct ? `<span class="t-meta primary" title="Taste match">${pct}</span>` : `<span class="t-meta">&mdash;</span>`}
    ${likeBtnHTML(a.artist)}
  </div>`;
}
