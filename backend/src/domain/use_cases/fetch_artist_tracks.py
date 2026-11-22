"""Use case: targeted artist track fetching, deduplication, auto-indexing, and discovery."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .._validation import normalize_artist_key, normalize_track_key
from ..entities.track import SeedArtist, Track
from ..genres import track_matches_genre_guard, track_matches_year
from ..interfaces.catalog import ICatalogProvider, ISeedDiscovery
from ..interfaces.repositories import (
    IBlacklistRepository,
    ISeedRepository,
    ITrackRepository,
)
from .index_catalog import IndexCatalog

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FetchArtistProgress:
    """Progress event during targeted artist fetch."""

    stage: str
    artist: str
    processed: int
    total: int
    message: str


@dataclass(frozen=True, slots=True)
class FetchArtistResult:
    """Summary of one targeted artist fetch run."""

    artist: str
    tracks_found: int
    tracks_saved: int
    tracks_indexed: int
    related_seeds_found: int


class FetchArtistTracks:
    """Fetch tracks for a specific artist, save them, auto-index, and optionally crawl related."""

    def __init__(
        self,
        *,
        catalog_provider: ICatalogProvider,
        track_repository: ITrackRepository,
        seed_repository: ISeedRepository | None = None,
        seed_discovery: ISeedDiscovery | None = None,
        index_catalog: IndexCatalog | None = None,
        blacklist_repository: IBlacklistRepository | None = None,
    ) -> None:
        self._catalog_provider = catalog_provider
        self._track_repository = track_repository
        self._seed_repository = seed_repository
        self._seed_discovery = seed_discovery
        self._index_catalog = index_catalog
        self._blacklist_repository = blacklist_repository

    async def execute(
        self,
        artist_name: str,
        *,
        tracks_limit: int = 50,
        auto_index: bool = True,
        discover_related: bool = False,
        related_limit: int = 10,
        min_year: int | None = None,
        electronic_only: bool = False,
        allowed_genres: Sequence[str] | None = None,
        progress: Callable[[FetchArtistProgress], None] | None = None,
    ) -> FetchArtistResult:
        artist_clean = artist_name.strip()
        if not artist_clean:
            raise ValueError("artist_name must not be empty")
        if tracks_limit <= 0:
            raise ValueError("tracks_limit must be positive")
        if related_limit < 0:
            raise ValueError("related_limit must not be negative")

        def notify(stage: str, processed: int, total: int, msg: str) -> None:
            if progress is not None:
                progress(
                    FetchArtistProgress(
                        stage=stage,
                        artist=artist_clean,
                        processed=processed,
                        total=total,
                        message=msg,
                    )
                )

        # 1. Check blacklist
        if self._blacklist_repository is not None:
            blocked_artists = await self._blacklist_repository.get_blocked_artist_keys()
            if normalize_artist_key(artist_clean) in blocked_artists:
                raise ValueError(f"Artist '{artist_clean}' is blacklisted")

        # 2. Fetch tracks from provider
        notify("fetching", 0, tracks_limit, f"Querying iTunes for '{artist_clean}'...")
        tracks = await self._catalog_provider.list_artist_tracks(
            artist_clean, limit=tracks_limit
        )

        filtered_tracks: list[Track] = []
        blocked_tracks: frozenset[str] = frozenset()
        if self._blacklist_repository is not None:
            blocked_tracks = await self._blacklist_repository.get_blocked_track_keys()

        for t in tracks:
            if (
                blocked_tracks
                and normalize_track_key(t.artist, t.title) in blocked_tracks
            ):
                LOGGER.info("Skipping blacklisted track: %s - %s", t.artist, t.title)
                continue
            if not track_matches_year(t.release_year, min_year=min_year):
                continue
            if not track_matches_genre_guard(
                t.genre,
                allowed_genres=allowed_genres or (),
                electronic_only=electronic_only,
            ):
                continue
            filtered_tracks.append(t)

        # 3. Save tracks to repository
        tracks_saved = 0
        if filtered_tracks:
            notify(
                "saving",
                len(filtered_tracks),
                len(filtered_tracks),
                f"Saving {len(filtered_tracks)} tracks to catalog...",
            )
            tracks_saved = await self._track_repository.upsert_many(filtered_tracks)

        # 4. Mark or record seed as fetched
        if self._seed_repository is not None:
            existing = await self._seed_repository.get_by_name(artist_clean)
            if existing is None:
                new_seed = SeedArtist(
                    name=artist_clean,
                    priority_score=1.0,
                    category="electronic",
                    status="fetched",
                    source="user",
                )
                await self._seed_repository.upsert_many([new_seed])
            else:
                await self._seed_repository.update_status(artist_clean, "fetched")

        # 5. Auto-index if requested
        tracks_indexed = 0
        if auto_index and self._index_catalog is not None and filtered_tracks:
            notify(
                "indexing",
                0,
                len(filtered_tracks),
                f"Auto-indexing audio for {len(filtered_tracks)} tracks...",
            )
            track_ids = [t.id for t in filtered_tracks]
            idx_res = await self._index_catalog.execute(
                track_ids=track_ids,
                limit=len(track_ids),
                progress=lambda p: notify(
                    "indexing",
                    p.processed,
                    len(track_ids),
                    f"Indexing: {p.processed}/{len(track_ids)} (failed {p.failed})",
                ),
            )
            tracks_indexed = idx_res.processed

        # 6. Discover related if requested
        related_seeds_count = 0
        if discover_related and self._seed_discovery is not None and related_limit > 0:
            notify(
                "discovering",
                0,
                related_limit,
                f"Discovering related artists for '{artist_clean}'...",
            )
            try:
                related = await self._seed_discovery.discover(
                    electronic_limit=related_limit,
                    general_limit=0,
                    max_depth=1,
                    seed_artists=[artist_clean],
                )
                if self._blacklist_repository is not None:
                    blocked = await self._blacklist_repository.get_blocked_artist_keys()
                    related = [
                        s
                        for s in related
                        if normalize_artist_key(s.name) not in blocked
                    ]
                if self._seed_repository is not None and related:
                    related_seeds_count = await self._seed_repository.record_discovery(
                        related
                    )
                else:
                    related_seeds_count = len(related)
            except Exception as e:  # noqa: BLE001
                LOGGER.warning(
                    "Related artist discovery failed for '%s': %s", artist_clean, e
                )

        notify(
            "done",
            tracks_saved,
            tracks_saved,
            f"Fetched {len(filtered_tracks)} tracks, saved {tracks_saved}, indexed {tracks_indexed}.",
        )

        return FetchArtistResult(
            artist=artist_clean,
            tracks_found=len(filtered_tracks),
            tracks_saved=tracks_saved,
            tracks_indexed=tracks_indexed,
            related_seeds_found=related_seeds_count,
        )
