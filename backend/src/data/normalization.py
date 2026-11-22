"""Text normalization used for catalog and seed deduplication."""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE = re.compile(r"\s+", flags=re.UNICODE)


def normalize_text(value: str) -> str:
    """Return a case-folded, accent-stripped, punctuation-free key.

    The original display string is always kept in SQLite; this key is only used
    for equality checks and UNIQUE constraints.
    """
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


def normalize_artist_title(artist: str, title: str) -> str:
    """Return the canonical deduplication key for a track."""
    return f"{normalize_text(artist)}|{normalize_text(title)}"


def normalize_seed_name(name: str) -> str:
    """Return the canonical deduplication key for an artist seed."""
    return normalize_text(name)
