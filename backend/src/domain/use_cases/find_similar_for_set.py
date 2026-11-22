"""Use case: dig for tracks and sets starting from an analyzed DJ set.

``similar_tracks`` aggregates the per-passage nearest-neighbour searches of a
stored DJ set into one ranked dig result: a track that is close to several
passages (played and re-played across the set) bubbles to the top because its
best similarity score wins the dedup. ``similar_sets`` finds the nearest
analyzed sets by mean-embedding cosine similarity — the "sets like this one"
seam.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..entities.dj_set import DJSet, Passage, SetMatch, TrackMatch
from ..entities.search import SearchFilter
from ..interfaces.repositories import ISetRepository, ITrackRepository
from ..value_objects.audio_features import BPM_MAX, BPM_MIN

LOGGER = logging.getLogger(__name__)

_MAX_FILTER_LIMIT = 500

#: Default result cap for passage-aggregated track digs.
DEFAULT_DIG_LIMIT = 100

#: Default result cap for whole-set similarity.
DEFAULT_SET_LIMIT = 12


class SetDigError(Exception):
    """Base class for set-dig lookup failures."""


class SetNotFoundError(SetDigError):
    """The requested DJ set id is not stored locally."""


class SetNotEmbeddedError(SetDigError):
    """The requested DJ set has no stored embedding yet — analyze it first."""


@dataclass(frozen=True, slots=True)
class SetDigResult:
    """The reference set plus the aggregated tracks it points at."""

    reference: DJSet
    matches: tuple[TrackMatch, ...]


class FindSimilarForSet:
    """Set-to-track and set-to-set similarity search over the local stores."""

    def __init__(
        self,
        *,
        track_repository: ITrackRepository,
        set_repository: ISetRepository,
    ) -> None:
        self._track_repository = track_repository
        self._set_repository = set_repository

    async def similar_tracks(
        self,
        set_id: str,
        search_filter: SearchFilter | None = None,
        *,
        limit: int = DEFAULT_DIG_LIMIT,
        bpm_tolerance: float | None = None,
    ) -> SetDigResult:
        """Return catalog tracks closest to any passage of ``set_id``.

        Every passage with an embedding issues its own ``±bpm_tolerance``
        vector search; results are deduplicated by track id keeping each
        track's best score, ordered by descending similarity, and truncated
        to ``limit``. ``exclude_heard`` in the filter is honored by the
        repository layer.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")
        reference = await self._set_repository.get_by_id(set_id)
        if reference is None:
            raise SetNotFoundError(f"DJ set {set_id!r} is not stored locally")

        base = search_filter or SearchFilter()
        effective_limit = min(limit, _MAX_FILTER_LIMIT)
        # Over-fetch per passage so the dedup across passages still fills the
        # requested limit even when several passages surface the same tracks.
        per_passage_limit = min(_MAX_FILTER_LIMIT, effective_limit)

        best_by_track: dict[str, TrackMatch] = {}
        for passage in reference.passages:
            if passage.embedding is None:
                continue
            passage_filter = self._passage_filter(
                base, passage, bpm_tolerance=bpm_tolerance
            )
            if passage_filter is None:
                continue  # tolerance window does not overlap the filter bounds
            try:
                matches = await self._track_repository.find_similar(
                    passage.embedding,
                    replace(passage_filter, limit=per_passage_limit),
                )
            except Exception:
                LOGGER.exception(
                    "passage search failed for %s; skipping passage",
                    passage.time_range,
                )
                continue
            for match in matches:
                current = best_by_track.get(match.track.id)
                if current is None or match.similarity_score > current.similarity_score:
                    best_by_track[match.track.id] = match

        ordered = sorted(
            best_by_track.values(),
            key=lambda match: match.similarity_score,
            reverse=True,
        )[:effective_limit]
        return SetDigResult(reference=reference, matches=tuple(ordered))

    async def similar_sets(
        self,
        set_id: str,
        *,
        limit: int = DEFAULT_SET_LIMIT,
    ) -> Sequence[SetMatch]:
        """Return the nearest stored sets to ``set_id`` (itself excluded)."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        reference = await self._set_repository.get_by_id(set_id)
        if reference is None:
            raise SetNotFoundError(f"DJ set {set_id!r} is not stored locally")
        if reference.embedding is None:
            raise SetNotEmbeddedError(
                f"DJ set {set_id!r} has no embedding yet; run `dig analyze-set` first"
            )
        matches = await self._set_repository.find_similar_sets(
            reference.embedding,
            limit=min(limit + 1, _MAX_FILTER_LIMIT),
        )
        return tuple(match for match in matches if match.dj_set.id != reference.id)[
            :limit
        ]

    @staticmethod
    def _passage_filter(
        base: SearchFilter,
        passage: Passage,
        *,
        bpm_tolerance: float | None,
    ) -> SearchFilter | None:
        """Narrow ``base`` to the passage's tempo window when possible.

        Returns ``None`` when the tolerance window does not overlap the
        caller's explicit bounds — that passage simply contributes nothing.
        """
        bpm_min = base.bpm_min
        bpm_max = base.bpm_max
        if bpm_tolerance is not None and passage.bpm is not None:
            if bpm_tolerance < 0:
                raise ValueError("bpm_tolerance must not be negative")
            low = max(BPM_MIN, passage.bpm.value - bpm_tolerance)
            high = min(BPM_MAX, passage.bpm.value + bpm_tolerance)
            if base.bpm_min is not None:
                low = max(low, base.bpm_min)
            if base.bpm_max is not None:
                high = min(high, base.bpm_max)
            if low > high:
                return None
            bpm_min, bpm_max = low, high
        return replace(base, bpm_min=bpm_min, bpm_max=bpm_max)


__all__ = [
    "DEFAULT_DIG_LIMIT",
    "DEFAULT_SET_LIMIT",
    "FindSimilarForSet",
    "SetDigError",
    "SetDigResult",
    "SetNotEmbeddedError",
    "SetNotFoundError",
]
