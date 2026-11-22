"""Use case: build a prioritized seed-artist list from graph and LLM sources.

The use case depends only on domain interfaces. Concrete Deezer and LLM
clients are injected by the composition root.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..entities.track import SeedArtist
from ..interfaces.catalog import ISeedDiscovery
from ..interfaces.llm import ILLMService
from ..interfaces.repositories import ISeedRepository


@dataclass(frozen=True, slots=True)
class CrawlProgress:
    """Progress event emitted during seed discovery."""

    stage: str
    name: str
    depth: int | None
    found: int


@dataclass(frozen=True, slots=True)
class BuildSeedListResult:
    """Summary of one seed-list build run."""

    discovered: int
    llm_generated: int
    written: int
    electronic_total: int
    general_total: int

    @property
    def total(self) -> int:
        """Total number of seeds currently stored."""
        return self.electronic_total + self.general_total


class BuildSeedList:
    """Populate ``seed_artists`` from a discovery graph and/or a local LLM."""

    def __init__(
        self,
        *,
        discovery: ISeedDiscovery | None,
        seed_repository: ISeedRepository,
        llm_service: ILLMService | None = None,
    ) -> None:
        self._discovery = discovery
        self._seed_repository = seed_repository
        self._llm_service = llm_service

    async def execute(
        self,
        *,
        electronic_limit: int = 1000,
        general_limit: int = 300,
        max_depth: int = 2,
        use_deezer: bool = True,
        llm_genres: Sequence[str] = (),
        llm_count: int = 0,
        exclude_artists: Sequence[str] = (),
        progress: Callable[[CrawlProgress], None] | None = None,
        use_local_seeds: bool = False,
        seed_artists: Sequence[str] | None = None,
    ) -> BuildSeedListResult:
        """Discover seeds, persist them, and return the resulting counts.

        Deezer discoveries go through :meth:`ISeedRepository.record_discovery`
        so rediscovered artists receive a priority bump. LLM suggestions use a
        plain upsert and therefore never reset an already-fetched artist.
        """
        if electronic_limit < 0:
            raise ValueError("electronic_limit must not be negative")
        if general_limit < 0:
            raise ValueError("general_limit must not be negative")
        if max_depth < 0:
            raise ValueError("max_depth must not be negative")
        if llm_count < 0:
            raise ValueError("llm_count must not be negative")

        effective_seed_artists = seed_artists
        if use_local_seeds:
            local_seeds = await self._seed_repository.list_by_source(
                "local-library", limit=100
            )
            if local_seeds:
                effective_seed_artists = tuple(seed.name for seed in local_seeds)

        discovered: Sequence[SeedArtist] = ()
        if use_deezer and self._discovery is not None:
            if effective_seed_artists is not None:
                discovered = await self._discovery.discover(
                    electronic_limit=electronic_limit,
                    general_limit=general_limit,
                    max_depth=max_depth,
                    progress=progress,
                    seed_artists=effective_seed_artists,
                )
            else:
                discovered = await self._discovery.discover(
                    electronic_limit=electronic_limit,
                    general_limit=general_limit,
                    max_depth=max_depth,
                    progress=progress,
                )

        llm_generated: Sequence[SeedArtist] = ()
        if self._llm_service is not None and llm_count > 0 and llm_genres:
            llm_generated = await self._llm_service.generate_seed_artists(
                genres=tuple(llm_genres),
                count=llm_count,
                exclude_artists=tuple(exclude_artists),
            )

        written = 0
        if discovered:
            written += await self._seed_repository.record_discovery(discovered)
        if llm_generated:
            written += await self._seed_repository.upsert_many(llm_generated)

        if progress is not None:
            progress(
                CrawlProgress(stage="writing", name="", depth=None, found=written)
            )

        return BuildSeedListResult(
            discovered=len(discovered),
            llm_generated=len(llm_generated),
            written=written,
            electronic_total=await self._seed_repository.count_by_category(
                "electronic"
            ),
            general_total=await self._seed_repository.count_by_category("general"),
        )
