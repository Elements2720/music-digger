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
    SourceStat,
)
from domain.entities.dj_set import DJSet, Passage, SetMatch, TrackMatch
from domain.entities.search import SearchFilter
from domain.entities.track import AudioBuffer, BlacklistEntry, SeedArtist, Track
from domain.interfaces.repositories import (
    IBlacklistRepository,
    ISetRepository,
    ITrackRepository,
)
from domain.use_cases import (
    DigSimilarTracks,
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
        self, limit: int = 20, *, offset: int = 0
    ) -> Sequence[Track]:
        embedded = [t for t in self.tracks.values() if t.embedding is not None]
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
        sort: str = "tracks_desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[ArtistSummary], int]:
        by_artist: dict[str, list[Track]] = {}
        for t in self.tracks.values():
            by_artist.setdefault(t.artist, []).append(t)

        summaries: list[ArtistSummary] = []
        for artist, trks in by_artist.items():
            if query and query.casefold() not in artist.casefold():
                continue
            if genre and not any(
                t.genre and t.genre.casefold() == genre.casefold() for t in trks
            ):
                continue
            if source and not any(t.source == source for t in trks):
                continue
            genres = tuple({t.genre for t in trks if t.genre})
            sources = tuple({t.source for t in trks if t.source})
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
                )
            )

        if sort == "artist_asc":
            summaries.sort(key=lambda s: s.artist.casefold())
        elif sort == "embedded_desc":
            summaries.sort(
                key=lambda s: (s.embedded_count, s.track_count), reverse=True
            )
        else:
            summaries.sort(
                key=lambda s: (s.track_count, s.embedded_count), reverse=True
            )

        return (tuple(summaries[offset : offset + limit]), len(summaries))

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
        self._counts = {
            "total": total,
            "pending": pending,
            "fetched": fetched,
            "failed": failed,
            "electronic": electronic,
            "general": general,
        }

    async def count(self) -> int:
        return self._counts["total"]

    async def count_by_status(self, status: str) -> int:
        return self._counts[status]

    async def count_by_category(self, category: str) -> int:
        return self._counts[category]

    async def list_by_source(
        self, source: str, limit: int = 100
    ) -> Sequence[SeedArtist]:
        return ()

    async def delete_by_name(self, name: str) -> bool:
        return True


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
    seed_repository = FakeSeedRepository()
    manage_catalog = ManageCatalog(
        track_repository=track_repository,
        seed_repository=seed_repository,
        blacklist_repository=blacklist_repository,
    )
    embedder = FakeClapEmbedder()
    decoder = FakeDecoder()
    dj_set = set_list[0] if set_list else make_set()

    return SimpleNamespace(
        settings=SimpleNamespace(
            clap_batch_size=16,
            preview_concurrency=16,
            set_cache_dir=Path("cache"),
            ytdlp_cookies_file=None,
            ytdlp_cookies_from_browser=None,
        ),
        track_repository=track_repository,
        seed_repository=seed_repository,
        blacklist_repository=blacklist_repository,
        manage_catalog=manage_catalog,
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
        import_local_library=FakeImportLocalLibrary(),
        analyze_dj_set=FakeAnalyzeDJSet(dj_set),
        set_downloader=FakeDownloader(),
        clap_embedder=embedder,
        audio_decoder=decoder,
        feature_extractor=object(),
        hardware_probe=FakeHardwareProbe(),
    )
