from __future__ import annotations

import dataclasses

import pytest

from domain.entities.search import SearchFilter
from domain.entities.track import Track
from domain.value_objects.audio_features import BPM, CamelotKey


def make_track(
    *,
    track_id: str = "t1",
    bpm: float | None = 128.0,
    key: str | None = "8A",
    genre: str | None = "Techno",
) -> Track:
    return Track(
        id=track_id,
        title="Track",
        artist="Artist",
        bpm=bpm,
        key=key,
        genre=genre,
    )


def test_search_filter_defaults() -> None:
    search_filter = SearchFilter()
    assert search_filter.bpm_min is None
    assert search_filter.bpm_max is None
    assert search_filter.camelot_keys == ()
    assert search_filter.exclude_heard is False
    assert search_filter.genre_filter is None
    assert search_filter.limit == 50


def test_search_filter_normalizes_bpm_bounds_and_keys() -> None:
    search_filter = SearchFilter(
        bpm_min=BPM(120.0),
        bpm_max=130,
        camelot_keys=("8a", "8A", CamelotKey("9A")),
    )
    assert search_filter.bpm_min == 120.0
    assert search_filter.bpm_max == 130.0
    assert search_filter.camelot_keys == (CamelotKey("8A"), CamelotKey("9A"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bpm_min", 39.99),
        ("bpm_min", 220.01),
        ("bpm_max", 39.99),
        ("bpm_max", 220.01),
    ],
)
def test_search_filter_rejects_out_of_range_bpm(field: str, value: float) -> None:
    with pytest.raises(ValueError, match=field):
        SearchFilter(**{field: value})


def test_search_filter_rejects_inverted_bpm_range() -> None:
    with pytest.raises(ValueError, match="bpm_min"):
        SearchFilter(bpm_min=140, bpm_max=120)


@pytest.mark.parametrize("field", ["bpm_min", "bpm_max"])
def test_search_filter_rejects_bad_bpm_types(field: str) -> None:
    with pytest.raises(TypeError):
        SearchFilter(**{field: "120"})


def test_search_filter_rejects_bad_camelot_keys() -> None:
    with pytest.raises(TypeError, match="camelot_keys"):
        SearchFilter(camelot_keys="8A")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Camelot key"):
        SearchFilter(camelot_keys=("13A",))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SearchFilter(camelot_keys=(8,))  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [1, 50, 500])
def test_search_filter_accepts_valid_limits(limit: int) -> None:
    assert SearchFilter(limit=limit).limit == limit


@pytest.mark.parametrize("limit", [0, -1, 501])
def test_search_filter_rejects_out_of_range_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        SearchFilter(limit=limit)


@pytest.mark.parametrize("limit", [True, 50.0, "50", None])
def test_search_filter_rejects_non_integer_limits(limit: object) -> None:
    with pytest.raises(TypeError, match="limit"):
        SearchFilter(limit=limit)  # type: ignore[arg-type]


def test_search_filter_normalizes_genre_and_validates_boolean() -> None:
    assert SearchFilter(genre_filter="  Techno  ").genre_filter == "Techno"
    with pytest.raises(ValueError, match="genre_filter"):
        SearchFilter(genre_filter=" ")
    with pytest.raises(TypeError, match="exclude_heard"):
        SearchFilter(exclude_heard=1)  # type: ignore[arg-type]


def test_search_filter_matches_bpm_range() -> None:
    search_filter = SearchFilter(bpm_min=120, bpm_max=130)
    assert search_filter.matches(make_track(bpm=120.0))
    assert search_filter.matches(make_track(bpm=130.0))
    assert not search_filter.matches(make_track(bpm=119.99))
    assert not search_filter.matches(make_track(bpm=130.01))
    assert not search_filter.matches(make_track(bpm=None))


def test_search_filter_matches_camelot_allow_list() -> None:
    search_filter = SearchFilter(camelot_keys=("8A", "9A"))
    assert search_filter.matches(make_track(key="8A"))
    assert search_filter.matches(make_track(key="9A"))
    assert not search_filter.matches(make_track(key="10A"))
    assert not search_filter.matches(make_track(key=None))


def test_search_filter_matches_exclude_heard() -> None:
    assert not SearchFilter(exclude_heard=True).matches(make_track(), heard_ids={"t1"})
    assert SearchFilter(exclude_heard=True).matches(make_track(), heard_ids={"t2"})
    assert SearchFilter(exclude_heard=False).matches(make_track(), heard_ids={"t1"})


def test_search_filter_matches_genre_case_insensitively() -> None:
    search_filter = SearchFilter(genre_filter="techno")
    assert search_filter.matches(make_track(genre="Techno"))
    assert search_filter.matches(make_track(genre="TECHNO"))
    assert not search_filter.matches(make_track(genre="House"))
    assert not search_filter.matches(make_track(genre=None))


def test_search_filter_matches_combines_constraints() -> None:
    search_filter = SearchFilter(
        bpm_min=120,
        bpm_max=130,
        camelot_keys=("8A",),
        exclude_heard=True,
        genre_filter="Techno",
    )
    assert search_filter.matches(make_track(), heard_ids={"other"})
    assert not search_filter.matches(make_track(), heard_ids={"t1"})
    assert not search_filter.matches(make_track(bpm=140.0), heard_ids={"other"})
    assert not search_filter.matches(make_track(key="9A"), heard_ids={"other"})
    assert not search_filter.matches(make_track(genre="House"), heard_ids={"other"})


def test_search_filter_matches_rejects_non_track() -> None:
    with pytest.raises(TypeError, match="track must be a Track"):
        SearchFilter().matches("not-a-track")  # type: ignore[arg-type]


def test_search_filter_is_immutable() -> None:
    search_filter = SearchFilter()
    with pytest.raises(dataclasses.FrozenInstanceError):
        search_filter.limit = 10  # type: ignore[misc]


def test_search_filter_has_local_and_source_filter() -> None:
    local_only = SearchFilter(has_local=True)
    remote_only = SearchFilter(has_local=False)
    itunes_only = SearchFilter(source_filter=" iTunes ")
    assert itunes_only.source_filter == "iTunes"
    local_track = Track(
        id="t-local",
        title="Local",
        artist="Artist",
        source="itunes",
        local_path="/music/track.m4a",
    )
    remote_track = Track(
        id="t-remote",
        title="Remote",
        artist="Artist",
        source="deezer",
        local_path=None,
    )
    assert local_only.matches(local_track)
    assert not local_only.matches(remote_track)
    assert not remote_only.matches(local_track)
    assert remote_only.matches(remote_track)
    assert itunes_only.matches(local_track)
    assert not itunes_only.matches(remote_track)
    with pytest.raises(TypeError):
        SearchFilter(has_local="yes")  # type: ignore[arg-type]
