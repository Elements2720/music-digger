"""Text normalization used for catalog and seed deduplication.

Delegates to canonical pure domain normalizers in ``domain._validation``
so that normalization logic can never diverge across layers.
"""

from __future__ import annotations

from domain._validation import (
    normalize_artist_key,
    normalize_key,
    normalize_track_key,
)

# Aliases preserving backwards compatibility with existing data-layer callers
normalize_text = normalize_key
normalize_seed_name = normalize_artist_key
normalize_artist_title = normalize_track_key

__all__ = [
    "normalize_artist_key",
    "normalize_artist_title",
    "normalize_key",
    "normalize_seed_name",
    "normalize_text",
    "normalize_track_key",
]
