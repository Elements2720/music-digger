"""Composition Root for DigDeeper Local.

This is the only module allowed to import concrete data-layer implementations.
The CLI and a future API layer depend on the wired interfaces exposed here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import httpx
from dotenv import load_dotenv

from data.datasources.local.lancedb_client import SET_VECTOR_SCHEMA, LanceDBClient
from data.datasources.local.sqlite_client import SQLiteClient
from data.datasources.remote.deezer_seed_crawler import DeezerSeedCrawler
from data.datasources.remote.itunes_provider import ITunesProvider
from data.datasources.remote.shazam_client import ShazamFingerprinter
from data.datasources.remote.ytdlp_downloader import YtDlpSetDownloader
from data.llm.multi_llm_client import MultiLLMClient
from data.ml.clap_embedder import ClapAudioEmbedder
from data.ml.ffmpeg_decoder import FFmpegAudioDecoder
from data.ml.hardware_probe import HardwareProbe
from data.ml.librosa_analyzer import LibrosaFeatureExtractor
from data.ml.set_segmenter import SetSegmenter
from data.repositories.seed_repository import SQLiteSeedRepository
from data.repositories.set_repository import HybridSetRepository
from data.repositories.track_repository import HybridTrackRepository
from domain.use_cases import (
    AnalyzeDJSet,
    BuildSeedList,
    DigSimilarTracks,
    FetchCatalogMetadata,
    FindSimilarForSet,
    IndexCatalog,
    VibeSearch,
)

LOGGER = logging.getLogger(__name__)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration resolved from environment variables."""

    repo_root: Path
    storage_dir: Path
    sqlite_path: Path
    lancedb_path: Path
    llm_base_url: str
    llm_api_key: str
    llm_fast_model: str
    llm_timeout_seconds: float
    itunes_country: str
    itunes_rate_limit_per_minute: int
    itunes_timeout_seconds: float
    deezer_rate_limit_per_second: float
    deezer_timeout_seconds: float
    seed_crawl_max_depth: int
    catalog_electronic_ratio: float
    device: str
    clap_model_id: str
    clap_batch_size: int
    cpu_workers: int
    preview_concurrency: int
    preview_timeout_seconds: float
    ffmpeg_timeout_seconds: float
    index_queue_maxsize: int
    set_cache_dir: Path
    ytdlp_cookies_file: Path | None
    ytdlp_cookies_from_browser: str | None

    @classmethod
    def from_env(cls, repo_root: Path | None = None) -> Settings:
        """Load ``.env`` from the repository root and resolve paths."""
        root = (repo_root or REPOSITORY_ROOT).resolve()
        load_dotenv(root / ".env", override=False)

        storage_dir = _resolve_path(
            root,
            os.getenv("STORAGE_DIR", "./storage"),
        )
        sqlite_path = _resolve_path(
            root,
            os.getenv("SQLITE_PATH", str(storage_dir / "app.db")),
        )
        lancedb_path = _resolve_path(
            root,
            os.getenv("LANCEDB_PATH", str(storage_dir / "lancedb")),
        )
        rate_limit = _env_int("ITUNES_RATE_LIMIT_PER_MINUTE", 18)
        if rate_limit > 18:
            LOGGER.warning(
                "ITUNES_RATE_LIMIT_PER_MINUTE=%s exceeds the hard 18/min ceiling; "
                "clamping",
                rate_limit,
            )
        deezer_rate = _env_float("DEEZER_RATE_LIMIT_PER_SEC", 8.0)
        if deezer_rate > 8.0:
            LOGGER.warning(
                "DEEZER_RATE_LIMIT_PER_SEC=%s exceeds the hard 8/sec ceiling; clamping",
                deezer_rate,
            )
        clap_batch_size = _env_int("CLAP_BATCH_SIZE", 16)
        if clap_batch_size > 48:
            LOGGER.warning(
                "CLAP_BATCH_SIZE=%s exceeds the hard 48 cap (6 GB VRAM budget); clamping",
                clap_batch_size,
            )
        # Default 4 of the 10-worker ceiling: leaves RAM headroom on 16 GB
        # machines when browsers/DAWs are open alongside the indexer.
        cpu_workers = _env_int("ANALYSIS_MAX_WORKERS", 4)
        if cpu_workers > 10:
            LOGGER.warning(
                "ANALYSIS_MAX_WORKERS=%s exceeds the 10-worker budget for a "
                "6C/12T CPU; clamping",
                cpu_workers,
            )
        preview_concurrency = _env_int("PREVIEW_CONCURRENCY", 16)
        if preview_concurrency > 24:
            LOGGER.warning(
                "PREVIEW_CONCURRENCY=%s exceeds the 24-download budget; clamping",
                preview_concurrency,
            )
        # YouTube bot-gate bypass: a Netscape cookies.txt wins over the
        # browser name (mirrors yt-dlp's own --cookies precedence).
        cookies_file_raw = os.getenv("YTDLP_COOKIES_FILE")
        cookies_browser_raw = os.getenv("YTDLP_COOKIES_FROM_BROWSER")
        return cls(
            repo_root=root,
            storage_dir=storage_dir,
            sqlite_path=sqlite_path,
            lancedb_path=lancedb_path,
            llm_base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
            llm_api_key=os.getenv("LLM_API_KEY", "local"),
            llm_fast_model=os.getenv("LLM_FAST_MODEL", "qwen2.5:7b-instruct"),
            llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", 120.0),
            itunes_country=os.getenv("ITUNES_COUNTRY", "US").upper(),
            itunes_rate_limit_per_minute=max(1, min(18, rate_limit)),
            itunes_timeout_seconds=_env_float("ITUNES_TIMEOUT_SECONDS", 30.0),
            deezer_rate_limit_per_second=max(0.1, min(8.0, deezer_rate)),
            deezer_timeout_seconds=_env_float("DEEZER_TIMEOUT_SECONDS", 30.0),
            seed_crawl_max_depth=_env_int("SEED_CRAWL_MAX_DEPTH", 2),
            catalog_electronic_ratio=_env_float("CATALOG_ELECTRONIC_RATIO", 0.75),
            device=os.getenv("DEVICE", "cuda"),
            clap_model_id=os.getenv("CLAP_MODEL_ID", "laion/clap-htsat-unfused"),
            clap_batch_size=max(1, min(48, clap_batch_size)),
            cpu_workers=max(1, min(10, cpu_workers)),
            preview_concurrency=max(1, min(24, preview_concurrency)),
            preview_timeout_seconds=_env_float("PREVIEW_TIMEOUT_SECONDS", 30.0),
            ffmpeg_timeout_seconds=_env_float("FFMPEG_TIMEOUT_SECONDS", 60.0),
            index_queue_maxsize=max(1, _env_int("INDEX_QUEUE_MAXSIZE", 64)),
            set_cache_dir=_resolve_path(
                root,
                os.getenv("SET_CACHE_DIR", str(storage_dir / "cache")),
            ),
            ytdlp_cookies_file=(
                _resolve_path(root, cookies_file_raw) if cookies_file_raw else None
            ),
            ytdlp_cookies_from_browser=(
                cookies_browser_raw if cookies_browser_raw else None
            ),
        )


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


