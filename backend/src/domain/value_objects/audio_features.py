"""Pure value objects describing musical and audio properties.

All objects are immutable and validate themselves on construction. No I/O,
third-party libraries, or outer-layer imports are allowed here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

from .._validation import require_float, require_int

BPM_MIN = 40.0
BPM_MAX = 220.0


@dataclass(frozen=True, slots=True, order=True)
class BPM:
    """Tempo in beats per minute, constrained to a musically useful range."""

    value: float

    def __post_init__(self) -> None:
        normalized = require_float(self.value, "BPM")
        if not BPM_MIN <= normalized <= BPM_MAX:
            raise ValueError(
                f"BPM must be between {BPM_MIN} and {BPM_MAX}, got {normalized}"
            )
        object.__setattr__(self, "value", normalized)

    @property
    def bpm(self) -> float:
        """Alias for ``value`` for call sites that prefer an explicit name."""
        return self.value

    def is_close_to(self, other: BPM, tolerance: float = 1.0) -> bool:
        """Return True when two tempos differ by at most ``tolerance`` BPM."""
        if not isinstance(other, BPM):
            raise TypeError("other must be a BPM")
        tolerance_value = require_float(tolerance, "tolerance")
        if tolerance_value < 0:
            raise ValueError("tolerance must not be negative")
        return abs(self.value - other.value) <= tolerance_value

    def __str__(self) -> str:
        return f"{self.value:g} BPM"


_CAMELOT_PATTERN = re.compile(r"^(?P<number>[1-9]|1[0-2])(?P<letter>[AB])$")


@dataclass(frozen=True, slots=True)
class CamelotKey:
    """A key on the Camelot wheel, written as ``1A``–``12A`` or ``1B``–``12B``."""

    notation: str

    def __post_init__(self) -> None:
        if not isinstance(self.notation, str):
            raise TypeError("Camelot key notation must be a string")
        normalized = self.notation.strip().upper()
        if not _CAMELOT_PATTERN.fullmatch(normalized):
            raise ValueError(
                f"Camelot key must use notation 1A-12A or 1B-12B, got {self.notation!r}"
            )
        object.__setattr__(self, "notation", normalized)

    @property
    def number(self) -> int:
        """The wheel position (1–12)."""
        return int(self.notation[:-1])

    @property
    def letter(self) -> str:
        """The wheel side: ``A`` (minor) or ``B`` (major)."""
        return self.notation[-1]

    @property
    def value(self) -> str:
        """Alias for the canonical notation."""
        return self.notation

    @property
    def key(self) -> str:
        """Alias for the canonical notation."""
        return self.notation

    def is_harmonic_compatible(self, other: CamelotKey) -> bool:
        """Return True when ``other`` can be mixed harmonically with this key.

        Compatible moves are the standard Camelot rules:

        * the same key;
        * the relative major/minor (same number, other letter);
        * one step clockwise or counter-clockwise on the same side, including
          the 12 ↔ 1 wrap-around.

        The optional +7 "energy boost" move is intentionally not included.
        """
        if not isinstance(other, CamelotKey):
            raise TypeError("other must be a CamelotKey")
        if self.notation == other.notation:
            return True
        if self.number == other.number:
            return True
        is_neighbour = self.letter == other.letter and (
            self.number - other.number
        ) % 12 in (1, 11)
        return is_neighbour

    def __str__(self) -> str:
        return self.notation


@dataclass(frozen=True, slots=True, order=True)
class TimeRange:
    """A half-open time interval ``[start_seconds, end_seconds)`` in seconds."""

    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        start = require_float(self.start_seconds, "start_seconds")
        end = require_float(self.end_seconds, "end_seconds")
        if start < 0:
            raise ValueError("start_seconds must not be negative")
        if end <= start:
            raise ValueError("end_seconds must be greater than start_seconds")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)

    @property
    def duration_seconds(self) -> float:
        """Length of the interval in seconds."""
        return self.end_seconds - self.start_seconds

    def contains(self, seconds: float) -> bool:
        """Return True when ``seconds`` lies in this half-open interval."""
        point = require_float(seconds, "seconds")
        return self.start_seconds <= point < self.end_seconds

    def overlaps(self, other: TimeRange) -> bool:
        """Return True when the two half-open intervals share any time."""
        if not isinstance(other, TimeRange):
            raise TypeError("other must be a TimeRange")
        return (
            self.start_seconds < other.end_seconds
            and other.start_seconds < self.end_seconds
        )

    def __str__(self) -> str:
        return f"[{self.start_seconds:g}s, {self.end_seconds:g}s)"


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """An immutable, finite-valued embedding vector.

    ``dimension`` is optional at construction: when omitted it is inferred from
    ``values``; when supplied it must match. Dimension consistency is also
    enforced when comparing vectors. Use :meth:`validate_dimension` when a model
    has a known output width (for example CLAP's 512-dimensional embeddings).
    """

    values: tuple[float, ...]
    dimension: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.values, (str, bytes, bytearray)):
            raise TypeError("embedding values must be an iterable of numbers")
        try:
            raw_values = tuple(self.values)
        except TypeError as exc:
            raise TypeError("embedding values must be an iterable of numbers") from exc
        if not raw_values:
            raise ValueError("embedding vector must not be empty")
        normalized = tuple(
            require_float(item, f"embedding value at index {index}")
            for index, item in enumerate(raw_values)
        )
        object.__setattr__(self, "values", normalized)

        if self.dimension is None:
            object.__setattr__(self, "dimension", len(normalized))
        else:
            dimension = require_int(self.dimension, "dimension")
            if dimension <= 0:
                raise ValueError("dimension must be positive")
            if dimension != len(normalized):
                raise ValueError(
                    f"embedding dimension mismatch: expected {dimension}, "
                    f"got {len(normalized)}"
                )
            object.__setattr__(self, "dimension", dimension)

    @classmethod
    def from_sequence(
        cls,
        values: Iterable[float],
        *,
        expected_dimension: int | None = None,
    ) -> EmbeddingVector:
        """Build a vector from any iterable and optionally check its width."""
        return cls(values=tuple(values), dimension=expected_dimension)

    def validate_dimension(self, expected_dimension: int) -> None:
        """Raise ``ValueError`` unless the vector has the expected width."""
        expected = require_int(expected_dimension, "expected_dimension")
        if expected <= 0:
            raise ValueError("expected_dimension must be positive")
        if self.dimension != expected:
            raise ValueError(
                f"embedding dimension mismatch: expected {expected}, got {self.dimension}"
            )

    def cosine_similarity(self, other: EmbeddingVector) -> float:
        """Return cosine similarity in ``[-1.0, 1.0]`` using pure Python math."""
        if not isinstance(other, EmbeddingVector):
            raise TypeError("other must be an EmbeddingVector")
        if self.dimension != other.dimension:
            raise ValueError(
                "cannot compare embeddings with different dimensions: "
                f"{self.dimension} != {other.dimension}"
            )
        dot_product = math.fsum(a * b for a, b in zip(self.values, other.values))
        self_norm = math.sqrt(math.fsum(value * value for value in self.values))
        other_norm = math.sqrt(math.fsum(value * value for value in other.values))
        if self_norm == 0.0 or other_norm == 0.0:
            raise ValueError("cosine similarity is undefined for a zero vector")
        score = dot_product / (self_norm * other_norm)
        # Guard against tiny floating-point excursions outside the valid range.
        return max(-1.0, min(1.0, score))

    def __len__(self) -> int:
        return len(self.values)


@dataclass(frozen=True, slots=True)
class AudioFeatures:
    """Musical features extracted from a single audio window.

    ``None`` means the extractor could not determine a confident value; the
    analysis pipeline must be able to continue with partial features.
    """

    bpm: BPM | None = None
    key: CamelotKey | None = None

    def __post_init__(self) -> None:
        if self.bpm is not None and not isinstance(self.bpm, BPM):
            object.__setattr__(self, "bpm", BPM(self.bpm))
        if self.key is not None and not isinstance(self.key, CamelotKey):
            object.__setattr__(self, "key", CamelotKey(self.key))
