"""Tests for Phase 2 use cases against in-memory interface doubles."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import pytest

from domain.entities.track import SeedArtist, Track, TrackReference, TrackVibe
from domain.interfaces.catalog import ICatalogProvider, ISeedDiscovery
from domain.interfaces.llm import ILLMService
from domain.use_cases import BuildSeedList, FetchCatalogMetadata


@dataclass
class FakeSeedRepository:
    seeds: dict[str, SeedArtist] = field(default_factory=dict)

    async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int:
        for seed in seeds:
            key = seed.name.casefold()
            existing = self.seeds.get(key)
            if existing is None:
                self.seeds[key] = seed
            else:
                self.seeds[key] = replace(
                    existing,
                    priority_score=max(existing.priority_score, seed.priority_score),
                    source=seed.source,
                )
        return len(seeds)

    async def record_discovery(
        self,
        seeds: Sequence[SeedArtist],
        *,
        priority_increment: float = 0.05,
    ) -> int:
        for seed in seeds:
            key = seed.name.casefold()
            existing = self.seeds.get(key)
            if existing is None:
                self.seeds[key] = seed
            else:
                self.seeds[key] = replace(
                    existing,
                    priority_score=min(
                        1.0,
                        max(existing.priority_score, seed.priority_score)
                        + priority_increment,
                    ),
                    source=seed.source,
                )
        return len(seeds)

    async def get_by_name(self, name: str) -> SeedArtist | None:
        return self.seeds.get(name.casefold())

    async def list_by_status(
        self,
        status: str,
        limit: int = 100,
    ) -> list[SeedArtist]:
        matching = [seed for seed in self.seeds.values() if seed.status == status]
        matching.sort(key=lambda seed: (-seed.priority_score, seed.name.casefold()))
        return matching[: max(0, limit)]

    async def update_status(self, name: str, status: str) -> None:
        key = name.casefold()
        if key in self.seeds:
            self.seeds[key] = replace(self.seeds[key], status=status)  # type: ignore[arg-type]

    async def count_by_category(self, category: str) -> int:
        return sum(1 for seed in self.seeds.values() if seed.category == category)

    async def count_by_status(self, status: str) -> int:
        return sum(1 for seed in self.seeds.values() if seed.status == status)

    async def count(self) -> int:
        return len(self.seeds)


class FakeDiscovery(ISeedDiscovery):
    def __init__(self, seeds: Sequence[SeedArtist]) -> None:
        self._seeds = tuple(seeds)
        self.calls: list[dict[str, int]] = []

    async def discover(
        self,
        *,
        electronic_limit: int = 1000,
        general_limit: int = 300,
        max_depth: int = 2,
    ) -> Sequence[SeedArtist]:
        self.calls.append(
            {
                "electronic_limit": electronic_limit,
                "general_limit": general_limit,
                "max_depth": max_depth,
            }
        )
        return self._seeds


class FakeLLM(ILLMService):
    def __init__(self, seeds: Sequence[SeedArtist]) -> None:
        self._seeds = tuple(seeds)
        self.calls: list[dict[str, object]] = []

    async def extract_tracklist_from_comments(
        self,
        comments: Sequence[str],
        *,
        context: str | None = None,
    ) -> Sequence[TrackReference]:
        return ()

    async def generate_seed_artists(
        self,
        *,
        genres: Sequence[str],
        count: int = 25,
        exclude_artists: Sequence[str] = (),
    ) -> Sequence[SeedArtist]:
        self.calls.append(
            {"genres": tuple(genres), "count": count, "exclude": tuple(exclude_artists)}
        )
        return self._seeds[:count]

    async def tag_track_vibe(self, track: Track) -> TrackVibe:
        return TrackVibe(tags=(), mood="neutral", energy=0.5)


class FakeProvider(ICatalogProvider):
    def __init__(self, tracks: Sequence[Track], *, fail_on: set[str] | None = None):
        self._tracks = tuple(tracks)
        self._fail_on = fail_on or set()
        self.requested: list[str] = []

    @property
    def provider_id(self) -> str:
        return "fake"

    async def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        return self._tracks[:limit]

    async def lookup_track(self, provider_track_id: str) -> Track | None:
        return next(
            (track for track in self._tracks if track.external_id == provider_track_id),
            None,
        )

    async def list_artist_tracks(
        self,
        artist_name: str,
        *,
        limit: int = 50,
    ) -> Sequence[Track]:
        self.requested.append(artist_name)
        if artist_name in self._fail_on:
            raise RuntimeError("provider exploded")
        return self._tracks[:limit]

    async def fetch_preview(self, track: Track) -> bytes | None:
        return None


@dataclass
class FakeTrackRepository:
    saved: list[Track] = field(default_factory=list)

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        self.saved.extend(tracks)
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        return next((track for track in self.saved if track.id == track_id), None)

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        return next(
            (
                track
                for track in self.saved
                if track.source == source and track.external_id == external_id
            ),
            None,
        )

    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        return [track for track in self.saved if track.id in set(track_ids)]

    async def find_similar(self, embedding: object, search_filter: object):
        return []

    async def find_by_filter(self, search_filter: object):
        return []

    async def mark_heard(self, track_id: str) -> None:
        return None

    async def get_heard_ids(self) -> frozenset[str]:
        return frozenset()

    async def count(self) -> int:
        return len(self.saved)

    async def count_embedded(self) -> int:
        return 0


def _seed(name: str, priority: float, category: str = "electronic") -> SeedArtist:
    return SeedArtist(name=name, priority_score=priority, category=category)


def _track(track_id: str) -> Track:
    return Track(
        id=track_id,
        title=f"Song {track_id}",
        artist="Artist",
        source="itunes",
        external_id=track_id,
        preview_url="https://example.test/preview.m4a",
        duration_seconds=300.0,
    )


async def test_build_seed_list_records_discoveries_and_counts() -> None:
    discovery = FakeDiscovery([_seed("A", 0.8), _seed("B", 0.6)])
    seeds = FakeSeedRepository()
    use_case = BuildSeedList(discovery=discovery, seed_repository=seeds)  # type: ignore[arg-type]

    result = await use_case.execute(electronic_limit=2, general_limit=1, max_depth=2)

    assert result.discovered == 2
    assert result.llm_generated == 0
    assert result.written == 2
    assert result.electronic_total == 2
    assert result.general_total == 0
    assert discovery.calls == [
        {"electronic_limit": 2, "general_limit": 1, "max_depth": 2}
    ]
    assert await seeds.count() == 2


async def test_build_seed_list_supplements_with_llm_seeds() -> None:
    discovery = FakeDiscovery([_seed("A", 0.8)])
    llm = FakeLLM([_seed("L", 0.7, "general")])
    seeds = FakeSeedRepository()
    use_case = BuildSeedList(  # type: ignore[arg-type]
        discovery=discovery,
        seed_repository=seeds,
        llm_service=llm,
    )

    result = await use_case.execute(
        electronic_limit=1,
        general_limit=1,
        llm_genres=("Melodic Techno", "Afro House"),
        llm_count=1,
    )

    assert result.discovered == 1
    assert result.llm_generated == 1
    assert llm.calls == [
        {
            "genres": ("Melodic Techno", "Afro House"),
            "count": 1,
            "exclude": (),
        }
    ]
    assert await seeds.get_by_name("L") is not None


async def test_build_seed_list_rediscovery_bumps_priority() -> None:
    seeds = FakeSeedRepository()
    await seeds.record_discovery([_seed("A", 0.5)])
    use_case = BuildSeedList(  # type: ignore[arg-type]
        discovery=FakeDiscovery([_seed("A", 0.5)]),
        seed_repository=seeds,
    )
    await use_case.execute(electronic_limit=1, general_limit=0)
    seed = await seeds.get_by_name("A")
    assert seed is not None
    assert seed.priority_score == pytest.approx(0.55)


async def test_build_seed_list_validates_arguments() -> None:
    seeds = FakeSeedRepository()
    use_case = BuildSeedList(  # type: ignore[arg-type]
        discovery=None,
        seed_repository=seeds,
    )
    with pytest.raises(ValueError, match="electronic_limit"):
        await use_case.execute(electronic_limit=-1)
    with pytest.raises(ValueError, match="general_limit"):
        await use_case.execute(general_limit=-1)
    with pytest.raises(ValueError, match="max_depth"):
        await use_case.execute(max_depth=-1)
    with pytest.raises(ValueError, match="llm_count"):
        await use_case.execute(llm_count=-1)


async def test_fetch_catalog_metadata_processes_pending_by_priority() -> None:
    seeds = FakeSeedRepository()
    await seeds.upsert_many([_seed("Low", 0.3), _seed("High", 0.9), _seed("Mid", 0.6)])
    provider = FakeProvider([_track("1"), _track("2")])
    tracks = FakeTrackRepository()
    use_case = FetchCatalogMetadata(  # type: ignore[arg-type]
        seed_repository=seeds,  # type: ignore[arg-type]
        catalog_provider=provider,
        track_repository=tracks,  # type: ignore[arg-type]
    )
    progress: list[tuple[str, int, int]] = []

    def on_progress(seed: SeedArtist, index: int, total: int) -> None:
        progress.append((seed.name, index, total))

    result = await use_case.execute(
        artists_limit=10,
        tracks_per_artist=50,
        progress=on_progress,
    )

    assert provider.requested == ["High", "Mid", "Low"]
    assert result.artists_processed == 3
    assert result.artists_failed == 0
    assert result.tracks_found == 6
    assert result.tracks_saved == 6
    assert [name for name, _, _ in progress] == ["High", "Mid", "Low"]
    for name in ("High", "Mid", "Low"):
        seed = await seeds.get_by_name(name)
        assert seed is not None and seed.status == "fetched"


async def test_fetch_catalog_metadata_marks_failures_and_continues() -> None:
    seeds = FakeSeedRepository()
    await seeds.upsert_many([_seed("Good", 0.9), _seed("Bad", 0.8)])
    provider = FakeProvider([_track("1")], fail_on={"Bad"})
    tracks = FakeTrackRepository()
    use_case = FetchCatalogMetadata(  # type: ignore[arg-type]
        seed_repository=seeds,  # type: ignore[arg-type]
        catalog_provider=provider,
        track_repository=tracks,  # type: ignore[arg-type]
    )

    result = await use_case.execute(artists_limit=5, tracks_per_artist=10)

    assert result.artists_processed == 1
    assert result.artists_failed == 1
    assert (await seeds.get_by_name("Bad")).status == "failed"
    assert (await seeds.get_by_name("Good")).status == "fetched"


async def test_fetch_catalog_metadata_retry_failed_takes_precedence() -> None:
    seeds = FakeSeedRepository()
    await seeds.upsert_many([_seed("Failed Seed", 0.9), _seed("Pending Seed", 0.8)])
    await seeds.update_status("Failed Seed", "failed")
    provider = FakeProvider([_track("1")])
    tracks = FakeTrackRepository()
    use_case = FetchCatalogMetadata(  # type: ignore[arg-type]
        seed_repository=seeds,  # type: ignore[arg-type]
        catalog_provider=provider,
        track_repository=tracks,  # type: ignore[arg-type]
    )

    default_run = await use_case.execute(artists_limit=1)
    assert provider.requested == ["Pending Seed"]
    assert default_run.artists_processed == 1

    retry_run = await use_case.execute(artists_limit=1, retry_failed=True)
    assert retry_run.artists_processed == 1
    assert (await seeds.get_by_name("Failed Seed")).status == "fetched"


async def test_fetch_catalog_metadata_validates_arguments() -> None:
    use_case = FetchCatalogMetadata(  # type: ignore[arg-type]
        seed_repository=FakeSeedRepository(),  # type: ignore[arg-type]
        catalog_provider=FakeProvider([]),
        track_repository=FakeTrackRepository(),  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="artists_limit"):
        await use_case.execute(artists_limit=0)
    with pytest.raises(ValueError, match="tracks_per_artist"):
        await use_case.execute(tracks_per_artist=0)
