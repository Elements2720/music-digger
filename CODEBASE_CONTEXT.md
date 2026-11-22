# DigDeeper Local — Codebase Context (Phase 3)

> **Generated**: 2026-11-21 · **Purpose**: Exhaustive technical handoff for an AI architect to understand the entire current implementation without reading every file.

---

## 1. Project Tree & Stack

### 1.1 Source Tree

```
backend/
  pyproject.toml
  src/
    container.py                                  # Composition Root
    domain/
      _validation.py                              # Pure validation helpers (stdlib only)
      __init__.py
      entities/
        __init__.py
        track.py                                  # Track, SeedArtist, AudioBuffer, TrackReference, TrackVibe
        dj_set.py                                 # TrackMatch, Passage, DJSet
        search.py                                 # SearchFilter
      value_objects/
        __init__.py
        audio_features.py                         # BPM, CamelotKey, TimeRange, EmbeddingVector, AudioFeatures
        hardware.py                               # HardwareInfo
      interfaces/
        __init__.py
        audio_engine.py                           # IAudioDecoder, IFeatureExtractor, IAudioEmbedder, IAudioSegmenter, IFingerprinter, ISetDownloader
        catalog.py                                # ICatalogProvider, ISeedDiscovery, ISeedCrawler
        hardware.py                               # IHardwareProbe
        llm.py                                    # ILLMService
        repositories.py                           # ITrackRepository, ISetRepository, ISeedRepository
      use_cases/
        __init__.py
        build_seed_list.py                        # BuildSeedList
        dig_similar_tracks.py                     # DigSimilarTracks
        fetch_catalog_metadata.py                 # FetchCatalogMetadata
        index_catalog.py                          # IndexCatalog
    data/
      __init__.py
      errors.py                                   # DataLayerError hierarchy
      normalization.py                            # normalize_text, normalize_artist_title, normalize_seed_name
      datasources/
        __init__.py
        local/
          __init__.py
          sqlite_client.py                        # SQLiteClient + SCHEMA DDL
          lancedb_client.py                       # LanceDBClient + VectorMatch
        remote/
          __init__.py
          artist_parser.py                        # parse_collaborators()
          deezer_seed_crawler.py                  # DeezerSeedCrawler (ISeedDiscovery + ISeedCrawler)
          itunes_provider.py                      # ITunesProvider (ICatalogProvider)
          rate_limiter.py                         # AsyncTokenBucket, exponential_backoff, retry_after_seconds
      llm/
        __init__.py
        multi_llm_client.py                       # MultiLLMClient (ILLMService)
      ml/
        __init__.py
        clap_embedder.py                          # ClapAudioEmbedder (IAudioEmbedder)
        ffmpeg_decoder.py                         # FFmpegAudioDecoder (IAudioDecoder)
        hardware_probe.py                         # HardwareProbe (IHardwareProbe)
        librosa_analyzer.py                       # LibrosaFeatureExtractor (IFeatureExtractor) + analyze_pcm
      mappers/
        __init__.py
        seed_mapper.py                            # seed_to_row / row_to_seed
        track_mapper.py                           # track_to_row / row_to_track / track_to_vector_row
      repositories/
        __init__.py
        seed_repository.py                        # SQLiteSeedRepository (ISeedRepository)
        track_repository.py                       # HybridTrackRepository (ITrackRepository)
    presentation/
      __init__.py
      cli/
        __init__.py
        __main__.py                               # python -m presentation.cli
        commands.py                               # Typer `dig` app
      api/
        __init__.py                               # (placeholder for later phase)
        routers/__init__.py
        schemas/__init__.py
  tests/
    domain/
      test_domain_purity.py                       # AST import scan
      test_bpm.py
      test_camelot_key.py
      test_time_range.py
      test_embedding_vector.py
      test_audio_features.py
      test_track_entities.py
      test_dj_set_entities.py
      test_search_filter.py
      test_dig_similar_tracks.py
      test_index_catalog.py
      test_interfaces.py
      test_use_cases.py
    data/
      conftest.py
      fakes.py                                    # Shared test doubles
      test_artist_parser.py
      test_clap_embedder.py
      test_deezer_crawler.py
      test_ffmpeg_decoder.py
      test_hardware_probe.py
      test_itunes_provider.py
      test_librosa_analyzer.py
      test_llm_client.py
      test_rate_limiter.py
      test_sqlite_seed_repository.py
      test_track_repository.py
```

### 1.2 Python Version & Key Dependencies

| Item | Spec |
|---|---|
| **Python** | `>= 3.11` |
| **Build** | `setuptools >= 68`, `package-dir = {"" = "src"}` |
| **Entry point** | `dig = presentation.cli.commands:main` |
| **torch source** | CUDA wheels from `https://download.pytorch.org/whl/cu124` via `[tool.uv.sources]` |

**Runtime dependencies**:

| Package | Version |
|---|---|
| `aiosqlite` | >= 0.22.1 |
| `httpx` | >= 0.28.1 |
| `lancedb` | >= 0.41.0 |
| `librosa` | >= 0.11.0 |
| `numpy` | >= 1.26 |
| `pyarrow` | >= 26.0.1 |
| `pylance` | >= 14.0.3 |
| `python-dotenv` | >= 1.2.4 |
| `rich` | >= 15.0.0 |
| `torch` | >= 2.6.0 (CUDA 12.4 wheels) |
| `transformers` | >= 4.45 |
| `typer` | >= 0.29.2 |

**Dev dependencies**: `pytest >= 8.0, < 9`, `pytest-asyncio >= 1.5.0`

**pytest config**: `pythonpath = ["src"]`, `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `addopts = ["-ra", "--strict-markers", "--strict-config"]`

### 1.3 Environment Variables (`.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `DEVICE` | `cuda` | torch device |
| `DEVICE_FP16` | `true` | Enable FP16 inference |
| `STORAGE_DIR` | `./storage` | Relative to repo root |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI-compatible endpoint |
| `LLM_API_KEY` | `local` | Bearer token |
| `LLM_FAST_MODEL` | `qwen2.5:7b-instruct` | Model for seed/vibe/tracklist |
| `LLM_AUDIO_MODEL` | `qwen2-audio:7b` | (Future) audio model |
| `CLAP_MODEL_ID` | `laion/clap-htsat-unfused` | HuggingFace model id (do NOT use `laion/larger_clap_music` — untrained audio tower) |
| `CLAP_BATCH_SIZE` | `16` | Micro-batch size (clamped to 32) |
| `CLAP_MAX_VRAM_GB` | `4.0` | VRAM budget |
| `ANALYSIS_MAX_WORKERS` | `4` | ProcessPoolExecutor workers (ceiling 6) |
| `PREVIEW_SECONDS` | `30` | Preview length |
| `TARGET_SAMPLE_RATE` | `48000` | PCM sample rate |
| `PREVIEW_CONCURRENCY` | `16` | Download semaphore (ceiling 16) |
| `PREVIEW_TIMEOUT_SECONDS` | `30` | HTTP download timeout |
| `FFMPEG_TIMEOUT_SECONDS` | `60` | Per-subprocess timeout |
| `INDEX_QUEUE_MAXSIZE` | `64` | asyncio.Queue bound between decode and embed |
| `ITUNES_RATE_LIMIT_PER_MINUTE` | `18` | Hard ceiling ≤ 18 |
| `ITUNES_COUNTRY` | `US` | Storefront |
| `ITUNES_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `DEEZER_RATE_LIMIT_PER_SEC` | `8` | Hard ceiling ≤ 8 |
| `DEEZER_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `SEED_CRAWL_MAX_DEPTH` | `2` | BFS depth for related artists |
| `CATALOG_ELECTRONIC_RATIO` | `0.75` | Target 75 / 25 split |
| `LLM_TIMEOUT_SECONDS` | `120` | Chat-completions timeout |
| `SQLITE_PATH` | `./storage/app.db` | Database file |
| `LANCEDB_PATH` | `./storage/lancedb` | Vector directory |

---

## 2. Domain Layer Contracts

### 2.1 Validation Helpers (`domain/_validation.py`)

| Function | Signature | Behavior |
|---|---|---|
| `require_str` | `(value, field, *, allow_empty=False) → str` | Strip, reject non-str / empty |
| `optional_str` | `(value \| None, field) → str \| None` | None pass-through, else require_str |
| `require_float` | `(value, field) → float` | Reject bool/non-numeric/non-finite |
| `require_int` | `(value, field) → int` | Reject bool |
| `require_bool` | `(value, field) → bool` | Strict bool |
| `freeze_tuple` | `(value, field, expected_type=None) → tuple[T, ...]` | Freeze iterable, optional type check |

### 2.2 Value Objects (`domain/value_objects/`)

#### `BPM` (frozen, slotted, ordered)
| Field | Type | Constraint |
|---|---|---|
| `value` | `float` | 40.0 ≤ value ≤ 220.0 |

Methods: `bpm` (property alias), `is_close_to(other, tolerance=1.0) → bool`

#### `CamelotKey` (frozen, slotted)
| Field | Type | Constraint |
|---|---|---|
| `notation` | `str` | Regex `^[1-9]|1[0-2][AB]$`, uppercased + stripped |

Properties: `number → int`, `letter → str`, `value → str`, `key → str`
Methods: `is_harmonic_compatible(other) → bool` — same key, same number (relative major/minor), ±1 on same side with 12↔1 wrap.

