/**
 * Typed contracts for the local FastAPI backend.
 *
 * Every type mirrors a serializer or request body in
 * backend/src/presentation/api/schemas.py and routes/*.py 1:1.
 * Field names are exact — do not rename.
 */

export interface Track {
  id: string;
  title: string;
  artist: string;
  album: string | null;
  genre: string | null;
  duration_seconds: number | null;
  bpm: number | null;
  key: string | null;
  release_year: number | null;
  preview_url: string | null;
  artwork_url: string | null;
  store_url: string | null;
  source: string;
  local_path: string | null;
  has_local_file: boolean;
  is_heard: boolean;
}

export interface Match {
  track: Track;
  similarity: number;
  is_exact_id: boolean;
}

export interface TasteRankedMatch extends Track {
  taste_percent: number;
}

export interface TasteRankingResponse {
  matches: TasteRankedMatch[];
  total: number;
  mode: string;
}

export interface GenreStat {
  genre: string;
  track_count: number;
  embedded_count: number;
}

export interface BpmBucketStat {
  label: string;
  track_count: number;
}

export interface SourceStat {
  source: string;
  track_count: number;
  embedded_count: number;
}

export interface KeyStat {
  camelot_key: string | null;
  track_count: number;
}

export interface CatalogAnalytics {
  total_tracks: number;
  total_embedded: number;
  total_artists: number;
  total_local: number;
  total_itunes: number;
  local_taste_count: number;
  genres: GenreStat[];
  bpm_buckets: BpmBucketStat[];
  sources: SourceStat[];
  top_keys: KeyStat[];
}

export interface DashboardResponse {
  stats: {
    seeds: {
      total: number;
      pending: number;
      fetched: number;
      failed: number;
      electronic: number;
      general: number;
    };
    tracks: { total: number; embedded: number; heard: number };
    sets: { total: number };
  };
  analytics: CatalogAnalytics;
  recent_tracks: Track[];
}

export interface CatalogStatsResponse {
  seeds: {
    total: number;
    pending: number;
    fetched: number;
    failed: number;
    electronic: number;
    general: number;
  };
  tracks: { total: number; embedded: number };
  sets: { total: number };
}

export interface GenrePreset {
  label: string;
  value: string;
}

export interface GenrePresetsResponse {
  electronic: GenrePreset[];
  general: GenrePreset[];
  [key: string]: unknown;
}

export interface SeedPurgeBody {
  status?: string;
  source?: string | null;
  category?: string | null;
  exclude_sources?: string[];
}

export interface DigResponse {
  matches: Match[];
  seed: Track;
}

export interface VibeSearchResponse {
  query: string;
  matches: Match[];
}

export interface FilterCatalogResponse {
  tracks: Track[];
}

export interface SearchTracksResponse {
  tracks: Track[];
  query: string;
}

export interface RecentTracksResponse {
  tracks: Track[];
}

export interface HeardToggleResponse {
  id: string;
  is_heard: boolean;
}

export interface ResetEmbeddingsResponse {
  cleared: number;
}

export interface DownloadTrackResponse extends Track {}

// ------------------------------------------------------------------ library

export interface ArtistSummary {
  artist: string;
  track_count: number;
  embedded_count: number;
  genres: string[];
  sources: string[];
  sample_track_id: string;
  sample_track_title: string;
  year_min: number | null;
  year_max: number | null;
  taste_match_percent: number | null;
  artwork_url: string | null;
  is_liked: boolean;
}

export interface ArtistsSummaryResponse {
  artists: ArtistSummary[];
  total: number;
}

export interface ArtistTracksResponse {
  artist: string;
  tracks: Track[];
}

export interface BlacklistEntry {
  id: number;
  kind: string;
  normalized_key: string;
  display_name: string;
  artist_name: string | null;
  track_title: string | null;
  reason: string | null;
  created_at: string;
}

export interface BlacklistResponse {
  entries: BlacklistEntry[];
  total: number;
}

export interface Seed {
  name: string;
  category: string;
  status: string;
  source: string | null;
  priority_score: number;
  external_id: string | null;
}

export interface SeedSourceStat {
  source: string;
  total: number;
  pending: number;
  fetched: number;
  failed: number;
}

export interface SeedBreakdown {
  total: number;
  pending: number;
  fetched: number;
  failed: number;
  by_source: SeedSourceStat[];
}

export interface SeedsResponse {
  seeds: Seed[];
  total: number;
  breakdown: SeedBreakdown;
}

export interface LikedArtist {
  artist_name: string;
  normalized_key: string;
  created_at: string;
}

export interface LikedArtistsResponse {
  liked_artists: LikedArtist[];
  total: number;
}

