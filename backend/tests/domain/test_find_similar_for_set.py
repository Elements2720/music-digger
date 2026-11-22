"""Tests for the set-to-track and set-to-set dig use case (all fakes)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from domain.entities.dj_set import DJSet, Passage, SetMatch, TrackMatch
from domain.entities.search import SearchFilter
from domain.entities.track import Track
from domain.use_cases import (
    FindSimilarForSet,
    SetNotEmbeddedError,
    SetNotFoundError,
)
from domain.value_objects.audio_features import BPM, EmbeddingVector, TimeRange

_DIMENSION = 8


def _vector(seed: float) -> EmbeddingVector:
    base = 0.1 + seed * 0.05
    return EmbeddingVector(
        values=tuple(round(base + 0.01 * index, 6) for index in range(_DIMENSION))
    )


def _track(track_id: str, *, bpm: float = 128.0) -> Track:
    return Track(id=track_id, title=f"Song {track_id}", artist="Artist", bpm=BPM(bpm))


def _set(
    set_id: str,
    *,
    passages: tuple[Passage, ...] | None = None,
    embedding: EmbeddingVector | None = None,
) -> DJSet:
    if passages is None:
        passages = ()
    return DJSet(
        id=set_id,
        title=f"Set {set_id}",
        duration_seconds=600.0,
        passages=passages,
        embedding=embedding,
    )


@dataclass
class FakeTrackRepository:
    """Returns per-call matches keyed by the passage's embedding seed."""

    responses: dict[int, tuple[TrackMatch, ...]] = field(default_factory=dict)
    filters: list[SearchFilter] = field(default_factory=list)

    async def find_similar(
        self, embedding: EmbeddingVector, search_filter: SearchFilter
    ) -> Sequence[TrackMatch]:
        self.filters.append(search_filter)
        seed = round((embedding.values[0] - 0.1) / 0.05 * 600.0)
        return self.responses.get(seed, ())


@dataclass
class FakeSetRepository:
    sets: dict[str, DJSet] = field(default_factory=dict)
    similar: Sequence[SetMatch] = ()

    async def save(self, dj_set: DJSet) -> None:  # pragma: no cover
        self.sets[dj_set.id] = dj_set

    async def get_by_id(self, set_id: str) -> DJSet | None:
        return self.sets.get(set_id)

    async def find_similar_sets(
        self, embedding: EmbeddingVector, *, limit: int = 12
    ) -> Sequence[SetMatch]:
        del embedding
        return self.similar[:limit]


def _passage(
    start: float, end: float, seed: float, *, bpm: float | None = 128.0
) -> Passage:
    return Passage(
        time_range=TimeRange(start, end),
        bpm=BPM(bpm) if bpm is not None else None,
        embedding=_vector(seed),
    )


async def test_aggregates_passage_matches_with_dedup() -> None:
    """A track surfaced by two passages keeps only its best score."""
    shared = TrackMatch(track=_track("itunes:1"), similarity_score=0.90)
    strong = TrackMatch(track=_track("itunes:2"), similarity_score=0.95)
    weak_shared = TrackMatch(track=_track("itunes:1"), similarity_score=0.80)
    only_second = TrackMatch(track=_track("itunes:3"), similarity_score=0.70)

    track_repository = FakeTrackRepository(
        responses={
            0: (shared, strong),  # passage 1 (starts at 0 s)
            300: (weak_shared, only_second),  # passage 2 (starts at 300 s)
        }
    )
    set_repository = FakeSetRepository(
        sets={
            "set-a": _set(
                "set-a",
                passages=(
                    _passage(0.0, 300.0, 0.0),
                    _passage(300.0, 600.0, 0.5),
                ),
            )
        }
    )

    result = await FindSimilarForSet(
        track_repository=track_repository,  # type: ignore[arg-type]
        set_repository=set_repository,  # type: ignore[arg-type]
    ).similar_tracks("set-a")

    assert [match.track.id for match in result.matches] == [
        "itunes:2",
        "itunes:1",
        "itunes:3",
    ]
    assert result.reference.id == "set-a"


