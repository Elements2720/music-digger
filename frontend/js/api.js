/* Thin fetch + SSE client for the local FastAPI backend. */

async function request(path, { method = "GET", body, params } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined || value === "") continue;
    url.searchParams.set(key, String(value));
  }
  const response = await fetch(url, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const detail =
      (data && typeof data === "object" && data.detail) ||
      `${response.status} ${response.statusText}`;
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail)
    );
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  stats: () => request("/api/stats"),
  hardware: () => request("/api/hardware"),

  searchTracks: (q, limit = 30) =>
    request("/api/tracks/search", { params: { q, limit } }),
  recentTracks: (limit = 30) =>
    request("/api/tracks/recent", { params: { limit } }),
  dig: (trackId, filters = {}) =>
    request(`/api/dig/${encodeURIComponent(trackId)}`, { params: filters }),
  vibeSearch: (payload) =>
    request("/api/vibe-search", { method: "POST", body: payload }),
  setHeard: (trackId, heard) =>
    request(`/api/tracks/${encodeURIComponent(trackId)}/heard`, {
      method: "PATCH",
      body: { heard },
    }),
  resetEmbeddings: () =>
    request("/api/reset-embeddings", {
      method: "POST",
      body: { confirm: true },
    }),

  sets: (limit = 50) => request("/api/sets", { params: { limit } }),
  setDetail: (setId, view, filters = {}) =>
    request(`/api/sets/${encodeURIComponent(setId)}`, {
      params: { view, ...filters },
    }),

  currentJob: () => request("/api/jobs/current"),
  startJob: (kind, params) =>
    request("/api/jobs", { method: "POST", body: { kind, params } }),
  cancelJob: () => request("/api/jobs/cancel", { method: "POST" }),
};

const TERMINAL = new Set(["done", "error", "cancelled"]);

/**
 * Subscribe to the job SSE stream. The server closes the stream after a
 * terminal event; we close the EventSource too so it does not reconnect in a
 * loop. Call again when a new job starts.
 */
export function subscribeJob(onEvent, onClose) {
  const source = new EventSource("/api/jobs/stream");
  let closed = false;

  source.onmessage = (message) => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch {
      return;
    }
    onEvent(event);
    if (TERMINAL.has(event.type) && !closed) {
      closed = true;
      source.close();
      onClose?.();
    }
  };
  source.onerror = () => {
    if (!closed && source.readyState === EventSource.CLOSED) {
      closed = true;
      onClose?.();
    }
  };
  return source;
}
