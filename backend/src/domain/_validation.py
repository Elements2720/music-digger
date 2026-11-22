"""Dependency-free validation helpers shared by domain objects.

This module is part of the pure domain layer: standard library only.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")

_NON_WORD = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE = re.compile(r"\s+", flags=re.UNICODE)


def normalize_key(value: str) -> str:
    """Return a case-folded, accent-stripped, punctuation-free key."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    folded = without_accents.casefold()
    replaced = _NON_WORD.sub(" ", folded)
    collapsed = _WHITESPACE.sub(" ", replaced).strip()
    return collapsed or folded.strip()


def normalize_artist_key(artist: str) -> str:
    """Return the canonical deduplication key for an artist."""
    return normalize_key(artist)


def normalize_track_key(artist: str, title: str) -> str:
    """Return the canonical deduplication key for a track (artist|title)."""
    return f"{normalize_key(artist)}|{normalize_key(title)}"


def require_str(value: object, field: str, *, allow_empty: bool = False) -> str:
    """Return a stripped string, rejecting non-strings and (by default) empties."""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def optional_str(value: object | None, field: str) -> str | None:
    """Validate an optional string, normalizing it when present."""
    if value is None:
        return None
    return require_str(value, field)


def require_float(value: object, field: str) -> float:
    """Return a finite float, rejecting booleans and non-numeric values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a real number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def require_int(value: object, field: str) -> int:
    """Return an int, rejecting booleans (which are ints at runtime)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    return value


def require_bool(value: object, field: str) -> bool:
    """Return a bool, rejecting truthy non-booleans."""
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a boolean")
    return value


def freeze_tuple(
    value: Iterable[T],
    field: str,
    expected_type: type | tuple[type, ...] | None = None,
) -> tuple[T, ...]:
    """Freeze an iterable into a tuple and optionally validate every item's type."""
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{field} must be an iterable of items, not a string or bytes")
    try:
        items = tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field} must be an iterable") from exc
    if expected_type is not None:
        for item in items:
            if not isinstance(item, expected_type):
                raise TypeError(
                    f"{field} must contain only {expected_type!r} instances"
                )
    return items
