# DigDeeper Local — Agent Guide

DigDeeper Local is a **100% local** DJ set analyzer and audio similarity engine, inspired by
digdeeper.fm and designed for consumer hardware. It ingests DJ sets and 30-second catalog
previews, identifies passages, extracts musical features, and searches a disk-backed embedding
index. No cloud services, no Docker, no data leaves the machine.

## Current phase

**Phase 3 — Local Audio Compute Engine, streaming catalog indexer, and "Dig" similarity search.**

- `backend/src/domain/` owns entities, value objects, interfaces, and pure use cases.
- `backend/src/data/` implements SQLite/LanceDB storage, Deezer discovery, iTunes metadata,
  the local LLM client, and the ML stack (`data/ml/`: FFmpeg decoder, librosa analyzer,
  CLAP embedder, hardware probe).
- `backend/src/presentation/cli/` exposes the `dig` command.
- `frontend/`, FastAPI routers, DJ set analysis (`yt-dlp`/segmentation) remain later phases.

Phase 3 pipeline rules (all enforced, not suggestions):

- Previews are downloaded straight into RAM and piped through an `ffmpeg` stdin/stdout
  subprocess (`f32le` 48 kHz mono). **Previews are never written to disk.**
- Downloads/decodes run under a semaphore (default 16) with a bounded hand-off queue
  (`asyncio.Queue(maxsize=64)`); PCM buffers are released immediately after each batch.
- BPM/key extraction runs on a `ProcessPoolExecutor` (default 4 workers, ceiling
  6); the worker function imports librosa/numpy lazily so the parent process
  stays light.
- CLAP inference (`laion/clap-htsat-unfused`, 512-dim) runs under `torch.inference_mode()`
  plus `torch.amp.autocast("cuda", float16)` when CUDA is available, with automatic CPU
  fallback. Models lazy-load on first use — `dig stats` stays instant.
- torch is installed from the CUDA wheel index (`pytorch-cu124`) via `[tool.uv.sources]`
  in `backend/pyproject.toml`; do not replace it with CPU-only wheels.

## Non-negotiable architecture

Strict Clean Architecture with source-code dependencies pointing **inward**:

```
presentation  ──►  domain  ◄──  data
       ▲                         │
       └──────── container ──────┘
```

- `domain/` owns entities, value objects, abstract interfaces, and use cases. It depends on
  **nothing** outside the Python standard library.
- `data/` implements the ABCs declared in `domain/interfaces/`. It may depend on `domain/`.
- `presentation/` depends on `domain/` (use cases and interfaces), never on concrete `data/`
  classes.
- `backend/src/container.py` is the **Composition Root** and the only place where concrete
  implementations are imported and wired together.

### The Domain Dependency Rule

`backend/src/domain/` MUST import **only the Python standard library**.

Forbidden inside `domain/`, without exception:

- Other layers: `data`, `presentation`, `container`, `src.*`.
- Web/HTTP: FastAPI, Starlette, Pydantic, httpx, requests, aiohttp, urllib3, `http`, `urllib`,
  `socket`.
- ML/audio: PyTorch, torchaudio, transformers, NumPy, SciPy, librosa, soundfile, essentia,
  madmom, aubio, CLAP, Hugging Face Hub.
- Storage: LanceDB, PyArrow, SQLite (`sqlite3`), SQLAlchemy, Alembic, pandas.
- Integrations: yt-dlp, mutagen, python-dotenv, any LLM SDK.

Rules of thumb:

- Use **relative imports** for all intra-domain imports.
- No I/O, network, database, filesystem reads/writes, subprocesses, clocks, randomness, or
  framework logging in `domain/`.
- Domain objects are frozen, validated dataclasses. Raise `TypeError` for wrong types and
  `ValueError` for invalid values.
- Collections exposed by domain objects are immutable tuples or frozensets.

`backend/tests/domain/test_domain_purity.py` enforces this rule with an AST scan. Any new import
that violates it must fail CI.

### SOLID

- **Single Responsibility**: one reason to change per module/class.
- **Open/Closed**: new catalog providers, embedders, and repositories implement existing ABCs;
  they do not modify domain code.
- **Liskov Substitution**: every data-layer implementation must honor the interface contract,
  including documented limits and error behavior.
- **Interface Segregation**: small, focused ABCs (`IAudioDecoder`, `IAudioEmbedder`,
  `IFingerprinter`, ...), not one god interface.
- **Dependency Inversion**: use cases depend on domain ABCs. Concrete classes are injected by
  `container.py`.

### External dependencies

Every external dependency (iTunes, LLM, PyTorch/CLAP, FFmpeg, LanceDB, SQLite, fingerprinting)
must be represented by an ABC in `domain/interfaces/`. Implementations live in `data/`.
Wiring happens **only** in `backend/src/container.py`.

## Target hardware and performance budget

These are hard constraints, not suggestions.

