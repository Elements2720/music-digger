# DigDeeper Local — Codebase Context (Phase 3 & 4 + GUI)

> **Generated**: 2026-11-22 · **Purpose**: Exhaustive technical handoff for an AI architect to understand the entire current implementation without reading every file.

---

## 1. Project Tree & Stack

### 1.1 Source Tree

```
backend/
  pyproject.toml
  src/
    container.py                                  # Composition Root (wires SQLite, LanceDB, ML, Repositories, Use Cases)
    domain/
      _validation.py                              # Pure validation helpers (stdlib only)
      genres.py                                   # Curated techno subgenre presets, token matching, year guard
      __init__.py
      entities/
        __init__.py
        track.py                                  # Track, BlacklistEntry, BlacklistKind, SeedArtist, AudioBuffer, TrackReference, TrackVibe
        analytics.py                              # GenreStat, BpmBucketStat, SourceStat, KeyStat, ArtistSummary, CatalogAnalytics, SeedBreakdown, SeedSourceStat
        dj_set.py                                 # TrackMatch, Passage, DJSet, DownloadedSet, SetMatch
        search.py                                 # SearchFilter (min_year, max_year, genres)
      value_objects/
        __init__.py
        audio_features.py                         # BPM, CamelotKey, TimeRange, EmbeddingVector, AudioFeatures
        hardware.py                               # HardwareInfo
      interfaces/
        __init__.py
        audio_engine.py                           # IAudioDecoder, IFeatureExtractor, IAudioEmbedder, IAudioSegmenter, IFingerprinter, ISetDownloader
        catalog.py                                # ICatalogProvider (search, lookup, crawl_keyword), ISeedDiscovery, ISeedCrawler
        hardware.py                               # IHardwareProbe
        llm.py                                    # ILLMService
        local_library.py                          # ILocalLibraryScanner
        repositories.py                           # ITrackRepository, ISetRepository, ISeedRepository, IBlacklistRepository
      use_cases/
        __init__.py
        analyze_dj_set.py                         # AnalyzeDJSet (Phase 4: end-to-end DJ set pipeline, multi-probe Shazam, boundary avoidance)
        build_seed_list.py                        # BuildSeedList (Deezer BFS + LLM seed generation, CrawlProgress, local roots)
        crawl_itunes_seeds.py                     # CrawlITunesSeeds (Phase B: iTunes techno/label keyword crawler)
        dig_similar_tracks.py                     # DigSimilarTracks (track-to-track similarity, harmonic/BPM filter)
        fetch_artist_tracks.py                    # FetchArtistTracks (targeted artist track fetching, auto-indexing, related discovery)
        fetch_catalog_metadata.py                 # FetchCatalogMetadata (iTunes artist metadata harvester, blacklist-aware)
        find_similar_for_set.py                   # FindSimilarForSet (set-to-set & passage-to-track similarity)
        import_local_library.py                   # ImportLocalLibrary (local folder import, middle-window decode, artist seeding)
        index_catalog.py                          # IndexCatalog (streaming audio decode, librosa analysis, CLAP embed)
        manage_catalog.py                         # ManageCatalog (safe track/artist delete without disk deletion, blacklist CRUD)
        vibe_search.py                            # VibeSearch (natural language query -> CLAP text embedding)
    data/
      __init__.py
      errors.py                                   # DataLayerError hierarchy
      normalization.py                            # normalize_text, normalize_artist_title, normalize_seed_name
      datasources/
        __init__.py
        local/
          __init__.py
          sqlite_client.py                        # SQLiteClient + Schema DDL (tracks, seed_artists, dj_sets, set_passages, blacklist)
          lancedb_client.py                       # LanceDBClient + VectorMatch (disk-backed IVF-PQ cosine index, delete_ids)
          local_library_scanner.py                # LocalLibraryScanner (ffprobe recursive tag reader + filename fallback)
        remote/
          __init__.py
          artist_parser.py                        # parse_collaborators() (remix/feature artist extractor)
          deezer_seed_crawler.py                  # DeezerSeedCrawler (BFS discovery with live CrawlProgress)
          itunes_provider.py                      # ITunesProvider (18 req/min token bucket, crawl_keyword, snowballing)
          rate_limiter.py                         # AsyncTokenBucket, exponential_backoff, retry_after_seconds
          shazam_client.py                        # ShazamFingerprinter (15s timeout, circuit breaker, CancelledError propagation)
          ytdlp_downloader.py                     # YtDlpSetDownloader (yt-dlp set streaming, browser cookies, comments)
      llm/
        __init__.py
        multi_llm_client.py                       # MultiLLMClient (ILLMService: OpenAI-compatible local LLM client)
      mappers/
        __init__.py
        blacklist_mapper.py                       # row_to_blacklist
        seed_mapper.py                            # seed_to_row / row_to_seed
        set_mapper.py                             # set_to_row / row_to_set / passage_to_row / row_to_passage
        track_mapper.py                           # track_to_row / row_to_track / track_to_vector_row
      ml/
        __init__.py
        clap_embedder.py                          # ClapAudioEmbedder (laion/clap-htsat-unfused 512-dim, FP16 CUDA/CPU)
        ffmpeg_decoder.py                         # FFmpegAudioDecoder (f32le 48kHz mono pipes, RAM-only, no disk writes)
        hardware_probe.py                         # HardwareProbe (CUDA/VRAM/RAM/FFmpeg probe)
        librosa_analyzer.py                       # LibrosaFeatureExtractor (BPM tempo folding, CQT Camelot key detection)
        set_segmenter.py                          # SetSegmenter (semantic CLAP + acoustic novelty curve, strictly clamped passage boundaries)
      repositories/
        __init__.py
        blacklist_repository.py                   # SQLiteBlacklistRepository (IBlacklistRepository)
        seed_repository.py                        # SQLiteSeedRepository (ISeedRepository: blacklist filtering, delete_by_name)
        set_repository.py                         # SQLiteSetRepository (ISetRepository: SQLite + LanceDB set vectors)
        track_repository.py                       # HybridTrackRepository (ITrackRepository: blacklist filtering, safe delete, analytics)
    presentation/
      __init__.py
      cli/
        __init__.py
        __main__.py                               # python -m presentation.cli
        commands.py                               # Typer `dig` CLI (ASCII only, rich progress, delete/blacklist/stats commands)
      api/
        __init__.py
        app.py                                    # FastAPI application factory & static file mounting
        job_manager.py                            # JobManager (single-job concurrency, SSE streaming, turbo mode, telemetry)
        schemas.py                                # Pydantic schemas, JobKind literal, Blacklist schemas & analytics serializers
        routes/
          __init__.py
          catalog.py                              # /api/catalog endpoints (tracks, seeds, stats, dig, analytics, artists, blacklist)
          hardware.py                             # /api/hardware endpoints (GPU, VRAM, RAM, FFmpeg probe)
          jobs.py                                 # /api/jobs endpoints (start, cancel, snapshot, SSE stream)
          sets.py                                 # /api/sets endpoints (DJ set analysis, passage queries, similar sets)
  tests/
    domain/
      test_domain_purity.py                       # AST import scan: enforces stdlib-only imports in domain/
      test_analyze_dj_set.py                      # DJ set use case unit tests (multi-probe Shazam, interior core, duplicate merging)
      test_audio_features.py
      test_bpm.py
      test_build_seed_list.py                     # Seed list building + CrawlProgress tests
      test_camelot_key.py
      test_crawl_itunes_seeds.py                  # iTunes techno keyword crawler tests
      test_dig_similar_tracks.py
      test_dj_set_entities.py                     # DJ set entity tests + 0.05s tolerance auto-clamp tests
      test_embedding_vector.py
      test_find_similar_for_set.py
      test_import_local_library.py                # Local library import & taste-based artist seeding tests
      test_index_catalog.py
      test_interfaces.py
      test_manage_catalog.py                      # Safe track/artist deletion and blacklist tests
      test_search_filter.py
      test_set_entities.py
      test_time_range.py
      test_track_entities.py
      test_use_cases.py
      test_vibe_search.py
    data/
      conftest.py
      fakes.py                                    # Shared test doubles (FakeClock, MockTransport)
      test_artist_parser.py
      test_blacklist_repository.py                # Blacklist repository CRUD and cache tests
      test_clap_embedder.py
      test_deezer_crawler.py
      test_ffmpeg_decoder.py
      test_hardware_probe.py
      test_itunes_provider.py                     # iTunes provider tests (18 req/min, crawl_keyword, token bucket)
      test_librosa_analyzer.py
      test_llm_client.py
      test_rate_limiter.py
      test_set_repository.py
      test_set_segmenter.py                       # Segmenter tests (semantic + acoustic boundary detection, duration clamp)
      test_shazam_client.py                       # Shazam tests (timeout, circuit breaker, CancelledError propagation)
      test_sqlite_seed_repository.py
      test_track_repository.py
      test_ytdlp_downloader.py
    presentation/
      api_fakes.py                                # Duck-typed container & fake services for API testing
      test_api_routes.py                          # FastAPI endpoint integration tests (catalog, blacklist, deletion)
      test_job_manager.py                         # JobManager execution, SSE streaming, turbo mode, speed/telemetry

frontend/
  index.html                                      # SPA single-page shell (modals for delete confirmation and blacklist)
  css/
    style.css                                     # Minimalist dark theme, responsive grid, progress tracks, #job-log, library manager UI
  js/
    api.js                                        # Fetch API client (analytics, artist management, blacklist CRUD, SSE subscription)
    format.js                                     # Number/BPM/Camelot/Time formatting utilities
    main.js                                       # Router & view switcher
    player.js                                     # Audio preview player controller
    state.js                                      # Lightweight global reactive state
    ui.js                                         # DOM construction helpers (trackRow with quick delete action)
    views/
      dig.js                                      # Dig view (track-to-track similarity, audio preview, harmonic filter)
      run.js                                      # Run view (job configuration, live progress, speed, recent messages log)
      sets.js                                     # Sets view (analyzed DJ set browser, tracklist, passage timeline)
      stats.js                                    # Stats view (rich Library Overview & Manager, KPI cards, visual distribution bars, searchable artists drawer, blacklist tab)
```

### 1.2 Python Version & Key Dependencies

| Item | Spec |
|---|---|
| **Python** | `>= 3.11` (tested on `3.13`) |
| **Build** | `setuptools >= 68`, `package-dir = {"" = "src"}` |
| **Entry point** | `dig = presentation.cli.commands:main` |
| **torch source** | CUDA wheels from `https://download.pytorch.org/whl/cu124` via `[tool.uv.sources]` |

**Runtime dependencies**:

| Package | Version | Purpose |
|---|---|---|
| `aiosqlite` | >= 0.22.1 | Async SQLite driver |
| `fastapi` | >= 0.115.0 | Web API framework |
| `httpx` | >= 0.28.1 | Async HTTP client with HTTP/2 and MockTransport support |
| `lancedb` | >= 0.41.0 | Disk-backed vector database |
| `librosa` | >= 0.11.0 | Audio feature analysis (BPM tempo folding, CQT Camelot key) |
| `numpy` | >= 1.26 | Numerical array manipulation |
| `pyarrow` | >= 26.0.1 | Columnar data representation for LanceDB |
| `pylance` | >= 14.0.3 | LanceDB query engine |
| `python-dotenv` | >= 1.2.4 | Environment variable loader |
| `rich` | >= 15.0.0 | Terminal formatting and progress bars |
| `shazamio` | >= 0.8.0 | Public Shazam endpoint client for exact-ID fingerprinting |
| `torch` | >= 2.6.0 | PyTorch CUDA 12.4 runtime |
| `transformers` | >= 4.45 | Hugging Face CLAP model loader (`laion/clap-htsat-unfused`) |
| `typer` | >= 0.29.2 | CLI framework |
| `uvicorn` | >= 0.32.0 | ASGI web server |
| `yt-dlp` | >= 2024.12.0 | Audio streaming and set download from YouTube/SoundCloud/Mixcloud |

