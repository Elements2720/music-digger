"""Use case: crawl iTunes catalog by techno subgenres, labels, and compilations.

Discovers tracks and electronic seed artists for underground club keywords,
enforcing the 18 requests/minute rate ceiling through the injected catalog
provider.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..entities.track import SeedArtist
from ..interfaces.catalog import ICatalogProvider
from ..interfaces.repositories import ISeedRepository, ITrackRepository

LOGGER = logging.getLogger(__name__)

DEFAULT_TECHNO_TERMS: tuple[str, ...] = (
    "hypnotic techno",
    "raw techno",
    "peak time techno",
    "hard techno",
    "minimal techno",
    "industrial techno",
    "melodic techno",
    "acid techno",
    "Drumcode",
    "KNTXT",
    "PoleGroup",
    "Mord Records",
    "Tresor",
    "Token Records",
    "Afterlife",
    "Exhale",
    "Possession",
    "Dystopian",
    "Ostgut",
    "Rekids",
)


@dataclass(frozen=True, slots=True)
class CrawlITunesResult:
    """Summary of one iTunes keyword crawl run."""

    terms_processed: int
    terms_failed: int
    tracks_found: int
    tracks_saved: int
    artists_discovered: int


class CrawlITunesSeeds:
    """Crawl underground techno terms, labels, and compilations on iTunes."""

    def __init__(
        self,
        *,
        catalog_provider: ICatalogProvider,
        track_repository: ITrackRepository,
        seed_repository: ISeedRepository,
    ) -> None:
        self._catalog_provider = catalog_provider
        self._track_repository = track_repository
        self._seed_repository = seed_repository

    async def execute(
        self,
        *,
        terms: Sequence[str] | None = None,
        tracks_per_term: int = 200,
        expand_compilations: bool = True,
        save_tracks: bool = True,
        priority_score: float = 0.85,
        progress: Callable[[str, int, int, int], None] | None = None,
    ) -> CrawlITunesResult:
        """Crawl iTunes by keyword/label/compilation.

        Per-term errors are isolated so one failed term never aborts the run.
        """
        if not 1 <= tracks_per_term <= 200:
            raise ValueError("tracks_per_term must be between 1 and 200")
        if not 0.0 <= priority_score <= 1.0:
            raise ValueError("priority_score must be between 0.0 and 1.0")

        if terms is None:
            terms_tuple = DEFAULT_TECHNO_TERMS
        else:
            if not isinstance(terms, Sequence):
                raise TypeError("terms must be a sequence of strings")
            if not terms:
                raise ValueError("terms must not be empty")
            cleaned: list[str] = []
            for term in terms:
                if not isinstance(term, str):
                    raise TypeError("each term must be a string")
                stripped = term.strip()
                if not stripped:
                    raise ValueError("terms must contain non-empty strings")
                cleaned.append(stripped)
            terms_tuple = tuple(cleaned)

        terms_processed = 0
        terms_failed = 0
        tracks_found = 0
        tracks_saved = 0
        seen_artists_overall: set[str] = set()

        total = len(terms_tuple)
        for index, term in enumerate(terms_tuple, start=1):
            term_tracks_found = 0
            try:
                tracks = await self._catalog_provider.crawl_keyword(
                    term,
                    limit=tracks_per_term,
                    expand_compilations=expand_compilations,
                )
                term_tracks_found = len(tracks)
                tracks_found += term_tracks_found

                if save_tracks and tracks:
                    tracks_saved += await self._track_repository.upsert_many(tracks)

                seen_in_term: set[str] = set()
                artists_to_record: list[SeedArtist] = []
                for track in tracks:
                    name = track.artist.strip()
                    key = name.casefold()
                    if not key or key in seen_in_term:
                        continue
                    seen_in_term.add(key)
                    artists_to_record.append(
                        SeedArtist(
                            name=name,
                            priority_score=priority_score,
                            category="electronic",
                            source="itunes-crawl",
                        )
                    )

                if artists_to_record:
                    await self._seed_repository.record_discovery(artists_to_record)
                    seen_artists_overall.update(seen_in_term)

                terms_processed += 1
            except Exception:
                LOGGER.warning("iTunes crawl failed for term %r", term, exc_info=True)
                terms_failed += 1
            finally:
                if progress is not None:
                    progress(term, index, total, term_tracks_found)

        return CrawlITunesResult(
            terms_processed=terms_processed,
            terms_failed=terms_failed,
            tracks_found=tracks_found,
            tracks_saved=tracks_saved,
            artists_discovered=len(seen_artists_overall),
        )
