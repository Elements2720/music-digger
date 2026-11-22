"""Curated Techno & underground electronic subgenre presets and pure guard filters."""

from __future__ import annotations

from collections.abc import Sequence

TECHNO_SUBGENRE_PRESETS: tuple[str, ...] = (
    "Techno",
    "Underground Techno",
    "Melodic Techno",
    "Hard Techno",
    "Peak Time Techno",
    "Driving Techno",
    "Hypnotic Techno",
    "Raw Techno",
    "Industrial Techno",
    "Minimal Techno",
    "Acid Techno",
    "Dark Techno",
    "Deep Techno",
    "Hardcore Techno",
    "Schranz",
    "Melodic House",
    "Afro House",
    "Tech House",
    "Progressive House",
    "Deep House",
    "Acid House",
    "Trance",
    "Psytrance",
    "Electronic",
    "House",
    "Dance",
)

ELECTRONIC_ALLOWED_GENRE_TOKENS: frozenset[str] = frozenset(
    {
        "techno",
        "electronic",
        "dance",
        "house",
        "trance",
        "electronica",
        "minimal",
        "hardcore",
        "hardstyle",
        "acid",
        "afro house",
        "melodic",
        "tech house",
        "deep house",
        "progressive",
        "psytrance",
        "schranz",
        "industrial",
        "rave",
        "club",
        "edm",
        "breakbeat",
        "drum & bass",
        "drum'n'bass",
        "jungle",
        "dubstep",
        "electro",
        "ambient",
        "downtempo",
        "idm",
    }
)

NON_ELECTRONIC_BLOCKED_GENRE_TOKENS: frozenset[str] = frozenset(
    {
        "pop",
        "hip-hop",
        "hip hop",
        "rap",
        "r&b",
        "soul",
        "rock",
        "alternative",
        "country",
        "jazz",
        "classical",
        "latin",
        "reggae",
        "metal",
        "folk",
        "blues",
        "punk",
        "indie",
        "soundtrack",
        "spoken word",
        "comedy",
        "children",
        "christian",
        "gospel",
        "k-pop",
        "j-pop",
        "disco",
        "funk",
        "singer/songwriter",
    }
)

_CORE_ELECTRONIC_TERMS: tuple[str, ...] = (
    "techno",
    "house",
    "trance",
    "electronic",
    "dance",
    "electronica",
    "schranz",
)


def track_matches_genre_guard(
    genre: str | None,
    *,
    allowed_genres: Sequence[str] = (),
    electronic_only: bool = False,
) -> bool:
    """Return True when ``genre`` satisfies allowed list or electronic constraints."""
    if allowed_genres:
        if not genre or not genre.strip():
            return False
        g_low = genre.strip().casefold()
        return any(
            req.strip().casefold() in g_low
            for req in allowed_genres
            if req and req.strip()
        )

    if electronic_only:
        if not genre or not genre.strip():
            # If no genre tag is present (common in local rips), don't discard
            return True
        g_low = genre.strip().casefold()
        has_electronic = any(tok in g_low for tok in ELECTRONIC_ALLOWED_GENRE_TOKENS)
        has_blocked = any(tok in g_low for tok in NON_ELECTRONIC_BLOCKED_GENRE_TOKENS)

        if has_electronic and not has_blocked:
            return True
        if has_blocked and not any(core in g_low for core in _CORE_ELECTRONIC_TERMS):
            return False
        return has_electronic

    return True


def track_matches_year(
    release_year: int | None,
    *,
    min_year: int | None = None,
    max_year: int | None = None,
    reject_none_on_filter: bool = False,
) -> bool:
    """Return True if ``release_year`` is within ``[min_year, max_year]``."""
    if min_year is not None:
        if release_year is None:
            return not reject_none_on_filter
        if release_year < min_year:
            return False

    if max_year is not None:
        if release_year is None:
            return not reject_none_on_filter
        if release_year > max_year:
            return False

    return True