**Dev dependencies**: `pytest >= 8.0, < 9`, `pytest-asyncio >= 1.5.0`, `ruff`

**pytest config**: `pythonpath = ["src"]`, `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `addopts = ["-ra", "--strict-markers", "--strict-config"]`

### 1.3 Environment Variables (`.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `DEVICE` | `cuda` | torch device (`cuda` or `cpu`) |
| `DEVICE_FP16` | `true` | Enable FP16 inference |
| `STORAGE_DIR` | `./storage` | Relative to repo root |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `HOST` | `127.0.0.1` | Web GUI host |
| `PORT` | `8123` | Web GUI port |
| `LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI-compatible endpoint |
| `LLM_API_KEY` | `local` | Bearer token |
| `LLM_FAST_MODEL` | `qwen2.5:7b-instruct` | Model for seed/vibe/tracklist |
| `LLM_AUDIO_MODEL` | `qwen2-audio:7b` | (Future) audio model |
| `CLAP_MODEL_ID` | `laion/clap-htsat-unfused` | HuggingFace model id (512-dim) |
| `CLAP_BATCH_SIZE` | `16` | Micro-batch size (clamped to 32) |
| `CLAP_MAX_VRAM_GB` | `4.0` | VRAM budget (GTX 1660 Super target) |
| `ANALYSIS_MAX_WORKERS` | `4` | ProcessPoolExecutor workers (ceiling 6) |
| `PREVIEW_SECONDS` | `30` | Preview length |
| `TARGET_SAMPLE_RATE` | `48000` | PCM sample rate for CLAP |
| `PREVIEW_CONCURRENCY` | `16` | Download semaphore (ceiling 16) |
| `PREVIEW_TIMEOUT_SECONDS` | `30` | HTTP download timeout |
| `FFMPEG_TIMEOUT_SECONDS` | `60` | Per-subprocess timeout |
| `INDEX_QUEUE_MAXSIZE` | `64` | asyncio.Queue bound between decode and embed |
| `ITUNES_RATE_LIMIT_PER_MINUTE` | `18` | Hard ceiling <= 18 |
| `ITUNES_COUNTRY` | `US` | Storefront |
| `ITUNES_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `DEEZER_RATE_LIMIT_PER_SEC` | `8` | Hard ceiling <= 8 |
| `DEEZER_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `SEED_CRAWL_MAX_DEPTH` | `2` | BFS depth for related artists |
| `CATALOG_ELECTRONIC_RATIO` | `0.75` | Target 75 / 25 split |
| `LLM_TIMEOUT_SECONDS` | `120` | Chat-completions timeout |
| `SQLITE_PATH` | `./storage/app.db` | Database file |
| `LANCEDB_PATH` | `./storage/lancedb` | Vector directory |
| `SET_CACHE_DIR` | `./storage/cache/sets` | DJ set temporary audio storage |
| `YTDLP_COOKIES_FILE` | `None` | Path to Netscape cookies.txt |
| `YTDLP_COOKIES_FROM_BROWSER` | `None` | Browser profile for cookies (firefox, chrome, edge...) |

---

## 2. Domain Layer Contracts

### 2.1 Validation Helpers (`domain/_validation.py`)

| Function | Signature | Behavior |
|---|---|---|
| `require_str` | `(value, field, *, allow_empty=False) -> str` | Strip, reject non-str / empty |
| `optional_str` | `(value | None, field) -> str | None` | None pass-through, else require_str |
| `require_float` | `(value, field) -> float` | Reject bool/non-numeric/non-finite |
| `require_int` | `(value, field) -> int` | Reject bool |
| `require_bool` | `(value, field) -> bool` | Strict bool |
| `freeze_tuple` | `(value, field, expected_type=None) -> tuple[T, ...]` | Freeze iterable, optional type check |
| `normalize_key` | `(text: str) -> str` | Pure stdlib alphanumeric lowercase normalization (re `[^a-z0-9]`) |
| `normalize_artist_key`| `(artist: str) -> str` | Normalized deduplication key for artist names |
| `normalize_track_key` | `(artist: str, title: str) -> str` | Composite normalized deduplication key (`artist:::title`) |

### 2.2 Value Objects (`domain/value_objects/`)

#### `BPM` (frozen, slotted, ordered)
| Field | Type | Constraint |
|---|---|---|
| `value` | `float` | 40.0 <= value <= 220.0 |

Methods: `bpm` (property alias), `is_close_to(other, tolerance=1.0) -> bool`

#### `CamelotKey` (frozen, slotted)
| Field | Type | Constraint |
|---|---|---|
| `notation` | `str` | Regex `^[1-9]|1[0-2][AB]$`, uppercased + stripped |

Properties: `number -> int`, `letter -> str`, `value -> str`, `key -> str`
Methods: `is_harmonic_compatible(other) -> bool` — same key, same number (relative major/minor), +-1 on same side with 12<->1 wrap.

#### `TimeRange` (frozen, slotted, ordered)
| Field | Type | Constraint |
|---|---|---|
| `start_seconds` | `float` | >= 0 |
| `end_seconds` | `float` | > start_seconds |

Properties: `duration_seconds`. Methods: `contains(seconds) -> bool`, `overlaps(other) -> bool`

#### `EmbeddingVector` (frozen, slotted)
| Field | Type | Constraint |
|---|---|---|
| `values` | `tuple[float, ...]` | Non-empty, all finite |
| `dimension` | `int | None` | Inferred from values if omitted; must match if supplied |

Methods: `from_sequence(cls, values, *, expected_dimension=None)`, `validate_dimension(expected)`, `cosine_similarity(other) -> float` (pure-Python `[-1.0, 1.0]`), `__len__`

#### `AudioFeatures` (frozen, slotted)
| Field | Type |
|---|---|
| `bpm` | `BPM | None` |
| `key` | `CamelotKey | None` |

#### `HardwareInfo` (frozen, slotted)
| Field | Type |
|---|---|
| `torch_version` | `str | None` |
| `cuda_available` | `bool` (default False) |
| `cuda_version` | `str | None` |
| `gpu_name` | `str | None` |
| `vram_total_mb` | `int | None` |
| `vram_free_mb` | `int | None` |
| `ram_total_mb` | `int | None` |
| `ram_free_mb` | `int | None` |
| `ffmpeg_path` | `str | None` |
| `ffmpeg_version` | `str | None` |

Properties: `has_ffmpeg`, `gpu_ready`. Methods: `vram_summary() -> str`, `ram_summary() -> str`

### 2.3 Entities (`domain/entities/`)

#### `Track` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `id` | `str` | *required* |
| `title` | `str` | *required* |
| `artist` | `str` | *required* |
| `duration_seconds` | `float | None` | `None` |
| `bpm` | `BPM | None` | `None` (auto-wraps raw float) |
| `key` | `CamelotKey | None` | `None` (auto-wraps raw string) |
| `genre` | `str | None` | `None` |
| `release_year` | `int | None` | `None` (1900-2100) |
| `isrc` | `str | None` | `None` |
| `preview_url` | `str | None` | `None` |
| `artwork_url` | `str | None` | `None` |
| `album` | `str | None` | `None` |
| `store_url` | `str | None` | `None` |
| `source` | `str` | `"unknown"` |
| `external_id` | `str | None` | `None` |
| `embedding` | `EmbeddingVector | None` | `None` |
| `local_path` | `str | None` | `None` |

Properties: `track_id`, `duration`, `display_name`. Methods: `with_embedding(EmbeddingVector) -> Track`

#### `BlacklistEntry` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `id` | `int | None` | `None` |
| `kind` | `Literal["artist", "track"]` | *required* |
| `normalized_key` | `str` | *required* |
| `display_name` | `str` | *required* |
| `artist_name` | `str | None` | `None` |
| `track_title` | `str | None` | `None` |
| `reason` | `str | None` | `None` |
| `created_at` | `str | None` | `None` |

#### Analytics Entities (`domain/entities/analytics.py`, frozen, slotted)
- `GenreStat`: `genre: str`, `track_count: int`, `embedded_count: int`
- `BpmBucketStat`: `label: str`, `track_count: int`
- `SourceStat`: `source: str`, `track_count: int`, `embedded_count: int`
- `KeyStat`: `camelot_key: str`, `track_count: int`
- `ArtistSummary`: `artist: str`, `track_count: int`, `embedded_count: int`, `genres: tuple[str, ...]`, `sample_track_id: str | None = None`, `sample_track_title: str | None = None`
- `CatalogAnalytics`: `total_tracks: int`, `total_embedded: int`, `total_artists: int`, `total_local: int`, `total_itunes: int`, `genres: tuple[GenreStat, ...]`, `bpm_buckets: tuple[BpmBucketStat, ...]`, `sources: tuple[SourceStat, ...]`, `keys: tuple[KeyStat, ...]`

#### `SeedArtist` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `name` | `str` | *required* |
| `priority_score` | `float` | *required* (0.0-1.0) |
| `category` | `Literal["electronic", "general"]` | *required* |
| `status` | `Literal["pending", "fetched", "failed"]` | `"pending"` |
| `source` | `str` | `"llm"` |
| `external_id` | `str | None` | `None` |

Properties: `is_pending`. Methods: `with_status(status) -> SeedArtist`

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
| `timestamp` | `TimeRange | None` | `None` |
| `confidence` | `float` | `1.0` (0.0-1.0) |

#### `TrackVibe` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `tags` | `tuple[str, ...]` | *required* (deduplicated case-fold) |
| `mood` | `str` | *required* |
| `energy` | `float` | *required* (0.0-1.0) |
| `description` | `str` | `""` |

#### `TrackMatch` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `track` | `Track` | *required* |
| `similarity_score` | `float` | *required* (-1.0 to 1.0) |
| `is_exact_id` | `bool` | `False` |

Property: `similarity_percent -> float` — `round(max(0.0, min(1.0, score)) * 100, 1)`, keeping one decimal place so near-perfect cosine matches do not collapse to identical scores.

#### `Passage` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `time_range` | `TimeRange` | *required* |
| `bpm` | `BPM | None` | `None` |
| `key` | `CamelotKey | None` | `None` |
| `exact_id_match` | `bool` | `False` |
| `closest_matches` | `tuple[TrackMatch, ...]` | `()` (auto-sorted descending by similarity) |
| `exact_id_title` | `str | None` | `None` |
| `exact_id_artist` | `str | None` | `None` |
| `exact_id_source` | `Literal["shazam", "comments"] | None` | `None` |
| `embedding` | `EmbeddingVector | None` | `None` |

Properties: `best_match`, `exact_match`, `exact_id_display_name`. Methods: `with_embedding(EmbeddingVector) -> Passage`

#### `DJSet` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `id` | `str` | *required* |
| `title` | `str` | *required* |
| `source_url` | `str | None` | `None` |
| `passages` | `tuple[Passage, ...]` | `()` |
| `duration_seconds` | `float | None` | `None` |
| `artist` | `str | None` | `None` |
| `thumbnail_url` | `str | None` | `None` |
| `bpm_min` | `BPM | None` | `None` |
| `bpm_max` | `BPM | None` | `None` |
| `embedding` | `EmbeddingVector | None` | `None` (L2-normalized mean passage vector) |

**Invariant & Tolerance**: In `__post_init__`, validates passage boundaries against `duration_seconds` with a `0.05s` floating-point tolerance. If `duration < end <= duration + 0.05`, the passage is automatically clamped to `TimeRange(start, duration)`. If `end > duration + 0.05`, `ValueError` is raised.

Properties: `set_id`, `passage_count`. Methods: `ordered_passages()`, `passage_at(seconds)`, `with_passage(Passage)`, `with_embedding(EmbeddingVector)`.

#### `DownloadedSet` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `audio_path` | `Path` | *required* |
| `title` | `str` | *required* |
| `duration_seconds` | `float | None` | `None` |
| `source_url` | `str | None` | `None` |
| `artist` | `str | None` | `None` |
| `thumbnail_url` | `str | None` | `None` |
| `description` | `str` | `""` |
| `comments` | `tuple[str, ...]` | `()` |
| `is_temporary` | `bool` | `True` |

#### `SetMatch` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `dj_set` | `DJSet` | *required* |
| `similarity_score` | `float` | *required* (-1.0 to 1.0) |

Property: `similarity_percent -> float`

#### `SearchFilter` (frozen, slotted)
| Field | Type | Default |
|---|---|---|
| `bpm_min` | `float | None` | `None` |
| `bpm_max` | `float | None` | `None` |
| `camelot_keys` | `tuple[CamelotKey, ...]` | `()` (deduplicated) |
| `exclude_heard` | `bool` | `False` |
| `genre_filter` | `str | None` | `None` |
| `limit` | `int` | `50` (1-500) |

Methods: `matches(track, heard_ids=frozenset()) -> bool`

#### Event Dataclasses (frozen, slotted)
- `CrawlProgress`: `stage: str`, `name: str`, `depth: int | None`, `found: int`
- `AnalyzeEvent`: `stage: str`, `completed: int`, `total: int`, `message: str = ""`, `failed: int = 0`

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
def detect_passages(self, path: Path, total_duration_seconds: float) -> Sequence[TimeRange]
```

