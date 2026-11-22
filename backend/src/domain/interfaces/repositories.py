"""Persistence interfaces implemented by the data layer.

SQLite and LanceDB are local, disk-backed stores. Their adapters expose async
methods so FastAPI request handlers and CLI commands can await them without
blocking the event loop. Remote services use the async interfaces in
``catalog.py`` and ``llm.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..entities.analytics import ArtistSummary, CatalogAnalytics, SeedBreakdown
from ..entities.dj_set import DJSet, SetMatch, TrackMatch
from ..entities.search import SearchFilter
from ..entities.track import BlacklistEntry, SeedArtist, SeedStatus, Track
from ..value_objects.audio_features import EmbeddingVector


class ITrackRepository(ABC):
    """Metadata plus vector search over the local track catalog."""

    @abstractmethod
    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        """Insert or update tracks, returning the number written.

        Metadata is persisted even when a track has no embedding yet. Tracks
        carrying an ``EmbeddingVector`` also update the disk-backed vector index.
        """

    @abstractmethod
    async def get_by_id(self, track_id: str) -> Track | None:
        """Return a track by local id, or ``None`` when absent."""

    @abstractmethod
    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        """Return a track by provider id for deduplication."""

    @abstractmethod
    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        """Return every found track for ``track_ids`` in the given order."""

    @abstractmethod
    async def find_similar(
        self,
        embedding: EmbeddingVector,
        search_filter: SearchFilter,
    ) -> Sequence[TrackMatch]:
        """Return the nearest catalog tracks, ordered by descending similarity."""

    @abstractmethod
    async def find_by_filter(self, search_filter: SearchFilter) -> Sequence[Track]:
        """Return metadata-only matches without running a vector query."""

    @abstractmethod
    async def search_tracks(self, query: str, limit: int = 30) -> Sequence[Track]:
        """Return catalog tracks whose title or artist contains ``query``.

        Matching is case-insensitive and bounded by ``limit`` so the UI can
        offer a search box without loading the whole catalog into memory.
        """

    @abstractmethod
    async def mark_heard(self, track_id: str) -> None:
        """Record that a track has already been played or surfaced to the user."""

    @abstractmethod
    async def set_heard(self, track_id: str, heard: bool) -> None:
        """Set the heard flag in either direction (toggle support)."""

    @abstractmethod
    async def get_heard_ids(self) -> frozenset[str]:
        """Return all track ids recorded as heard."""

    @abstractmethod
    async def count(self) -> int:
        """Return the number of tracks in the catalog."""

    @abstractmethod
    async def count_embedded(self) -> int:
        """Return the number of tracks that have a stored embedding."""

    async def get_embedded_ids(self, track_ids: Sequence[str]) -> frozenset[str]:
        """Return the subset of ``track_ids`` that have stored embeddings."""
        tracks = await self.get_many(track_ids)
        return frozenset(t.id for t in tracks if t.embedding is not None)

    @abstractmethod
    async def list_unembedded(
        self,
        limit: int = 100,
        *,
        max_failures: int = 3,
    ) -> Sequence[Track]:
        """Return tracks still missing an embedding, oldest first.

        Only tracks that carry a preview URL and whose consecutive indexing
        failures are below ``max_failures`` are returned, so permanently broken
        previews never block the pipeline.
        """

    @abstractmethod
    async def list_embedded(
        self, limit: int = 20, *, offset: int = 0
    ) -> Sequence[Track]:
        """Return embedded tracks, most recently indexed first."""

    @abstractmethod
    async def mark_index_failed(self, track_id: str) -> None:
        """Record one failed indexing attempt for a track.

        Repeated failures accumulate; once a track exceeds the caller's
        ``max_failures`` threshold it disappears from
        :meth:`list_unembedded` until the counter is reset manually.
        """

    @abstractmethod
    async def list_reindexable(
        self,
        limit: int = 100,
        *,
        max_failures: int = 3,
    ) -> Sequence[Track]:
        """Return tracks worth (re-)embedding, including already-embedded ones.

        Used by ``dig index --reindex``: unlike :meth:`list_unembedded` this
        includes embedded tracks so improved ML logic can re-process the whole
        catalog. Tracks with too many consecutive failures are still skipped.
        """

    @abstractmethod
    async def reset_embeddings(self) -> int:
        """Drop every stored embedding, keeping track metadata.

        Clears the vector index and the embedded/BPM/key columns in SQLite so
        a fresh ``dig index`` run re-embeds the catalog from scratch. Returns
        the number of tracks that had embeddings.
        """

    async def delete_by_ids(self, track_ids: Sequence[str]) -> int:
        """Delete tracks by their IDs, returning the count removed."""
        return 0

    async def delete_by_artist(self, artist_name: str) -> tuple[int, tuple[str, ...]]:
        """Delete all tracks by artist name, returning (count_deleted, deleted_ids)."""
        return (0, ())

    async def list_by_artist(
        self, artist_name: str, *, limit: int = 200, offset: int = 0
    ) -> Sequence[Track]:
        """List tracks by artist name."""
        return ()

    async def list_artists_summary(
        self,
        *,
        query: str | None = None,
        genre: str | None = None,
        source: str | None = None,
        min_year: int | None = None,
        sort: str = "tracks_desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[ArtistSummary], int]:
        """List artists summary with counts and genres, returning (artists, total_count)."""
        return ((), 0)

    async def get_artist_taste_scores(self) -> tuple[dict[str, float], int]:
        """Return (artist_taste_scores, local_taste_count).

        Scores are 0.0-100.0 percentages reflecting how close each artist's
        catalog is to the user's local music taste profile.
        """
        return ({}, 0)

    async def get_catalog_analytics(self) -> CatalogAnalytics:
        """Return high-level analytics and distributions across the catalog."""
        return CatalogAnalytics(
            total_tracks=0,
            total_embedded=0,
            total_artists=0,
            total_local=0,
            total_itunes=0,
            genres=(),
            bpm_buckets=(),
            sources=(),
            top_keys=(),
        )


class ISetRepository(ABC):
    """Persistence for analyzed DJ sets."""

    @abstractmethod
    async def save(self, dj_set: DJSet) -> None:
        """Insert or replace a DJ set and its passages."""

    @abstractmethod
    async def get_by_id(self, set_id: str) -> DJSet | None:
        """Return a DJ set by id, or ``None`` when absent."""

    @abstractmethod
    async def list_all(self, limit: int = 20) -> Sequence[DJSet]:
        """Return the most recently saved sets, newest first."""

    @abstractmethod
    async def delete(self, set_id: str) -> bool:
        """Delete a set, returning True when a record was removed."""

    @abstractmethod
    async def count(self) -> int:
        """Return the number of stored DJ sets."""

    @abstractmethod
    async def find_similar_sets(
        self,
        embedding: EmbeddingVector,
        *,
        limit: int = 12,
    ) -> Sequence[SetMatch]:
        """Return the nearest stored sets by mean-embedding cosine similarity.

        Ordered by descending similarity. The result may include the reference
        set itself; callers exclude it when needed.
        """


class ISeedRepository(ABC):
    """Persistence for catalog crawl seeds."""

    @abstractmethod
    async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int:
        """Insert or update seeds, returning the number written.

        Existing rows keep their status so a repeated LLM or manual seed import
        does not reset already-fetched artists.
        """

    @abstractmethod
    async def record_discovery(
        self,
        seeds: Sequence[SeedArtist],
        *,
        priority_increment: float = 0.05,
    ) -> int:
        """Persist graph discoveries and bump priority on rediscovery.

        New seeds are inserted with their supplied priority. An existing seed
        keeps its status and has its priority raised by ``priority_increment``
        (capped at ``1.0``), which makes central scene artists bubble to the top
        of the fetch queue.
        """

    @abstractmethod
    async def get_by_name(self, name: str) -> SeedArtist | None:
        """Return a seed by artist name, using normalized comparison."""

    @abstractmethod
    async def list_by_status(
        self, status: SeedStatus, limit: int = 100
    ) -> Sequence[SeedArtist]:
        """Return seeds with the given status, highest priority first."""

    async def list_by_source(
        self, source: str, limit: int = 100
    ) -> Sequence[SeedArtist]:
        """Return seeds for a specific source, highest priority first."""
        return ()

    @abstractmethod
    async def update_status(self, name: str, status: SeedStatus) -> None:
        """Update a seed's crawl status."""

    @abstractmethod
    async def count_by_category(self, category: str) -> int:
        """Return the number of seeds in a category (``electronic`` or ``general``)."""

    @abstractmethod
    async def count_by_status(self, status: SeedStatus) -> int:
        """Return the number of seeds with the given status."""

    @abstractmethod
    async def count(self) -> int:
        """Return the total number of seeds."""

    async def delete_by_name(self, name: str) -> bool:
        """Delete a seed by artist name, returning True if deleted."""
        return False

    async def list_seeds(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        category: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[SeedArtist], int]:
        """List seeds matching filters with pagination, returning (seeds, total_count)."""
        return ((), 0)

    async def get_breakdown(self) -> SeedBreakdown:
        """Return overall count breakdown by status and by source."""
        return SeedBreakdown(total=0, pending=0, fetched=0, failed=0, by_source=())

    async def purge_seeds(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        category: str | None = None,
    ) -> int:
        """Purge seeds matching criteria, returning the count of deleted seeds."""
        return 0


