from __future__ import annotations

import dataclasses

import pytest

from domain.entities.dj_set import DJSet, Passage, TrackMatch
from domain.entities.track import Track
from domain.value_objects.audio_features import BPM, CamelotKey, TimeRange


def make_track(track_id: str = "t1", title: str = "Track") -> Track:
    return Track(id=track_id, title=title, artist="Artist")


def make_match(
    track_id: str = "t1", score: float = 0.9, exact: bool = False
) -> TrackMatch:
    return TrackMatch(
        track=make_track(track_id), similarity_score=score, is_exact_id=exact
    )


def test_track_match_valid_and_defaults() -> None:
    match = TrackMatch(track=make_track(), similarity_score=0.87)
    assert match.track.id == "t1"
    assert match.similarity_score == 0.87
    assert match.is_exact_id is False


@pytest.mark.parametrize("score", [-1.0, 0.0, 0.5, 1.0])
def test_track_match_accepts_score_boundaries(score: float) -> None:
    assert TrackMatch(make_track(), score).similarity_score == score


@pytest.mark.parametrize("score", [-1.01, 1.01, float("nan"), float("inf")])
def test_track_match_rejects_invalid_scores(score: float) -> None:
    with pytest.raises(ValueError):
        TrackMatch(make_track(), score)


def test_track_match_rejects_bad_types() -> None:
    with pytest.raises(TypeError, match="track must be a Track"):
        TrackMatch("not-a-track", 0.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="similarity_score"):
        TrackMatch(make_track(), "0.5")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="is_exact_id"):
        TrackMatch(make_track(), 0.5, is_exact_id=1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("score", "expected_percent"),
    [
        (1.0, 100.0),
        (0.876, 87.6),
        (0.0, 0.0),
        (-0.5, 0.0),  # negative cosine similarity clamps to 0%
    ],
)
def test_track_match_similarity_percent(score: float, expected_percent: float) -> None:
    assert TrackMatch(make_track(), score).similarity_percent == expected_percent


def test_similarity_percent_keeps_one_decimal_place() -> None:
    """0.995 and 0.981 must NOT both collapse to 100 (regression)."""
    near_perfect = TrackMatch(make_track(), 0.995)
    high = TrackMatch(make_track(), 0.981)

    assert near_perfect.similarity_percent == 99.5
    assert high.similarity_percent == 98.1
    assert near_perfect.similarity_percent != high.similarity_percent


def test_passage_defaults_and_feature_coercion() -> None:
    passage = Passage(
        time_range=TimeRange(0.0, 30.0),
        bpm=128.0,
        key="8a",
    )
    assert passage.bpm == BPM(128.0)
    assert passage.key == CamelotKey("8A")
    assert passage.exact_id_match is False
    assert passage.closest_matches == ()
    assert passage.best_match is None
    assert passage.exact_match is None


def test_passage_sorts_matches_by_descending_similarity() -> None:
    low = make_match("low", 0.4)
    high = make_match("high", 0.95)
    exact = make_match("exact", 0.8, exact=True)
    passage = Passage(
        time_range=TimeRange(0.0, 30.0),
        closest_matches=(low, high, exact),
    )
    assert [match.track.id for match in passage.closest_matches] == [
        "high",
        "exact",
        "low",
    ]
    assert passage.best_match is high
    assert passage.exact_match is exact


def test_passage_accepts_list_of_matches_and_freezes_it() -> None:
    matches = [make_match("a", 0.5), make_match("b", 0.7)]
    passage = Passage(time_range=TimeRange(0.0, 30.0), closest_matches=matches)  # type: ignore[arg-type]
    assert isinstance(passage.closest_matches, tuple)
    assert [match.track.id for match in passage.closest_matches] == ["b", "a"]


