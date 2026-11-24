/* Thin fetch + SSE client for the local FastAPI backend.
 * Every method maps 1:1 to a backend endpoint — do not reshape responses here.
 */

async function request(path, { method = "GET", body, params, raw = false } = {}) {
  const url = new URL(path, window.location.origin);
  if (params) {
    const entries = params instanceof URLSearchParams ? params.entries() : Object.entries(params);
    for (const [key, value] of entries) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Cannot reach the local backend — is the server running?");
  }
  if (raw) {
    const text = await res.text();
    if (!res.ok) throw new Error(text || `Request failed (${res.status})`);
    return text;
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let detail = data?.detail ?? `Request failed (${res.status})`;
    if (typeof detail === "object" && detail !== null) {
      if (detail.msg) detail = detail.msg;
      else detail = JSON.stringify(detail);
    } else if (typeof data.error === "string") {
      detail = data.error;
    }
    throw new Error(detail);
  }
  return data;
}

export const api = {
  // ---- system ----
  health: () => request("/api/health"),
  stats: () => request("/api/stats"),
  dashboard: () => request("/api/catalog/dashboard"),

  // ---- catalog: tracks ----
  searchTracks: (q, limit = 30) =>
    request(`/api/tracks/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  recentTracks: (limit = 30) => request(`/api/tracks/recent?limit=${limit}`),
  track: (trackId) => request(`/api/tracks/${encodeURIComponent(trackId)}`),
  downloadTrack: (trackId, force = false) =>
    request(`/api/tracks/${encodeURIComponent(trackId)}/download`, {
      method: "POST",
      body: { force },
    }),
  deleteTrack: (trackId, blacklist = false, reason = null) =>
    request(`/api/tracks/${encodeURIComponent(trackId)}?blacklist=${blacklist}${reason ? `&reason=${encodeURIComponent(reason)}` : ""}`, {
      method: "DELETE",
    }),

  // ---- catalog: artists ----
  artists: (params = {}) => request("/api/catalog/artists", { params }),
  fetchArtist: (artistName) =>
    request("/api/jobs", {
      method: "POST",
      body: { kind: "fetch-artist", params: { artist: artistName } },
    }),
  artistTracks: (artistName, params = {}) =>
    request(`/api/catalog/artists/${encodeURIComponent(artistName)}/tracks`, { params }),
  likeArtist: (artistName) =>
    request(`/api/catalog/liked-artists/${encodeURIComponent(artistName)}`, { method: "POST" }),
  unlikeArtist: (artistName) =>
    request(`/api/catalog/liked-artists/${encodeURIComponent(artistName)}`, { method: "DELETE" }),
  likedArtists: (params = {}) => request("/api/catalog/liked-artists", { params }),
  deleteArtist: (artistName, blacklist = false, reason = null) =>
    request(`/api/catalog/artists/${encodeURIComponent(artistName)}?blacklist=${blacklist}${reason ? `&reason=${encodeURIComponent(reason)}` : ""}`, {
      method: "DELETE",
    }),

  // ---- dig ----
  dig: (trackId, params = {}) =>
    request(`/api/dig/${encodeURIComponent(trackId)}`, { params }),
  vibeSearch: (payload) => request("/api/vibe-search", { method: "POST", body: payload }),
  catalogFilter: (params = {}) => request("/api/catalog/filter", { params }),
  tasteRanking: (params = {}) => request("/api/catalog/taste-ranking", { params }),

  // ---- seeds ----
  seeds: (params = {}) => request("/api/catalog/seeds", { params }),
  deleteSeed: (name) => request(`/api/catalog/seeds/${encodeURIComponent(name)}`, { method: "DELETE" }),
  purgeSeeds: (payload = {}) => request("/api/catalog/seeds/purge", { method: "POST", body: payload }),

  // ---- bulk cleanup ----
  previewBulkCleanup: (criteria) =>
    request("/api/catalog/artists/bulk-cleanup/preview", { method: "POST", body: criteria }),
  executeBulkCleanup: (payload) =>
    request("/api/catalog/artists/bulk-cleanup", { method: "POST", body: payload }),
  bulkDeleteArtists: (artistNames, blacklist = true) =>
    request("/api/catalog/artists/bulk-cleanup", {
      method: "POST",
      body: { artists: artistNames, blacklist },
    }),

  // ---- blacklist ----
  blacklist: (params = {}) => request("/api/catalog/blacklist", { params }),
  addBlacklist: (payload) =>
    request("/api/catalog/blacklist", { method: "POST", body: { kind: "artist", ...payload } }),  removeBlacklist: (entryId) =>
    request(`/api/catalog/blacklist/${entryId}`, { method: "DELETE" }),

  // ---- set helper ----
  suggestNext: (fromTrackId, params = {}) =>
    request("/api/set-helper/suggest-next", { method: "POST", body: { from_track_id: fromTrackId, ...params } }),
  findBridge: (trackAId, trackBId, params = {}) =>
    request("/api/set-helper/bridge", { method: "POST", body: { track_a_id: trackAId, track_b_id: trackBId, ...params } }),
  autoSequence: (trackIds, params = {}) =>
    request("/api/set-helper/auto-sequence", { method: "POST", body: { track_ids: trackIds, ...params } }),
  evaluateSequence: (trackIds, params = {}) =>
    request("/api/set-helper/evaluate", { method: "POST", body: { track_ids: trackIds, ...params } }),

  // ---- planned sets ----
  listPlannedSets: () => request("/api/set-helper/sets"),
  getPlannedSet: (id) => request(`/api/set-helper/sets/${id}`),
  createPlannedSet: (name, trackIds) =>
    request("/api/set-helper/sets", { method: "POST", body: { name, track_ids: trackIds } }),
  updatePlannedSet: (id, payload) =>
    request(`/api/set-helper/sets/${id}`, { method: "PATCH", body: payload }),
  deletePlannedSet: (id) => request(`/api/set-helper/sets/${id}`, { method: "DELETE" }),
  exportPlannedSet: (id) => request(`/api/set-helper/sets/${id}/export.m3u8`, { raw: true }),

  // ---- DJ sets (analyzed) ----
  listSets: (limit = 20) => request(`/api/sets?limit=${limit}`),
  getSet: (id) => request(`/api/sets/${id}`),

  // ---- jobs ----
  startJob: (kind, params = {}) =>
    request("/api/jobs", { method: "POST", body: { kind, params } }),
  currentJob: () => request("/api/jobs/current"),
  cancelJob: () => request("/api/jobs/cancel", { method: "POST" }),
};

/** Subscribe to the global job SSE stream (one job runs at a time).
 * Returns an EventTarget dispatching 'progress', 'state' and 'error' events;
 * call .close() when done. */
export function subscribeJob() {
  const target = new EventTarget();
  const source = new EventSource("/api/jobs/stream");
  const close = () => source.close();
  source.onmessage = (event) => {
    let parsed;
    try {
      parsed = JSON.parse(event.data);
    } catch {
      return;
    }
    const type = parsed.type ?? "progress";
    target.dispatchEvent(new CustomEvent(type, { detail: parsed }));
    if (type === "done" || type === "error" || type === "cancelled") {
      target.dispatchEvent(new CustomEvent("state", { detail: parsed }));
      close();
    }
  };
  source.onerror = () => {
    target.dispatchEvent(new CustomEvent("error", { detail: { message: "stream interrupted" } }));
    close();
  };
  target.close = close;
  return target;
}