#### `TimeRange` (frozen, slotted, ordered)
| Field | Type | Constraint |
|---|---|---|
| `start_seconds` | `float` | ≥ 0 |
| `end_seconds` | `float` | > start_seconds |

Properties: `duration_seconds`. Methods: `contains(seconds) → bool`, `overlaps(other) → bool`

#### `EmbeddingVector` (frozen, slotted)
| Field | Type | Constraint |
|---|---|---|
| `values` | `tuple[float, ...]` | Non-empty, all finite |
| `dimension` | `int \| None` | Inferred from values if omitted; must match if supplied |

Methods: `from_sequence(cls, values, *, expected_dimension=None)`, `validate_dimension(expected)`, `cosine_similarity(other) → float` (pure-Python `[-1.0, 1.0]`), `__len__`

#### `AudioFeatures` (frozen, slotted)
| Field | Type |
|---|---|
| `bpm` | `BPM \| None` |
| `key` | `CamelotKey \| None` |

#### `HardwareInfo` (frozen, slotted)
| Field | Type |
|---|---|
| `torch_version` | `str \| None` |
| `cuda_available` | `bool` (default False) |
| `cuda_version` | `str \| None` |
| `gpu_name` | `str \| None` |
| `vram_total_mb` | `int \| None` |
| `vram_free_mb` | `int \| None` |
| `ram_total_mb` | `int \| None` |
| `ram_free_mb` | `int \| None` |
| `ffmpeg_path` | `str \| None` |
| `ffmpeg_version` | `str \| None` |

Properties: `has_ffmpeg`, `gpu_ready`. Methods: `vram_summary() → str`, `ram_summary() → str`

### 2.3 Entities (`domain/entities/`)

#### `Track` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `id` | `str` | *required* |
| `title` | `str` | *required* |
| `artist` | `str` | *required* |
| `duration_seconds` | `float \| None` | `None` |
| `bpm` | `BPM \| None` | `None` (auto-wraps raw float) |
| `key` | `CamelotKey \| None` | `None` (auto-wraps raw string) |
| `genre` | `str \| None` | `None` |
| `release_year` | `int \| None` | `None` (1900–2100) |
| `isrc` | `str \| None` | `None` |
| `preview_url` | `str \| None` | `None` |
| `artwork_url` | `str \| None` | `None` |
| `album` | `str \| None` | `None` |
| `store_url` | `str \| None` | `None` |
| `source` | `str` | `"unknown"` |
| `external_id` | `str \| None` | `None` |
| `embedding` | `EmbeddingVector \| None` | `None` |

Properties: `track_id`, `duration`, `display_name`. Methods: `with_embedding(EmbeddingVector) → Track`

#### `SeedArtist` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `name` | `str` | *required* |
| `priority_score` | `float` | *required* (0.0–1.0) |
| `category` | `Literal["electronic", "general"]` | *required* |
| `status` | `Literal["pending", "fetched", "failed"]` | `"pending"` |
| `source` | `str` | `"llm"` |
| `external_id` | `str \| None` | `None` |

Properties: `is_pending`. Methods: `with_status(status) → SeedArtist`

#### `AudioBuffer` (frozen, slotted)
| Field | Type | Constraint |
|---|---|---|
| `pcm_bytes` | `bytes` | Non-empty; accepts bytearray/memoryview |
| `sample_rate` | `int` | > 0 |

Properties: `size_bytes`

#### `TrackReference` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `artist` | `str` | *required* |
| `title` | `str` | *required* |
| `timestamp` | `TimeRange \| None` | `None` |
| `confidence` | `float` | `1.0` (0.0–1.0) |

#### `TrackVibe` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `tags` | `tuple[str, ...]` | *required* (deduplicated case-fold) |
| `mood` | `str` | *required* |
| `energy` | `float` | *required* (0.0–1.0) |
| `description` | `str` | `""` |

#### `TrackMatch` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `track` | `Track` | *required* |
| `similarity_score` | `float` | *required* (-1.0 to 1.0) |
| `is_exact_id` | `bool` | `False` |

Property: `similarity_percent → int` — `max(0, min(1, score)) * 100`, rounded.

#### `Passage` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `time_range` | `TimeRange` | *required* |
| `bpm` | `BPM \| None` | `None` |
| `key` | `CamelotKey \| None` | `None` |
| `exact_id_match` | `bool` | `False` |
| `closest_matches` | `tuple[TrackMatch, ...]` | `()` (auto-sorted descending) |

Properties: `best_match`, `exact_match`

#### `DJSet` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `id` | `str` | *required* |
| `title` | `str` | *required* |
| `source_url` | `str \| None` | `None` |
| `passages` | `tuple[Passage, ...]` | `()` |
| `duration_seconds` | `float \| None` | `None` (validates passages fit within) |

Properties: `set_id`, `passage_count`. Methods: `ordered_passages()`, `passage_at(seconds)`, `with_passage(Passage)`

#### `SearchFilter` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `bpm_min` | `float \| None` | `None` |
| `bpm_max` | `float \| None` | `None` |
| `camelot_keys` | `tuple[CamelotKey, ...]` | `()` (deduplicated) |
| `exclude_heard` | `bool` | `False` |
| `genre_filter` | `str \| None` | `None` |
| `limit` | `int` | `50` (1–500) |

Methods: `matches(track, heard_ids=frozenset()) → bool` — applies all constraints.

### 2.4 Interfaces (`domain/interfaces/`)

#### `IAudioDecoder` (ABC)
```python
async def decode(self, source: BinaryIO, *, sample_rate=48000, channels=1) -> AudioBuffer
async def decode_url(self, url: str, *, sample_rate=48000, channels=1) -> AudioBuffer
async def decode_segment(self, path: Path, time_range: TimeRange, *, sample_rate=48000, channels=1) -> AudioBuffer
```

#### `IFeatureExtractor` (ABC)
```python
def extract(self, audio: AudioBuffer) -> AudioFeatures
```

#### `IAudioEmbedder` (ABC)
```python
@property model_id -> str
@property embedding_dimension -> int
def embed(self, audio: AudioBuffer) -> EmbeddingVector
def embed_batch(self, audios: Sequence[AudioBuffer]) -> Sequence[EmbeddingVector]
def embed_text(self, query: str) -> EmbeddingVector  # default raises NotImplementedError
```

#### `IAudioSegmenter` (ABC)
```python
def plan_segments(self, total_duration_seconds: float, *, window_seconds=30.0, hop_seconds=15.0) -> Sequence[TimeRange]
```

#### `IFingerprinter` (ABC)
```python
def compute(self, audio: AudioBuffer) -> str
def identify(self, audio: AudioBuffer) -> Track | None
```

#### `ISetDownloader` (ABC)
```python
async def download(self, url: str, destination: Path) -> Path
```

#### `ICatalogProvider` (ABC)
```python
@property provider_id -> str
async def search_tracks(self, query: str, *, limit=25) -> Sequence[Track]
async def lookup_track(self, provider_track_id: str) -> Track | None
async def list_artist_tracks(self, artist_name: str, *, limit=50) -> Sequence[Track]
async def fetch_preview(self, track: Track) -> bytes | None
```

#### `ISeedDiscovery` (ABC)
```python
async def discover(self, *, electronic_limit=1000, general_limit=300, max_depth=2) -> Sequence[SeedArtist]
```

#### `ISeedCrawler` (ABC)
```python
def crawl(self, seeds: Sequence[SeedArtist], *, tracks_per_artist=50) -> AsyncIterator[Track]
```

#### `IHardwareProbe` (ABC)
```python
def probe(self) -> HardwareInfo
```

#### `ILLMService` (ABC)
```python
async def extract_tracklist_from_comments(self, comments: Sequence[str], *, context: str | None = None) -> Sequence[TrackReference]
async def generate_seed_artists(self, *, genres: Sequence[str], count=25, exclude_artists: Sequence[str] = ()) -> Sequence[SeedArtist]
async def tag_track_vibe(self, track: Track) -> TrackVibe
```

#### `ITrackRepository` (ABC)
```python
async def upsert_many(self, tracks: Sequence[Track]) -> int
async def get_by_id(self, track_id: str) -> Track | None
async def get_by_external_id(self, source: str, external_id: str) -> Track | None
async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]
async def find_similar(self, embedding: EmbeddingVector, search_filter: SearchFilter) -> Sequence[TrackMatch]
async def find_by_filter(self, search_filter: SearchFilter) -> Sequence[Track]
async def mark_heard(self, track_id: str) -> None
async def get_heard_ids(self) -> frozenset[str]
async def count(self) -> int
async def count_embedded(self) -> int
async def list_unembedded(self, limit=100, *, max_failures=3) -> Sequence[Track]
async def list_embedded(self, limit=20, *, offset=0) -> Sequence[Track]
async def mark_index_failed(self, track_id: str) -> None
```

#### `ISetRepository` (ABC)
```python
async def save(self, dj_set: DJSet) -> None
async def get_by_id(self, set_id: str) -> DJSet | None
async def list_all(self, limit=20) -> Sequence[DJSet]
async def delete(self, set_id: str) -> bool
async def count(self) -> int
```

