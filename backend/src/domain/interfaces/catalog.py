"""Remote catalog and seed-crawling interfaces.

Implementations live in ``data/datasources/remote`` and must enforce the
iTunes ceiling of **18 metadata requests per minute** documented in AGENTS.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Sequence
from typing import TYPE_CHECKING

from ..entities.track import SeedArtist, Track

if TYPE_CHECKING:
    from ..use_cases.build_seed_list import CrawlProgress


class ICatalogProvider(ABC):
    """A source of track metadata and 30-second preview payloads."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable provider identifier stored on ``Track.source``."""

    @abstractmethod
    async def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        """Search the provider catalog and return lightweight track metadata."""

    @abstractmethod
    async def lookup_track(self, provider_track_id: str) -> Track | None:
        """Look up one provider track by its provider-specific id."""

    @abstractmethod
    async def list_artist_tracks(
        self, artist_name: str, *, limit: int = 50
    ) -> Sequence[Track]:
        """List tracks by an artist for seed crawling."""

    @abstractmethod
    async def fetch_preview(self, track: Track) -> bytes | None:
        """Fetch the compressed preview payload for a track.

        Returns ``None`` when the provider has no preview. The caller decodes the
        payload through ``IAudioDecoder`` and discards the bytes afterwards; this
        interface must never retain preview audio.
        """

    async def crawl_keyword(
        self,
        keyword: str,
        *,
        limit: int = 200,
        expand_compilations: bool = True,
    ) -> Sequence[Track]:
        """Keyword/label/compilation crawl. Default: unsupported."""
        return ()


class ISeedDiscovery(ABC):
    """Discovers artist names that should become catalog crawl seeds.

    Implementations may walk a public artist graph and/or read public charts.
    They must rate-limit their own requests, deduplicate by normalized artist
    name, and return immutable ``SeedArtist`` objects.
    """

    @abstractmethod
    async def discover(
        self,
        *,
        electronic_limit: int = 1000,
        general_limit: int = 300,
        max_depth: int = 2,
        progress: Callable[[CrawlProgress], None] | None = None,
    ) -> Sequence[SeedArtist]:
        """Return deduplicated seeds across electronic and general categories.

        An optional ``progress`` callback receives a :class:`CrawlProgress` event
        as discovery proceeds.
        """


class ISeedCrawler(ABC):
    """Streams catalog tracks for seed artists without materializing the catalog."""

    @abstractmethod
    def crawl(
        self,
        seeds: Sequence[SeedArtist],
        *,
        tracks_per_artist: int = 50,
    ) -> AsyncIterator[Track]:
        """Yield tracks for each seed, respecting provider rate limits.

        Implementations must stream results and deduplicate by provider id; they
        must not build an in-memory list of the whole crawl.
        """