export interface SimilarArtist {
  artist: string;
  similarity_percent: number;
  track_count: number;
  embedded_count: number;
  genres: string[];
  bpm_min: number | null;
  bpm_max: number | null;
  year_min: number | null;
  year_max: number | null;
  is_liked: boolean;
}

export interface SimilarArtistsResponse {
  seed_artists: string[];
  seed_tracks_used: number;
  items: SimilarArtist[];
}

export interface BulkDeleteArtistsResponse {
  artists_requested: number;
  artists_deleted: number;
  tracks_deleted: number;
  seeds_removed: number;
  blacklisted_count: number;
  skipped_protected: number;
}

export interface BulkCleanupPreviewResponse {
  artist_count: number;
  track_count: number;
  sample_artists: ArtistSummary[];
}

export interface BulkCleanupExecuteResponse extends BulkDeleteArtistsResponse {}

export interface DeleteTrackResponse {
  success: boolean;
  track_id: string;
  blacklisted: boolean;
}

export interface DeleteArtistResponse {
  success: boolean;
  artist: string;
  tracks_deleted: number;
  seed_removed: boolean;
  blacklisted: boolean;
}

// -------------------------------------------------------------------- sets

export interface SetSummaryPayload {
  id: string;
  title: string;
  artist: string;
  source_url: string | null;
  duration_seconds: number | null;
  thumbnail_url: string | null;
  bpm_min: number | null;
  bpm_max: number | null;
  passage_count: number;
}

export interface SetsListResponse {
  sets: SetSummaryPayload[];
}

export interface PassagePayload {
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  bpm: number | null;
  key: string | null;
  exact_id_match: boolean;
  exact_id_title: string | null;
  exact_id_artist: string | null;
  exact_id_source: string | null;
  exact_id_display_name: string | null;
  matches: Match[];
}

export interface SetDetailResponse {
  set: SetSummaryPayload;
  view: string;
  passages?: PassagePayload[];
  matches?: Match[];
  sets?: { set: SetSummaryPayload; similarity: number }[];
}

// ---------------------------------------------------------------- set helper

export interface TransitionEvaluation {
  score: number;
  harmonic_score: number;
  bpm_score: number;
  audio_score: number;
  camelot_move: string | null;
  bpm_delta: number | null;
}

export interface NextTrackSuggestion {
  track: Track;
  evaluation: TransitionEvaluation;
}

export interface SuggestNextResponse {
  from_track_id: string;
  suggestions: NextTrackSuggestion[];
}

export interface BridgeSuggestion {
  bridge_track: Track;
  eval_from_a: TransitionEvaluation;
  eval_to_b: TransitionEvaluation;
  combined_score: number;
}

export interface BridgeResponse {
  track_a_id: string;
  track_b_id: string;
  bridges: BridgeSuggestion[];
}

export interface AutoSequenceResponse {
  ordered_track_ids: string[];
  average_score: number;
}

export interface EvaluateSequenceResponse {
  transitions: TransitionEvaluation[];
}

export interface PlannedSet {
  id: number;
  name: string;
  track_ids: string[];
  track_count: number;
  created_at: string;
  updated_at: string;
  tracks?: Track[];
}

// ---------------------------------------------------------------- hardware

export interface HardwareResponse {
  torch_version: string | null;
  cuda_available: boolean;
  cuda_version: string | null;
  gpu_name: string | null;
  vram_total_mb: number | null;
  vram_free_mb: number | null;
  ram_total_mb: number | null;
  ram_free_mb: number | null;
  ffmpeg_path: string | null;
  ffmpeg_version: string | null;
  gpu_ready: boolean;
  has_ffmpeg: boolean;
}

// -------------------------------------------------------------------- jobs

export type JobKind =
  | "index"
  | "seed-crawl"
  | "seed-llm"
  | "fetch-metadata"
  | "analyze-set"
  | "seed-itunes"
  | "import-local"
  | "fetch-artist"
  | "download-tracks";

export interface JobSnapshot {
  kind: string;
  params: Record<string, unknown>;
  status: "idle" | "running" | "done" | "error" | "cancelled";
  started_at: number | null;
  finished_at: number | null;
  stage: string;
  message: string;
  processed: number;
  failed: number;
  total: number | null;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface JobStartResponse {
  job: JobSnapshot;
}

export interface JobCurrentResponse {
  job: JobSnapshot | null;
  active: boolean;
}

export interface JobCancelResponse {
  cancelled: boolean;
}

export type JobEvent =
  | { type: "state"; job: JobSnapshot | null }
  | { type: "progress"; job: JobSnapshot; speed?: number; memory?: Record<string, number> | null }
  | { type: "done"; job: JobSnapshot; result?: Record<string, unknown> | null; message?: string | null }
  | { type: "error"; job: JobSnapshot; result?: null; message?: string | null }
  | { type: "cancelled"; job: JobSnapshot; result?: null; message?: string | null };
