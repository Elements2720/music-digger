"""Use case: find the closest catalog tracks to one indexed track.

Given a reference track id and a :class:`SearchFilter`, the use case loads the
reference's stored CLAP vector, queries the disk-backed vector index for the
nearest neighbours (cosine similarity), removes the reference itself, and
applies optional BPM-tolerance and harmonic (Camelot wheel) constraints
before returning ordered matches.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..entities.dj_set import TrackMatch
from ..entities.search import SearchFilter
from ..entities.track import Track
from ..interfaces.repositories import ITrackRepository
from ..value_objects.audio_features import BPM_MAX, BPM_MIN, CamelotKey

LOGGER = logging.getLogger(__name__)

_MAX_FILTER_LIMIT = 500


class DigLookupError(Exception):
    """Base class for dig lookup failures."""


class TrackNotFoundError(DigLookupError):
    """The requested track id is not in the local catalog."""


class TrackNotEmbeddedError(DigLookupError):
    """The requested track has no stored embedding yet — index it first."""


@dataclass(frozen=True, slots=True)
class DigResult:
    """The reference track plus its nearest neighbours, best first."""

    reference: Track
    matches: tuple[TrackMatch, ...]


class DigSimilarTracks:
    """Track-to-track similarity search over the local catalog."""

    def __init__(self, *, track_repository: ITrackRepository) -> None:
        self._track_repository = track_repository

    async def execute(
        self,
        track_id: str,
        search_filter: SearchFilter | None = None,
        *,
        bpm_tolerance: float | None = None,
        harmonic: bool = False,
    ) -> DigResult:
        """Return the closest tracks to ``track_id``.

        ``bpm_tolerance`` narrows the filter to ``reference_bpm ± tolerance``
        (intersected with any explicit bounds). ``harmonic`` expands the
        Camelot allow-list with the reference key's compatible neighbours
        (same key, relative major/minor, ±1 on the same side). One extra
        neighbour is fetched so removing the reference itself still leaves
        ``filter.limit`` results.
        """
        reference = await self._track_repository.get_by_id(track_id)
        if reference is None:
            raise TrackNotFoundError(f"track {track_id!r} is not in the catalog")
        if reference.embedding is None:
            raise TrackNotEmbeddedError(
                f"track {track_id!r} has no embedding yet; run `dig index` first"
            )

        base = search_filter or SearchFilter()
        effective = self._effective_filter(
            reference,
            base,
            bpm_tolerance=bpm_tolerance,
            harmonic=harmonic,
        )

        # Over-fetch by one so dropping the reference still fills the limit.
        fetch_limit = min(_MAX_FILTER_LIMIT, effective.limit + 1)
        matches = await self._track_repository.find_similar(
            reference.embedding,
            replace(effective, limit=fetch_limit),
        )
        filtered = tuple(match for match in matches if match.track.id != reference.id)[
            : effective.limit
        ]
        return DigResult(reference=reference, matches=filtered)

    @staticmethod
    def _effective_filter(
        reference: Track,
        search_filter: SearchFilter,
        *,
        bpm_tolerance: float | None,
        harmonic: bool,
    ) -> SearchFilter:
        bpm_min = search_filter.bpm_min
        bpm_max = search_filter.bpm_max
        if bpm_tolerance is not None and reference.bpm is not None:
            if bpm_tolerance < 0:
                raise ValueError("bpm_tolerance must not be negative")
            low = max(BPM_MIN, reference.bpm.value - bpm_tolerance)
            high = min(BPM_MAX, reference.bpm.value + bpm_tolerance)
            if search_filter.bpm_min is not None:
                low = max(low, search_filter.bpm_min)
            if search_filter.bpm_max is not None:
                high = min(high, search_filter.bpm_max)
            if low > high:
                raise ValueError(
                    "bpm tolerance window does not overlap the filter bounds"
                )
            bpm_min, bpm_max = low, high

        camelot_keys = search_filter.camelot_keys
        if harmonic and reference.key is not None:
            compatible = {
                key
                for key in _all_camelot_keys()
                if reference.key.is_harmonic_compatible(key)
            }
            camelot_keys = tuple(
                dict.fromkeys((*search_filter.camelot_keys, *compatible))
            )

        return replace(
            search_filter,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            camelot_keys=camelot_keys,
        )


def _all_camelot_keys() -> Sequence[CamelotKey]:
    return tuple(
        CamelotKey(f"{number}{letter}")
        for number in range(1, 13)
        for letter in ("A", "B")
    )


__all__ = [
    "DigLookupError",
    "DigResult",
    "DigSimilarTracks",
    "TrackNotEmbeddedError",
    "TrackNotFoundError",
]