#### `IFingerprinter` (ABC)
```python
def compute(self, audio: AudioBuffer) -> str
def identify(self, audio: AudioBuffer) -> Track | None
def identify_async(self, audio: AudioBuffer) -> Coroutine[Any, Any, TrackReference | None]
def reset_circuit_breaker(self) -> None
```

#### `ISetDownloader` (ABC)
```python
async def download(self, url: str, destination: Path) -> Path
async def fetch_set(self, source: str, destination_dir: Path, *, fetch_comments: bool = True) -> DownloadedSet
def set_cookie_overrides(self, cookies_file: Path | None = None, cookies_from_browser: str | None = None) -> None
```

#### `ICatalogProvider` (ABC)
```python
@property provider_id -> str
async def search_tracks(self, query: str, *, limit=25) -> Sequence[Track]
async def lookup_track(self, provider_track_id: str) -> Track | None
async def list_artist_tracks(self, artist_name: str, *, limit=50) -> Sequence[Track]
async def fetch_preview(self, track: Track) -> bytes | None
async def crawl_keyword(self, keyword: str, *, limit: int = 200, expand_compilations: bool = True) -> Sequence[Track]
```

#### `ISeedDiscovery` (ABC)
```python
async def discover(self, *, electronic_limit=1000, general_limit=300, max_depth=2, progress=None) -> Sequence[SeedArtist]
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
async def delete_by_ids(self, track_ids: Sequence[str]) -> tuple[int, tuple[str, ...]]
async def delete_by_artist(self, artist_name: str) -> tuple[int, tuple[str, ...]]
async def list_by_artist(self, artist_name: str) -> Sequence[Track]
async def list_artists_summary(self, *, query: str | None = None, sort: str = "tracks_desc", limit: int = 50, offset: int = 0) -> tuple[Sequence[ArtistSummary], int]
async def get_catalog_analytics(self) -> CatalogAnalytics
```

#### `ISetRepository` (ABC)
```python
async def save(self, dj_set: DJSet) -> None
async def get_by_id(self, set_id: str) -> DJSet | None
async def list_all(self, limit=20) -> Sequence[DJSet]
async def delete(self, set_id: str) -> bool
async def count(self) -> int
async def find_similar_sets(self, embedding: EmbeddingVector, *, limit=12) -> Sequence[SetMatch]
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
async def delete_by_name(self, name: str) -> bool
```

#### `IBlacklistRepository` (ABC)
```python
async def add(self, entry: BlacklistEntry) -> BlacklistEntry
async def get_by_key(self, kind: BlacklistKind, normalized_key: str) -> BlacklistEntry | None
async def is_blacklisted(self, kind: BlacklistKind, normalized_key: str) -> bool
async def list_all(self, kind: BlacklistKind | None = None) -> Sequence[BlacklistEntry]
async def remove(self, entry_id: int) -> bool
```

### 2.5 Use Cases (`domain/use_cases/`)

#### `AnalyzeDJSet`
- **Dependencies**: `ISetDownloader`, `IAudioSegmenter`, `IAudioDecoder`, `IFeatureExtractor`, `IAudioEmbedder`, `ITrackRepository`, `ISetRepository`, `ISeedRepository`, `IFingerprinter | None`, `ILLMService | None`.
- **Entry**: `async execute(source, destination_dir=..., use_shazam=True, use_comments=True, keep_audio=False, shazam_probes: int = 3, progress=None) -> DJSet`
- **Flow**:
  1. `download`: Streams audio file/URL to temporary disk storage via `ISetDownloader.fetch_set`.
  2. `segment`: Calls `IAudioSegmenter.detect_passages` to partition the set into coherent musical passages (semantic CLAP + acoustic novelty curves).
  3. `extract`: Emits per-passage `1/N .. N/N` feature extraction events (BPM & Camelot key) processed via bounded `ProcessPoolExecutor`.
  4. `embed`: Uses `_safe_interior()` boundary avoidance (inward shrink of 25s for >=90s, 10s for 45s-90s) to center 30s core windows cleanly away from transitions; computes CLAP embeddings in micro-batches (`<= 32`), frees raw PCM immediately, emits per-passage `1/N .. N/N` embed events.
  5. `match`: Queries vector index for top catalog matches per passage within +-5 BPM, emits per-passage `1/N .. N/N` match events.
  6. `identify`: First matches timestamps against comment tracklists (LLM parsed). For unidentified passages, executes multi-probe Shazam (`shazam_probes: int = 3`) sampling up to 3 candidate interior probe offsets (50% center, 30% early, 70% late) with early exit upon successful identification; wrapped under a 15s timeout with circuit breaker protection; emits per-passage `1/N .. N/N` identify events. Fast CLAP default runs instantly when `use_shazam=False`.
  7. `post-process & persist`: Runs `_merge_duplicate_passages()` to merge consecutive passages sharing identical exact IDs into single contiguous musical passages; clamps any boundary exceeding duration before creating `DJSet`, saves entity and LanceDB set embedding, auto-snowballs discovered artist names into high-priority seeds, and cleans up temporary set audio unless `keep_audio=True`.

#### `BuildSeedList`
- **Dependencies**: `ISeedDiscovery | None`, `ISeedRepository`, `ILLMService | None`
- **Entry**: `async execute(*, electronic_limit=1000, general_limit=300, max_depth=2, use_deezer=True, llm_genres=(), llm_count=0, exclude_artists=(), progress=None) -> BuildSeedListResult`
- **Flow**: Optionally runs Deezer BFS discovery with live `CrawlProgress` events -> persists via `record_discovery` (priority bump on rediscovery). Optionally asks LLM for seeds -> persists via `upsert_many`. Emits final `"writing"` progress event.

#### `CrawlITunesSeeds`
- **Dependencies**: `ICatalogProvider`, `ITrackRepository`, `ISeedRepository`
- **Entry**: `async execute(*, terms=..., tracks_per_term=200, expand_compilations=True, save_tracks=True, progress=None) -> CrawlITunesResult`
- **Flow**: Iterates keyword terms (e.g. techno labels, genres, artists) -> calls `crawl_keyword()` -> parses collaborators/remixers -> upserts new seed artists with electronic priority -> optionally persists catalog tracks.

#### `DigSimilarTracks`
- **Dependencies**: `ITrackRepository`
- **Entry**: `async execute(track_id, search_filter=None, *, bpm_tolerance=None, harmonic=False) -> DigResult`
- **Flow**: Loads reference by id -> validates embedding exists -> builds effective filter (intersects BPM tolerance window, expands Camelot keys if harmonic) -> over-fetches by 1 from vector index -> strips reference id -> trims to limit.

#### `FetchCatalogMetadata`
- **Dependencies**: `ISeedRepository`, `ICatalogProvider`, `ITrackRepository`
- **Entry**: `async execute(*, artists_limit=50, tracks_per_artist=50, retry_failed=False, progress=None) -> FetchMetadataResult`
- **Flow**: Selects pending (optionally failed) seeds by priority -> for each calls `list_artist_tracks` -> `upsert_many` tracks -> marks seed fetched/failed. Resumable.

#### `FindSimilarForSet`
- **Dependencies**: `ISetRepository`, `ITrackRepository`
- **Entry**: `async execute(set_id, *, limit=12, passage_limit=5) -> SimilarSetResult`
- **Flow**: Fetches stored `DJSet` -> queries whole-set vector similarities from LanceDB set index -> queries top track matches for each passage.

#### `IndexCatalog`
- **Dependencies**: `ITrackRepository`, `IAudioDecoder`, `IFeatureExtractor`, `IAudioEmbedder`, `Executor | None`, `cpu_workers=4`, `queue_maxsize=64`, `chunk_size=32`
- **Entry**: `async execute(*, limit=500, batch_size=16, max_failures=3, reindex=False, progress=None) -> IndexResult`
- **Flow**: Bounded producer-consumer. Producers download+decode previews via `decode_url(sample_rate=48000, channels=1)` -> enqueue to bounded `asyncio.Queue`. Consumer drains queue -> runs `extract()` on `ProcessPoolExecutor` -> accumulates batch -> calls `embed_batch()` via `asyncio.to_thread` -> `upsert_many` hydrated tracks. PCM released immediately per batch.

#### `ImportLocalLibrary`
- **Dependencies**: `ILocalLibraryScanner`, `IAudioDecoder`, `IFeatureExtractor`, `IAudioEmbedder`, `ITrackRepository`, `ISeedRepository`, `Executor | None`, `cpu_workers=4`
- **Entry**: `async execute(folder_path, recursive=True, batch_size=16, reindex=False, seed_artists=True, progress=None) -> ImportLocalLibraryResult`
- **Flow**: Recursively scans folder via `ffprobe` tag extraction -> skips already indexed tracks unless `reindex=True` -> extracts 30s centered core window (40%-45% duration) -> extracts BPM and Camelot key via process pool -> micro-batches CLAP embeddings -> upserts into `tracks` and LanceDB -> optionally seeds discovered artists with high electronic priority.

#### `ManageCatalog`
- **Dependencies**: `ITrackRepository`, `ISeedRepository`, `IBlacklistRepository`
- **Entry**:
  - `delete_track(track_id, *, blacklist=False, reason=None) -> DeleteTrackResult`
  - `delete_artist(artist_name, *, blacklist=False, reason=None) -> DeleteArtistResult`
  - `blacklist_artist(artist_name, *, reason=None) -> BlacklistEntry`
  - `blacklist_track(artist, title, *, reason=None) -> BlacklistEntry`
  - `list_blacklist(kind=None) -> Sequence[BlacklistEntry]`
  - `remove_from_blacklist(entry_id) -> bool`
- **Flow**: Strict Safe Deletion: Removes records from SQLite (`tracks`, `seed_artists`) and LanceDB (`track_vectors`), but **NEVER touches or deletes audio files on disk** (guaranteed safe for `local_path`). If `blacklist=True`, writes normalized deduplication entry to `blacklist` table so future iTunes crawls or local library scans automatically ignore that artist/track.

#### `VibeSearch`
- **Dependencies**: `ITrackRepository`, `IAudioEmbedder`
- **Entry**: `async execute(prompt, *, limit=20, bpm_tolerance=None) -> VibeResult`
- **Flow**: Converts prompt to vector via `IAudioEmbedder.embed_text` -> queries LanceDB vector index -> applies filter and returns ranked tracks.

