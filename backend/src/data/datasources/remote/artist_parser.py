"""Extract collaborator, featured, and remixer names from track metadata."""

from __future__ import annotations

import re

_FEAT = re.compile(r"\b(?:featuring|feat|ft|with)\b\.?", flags=re.IGNORECASE)
_SEPARATOR = re.compile(
    r"\s*(?:,|&|;|×|\+|\||\s+x\s+)\s*",
    flags=re.IGNORECASE,
)
_REMIX_BRACKET = re.compile(
    r"[\(\[]\s*(?P<name>[^\)\]]+?)\s+"
    r"(?:remix|edit|bootleg|rework|vip|mix)\s*[\)\]]",
    flags=re.IGNORECASE,
)
_REMIX_DASH = re.compile(
    r"\s[-–—]\s*(?P<name>[^-–—]+?)\s+"
    r"(?:remix|edit|bootleg|rework|vip|mix)\b",
    flags=re.IGNORECASE,
)
_TRAILING_ROLE = re.compile(
    r"\s+(?:remix|edit|bootleg|rework|vip|mix|version)$",
    flags=re.IGNORECASE,
)
_GENERIC_NAMES = frozenset(
    {
        "edit",
        "extended mix",
        "original mix",
        "radio edit",
        "remix",
        "rework",
        "unknown",
        "various artists",
        "vip",
    }
)


def parse_collaborators(artist_name: str, track_title: str = "") -> tuple[str, ...]:
    """Return distinct collaborator/remixer names in first-seen order.

    The parser intentionally handles the messy strings found in catalog data:
    ``A & B``, ``A, B``, ``A feat. B``, ``A ft. B``, ``A x B``, and
    ``Title (B Remix)``. Names found in the title (remixers, featured guests)
    come first, followed by the split artist field, in first-seen order.
    It does not try to resolve aliases.
    """
    if not isinstance(artist_name, str):
        raise TypeError("artist_name must be a string")
    if not isinstance(track_title, str):
        raise TypeError("track_title must be a string")

    candidates: list[str] = []
    for match in _REMIX_BRACKET.finditer(track_title):
        candidates.append(match.group("name"))
    for match in _REMIX_DASH.finditer(track_title):
        candidates.append(match.group("name"))

    title_without_remixes = _REMIX_BRACKET.sub(" ", track_title)
    if _FEAT.search(title_without_remixes):
        featured = _FEAT.split(title_without_remixes, maxsplit=1)[-1]
        candidates.extend(_SEPARATOR.split(featured))

    normalized_artist = _FEAT.sub("|", artist_name)
    candidates.extend(_SEPARATOR.split(normalized_artist))

    names: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        name = _clean_name(candidate)
        if not name:
            continue
        key = name.casefold()
        if key in _GENERIC_NAMES or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return tuple(names)


def _clean_name(value: str) -> str:
    cleaned = value.strip(" \t\r\n-–—,;:()[]{}'\"")
    cleaned = _TRAILING_ROLE.sub("", cleaned).strip()
    if len(cleaned) < 2 or len(cleaned) > 80:
        return ""
    if not any(character.isalpha() for character in cleaned):
        return ""
    return cleaned
