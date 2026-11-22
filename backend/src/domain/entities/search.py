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

        genre_matches = self.genre_filter is None or (
            track.genre is not None
            and track.genre.casefold() == self.genre_filter.casefold()
        )
        return genre_matches