---

## 3. Data Layer & Schemas

### 3.1 SQLite (`sqlite_client.py`)

**Connection setup**: WAL mode, `foreign_keys=ON`, `busy_timeout=5000`, `synchronous=NORMAL`. Single `aiosqlite.Connection` guarded by `asyncio.Lock`. Row factory = `aiosqlite.Row`.

#### Table `seed_artists`
| Column | Type | Constraints |
|---|---|---|
| `id` | `INTEGER` | PK AUTOINCREMENT |
| `name` | `TEXT NOT NULL` | |
| `name_normalized` | `TEXT NOT NULL` | UNIQUE |
| `deezer_id` | `TEXT` | UNIQUE WHERE NOT NULL |
| `priority_score` | `REAL NOT NULL DEFAULT 0.0` | CHECK 0.0-1.0 |
| `category` | `TEXT NOT NULL` | CHECK IN ('electronic', 'general') |
| `status` | `TEXT NOT NULL DEFAULT 'pending'` | CHECK IN ('pending', 'fetched', 'failed') |
| `source` | `TEXT NOT NULL DEFAULT 'unknown'` | |
| `created_at` / `updated_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |

**Indexes**: `idx_seed_artists_deezer_id` (unique, partial WHERE NOT NULL), `idx_seed_artists_status_priority` (status, priority_score DESC).

#### Table `tracks`
| Column | Type | Constraints |
|---|---|---|
| `id` | `TEXT` | PK |
| `itunes_track_id` | `TEXT` | UNIQUE |
| `title` | `TEXT NOT NULL` | |
| `artist` | `TEXT NOT NULL` | |
| `normalized_key` | `TEXT NOT NULL` | UNIQUE |
| `album`, `genre` | `TEXT` | |
| `duration_sec`, `bpm` | `REAL` | |
| `release_year` | `INTEGER` | |
| `preview_url`, `artwork_url`, `store_url` | `TEXT` | |
| `camelot_key` | `TEXT` | |
| `is_embedded`, `is_heard` | `INTEGER NOT NULL DEFAULT 0` | CHECK IN (0, 1) |
| `index_failures` | `INTEGER NOT NULL DEFAULT 0` | |
| `source` | `TEXT NOT NULL DEFAULT 'itunes'` | |
| `external_id`, `isrc` | `TEXT` | |
| `local_path` | `TEXT` | Path to local audio file (if source='local') |
| `created_at` / `updated_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |

**Indexes**: `idx_tracks_external_id` (source, external_id), `idx_tracks_bpm`, `idx_tracks_genre`, `idx_tracks_heard`.

#### Table `blacklist`
| Column | Type | Constraints |
|---|---|---|
| `id` | `INTEGER` | PK AUTOINCREMENT |
| `kind` | `TEXT NOT NULL` | CHECK IN ('artist', 'track') |
| `normalized_key` | `TEXT NOT NULL` | UNIQUE |
| `display_name` | `TEXT NOT NULL` | |
| `artist_name` | `TEXT` | |
| `track_title` | `TEXT` | |
| `reason` | `TEXT` | |
| `created_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |

**Indexes**: `idx_blacklist_kind` (kind), `idx_blacklist_created_at` (created_at DESC).

#### Table `dj_sets`
| Column | Type | Constraints |
|---|---|---|
| `id` | `TEXT` | PK |
| `title` | `TEXT NOT NULL` | |
| `source_url` | `TEXT` | |
| `duration_sec` | `REAL` | |
| `artist` | `TEXT` | |
| `thumbnail_url` | `TEXT` | |
| `bpm_min`, `bpm_max` | `REAL` | |
| `embedding_json` | `TEXT` | L2-normalized mean embedding |
| `created_at` / `updated_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | |

#### Table `set_passages`
| Column | Type | Constraints |
|---|---|---|
| `id` | `INTEGER` | PK AUTOINCREMENT |
| `set_id` | `TEXT NOT NULL` | FK -> dj_sets(id) ON DELETE CASCADE |
| `start_sec`, `end_sec` | `REAL NOT NULL` | |
| `bpm` | `REAL` | |
| `camelot_key` | `TEXT` | |
| `exact_id_match` | `INTEGER NOT NULL DEFAULT 0` | CHECK IN (0, 1) |
| `exact_id_title` | `TEXT` | |
| `exact_id_artist` | `TEXT` | |
| `exact_id_source` | `TEXT` | |
| `embedding_json` | `TEXT` | |
| `closest_matches_json` | `TEXT NOT NULL DEFAULT '[]'` | |
| UNIQUE(set_id, start_sec, end_sec) | | |

**Index**: `idx_set_passages_set_id` (set_id, start_sec).

### 3.2 LanceDB (`lancedb_client.py`)

**Tables**:
- `track_vectors`: CLAP embeddings for catalog tracks (512-dim, float16).
- `set_vectors`: Mean embeddings for analyzed DJ sets.
**Search**: `cosine` distance. IVF-PQ automatic indexing when table exceeds 10,000 vectors.
**Batch Deletion**: `delete_ids(track_ids)` deletes vectors in bounded 500-item chunks using SQL filter predicates (`id IN (...)`), guarded by table existence checks.

### 3.3 Remote Providers & Ingestion

#### `ITunesProvider` (`data/datasources/remote/itunes_provider.py`)
- Hard ceiling: 18 req/min enforced via `AsyncTokenBucket`.
- Keyword search: `crawl_keyword(keyword, limit=200, expand_compilations=True)` enables crawling techno labels, clubs, and compilation albums.
- Collaborator snowballing: `_discover_from_tracks()` extracts remixers/features into `SeedArtist` records.

#### `DeezerSeedCrawler` (`data/datasources/remote/deezer_seed_crawler.py`)
- BFS discovery starting from curated electronic artists with live `CrawlProgress` callbacks.

#### `YtDlpSetDownloader` (`data/datasources/remote/ytdlp_downloader.py`)
- Downloads and streams DJ set audio from YouTube/SoundCloud/Mixcloud into temporary files.
- Supports Netscape cookie files and browser profiles (`--cookies-from-browser`).
- Extracts video comments and metadata for tracklist parsing.

#### `ShazamFingerprinter` (`data/datasources/remote/shazam_client.py`)
- Exact-ID audio fingerprinting using lazy-loaded `shazamio`.
- Converts raw float32 mono PCM to in-memory 16-bit WAV containers.
- **Strict 15.0s Timeout**: Each recognize call is wrapped in `asyncio.wait_for(..., timeout=15.0)`.
- **Circuit Breaker**: After 5 consecutive timeouts or network errors, `is_circuit_open = True` and subsequent calls are skipped cleanly with clear warning logs. Success resets the counter. `reset_circuit_breaker()` provides manual reset.
- **Immediate Cancellation**: Never catches or swallows `asyncio.CancelledError`, allowing immediate GUI cancellation.

### 3.4 ML Engine

#### `SetSegmenter` (`data/ml/set_segmenter.py`)
- Accepts optional `embedder: IAudioEmbedder | None = None`.
- Streams 16 kHz audio without loading full set into RAM.
- **Semantic + Acoustic Novelty**: When embedder is present, extracts semantic novelty curves by sliding 10s audio buffers across the set, computing cosine distance between adjacent CLAP embeddings, merged with STFT onset flux, chroma, and MFCC pooled novelty curves.
- Checkerboard filter detects musical transition boundaries with automatic acoustic fallback.
- **Strict Passage Clamping**: Intermediate boundaries are rounded `< total_duration_seconds`. Terminal pieces strictly clamp `p_end = min(round(piece_end, 3), total_duration_seconds)`, guaranteeing no passage ever exceeds `total_duration_seconds`.

#### `ClapAudioEmbedder` (`data/ml/clap_embedder.py`)
- Model: `laion/clap-htsat-unfused` (512-dim).
- FP16 inference under `torch.inference_mode()` with `torch.amp.autocast("cuda", dtype=float16)`.
- Bounded micro-batches (`<= 32`), lazy model loading on first inference.

#### `LibrosaFeatureExtractor` (`data/ml/librosa_analyzer.py`)
- BPM estimation with octave tempo folding to `[70, 175]`.
- Constant-Q chromagram correlated against Krumhansl-Schmuckler key profiles to detect Camelot notation (`8A`, `11B`, etc.).

---

## 4. Wiring, Presentation & Web GUI

### 4.1 Container (`container.py`)

Single Composition Root wired in `Container.start()`:
1. `SQLiteClient` & `LanceDBClient`
2. `SQLiteSeedRepository`, `HybridTrackRepository`, `SQLiteSetRepository`, `SQLiteBlacklistRepository`
3. `Shared HTTP Client` (httpx)
4. `ITunesProvider`, `DeezerSeedCrawler`, `MultiLLMClient`, `LocalLibraryScanner`
5. `FFmpegAudioDecoder`, `LibrosaFeatureExtractor`, `ClapAudioEmbedder`, `HardwareProbe`
6. `SetSegmenter(embedder=clap_embedder)`, `YtDlpSetDownloader`, `ShazamFingerprinter`
7. All 10 Use Cases: `BuildSeedList`, `DigSimilarTracks`, `FetchCatalogMetadata`, `IndexCatalog`, `AnalyzeDJSet`, `FindSimilarForSet`, `CrawlITunesSeeds`, `ImportLocalLibrary`, `ManageCatalog`, `VibeSearch`

### 4.2 CLI Commands (`presentation/cli/commands.py`)

All outputs enforce ASCII-only strings for Windows console compatibility.
- `dig check-hw`: Verify FFmpeg, CUDA, VRAM, and RAM.
- `dig seed-crawl`: Deezer BFS discovery with live Rich progress.
- `dig seed-llm`: Prompt LLM for genre-specific seed artists.
- `dig seed-itunes`: Crawl iTunes keywords, labels, or compilations.
- `dig fetch-metadata`: Ingest tracks from pending seeds (18 req/min ceiling).
- `dig index`: Batch decode, analyze, and embed catalog tracks.
- `dig import-local <folder>`: Scan local folders, middle-window decode, embed, and seed artists.
- `dig list-tracks`: View indexed catalog tracks.
- `dig dig <track_id>`: Audio similarity search with BPM and harmonic key filtering.
- `dig analyze-set <source>`: Full DJ set analysis with multi-probe Shazam (`--shazam-probes 1..3`) and live progress.
- `dig show-set <set_id>`: View tracklist, passage matches, or set similarity.
- `dig list-sets`: List analyzed sets and ID counts.
- `dig mark-heard <track_id>`: Mark track as heard for `--exclude-heard` filtering.
- `dig stats`: Rich seed, track, local vs iTunes breakdown, and top genres summary.
- `dig delete-track <track_id>`: Delete track from DB/vector index without touching audio on disk; optional `--blacklist`.
- `dig delete-artist <artist_name>`: Delete artist, their tracks, and seeds without touching audio on disk; optional `--blacklist`.
- `dig blacklist-list`: List blacklisted artists and tracks.
- `dig blacklist-remove <entry_id>`: Remove an entry from the blacklist.

### 4.3 Web API & GUI (`presentation/api/` & `frontend/`)

- **FastAPI Backend** (`presentation/api/app.py`):
  - REST endpoints for catalog, sets, hardware probe, jobs, analytics, artists, and blacklist.
  - Server-Sent Events (SSE) streaming on `/api/jobs/stream`.
  - Static file hosting for `frontend/`.
