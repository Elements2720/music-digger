from __future__ import annotations

import pytest

from domain.entities.search import SearchFilter
from domain.entities.track import Track
from domain.genres import (
    ELECTRONIC_ALLOWED_GENRE_TOKENS,
    NON_ELECTRONIC_BLOCKED_GENRE_TOKENS,
    TECHNO_SUBGENRE_PRESETS,
    track_matches_genre_guard,
    track_matches_year,
)


def test_genre_presets_and_tokens_defined() -> None:
    assert "Techno" in TECHNO_SUBGENRE_PRESETS
    assert "Melodic Techno" in TECHNO_SUBGENRE_PRESETS
    assert "techno" in ELECTRONIC_ALLOWED_GENRE_TOKENS
    assert "pop" in NON_ELECTRONIC_BLOCKED_GENRE_TOKENS
    assert "rock" in NON_ELECTRONIC_BLOCKED_GENRE_TOKENS


def test_track_matches_genre_guard_allowed_list() -> None:
    assert track_matches_genre_guard(
        "Peak Time Techno", allowed_genres=("Techno", "House")
    )
    assert track_matches_genre_guard("Deep House", allowed_genres=("Techno", "House"))
    assert not track_matches_genre_guard("Pop", allowed_genres=("Techno", "House"))
    assert not track_matches_genre_guard(None, allowed_genres=("Techno", "House"))
    assert not track_matches_genre_guard("", allowed_genres=("Techno", "House"))


def test_track_matches_genre_guard_electronic_only() -> None:
    assert track_matches_genre_guard("Techno", electronic_only=True)
    assert track_matches_genre_guard("Tech House", electronic_only=True)
    assert track_matches_genre_guard("Melodic Trance", electronic_only=True)
    assert not track_matches_genre_guard("Pop / Rock", electronic_only=True)
    assert not track_matches_genre_guard("Hip-Hop / Rap", electronic_only=True)
    # None/blank preserves local rips
    assert track_matches_genre_guard(None, electronic_only=True)
    assert track_matches_genre_guard("", electronic_only=True)


def test_track_matches_year() -> None:
    assert track_matches_year(2021, min_year=2018, max_year=2023)
    assert not track_matches_year(2015, min_year=2018)
    assert not track_matches_year(2025, max_year=2023)
    assert track_matches_year(None, min_year=2018, reject_none_on_filter=False)
    assert not track_matches_year(None, min_year=2018, reject_none_on_filter=True)


def test_search_filter_year_and_genres() -> None:
    sf = SearchFilter(min_year=2018, max_year=2024, genres=("Techno", "House"))
    assert sf.min_year == 2018
    assert sf.max_year == 2024
    assert sf.genres == ("Techno", "House")

    t1 = Track(
        id="t1",
        title="Track 1",
        artist="Artist",
        release_year=2020,
        genre="Peak Time Techno",
    )
    t2 = Track(
        id="t2",
        title="Track 2",
        artist="Artist",
        release_year=2015,
        genre="Peak Time Techno",
    )
    t3 = Track(
        id="t3", title="Track 3", artist="Artist", release_year=2021, genre="Rock"
    )

    assert sf.matches(t1)
    assert not sf.matches(t2)  # too old
    assert not sf.matches(t3)  # wrong genre


def test_search_filter_rejects_inverted_year() -> None:
    with pytest.raises(
        ValueError, match="min_year must be less than or equal to max_year"
    ):
        SearchFilter(min_year=2025, max_year=2020)
