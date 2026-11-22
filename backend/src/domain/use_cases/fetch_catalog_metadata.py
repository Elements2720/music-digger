"""Use case: fetch catalog metadata for the highest-priority pending seeds.

The use case is resumable: a seed is marked ``fetched`` only after its tracks
have been written, and a failure leaves the seed as ``failed`` so the next run
can retry it explicitly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..entities.track import SeedArtist
from ..interfaces.catalog import ICatalogProvider
from ..interfaces.repositories import ISeedRepository, ITrackRepository

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FetchMetadataResult:
    """Summary of one catalog metadata fetch run."""

    artists_processed: int
    artists_failed: int
    artists_skipped: int
    tracks_found: int
    tracks_saved: int


class FetchCatalogMetadata:
    """Fetch tracks for pending seeds, in descending priority order."""

    def __init__(
        self,
        *,
        seed_repository: ISeedRepository,
        catalog_provider: ICatalogProvider,
        track_repository: ITrackRepository,
    ) -> None:
        self._seed_repository = seed_repository
        self._catalog_provider = catalog_provider
        self._track_repository = track_repository

    async def execute(
        self,
        *,
        artists_limit: int = 50,
        # 200 matches ITUNES_SEARCH_LIMIT: one search request already returns
        # up to 200 tracks per artist, so keeping fewer would discard rows we
        # paid a rate-limited request for.
        tracks_per_artist: int = 200,
        retry_failed: bool = False,
        progress: Callable[[SeedArtist, int, int], None] | None = None,
    ) -> FetchMetadataResult:
        """Fetch metadata for up to ``artists_limit`` seeds.

        ``progress`` receives ``(seed, index, total)`` before each provider call.
        It is deliberately synchronous so CLI progress rendering stays simple.
        """
        if artists_limit <= 0:
            raise ValueError("artists_limit must be positive")
        if tracks_per_artist <= 0:
            raise ValueError("tracks_per_artist must be positive")

        seeds = await self._select_seeds(artists_limit, retry_failed)
        processed = 0
        failed = 0
        tracks_found = 0
        tracks_saved = 0

        for index, seed in enumerate(seeds, start=1):
            if progress is not None:
                progress(seed, index, len(seeds))
            try:
                tracks = await self._catalog_provider.list_artist_tracks(
                    seed.name,
                    limit=tracks_per_artist,
                )
                tracks_found += len(tracks)
                tracks_saved += await self._track_repository.upsert_many(tracks)
                await self._seed_repository.update_status(seed.name, "fetched")
                processed += 1
            except Exception:
                # Keep the run resumable instead of aborting the whole batch on
                # one malformed artist response or one transient provider error.
                LOGGER.exception("Could not fetch metadata for seed %s", seed.name)
                await self._seed_repository.update_status(seed.name, "failed")
                failed += 1

        return FetchMetadataResult(
            artists_processed=processed,
            artists_failed=failed,
            artists_skipped=max(0, artists_limit - len(seeds)),
            tracks_found=tracks_found,
            tracks_saved=tracks_saved,
        )

    async def _select_seeds(
        self,
        artists_limit: int,
        retry_failed: bool,
    ) -> Sequence[SeedArtist]:
        statuses = ("failed", "pending") if retry_failed else ("pending",)
        selected: list[SeedArtist] = []
        seen: set[str] = set()
        for status in statuses:
            remaining = artists_limit - len(selected)
            if remaining <= 0:
                break
            batch = await self._seed_repository.list_by_status(status, limit=remaining)
            for seed in batch:
                key = seed.name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                selected.append(seed)
        return tuple(selected)
