"""Tests for collaborator and remixer parsing."""

from __future__ import annotations

import pytest

from data.datasources.remote.artist_parser import parse_collaborators


@pytest.mark.parametrize(
    ("artist", "title", "expected"),
    [
        ("Solomun", "Home", ("Solomun",)),
        ("Tale Of Us & Mind Against", "Monument", ("Tale Of Us", "Mind Against")),
        ("Miss Monique, Argy", "Neon Nights", ("Miss Monique", "Argy")),
        ("Argy feat. omnya", "Aria", ("Argy", "omnya")),
        ("Argy ft. omnya", "Aria", ("Argy", "omnya")),
        ("Solomun x Keinemusik", "Pair", ("Solomun", "Keinemusik")),
        ("Vintage Culture", "Neon Brown (Mau P Remix)", ("Mau P", "Vintage Culture")),
        ("Anyma", "Explore (Chris Lake Remix)", ("Chris Lake", "Anyma")),
        ("Anyma", "Explore [Argy Remix]", ("Argy", "Anyma")),
        ("Boris Brejcha", "Gravity - Space 92 Remix", ("Space 92", "Boris Brejcha")),
        (
            "Nina Kraviz",
            "Skyscrapers (feat. John Summit)",
            ("John Summit", "Nina Kraviz"),
        ),
        ("Rüfüs Du Sol", "Sundream", ("Rüfüs Du Sol",)),
    ],
)
def test_parse_collaborators_extracts_expected_names(
    artist: str,
    title: str,
    expected: tuple[str, ...],
) -> None:
    assert parse_collaborators(artist, title) == expected


def test_parse_collaborators_deduplicates_case_insensitively() -> None:
    names = parse_collaborators("Solomun & solomun", "Home (Solomun Remix)")
    assert names == ("Solomun",)


def test_parse_collaborators_rejects_wrong_types() -> None:
    with pytest.raises(TypeError, match="artist_name"):
        parse_collaborators(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="track_title"):
        parse_collaborators("A", 1)  # type: ignore[arg-type]