- **Catalog Management & Analytics Endpoints** (`presentation/api/routes/catalog.py`):
  - `GET /api/catalog/analytics`: Overall counts, genres, BPM distribution, Camelot keys, sources.
  - `GET /api/catalog/artists`: Searchable, paginated artists summary with track counts and samples.
  - `GET /api/catalog/artists/{name}/tracks`: Tracks for an artist (for drawer accordion).
  - `DELETE /api/catalog/tracks/{id}`: Safe track deletion; optional `blacklist` and `reason`.
  - `DELETE /api/catalog/artists/{name}`: Safe artist deletion; optional `blacklist` and `reason`.
  - `GET /api/catalog/blacklist`, `POST /api/catalog/blacklist`, `DELETE /api/catalog/blacklist/{id}`: Blacklist CRUD.
- **JobManager** (`presentation/api/job_manager.py`):
  - Strictly serial execution (1 background job at a time).
  - Supported jobs: `index`, `import-local`, `seed-crawl`, `seed-llm`, `seed-itunes`, `fetch-metadata`, `analyze-set`.
  - Live progress broadcasting (stage, processed, total, failed, speed, memory).
  - Turbo indexing mode for high-throughput batching.
- **Frontend Architecture** (`frontend/`):
  - 100% vanilla ES modules, no build tools, zero external dependencies or CDNs.
  - Views:
    - `run`: Interactive form for launching any job, real-time progress bar, live speed in `tracks/s` or `passages/s`, VRAM/RAM metrics, and scrollable `#job-log` event stream.
    - `dig`: Interactive track similarity engine with HTML5 audio preview player and Camelot wheel visualizer; track rows include quick delete action button with confirmation & blacklist toggle.
    - `sets`: DJ set analysis viewer, passage-by-passage timeline, Shazam/comment match badges, track digging, and quick deletion actions.
    - `stats`: Complete Library Overview & Manager:
      - KPI summary cards (Total Tracks, Embedded %, Total Artists, Local Files, Active Blacklist).
      - Visual distribution bars for Top Genres, BPM Buckets, and Camelot Harmonics.
      - Artists Directory: live search filter, sort dropdown (most tracks, most embedded, A-Z), pagination, inline expandable tracks drawer with direct playback and per-track delete.
      - Artist Action Menu: Delete artist with optional blacklist checkbox.
      - Blacklist Management tab: filter by artist/track, add new blacklist entry modal, unblock button.

---

## 5. Current State & Implementation Details

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
├── EmbeddingError
├── SetDownloadError
└── FingerprintError
```

### 5.2 Critical Bug Fixes & Architectural Hardening

1. **Floating-Point Duration Clamping (Bug 1)**:
   - Sets with float durations (e.g. `7374.262857`) could previously produce a final passage `end_seconds` rounded up to `7374.263`, violating strict set duration bounds.
   - Fixed with a 3-layer safeguard:
     - `SetSegmenter._build_passages`: clamps terminal piece `p_end = min(round(piece_end, 3), total_duration_seconds)`.
     - `DJSet.__post_init__`: allows `0.05s` tolerance and auto-clamps within tolerance.
     - `AnalyzeDJSet._build_set`: clamps any passage boundary exceeding duration before creating `DJSet`.
2. **Shazam Timeout & Circuit Breaker (Bug 2)**:
   - Shazam network calls now run under `asyncio.wait_for(timeout=15.0)`.
   - A consecutive failure counter triggers a circuit breaker after 5 errors/timeouts, skipping subsequent calls with a warning.
   - Automatically reset at the start of every `analyze-set` job in `JobManager._run_analyze_set` and `AnalyzeDJSet.execute()` so a tripped breaker from a previous set never persists to new sets.
   - `asyncio.CancelledError` is never caught, enabling immediate cancellation.
   - Fast CLAP default: when Shazam is unchecked in GUI or `--no-shazam` is passed, analysis completes without network stalling.
3. **True Live Per-Passage Progress**:
   - `AnalyzeDJSet` emits incremental `1/N .. N/N` progress events across all pipeline stages: `extract` (BPM/Key), `embed`, `match` (top track & similarity %), and `identify` (Shazam match or timeout).
   - `JobManager` calculates speed and transmits events to GUI's `#job-log` panel.
4. **Domain Purity**:
   - `backend/src/domain/` imports exclusively from the Python standard library. Enforced via AST scan in `test_domain_purity.py`.

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

### 6.5 `backend/src/data/ml/set_segmenter.py`

