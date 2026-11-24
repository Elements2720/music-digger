/**
 * Thin fetch + SSE client for the local FastAPI backend.
 * Every method maps 1:1 to a backend route — do not reshape responses here.
 */
import type {
  ArtistTracksResponse,
  ArtistsSummaryResponse,
  AutoSequenceResponse,
  BlacklistResponse,
  BridgeResponse,
  BulkCleanupExecuteResponse,
  BulkCleanupPreviewResponse,
  BulkDeleteArtistsResponse,
  CatalogAnalytics,
  CatalogStatsResponse,
  DashboardResponse,
  DeleteArtistResponse,
  DeleteTrackResponse,
  DigResponse,
  DownloadTrackResponse,
  EvaluateSequenceResponse,
  FilterCatalogResponse,
  GenrePresetsResponse,
  HardwareResponse,
  HeardToggleResponse,
  JobCancelResponse,
  JobCurrentResponse,
  JobEvent,
  JobStartResponse,
  LikedArtistsResponse,
  PlannedSet,
  RecentTracksResponse,
  ResetEmbeddingsResponse,
  SearchTracksResponse,
  SeedPurgeBody,
  SeedsResponse,
  SetDetailResponse,
  SetsListResponse,
  SimilarArtistsResponse,
  SuggestNextResponse,
  TasteRankingResponse,
  VibeSearchResponse,
} from "../types/apiTypes";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const BASE = "";

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  raw?: boolean;
}

