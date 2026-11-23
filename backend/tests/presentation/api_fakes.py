"""Injected fakes for presentation-layer tests (no GPU, network, or disk)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

from domain.entities.analytics import (
    ArtistSummary,
    BpmBucketStat,
    CatalogAnalytics,
    GenreStat,
    KeyStat,
    SeedBreakdown,
    SeedSourceStat,
    SourceStat,
)
from domain.entities.dj_set import DJSet, Passage, SetMatch, TrackMatch
from domain.entities.search import SearchFilter
from domain.entities.set_plan import PlannedSet
from domain.entities.track import (
    AudioBuffer,
    BlacklistEntry,
    LikedArtist,
    SeedArtist,
    Track,
)
from domain.interfaces.downloader import ITrackDownloader, TrackDownloadResult
from domain.interfaces.repositories import (
    IBlacklistRepository,
    ILikedArtistRepository,
    IPlannedSetRepository,
    ISetRepository,
    ITrackRepository,
)
from domain.use_cases import (
    DigSimilarTracks,
    DJSetHelper,
    DownloadTracks,
    FindSimilarForSet,
    ManageCatalog,
    VibeSearch,
)
from domain.value_objects.audio_features import EmbeddingVector, TimeRange
from domain.value_objects.hardware import HardwareInfo


def make_track(
    track_id: str,
    *,
    title: str | None = None,
    artist: str | None = None,
    embedding: tuple[float, float] | None = (1.0, 0.0),
    preview_url: str | None = "https://cdn.test/preview.m4a",
) -> Track:
    return Track(
        id=track_id,
        title=title or f"Title {track_id}",
        artist=artist or f"Artist {track_id}",
        bpm=126.0,
        key="8A",
        genre="Melodic Techno",
        preview_url=preview_url,
        artwork_url="https://cdn.test/art.jpg",
        store_url="https://music.test/track",
        embedding=(
            EmbeddingVector(values=embedding, dimension=2)
            if embedding is not None
            else None
        ),
    )


class FakeTrackRepository(ITrackRepository):
    """In-memory catalog with 2-D cosine similarity."""

    def __init__(
        self,
        tracks: Sequence[Track] = (),
        *,
        heard: Sequence[str] = (),
    ) -> None:
        self.tracks: dict[str, Track] = {track.id: track for track in tracks}
        self.heard: set[str] = set(heard)

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        for track in tracks:
            self.tracks[track.id] = track
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        return self.tracks.get(track_id)

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        return None

    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        return [self.tracks[key] for key in track_ids if key in self.tracks]

    async def find_similar(
        self, embedding: EmbeddingVector, search_filter: SearchFilter
    ) -> Sequence[TrackMatch]:
        scored = [
            (track, embedding.cosine_similarity(track.embedding))
            for track in self.tracks.values()
            if track.embedding is not None
        ]
        if search_filter.exclude_heard:
            scored = [(t, s) for t, s in scored if t.id not in self.heard]
        if search_filter.genre_filter is not None:
            scored = [
                (t, s)
                for t, s in scored
                if t.genre is not None
                and t.genre.casefold() == search_filter.genre_filter.casefold()
            ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [
            TrackMatch(track=track, similarity_score=score)
            for track, score in scored[: search_filter.limit]
        ]

    async def find_by_filter(self, search_filter: SearchFilter) -> Sequence[Track]:
        return ()

    async def search_tracks(self, query: str, limit: int = 30) -> Sequence[Track]:
        needle = query.strip().casefold()
        if not needle or limit <= 0:
            return ()
        hits = [
            track
            for track in self.tracks.values()
            if needle in track.title.casefold() or needle in track.artist.casefold()
        ]
        return hits[:limit]

    async def mark_heard(self, track_id: str) -> None:
        self.heard.add(track_id)

    async def set_heard(self, track_id: str, heard: bool) -> None:
        if heard:
            self.heard.add(track_id)
        else:
            self.heard.discard(track_id)

    async def get_heard_ids(self) -> frozenset[str]:
        return frozenset(self.heard)

    async def count(self) -> int:
        return len(self.tracks)

    async def count_embedded(self) -> int:
        return sum(1 for t in self.tracks.values() if t.embedding is not None)

    async def get_embedded_ids(self, track_ids: Sequence[str]) -> frozenset[str]:
        return frozenset(
            track_id
            for track_id in track_ids
            if track_id in self.tracks and self.tracks[track_id].embedding is not None
        )

    async def list_unembedded(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def list_embedded(
        self, limit: int = 20, *, offset: int = 0, features_first: bool = False
    ) -> Sequence[Track]:
        embedded = [t for t in self.tracks.values() if t.embedding is not None]
        if features_first:
            embedded = sorted(embedded, key=lambda t: t.bpm is not None, reverse=True)
        return embedded[offset : offset + max(0, limit)]

    async def mark_index_failed(self, track_id: str) -> None:
        return None

    async def list_reindexable(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def reset_embeddings(self) -> int:
        cleared = 0
        for track_id, track in self.tracks.items():
            if track.embedding is not None:
                self.tracks[track_id] = Track(
                    id=track.id, title=track.title, artist=track.artist
                )
                cleared += 1
        return cleared

    async def delete_by_ids(self, track_ids: Sequence[str]) -> int:
        count = 0
        for tid in track_ids:
            if tid in self.tracks:
                del self.tracks[tid]
                count += 1
        return count

    async def delete_by_artist(self, artist_name: str) -> tuple[int, tuple[str, ...]]:
        matching = [
            tid
            for tid, t in self.tracks.items()
            if t.artist.casefold() == artist_name.casefold()
        ]
        count = await self.delete_by_ids(matching)
        return (count, tuple(matching))

    async def delete_by_artists(
        self, artist_names: Sequence[str]
    ) -> tuple[int, tuple[str, ...]]:
        names_lower = {a.casefold() for a in artist_names}
        matching = [
            tid for tid, t in self.tracks.items() if t.artist.casefold() in names_lower
        ]
        count = await self.delete_by_ids(matching)
        return (count, tuple(matching))

    async def get_artists_with_local_tracks(self) -> frozenset[str]:
        from domain._validation import normalize_artist_key

        return frozenset(
            normalize_artist_key(t.artist)
            for t in self.tracks.values()
            if t.source == "local" or t.local_path is not None
        )

    async def list_by_artist(
        self, artist_name: str, *, limit: int = 200, offset: int = 0
    ) -> Sequence[Track]:
        matched = [
            t
            for t in self.tracks.values()
            if t.artist.casefold() == artist_name.casefold()
        ]
        return tuple(matched[offset : offset + limit])

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
        taste_mode: str = "both",
        liked_artist_keys: frozenset[str] = frozenset(),
        liked_only: bool = False,
    ) -> tuple[Sequence[ArtistSummary], int]:
        from domain._validation import normalize_artist_key

        by_artist: dict[str, list[Track]] = {}
        for t in self.tracks.values():
            by_artist.setdefault(t.artist, []).append(t)

        summaries: list[ArtistSummary] = []
        for artist, trks in by_artist.items():
            norm_k = normalize_artist_key(artist)
            is_liked = norm_k in liked_artist_keys
            if liked_only and not is_liked:
                continue
            if query and query.casefold() not in artist.casefold():
                continue
            if genre and not any(
                t.genre and t.genre.casefold() == genre.casefold() for t in trks
            ):
                continue
            if source and not any(t.source == source for t in trks):
                continue
            if min_year and not any(
                t.release_year is not None and t.release_year >= min_year for t in trks
            ):
                continue
            genres = tuple({t.genre for t in trks if t.genre})
            sources = tuple({t.source for t in trks if t.source})
            years = [t.release_year for t in trks if t.release_year is not None]
            emb_cnt = sum(1 for t in trks if t.embedding is not None)
            summaries.append(
                ArtistSummary(
                    artist=artist,
                    track_count=len(trks),
                    embedded_count=emb_cnt,
                    genres=genres,
                    sources=sources,
                    sample_track_id=trks[0].id if trks else None,
                    sample_track_title=trks[0].title if trks else None,
                    year_min=min(years) if years else None,
                    year_max=max(years) if years else None,
                    is_liked=is_liked,
                )
            )

        if sort == "artist_asc":
            summaries.sort(key=lambda s: s.artist.casefold())
        elif sort == "embedded_desc":
            summaries.sort(
                key=lambda s: (s.embedded_count, s.track_count), reverse=True
            )
        elif sort == "taste_desc":
            summaries.sort(
                key=lambda s: (
                    s.taste_match_percent is not None,
                    s.taste_match_percent or 0.0,
                ),
                reverse=True,
            )
        elif sort == "taste_asc":
            summaries.sort(
                key=lambda s: (
                    s.taste_match_percent is not None,
                    -(
                        s.taste_match_percent
                        if s.taste_match_percent is not None
                        else 999.0
                    ),
                ),
                reverse=True,
            )
        else:
            summaries.sort(
                key=lambda s: (s.track_count, s.embedded_count), reverse=True
            )

        return (tuple(summaries[offset : offset + limit]), len(summaries))

    async def get_embeddings_map(
        self, track_ids: Sequence[str]
    ) -> dict[str, EmbeddingVector]:
        return {
            tid: self.tracks[tid].embedding
            for tid in track_ids
            if tid in self.tracks and self.tracks[tid].embedding is not None
        }

    async def get_artist_taste_scores(self) -> tuple[dict[str, float], int]:
        local_count = sum(1 for t in self.tracks.values() if t.source == "local")
        return ({}, local_count)

    async def get_catalog_analytics(self) -> CatalogAnalytics:
        genres_map: dict[str, list[Track]] = {}
        sources_map: dict[str, list[Track]] = {}
        keys_map: dict[str, int] = {}
        total_embedded = 0
        total_local = 0
        total_itunes = 0

        for t in self.tracks.values():
            if t.embedding is not None:
                total_embedded += 1
            if t.source == "local":
                total_local += 1
            elif t.source == "itunes":
                total_itunes += 1
            if t.genre:
                genres_map.setdefault(t.genre, []).append(t)
            if t.source:
                sources_map.setdefault(t.source, []).append(t)
            if t.key:
                keys_map[t.key.notation] = keys_map.get(t.key.notation, 0) + 1

        genres = tuple(
            GenreStat(
                genre=g,
                track_count=len(trks),
                embedded_count=sum(1 for tr in trks if tr.embedding is not None),
            )
            for g, trks in genres_map.items()
        )
        sources = tuple(
            SourceStat(
                source=s,
                track_count=len(trks),
                embedded_count=sum(1 for tr in trks if tr.embedding is not None),
            )
            for s, trks in sources_map.items()
        )
        top_keys = tuple(
            KeyStat(camelot_key=k, track_count=cnt) for k, cnt in keys_map.items()
        )
        bpm_buckets = (
            (BpmBucketStat(label="120-124", track_count=len(self.tracks)),)
            if self.tracks
            else ()
        )

        return CatalogAnalytics(
            total_tracks=len(self.tracks),
            total_embedded=total_embedded,
            total_artists=len({t.artist for t in self.tracks.values()}),
            total_local=total_local,
            total_itunes=total_itunes,
            genres=genres,
            bpm_buckets=bpm_buckets,
            sources=sources,
            top_keys=top_keys,
        )


class FakeSetRepository(ISetRepository):
    """In-memory set store."""

    def __init__(
        self,
        sets: Sequence[DJSet] = (),
        similar: Sequence[SetMatch] = (),
    ) -> None:
        self.sets: dict[str, DJSet] = {dj_set.id: dj_set for dj_set in sets}
        self.similar = tuple(similar)

    async def save(self, dj_set: DJSet) -> None:
        self.sets[dj_set.id] = dj_set

    async def get_by_id(self, set_id: str) -> DJSet | None:
        return self.sets.get(set_id)

    async def list_all(self, limit: int = 20) -> Sequence[DJSet]:
        return tuple(self.sets.values())[:limit]

    async def delete(self, set_id: str) -> bool:
        return self.sets.pop(set_id, None) is not None

    async def count(self) -> int:
        return len(self.sets)

    async def find_similar_sets(
        self, embedding: EmbeddingVector, *, limit: int = 12
    ) -> Sequence[SetMatch]:
        return self.similar[:limit]


class FakeSeedRepository:
    def __init__(
        self,
        *,
        total: int = 7,
        pending: int = 3,
        fetched: int = 3,
        failed: int = 1,
        electronic: int = 5,
        general: int = 2,
    ) -> None:
        self.seeds: list[SeedArtist] = [
            SeedArtist(
                "Tale of Us", 0.9, "electronic", status="pending", source="deezer"
            ),
            SeedArtist("ARTBAT", 0.8, "electronic", status="pending", source="itunes"),
            SeedArtist(
                "Solomun", 0.7, "electronic", status="pending", source="local-library"
            ),
            SeedArtist(
                "Boris Brejcha", 0.6, "electronic", status="fetched", source="deezer"
            ),
            SeedArtist(
                "Maceo Plex", 0.5, "electronic", status="fetched", source="deezer"
            ),
            SeedArtist(
                "Stephan Bodzin", 0.4, "general", status="fetched", source="itunes"
            ),
            SeedArtist("Dead Artist", 0.1, "general", status="failed", source="crawl"),
        ]

    async def count(self) -> int:
        return len(self.seeds)

    async def count_by_status(self, status: str) -> int:
        return sum(1 for s in self.seeds if s.status == status)

    async def count_by_category(self, category: str) -> int:
        return sum(1 for s in self.seeds if s.category == category)

    async def list_by_source(
        self, source: str, limit: int = 100
    ) -> Sequence[SeedArtist]:
        return tuple(s for s in self.seeds if s.source == source)[:limit]

    async def delete_by_name(self, name: str) -> bool:
        before = len(self.seeds)
        self.seeds = [s for s in self.seeds if s.name.lower() != name.lower()]
        return len(self.seeds) < before

    async def delete_by_names(self, names: Sequence[str]) -> int:
        names_lower = {n.lower() for n in names}
        before = len(self.seeds)
        self.seeds = [s for s in self.seeds if s.name.lower() not in names_lower]
        return before - len(self.seeds)

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
        matches = self.seeds
        if status:
            matches = [s for s in matches if s.status == status]
        if source:
            matches = [s for s in matches if s.source == source]
        if category:
            matches = [s for s in matches if s.category == category]
        if query:
            matches = [s for s in matches if query.lower() in s.name.lower()]
        return tuple(matches[offset : offset + limit]), len(matches)

    async def get_breakdown(self) -> SeedBreakdown:
        total = len(self.seeds)
        pending = sum(1 for s in self.seeds if s.status == "pending")
        fetched = sum(1 for s in self.seeds if s.status == "fetched")
        failed = sum(1 for s in self.seeds if s.status == "failed")
        sources = sorted({s.source or "unknown" for s in self.seeds})
        by_source = tuple(
            SeedSourceStat(
                source=src,
                total=sum(1 for s in self.seeds if (s.source or "unknown") == src),
                pending=sum(
                    1
                    for s in self.seeds
                    if (s.source or "unknown") == src and s.status == "pending"
                ),
                fetched=sum(
                    1
                    for s in self.seeds
                    if (s.source or "unknown") == src and s.status == "fetched"
                ),
                failed=sum(
                    1
                    for s in self.seeds
                    if (s.source or "unknown") == src and s.status == "failed"
                ),
            )
            for src in sources
        )
        return SeedBreakdown(
            total=total,
            pending=pending,
            fetched=fetched,
            failed=failed,
            by_source=by_source,
        )

    async def purge_seeds(
        self,
        *,
        status: str = "pending",
        source: str | None = None,
        category: str | None = None,
        exclude_sources: Sequence[str] = (),
    ) -> int:
        before = len(self.seeds)
        self.seeds = [
            s
            for s in self.seeds
            if not (
                (status is None or s.status == status)
                and (source is None or s.source == source)
                and (category is None or s.category == category)
                and (
                    not exclude_sources
                    or (s.source or "unknown") not in exclude_sources
                )
            )
        ]
        return before - len(self.seeds)

    async def record_discovery(
        self,
        seeds: Sequence[SeedArtist],
        *,
        priority_increment: float = 0.5,
    ) -> int:
        for s in seeds:
            self.seeds.append(s)
        return len(seeds)


class FakeBlacklistRepository(IBlacklistRepository):
    def __init__(self) -> None:
        self.entries: dict[int, BlacklistEntry] = {}
        self._next_id = 1

    async def add(self, entry: BlacklistEntry) -> BlacklistEntry:
        for eid, existing in self.entries.items():
            if existing.normalized_key == entry.normalized_key:
                updated = BlacklistEntry(
                    id=eid,
                    kind=entry.kind,
                    normalized_key=entry.normalized_key,
                    display_name=entry.display_name,
                    artist_name=entry.artist_name,
                    track_title=entry.track_title,
                    reason=entry.reason,
                    created_at="2026-11-22",
                )
                self.entries[eid] = updated
                return updated
        eid = self._next_id
        self._next_id += 1
        persisted = BlacklistEntry(
            id=eid,
            kind=entry.kind,
            normalized_key=entry.normalized_key,
            display_name=entry.display_name,
            artist_name=entry.artist_name,
            track_title=entry.track_title,
            reason=entry.reason,
            created_at="2026-11-22",
        )
        self.entries[eid] = persisted
        return persisted

    async def remove(self, entry_id: int) -> bool:
        return self.entries.pop(entry_id, None) is not None

    async def list_all(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BlacklistEntry]:
        result = list(self.entries.values())
        if kind:
            result = [e for e in result if e.kind == kind]
        if query:
            q = query.casefold()
            result = [e for e in result if q in e.display_name.casefold()]
        return tuple(result[offset : offset + limit])

    async def count(self, *, kind: str | None = None) -> int:
        if kind:
            return sum(1 for e in self.entries.values() if e.kind == kind)
        return len(self.entries)

    async def get_blocked_artist_keys(self) -> frozenset[str]:
        return frozenset(
            e.normalized_key for e in self.entries.values() if e.kind == "artist"
        )

    async def get_blocked_track_keys(self) -> frozenset[str]:
        return frozenset(
            e.normalized_key for e in self.entries.values() if e.kind == "track"
        )

    async def is_artist_blocked(self, normalized_artist: str) -> bool:
        return normalized_artist in await self.get_blocked_artist_keys()

    async def is_track_blocked(self, normalized_track_key: str) -> bool:
        return normalized_track_key in await self.get_blocked_track_keys()


class FakeLikedArtistRepository(ILikedArtistRepository):
    def __init__(self) -> None:
        self.liked: dict[str, LikedArtist] = {}

    async def like(self, artist_name: str) -> LikedArtist:
        from domain._validation import normalize_artist_key

        clean = artist_name.strip()
        norm_key = normalize_artist_key(clean)
        liked = LikedArtist(
            artist_name=clean, normalized_key=norm_key, created_at="2026-11-22"
        )
        self.liked[norm_key] = liked
        return liked

    async def unlike(self, artist_name: str) -> bool:
        from domain._validation import normalize_artist_key

        norm_key = normalize_artist_key(artist_name.strip())
        return self.liked.pop(norm_key, None) is not None

    async def is_liked(self, artist_name: str) -> bool:
        from domain._validation import normalize_artist_key

        norm_key = normalize_artist_key(artist_name.strip())
        return norm_key in self.liked

    async def list_all(self) -> Sequence[LikedArtist]:
        return tuple(self.liked.values())

    async def get_liked_keys(self) -> frozenset[str]:
        return frozenset(self.liked.keys())

    async def count(self) -> int:
        return len(self.liked)


class FakePlannedSetRepository(IPlannedSetRepository):
    def __init__(self) -> None:
        self.sets: dict[int, PlannedSet] = {}
        self._next_id = 1

    async def save(self, planned_set: PlannedSet) -> PlannedSet:
        if planned_set.id is None:
            sid = self._next_id
            self._next_id += 1
        else:
            sid = planned_set.id
        saved = PlannedSet(
            id=sid,
            name=planned_set.name,
            track_ids=tuple(planned_set.track_ids),
            created_at="2026-11-22T00:00:00",
            updated_at="2026-11-22T00:00:00",
        )
        self.sets[sid] = saved
        return saved

    async def get_by_id(self, set_id: int) -> PlannedSet | None:
        return self.sets.get(set_id)

    async def list_all(self) -> Sequence[PlannedSet]:
        return tuple(self.sets.values())

    async def delete(self, set_id: int) -> bool:
        return self.sets.pop(set_id, None) is not None


class FakeVectors:
    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = tracks

    async def compute_similarity_to_seed_ids(
        self,
        seed_track_ids: Sequence[str],
        *,
        weights: Any = None,
        batch_size: int = 2048,
    ) -> dict[str, float]:
        return {
            t.id: 85.0
            for t in self.tracks
            if t.embedding is not None and t.id not in seed_track_ids
        }

    async def get_vectors(
        self, track_ids: Sequence[str]
    ) -> dict[str, tuple[float, ...]]:
        return {
            t.id: t.embedding.values
            for t in self.tracks
            if t.id in track_ids and t.embedding is not None
        }


class FakeSqlite:
    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = tracks

    async def fetchall(self, sql: str, params: Any = ()) -> list[dict[str, Any]]:
        if "GROUP BY artist" in sql:
            by_artist: dict[str, list[Track]] = {}
            for t in self.tracks:
                by_artist.setdefault(t.artist, []).append(t)
            return [
                {
                    "artist": artist,
                    "track_count": len(trks),
                    "embedded_count": sum(1 for t in trks if t.embedding is not None),
                    "bpm_min": 124.0,
                    "bpm_max": 124.0,
                    "year_min": 2020,
                    "year_max": 2022,
                    "genres_concat": ",".join(filter(None, [t.genre for t in trks]))
                    or "Techno",
                }
                for artist, trks in by_artist.items()
            ]
        return [
            {"id": t.id, "artist": t.artist, "source": t.source}
            for t in self.tracks
            if t.embedding is not None
        ]


class FakeEmbedder:
    """Text queries map to (1, 0), matching the first fake track."""

    model_id = "fake-clap"
    embedding_dimension = 2

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_text(self, query: str) -> EmbeddingVector:
        self.queries.append(query)
        return EmbeddingVector(values=(1.0, 0.0), dimension=2)

    def embed(self, audio: AudioBuffer) -> EmbeddingVector:  # pragma: no cover
        raise AssertionError("API tests never embed audio")

    def embed_batch(  # pragma: no cover
        self, audios: Sequence[AudioBuffer]
    ) -> Sequence[EmbeddingVector]:
        raise AssertionError("API tests never embed audio")


class FakeClapEmbedder(FakeEmbedder):
    """Adds the runtime batch-size knob used by turbo mode."""

    def __init__(self, batch_size: int = 16) -> None:
        super().__init__()
        self._batch_size = batch_size

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @batch_size.setter
    def batch_size(self, value: int) -> None:
        self._batch_size = value


class FakeDecoder:
    def __init__(self, concurrency: int = 16) -> None:
        self.concurrency = concurrency

    def set_concurrency(self, concurrency: int) -> None:
        self.concurrency = concurrency


class FakeIndexCatalog:
    """Emits two progress events, then reports a small summary."""

    instances: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        FakeIndexCatalog.instances.append(kwargs)

    async def execute(self, **kwargs: Any) -> Any:
        progress = kwargs.get("progress")
        if progress is not None:
            progress(SimpleNamespace(processed=1, failed=0))
            progress(SimpleNamespace(processed=2, failed=1))
        return SimpleNamespace(processed=2, failed=1, embedded_total=9)


class SlowIndexCatalog(FakeIndexCatalog):
    """Never finishes until cancelled (cancel-path tests)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.started = asyncio.Event()

    async def execute(self, **kwargs: Any) -> Any:
        self.started.set()
        await asyncio.Event().wait()  # pragma: no cover - cancelled
        raise AssertionError("unreachable")