```python
"""Transition segmentation for long DJ sets.

Plays the DigDeeper role of splitting a multi-hour recording into musically
coherent passages. The audio is decoded **once** as a 16 kHz mono stream in
bounded blocks (a 3 h set peaks at ~40 MB of PCM per block instead of the
~690 MB a full decode would need), pooled into a tiny ~2 fps feature matrix
(spectral flux + chroma + MFCC, ≤ ~25 MB even for 3 h), and a Foote-style
**checkerboard kernel** novelty score is evaluated over candidate passage
lengths (90-360 s). Peaks in the novelty curve become passage boundaries;
passages are then normalized to realistic DJ lengths (short ones merged,
long flat regions subdivided evenly).

All heavy work is synchronous and safe to run through ``asyncio.to_thread``
from the use case; ffmpeg runs as a subprocess via an injectable stream
factory so tests can feed synthetic PCM without touching the network.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterator, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from domain.interfaces.audio_engine import IAudioSegmenter
from domain.value_objects.audio_features import TimeRange

from ..errors import AudioDecodeError, FFmpegNotFoundError

LOGGER = logging.getLogger(__name__)

#: Segmentation only needs spectral shape, not pitch fidelity: 16 kHz mono
#: keeps peak RAM under ~600 MB even for a 3-hour set.
SEGMENT_SAMPLE_RATE = 16_000
#: Novelty features per second. ~2 fps is plenty for 90-360 s passages and
#: keeps the whole-set feature matrix in the low megabytes.
FEATURE_FPS = 2.0
#: Audio block decoded at once (streamed through ffmpeg stdout).
BLOCK_SECONDS = 600.0
#: Realistic DJ passage bounds: transitions every 1.5-6 minutes.
MIN_PASSAGE_SECONDS = 90.0
MAX_PASSAGE_SECONDS = 360.0
#: Candidate passage lengths for the checkerboard kernel, in seconds.
CANDIDATE_PASSAGE_SECONDS: tuple[float, ...] = (90.0, 120.0, 180.0, 240.0, 300.0, 360.0)
#: Blocks are processed with a small lookback so STFT frames spanning block
#: edges are not double counted or dropped.
BLOCK_OVERLAP_SECONDS = 4.0

StftHop = 512
StftNfft = 2048
PoolGroup = int(SEGMENT_SAMPLE_RATE / StftHop / FEATURE_FPS)  # ~15.6 -> 16 frames
_FLUX_DIM = 1
_CHROMA_DIM = 12
_MFCC_DIM = 13

StreamFactory = Callable[[Sequence[str]], Iterator[bytes]]


def default_stream_factory(ffmpeg_bin: str) -> StreamFactory:
    """Spawn one blocking ffmpeg subprocess and yield its PCM stdout."""

    def factory(args: Sequence[str]) -> Iterator[bytes]:
        import subprocess

        try:
            process = subprocess.Popen(
                [ffmpeg_bin, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise FFmpegNotFoundError(
                f"ffmpeg binary not found ({ffmpeg_bin!r}); install FFmpeg and "
                "make sure it is on PATH"
            ) from exc
        except OSError as exc:
            raise AudioDecodeError(f"ffmpeg could not be started: {exc}") from exc

        assert process.stdout is not None
        try:
            while True:
                chunk = process.stdout.read(1_048_576)
                if not chunk:
                    break
                yield chunk
            returncode = process.wait(timeout=30)
            if returncode != 0:
                stderr = process.stderr.read() if process.stderr else b""
                detail = stderr.decode("utf-8", "replace").strip().splitlines()
                tail = detail[-1] if detail else "no stderr output"
                raise AudioDecodeError(f"ffmpeg failed with code {returncode}: {tail}")
        finally:
            if process.stderr:
                process.stderr.close()
            if process.stdout:
                process.stdout.close()
            if process.poll() is None:
                process.kill()

    return factory


class SetSegmenter(IAudioSegmenter):
    """Stream-based novelty segmentation of a DJ set file on disk."""

    def __init__(
        self,
        *,
        ffmpeg_bin: str = "ffmpeg",
        sample_rate: int = SEGMENT_SAMPLE_RATE,
        feature_fps: float = FEATURE_FPS,
        block_seconds: float = BLOCK_SECONDS,
        min_passage_seconds: float = MIN_PASSAGE_SECONDS,
        max_passage_seconds: float = MAX_PASSAGE_SECONDS,
        candidate_passage_seconds: Sequence[float] = CANDIDATE_PASSAGE_SECONDS,
        stream_factory: StreamFactory | None = None,
    ) -> None:
        if sample_rate < 1:
            raise ValueError("sample_rate must be positive")
        if feature_fps <= 0:
            raise ValueError("feature_fps must be positive")
        if min_passage_seconds <= 0 or max_passage_seconds < min_passage_seconds:
            raise ValueError("passage bounds must satisfy 0 < min <= max")
        self._ffmpeg_bin = ffmpeg_bin
        self._sample_rate = sample_rate
        self._feature_fps = feature_fps
        self._block_seconds = block_seconds
        self._min_passage = min_passage_seconds
        self._max_passage = max_passage_seconds
        self._candidates = tuple(candidate_passage_seconds)
        self._stream_factory = stream_factory or default_stream_factory(ffmpeg_bin)

    # ------------------------------------------------------------------ API

    def plan_segments(
        self,
        total_duration_seconds: float,
        *,
        window_seconds: float = 30.0,
        hop_seconds: float = 15.0,
    ) -> Sequence[TimeRange]:
        """Return fixed analysis windows covering the set (interface method)."""
        if total_duration_seconds <= 0:
            raise ValueError("total_duration_seconds must be positive")
        if window_seconds <= 0 or hop_seconds <= 0:
            raise ValueError("window_seconds and hop_seconds must be positive")
        windows: list[TimeRange] = []
        start = 0.0
        while start < total_duration_seconds - 1e-9:
            end = min(start + window_seconds, total_duration_seconds)
            if end - start <= 0:
                break
            windows.append(TimeRange(start, end))
            start += hop_seconds
        return tuple(windows)

    def detect_passages(
        self,
        path: Path,
        total_duration_seconds: float,
    ) -> Sequence[TimeRange]:
        """Detect ordered, non-overlapping passages in ``path``."""
        if total_duration_seconds <= 0:
            raise ValueError("total_duration_seconds must be positive")
        features, feature_times = self._stream_features(path, total_duration_seconds)
        if len(features) == 0:
            return (TimeRange(0.0, total_duration_seconds),)

        boundaries = self._pick_boundaries(
            self._novelty_curve(features), feature_times, total_duration_seconds
        )
        return self._build_passages(boundaries, total_duration_seconds)

    # -------------------------------------------------------------- features

    def _ffmpeg_args(self, path: Path) -> list[str]:
        return [
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vn",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ac",
            "1",
            "-ar",
            str(self._sample_rate),
            "pipe:1",
        ]

    def _stream_features(
        self, path: Path, total_duration_seconds: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Stream the file through ffmpeg and return pooled features + times.

        Returns ``(features, times)`` where ``features`` has shape
        ``(frames, dims)`` (L2-normalized rows) and ``times[i]`` is the time of
        the frame start in seconds.
        """
        block_samples = int(self._block_seconds * self._sample_rate)
        overlap_samples = int(BLOCK_OVERLAP_SECONDS * self._sample_rate)

        feature_blocks: list[np.ndarray] = []
        time_blocks: list[np.ndarray] = []
        covered_until = 0.0  # seconds fully processed so far
        buffer = bytearray()
        bytes_per_sample = 4

        for chunk in self._stream_factory(self._ffmpeg_args(path)):
            buffer.extend(chunk)
            while len(buffer) >= (block_samples + overlap_samples) * bytes_per_sample:
                block = np.frombuffer(
                    buffer[: (block_samples + overlap_samples) * bytes_per_sample],
                    dtype=np.float32,
                )
                frames, frame_times = self._block_features(block)
                if frames.size:
                    # `frame_times` are block-relative; the +overlap lookahead
                    # only exists so frames near the block edge are complete.
                    keep = frame_times < self._block_seconds
                    feature_blocks.append(frames[keep])
                    time_blocks.append(frame_times[keep] + covered_until)
                covered_until += self._block_seconds
                del buffer[: block_samples * bytes_per_sample]

        if buffer:
            block = np.frombuffer(buffer, dtype=np.float32)
            frames, frame_times = self._block_features(block)
            if frames.size:
                # The final block was never processed, so keep every frame;
                # its start is exactly `covered_until` (== samples dropped so
                # far), which the +offset already accounts for.
                feature_blocks.append(frames)
                time_blocks.append(frame_times + covered_until)

        if not feature_blocks:
            return np.zeros((0, 0), dtype=np.float32), np.zeros(0)

        features = np.concatenate(feature_blocks, axis=0)
        times = np.concatenate(time_blocks)
        norms = np.linalg.norm(features, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        features = features / norms
        # A declared duration longer than the actual audio must not leave the
        # tail uncovered; clamp frame times to the declared duration.
        return features.astype(np.float32), np.minimum(
            times, max(total_duration_seconds, 0.0)
        )

    def _block_features(self, block: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Compute pooled flux+chroma+mfcc features for one PCM block."""
        import librosa

        samples = np.asarray(block, dtype=np.float32)
        if samples.size < StftNfft:
            return np.zeros((0, 0), dtype=np.float32), np.zeros(0)

        common: dict[str, Any] = {
            "y": samples,
            "sr": self._sample_rate,
            "n_fft": StftNfft,
            "hop_length": StftHop,
            "center": False,
        }
        flux = librosa.onset.onset_strength(
            y=samples, sr=self._sample_rate, hop_length=StftHop, n_fft=StftNfft
        )
        chroma = librosa.feature.chroma_stft(**common)
        mfcc = librosa.feature.mfcc(**common, n_mfcc=_MFCC_DIM)

        frame_count = min(flux.size, chroma.shape[1], mfcc.shape[1])
        stacked = np.vstack(
            [
                flux[np.newaxis, :frame_count],
                chroma[:, :frame_count],
                mfcc[:, :frame_count],
            ]
        ).T.astype(np.float32)  # (frame_count, dims)

        # Pool ~16 STFT frames (0.5 s) into one novelty frame (~2 fps).
        groups = max(1, frame_count // PoolGroup)
        pooled = stacked[: groups * PoolGroup].reshape(
            groups, PoolGroup, stacked.shape[1]
        )
        features = pooled.mean(axis=1)
        frame_times = np.arange(groups, dtype=np.float64) * (
            PoolGroup * StftHop / self._sample_rate
        )
        return features, frame_times

    # --------------------------------------------------------------- novelty

    def _novelty_curve(self, features: np.ndarray) -> np.ndarray:
        """Checkerboard-kernel novelty, maximized over candidate lags.

        For a candidate passage length ``L`` (half-window ``h = L/2`` frames)
        and boundary position ``t``, the checkerboard score is

            Nov(t) = sum_{i,j} K(i,j) * S(t-h+i, t-h+j)

        with ``+1`` for same-side kernel cells and ``-1`` across the boundary.
        Expanding the similarity ``S(a, b) = X[a] . X[b]`` by lag collapses the
        double sum into weighted boxcar sums of the lag correlation ``R(l, t)``,
        which keeps memory at O(frames) instead of materializing a self-
        similarity matrix.
        """
        total_frames = features.shape[0]
        novelty = np.full(total_frames, -np.inf, dtype=np.float64)
        frame_duration = 1.0 / self._feature_fps

        for candidate in self._candidates:
            half = round(candidate * self._feature_fps / 2.0)
            if half < 2 or 2 * half > total_frames:
                continue
            score = self._checkerboard_scores(features, half)
            if score.size == 0:
                continue
            valid = novelty[half : half + score.size]
            np.maximum(valid, score, out=valid)
            novelty[half : half + score.size] = valid

        novelty[~np.isfinite(novelty)] = 0.0
        # Candidate lags overlap; the max over lags can be noisy at the very
        # edges, so smooth with a small centered moving average (~5 s).
        return _moving_average(novelty, round(5.0 / frame_duration))

    @staticmethod
    def _checkerboard_scores(features: np.ndarray, half: int) -> np.ndarray:
        """Checkerboard novelty for one half-window size, all valid positions."""
        total_frames = features.shape[0]
        span = 2 * half
        # Per-lag local correlation R(l, t) = X[t] . X[t + l].
        lag_weights = np.empty(span, dtype=np.float64)
        novelty = np.zeros(total_frames - span + 1, dtype=np.float64)
        for lag in range(1, span):
            if lag >= half:
                lag_weights[lag] = -(span - lag)
            else:
                lag_weights[lag] = 2.0 * half - 3.0 * lag
            correlation = np.einsum(
                "ft,ft->f",
                features[: total_frames - lag],
                features[lag:],
                optimize=True,
            )
            cumulative = np.concatenate(([0.0], np.cumsum(correlation)))
            # Boxcar sum of correlation over positions [t, t + span - lag):
            # Nov(j) += c_l * (cum[j + span - lag] - cum[j]).
            positions = np.arange(0, len(novelty))
            box = cumulative[positions + span - lag] - cumulative[positions]
            novelty += lag_weights[lag] * box
        # The lag-0 diagonal is constant (L2-normalized rows) and drops out.
        return novelty

    # -------------------------------------------------------------- passages

    def _pick_boundaries(
        self,
        novelty: np.ndarray,
        feature_times: np.ndarray,
        total_duration_seconds: float,
    ) -> list[float]:
        """Pick novelty peaks, separated by at least ``min_passage``."""
        if novelty.size < 3 or float(novelty.std()) < 1e-9:
            return []  # flat/degenerate audio: rely on subdivision only
        # 3 sigma: stationary material produces tiny numerical ripples that
        # must not be mistaken for transitions.
        threshold = float(novelty.mean() + 3.0 * novelty.std())
        min_gap = max(1, round(self._min_passage * self._feature_fps))
        candidates = [
            index
            for index in range(1, novelty.size - 1)
            if novelty[index] >= novelty[index - 1]
            and novelty[index] >= novelty[index + 1]
            and novelty[index] >= threshold
        ]
        selected: list[int] = []
        for index in sorted(candidates, key=lambda i: novelty[i], reverse=True):
            if all(abs(index - chosen) >= min_gap for chosen in selected):
                selected.append(index)
        times = [
            float(feature_times[index])
            for index in sorted(selected)
            if 0.0 < float(feature_times[index]) < total_duration_seconds
        ]
        return times

    def _build_passages(
        self,
        boundaries: Sequence[float],
        total_duration_seconds: float,
    ) -> tuple[TimeRange, ...]:
        """Turn boundaries into passages honoring the min/max passage bounds."""
        edges = [0.0]
        for boundary in boundaries:
            r_b = round(boundary, 3)
            if 0.0 < r_b < total_duration_seconds:
                edges.append(r_b)
        # Always use unrounded total_duration_seconds for the terminal edge;
        # never round upward past total_duration_seconds.
        edges.append(total_duration_seconds)
        edges = sorted(set(edges))

        # Merge sections shorter than the minimum into their weaker neighbour
        # (greedily into the previous section; the first into the next).
        sections = list(edges)
        changed = True
        while changed and len(sections) > 2:
            changed = False
            for index in range(len(sections) - 1):
                if sections[index + 1] - sections[index] < self._min_passage:
                    if index == 0:
                        del sections[1]
                    elif index + 2 == len(sections):
                        del sections[-2]
                    else:
                        # Drop the boundary of the shorter adjacent section.
                        left = sections[index] - sections[index - 1]
                        right = sections[index + 2] - sections[index + 1]
                        del sections[index + 1 if right >= left else index]
                    changed = True
                    break

        # Subdivide long flat regions evenly; equal splits of a >max region
        # always stay >= min because max >= 2 * min by construction.
        passages: list[TimeRange] = []
        for s_idx, (start, end) in enumerate(pairwise(sections)):
            span = end - start
            if span <= 0:
                continue
            parts = max(1, math.ceil(span / self._max_passage - 1e-9))
            step = span / parts
            is_last_section = s_idx == len(sections) - 2
            for part in range(parts):
                piece_start = start + part * step
                piece_end = piece_start + step if part < parts - 1 else end
                is_last_piece = is_last_section and (part == parts - 1)

                p_start = round(piece_start, 3)
                if is_last_piece:
                    # NEVER round upward past total_duration_seconds
                    p_end = min(round(piece_end, 3), total_duration_seconds)
                    if p_end <= p_start:
                        p_start = round(max(0.0, p_end - 0.001), 3)
                else:
                    p_end = min(round(piece_end, 3), total_duration_seconds)

                if p_end > p_start:
                    passages.append(TimeRange(p_start, p_end))
        return tuple(passages)


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average with edge truncation (no padding)."""
    if window <= 1 or values.size <= window:
        return values
    half = window // 2
    kernel = np.ones(window, dtype=np.float64) / window
    smoothed = np.convolve(values, kernel, mode="same")
    smoothed[:half] = values[:half]
    smoothed[-half:] = values[-half:]
    return smoothed


__all__ = [
    "SEGMENT_SAMPLE_RATE",
    "SetSegmenter",
]

```

### 6.6 `backend/src/data/datasources/remote/shazam_client.py`

