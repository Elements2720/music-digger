"""DJ set analysis entities: matches, passages, and whole sets."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal

from .._validation import (
    freeze_tuple,
    optional_str,
    require_bool,
    require_float,
    require_str,
)
from ..value_objects.audio_features import BPM, CamelotKey, EmbeddingVector, TimeRange
from .track import Track

ExactIdSource = Literal["shazam", "comments"]
EXACT_ID_SOURCES: Final[frozenset[str]] = frozenset({"shazam", "comments"})


@dataclass(frozen=True, slots=True)
class TrackMatch:
    """A catalog track returned by a similarity or exact-ID search."""

    track: Track
    similarity_score: float
    is_exact_id: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.track, Track):
            raise TypeError("track must be a Track")
        score = require_float(self.similarity_score, "similarity_score")
        if not -1.0 <= score <= 1.0:
            raise ValueError("similarity_score must be between -1.0 and 1.0")
        object.__setattr__(self, "similarity_score", score)
        object.__setattr__(
            self, "is_exact_id", require_bool(self.is_exact_id, "is_exact_id")
        )

    @property
    def similarity_percent(self) -> float:
        """Similarity clamped to ``[0, 1]`` and expressed as 0–100.

        One decimal place is kept: a plain integer collapses the realistically
        narrow spread of cosine similarities (0.99 vs 0.97) to identical "100"s
        and hides ordering information from the CLI table.
        """
        clamped = max(0.0, min(1.0, self.similarity_score))
        return round(clamped * 100, 1)


@dataclass(frozen=True, slots=True)
class Passage:
    """A time slice of a DJ set with detected features and candidate matches.

    ``exact_id_match`` records whether fingerprinting or tracklist parsing
    produced a definitive identification for this passage. When it did, the
    identified name lives in ``exact_id_title``/``exact_id_artist`` and
    ``exact_id_source`` says where it came from (``"shazam"`` or
    ``"comments"``). The identified track itself, when it is also in the local
    catalog, is represented by the corresponding ``TrackMatch`` in
    ``closest_matches`` with ``is_exact_id=True``.
    """

    time_range: TimeRange
    bpm: BPM | None = None
    key: CamelotKey | None = None
    exact_id_match: bool = False
    closest_matches: tuple[TrackMatch, ...] = ()
    exact_id_title: str | None = None
    exact_id_artist: str | None = None
    exact_id_source: ExactIdSource | None = None
    embedding: EmbeddingVector | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.time_range, TimeRange):
            raise TypeError("time_range must be a TimeRange")
        if self.bpm is not None and not isinstance(self.bpm, BPM):
            object.__setattr__(self, "bpm", BPM(self.bpm))
        if self.key is not None and not isinstance(self.key, CamelotKey):
            object.__setattr__(self, "key", CamelotKey(self.key))
        object.__setattr__(
            self,
            "exact_id_match",
            require_bool(self.exact_id_match, "exact_id_match"),
        )
        object.__setattr__(
            self, "exact_id_title", optional_str(self.exact_id_title, "exact_id_title")
        )
        object.__setattr__(
            self,
            "exact_id_artist",
            optional_str(self.exact_id_artist, "exact_id_artist"),
        )
        if self.exact_id_source is not None and (
            not isinstance(self.exact_id_source, str)
            or self.exact_id_source not in EXACT_ID_SOURCES
        ):
            raise ValueError(
                f"exact_id_source must be one of {sorted(EXACT_ID_SOURCES)} or None, "
                f"got {self.exact_id_source!r}"
            )
        if self.embedding is not None and not isinstance(
            self.embedding, EmbeddingVector
        ):
            raise TypeError("embedding must be an EmbeddingVector or None")
        matches = freeze_tuple(self.closest_matches, "closest_matches", TrackMatch)
        ordered = tuple(
            sorted(matches, key=lambda match: match.similarity_score, reverse=True)
        )
        object.__setattr__(self, "closest_matches", ordered)

    @property
    def best_match(self) -> TrackMatch | None:
        """Highest-scoring candidate, or ``None`` when nothing matched."""
        return self.closest_matches[0] if self.closest_matches else None

    @property
    def exact_match(self) -> TrackMatch | None:
        """The first fingerprint-confirmed candidate, if one was recorded."""
        return next(
            (match for match in self.closest_matches if match.is_exact_id), None
        )

    @property
    def exact_id_display_name(self) -> str | None:
        """Human-readable identified track, or ``None`` when unidentified."""
        if self.exact_id_title is None:
            return None
        if self.exact_id_artist is None:
            return self.exact_id_title
        return f"{self.exact_id_artist} - {self.exact_id_title}"

    def with_embedding(self, embedding: EmbeddingVector) -> Passage:
        """Return a copy carrying ``embedding`` without mutating this entity."""
        if not isinstance(embedding, EmbeddingVector):
            raise TypeError("embedding must be an EmbeddingVector")
        return replace(self, embedding=embedding)


@dataclass(frozen=True, slots=True)
class DJSet:
    """A downloaded DJ set and its analyzed passages."""

    id: str
    title: str
    source_url: str | None = None
    passages: tuple[Passage, ...] = ()
    duration_seconds: float | None = None
    artist: str | None = None
    thumbnail_url: str | None = None
    bpm_min: BPM | None = None
    bpm_max: BPM | None = None
    embedding: EmbeddingVector | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_str(self.id, "id"))
        object.__setattr__(self, "title", require_str(self.title, "title"))
        object.__setattr__(
            self, "source_url", optional_str(self.source_url, "source_url")
        )
        object.__setattr__(self, "artist", optional_str(self.artist, "artist"))
        object.__setattr__(
            self, "thumbnail_url", optional_str(self.thumbnail_url, "thumbnail_url")
        )
        if self.bpm_min is not None and not isinstance(self.bpm_min, BPM):
            object.__setattr__(self, "bpm_min", BPM(self.bpm_min))
        if self.bpm_max is not None and not isinstance(self.bpm_max, BPM):
            object.__setattr__(self, "bpm_max", BPM(self.bpm_max))
        if (
            self.bpm_min is not None
            and self.bpm_max is not None
            and self.bpm_min.value > self.bpm_max.value
        ):
            raise ValueError("bpm_min must be less than or equal to bpm_max")
        if self.embedding is not None and not isinstance(
            self.embedding, EmbeddingVector
        ):
            raise TypeError("embedding must be an EmbeddingVector or None")
        object.__setattr__(
            self,
            "passages",
            freeze_tuple(self.passages, "passages", Passage),
        )

        if self.duration_seconds is not None:
            duration = require_float(self.duration_seconds, "duration_seconds")
            if duration <= 0:
                raise ValueError("duration_seconds must be positive")
            for passage in self.passages:
                if passage.time_range.end_seconds > duration:
                    raise ValueError(
                        "passage ends after the DJ set duration: "
                        f"{passage.time_range.end_seconds} > {duration}"
                    )
            object.__setattr__(self, "duration_seconds", duration)

    @property
    def set_id(self) -> str:
        """Alias for ``id`` for call sites that prefer an explicit name."""
        return self.id

    @property
    def passage_count(self) -> int:
        """Number of analyzed passages."""
        return len(self.passages)

    def ordered_passages(self) -> tuple[Passage, ...]:
        """Passages sorted by start time."""
        return tuple(
            sorted(self.passages, key=lambda passage: passage.time_range.start_seconds)
        )

    def passage_at(self, seconds: float) -> Passage | None:
        """Return the passage containing ``seconds``, if any."""
        point = require_float(seconds, "seconds")
        if point < 0:
            raise ValueError("seconds must not be negative")
        return next(
            (
                passage
                for passage in self.passages
                if passage.time_range.contains(point)
            ),
            None,
        )

    def with_passage(self, passage: Passage) -> DJSet:
        """Return a copy with ``passage`` appended."""
        if not isinstance(passage, Passage):
            raise TypeError("passage must be a Passage")
        return replace(self, passages=(*self.passages, passage))

    def with_embedding(self, embedding: EmbeddingVector) -> DJSet:
        """Return a copy carrying ``embedding`` without mutating this entity."""
        if not isinstance(embedding, EmbeddingVector):
            raise TypeError("embedding must be an EmbeddingVector")
        return replace(self, embedding=embedding)


@dataclass(frozen=True, slots=True)
class SetMatch:
    """A stored DJ set returned by a whole-set similarity search."""

    dj_set: DJSet
    similarity_score: float

    def __post_init__(self) -> None:
        if not isinstance(self.dj_set, DJSet):
            raise TypeError("dj_set must be a DJSet")
        score = require_float(self.similarity_score, "similarity_score")
        if not -1.0 <= score <= 1.0:
            raise ValueError("similarity_score must be between -1.0 and 1.0")
        object.__setattr__(self, "similarity_score", score)

    @property
    def similarity_percent(self) -> float:
        """Similarity clamped to ``[0, 1]`` and expressed as 0-100.

        Matches :attr:`TrackMatch.similarity_percent`: one decimal place, so
        near-perfect neighbours stay distinguishable instead of collapsing
        into identical "100"s.
        """
        clamped = max(0.0, min(1.0, self.similarity_score))
        return round(clamped * 100, 1)


@dataclass(frozen=True, slots=True)
class DownloadedSet:
    """A DJ set resolved to a file on disk, ready for window-by-window analysis.

    ``is_temporary`` is ``True`` when the audio was downloaded by the caller's
    pipeline into a cache directory and may be deleted after analysis; local
    files the user pointed at are never temporary.
    """

    audio_path: Path
    title: str
    artist: str | None = None
    duration_seconds: float | None = None
    source_url: str | None = None
    thumbnail_url: str | None = None
    description: str = ""
    comments: tuple[str, ...] = ()
    is_temporary: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.audio_path, Path):
            raise TypeError("audio_path must be a Path")
        object.__setattr__(self, "title", require_str(self.title, "title"))
        object.__setattr__(self, "artist", optional_str(self.artist, "artist"))
        object.__setattr__(
            self, "source_url", optional_str(self.source_url, "source_url")
        )
        object.__setattr__(
            self, "thumbnail_url", optional_str(self.thumbnail_url, "thumbnail_url")
        )
        object.__setattr__(
            self,
            "description",
            require_str(self.description, "description", allow_empty=True),
        )
        comments = freeze_tuple(self.comments, "comments", str)
        object.__setattr__(self, "comments", comments)
        object.__setattr__(
            self, "is_temporary", require_bool(self.is_temporary, "is_temporary")
        )
        if self.duration_seconds is not None:
            duration = require_float(self.duration_seconds, "duration_seconds")
            if duration <= 0:
                raise ValueError("duration_seconds must be positive")
            object.__setattr__(self, "duration_seconds", duration)