class FakeBuildSeedList:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        progress = kwargs.get("progress")
        if progress is not None:
            progress(
                SimpleNamespace(stage="electronic", name="Solomun", depth=0, found=1)
            )
            progress(SimpleNamespace(stage="writing", name="", depth=None, found=15))
        return SimpleNamespace(
            discovered=10,
            llm_generated=5,
            written=15,
            electronic_total=100,
            general_total=40,
        )


class FakeFetchMetadata:
    async def execute(self, **kwargs: Any) -> Any:
        progress = kwargs.get("progress")
        if progress is not None:
            progress(SimpleNamespace(name="Tale Of Us"), 1, 2)
            progress(SimpleNamespace(name="ARTBAT"), 2, 2)
        return SimpleNamespace(
            artists_processed=2,
            artists_failed=0,
            artists_skipped=0,
            tracks_found=20,
            tracks_saved=18,
        )


class FakeFetchArtistTracks:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(self, artist_name: str, **kwargs: Any) -> Any:
        self.calls.append({"artist_name": artist_name, **kwargs})
        progress = kwargs.get("progress")
        if progress is not None:
            progress(
                SimpleNamespace(
                    stage="fetching",
                    artist=artist_name,
                    processed=0,
                    total=kwargs.get("tracks_limit", 50),
                    message=f"Fetching {artist_name}",
                )
            )
        auto_index = kwargs.get("auto_index", True)
        discover_related = kwargs.get("discover_related", False)
        return SimpleNamespace(
            artist=artist_name,
            tracks_found=10,
            tracks_saved=8,
            tracks_indexed=8 if auto_index else 0,
            related_seeds_found=5 if discover_related else 0,
        )