```python
"""Exact-ID fingerprinting through ``shazamio``.

Each passage contributes a ~12 s snippet; recognition runs under a semaphore
(default 3) with small jitter so Shazam's public endpoint is never hammered.
Unreleased IDs, unknown tracks, and network hiccups all degrade gracefully to
``None`` — "no match" must never abort an analysis. ``shazamio`` is imported
lazily inside the recognition path and snippets are wrapped into a WAV
container in memory (stdlib ``wave``) because raw PCM has no recognizable
container header.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import random
import struct
import wave
from collections.abc import Callable
from typing import Any

from domain.entities.track import AudioBuffer, TrackReference
from domain.interfaces.audio_engine import IFingerprinter

from ...errors import FingerprintError

LOGGER = logging.getLogger(__name__)

#: Parallel recognition ceiling — polite toward the public Shazam endpoint.
MAX_CONCURRENCY = 3
#: Extra delay between recognitions to space out bursts.
JITTER_SECONDS = 0.25


RecognizerFactory = Callable[[], Any]


class ShazamFingerprinter(IFingerprinter):
    """Async-only fingerprinter backed by the ``shazamio`` service."""

    def __init__(
        self,
        *,
        recognizer_factory: RecognizerFactory | None = None,
        max_concurrency: int = MAX_CONCURRENCY,
        jitter_seconds: float = JITTER_SECONDS,
        timeout_seconds: float = 15.0,
        max_consecutive_failures: int = 5,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if jitter_seconds < 0:
            raise ValueError("jitter_seconds must not be negative")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1")
        self._recognizer_factory = recognizer_factory or self._default_factory
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._jitter_seconds = jitter_seconds
        self._timeout_seconds = timeout_seconds
        self._max_consecutive_failures = max_consecutive_failures
        self._recognizer: Any | None = None
        self._consecutive_failures: int = 0
        self._circuit_open: bool = False

    # ------------------------------------------------------------------ API

    @property
    def is_circuit_open(self) -> bool:
        """True when consecutive timeouts/errors have opened the circuit breaker."""
        return self._circuit_open

    def reset_circuit_breaker(self) -> None:
        """Reset the consecutive failure count and close the circuit breaker."""
        self._consecutive_failures = 0
        self._circuit_open = False

    def compute(self, audio: AudioBuffer) -> str:
        """Stable content fingerprint (sha256 of the PCM bytes)."""
        return hashlib.sha256(audio.pcm_bytes).hexdigest()

    def identify(self, audio: AudioBuffer) -> Any | None:
        """Sync seam: unsupported — Shazam recognition is async-only.

        The interface's :meth:`identify_async` is the real entry point; the
        sync variant returns ``None`` (documented "unidentified") instead of
        blocking or raising inside a running event loop.
        """
        LOGGER.debug(
            "ShazamFingerprinter.identify is sync-unsupported; use identify_async"
        )
        return None

    async def identify_async(self, audio: AudioBuffer) -> TrackReference | None:
        """Recognize one snippet; ``None`` means "no confident match"."""
        if self._circuit_open:
            LOGGER.warning("Shazam circuit breaker open; skipping recognition call")
            return None

        try:
            recognizer = self._ensure_recognizer()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - missing shazamio degrades to None
            LOGGER.warning("Shazam recognizer unavailable: %s", exc)
            return None

        wav_bytes = pcm_to_wav(audio)
        async with self._semaphore:
            if self._jitter_seconds:
                await asyncio.sleep(random.uniform(0.05, self._jitter_seconds))
            try:
                result = await asyncio.wait_for(
                    self._recognize(recognizer, wav_bytes),
                    timeout=self._timeout_seconds,
                )
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                self._consecutive_failures += 1
                LOGGER.warning(
                    "Shazam recognition timed out after %.1fs (failure %d/%d)",
                    self._timeout_seconds,
                    self._consecutive_failures,
                    self._max_consecutive_failures,
                )
                if self._consecutive_failures >= self._max_consecutive_failures:
                    self._circuit_open = True
                    LOGGER.warning(
                        "Shazam circuit breaker opened after %d consecutive failures; skipping subsequent calls",
                        self._consecutive_failures,
                    )
                return None
            except Exception as exc:  # noqa: BLE001 - one bad snippet must not fail the set
                self._consecutive_failures += 1
                LOGGER.debug(
                    "Shazam recognition failed (failure %d/%d): %s",
                    self._consecutive_failures,
                    self._max_consecutive_failures,
                    exc,
                )
                if self._consecutive_failures >= self._max_consecutive_failures:
                    self._circuit_open = True
                    LOGGER.warning(
                        "Shazam circuit breaker opened after %d consecutive failures; skipping subsequent calls",
                        self._consecutive_failures,
                    )
                return None

        self._consecutive_failures = 0
        return self._reference_from_result(result)

    # ------------------------------------------------------------ internals

    @staticmethod
    def _default_factory() -> Any:
        from shazamio import Shazam  # lazy: heavy dependency graph

        return Shazam()

    def _ensure_recognizer(self) -> Any:
        if self._recognizer is None:
            self._recognizer = self._recognizer_factory()
        return self._recognizer

    @staticmethod
    async def _recognize(recognizer: Any, wav_bytes: bytes) -> Any:
        recognize = getattr(recognizer, "recognize", None)
        if recognize is None:
            recognize = recognizer.full_recognize
        return await recognize(wav_bytes)

    @staticmethod
    def _reference_from_result(result: Any) -> TrackReference | None:
        if not isinstance(result, dict):
            return None
        track = result.get("track")
        if not isinstance(track, dict):
            return None  # unrecognized or unreleased: Shazam found no track
        title = str(track.get("title") or "").strip()
        subtitle = str(track.get("subtitle") or "").strip()
        if not title or not subtitle:
            return None
        try:
            return TrackReference(
                artist=subtitle,
                title=title,
                confidence=1.0,
            )
        except (TypeError, ValueError):
            return None


def pcm_to_wav(audio: AudioBuffer) -> bytes:
    """Wrap mono float32 PCM into a 16-bit WAV container in memory."""
    if audio.sample_rate <= 0:
        raise FingerprintError("audio sample rate must be positive")
    count = len(audio.pcm_bytes) // 4
    samples = struct.unpack(f"<{count}f", audio.pcm_bytes[: count * 4])
    int16 = b"".join(
        struct.pack("<h", max(-32768, min(32767, int(sample * 32767.0))))
        for sample in samples
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(audio.sample_rate)
        handle.writeframes(int16)
    return buffer.getvalue()


__all__ = ["MAX_CONCURRENCY", "ShazamFingerprinter", "pcm_to_wav"]

```

### 6.7 `backend/src/domain/use_cases/analyze_dj_set.py`