class Container:
    """Owns the application's wired service graph."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.sqlite: SQLiteClient | None = None
        self.vectors: LanceDBClient | None = None
        self.seed_repository: SQLiteSeedRepository | None = None
        self.track_repository: HybridTrackRepository | None = None
        self.http_client: httpx.AsyncClient | None = None
        self.itunes_provider: ITunesProvider | None = None
        self.deezer_crawler: DeezerSeedCrawler | None = None
        self.llm_service: MultiLLMClient | None = None
        self.audio_decoder: FFmpegAudioDecoder | None = None
        self.feature_extractor: LibrosaFeatureExtractor | None = None
        self.clap_embedder: ClapAudioEmbedder | None = None
        self.hardware_probe: HardwareProbe | None = None
        self.set_vectors: LanceDBClient | None = None
        self.set_repository: HybridSetRepository | None = None
        self.set_downloader: YtDlpSetDownloader | None = None
        self.set_segmenter: SetSegmenter | None = None
        self.shazam_fingerprinter: ShazamFingerprinter | None = None
        self.analyze_dj_set: AnalyzeDJSet | None = None
        self.find_similar_for_set: FindSimilarForSet | None = None
        self.build_seed_list: BuildSeedList | None = None
        self.fetch_catalog_metadata: FetchCatalogMetadata | None = None
        self.index_catalog: IndexCatalog | None = None
        self.dig_similar_tracks: DigSimilarTracks | None = None
        self.vibe_search: VibeSearch | None = None
        self._started = False

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def start(self) -> None:
        """Open storage, build adapters, and wire use cases."""
        if self._started:
            return
        settings = self.settings
        settings.storage_dir.mkdir(parents=True, exist_ok=True)

        sqlite = SQLiteClient(settings.sqlite_path)
        await sqlite.connect()
        vectors = LanceDBClient(settings.lancedb_path)
        await vectors.connect()
        seed_repository = SQLiteSeedRepository(sqlite)
        track_repository = HybridTrackRepository(sqlite, vectors)

        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.itunes_timeout_seconds),
            headers={"User-Agent": "DigDeeperLocal/0.1"},
        )
        itunes_provider = ITunesProvider(
            http_client=http_client,
            seed_repository=seed_repository,
            country=settings.itunes_country,
            rate_limit_per_minute=settings.itunes_rate_limit_per_minute,
            timeout_seconds=settings.itunes_timeout_seconds,
        )
        deezer_crawler = DeezerSeedCrawler(
            http_client=http_client,
            rate_limit_per_second=settings.deezer_rate_limit_per_second,
            timeout_seconds=settings.deezer_timeout_seconds,
        )
        llm_service = MultiLLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_fast_model,
            http_client=http_client,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        audio_decoder = FFmpegAudioDecoder(
            http_client=http_client,
            download_concurrency=settings.preview_concurrency,
            timeout_seconds=settings.preview_timeout_seconds,
            ffmpeg_timeout_seconds=settings.ffmpeg_timeout_seconds,
        )
        feature_extractor = LibrosaFeatureExtractor()
        clap_embedder = ClapAudioEmbedder(
            model_id=settings.clap_model_id,
            device=settings.device,
            batch_size=settings.clap_batch_size,
        )
        hardware_probe = HardwareProbe()

        self.sqlite = sqlite
        self.vectors = vectors
        self.seed_repository = seed_repository
        self.track_repository = track_repository
        self.http_client = http_client
        self.itunes_provider = itunes_provider
        self.deezer_crawler = deezer_crawler
        self.llm_service = llm_service
        self.audio_decoder = audio_decoder
        self.feature_extractor = feature_extractor
        self.clap_embedder = clap_embedder
        self.hardware_probe = hardware_probe
        self.build_seed_list = BuildSeedList(
            discovery=deezer_crawler,
            seed_repository=seed_repository,
            llm_service=llm_service,
        )
        self.fetch_catalog_metadata = FetchCatalogMetadata(
            seed_repository=seed_repository,
            catalog_provider=itunes_provider,
            track_repository=track_repository,
        )
        self.index_catalog = IndexCatalog(
            track_repository=track_repository,
            audio_decoder=audio_decoder,
            feature_extractor=feature_extractor,
            audio_embedder=clap_embedder,
            cpu_workers=settings.cpu_workers,
            queue_maxsize=settings.index_queue_maxsize,
        )
        self.dig_similar_tracks = DigSimilarTracks(
            track_repository=track_repository,
        )
        self.vibe_search = VibeSearch(
            embedder=clap_embedder,
            track_repository=track_repository,
        )

        # ----- Phase 4: DJ set analysis -----------------------------------
        # Second disk-backed table: whole-set mean vectors. A separate
        # LanceDBClient instance keeps the track schema untouched.
        set_vectors = LanceDBClient(
            settings.lancedb_path,
            table_name="set_vectors",
            schema=SET_VECTOR_SCHEMA,
        )
        await set_vectors.connect()
        set_repository = HybridSetRepository(sqlite, set_vectors)
        set_downloader = YtDlpSetDownloader(
            cache_dir=settings.set_cache_dir,
            cookies_file=settings.ytdlp_cookies_file,
            cookies_from_browser=settings.ytdlp_cookies_from_browser,
        )
        set_segmenter = SetSegmenter()
        shazam_fingerprinter = ShazamFingerprinter()
        self.set_vectors = set_vectors
        self.set_repository = set_repository
        self.set_downloader = set_downloader
        self.set_segmenter = set_segmenter
        self.shazam_fingerprinter = shazam_fingerprinter
        self.analyze_dj_set = AnalyzeDJSet(
            set_downloader=set_downloader,
            audio_segmenter=set_segmenter,
            audio_decoder=audio_decoder,
            feature_extractor=feature_extractor,
            audio_embedder=clap_embedder,
            track_repository=track_repository,
            set_repository=set_repository,
            seed_repository=seed_repository,
            fingerprinter=shazam_fingerprinter,
            llm_service=llm_service,
            # `cpu_executor` stays None: AnalyzeDJSet spins up a bounded
            # ProcessPoolExecutor per run and shuts it down afterwards.
            cpu_workers=settings.cpu_workers,
            embed_batch_size=min(settings.clap_batch_size, 16),
        )
        self.find_similar_for_set = FindSimilarForSet(
            track_repository=track_repository,
            set_repository=set_repository,
        )
        self._started = True

    async def close(self) -> None:
        """Close HTTP and storage resources in reverse order."""
        if not self._started:
            return
        if self.http_client is not None:
            await self.http_client.aclose()
        if self.set_vectors is not None:
            await self.set_vectors.close()
        if self.vectors is not None:
            await self.vectors.close()
        if self.sqlite is not None:
            await self.sqlite.close()
        self._started = False
