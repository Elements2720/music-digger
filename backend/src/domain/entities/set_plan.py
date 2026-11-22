"""Domain entities for DJ set planning and transition evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .track import Track

FlowMode = Literal["steady", "ramp_up", "cool_down", "any"]


@dataclass(frozen=True, slots=True)
class TransitionEvaluation:
    """Detailed score and breakdown of a musical transition between two tracks."""

    score: float
    harmonic_score: float
    bpm_score: float
    audio_score: float
    camelot_move: str
    bpm_delta: float


@dataclass(frozen=True, slots=True)
class NextTrackSuggestion:
    """A recommended candidate track for following a reference track in a set."""

    track: Track
    evaluation: TransitionEvaluation


@dataclass(frozen=True, slots=True)
class BridgeSuggestion:
    """A stepping-stone track bridging two musically distant tracks."""

    bridge_track: Track
    eval_from_a: TransitionEvaluation
    eval_to_b: TransitionEvaluation
    combined_score: float


@dataclass(frozen=True, slots=True)
class PlannedSet:
    """A curated, ordered set plan saved by the user."""

    id: int | None
    name: str
    track_ids: tuple[str, ...]
    created_at: str | None = None
    updated_at: str | None = None