async def test_limit_truncates_and_respects_exclude_heard() -> None:
    matches = tuple(
        TrackMatch(track=_track(f"itunes:{index}"), similarity_score=1.0 - index / 10)
        for index in range(5)
    )
    track_repository = FakeTrackRepository(responses={0: matches})
    set_repository = FakeSetRepository(
        sets={"set-a": _set("set-a", passages=(_passage(0.0, 300.0, 0.0),))}
    )
    use_case = FindSimilarForSet(
        track_repository=track_repository,  # type: ignore[arg-type]
        set_repository=set_repository,  # type: ignore[arg-type]
    )

    search_filter = SearchFilter(limit=5, exclude_heard=True, genre_filter="Techno")
    result = await use_case.similar_tracks("set-a", search_filter, limit=3)

    assert len(result.matches) == 3
    forwarded = track_repository.filters[0]
    assert forwarded.exclude_heard is True
    assert forwarded.genre_filter == "Techno"
    # Per-passage fetch is over-fetched to fill the limit after dedup.
    assert forwarded.limit == 3


async def test_bpm_tolerance_builds_passage_scoped_filters() -> None:
    track_repository = FakeTrackRepository(responses={0: ()})
    set_repository = FakeSetRepository(
        sets={
            "set-a": _set(
                "set-a",
                passages=(
                    _passage(0.0, 300.0, 0.0, bpm=128.0),
                    _passage(300.0, 600.0, 0.5, bpm=None),
                ),
            )
        }
    )
    use_case = FindSimilarForSet(
        track_repository=track_repository,  # type: ignore[arg-type]
        set_repository=set_repository,  # type: ignore[arg-type]
    )

    base = SearchFilter(limit=5, bpm_min=100.0, bpm_max=140.0)
    await use_case.similar_tracks("set-a", base, bpm_tolerance=5.0)

    first, second = track_repository.filters
    # Passage with BPM 128: window is max(100, 123) - min(140, 133).
    assert (first.bpm_min, first.bpm_max) == (123.0, 133.0)
    # Passage without BPM: the base filter passes through unchanged.
    assert (second.bpm_min, second.bpm_max) == (100.0, 140.0)


async def test_tolerance_window_outside_filter_bounds_skips_passage() -> None:
    track_repository = FakeTrackRepository(responses={0: ()})
    set_repository = FakeSetRepository(
        sets={"set-a": _set("set-a", passages=(_passage(0.0, 300.0, 0.0, bpm=128.0),))}
    )
    use_case = FindSimilarForSet(
        track_repository=track_repository,  # type: ignore[arg-type]
        set_repository=set_repository,  # type: ignore[arg-type]
    )

    # Filter only allows 140-150, the ±5 window around 128 cannot overlap.
    await use_case.similar_tracks(
        "set-a", SearchFilter(limit=5, bpm_min=140.0, bpm_max=150.0), bpm_tolerance=5.0
    )
    assert track_repository.filters == []


async def test_missing_set_raises_set_not_found() -> None:
    use_case = FindSimilarForSet(
        track_repository=FakeTrackRepository(),  # type: ignore[arg-type]
        set_repository=FakeSetRepository(),  # type: ignore[arg-type]
    )
    with pytest.raises(SetNotFoundError):
        await use_case.similar_tracks("missing")
    with pytest.raises(SetNotFoundError):
        await use_case.similar_sets("missing")


async def test_similar_sets_excludes_the_reference_itself() -> None:
    reference = _set("set-a", embedding=_vector(0.0))
    other = _set("set-b", embedding=_vector(0.3))
    set_repository = FakeSetRepository(
        sets={"set-a": reference, "set-b": other},
        similar=(
            SetMatch(dj_set=reference, similarity_score=1.0),
            SetMatch(dj_set=other, similarity_score=0.88),
        ),
    )
    use_case = FindSimilarForSet(
        track_repository=FakeTrackRepository(),  # type: ignore[arg-type]
        set_repository=set_repository,  # type: ignore[arg-type]
    )

    matches = await use_case.similar_sets("set-a")

    assert [match.dj_set.id for match in matches] == ["set-b"]
    assert matches[0].similarity_percent == 88.0


async def test_similar_sets_requires_an_embedding() -> None:
    set_repository = FakeSetRepository(sets={"set-a": _set("set-a")})
    use_case = FindSimilarForSet(
        track_repository=FakeTrackRepository(),  # type: ignore[arg-type]
        set_repository=set_repository,  # type: ignore[arg-type]
    )
    with pytest.raises(SetNotEmbeddedError):
        await use_case.similar_sets("set-a")


async def test_invalid_limits_are_rejected() -> None:
    set_repository = FakeSetRepository(
        sets={"set-a": _set("set-a", embedding=_vector(0.0))}
    )
    use_case = FindSimilarForSet(
        track_repository=FakeTrackRepository(),  # type: ignore[arg-type]
        set_repository=set_repository,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="limit"):
        await use_case.similar_tracks("set-a", limit=0)
    with pytest.raises(ValueError, match="limit"):
        await use_case.similar_sets("set-a", limit=0)
