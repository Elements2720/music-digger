from __future__ import annotations

import dataclasses

import pytest

from domain.value_objects.audio_features import CamelotKey

ALL_KEYS = [f"{number}{letter}" for number in range(1, 13) for letter in ("A", "B")]


@pytest.mark.parametrize("notation", ALL_KEYS)
def test_camelot_key_accepts_every_valid_notation(notation: str) -> None:
    key = CamelotKey(notation)
    assert key.notation == notation
    assert key.value == notation
    assert key.key == notation
    assert str(key) == notation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("8a", "8A"), (" 8A ", "8A"), ("12b", "12B"), ("1A", "1A")],
)
def test_camelot_key_normalizes_whitespace_and_case(raw: str, expected: str) -> None:
    assert CamelotKey(raw).notation == expected


@pytest.mark.parametrize(
    "notation",
    ["", "0A", "13A", "8C", "A8", "8", "8AA", "08A", "1a1", "  ", "8 A", "8-A"],
)
def test_camelot_key_rejects_invalid_notation(notation: str) -> None:
    with pytest.raises(ValueError, match="Camelot key"):
        CamelotKey(notation)


@pytest.mark.parametrize("notation", [8, None, True, ["8A"]])
def test_camelot_key_rejects_non_strings(notation: object) -> None:
    with pytest.raises(TypeError, match="must be a string"):
        CamelotKey(notation)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("notation", "number", "letter"),
    [("1A", 1, "A"), ("8B", 8, "B"), ("12A", 12, "A")],
)
def test_camelot_key_parts(notation: str, number: int, letter: str) -> None:
    key = CamelotKey(notation)
    assert key.number == number
    assert key.letter == letter


def test_camelot_key_is_immutable() -> None:
    key = CamelotKey("8A")
    with pytest.raises(dataclasses.FrozenInstanceError):
        key.notation = "9A"  # type: ignore[misc]


def test_camelot_key_equality_and_hashability() -> None:
    assert CamelotKey("8a") == CamelotKey("8A")
    assert CamelotKey("8A") != CamelotKey("8B")
    assert len({CamelotKey("8A"), CamelotKey("8a"), CamelotKey("9A")}) == 2


def test_same_key_is_harmonically_compatible() -> None:
    key = CamelotKey("8A")
    assert key.is_harmonic_compatible(CamelotKey("8A"))
    assert key.is_harmonic_compatible(key)


@pytest.mark.parametrize("number", range(1, 13))
def test_relative_major_minor_is_harmonically_compatible(number: int) -> None:
    minor = CamelotKey(f"{number}A")
    major = CamelotKey(f"{number}B")
    assert minor.is_harmonic_compatible(major)
    assert major.is_harmonic_compatible(minor)


@pytest.mark.parametrize("number", range(1, 13))
@pytest.mark.parametrize("letter", ["A", "B"])
def test_neighbouring_keys_are_harmonically_compatible(
    number: int, letter: str
) -> None:
    key = CamelotKey(f"{number}{letter}")
    previous_number = 12 if number == 1 else number - 1
    next_number = 1 if number == 12 else number + 1
    assert key.is_harmonic_compatible(CamelotKey(f"{previous_number}{letter}"))
    assert key.is_harmonic_compatible(CamelotKey(f"{next_number}{letter}"))


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("12A", "1A"),
        ("1A", "12A"),
        ("12B", "1B"),
        ("1B", "12B"),
        ("8A", "7A"),
        ("8A", "9A"),
        ("8B", "7B"),
        ("8B", "9B"),
    ],
)
def test_wraparound_and_neighbour_pairs(left: str, right: str) -> None:
    assert CamelotKey(left).is_harmonic_compatible(CamelotKey(right))


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("8A", "10A"),
        ("8A", "6A"),
        ("8A", "3A"),
        ("1A", "3A"),
        ("1B", "11B"),
        ("8A", "9B"),
        ("8A", "7B"),
        ("12A", "2B"),
    ],
)
def test_incompatible_pairs(left: str, right: str) -> None:
    assert not CamelotKey(left).is_harmonic_compatible(CamelotKey(right))


def test_harmonic_compatibility_rejects_non_keys() -> None:
    with pytest.raises(TypeError, match="other must be a CamelotKey"):
        CamelotKey("8A").is_harmonic_compatible("9A")  # type: ignore[arg-type]