class FakeCrawlITunesSeeds:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        progress = kwargs.get("progress")
        terms = kwargs.get("terms") or ("hypnotic techno", "Drumcode")
        if progress is not None:
            for idx, term in enumerate(terms, start=1):
                progress(term, idx, len(terms), 10)
        return SimpleNamespace(
            terms_processed=len(terms),
            terms_failed=0,
            tracks_found=len(terms) * 10,
            tracks_saved=len(terms) * 8,
            artists_discovered=len(terms) * 4,
        )


class FakeAnalyzeDJSet:
    def __init__(self, dj_set: DJSet) -> None:
        self._dj_set = dj_set
        self.calls: list[dict[str, Any]] = []

    async def execute(self, source: str, **kwargs: Any) -> DJSet:
        self.calls.append({"source": source, **kwargs})
        progress = kwargs.get("progress")
        if progress is not None:
            progress(
                SimpleNamespace(
                    stage="analyze", completed=1, total=2, message="passage 1"
                )
            )
        return self._dj_set


class FakeImportLocalLibrary:
    def __init__(
        self,
        *,
        scanned: int = 10,
        imported: int = 8,
        embedded: int = 8,
        failed: int = 0,
        artists_seeded: int = 5,
    ) -> None:
        self.scanned = scanned
        self.imported = imported
        self.embedded = embedded
        self.failed = failed
        self.artists_seeded = artists_seeded
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        folder_path: Any,
        *,
        recursive: bool = True,
        batch_size: int = 16,
        reindex: bool = False,
        seed_artists: bool = True,
        progress: Any = None,
    ) -> Any:
        self.calls.append(
            {
                "folder_path": folder_path,
                "recursive": recursive,
                "batch_size": batch_size,
                "reindex": reindex,
                "seed_artists": seed_artists,
            }
        )
        if progress is not None:
            progress(
                SimpleNamespace(
                    stage="indexing",
                    completed=self.imported,
                    total=self.scanned,
                    failed=self.failed,
                    message="Artist - Title",
                )
            )
        return SimpleNamespace(
            scanned=self.scanned,
            imported=self.imported,
            embedded=self.embedded,
            failed=self.failed,
            artists_seeded=self.artists_seeded,
        )