#### `ISeedRepository` (ABC)
```python
async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int
async def record_discovery(self, seeds: Sequence[SeedArtist], *, priority_increment=0.05) -> int
async def get_by_name(self, name: str) -> SeedArtist | None
async def list_by_status(self, status: SeedStatus, limit=100) -> Sequence[SeedArtist]
async def update_status(self, name: str, status: SeedStatus) -> None
async def count_by_category(self, category: str) -> int
async def count_by_status(self, status: SeedStatus) -> int
async def count(self) -> int
```

### 2.5 Use Cases (`domain/use_cases/`)

#### `BuildSeedList`
- **Dependencies**: `ISeedDiscovery | None`, `ISeedRepository`, `ILLMService | None`
- **Entry**: `async execute(*, electronic_limit=1000, general_limit=300, max_depth=2, use_deezer=True, llm_genres=(), llm_count=0, exclude_artists=()) → BuildSeedListResult`
- **Flow**: Optionally runs Deezer BFS discovery → persists via `record_discovery` (priority bump on rediscovery). Optionally asks LLM for seeds → persists via `upsert_many`. Returns counts.
- **Result**: `BuildSeedListResult(discovered, llm_generated, written, electronic_total, general_total)`

#### `DigSimilarTracks`
- **Dependencies**: `ITrackRepository`
- **Entry**: `async execute(track_id, search_filter=None, *, bpm_tolerance=None, harmonic=False) → DigResult`
- **Flow**: Loads reference by id → validates embedding exists → builds effective filter (intersects BPM tolerance window, expands Camelot keys if harmonic) → over-fetches by 1 from vector index → strips reference id → trims to limit.
- **Errors**: `TrackNotFoundError`, `TrackNotEmbeddedError`
- **Result**: `DigResult(reference: Track, matches: tuple[TrackMatch, ...])`

#### `FetchCatalogMetadata`
- **Dependencies**: `ISeedRepository`, `ICatalogProvider`, `ITrackRepository`
- **Entry**: `async execute(*, artists_limit=50, tracks_per_artist=50, retry_failed=False, progress=None) → FetchMetadataResult`
- **Flow**: Selects pending (optionally failed) seeds by priority → for each calls `list_artist_tracks` → `upsert_many` tracks → marks seed fetched/failed. Resumable: failures don't abort the batch.
- **Result**: `FetchMetadataResult(artists_processed, artists_failed, artists_skipped, tracks_found, tracks_saved)`

#### `IndexCatalog`
- **Dependencies**: `ITrackRepository`, `IAudioDecoder`, `IFeatureExtractor`, `IAudioEmbedder`, `Executor | None`, `cpu_workers=4`, `queue_maxsize=64`, `chunk_size=32`
- **Entry**: `async execute(*, limit=500, batch_size=16, max_failures=3, progress=None) → IndexResult`
- **Flow**: Bounded producer-consumer. Producers download+decode previews via `decode_url(sample_rate=48000, channels=1)` → enqueue to bounded `asyncio.Queue`. Consumer drains queue → runs `extract()` on `ProcessPoolExecutor` → accumulates batch → calls `embed_batch()` via `asyncio.to_thread` → `upsert_many` hydrated tracks. PCM released immediately per batch. Failed tracks marked via `mark_index_failed`. Resumable across runs (skips already-embedded).
- **Constants**: `_MAX_BATCH_SIZE=32`, `_DEFAULT_QUEUE_MAXSIZE=64`, `_DEFAULT_CHUNK_SIZE=32`
- **Result**: `IndexResult(processed, failed, embedded_total)`

---

## 3. Data Layer & Schemas

### 3.1 SQLite (`sqlite_client.py`)

**Connection setup**: WAL mode, `foreign_keys=ON`, `busy_timeout=5000`, `synchronous=NORMAL`. Single `aiosqlite.Connection` guarded by `asyncio.Lock`. Row factory = `aiosqlite.Row`.

**Migration**: Before running the SCHEMA script, `_migrate()` checks `PRAGMA table_info(tracks)` and adds missing columns (`source TEXT NOT NULL DEFAULT 'itunes'`, `external_id TEXT`, `index_failures INTEGER NOT NULL DEFAULT 0`).

#### Table `seed_artists`

| Column | Type | Constraints |
|---|---|---|
| `id` | `INTEGER` | PK AUTOINCREMENT |
| `name` | `TEXT NOT NULL` | |
| `name_normalized` | `TEXT NOT NULL` | UNIQUE |
| `deezer_id` | `TEXT` | UNIQUE WHERE NOT NULL |
| `priority_score` | `REAL NOT NULL DEFAULT 0.0` | CHECK 0.0–1.0 |
| `category` | `TEXT NOT NULL` | CHECK IN ('electronic', 'general') |
| `status` | `TEXT NOT NULL DEFAULT 'pending'` | CHECK IN ('pending', 'fetched', 'failed') |
| `source` | `TEXT NOT NULL DEFAULT 'unknown'` | |
| `created_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |
| `updated_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |

**Indexes**: `idx_seed_artists_deezer_id` (unique, partial WHERE NOT NULL), `idx_seed_artists_status_priority` (status, priority_score DESC).

#### Table `tracks`

| Column | Type | Constraints |
|---|---|---|
| `id` | `TEXT` | PK |
| `itunes_track_id` | `TEXT` | UNIQUE |
| `title` | `TEXT NOT NULL` | |
| `artist` | `TEXT NOT NULL` | |
| `normalized_key` | `TEXT NOT NULL` | UNIQUE |
| `album` | `TEXT` | |
| `genre` | `TEXT` | |
| `duration_sec` | `REAL` | |
| `release_year` | `INTEGER` | |
| `preview_url` | `TEXT` | |
| `artwork_url` | `TEXT` | |
| `store_url` | `TEXT` | |
| `bpm` | `REAL` | |
| `camelot_key` | `TEXT` | |
| `is_embedded` | `INTEGER NOT NULL DEFAULT 0` | CHECK IN (0, 1) |
| `is_heard` | `INTEGER NOT NULL DEFAULT 0` | CHECK IN (0, 1) |
| `index_failures` | `INTEGER NOT NULL DEFAULT 0` | |
| `source` | `TEXT NOT NULL DEFAULT 'itunes'` | |
| `external_id` | `TEXT` | |
| `isrc` | `TEXT` | |
| `created_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |
| `updated_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |

**Indexes**: `idx_tracks_external_id` (source, external_id), `idx_tracks_bpm` (bpm), `idx_tracks_genre` (genre), `idx_tracks_heard` (is_heard).

**Upsert logic**: `ON CONFLICT(id) DO UPDATE SET ...`, notably `is_embedded = MAX(tracks.is_embedded, excluded.is_embedded)` and `is_heard = MAX(tracks.is_heard, excluded.is_heard)` — once heard/embedded, always heard/embedded.

**Deduplication**: Before upsert, `_find_existing_id` checks `normalized_key` or `itunes_track_id` match; if found under a different `id`, the existing id is reused.

#### Table `dj_sets`