function buildQuery(params: RequestOptions["params"]): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    qs.set(key, String(value));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, params, raw = false } = options;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${buildQuery(params)}`, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Cannot reach the local backend — is the server running?", 0);
  }
  if (raw) {
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new ApiError(text || `Request failed (${res.status})`, res.status);
    }
    return (await res.text()) as T;
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data?.detail === "string") detail = data.detail;
      else if (data?.detail != null) detail = JSON.stringify(data.detail);
    } catch {
      /* keep default detail */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

function encodedPath(value: string): string {
  return encodeURIComponent(value);
}

// ------------------------------------------------------------------ catalog

export const api = {
  health(): Promise<{ status: string }> {
    return request("/api/health");
  },

  hardware(): Promise<HardwareResponse> {
    return request("/api/hardware");
  },

  stats(): Promise<CatalogStatsResponse> {
    return request("/api/stats");
  },

  dashboard(): Promise<DashboardResponse> {
    return request("/api/catalog/dashboard");
  },

  analytics(): Promise<CatalogAnalytics> {
    return request("/api/catalog/analytics");
  },

  searchTracks(q: string, limit = 30): Promise<SearchTracksResponse> {
    return request("/api/tracks/search", { params: { q, limit } });
  },

  recentTracks(limit = 24): Promise<RecentTracksResponse> {
    return request("/api/tracks/recent", { params: { limit } });
  },

  filterCatalog(params: {
    q?: string;
    key?: string;
    bpm_min?: number;
    bpm_max?: number;
    source?: string;
    limit?: number;
  }): Promise<FilterCatalogResponse> {
    return request("/api/catalog/filter", { params });
  },

  genrePresets(): Promise<GenrePresetsResponse> {
    return request("/api/catalog/genre-presets");
  },

  dig(
    trackId: string,
    params: {
      limit?: number;
      bpm_tolerance?: number;
      harmonic?: boolean;
      genre?: string;
      genres?: string;
      min_year?: number;
      max_year?: number;
      exclude_heard?: boolean;
    } = {},
  ): Promise<DigResponse> {
    return request(`/api/dig/${encodedPath(trackId)}`, { params });
  },

  vibeSearch(payload: {
    query: string;
    limit?: number;
    bpm_min?: number | null;
    bpm_max?: number | null;
    camelot_keys?: string[];
    exclude_heard?: boolean;
    genre?: string | null;
  }): Promise<VibeSearchResponse> {
    return request("/api/vibe-search", { method: "POST", body: payload });
  },

  setHeard(trackId: string, heard: boolean): Promise<HeardToggleResponse> {
    return request(`/api/tracks/${encodedPath(trackId)}/heard`, {
      method: "PATCH",
      body: { heard },
    });
  },

  resetEmbeddings(confirm: boolean): Promise<ResetEmbeddingsResponse> {
    return request("/api/reset-embeddings", {
      method: "POST",
      body: { confirm },
    });
  },

  downloadTrack(trackId: string, force = false): Promise<DownloadTrackResponse> {
    return request(`/api/catalog/tracks/${encodedPath(trackId)}/download`, {
      method: "POST",
      params: { force },
    });
  },

  deleteTrack(
    trackId: string,
    blacklist = false,
    reason?: string,
  ): Promise<DeleteTrackResponse> {
    return request(`/api/catalog/tracks/${encodedPath(trackId)}`, {
      method: "DELETE",
      params: { blacklist, reason },
    });
  },

  // -------------------------------------------------------------- artists

  artists(params: {
    q?: string;
    genre?: string;
    source?: string;
    min_year?: number;
    sort?: string;
    limit?: number;
    offset?: number;
    taste_mode?: string;
    liked_only?: boolean;
  }): Promise<ArtistsSummaryResponse> {
    return request("/api/catalog/artists", { params });
  },

  artistTracks(artistName: string, limit = 100): Promise<ArtistTracksResponse> {
    return request(`/api/catalog/artists/${encodedPath(artistName)}/tracks`, {
      params: { limit },
    });
  },

  deleteArtist(
    artistName: string,
    blacklist = false,
    reason?: string,
  ): Promise<DeleteArtistResponse> {
    return request(`/api/catalog/artists/${encodedPath(artistName)}`, {
      method: "DELETE",
      params: { blacklist, reason },
    });
  },

  bulkDeleteArtists(payload: {
    artist_names: string[];
    blacklist?: boolean;
    reason?: string | null;
  }): Promise<BulkDeleteArtistsResponse> {
    return request("/api/catalog/artists/bulk-delete", {
      method: "POST",
      body: payload,
    });
  },

  bulkCleanupPreview(payload: {
    max_taste_percent?: number | null;
    taste_mode?: "both" | "local" | "liked";
    genre?: string | null;
    source?: string | null;
    protect_liked?: boolean;
    protect_local?: boolean;
  }): Promise<BulkCleanupPreviewResponse> {
    return request("/api/catalog/artists/bulk-cleanup/preview", {
      method: "POST",
      body: payload,
    });
  },

  bulkCleanupExecute(payload: {
    max_taste_percent?: number | null;
    taste_mode?: "both" | "local" | "liked";
    genre?: string | null;
    source?: string | null;
    protect_liked?: boolean;
    protect_local?: boolean;
    blacklist?: boolean;
    reason?: string | null;
  }): Promise<BulkCleanupExecuteResponse> {
    return request("/api/catalog/artists/bulk-cleanup", {
      method: "POST",
      body: payload,
    });
  },

  tasteRanking(params: {
    mode?: "both" | "local" | "liked";
    genre?: string;
    source?: string;
    limit?: number;
  }): Promise<TasteRankingResponse> {
    return request("/api/catalog/taste-ranking", { params });
  },

  // ------------------------------------------------------------ blacklist

  blacklist(params: {
    kind?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }): Promise<BlacklistResponse> {
    return request("/api/catalog/blacklist", { params });
  },

  addBlacklist(payload: {
    kind: "artist" | "track";
    name: string;
    track_title?: string | null;
    reason?: string | null;
  }): Promise<BlacklistResponse["entries"][number]> {
    return request("/api/catalog/blacklist", { method: "POST", body: payload });
  },

  removeBlacklistEntry(entryId: number): Promise<{ success: boolean; id: number }> {
    return request(`/api/catalog/blacklist/${entryId}`, { method: "DELETE" });
  },

  // ---------------------------------------------------------------- seeds

  seeds(params: {
    status?: string;
    source?: string;
    category?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }): Promise<SeedsResponse> {
    return request("/api/catalog/seeds", { params });
  },

  deleteSeed(name: string): Promise<{ name: string; deleted: boolean }> {
    return request(`/api/catalog/seeds/${name}`, { method: "DELETE" });
  },

  purgeSeeds(payload: SeedPurgeBody): Promise<{ purged: number }> {
    return request("/api/catalog/seeds/purge", { method: "POST", body: payload });
  },

  // -------------------------------------------------------- liked artists

  likedArtists(): Promise<LikedArtistsResponse> {
    return request("/api/catalog/liked-artists");
  },

  likeArtist(artistName: string): Promise<{ liked: boolean }> {
    return request(`/api/catalog/liked-artists/${encodedPath(artistName)}`, {
      method: "POST",
    });
  },

  unlikeArtist(artistName: string): Promise<{ deleted: boolean; unliked: boolean }> {
    return request(`/api/catalog/liked-artists/${encodedPath(artistName)}`, {
      method: "DELETE",
    });
  },

  similarArtists(params: {
    artist?: string;
    min_year?: number;
    limit?: number;
  }): Promise<SimilarArtistsResponse> {
    return request("/api/catalog/liked-artists/similar", { params });
  },

  // ------------------------------------------------------ DJ sets (mixes)

  listSets(limit = 20): Promise<SetsListResponse> {
    return request("/api/sets", { params: { limit } });
  },

  setDetail(
    setId: string,
    params: {
      view?: "tracklist" | "tracks" | "sets";
      limit?: number;
      bpm_tolerance?: number;
      exclude_heard?: boolean;
      genre?: string;
    } = {},
  ): Promise<SetDetailResponse> {
    return request(`/api/sets/${encodedPath(setId)}`, { params });
  },

  // ------------------------------------------------------------ set helper

  suggestNext(payload: {
    from_track_id: string;
    limit?: number;
    flow?: "steady" | "ramp_up" | "cool_down" | "any";
    local_only?: boolean;
    bpm_max_delta?: number;
  }): Promise<SuggestNextResponse> {
    return request("/api/set-helper/suggest-next", {
      method: "POST",
      body: payload,
    });
  },

  bridge(payload: {
    track_a_id: string;
    track_b_id: string;
    limit?: number;
    local_only?: boolean;
  }): Promise<BridgeResponse> {
    return request("/api/set-helper/bridge", { method: "POST", body: payload });
  },

  autoSequence(payload: {
    track_ids: string[];
    flow?: "steady" | "ramp_up" | "cool_down" | "any";
    lock_first?: boolean;
  }): Promise<AutoSequenceResponse> {
    return request("/api/set-helper/auto-sequence", {
      method: "POST",
      body: payload,
    });
  },

  evaluate(payload: {
    track_ids: string[];
    flow?: "steady" | "ramp_up" | "cool_down" | "any";
  }): Promise<EvaluateSequenceResponse> {
    return request("/api/set-helper/evaluate", { method: "POST", body: payload });
  },

  listPlannedSets(): Promise<PlannedSet[]> {
    return request("/api/set-helper/sets");
  },

  createPlannedSet(payload: {
    name: string;
    track_ids: string[];
  }): Promise<PlannedSet> {
    return request("/api/set-helper/sets", { method: "POST", body: payload });
  },

  getPlannedSet(setId: number): Promise<PlannedSet> {
    return request(`/api/set-helper/sets/${setId}`);
  },

  updatePlannedSet(
    setId: number,
    payload: { name?: string | null; track_ids?: string[] | null },
  ): Promise<PlannedSet> {
    return request(`/api/set-helper/sets/${setId}`, {
      method: "PUT",
      body: payload,
    });
  },

  deletePlannedSet(setId: number): Promise<{ deleted: boolean; id: number }> {
    return request(`/api/set-helper/sets/${setId}`, { method: "DELETE" });
  },

  exportPlannedSetM3u8(setId: number): Promise<string> {
    return request(`/api/set-helper/sets/${setId}/export.m3u8`, { raw: true });
  },

  // ----------------------------------------------------------------- jobs

  startJob(kind: string, params: Record<string, unknown>): Promise<JobStartResponse> {
    return request("/api/jobs", { method: "POST", body: { kind, params } });
  },

  currentJob(): Promise<JobCurrentResponse> {
    return request("/api/jobs/current");
  },

  cancelJob(): Promise<JobCancelResponse> {
    return request("/api/jobs/cancel", { method: "POST" });
  },

  /** Subscribe to `/api/jobs/stream` Server-Sent Events. Returns a closer. */
  streamJobs(onEvent: (event: JobEvent) => void, onError?: () => void): () => void {
    const source = new EventSource(`${BASE}/api/jobs/stream`);
    source.onmessage = (event: MessageEvent<string>) => {
      try {
        onEvent(JSON.parse(event.data) as JobEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    source.onerror = () => onError?.();
    return () => source.close();
  },
};
