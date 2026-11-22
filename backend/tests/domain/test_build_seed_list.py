"""Tests for BuildSeedList use case and its progress callback."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from domain.entities.track import SeedArtist
from domain.interfaces.catalog import ISeedDiscovery
from domain.interfaces.repositories import ISeedRepository
from domain.use_cases.build_seed_list import BuildSeedList, CrawlProgress


@dataclass
class FakeSeedRepository(ISeedRepository):
    seeds: dict[str, SeedArtist] = field(default_factory=dict)

    async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int:
        for seed in seeds:
            self.seeds[seed.name.casefold()] = seed
        return len(seeds)

    async def record_discovery(
        self,
        seeds: Sequence[SeedArtist],
        *,
        priority_increment: float = 0.05,
    ) -> int:
        for seed in seeds:
            self.seeds[seed.name.casefold()] = seed
        return len(seeds)

    async def get_by_name(self, name: str) -> SeedArtist | None:
        return self.seeds.get(name.casefold())

    async def list_by_status(self, status: str, limit: int = 100) -> list[SeedArtist]:
        return [s for s in self.seeds.values() if s.status == status][:limit]

    async def update_status(self, name: str, status: str) -> None:
        pass

    async def count_by_category(self, category: str) -> int:
        return sum(1 for s in self.seeds.values() if s.category == category)

    async def count_by_status(self, status: str) -> int:
        return sum(1 for s in self.seeds.values() if s.status == status)

    async def count(self) -> int:
        return len(self.seeds)


class FakeDiscovery(ISeedDiscovery):
    def __init__(self, seeds: Sequence[SeedArtist]) -> None:
        self._seeds = tuple(seeds)

    async def discover(
        self,
        *,
        electronic_limit: int = 1000,
        general_limit: int = 300,
        max_depth: int = 2,
        progress: object = None,
    ) -> Sequence[SeedArtist]:
        if callable(progress):
            progress(CrawlProgress(stage="electronic", name="Seed 1", depth=0, found=1))
            progress(CrawlProgress(stage="electronic", name="Seed 2", depth=1, found=2))
        return self._seeds


async def test_build_seed_list_progress_events() -> None:
    seed1 = SeedArtist(name="Seed 1", priority_score=0.9, category="electronic")
    seed2 = SeedArtist(name="Seed 2", priority_score=0.8, category="electronic")
    repo = FakeSeedRepository()
    discovery = FakeDiscovery([seed1, seed2])
    use_case = BuildSeedList(discovery=discovery, seed_repository=repo)

    events: list[CrawlProgress] = []
    result = await use_case.execute(
        electronic_limit=10,
        general_limit=5,
        use_deezer=True,
        progress=events.append,
    )

    assert result.discovered == 2
    assert result.written == 2
    assert len(events) == 3
    assert events[0] == CrawlProgress(
        stage="electronic", name="Seed 1", depth=0, found=1
    )
    assert events[1] == CrawlProgress(
        stage="electronic", name="Seed 2", depth=1, found=2
    )
    assert events[2] == CrawlProgress(
        stage="writing", name="", depth=None, found=2
    )


async def test_build_seed_list_default_progress_is_none() -> None:
    seed = SeedArtist(name="Seed 1", priority_score=0.9, category="electronic")
    repo = FakeSeedRepository()
    discovery = FakeDiscovery([seed])
    use_case = BuildSeedList(discovery=discovery, seed_repository=repo)

    result = await use_case.execute(
        electronic_limit=10,
        general_limit=5,
        use_deezer=True,
    )

    assert result.discovered == 1
    assert result.written == 1