class FakeDownloader:
    def __init__(self) -> None:
        self.calls: list[tuple[Path | None, str | None]] = []

    def set_cookie_overrides(
        self,
        *,
        cookies_file: Path | None,
        cookies_from_browser: str | None,
    ) -> None:
        self.calls.append((cookies_file, cookies_from_browser))


class FakeHardwareProbe:
    def probe(self) -> HardwareInfo:
        return HardwareInfo(
            torch_version="2.6.0",
            cuda_available=True,
            cuda_version="12.4",
            gpu_name="GTX 1660 Super",
            vram_total_mb=6144,
            vram_free_mb=5000,
            ram_total_mb=16384,
            ram_free_mb=8000,
            ffmpeg_path="C:/ffmpeg/bin/ffmpeg.exe",
            ffmpeg_version="ffmpeg version 7",
        )


class FakeTrackDownloader(ITrackDownloader):
    """In-memory downloader fake for testing."""

    def __init__(self, output_file: str = "storage/downloads/test.m4a") -> None:
        self.output_file = output_file
        self.downloaded_tracks: list[Track] = []

    async def download_track(
        self, track: Track, output_dir: str
    ) -> TrackDownloadResult:
        self.downloaded_tracks.append(track)
        file_path = f"{output_dir}/{track.artist} - {track.title}.m4a"
        return TrackDownloadResult(
            track_id=track.id,
            file_path=file_path,
            format="m4a",
        )