def test_passage_rejects_bad_types() -> None:
    with pytest.raises(TypeError, match="time_range"):
        Passage(time_range=(0.0, 30.0))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="BPM|bpm"):
        Passage(time_range=TimeRange(0.0, 30.0), bpm="128")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Camelot|key"):
        Passage(time_range=TimeRange(0.0, 30.0), key=8)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact_id_match"):
        Passage(time_range=TimeRange(0.0, 30.0), exact_id_match=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="closest_matches"):
        Passage(time_range=TimeRange(0.0, 30.0), closest_matches=("nope",))  # type: ignore[arg-type]


def test_dj_set_valid_empty_set() -> None:
    dj_set = DJSet(
        id="set-1", title="Closing Set", source_url="https://example.test/set"
    )
    assert dj_set.id == "set-1"
    assert dj_set.set_id == "set-1"
    assert dj_set.title == "Closing Set"
    assert dj_set.source_url == "https://example.test/set"
    assert dj_set.passages == ()
    assert dj_set.passage_count == 0
    assert dj_set.duration_seconds is None


def test_dj_set_freezes_passages_and_validates_duration() -> None:
    first = Passage(TimeRange(0.0, 30.0))
    second = Passage(TimeRange(30.0, 60.0))
    dj_set = DJSet(
        id="set-1",
        title="Set",
        passages=[first, second],  # type: ignore[arg-type]
        duration_seconds=60,
    )
    assert isinstance(dj_set.passages, tuple)
    assert dj_set.passage_count == 2
    assert dj_set.duration_seconds == 60.0


def test_dj_set_rejects_passages_past_duration() -> None:
    with pytest.raises(ValueError, match="after the DJ set duration"):
        DJSet(
            id="set-1",
            title="Set",
            passages=(Passage(TimeRange(0.0, 61.0)),),
            duration_seconds=60,
        )


def test_dj_set_rejects_bad_values() -> None:
    with pytest.raises(ValueError, match="id"):
        DJSet(id=" ", title="Set")
    with pytest.raises(ValueError, match="title"):
        DJSet(id="set-1", title=" ")
    with pytest.raises(ValueError, match="source_url"):
        DJSet(id="set-1", title="Set", source_url=" ")
    with pytest.raises(ValueError, match="duration_seconds"):
        DJSet(id="set-1", title="Set", duration_seconds=0)
    with pytest.raises(TypeError, match="passages"):
        DJSet(id="set-1", title="Set", passages=("nope",))  # type: ignore[arg-type]


def test_dj_set_passage_at_and_ordering() -> None:
    later = Passage(TimeRange(60.0, 90.0))
    earlier = Passage(TimeRange(0.0, 30.0))
    middle = Passage(TimeRange(30.0, 60.0))
    dj_set = DJSet(id="set-1", title="Set", passages=(later, earlier, middle))

    assert dj_set.passage_at(0.0) is earlier
    assert dj_set.passage_at(45.0) is middle
    assert dj_set.passage_at(90.0) is None
    assert [
        passage.time_range.start_seconds for passage in dj_set.ordered_passages()
    ] == [
        0.0,
        30.0,
        60.0,
    ]


def test_dj_set_passage_at_rejects_invalid_points() -> None:
    dj_set = DJSet(id="set-1", title="Set")
    with pytest.raises(ValueError, match="negative"):
        dj_set.passage_at(-1.0)
    with pytest.raises(TypeError):
        dj_set.passage_at("30")  # type: ignore[arg-type]


def test_dj_set_with_passage_returns_a_new_entity() -> None:
    dj_set = DJSet(id="set-1", title="Set")
    passage = Passage(TimeRange(0.0, 30.0))
    updated = dj_set.with_passage(passage)
    assert updated is not dj_set
    assert updated.passages == (passage,)
    assert dj_set.passages == ()


def test_dj_set_with_passage_rejects_non_passage() -> None:
    with pytest.raises(TypeError, match="passage must be a Passage"):
        DJSet(id="set-1", title="Set").with_passage("nope")  # type: ignore[arg-type]


def test_dj_set_is_immutable() -> None:
    dj_set = DJSet(id="set-1", title="Set")
    with pytest.raises(dataclasses.FrozenInstanceError):
        dj_set.title = "Other"  # type: ignore[misc]