| Component | Target | Rule |
|---|---|---|
| CPU | AMD Ryzen 5 5600X (6C / 12T) | Bounded process pools for CPU-bound audio analysis: default 4 workers, ceiling 6. Never spawn unbounded pools. |
| GPU | NVIDIA GTX 1660 Super (6 GB VRAM) | PyTorch CUDA with FP16 (`torch.float16`), `batch_size <= 32`, Hugging Face `transformers` model `laion/clap-htsat-unfused`. Keep peak VRAM below 4 GB. Do NOT switch to `laion/larger_clap_music`: its hub checkpoint ships an untrained audio tower (all audio embeddings collapse to ~0.99 similarity). |
| RAM | 16 GB DDR4 | Never load full audio datasets or full vector indices into memory. |
| OS | Windows / Linux | No Docker containers. Native processes and FFmpeg. |

### Audio and memory rules

- Stream **30-second previews** through FFmpeg pipes into RAM, extract features/embeddings, then
  immediately discard the raw PCM. Do not cache decoded preview audio.
- Full DJ sets are downloaded to disk and decoded **window by window** (`TimeRange` windows);
  never load a whole set into memory.
- Store embeddings as **float16** vectors in a disk-backed **LanceDB** index.
- Store track metadata, heard history, seed artists, and DJ set records in **SQLite**.
- Do not load the entire vector index into RAM for a query; use LanceDB's disk-backed search.
- Clear CUDA caches between batches; on VRAM pressure reduce batch size (32 → 16 → 8) before
  falling back to CPU.

### iTunes catalog rate limits

- **Maximum 18 requests per minute** against iTunes metadata endpoints (search, lookup, artist
  listings). This is a hard ceiling, below Apple's nominal limit.
- Serialize metadata calls with a token bucket / rate limiter; no parallel bursts.
- Cache responses and deduplicate lookups.
- On HTTP 429 or 5xx, back off exponentially and respect `Retry-After`; never retry in a tight
  loop.
- Preview media downloads are separate from metadata calls but must remain polite and bounded.

### Catalog scope

All genres are supported. Seed generation and crawling target approximately:

- **75% electronic / club**: Techno, Melodic Techno, Progressive House, Deep House, Afro House,
  Tech House, Trance, Indie Dance, Minimal, Drum & Bass.
- **25% general**: Pop, Hip-Hop, Arabic, Latin, Rock.

## Repository layout

```
backend/
  pyproject.toml
  src/
    container.py                 # Composition Root (wiring only)
    domain/
      entities/                  # Track, SeedArtist, AudioBuffer, DJSet, SearchFilter...
      value_objects/             # BPM, CamelotKey, TimeRange, EmbeddingVector, HardwareInfo...
      interfaces/                # ABCs for repositories, catalog, audio, LLM, hardware
      use_cases/                 # pure orchestration (IndexCatalog, DigSimilarTracks, ...)
    data/
      datasources/local/         # SQLite + LanceDB clients
      datasources/remote/        # Deezer, iTunes, rate limiting
      llm/                       # OpenAI-compatible local LLM client
      ml/                        # FFmpegAudioDecoder, LibrosaFeatureExtractor,
                                 # ClapAudioEmbedder, HardwareProbe
      mappers/                   # row <-> domain mapping
      repositories/              # SQLiteSeedRepository, HybridTrackRepository
    presentation/cli/            # Typer + Rich `dig` command
  tests/domain/                  # pure unit tests + AST purity test
  tests/data/                    # adapter tests with mocked HTTP / temp DBs
frontend/                        # placeholder for a later phase
storage/                         # runtime data; git-ignored
```

## Environment

Copy `.env.example` to `.env` at the repository root and adjust values. Required keys include:

- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_FAST_MODEL`, `LLM_AUDIO_MODEL`
- `STORAGE_DIR`
- `DEVICE=cuda`

`STORAGE_DIR` is resolved relative to the repository root by the future container.

## Commands

From `backend/`:

```bash
uv sync                 # create .venv and install runtime + dev dependencies
uv run pytest                 # run domain and data tests
uv run pytest tests/domain/test_domain_purity.py -q
uv run dig --help             # CLI entry point
uv run dig check-hw           # verify ffmpeg / torch / CUDA / VRAM / RAM
uv run dig seed-crawl --electronic-limit 1000 --general-limit 300
uv run dig seed-llm --genre "Melodic Techno & Afro House" --count 100
uv run dig fetch-metadata --artists-limit 50
uv run dig index --limit 500 --batch-size 16
uv run dig list-tracks --limit 20
uv run dig dig <track_id> --limit 10 --bpm-tolerance 4 --harmonic
uv run dig stats
```

With standard pip:

```bash
python -m venv .venv
.venv/Scripts/pip install pytest     # Windows
# .venv/bin/pip install pytest       # Linux/macOS
.venv/Scripts/python -m pytest
```

## Testing rules

- All domain behavior is covered by `pytest` unit tests.
- Every value object has boundary, type, and immutability tests.
- Camelot harmonic compatibility is tested for same key, relative major/minor, ±1 neighbours,
  and 12↔1 wrap-around.
- The AST purity test must remain green; do not weaken it to accommodate a shortcut.
- No network, GPU, FFmpeg, or database access in domain tests.
- ML adapter tests use injected fakes (fake ffmpeg runners, tiny fake CLAP models,
  synthetic sine/click PCM) — they never download HuggingFace weights or hit the network.
  The only network touchpoint is `httpx.MockTransport`.