```python
"""Use case: analyze a full DJ set into passages, IDs, and matches.

Pipeline (memory-bounded for 16 GB RAM / 6 GB VRAM):

1. ``ISetDownloader.fetch_set`` resolves a URL or local file to audio on disk
   (downloaded files land in the storage cache and are marked temporary).
2. ``IAudioSegmenter.detect_passages`` streams a 16 kHz mono view to find
   musically coherent passages — the full set is never decoded into RAM.
3. For every passage, only a clean 30 s window from its middle (skipping
   crossfade edges) is decoded at a time; BPM/key extraction runs on the
   bounded CPU pool and the 30 s buffers are embedded on GPU in FP16
   micro-batches, then released immediately.
4. Exact IDs come from two sources: comment timestamps parsed by the local
   LLM (matched within ±45 s of a passage) and async fingerprinting
   (Shazam) for passages the comments could not name.
5. Every passage — including unreleased "no-ID" ones — gets its closest
   catalog tracks within ±5 BPM (DigDeeper's "closest we found").
6. The set's tempo range and L2-normalized mean embedding are persisted
   through ``ISetRepository``; discovered artist names snowball into the seed
   list; the temporary download is deleted unless ``keep_audio`` is set.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..entities.dj_set import DJSet, DownloadedSet, Passage, TrackMatch
from ..entities.search import SearchFilter
from ..entities.track import SeedArtist, TrackReference
from ..interfaces.audio_engine import (
    IAudioDecoder,
    IAudioEmbedder,
    IAudioSegmenter,
    IFeatureExtractor,
    IFingerprinter,
    ISetDownloader,
)
from ..interfaces.llm import ILLMService
from ..interfaces.repositories import ISeedRepository, ISetRepository, ITrackRepository
from ..value_objects.audio_features import (
    BPM,
    BPM_MAX,
    BPM_MIN,
    AudioFeatures,
    EmbeddingVector,
    TimeRange,
)

LOGGER = logging.getLogger(__name__)

#: GPU micro-batch ceiling for the 6 GB card (AnalysisBatch rule from AGENTS).
MAX_EMBED_BATCH = 16
DEFAULT_CORE_WINDOW_SECONDS = 30.0
DEFAULT_SNIPPET_SECONDS = 12.0
DEFAULT_BPM_MATCH_TOLERANCE = 5.0
DEFAULT_ID_MATCH_TOLERANCE_SECONDS = 45.0
DEFAULT_MAX_MATCHES_PER_PASSAGE = 5
#: Snowball priority for artists discovered inside DJ sets.
DISCOVERY_PRIORITY = 0.9


@dataclass(frozen=True, slots=True)
class AnalyzeEvent:
    """Progress event emitted at each pipeline stage."""

    stage: str
    completed: int
    total: int
    message: str = ""
    failed: int = 0


class AnalyzeDJSet:
    """Analyze one DJ set end-to-end and persist it for set-to-set digging."""

    def __init__(
        self,
        *,
        set_downloader: ISetDownloader,
        audio_segmenter: IAudioSegmenter,
        audio_decoder: IAudioDecoder,
        feature_extractor: IFeatureExtractor,
        audio_embedder: IAudioEmbedder,
        track_repository: ITrackRepository,
        set_repository: ISetRepository,
        seed_repository: ISeedRepository,
        fingerprinter: IFingerprinter | None = None,
        llm_service: ILLMService | None = None,
        cpu_executor: Executor | None = None,
        cpu_workers: int = 4,
        embed_batch_size: int = MAX_EMBED_BATCH,
        core_window_seconds: float = DEFAULT_CORE_WINDOW_SECONDS,
        snippet_seconds: float = DEFAULT_SNIPPET_SECONDS,
        bpm_match_tolerance: float = DEFAULT_BPM_MATCH_TOLERANCE,
        id_match_tolerance_seconds: float = DEFAULT_ID_MATCH_TOLERANCE_SECONDS,
        max_matches_per_passage: int = DEFAULT_MAX_MATCHES_PER_PASSAGE,
    ) -> None:
        if cpu_workers < 1:
            raise ValueError("cpu_workers must be at least 1")
        if not 1 <= embed_batch_size <= MAX_EMBED_BATCH:
            raise ValueError(
                f"embed_batch_size must be between 1 and {MAX_EMBED_BATCH}"
            )
        if core_window_seconds <= 0 or snippet_seconds <= 0:
            raise ValueError("window sizes must be positive")
        self._set_downloader = set_downloader
        self._audio_segmenter = audio_segmenter
        self._audio_decoder = audio_decoder
        self._feature_extractor = feature_extractor
        self._audio_embedder = audio_embedder
        self._track_repository = track_repository
        self._set_repository = set_repository
        self._seed_repository = seed_repository
        self._fingerprinter = fingerprinter
        self._llm_service = llm_service
        self._cpu_executor = cpu_executor
        self._cpu_workers = cpu_workers
        self._embed_batch_size = embed_batch_size
        self._core_window_seconds = core_window_seconds
        self._snippet_seconds = snippet_seconds
        self._bpm_tolerance = bpm_match_tolerance
        self._id_tolerance = id_match_tolerance_seconds
        self._max_matches = max_matches_per_passage

    async def execute(
        self,
        source: str,
        *,
        destination_dir: Path,
        use_shazam: bool = True,
        use_comments: bool = True,
        keep_audio: bool = False,
        progress: Callable[[AnalyzeEvent], None] | None = None,
    ) -> DJSet:
        """Analyze ``source`` and return the persisted :class:`DJSet`."""
        downloaded = await self._set_downloader.fetch_set(
            source, destination_dir, fetch_comments=use_comments
        )
        self._notify(progress, "download", 1, 1, downloaded.title)

        try:
            if downloaded.duration_seconds is None:
                raise ValueError(
                    "the downloaded set has no duration; cannot segment it"
                )
            duration = downloaded.duration_seconds

            if self._fingerprinter is not None and hasattr(
                self._fingerprinter, "reset_circuit_breaker"
            ):
                self._fingerprinter.reset_circuit_breaker()

            ranges = await asyncio.to_thread(
                self._audio_segmenter.detect_passages,
                downloaded.audio_path,
                duration,
            )
            if not ranges:
                ranges = (TimeRange(0.0, duration),)
            self._notify(
                progress, "segment", len(ranges), len(ranges), f"{len(ranges)} passages"
            )

            own_executor = self._cpu_executor is None
            executor = self._cpu_executor or ProcessPoolExecutor(
                max_workers=self._cpu_workers
            )
            try:
                passages = await self._analyze_passages(
                    downloaded, ranges, executor, progress
                )
                passages = await self._identify_passages(
                    downloaded,
                    passages,
                    use_shazam=use_shazam,
                    use_comments=use_comments,
                    progress=progress,
                )
            finally:
                if own_executor:
                    executor.shutdown(wait=True)

            dj_set = self._build_set(source, downloaded, passages)
            await self._set_repository.save(dj_set)
            self._notify(progress, "persist", 1, 1, dj_set.id)
            await self._snowball(passages, downloaded)
            return dj_set
        finally:
            if downloaded.is_temporary and not keep_audio:
                await asyncio.to_thread(_delete_quietly, downloaded.audio_path)

    # --------------------------------------------------------- core windows

    def _core_window(self, passage_range: TimeRange) -> TimeRange:
        """Clean 30 s window centered in the passage (crossfades skipped)."""
        span = passage_range.duration_seconds
        window = min(self._core_window_seconds, span)
        middle = passage_range.start_seconds + span / 2.0
        start = middle - window / 2.0
        return TimeRange(start, start + window)

    async def _analyze_passages(
        self,
        downloaded: DownloadedSet,
        ranges: Sequence[TimeRange],
        executor: Executor,
        progress: Callable[[AnalyzeEvent], None] | None,
    ) -> list[Passage]:
        """Decode/extract/embed in chunks so RAM holds one batch of windows."""
        loop = asyncio.get_running_loop()
        passages: list[Passage] = []
        extract_completed = 0
        embed_completed = 0
        total_passages = len(ranges)

        for chunk_start in range(0, total_passages, self._embed_batch_size):
            chunk = list(ranges[chunk_start : chunk_start + self._embed_batch_size])
            buffers = []
            for passage_range in chunk:
                core = self._core_window(passage_range)
                buffers.append(
                    await self._audio_decoder.decode_segment(
                        downloaded.audio_path,
                        core,
                        sample_rate=48_000,
                        channels=1,
                    )
                )

            tasks = [
                loop.run_in_executor(executor, self._feature_extractor.extract, b)
                for b in buffers
            ]
            features: list[Any] = []
            for p_range, fut in zip(chunk, tasks):
                try:
                    feature = await fut
                except Exception as exc:  # noqa: BLE001
                    feature = exc
                features.append(feature)
                extract_completed += 1
                extracted = _coerce_features(feature)
                bpm_str = f"{extracted.bpm.value:.0f} BPM" if extracted.bpm else "? BPM"
                key_str = f", {extracted.key.notation}" if extracted.key else ""
                self._notify(
                    progress,
                    "extract",
                    extract_completed,
                    total_passages,
                    f"{_range_label(p_range)} ({bpm_str}{key_str})",
                )

            vectors = await asyncio.to_thread(self._audio_embedder.embed_batch, buffers)
            # PCM is dead the moment embeddings exist.
            buffers.clear()

            chunk_passages: list[Passage] = []
            for p_range, feature, vector in zip(chunk, features, vectors):
                extracted = _coerce_features(feature)
                passage = Passage(
                    time_range=p_range,
                    bpm=extracted.bpm,
                    key=extracted.key,
                    embedding=vector,
                )
                chunk_passages.append(passage)
                embed_completed += 1
                self._notify(
                    progress,
                    "embed",
                    embed_completed,
                    total_passages,
                    _range_label(p_range),
                )

            passages.extend(chunk_passages)
            await self._attach_closest_matches(
                passages,
                start=len(passages) - len(chunk_passages),
                progress=progress,
                total=total_passages,
            )
        return passages

    async def _attach_closest_matches(
        self,
        passages: list[Passage],
        *,
        start: int,
        progress: Callable[[AnalyzeEvent], None] | None = None,
        total: int | None = None,
    ) -> None:
        """Fill each new passage's top catalog matches within ±5 BPM."""
        total_count = total or len(passages)
        for index in range(start, len(passages)):
            passage = passages[index]
            matches: tuple[TrackMatch, ...] = ()
            if passage.embedding is not None:
                try:
                    matches = await self._find_closest(passage)
                except Exception:
                    LOGGER.exception(
                        "closest-track lookup failed for %s", passage.time_range
                    )
            if matches:
                passages[index] = replace(passage, closest_matches=matches)
                top = matches[0]
                detail = f": top {top.track.display_name} ({top.similarity_percent:.0f}%)"
            else:
                detail = ": no close match"
            self._notify(
                progress,
                "match",
                index + 1,
                total_count,
                f"{_range_label(passage.time_range)}{detail}",
            )

    async def _find_closest(self, passage: Passage) -> tuple[TrackMatch, ...]:
        assert passage.embedding is not None
        bpm_min: float | None = None
        bpm_max: float | None = None
        if passage.bpm is not None:
            bpm_min = max(BPM_MIN, passage.bpm.value - self._bpm_tolerance)
            bpm_max = min(BPM_MAX, passage.bpm.value + self._bpm_tolerance)
        search_filter = SearchFilter(
            limit=self._max_matches,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
        )
        return tuple(
            await self._track_repository.find_similar(passage.embedding, search_filter)
        )

    # --------------------------------------------------------- exact IDs

    async def _identify_passages(
        self,
        downloaded: DownloadedSet,
        passages: list[Passage],
        *,
        use_shazam: bool,
        use_comments: bool,
        progress: Callable[[AnalyzeEvent], None] | None,
    ) -> list[Passage]:
        """Fill exact-id fields from comments first, then Shazam for the rest."""
        comment_references: tuple[TrackReference, ...] = ()
        if use_comments and self._llm_service is not None and downloaded.comments:
            try:
                comment_references = tuple(
                    await self._llm_service.extract_tracklist_from_comments(
                        downloaded.comments, context=downloaded.title
                    )
                )
            except Exception as exc:  # noqa: BLE001 - LLM failure must not kill analysis
                # An unconfigured or overloaded LLM must never kill an analysis.
                LOGGER.warning("LLM tracklist extraction skipped: %s", exc)

        total_passages = len(passages)
        identified: list[Passage] = []
        failed_count = 0

        for idx, passage in enumerate(passages, start=1):
            identified_passage = self._match_comment_reference(
                passage, comment_references
            )
            msg = ""
            if identified_passage.exact_id_match:
                msg = f"Comments {idx}/{total_passages}: {identified_passage.exact_id_display_name}"
            elif use_shazam and self._fingerprinter is not None:
                if getattr(self._fingerprinter, "is_circuit_open", False):
                    failed_count += 1
                    msg = f"Shazam {idx}/{total_passages}: skipped (circuit open)"
                else:
                    shazam_result = await self._shazam_passage(
                        downloaded, identified_passage
                    )
                    if shazam_result.exact_id_match:
                        identified_passage = shazam_result
                        msg = f"Shazam {idx}/{total_passages}: matched {identified_passage.exact_id_display_name}"
                    else:
                        failed_count += 1
                        msg = f"Shazam {idx}/{total_passages}: no match / timed out"
            else:
                msg = f"Passage {idx}/{total_passages}: unidentified"

            identified.append(identified_passage)
            self._notify(
                progress,
                "identify",
                idx,
                total_passages,
                message=msg,
                failed=failed_count,
            )

        return identified

    def _match_comment_reference(
        self, passage: Passage, references: Sequence[TrackReference]
    ) -> Passage:
        """Attach the best comment reference within ±45 s of the passage."""
        middle = (
            passage.time_range.start_seconds + passage.time_range.duration_seconds / 2.0
        )
        best: TrackReference | None = None
        for reference in references:
            start = (
                reference.timestamp.start_seconds
                if reference.timestamp is not None
                else None
            )
            if start is None:
                continue
            if abs(start - middle) > self._id_tolerance:
                continue
            if best is None or reference.confidence > best.confidence:
                best = reference
        if best is None:
            return passage
        return replace(
            passage,
            exact_id_match=True,
            exact_id_title=best.title,
            exact_id_artist=best.artist,
            exact_id_source="comments",
        )

    async def _shazam_passage(
        self, downloaded: DownloadedSet, passage: Passage
    ) -> Passage:
        assert self._fingerprinter is not None
        span = passage.time_range.duration_seconds
        middle = passage.time_range.start_seconds + span / 2.0
        window = min(self._snippet_seconds, span)
        try:
            snippet = await self._audio_decoder.decode_segment(
                downloaded.audio_path,
                TimeRange(middle - window / 2.0, middle + window / 2.0),
                sample_rate=16_000,
                channels=1,
            )
            reference = await self._fingerprinter.identify_async(snippet)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - fingerprinting is best-effort
            LOGGER.warning(
                "Shazam identification failed for %s: %s", passage.time_range, exc
            )
            return passage
        if reference is None:
            return passage
        return replace(
            passage,
            exact_id_match=True,
            exact_id_title=reference.title,
            exact_id_artist=reference.artist,
            exact_id_source="shazam",
        )

    # ------------------------------------------------------------- persist

    def _build_set(
        self,
        source: str,
        downloaded: DownloadedSet,
        passages: Sequence[Passage],
    ) -> DJSet:
        duration = downloaded.duration_seconds
        clamped_passages: list[Passage] = []
        for p in passages:
            if duration is not None and p.time_range.end_seconds > duration:
                start = min(p.time_range.start_seconds, max(0.0, duration - 0.001))
                clamped_passages.append(
                    replace(p, time_range=TimeRange(start, duration))
                )
            else:
                clamped_passages.append(p)

        bpms = [p.bpm.value for p in clamped_passages if p.bpm is not None]
        embedding = _mean_embedding([p.embedding for p in clamped_passages])
        return DJSet(
            id=f"set-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:12]}",
            title=downloaded.title,
            source_url=downloaded.source_url,
            duration_seconds=downloaded.duration_seconds,
            artist=downloaded.artist,
            thumbnail_url=downloaded.thumbnail_url,
            bpm_min=BPM(min(bpms)) if bpms else None,
            bpm_max=BPM(max(bpms)) if bpms else None,
            embedding=embedding,
            passages=tuple(clamped_passages),
        )

    async def _snowball(
        self, passages: Sequence[Passage], downloaded: DownloadedSet
    ) -> None:
        """Auto-enqueue newly discovered artist names as high-priority seeds."""
        names: dict[str, str] = {}
        for passage in passages:
            if passage.exact_id_artist:
                names[passage.exact_id_artist.casefold()] = passage.exact_id_artist
        if not names:
            return
        seeds = [
            SeedArtist(
                name=name,
                priority_score=DISCOVERY_PRIORITY,
                category="electronic",
                status="pending",
                source="dj-set",
            )
            for name in sorted(names.values())
        ]
        try:
            await self._seed_repository.record_discovery(seeds)
        except Exception:
            LOGGER.exception("seed snowballing failed; analysis result is kept")

    @staticmethod
    def _notify(
        progress: Callable[[AnalyzeEvent], None] | None,
        stage: str,
        completed: int,
        total: int,
        message: str = "",
        failed: int = 0,
    ) -> None:
        if progress is not None:
            progress(
                AnalyzeEvent(
                    stage=stage,
                    completed=completed,
                    total=total,
                    message=message,
                    failed=failed,
                )
            )


# ------------------------------------------------------------------ helpers


def _coerce_features(feature: Any) -> AudioFeatures:
    """Pass through AudioFeatures; failed extractions degrade to empty."""
    if feature is None or isinstance(feature, BaseException):
        return AudioFeatures()
    return feature


def _range_label(passage_range: TimeRange) -> str:
    minutes = int(passage_range.start_seconds // 60)
    seconds = int(passage_range.start_seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"


def _mean_embedding(
    vectors: Sequence[EmbeddingVector | None],
) -> EmbeddingVector | None:
    """L2-normalized mean of the given vectors (None when there are none)."""
    present = [vector for vector in vectors if vector is not None]
    if not present:
        return None
    dimension = len(present[0].values)
    mean = [0.0] * dimension
    for vector in present:
        if len(vector.values) != dimension:
            raise ValueError("passage embeddings have mixed dimensions")
        for index, value in enumerate(vector.values):
            mean[index] += value
    count = float(len(present))
    norm = math.sqrt(math.fsum(value * value / (count * count) for value in mean))
    if norm <= 0.0:
        return None
    normalized = tuple(value / count / norm for value in mean)
    return EmbeddingVector(values=normalized, dimension=dimension)


def _delete_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("could not delete temporary set audio %s", path)


__all__ = ["MAX_EMBED_BATCH", "AnalyzeDJSet", "AnalyzeEvent"]

```