def make_set(set_id: str = "set:1") -> DJSet:
    match = TrackMatch(
        track=make_track("itunes:1"),
        similarity_score=0.93,
        is_exact_id=True,
    )
    passage = Passage(
        time_range=TimeRange(0.0, 30.0),
        bpm=126.0,
        key="8A",
        exact_id_match=True,
        closest_matches=(match,),
        exact_id_title="Night Drive",
        exact_id_artist="Solomun",
        exact_id_source="shazam",
        embedding=EmbeddingVector(values=(1.0, 0.0), dimension=2),
    )
    return DJSet(
        id=set_id,
        title="Sunset Set",
        artist="DJ Test",
        source_url="https://youtube.test/watch?v=1",
        passages=(passage,),
        duration_seconds=3600.0,
        bpm_min=124.0,
        bpm_max=128.0,
        embedding=EmbeddingVector(values=(1.0, 0.0), dimension=2),
    )


def make_container(
    *,
    tracks: Sequence[Track] | None = None,
    sets: Sequence[DJSet] | None = None,
    similar_sets: Sequence[SetMatch] = (),
    index_catalog: Any | None = None,
) -> SimpleNamespace:
    """Build a duck-typed container with real use cases over fake stores."""
    track_list = list(
        tracks
        if tracks is not None
        else [
            make_track("itunes:1", title="Night Drive", artist="Solomun"),
            make_track(
                "itunes:2", title="Sunrise", artist="Tale Of Us", embedding=(0.0, 1.0)
            ),
            make_track("itunes:3", title="Horizon", artist="ARTBAT", embedding=None),
        ]
    )
    track_repository = FakeTrackRepository(track_list)
    set_list = list(sets) if sets is not None else [make_set()]
    set_repository = FakeSetRepository(set_list, similar_sets)
    blacklist_repository = FakeBlacklistRepository()
    liked_artist_repository = FakeLikedArtistRepository()
    planned_set_repository = FakePlannedSetRepository()
    seed_repository = FakeSeedRepository()
    manage_catalog = ManageCatalog(
        track_repository=track_repository,
        seed_repository=seed_repository,
        blacklist_repository=blacklist_repository,
        liked_artist_repository=liked_artist_repository,
    )
    dj_set_helper = DJSetHelper(
        track_repository=track_repository,
        planned_set_repository=planned_set_repository,
        blacklist_repository=blacklist_repository,
    )
    embedder = FakeClapEmbedder()
    decoder = FakeDecoder()
    dj_set = set_list[0] if set_list else make_set()
    fake_vectors = FakeVectors(track_list)
    fake_sqlite = FakeSqlite(track_list)
    track_downloader = FakeTrackDownloader()
    download_tracks = DownloadTracks(
        track_repository=track_repository,
        downloader=track_downloader,
        output_dir="storage/downloads",
    )

    return SimpleNamespace(
        settings=SimpleNamespace(
            clap_batch_size=16,
            preview_concurrency=16,
            set_cache_dir=Path("cache"),
            download_dir=Path("storage/downloads"),
            amdl_base_url="https://am-dl.pages.dev",
            amdl_timeout_seconds=45,
            ytdlp_cookies_file=None,
            ytdlp_cookies_from_browser=None,
        ),
        sqlite=fake_sqlite,
        vectors=fake_vectors,
        track_repository=track_repository,
        seed_repository=seed_repository,
        blacklist_repository=blacklist_repository,
        liked_artist_repository=liked_artist_repository,
        planned_set_repository=planned_set_repository,
        manage_catalog=manage_catalog,
        dj_set_helper=dj_set_helper,
        track_downloader=track_downloader,
        download_tracks=download_tracks,
        set_repository=set_repository,
        dig_similar_tracks=DigSimilarTracks(track_repository=track_repository),
        find_similar_for_set=FindSimilarForSet(
            track_repository=track_repository,
            set_repository=set_repository,
        ),
        vibe_search=VibeSearch(embedder=embedder, track_repository=track_repository),
        index_catalog=index_catalog or FakeIndexCatalog(),
        build_seed_list=FakeBuildSeedList(),
        crawl_itunes_seeds=FakeCrawlITunesSeeds(),
        fetch_catalog_metadata=FakeFetchMetadata(),
        fetch_artist_tracks=FakeFetchArtistTracks(),
        import_local_library=FakeImportLocalLibrary(),
        analyze_dj_set=FakeAnalyzeDJSet(dj_set),
        set_downloader=FakeDownloader(),
        clap_embedder=embedder,
        audio_decoder=decoder,
        feature_extractor=object(),
        hardware_probe=FakeHardwareProbe(),
    )