class IBlacklistRepository(ABC):
    """Persistence for blocked artists and tracks."""

    @abstractmethod
    async def add(self, entry: BlacklistEntry) -> BlacklistEntry:
        """Insert or replace a blacklist entry."""

    @abstractmethod
    async def remove(self, entry_id: int) -> bool:
        """Remove a blacklist entry by ID, returning True if deleted."""

    @abstractmethod
    async def list_all(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BlacklistEntry]:
        """List blacklist entries with optional filtering by kind and query."""

    @abstractmethod
    async def count(self, *, kind: str | None = None) -> int:
        """Return the count of blacklist entries, optionally filtered by kind."""

    @abstractmethod
    async def get_blocked_artist_keys(self) -> frozenset[str]:
        """Return all blocked normalized artist keys in memory for fast lookup."""

    @abstractmethod
    async def get_blocked_track_keys(self) -> frozenset[str]:
        """Return all blocked normalized track keys ('artist|title') in memory for fast lookup."""

    @abstractmethod
    async def is_artist_blocked(self, normalized_artist: str) -> bool:
        """Check whether an artist is blocked."""

    @abstractmethod
    async def is_track_blocked(self, normalized_track_key: str) -> bool:
        """Check whether a track key ('artist|title') is blocked."""

    async def get_by_key(self, kind: str, normalized_key: str) -> BlacklistEntry | None:
        """Fetch a blacklist entry by kind and normalized key."""
        return None
