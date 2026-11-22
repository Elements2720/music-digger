"""Shared fakes for data-layer tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from domain.entities.track import SeedArtist, SeedStatus, Track
from domain.interfaces.repositories import ISeedRepository
from domain.value_objects.audio_features import EmbeddingVector


class FakeClock:
    """Deterministic clock/sleep pair for rate-limiter tests."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class InMemorySeedRepository(ISeedRepository):
    """Seed repository double that records every write."""

    def __init__(self, *, increment: float = 0.05) -> None:
        self._increment = increment
        self._seeds: dict[str, SeedArtist] = {}
        self.discovery_calls: list[SeedArtist] = []
        self.upsert_calls: list[SeedArtist] = []

    async def upsert_many(self, seeds: Any) -> int:
        self.upsert_calls.extend(seeds)
        for seed in seeds:
            key = seed.name.casefold()
            existing = self._seeds.get(key)
            if existing is None:
                self._seeds[key] = seed
            else:
                self._seeds[key] = replace(
                    existing,
                    priority_score=max(existing.priority_score, seed.priority_score),
                    source=seed.source,
                    external_id=seed.external_id or existing.external_id,
                )
        return len(seeds)

    async def record_discovery(
        self,
        seeds: Any,
        *,
        priority_increment: float | None = None,
    ) -> int:
        increment = (
            self._increment if priority_increment is None else priority_increment
        )
        self.discovery_calls.extend(seeds)
        for seed in seeds:
            key = seed.name.casefold()
            existing = self._seeds.get(key)
            if existing is None:
                self._seeds[key] = seed
            else:
                self._seeds[key] = replace(
                    existing,
                    priority_score=min(
                        1.0,
                        max(existing.priority_score, seed.priority_score) + increment,
                    ),
                    source=seed.source,
                    external_id=seed.external_id or existing.external_id,
                )
        return len(seeds)

    async def get_by_name(self, name: str) -> SeedArtist | None:
        return self._seeds.get(name.casefold())

    async def list_by_status(
        self,
        status: SeedStatus,
        limit: int = 100,
    ) -> list[SeedArtist]:
        matching = [seed for seed in self._seeds.values() if seed.status == status]
        matching.sort(key=lambda seed: (-seed.priority_score, seed.name.casefold()))
        return matching[: max(0, limit)]

    async def list_by_source(
        self,
        source: str,
        limit: int = 100,
    ) -> list[SeedArtist]:
        matching = [seed for seed in self._seeds.values() if seed.source == source]
        matching.sort(key=lambda seed: (-seed.priority_score, seed.name.casefold()))
        return matching[: max(0, limit)]

    async def update_status(self, name: str, status: SeedStatus) -> None:
        key = name.casefold()
        if key in self._seeds:
            self._seeds[key] = replace(self._seeds[key], status=status)

    async def count_by_category(self, category: str) -> int:
        return sum(1 for seed in self._seeds.values() if seed.category == category)

    async def count_by_status(self, status: SeedStatus) -> int:
        return sum(1 for seed in self._seeds.values() if seed.status == status)

    async def count(self) -> int:
        return len(self._seeds)


class FakeTrackRepository:
    """Minimal track repository double for use-case tests."""

    def __init__(self) -> None:
        self.saved: list[Track] = []

    async def upsert_many(self, tracks: Any) -> int:
        self.saved.extend(tracks)
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        for track in self.saved:
            if track.id == track_id:
                return track
        return None

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        for track in self.saved:
            if track.source == source and track.external_id == external_id:
                return track
        return None

    async def get_many(self, track_ids: Any) -> list[Track]:
        wanted = set(track_ids)
        return [track for track in self.saved if track.id in wanted]

    async def get_embedded_ids(self, track_ids: Any) -> frozenset[str]:
        wanted = set(track_ids)
        return frozenset(
            track.id
            for track in self.saved
            if track.id in wanted and track.embedding is not None
        )

    async def find_similar(
        self,
        embedding: EmbeddingVector,
        search_filter: Any,
    ) -> list[Any]:
        return []

    async def find_by_filter(self, search_filter: Any) -> list[Track]:
        return []

    async def mark_heard(self, track_id: str) -> None:
        return None

    async def get_heard_ids(self) -> frozenset[str]:
        return frozenset()

    async def count(self) -> int:
        return len(self.saved)

    async def count_embedded(self) -> int:
        return sum(1 for track in self.saved if track.embedding is not None)