| Column | Type | Constraints |
|---|---|---|
| `id` | `TEXT` | PK |
| `title` | `TEXT NOT NULL` | |
| `source_url` | `TEXT` | |
| `duration_sec` | `REAL` | |
| `created_at` / `updated_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |

#### Table `set_passages`

| Column | Type | Constraints |
|---|---|---|
| `id` | `INTEGER` | PK AUTOINCREMENT |
| `set_id` | `TEXT NOT NULL` | FK → dj_sets(id) ON DELETE CASCADE |
| `start_sec` | `REAL NOT NULL` | |
| `end_sec` | `REAL NOT NULL` | |
| `bpm` | `REAL` | |
| `camelot_key` | `TEXT` | |
| `exact_id_match` | `INTEGER NOT NULL DEFAULT 0` | CHECK IN (0, 1) |
| `closest_matches_json` | `TEXT NOT NULL DEFAULT '[]'` | |
| UNIQUE(set_id, start_sec, end_sec) | | |

**Index**: `idx_set_passages_set_id` (set_id, start_sec).

### 3.2 LanceDB (`lancedb_client.py`)

**Table name**: `track_vectors` (configurable). **Storage**: disk-backed directory at `LANCEDB_PATH`.

#### Schema (PyArrow)

| Column | Arrow Type | Purpose |
|---|---|---|
| `id` | `pa.string()` | Matches SQLite `tracks.id` |
| `bpm` | `pa.float32()` | Copied for filter push-down |
| `camelot_key` | `pa.string()` | Copied for filter push-down |
| `genre` | `pa.string()` | Copied for filter push-down |
| `vector` | `pa.list_(pa.float16(), 512)` | CLAP embedding, **float16**, 512 dims |

#### Search

- **Distance metric**: `cosine`
- **Similarity conversion**: `similarity = max(-1.0, min(1.0, 1.0 - _distance))` where `_distance` is cosine distance (0 = identical, 2 = opposite)
- **Filter push-down**: optional `where` clause built by `HybridTrackRepository._vector_where()` with BPM range, Camelot keys IN-list, genre equality, and heard-id exclusion
- **Upsert**: `merge_insert("id").when_matched_update_all().when_not_matched_insert_all()` with fallback to delete+add for older LanceDB versions

#### IVF-PQ Index

- **Threshold**: created automatically when row count > `INDEX_THRESHOLD = 10,000`
- **Configuration**: `IvfPq(distance_type="cosine", num_partitions=max(1, min(256, row_count // 1000)), num_sub_vectors=32)` (or 1 when dimension < 64)
- **Trigger**: called after every `upsert_many`; skips if an index already exists

### 3.3 Remote Providers

#### `ITunesProvider` (implements `ICatalogProvider`)

| Param | Value |
|---|---|
| **API base** | `https://itunes.apple.com` |
| **Search endpoint** | `/search?term=...&entity=song&attribute=artistTerm&limit=200&country={CC}` |
| **Lookup endpoint** | `/lookup?id=...&entity=song&country={CC}` |
| **Search limit** | `ITUNES_SEARCH_LIMIT = 200` per request |
| **Rate limit** | Token bucket at `rate_limit_per_minute / 60.0` tokens/sec, capacity 1 (serialized) |
| **Max retries** | 4 (default), with exponential backoff + `Retry-After` |
| **Retried statuses** | 403, 429, 5xx |
| **Response cache** | In-memory dict keyed by `(query.casefold(), country)`, TTL `cache_ttl_seconds=3600` |
| **Track ID format** | `itunes:{trackId}` |

**Filtering rules** (in `_passes_filters`):
- Must have `preview_url`
- Must have `duration_seconds`
- Duration: 120 ≤ seconds ≤ 900
- Genre not in `NON_MUSIC_GENRES` (podcasts, comedy, audiobooks, children's music, kids, spoken word)

**Deduplication** (in `_filter_and_dedup`):
- By `external_id` (iTunes trackId)
- By `normalize_artist_title(artist, title)` — NFKD case-folded, accent-stripped, punctuation-removed

**Snowball discovery** (`_discover_from_tracks`): Parses collaborators/remixers via `parse_collaborators()`, creates `SeedArtist` entries (source=`itunes-snowball`), persists via `seed_repository.record_discovery()`. Capped at `discovery_limit=100` new seeds per search. Priority: electronic base 0.55, general base 0.35, +0.05 per additional co-occurrence, capped at 0.9.

#### `artist_parser.py` — `parse_collaborators(artist_name, track_title) → tuple[str, ...]`

Extracts names from:
- Bracket remixes: `(Name Remix)`, `[Name Edit]`, `(Name Bootleg)`
- Dash remixes: `- Name Remix`
- Featured: `feat.`, `ft.`, `featuring`, `with` in title
- Artist separators: `, & ; × + | x`

Filters out generic names (`"remix"`, `"original mix"`, `"various artists"`, etc.) and names < 2 or > 80 chars.

#### `DeezerSeedCrawler` (implements `ISeedDiscovery` + `ISeedCrawler`)

| Param | Value |
|---|---|
| **API base** | `https://api.deezer.com` |
| **Rate limit** | 8 req/sec token bucket (capacity=8, burst allowed) |
| **Max retries** | 3 |
| **Retried statuses** | 403, 429, 5xx, Deezer error code 4 |

**Electronic discovery**: BFS from `CORE_ELECTRONIC_ARTISTS` (70 curated names including Solomun, Charlotte de Witte, Boris Brejcha, etc.) via `/artist/{id}/related` (limit=100). Priority decays by depth: `max(0.35, 0.95 - 0.15 * depth)`. Rediscovered artists get +0.05 bump.

**General discovery**: `/chart/{genre_id}/artists` for 5 genres (Pop/132, Hip-Hop/116, Rock/152, Latin/197, Arabic/12), limit=100 each. Priority: `max(0.2, 0.6 - 0.005 * index)`.

**Crawl** (`crawl()` AsyncIterator): For each seed, fetches `/artist/{id}/top?limit=min(100, tracks_per_artist)`, deduplicates by external_id, yields `Track` objects with id=`deezer:{trackId}`.

#### `AsyncTokenBucket` (rate_limiter.py)

- Concurrency-safe (`asyncio.Lock`)
- `acquire(tokens=1.0)` — refills based on elapsed time, waits on deficit
- `exponential_backoff(attempt, *, base_seconds=1.0, factor=2.0, max_seconds=60.0)` — deterministic, no jitter
- `retry_after_seconds(response, default)` — parses `Retry-After` header (numeric or HTTP date)

### 3.4 LLM Client (`multi_llm_client.py`)

**Class**: `MultiLLMClient` implements `ILLMService`

**Endpoint**: `POST {base_url}/chat/completions` (auto-appends if not already in URL)

**Implemented methods**:

| Method | Temperature | response_format | JSON key |
|---|---|---|---|
| `generate_seed_artists` | 0.4 | `json_object` | `"artists"` |
| `extract_tracklist_from_comments` | 0.1 | `json_object` | `"tracks"` |
| `tag_track_vibe` | 0.3 | `json_object` | root object |

**Request handling**:
- Sets `model`, `messages`, `temperature`, `stream: false`, optional `response_format`
- Up to `max_retries=2` with exponential backoff
- If HTTP 400 and `response_format` was set → retries without it (some local servers reject it)
- Retries on 429 and 5xx

**JSON parsing fallbacks** (`_parse_json`):
1. Strip ```json fences via regex
2. Try `json.loads(cleaned)`
3. Find first `{` or `[`, find last `}` or `]`, try parsing substring
4. Raise `LLMError` if all fail

**Content extraction**: `choices[0].message.content` from OpenAI response shape.

### 3.5 ML Engine

#### `FFmpegAudioDecoder` (implements `IAudioDecoder`)

**FFmpeg command** (pipe mode):
```
ffmpeg -hide_banner -loglevel error -i pipe:0 -vn -f f32le -acodec pcm_f32le -ac 1 -ar 48000 pipe:1
```

**Segment mode** (file on disk):
```
ffmpeg -hide_banner -loglevel error -ss {start:.3f} -i {path} -t {duration:.3f} -f f32le -acodec pcm_f32le -ac {channels} -ar {sample_rate} pipe:1
```

| Config | Default |
|---|---|
| Sample rate | 48,000 Hz |
| Channels | 1 (mono) |
| Format | `f32le` (32-bit float little-endian) |
| Download concurrency | Semaphore(16) |
| Download max retries | 2 |
| FFmpeg timeout | 60 s per subprocess |
| Max payload | 32 MiB |

**Download**: Via `httpx.AsyncClient.get()` with follow_redirects. 404 → permanent failure. 429/5xx → transient retry with exponential backoff (capped 8s). Payload size validated.

**PCM post-processing**: Trims trailing partial frames (`len(pcm) % (4 * channels)`), raises if empty.

#### `LibrosaFeatureExtractor` (implements `IFeatureExtractor`)

**Entry**: `extract(audio: AudioBuffer) → AudioFeatures` calls module-level `analyze_pcm()`.

**`analyze_pcm(pcm_bytes, sample_rate, *, tempo_low=70, tempo_high=175, min_duration_seconds=3.0)`**:

1. Converts bytes to `np.float32` array
2. Rejects if fewer than `sample_rate * 3` samples
3. **BPM detection**:
   - `librosa.onset.onset_strength(y=samples, sr=sample_rate)`
   - `librosa.feature.tempo(onset_envelope=..., sr=sample_rate, aggregate=np.median)`
   - Uses default `hop_length` (librosa default = 512)
   - `fold_tempo()`: doubles if < 70, halves if > 175, then clamps to [40, 220]
4. **Key detection** (`_detect_key`):
   - `librosa.feature.chroma_cqt(y=samples, sr=sample_rate)` — Constant-Q chromagram (not STFT)
   - Averages over time axis → 12-bin vector
   - `_detect_key_from_chroma`: correlates (Pearson) all 24 rotations (12 major + 12 minor) against **Krumhansl–Schmuckler profiles**
   - Best root+mode → mapped via `_MAJOR_CAMELOT` / `_MINOR_CAMELOT` lookup tables to Camelot notation (e.g. C major → 8B, A minor → 8A)
5. Returns `AudioFeatures(bpm=BPM|None, key=CamelotKey|None)` — individual failures degrade to None

**librosa/numpy imported lazily inside the function** so parent process stays light. The extractor class is picklable for `ProcessPoolExecutor`.

#### `ClapAudioEmbedder` (implements `IAudioEmbedder`)

**Model**: `laion/clap-htsat-unfused` (512-dim). Loaded via `ClapModel.from_pretrained` + `ClapProcessor.from_pretrained`. Do NOT switch back to `laion/larger_clap_music`: its hub checkpoint ships an untrained audio tower (all audio-side biases zero, projection MLP at random-init), collapsing every embedding to ~0.99 similarity.

**Lazy loading**: Model/processor loaded on first `embed()`/`embed_batch()` call, inside a `threading.Lock`. `torch` and `transformers` are imported inside the lock body.

**Device resolution**: Requests CUDA → checks `torch.cuda.is_available()` → falls back to CPU with warning. Test seam: `cuda_available` constructor param.

**`embed_batch(audios)`**:
1. Converts each `AudioBuffer.pcm_bytes` to `np.float32` array
2. Validates all sample rates are identical
3. Under `torch.inference_mode()`, splits into micro-batches of `self._batch_size` (clamped ≤ 32)
4. Each chunk:
   - `processor(audio=list(chunk), sampling_rate=..., return_tensors="pt", padding=True)` (falls back to `audios=` kwarg)
   - Moves inputs to device
   - If CUDA: `torch.amp.autocast("cuda", dtype=torch.float16)` around `model.get_audio_features(**inputs)`
   - `_extract_projection()`: handles bare Tensor, `BaseModelOutputWithPooling.pooler_output`, or tuple returns; validates shape `(batch, 512)`
   - `torch.nn.functional.normalize(features, p=2, dim=-1)` — L2 normalization
   - Cast to `torch.float16`, move to CPU
   - Convert to `EmbeddingVector(values=tuple(row), dimension=512)`

**`embed_text(query)`**: Similar flow using `model.get_text_features(**inputs)`.

**`model_factory` test seam**: Constructor accepts an optional factory returning an object with `.model` and `.processor`.

#### `HardwareProbe` (implements `IHardwareProbe`)

Lazy-imports torch, calls `torch.cuda.is_available()`, `torch.cuda.get_device_name(0)`, `torch.cuda.mem_get_info(0)`. FFmpeg: `shutil.which()` + `subprocess.run([path, "-version"])` (cached). RAM: `GlobalMemoryStatusEx` on Windows, `/proc/meminfo` on Linux.

---

## 4. Wiring & CLI

### 4.1 Container (`container.py`)

**`Settings.from_env(repo_root=None)`**: Loads `.env` via `python-dotenv`, resolves relative paths from repo root, clamps env values to hard ceilings:

| Setting | Ceiling | Clamp logic |
|---|---|---|
| `itunes_rate_limit_per_minute` | 18 | `max(1, min(18, raw))` |
| `deezer_rate_limit_per_second` | 8.0 | `max(0.1, min(8.0, raw))` |
| `clap_batch_size` | 32 | `max(1, min(32, raw))` |
| `cpu_workers` | 6 | `max(1, min(6, raw))` |
| `preview_concurrency` | 16 | `max(1, min(16, raw))` |

**`Container.start()`** wiring order:
1. `SQLiteClient(sqlite_path)` → `.connect()`
2. `LanceDBClient(lancedb_path)` → `.connect()`
3. `SQLiteSeedRepository(sqlite)`
4. `HybridTrackRepository(sqlite, vectors)`
5. `httpx.AsyncClient` (shared by iTunes, Deezer, LLM, decoder)
6. `ITunesProvider(http_client, seed_repository, country, rate_limit, timeout)`
7. `DeezerSeedCrawler(http_client, rate_limit_per_second, timeout)`
8. `MultiLLMClient(base_url, api_key, model, http_client, timeout)`
9. `FFmpegAudioDecoder(http_client, download_concurrency, timeout, ffmpeg_timeout)`
10. `LibrosaFeatureExtractor()` (default params)
11. `ClapAudioEmbedder(model_id, device, batch_size)`
12. `HardwareProbe()`
13. Use cases wired with their interface dependencies

**`Container.close()`**: HTTP client → LanceDB → SQLite (reverse order).

Supports `async with Container() as c:` context manager.

### 4.2 CLI Commands (`presentation/cli/commands.py`)

All commands use `Typer` + `Rich`. Each wraps an async function and runs it via `asyncio.run()`.

#### `dig check-hw`
No arguments. Probes hardware and prints a Rich table.

#### `dig seed-crawl`
| Flag | Type | Default |
|---|---|---|
| `--electronic-limit` | int (min 0) | 1000 |
| `--general-limit` | int (min 0) | 300 |
| `--max-depth` | int (min 0) | 2 |

#### `dig seed-llm`
| Flag | Type | Default |
|---|---|---|
| `--genre` / `-g` | str | *required* |
| `--count` | int (min 1) | 100 |

Splits `--genre` by commas into a tuple of genre strings.

#### `dig fetch-metadata`
| Flag | Type | Default |
|---|---|---|
| `--artists-limit` | int (min 1) | 50 |
| `--tracks-per-artist` | int (min 1) | 50 |
| `--retry-failed` | bool | False |

Shows a live Rich progress bar during fetching.

#### `dig index`
| Flag | Type | Default |
|---|---|---|
| `--limit` | int (min 0) | 500 |
| `--batch-size` | int (1–32) | 16 |
| `--retry-failed` | bool | False |

`--limit 0` = no cap (translates to `10**9`). `--retry-failed` sets `max_failures=10**9`. Shows live progress bar with speed (tracks/s), failure count, and RAM/VRAM usage.

#### `dig list-tracks`
| Flag | Type | Default |
|---|---|---|
| `--limit` | int (min 1) | 20 |
| `--offset` | int (min 0) | 0 |

Shows embedded tracks (ID, Artist, Title, BPM, Key).

#### `dig dig <track_id>`
| Flag | Type | Default |
|---|---|---|
| `track_id` | str (positional) | *required* |
| `--limit` | int (min 1) | 10 |
| `--bpm-tolerance` | float \| None | None |
| `--harmonic` | bool | False |
| `--genre` | str \| None | None |
| `--exclude-heard` | bool | False |

Constructs `SearchFilter(limit=limit, genre_filter=genre)` and passes `bpm_tolerance` and `harmonic` to `DigSimilarTracks.execute()`. Shows reference track info and Rich table of matches (Title, Artist, Match %, BPM, Key, Genre).

#### `dig stats`
No arguments. Prints seed counts (total, pending, fetched, failed, electronic, general) and track counts (total, embedded).

---

## 5. Current State & Important Implementation Details

### 5.1 Data Error Hierarchy (`data/errors.py`)

```
DataLayerError
├── ProviderError
│   └── ProviderRateLimitError
├── LLMError
├── AudioPipelineError
│   ├── FFmpegNotFoundError
│   ├── PreviewDownloadError
│   └── AudioDecodeError
└── EmbeddingError
```

### 5.2 Normalization (`data/normalization.py`)

`normalize_text(value)`: NFKD decomposition → strip combining characters → casefold → replace non-word chars with spaces → collapse whitespace. Used for:
- `normalize_artist_title(artist, title) → "{normalized_artist}|{normalized_title}"` — dedup key for tracks
- `normalize_seed_name(name) → str` — dedup key for seeds

### 5.3 Repositories

**`HybridTrackRepository`**: Coordinates SQLite (metadata) with LanceDB (vectors). On `upsert_many`, tracks with embeddings are written to both stores. On `get_by_id`, if `is_embedded`, fetches the vector from LanceDB and hydrates the Track. `find_similar` delegates the vector search to LanceDB with filter push-down, then hydrates tracks from SQLite.

**`SQLiteSeedRepository`**: Uses `ON CONFLICT(name_normalized)` for upserts. `record_discovery` bumps priority by `priority_increment` (default 0.05, capped at 1.0) on rediscovery. `list_by_status` orders by `priority_score DESC`.

### 5.4 Known TODOs & Caveats

- **`IAudioSegmenter`, `IFingerprinter`, `ISetDownloader`**: Declared as ABCs in `domain/interfaces/` but have **no concrete implementations yet** — these are Phase 4+ (DJ set analysis).
- **`ISetRepository`**: ABC declared but **no concrete implementation** — Phase 4+.
- **`presentation/api/`**: Empty placeholder package (routers + schemas `__init__.py` only).
- **`LLM_AUDIO_MODEL`**: Defined in `.env.example` but not used anywhere in current code.
- **`DEVICE_FP16`**: Defined in `.env.example` but not read by container/settings — FP16 is always used when CUDA is available via `torch.amp.autocast`.
- **`CLAP_MAX_VRAM_GB`**: Defined in `.env.example` but not enforced in code — batch size clamping is the proxy.
- **`PREVIEW_SECONDS`, `TARGET_SAMPLE_RATE`**: Defined in `.env.example` but hardcoded as `48_000` in `decode_url()` and throughout the pipeline.
- **Match % display**: The `similarity_percent` property on `TrackMatch` computes `round(max(0, min(1, cosine_similarity)) * 100)`. Since LanceDB uses cosine **distance**, the conversion is `1.0 - _distance`. Cosine distance ranges [0, 2], so similarity = `1 - distance` can be negative (for truly anti-correlated vectors, though rare with CLAP embeddings). Negative scores are clamped to 0 by `similarity_percent`.
- **BPM in dig output**: Comes from the SQLite `tracks.bpm` column, which is populated during indexing via `librosa.feature.tempo()` → `fold_tempo()`. BPM is `None` for tracks that haven't been indexed, displayed as "—".
- **Text normalization for dedup**: `normalize_artist_title` uses NFKD + casefold + accent strip + punctuation removal, which means accented characters (e.g., "Âme") collapse correctly.

---

## 6. Critical Source Files (Verbatim)

### 6.1 `backend/src/data/ml/clap_embedder.py`

```python
"""GPU audio embeddings via HuggingFace CLAP (``laion/clap-htsat-unfused``).

The model is **lazy-loaded on first use** so fast CLI commands (``dig stats``,
``dig list-tracks``) never pay the load cost. Inference runs under
``torch.inference_mode()`` with ``torch.amp.autocast("cuda", dtype=float16)``
whenever CUDA is available, vectors are L2-normalized, cast to ``float16`` and
returned as domain :class:`EmbeddingVector` objects. If CUDA is requested but
unavailable (CI, CPU-only machine) the embedder falls back to CPU.

torch and transformers are imported *inside* the load path only: importing
this module must stay cheap.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Any

from domain.entities.track import AudioBuffer
from domain.interfaces.audio_engine import IAudioEmbedder
from domain.value_objects.audio_features import EmbeddingVector

from ..errors import EmbeddingError

LOGGER = logging.getLogger(__name__)

DEFAULT_CLAP_MODEL_ID = "laion/clap-htsat-unfused"
CLAP_EMBEDDING_DIMENSION = 512
CLAP_SAMPLE_RATE = 48_000
MAX_BATCH_SIZE = 32


class ClapAudioEmbedder(IAudioEmbedder):
    """Bounded, FP16, L2-normalized CLAP audio embedder."""

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_CLAP_MODEL_ID,
        device: str = "cuda",
        batch_size: int = 16,
        embedding_dimension: int = CLAP_EMBEDDING_DIMENSION,
        model_factory: Any | None = None,
        cuda_available: bool | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._model_id = model_id
        self._requested_device = device
        self._batch_size = min(batch_size, MAX_BATCH_SIZE)
        self._embedding_dimension = embedding_dimension
        self._model_factory = model_factory
        # Test seam: None defers to torch.cuda.is_available() at load time.
        self._cuda_available = cuda_available
        self._lock = threading.Lock()
        self._torch: Any | None = None
        self._model: Any | None = None
        self._processor: Any | None = None
        self._device: Any | None = None

    # ------------------------------------------------------------- properties

    @property
    def model_id(self) -> str:
        """Hugging Face model identifier."""
        return self._model_id

    @property
    def embedding_dimension(self) -> int:
        """Width of the returned vectors (512 for CLAP)."""
        return self._embedding_dimension

    @property
    def resolved_device(self) -> Any | None:
        """The torch device picked at load time, or ``None`` before loading."""
        return self._device

    @property
    def batch_size(self) -> int:
        """Configured micro-batch size, clamped to the hard cap of 32."""
        return self._batch_size

    # ----------------------------------------------------------------- public

    def embed(self, audio: AudioBuffer) -> EmbeddingVector:
        """Embed one audio window."""
        return self.embed_batch([audio])[0]

    def embed_batch(self, audios: Sequence[AudioBuffer]) -> Sequence[EmbeddingVector]:
        """Embed a batch, splitting it into GPU-sized micro-batches."""
        if not audios:
            return ()
        torch, model, processor, device = self._ensure_loaded()
        import numpy as np

        waveforms = [
            np.frombuffer(audio.pcm_bytes, dtype=np.float32) for audio in audios
        ]
        sample_rates = {audio.sample_rate for audio in audios}
        if len(sample_rates) > 1:
            raise EmbeddingError(
                f"batch mixes sample rates {sorted(sample_rates)}; resample first"
            )
        sample_rate = sample_rates.pop()

        vectors: list[EmbeddingVector] = []
        with torch.inference_mode():
            for start in range(0, len(waveforms), self._batch_size):
                chunk = waveforms[start : start + self._batch_size]
                vectors.extend(
                    self._embed_chunk(
                        torch, model, processor, device, chunk, sample_rate
                    )
                )
        return vectors

    def embed_text(self, query: str) -> EmbeddingVector:
        """Embed a free-text query into the audio-embedding space."""
        if not query.strip():
            raise ValueError("query must not be empty")
        torch, model, processor, device = self._ensure_loaded()
        try:
            inputs = processor(text=query.strip(), return_tensors="pt", padding=True)
        except TypeError:
            inputs = processor(texts=[query.strip()], return_tensors="pt", padding=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            if device.type == "cuda":
                with torch.amp.autocast("cuda", dtype=torch.float16):
                    features = model.get_text_features(**inputs)
            else:
                features = model.get_text_features(**inputs)
            features = self._extract_projection(torch, features, batch_size=1)
            features = torch.nn.functional.normalize(features, p=2, dim=-1)
            features = features.to(torch.float16).cpu()
        rows = features.tolist()
        return EmbeddingVector(
            values=tuple(rows[0]), dimension=self._embedding_dimension
        )

    # ------------------------------------------------------------------ infra

    def _extract_projection(self, torch: Any, features: Any, *, batch_size: int) -> Any:
        """Pull the projected ``(batch, dim)`` tensor out of a CLAP output.

        ``ClapModel.get_audio_features``/``get_text_features`` return either a
        bare tensor or a ``BaseModelOutputWithPooling`` whose ``pooler_output``
        holds the projected features (transformers >= 4.x behaviour, and the
        default in transformers 5.x). Accept both, plus tuple-shaped returns.
        """
        tensor = features
        if not isinstance(tensor, torch.Tensor):
            tensor = getattr(tensor, "pooler_output", None)
            if tensor is None and isinstance(features, (tuple, list)) and features:
                tensor = features[0]
            if not isinstance(tensor, torch.Tensor):
                raise EmbeddingError(
                    f"CLAP model returned {type(features).__name__} without a "
                    "usable pooler_output tensor"
                )
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        expected = (batch_size, self._embedding_dimension)
        if tuple(tensor.shape) != expected:
            raise EmbeddingError(
                f"CLAP projection has shape {tuple(tensor.shape)}, expected {expected}"
            )
        return tensor

    def _embed_chunk(
        self,
        torch: Any,
        model: Any,
        processor: Any,
        device: Any,
        chunk: Sequence[Any],
        sample_rate: int,
    ) -> list[EmbeddingVector]:
        inputs = self._prepare_inputs(processor, chunk, sample_rate)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        if device.type == "cuda":
            # FP16 autocast keeps peak VRAM well under 4 GB on a 6 GB card.
            with torch.amp.autocast("cuda", dtype=torch.float16):
                features = model.get_audio_features(**inputs)
        else:
            features = model.get_audio_features(**inputs)
        features = self._extract_projection(torch, features, batch_size=len(chunk))
        features = torch.nn.functional.normalize(features, p=2, dim=-1)
        features = features.to(torch.float16).cpu()
        return [
            EmbeddingVector(values=tuple(row), dimension=self._embedding_dimension)
            for row in features.tolist()
        ]

    @staticmethod
    def _prepare_inputs(
        processor: Any,
        chunk: Sequence[Any],
        sample_rate: int,
    ) -> dict[str, Any]:
        """Call the processor with whichever keyword it accepts."""
        try:
            inputs = processor(
                audio=list(chunk),
                sampling_rate=sample_rate,
                return_tensors="pt",
                padding=True,
            )
        except TypeError:
            inputs = processor(
                audios=list(chunk),
                sampling_rate=sample_rate,
                return_tensors="pt",
                padding=True,
            )
        if not hasattr(inputs, "items"):
            inputs = inputs.data  # BatchEncoding → dict-like
        return dict(inputs)

    def _ensure_loaded(self) -> tuple[Any, Any, Any, Any]:
        """Load torch/model/processor once; safe under concurrency."""
        if self._torch is not None:
            return self._torch, self._model, self._processor, self._device
        with self._lock:
            if self._torch is not None:
                return self._torch, self._model, self._processor, self._device
            import torch

            device = self._resolve_device(torch)
            LOGGER.info("Loading CLAP model %s on %s", self._model_id, device)
            if self._model_factory is not None:
                bundle = self._model_factory()
                model = bundle.model
                processor = bundle.processor
            else:
                from transformers import ClapModel, ClapProcessor

                model = ClapModel.from_pretrained(self._model_id)
                processor = ClapProcessor.from_pretrained(self._model_id)
            model = model.to(device)
            model.eval()
            self._torch = torch
            self._model = model
            self._processor = processor
            self._device = device
            return torch, model, processor, device

    def _resolve_device(self, torch: Any) -> Any:
        cuda_ready = (
            torch.cuda.is_available()
            if self._cuda_available is None
            else self._cuda_available
        )
        requested = self._requested_device
        if requested in (None, "", "auto"):
            requested = "cuda" if cuda_ready else "cpu"
        device = torch.device(requested)
        if device.type == "cuda" and not cuda_ready:
            LOGGER.warning(
                "DEVICE=cuda requested but CUDA is unavailable; falling back to CPU"
            )
            device = torch.device("cpu")
        return device


__all__ = [
    "CLAP_EMBEDDING_DIMENSION",
    "CLAP_SAMPLE_RATE",
    "DEFAULT_CLAP_MODEL_ID",
    "MAX_BATCH_SIZE",
    "ClapAudioEmbedder",
]
```

### 6.2 `backend/src/data/ml/librosa_analyzer.py`

```python
"""CPU tempo and key extraction with librosa, safe for process pools.

``analyze_pcm`` is a module-level worker function: it imports librosa/numpy
*inside* the call so parent processes never pay the import cost and workers
spawned on Windows can pickle/re-import the module cleanly.

Tempo handling: librosa's estimate is folded by doubling/halving into the
club-music band ``[70, 175]`` BPM (a raw 65 becomes 130, a raw 240 becomes
120) and finally clamped to the domain's hard ``[40, 220]`` bounds.

Key handling: a constant-Q chromagram (``chroma_cqt``) is averaged over time and
correlated (Pearson) against the Krumhansl–Schmuckler major/minor profiles
rotated over the 12 pitch classes. The winning root/mode maps onto the
standard Camelot wheel (C major → 8B, A minor → 8A, ...).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from typing import Any

from domain.entities.track import AudioBuffer
from domain.interfaces.audio_engine import IFeatureExtractor
from domain.value_objects.audio_features import (
    BPM,
    BPM_MAX,
    BPM_MIN,
    AudioFeatures,
    CamelotKey,
)

LOGGER = logging.getLogger(__name__)

#: Fold band for raw tempo estimates (see module docstring).
TEMPO_FOLD_LOW = 70.0
TEMPO_FOLD_HIGH = 175.0

#: Minimum audio length for a meaningful analysis, in seconds.
MIN_ANALYSIS_SECONDS = 3.0

# Krumhansl–Schmuckler key profiles, index 0 = tonic.
_KRUMHANSL_MAJOR: tuple[float, ...] = (
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
)
_KRUMHANSL_MINOR: tuple[float, ...] = (
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
)

# Camelot wheel: pitch-class index (0 = C) → major-key notation.
_MAJOR_CAMELOT: Mapping[int, str] = {
    0: "8B",  # C
    1: "3B",  # C#/Db
    2: "10B",  # D
    3: "5B",  # D#/Eb
    4: "12B",  # E
    5: "7B",  # F
    6: "2B",  # F#/Gb
    7: "9B",  # G
    8: "4B",  # G#/Ab
    9: "11B",  # A
    10: "6B",  # A#/Bb
    11: "1B",  # B
}

# The relative minor of a major key keeps the same Camelot number: minor root
# r has its relative major at r + 3 semitones.
_MINOR_CAMELOT: Mapping[int, str] = {
    root: f"{_MAJOR_CAMELOT[(root + 3) % 12][:-1]}A" for root in range(12)
}

_PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def fold_tempo(
    raw_tempo: float,
    *,
    low: float = TEMPO_FOLD_LOW,
    high: float = TEMPO_FOLD_HIGH,
    hard_min: float = BPM_MIN,
    hard_max: float = BPM_MAX,
) -> float:
    """Fold a raw tempo estimate into ``[low, high]`` by doubling or halving.

    Raises ``ValueError`` for non-positive or non-finite input.
    """
    tempo = float(raw_tempo)
    if not math.isfinite(tempo) or tempo <= 0:
        raise ValueError(f"raw_tempo must be positive and finite, got {raw_tempo}")
    while tempo < low:
        tempo *= 2.0
    while tempo > high:
        tempo /= 2.0
    return min(hard_max, max(hard_min, tempo))


def analyze_pcm(
    pcm_bytes: bytes,
    sample_rate: int,
    *,
    tempo_low: float = TEMPO_FOLD_LOW,
    tempo_high: float = TEMPO_FOLD_HIGH,
    min_duration_seconds: float = MIN_ANALYSIS_SECONDS,
) -> AudioFeatures:
    """Extract BPM and musical key from mono float32 PCM.

    Individual features degrade to ``None`` when the audio is too short,
    silent, or the analysis fails — partial results must never abort a batch.
    """
    import numpy as np

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    samples = np.frombuffer(pcm_bytes, dtype=np.float32)
    if samples.size < int(sample_rate * min_duration_seconds):
        return AudioFeatures()

    bpm: BPM | None = None
    key: Any | None = None
    try:
        raw_tempo = _detect_raw_tempo(samples, sample_rate)
        if raw_tempo is not None:
            bpm = BPM(fold_tempo(raw_tempo, low=tempo_low, high=tempo_high))
    except Exception:
        LOGGER.debug("Tempo detection failed", exc_info=True)
    try:
        key = _detect_key(samples, sample_rate)
    except Exception:
        LOGGER.debug("Key detection failed", exc_info=True)
    return AudioFeatures(bpm=bpm, key=key)


def _detect_raw_tempo(samples: Any, sample_rate: int) -> float | None:
    """Return librosa's raw tempo estimate (before folding), or ``None``."""
    import librosa
    import numpy as np

    onset_envelope = librosa.onset.onset_strength(y=samples, sr=sample_rate)
    if onset_envelope.size == 0 or not np.any(onset_envelope):
        return None
    tempo = librosa.feature.tempo(
        onset_envelope=onset_envelope,
        sr=sample_rate,
        aggregate=np.median,
    )
    if tempo.size == 0:
        return None
    raw = float(tempo[0])
    return raw if math.isfinite(raw) and raw > 0 else None


def _detect_key(samples: Any, sample_rate: int) -> Any | None:
    """Match the mean chromagram against Krumhansl–Schmuckler profiles."""
    import librosa

    # Constant-Q chroma: unlike chroma_stft, its log-frequency bins keep a
    # pure tone's energy inside one semitone (stft leakage into neighbours
    # can flip a C-major triad to E minor). CQT is slower but runs on a
    # worker process, off the asyncio loop.
    chroma = librosa.feature.chroma_cqt(y=samples, sr=sample_rate)
    if chroma.size == 0:
        return None
    chroma_mean = [float(value) for value in chroma.mean(axis=1)]
    return _detect_key_from_chroma(chroma_mean)


def _detect_key_from_chroma(chroma: Any) -> CamelotKey | None:
    """Correlate a 12-bin chroma vector (index 0 = C) against KS profiles."""
    import numpy as np

    chroma_mean = np.asarray(chroma, dtype=np.float64)
    if chroma_mean.shape != (12,) or not np.any(chroma_mean):
        return None

    best_score = -2.0
    best_root = 0
    best_mode = "major"
    for root in range(12):
        rotated = np.array([chroma_mean[(root + step) % 12] for step in range(12)])
        for mode, profile in (
            ("major", _KRUMHANSL_MAJOR),
            ("minor", _KRUMHANSL_MINOR),
        ):
            score = _pearson(rotated, np.array(profile))
            if score > best_score:
                best_score = score
                best_root = root
                best_mode = mode

    if not math.isfinite(best_score):
        return None
    LOGGER.debug(
        "Detected key %s %s (score %.3f)",
        _PITCH_CLASSES[best_root],
        best_mode,
        best_score,
    )
    if best_mode == "major":
        return CamelotKey(_MAJOR_CAMELOT[best_root])
    return CamelotKey(_MINOR_CAMELOT[best_root])


def _pearson(left: Any, right: Any) -> float:
    """Pearson correlation without numpy.corrcoef (avoids NaN amplification)."""
    import numpy as np

    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = math.sqrt(
        float(np.dot(left_centered, left_centered))
        * float(np.dot(right_centered, right_centered))
    )
    if denominator == 0.0:
        return float("nan")
    return float(np.dot(left_centered, right_centered)) / denominator


class LibrosaFeatureExtractor(IFeatureExtractor):
    """Runs :func:`analyze_pcm` on decoded buffers.

    Instances hold only plain configuration values so they can be pickled and
    shipped to a ``ProcessPoolExecutor`` worker. The heavy librosa import
    happens inside the worker, never in the event-loop process.
    """

    def __init__(
        self,
        *,
        tempo_low: float = TEMPO_FOLD_LOW,
        tempo_high: float = TEMPO_FOLD_HIGH,
        min_duration_seconds: float = MIN_ANALYSIS_SECONDS,
    ) -> None:
        if tempo_low <= 0 or tempo_high < tempo_low:
            raise ValueError("tempo band must satisfy 0 < low <= high")
        if min_duration_seconds <= 0:
            raise ValueError("min_duration_seconds must be positive")
        self.tempo_low = tempo_low
        self.tempo_high = tempo_high
        self.min_duration_seconds = min_duration_seconds

    def extract(self, audio: AudioBuffer) -> AudioFeatures:
        """Return ``(bpm, key)`` for one decoded window; fields may be ``None``."""
        return analyze_pcm(
            audio.pcm_bytes,
            audio.sample_rate,
            tempo_low=self.tempo_low,
            tempo_high=self.tempo_high,
            min_duration_seconds=self.min_duration_seconds,
        )


__all__ = [
    "MIN_ANALYSIS_SECONDS",
    "TEMPO_FOLD_HIGH",
    "TEMPO_FOLD_LOW",
    "LibrosaFeatureExtractor",
    "analyze_pcm",
    "fold_tempo",
]
```

### 6.3 `backend/src/data/datasources/local/lancedb_client.py`

```python
"""Disk-backed LanceDB wrapper for CLAP embedding vectors.

Vectors are stored as fixed-size ``float16`` lists. The table is never loaded
into memory as a whole; searches use LanceDB's on-disk index.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from lancedb.index import IvfPq

LOGGER = logging.getLogger(__name__)

CLAP_DIMENSION = 512
INDEX_THRESHOLD = 10_000


@dataclass(frozen=True, slots=True)
class VectorMatch:
    """A vector-search hit before SQLite metadata hydration."""

    track_id: str
    similarity: float


class LanceDBClient:
    """Owns one LanceDB database directory and its track-vector table."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        table_name: str = "track_vectors",
        vector_dimension: int = CLAP_DIMENSION,
    ) -> None:
        self._path = Path(db_path)
        self._table_name = table_name
        self._vector_dimension = vector_dimension
        self._db: Any | None = None
        self._table: Any | None = None

    @property
    def path(self) -> Path:
        """Filesystem path of the LanceDB directory."""
        return self._path

    @property
    def vector_dimension(self) -> int:
        """Expected embedding width."""
        return self._vector_dimension

    async def connect(self) -> None:
        """Open the database and prepare the table if it already exists."""
        if self._db is not None:
            return
        self._path.mkdir(parents=True, exist_ok=True)
        self._db = await asyncio.to_thread(lancedb.connect, str(self._path))
        table_names = await asyncio.to_thread(self._list_tables)
        if self._table_name in table_names:
            self._table = await asyncio.to_thread(self._db.open_table, self._table_name)

    def _list_tables(self) -> list[str]:
        list_tables = getattr(self._db, "list_tables", None)
        if callable(list_tables):
            return list(list_tables())
        return list(self._db.table_names())

    async def close(self) -> None:
        """Release references. LanceDB has no explicit connection close."""
        self._table = None
        self._db = None

    async def upsert_many(self, rows: Sequence[dict[str, Any]]) -> int:
        """Insert or update vector rows keyed by ``id``."""
        if not rows:
            return 0
        for row in rows:
            vector = row.get("vector")
            if not isinstance(vector, (list, tuple)):
                raise TypeError("vector row must contain a list of numbers")
            if len(vector) != self._vector_dimension:
                raise ValueError(
                    "embedding dimension mismatch: expected "
                    f"{self._vector_dimension}, got {len(vector)}"
                )

        table = await self._ensure_table()
        try:
            merge = table.merge_insert("id")
            merge = merge.when_matched_update_all()
            merge = merge.when_not_matched_insert_all()
            await asyncio.to_thread(merge.execute, list(rows))
        except Exception:  # noqa: BLE001 - fallback for older LanceDB releases
            # Older LanceDB builds may not expose merge_insert. Deleting and
            # appending keeps the operation idempotent at the cost of a rewrite.
            ids = [str(row["id"]) for row in rows]
            quoted = ", ".join(self._quote(value) for value in ids)
            await asyncio.to_thread(table.delete, f"id IN ({quoted})")
            await asyncio.to_thread(table.add, list(rows))

        await self.maybe_create_index()
        return len(rows)

    async def search(
        self,
        vector: Sequence[float],
        *,
        limit: int = 50,
        where: str | None = None,
    ) -> Sequence[VectorMatch]:
        """Return nearest neighbours using cosine distance."""
        if len(vector) != self._vector_dimension:
            raise ValueError(
                "embedding dimension mismatch: expected "
                f"{self._vector_dimension}, got {len(vector)}"
            )
        if limit <= 0:
            return ()
        table = await self._ensure_table()
        query = table.search(list(vector)).metric("cosine").limit(limit)
        if where:
            query = query.where(where)
        rows = await asyncio.to_thread(query.to_list)
        matches: list[VectorMatch] = []
        for row in rows:
            distance = float(row.get("_distance", 1.0))
            similarity = max(-1.0, min(1.0, 1.0 - distance))
            matches.append(VectorMatch(track_id=str(row["id"]), similarity=similarity))
        return tuple(matches)

    async def get_vector(self, track_id: str) -> tuple[float, ...] | None:
        """Return one stored vector, or ``None`` when the id is absent."""
        table = await self._ensure_table()
        try:
            arrow = await asyncio.to_thread(
                table.to_lance().to_table,
                filter=f"id = {self._quote(track_id)}",
                columns=["vector"],
            )
        except Exception:  # noqa: BLE001 - a missing row is a normal lookup miss
            return None
        rows = arrow.to_pylist()
        if not rows:
            return None
        return tuple(float(value) for value in rows[0]["vector"])

    async def count(self) -> int:
        """Return the number of vector rows without loading them."""
        table = await self._ensure_table()
        return int(await asyncio.to_thread(table.count_rows))

    async def maybe_create_index(self) -> bool:
        """Create an IVF-PQ index once the table exceeds 10,000 rows.

        Returns ``True`` when an index was created during this call.
        """
        table = await self._ensure_table()
        row_count = int(await asyncio.to_thread(table.count_rows))
        if row_count <= INDEX_THRESHOLD:
            return False
        try:
            existing = await asyncio.to_thread(table.list_indices)
            if existing:
                return False
        except Exception:
            LOGGER.debug("LanceDB list_indices is unavailable", exc_info=True)

        num_partitions = max(1, min(256, row_count // 1000))
        num_sub_vectors = 32 if self._vector_dimension >= 64 else 1
        try:
            await asyncio.to_thread(
                table.create_index,
                "vector",
                config=IvfPq(
                    distance_type="cosine",
                    num_partitions=num_partitions,
                    num_sub_vectors=num_sub_vectors,
                ),
            )
            return True
        except Exception:
            LOGGER.warning("Could not create LanceDB IVF-PQ index", exc_info=True)
            return False

    async def _ensure_table(self) -> Any:
        if self._db is None:
            raise RuntimeError("LanceDBClient is not connected")
        if self._table is not None:
            return self._table
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("bpm", pa.float32()),
                pa.field("camelot_key", pa.string()),
                pa.field("genre", pa.string()),
                pa.field(
                    "vector",
                    pa.list_(pa.float16(), self._vector_dimension),
                ),
            ]
        )
        self._table = await asyncio.to_thread(
            self._db.create_table,
            self._table_name,
            schema=schema,
        )
        return self._table

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"
```

### 6.4 `backend/src/domain/use_cases/dig_similar_tracks.py`

```python
"""Use case: find the closest catalog tracks to one indexed track.

Given a reference track id and a :class:`SearchFilter`, the use case loads the
reference's stored CLAP vector, queries the disk-backed vector index for the
nearest neighbours (cosine similarity), removes the reference itself, and
applies optional BPM-tolerance and harmonic (Camelot wheel) constraints
before returning ordered matches.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..entities.dj_set import TrackMatch
from ..entities.search import SearchFilter
from ..entities.track import Track
from ..interfaces.repositories import ITrackRepository
from ..value_objects.audio_features import BPM_MAX, BPM_MIN, CamelotKey

LOGGER = logging.getLogger(__name__)

_MAX_FILTER_LIMIT = 500


class DigLookupError(Exception):
    """Base class for dig lookup failures."""


class TrackNotFoundError(DigLookupError):
    """The requested track id is not in the local catalog."""


class TrackNotEmbeddedError(DigLookupError):
    """The requested track has no stored embedding yet — index it first."""


@dataclass(frozen=True, slots=True)
class DigResult:
    """The reference track plus its nearest neighbours, best first."""

    reference: Track
    matches: tuple[TrackMatch, ...]


class DigSimilarTracks:
    """Track-to-track similarity search over the local catalog."""

    def __init__(self, *, track_repository: ITrackRepository) -> None:
        self._track_repository = track_repository

    async def execute(
        self,
        track_id: str,
        search_filter: SearchFilter | None = None,
        *,
        bpm_tolerance: float | None = None,
        harmonic: bool = False,
    ) -> DigResult:
        """Return the closest tracks to ``track_id``.

        ``bpm_tolerance`` narrows the filter to ``reference_bpm ± tolerance``
        (intersected with any explicit bounds). ``harmonic`` expands the
        Camelot allow-list with the reference key's compatible neighbours
        (same key, relative major/minor, ±1 on the same side). One extra
        neighbour is fetched so removing the reference itself still leaves
        ``filter.limit`` results.
        """
        reference = await self._track_repository.get_by_id(track_id)
        if reference is None:
            raise TrackNotFoundError(f"track {track_id!r} is not in the catalog")
        if reference.embedding is None:
            raise TrackNotEmbeddedError(
                f"track {track_id!r} has no embedding yet; run `dig index` first"
            )

        base = search_filter or SearchFilter()
        effective = self._effective_filter(
            reference,
            base,
            bpm_tolerance=bpm_tolerance,
            harmonic=harmonic,
        )

        # Over-fetch by one so dropping the reference still fills the limit.
        fetch_limit = min(_MAX_FILTER_LIMIT, effective.limit + 1)
        matches = await self._track_repository.find_similar(
            reference.embedding,
            replace(effective, limit=fetch_limit),
        )
        filtered = tuple(match for match in matches if match.track.id != reference.id)[
            : effective.limit
        ]
        return DigResult(reference=reference, matches=filtered)

    @staticmethod
    def _effective_filter(
        reference: Track,
        search_filter: SearchFilter,
        *,
        bpm_tolerance: float | None,
        harmonic: bool,
    ) -> SearchFilter:
        bpm_min = search_filter.bpm_min
        bpm_max = search_filter.bpm_max
        if bpm_tolerance is not None and reference.bpm is not None:
            if bpm_tolerance < 0:
                raise ValueError("bpm_tolerance must not be negative")
            low = max(BPM_MIN, reference.bpm.value - bpm_tolerance)
            high = min(BPM_MAX, reference.bpm.value + bpm_tolerance)
            if search_filter.bpm_min is not None:
                low = max(low, search_filter.bpm_min)
            if search_filter.bpm_max is not None:
                high = min(high, search_filter.bpm_max)
            if low > high:
                raise ValueError(
                    "bpm tolerance window does not overlap the filter bounds"
                )
            bpm_min, bpm_max = low, high

        camelot_keys = search_filter.camelot_keys
        if harmonic and reference.key is not None:
            compatible = {
                key
                for key in _all_camelot_keys()
                if reference.key.is_harmonic_compatible(key)
            }
            camelot_keys = tuple(
                dict.fromkeys((*search_filter.camelot_keys, *compatible))
            )

        return replace(
            search_filter,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            camelot_keys=camelot_keys,
        )


def _all_camelot_keys() -> Sequence[CamelotKey]:
    return tuple(
        CamelotKey(f"{number}{letter}")
        for number in range(1, 13)
        for letter in ("A", "B")
    )


__all__ = [
    "DigLookupError",
    "DigResult",
    "DigSimilarTracks",
    "TrackNotEmbeddedError",
    "TrackNotFoundError",
]
```
