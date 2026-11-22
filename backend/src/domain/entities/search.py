"""Search criteria for the local similarity index."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from .._validation import (
    freeze_tuple,
    optional_str,
    require_bool,
    require_float,
    require_int,
)
from ..value_objects.audio_features import BPM, BPM_MAX, BPM_MIN, CamelotKey
from .track import Track

_MAX_LIMIT = 500


@dataclass(frozen=True, slots=True)
class SearchFilter:
    """Constraints applied to a local vector/metadata search.

    BPM bounds are inclusive. ``camelot_keys`` is an exact allow-list; callers
    that want harmonic neighbours should expand it with
    :meth:`CamelotKey.is_harmonic_compatible` before constructing the filter.
    """

    bpm_min: float | None = None
    bpm_max: float | None = None
    camelot_keys: tuple[CamelotKey, ...] = ()
    exclude_heard: bool = False
    genre_filter: str | None = None
    limit: int = 50
    min_year: int | None = None
    max_year: int | None = None
    genres: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        minimum = self._normalize_bpm_bound(self.bpm_min, "bpm_min")
        maximum = self._normalize_bpm_bound(self.bpm_max, "bpm_max")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("bpm_min must be less than or equal to bpm_max")
        object.__setattr__(self, "bpm_min", minimum)
        object.__setattr__(self, "bpm_max", maximum)

        raw_keys = freeze_tuple(self.camelot_keys, "camelot_keys")
        normalized_keys: list[CamelotKey] = []
        seen: set[CamelotKey] = set()
        for key in raw_keys:
            camelot_key = key if isinstance(key, CamelotKey) else CamelotKey(key)
            if camelot_key not in seen:
                seen.add(camelot_key)
                normalized_keys.append(camelot_key)
        object.__setattr__(self, "camelot_keys", tuple(normalized_keys))

        object.__setattr__(
            self,
            "exclude_heard",
            require_bool(self.exclude_heard, "exclude_heard"),
        )
        object.__setattr__(
            self, "genre_filter", optional_str(self.genre_filter, "genre_filter")
        )

        limit = require_int(self.limit, "limit")
        if not 1 <= limit <= _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
        object.__setattr__(self, "limit", limit)

        if self.min_year is not None:
            min_y = require_int(self.min_year, "min_year")
            if not 1900 <= min_y <= 2100:
                raise ValueError("min_year must be between 1900 and 2100")
            object.__setattr__(self, "min_year", min_y)

        if self.max_year is not None:
            max_y = require_int(self.max_year, "max_year")
            if not 1900 <= max_y <= 2100:
                raise ValueError("max_year must be between 1900 and 2100")
            object.__setattr__(self, "max_year", max_y)

        if (
            self.min_year is not None
            and self.max_year is not None
            and self.min_year > self.max_year
        ):
            raise ValueError("min_year must be less than or equal to max_year")

        raw_genres = freeze_tuple(self.genres, "genres", str)
        normalized_genres: list[str] = []
        seen_g: set[str] = set()
        for g in raw_genres:
            clean_g = g.strip()
            if clean_g:
                key_g = clean_g.casefold()
                if key_g not in seen_g:
                    seen_g.add(key_g)
                    normalized_genres.append(clean_g)
        object.__setattr__(self, "genres", tuple(normalized_genres))

    @staticmethod
    def _normalize_bpm_bound(value: object | None, field: str) -> float | None:
        if value is None:
            return None
        number = value.value if isinstance(value, BPM) else require_float(value, field)
        if not BPM_MIN <= number <= BPM_MAX:
            raise ValueError(f"{field} must be between {BPM_MIN} and {BPM_MAX}")
        return number

    def matches(self, track: Track, heard_ids: Collection[str] = frozenset()) -> bool:
        """Return True when ``track`` satisfies every active constraint."""
        if not isinstance(track, Track):
            raise TypeError("track must be a Track")

        if self.bpm_min is not None and (
            track.bpm is None or track.bpm.value < self.bpm_min
        ):
            return False
        if self.bpm_max is not None and (
            track.bpm is None or track.bpm.value > self.bpm_max
        ):
            return False

        if self.camelot_keys and (
            track.key is None or track.key not in self.camelot_keys
        ):
            return False

        if self.exclude_heard and track.id in heard_ids:
            return False

        if self.min_year is not None and (
            track.release_year is None or track.release_year < self.min_year
        ):
            return False

        if self.max_year is not None and (
            track.release_year is None or track.release_year > self.max_year
        ):
            return False

        if self.genres:
            if track.genre is None:
                return False
            g_low = track.genre.casefold()
            if not any(req.casefold() in g_low for req in self.genres):
                return False
        elif self.genre_filter is not None and (
            track.genre is None
            or track.genre.casefold() != self.genre_filter.casefold()
        ):
            return False

        return True
