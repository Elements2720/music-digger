"""Tests for the Phase 3 DigSimilarTracks use case against interface doubles."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest

from domain.entities.dj_set import TrackMatch
from domain.entities.search import SearchFilter
from domain.entities.track import Track
from domain.interfaces.repositories import ITrackRepository
from domain.use_cases import (
    DigSimilarTracks,
    TrackNotEmbeddedError,
    TrackNotFoundError,
)
from domain.value_objects.audio_features import EmbeddingVector

# A fixed 2-dimensional embedding set: vectors spread around the unit circle.
_VECTORS: dict[str, tuple[float, float]] = {
    "ref": (1.0, 0.0),
    "close": (0.99, 0.141),  # ~8 degrees away
    "mid": (0.707, 0.707),  # 45 degrees away
    "far": (0.0, 1.0),  # 90 degrees away
    "opposite": (-1.0, 0.0),
}


def vector(track_id: str) -> EmbeddingVector:
    x, y = _VECTORS[track_id]
    return EmbeddingVector(values=(x, y), dimension=2)


def make_track(track_id: str, *, bpm: float = 126.0, key: str = "8A") -> Track:
    return Track(
        id=track_id,
        title=f"Title {track_id}",
        artist=f"Artist {track_id}",
        bpm=bpm,
        key=key,
        genre="Melodic Techno",
        embedding=vector(track_id),
    )


class FakeTrackRepository(ITrackRepository):
    """Vector-aware in-memory store: cosine similarity over 2-D vectors."""

    def __init__(self, tracks: Sequence[Track], *, heard: Sequence[str] = ()) -> None:
        self._tracks: dict[str, Track] = {track.id: track for track in tracks}
        self._heard = frozenset(heard)
        self.similar_calls: list[tuple[str, SearchFilter]] = []

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        for track in tracks:
            self._tracks[track.id] = track
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        return self._tracks.get(track_id)

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        return None

    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        return [self._tracks[key] for key in track_ids if key in self._tracks]

    async def find_similar(
        self, embedding: EmbeddingVector, search_filter: SearchFilter
    ) -> Sequence[TrackMatch]:
        self.similar_calls.append((repr(embedding.values), search_filter))
        scored = [
            (track, embedding.cosine_similarity(track.embedding))
            for track in self._tracks.values()
            if track.embedding is not None
        ]
        if search_filter.bpm_min is not None:
            scored = [
                (t, s)
                for t, s in scored
                if t.bpm is not None and t.bpm.value >= search_filter.bpm_min
            ]
        if search_filter.bpm_max is not None:
            scored = [
                (t, s)
                for t, s in scored
                if t.bpm is not None and t.bpm.value <= search_filter.bpm_max
            ]
        if search_filter.camelot_keys:
            scored = [
                (t, s)
                for t, s in scored
                if t.key is not None and t.key in search_filter.camelot_keys
            ]
        if search_filter.exclude_heard:
            scored = [(t, s) for t, s in scored if t.id not in self._heard]
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

    async def mark_heard(self, track_id: str) -> None:
        self._heard |= {track_id}

    async def set_heard(self, track_id: str, heard: bool) -> None:
        if heard:
            self._heard |= {track_id}
        else:
            self._heard -= {track_id}

    async def search_tracks(self, query: str, limit: int = 30) -> Sequence[Track]:
        needle = query.strip().casefold()
        if not needle or limit <= 0:
            return ()
        hits = [
            track
            for track in self._tracks.values()
            if needle in track.title.casefold() or needle in track.artist.casefold()
        ]
        return hits[:limit]

    async def get_heard_ids(self) -> frozenset[str]:
        return self._heard

    async def count(self) -> int:
        return len(self._tracks)

    async def count_embedded(self) -> int:
        return sum(1 for t in self._tracks.values() if t.embedding is not None)

    async def list_unembedded(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def list_embedded(
        self, limit: int = 20, *, offset: int = 0
    ) -> Sequence[Track]:
        return ()

    async def mark_index_failed(self, track_id: str) -> None:
        return None

    async def list_reindexable(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def reset_embeddings(self) -> int:
        return 0


def make_use_case(tracks: Sequence[Track], **kwargs: Any) -> DigSimilarTracks:
    return DigSimilarTracks(track_repository=FakeTrackRepository(tracks, **kwargs))


async def test_returns_closest_matches_excluding_the_reference() -> None:
    tracks = [make_track(name) for name in _VECTORS]
    use_case = make_use_case(tracks)

    result = await use_case.execute("ref", SearchFilter(limit=10))

    assert result.reference.id == "ref"
    returned_ids = [match.track.id for match in result.matches]
    assert "ref" not in returned_ids
    # Sorted best-first: close, mid, far, then the opposite vector.
    assert returned_ids == ["close", "mid", "far", "opposite"]
    best = result.matches[0]
    assert 0 <= best.similarity_percent <= 100
    assert best.similarity_percent == pytest.approx(
        vector("ref").cosine_similarity(vector("close")) * 100, abs=1
    )


async def test_limit_is_respected_even_after_dropping_reference() -> None:
    tracks = [make_track(name) for name in _VECTORS]
    use_case = make_use_case(tracks)

    result = await use_case.execute("ref", SearchFilter(limit=2))

    assert len(result.matches) == 2
    assert [match.track.id for match in result.matches] == ["close", "mid"]


async def test_bpm_tolerance_narrows_the_filter() -> None:
    tracks = [
        make_track("ref", bpm=126.0),
        make_track("close", bpm=127.0),
        make_track("mid", bpm=132.0),
    ]
    repository = FakeTrackRepository(tracks)
    use_case = DigSimilarTracks(track_repository=repository)

    result = await use_case.execute("ref", SearchFilter(limit=10), bpm_tolerance=4.0)

    assert [match.track.id for match in result.matches] == ["close"]
    # The effective filter received the narrowed BPM window.
    _, used_filter = repository.similar_calls[-1]
    assert used_filter.bpm_min == pytest.approx(122.0)
    assert used_filter.bpm_max == pytest.approx(130.0)


async def test_bpm_tolerance_intersects_explicit_bounds() -> None:
    tracks = [
        make_track("ref", bpm=126.0),
        make_track("close", bpm=127.0),
    ]
    repository = FakeTrackRepository(tracks)
    use_case = DigSimilarTracks(track_repository=repository)

    await use_case.execute(
        "ref", SearchFilter(limit=10, bpm_min=125.0, bpm_max=126.5), bpm_tolerance=4.0
    )

    _, used_filter = repository.similar_calls[-1]
    assert used_filter.bpm_min == pytest.approx(125.0)
    assert used_filter.bpm_max == pytest.approx(126.5)


async def test_harmonic_expands_to_compatible_camelot_keys() -> None:
    tracks = [
        make_track("ref", key="8A"),
        make_track("close", key="8A"),
        make_track("mid", key="7A"),  # clockwise neighbour
        make_track("far", key="8B"),  # relative major
        make_track("opposite", key="2B"),  # unrelated
    ]
    repository = FakeTrackRepository(tracks)
    use_case = DigSimilarTracks(track_repository=repository)

    result = await use_case.execute("ref", SearchFilter(limit=10), harmonic=True)

    _, used_filter = repository.similar_calls[-1]
    used_notations = {key.notation for key in used_filter.camelot_keys}
    assert used_notations == {"7A", "8A", "9A", "8B"}
    assert [match.track.id for match in result.matches] == [
        "close",
        "mid",
        "far",
    ]


async def test_harmonic_wraps_around_the_wheel() -> None:
    tracks = [make_track("ref", key="1A"), make_track("far", key="12A")]
    use_case = make_use_case(tracks)

    result = await use_case.execute("ref", SearchFilter(limit=10), harmonic=True)

    assert [match.track.id for match in result.matches] == ["far"]


async def test_harmonic_without_reference_key_ignores_key_filter() -> None:
    reference = replace(make_track("ref"), key=None)
    tracks = [reference, make_track("close", key="8A"), make_track("mid", key="2B")]
    use_case = make_use_case(tracks)

    result = await use_case.execute("ref", SearchFilter(limit=10), harmonic=True)

    assert {match.track.id for match in result.matches} == {"close", "mid"}


async def test_exclude_heard_removes_played_tracks() -> None:
    tracks = [make_track(name) for name in _VECTORS]
    repository = FakeTrackRepository(tracks, heard=["close", "far"])
    use_case = DigSimilarTracks(track_repository=repository)

    result = await use_case.execute("ref", SearchFilter(limit=10, exclude_heard=True))

    assert [match.track.id for match in result.matches] == ["mid", "opposite"]


async def test_genre_filter_is_applied() -> None:
    tracks = [
        make_track("ref"),
        make_track("close"),
        replace(make_track("mid"), genre="Techno"),
    ]
    use_case = make_use_case(tracks)

    result = await use_case.execute(
        "ref", SearchFilter(limit=10, genre_filter="melodic techno")
    )

    assert [match.track.id for match in result.matches] == ["close"]


async def test_unknown_track_raises_track_not_found() -> None:
    use_case = make_use_case([make_track("ref")])

    with pytest.raises(TrackNotFoundError):
        await use_case.execute("missing", SearchFilter())


async def test_unembedded_reference_raises_track_not_embedded() -> None:
    bare = replace(make_track("ref"), embedding=None)
    use_case = make_use_case([bare, make_track("close")])

    with pytest.raises(TrackNotEmbeddedError):
        await use_case.execute("ref", SearchFilter())


async def test_matches_with_no_filter_and_no_candidates() -> None:
    use_case = make_use_case([make_track("ref")])

    result = await use_case.execute("ref")

    assert result.reference.id == "ref"
    assert result.matches == ()


async def test_negative_bpm_tolerance_is_rejected() -> None:
    tracks = [make_track("ref")]
    use_case = make_use_case(tracks)

    with pytest.raises(ValueError):
        await use_case.execute("ref", SearchFilter(), bpm_tolerance=-1.0)


async def test_energy_boost_widens_the_harmonic_allow_list() -> None:
    tracks = [
        make_track("ref", key="8A"),
        make_track("close", key="8A"),
        make_track("mid", key="6A"),  # two fifths up: strict rejects it
        make_track("far", key="9B"),  # a fifth across the relative major
        make_track("opposite", key="2B"),  # unrelated
    ]
    repository = FakeTrackRepository(tracks)
    use_case = DigSimilarTracks(track_repository=repository)

    result = await use_case.execute(
        "ref",
        SearchFilter(limit=10),
        harmonic=True,
        harmonic_mode="energy_boost",
    )

    _, used_filter = repository.similar_calls[-1]
    assert {key.notation for key in used_filter.camelot_keys} == {
        "6A",
        "7A",
        "8A",
        "9A",
        "10A",
        "7B",
        "8B",
        "9B",
    }
    assert [match.track.id for match in result.matches] == ["close", "mid", "far"]


async def test_strict_mode_keeps_the_narrow_harmonic_set() -> None:
    repository = FakeTrackRepository([make_track("ref", key="8A")])
    use_case = DigSimilarTracks(track_repository=repository)

    await use_case.execute(
        "ref", SearchFilter(limit=10), harmonic=True, harmonic_mode="strict"
    )

    _, used_filter = repository.similar_calls[-1]
    assert {key.notation for key in used_filter.camelot_keys} == {
        "7A",
        "8A",
        "9A",
        "8B",
    }


async def test_unknown_harmonic_mode_is_rejected() -> None:
    use_case = make_use_case([make_track("ref")])

    with pytest.raises(ValueError):
        await use_case.execute("ref", SearchFilter(), harmonic_mode="smooth")


async def test_max_per_artist_caps_matches_and_still_fills_the_limit() -> None:
    tracks = [
        make_track("ref"),
        replace(make_track("close"), artist="Solomun"),
        replace(make_track("mid"), artist="Solomun"),
        replace(make_track("far"), artist="ARTBAT"),
        replace(make_track("opposite"), artist="Tale Of Us"),
    ]
    repository = FakeTrackRepository(tracks)
    use_case = DigSimilarTracks(track_repository=repository)

    result = await use_case.execute("ref", SearchFilter(limit=10), max_per_artist=1)

    assert [match.track.id for match in result.matches] == [
        "close",
        "far",
        "opposite",
    ]
    # A capped query asks for a deeper pool than the plain over-fetch of one.
    _, used_filter = repository.similar_calls[-1]
    assert used_filter.limit > SearchFilter(limit=10).limit + 1


async def test_max_per_artist_still_respects_the_limit() -> None:
    tracks = [make_track("ref")] + [
        replace(make_track("mid"), id=f"t{index}", artist=f"Artist {index}")
        for index in range(6)
    ]
    use_case = make_use_case(tracks)

    result = await use_case.execute("ref", SearchFilter(limit=3), max_per_artist=2)

    assert len(result.matches) == 3


async def test_negative_max_per_artist_is_rejected() -> None:
    use_case = make_use_case([make_track("ref")])

    with pytest.raises(ValueError):
        await use_case.execute("ref", SearchFilter(), max_per_artist=-1)
