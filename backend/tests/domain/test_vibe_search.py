"""Tests for the text-to-audio VibeSearch use case."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from domain.entities.dj_set import TrackMatch
from domain.entities.search import SearchFilter
from domain.entities.track import AudioBuffer, Track
from domain.use_cases import VibeSearch
from domain.value_objects.audio_features import EmbeddingVector


def make_track(track_id: str) -> Track:
    return Track(id=track_id, title=f"Title {track_id}", artist=f"Artist {track_id}")


class FakeEmbedder:
    """Records text queries and returns a fixed 2-D vector."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_text(self, query: str) -> EmbeddingVector:
        self.queries.append(query)
        return EmbeddingVector(values=(0.6, 0.8), dimension=2)

    def embed(self, audio: AudioBuffer) -> EmbeddingVector:  # pragma: no cover
        raise AssertionError("vibe search must not embed audio")

    def embed_batch(  # pragma: no cover
        self, audios: Sequence[AudioBuffer]
    ) -> Sequence[EmbeddingVector]:
        raise AssertionError("vibe search must not embed audio")


class FakeTrackRepository:
    """Returns a fixed ranked list and records the search arguments."""

    def __init__(self, matches: Sequence[TrackMatch]) -> None:
        self._matches = tuple(matches)
        self.calls: list[tuple[EmbeddingVector, SearchFilter]] = []

    async def find_similar(
        self,
        embedding: EmbeddingVector,
        search_filter: SearchFilter,
    ) -> Sequence[TrackMatch]:
        self.calls.append((embedding, search_filter))
        return self._matches


def make_use_case(
    matches: Sequence[TrackMatch] | None = None,
) -> tuple[VibeSearch, FakeEmbedder, FakeTrackRepository]:
    embedder = FakeEmbedder()
    repository = FakeTrackRepository(matches or ())
    use_case = VibeSearch(embedder=embedder, track_repository=repository)
    return use_case, embedder, repository


async def test_embeds_the_text_and_returns_repository_matches() -> None:
    expected = (
        TrackMatch(track=make_track("itunes:1"), similarity_score=0.91),
        TrackMatch(track=make_track("itunes:2"), similarity_score=0.72),
    )
    use_case, embedder, repository = make_use_case(expected)

    result = await use_case.execute("  dark hypnotic techno  ")

    assert tuple(result) == expected
    assert embedder.queries == ["dark hypnotic techno"], "the query is stripped"
    ((embedding, search_filter),) = repository.calls
    assert embedding.values == (0.6, 0.8)
    assert search_filter == SearchFilter(), "defaults are used when no filter is given"


async def test_passes_the_search_filter_through_unchanged() -> None:
    search_filter = SearchFilter(
        bpm_min=124,
        bpm_max=132,
        exclude_heard=True,
        genre_filter="Techno",
        limit=12,
    )
    use_case, _, repository = make_use_case()

    await use_case.execute("rolling bassline", search_filter)

    assert repository.calls[0][1] is search_filter


async def test_blank_query_is_rejected_before_embedding() -> None:
    use_case, embedder, repository = make_use_case()

    with pytest.raises(ValueError):
        await use_case.execute("   ")

    assert embedder.queries == []
    assert repository.calls == []


async def test_embedder_without_text_support_surfaces_the_error() -> None:
    class AudioOnlyEmbedder(FakeEmbedder):
        def embed_text(self, query: str) -> EmbeddingVector:
            raise NotImplementedError("this embedder does not support text queries")

    repository = FakeTrackRepository(())
    use_case = VibeSearch(
        embedder=AudioOnlyEmbedder(),
        track_repository=repository,
    )

    with pytest.raises(NotImplementedError):
        await use_case.execute("techno")
    assert repository.calls == []
