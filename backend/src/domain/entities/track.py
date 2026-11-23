"""Track-centric domain entities."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Literal

from .._validation import (
    freeze_tuple,
    optional_str,
    require_float,
    require_int,
    require_str,
)
from ..value_objects.audio_features import BPM, CamelotKey, EmbeddingVector, TimeRange

SeedCategory = Literal["electronic", "general"]
SeedStatus = Literal["pending", "fetched", "failed"]

SEED_CATEGORIES: Final[frozenset[str]] = frozenset({"electronic", "general"})
SEED_STATUSES: Final[frozenset[str]] = frozenset({"pending", "fetched", "failed"})

_MIN_RELEASE_YEAR = 1900
_MAX_RELEASE_YEAR = 2100


@dataclass(frozen=True, slots=True)
class Track:
    """A catalog track and the metadata needed for similarity search.

    ``bpm`` and ``key`` may be supplied as raw values; they are normalized into
    the corresponding value objects during construction. ``embedding`` is
    optional because a track can be catalogued before its preview is analyzed.
    """

    id: str
    title: str
    artist: str
    duration_seconds: float | None = None
    bpm: BPM | None = None
    key: CamelotKey | None = None
    genre: str | None = None
    release_year: int | None = None
    isrc: str | None = None
    preview_url: str | None = None
    artwork_url: str | None = None
    album: str | None = None
    store_url: str | None = None
    source: str = "unknown"
    external_id: str | None = None
    embedding: EmbeddingVector | None = None
    local_path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_str(self.id, "id"))
        object.__setattr__(self, "title", require_str(self.title, "title"))
        object.__setattr__(self, "artist", require_str(self.artist, "artist"))
        object.__setattr__(self, "source", require_str(self.source, "source"))

        if self.duration_seconds is not None:
            duration = require_float(self.duration_seconds, "duration_seconds")
            if duration <= 0:
                raise ValueError("duration_seconds must be positive")
            object.__setattr__(self, "duration_seconds", duration)

        if self.bpm is not None and not isinstance(self.bpm, BPM):
            object.__setattr__(self, "bpm", BPM(self.bpm))
        if self.key is not None and not isinstance(self.key, CamelotKey):
            object.__setattr__(self, "key", CamelotKey(self.key))

        object.__setattr__(self, "genre", optional_str(self.genre, "genre"))
        object.__setattr__(self, "isrc", optional_str(self.isrc, "isrc"))
        object.__setattr__(
            self, "preview_url", optional_str(self.preview_url, "preview_url")
        )
        object.__setattr__(
            self, "artwork_url", optional_str(self.artwork_url, "artwork_url")
        )
        object.__setattr__(self, "album", optional_str(self.album, "album"))
        object.__setattr__(self, "store_url", optional_str(self.store_url, "store_url"))
        object.__setattr__(
            self, "external_id", optional_str(self.external_id, "external_id")
        )
        object.__setattr__(
            self, "local_path", optional_str(self.local_path, "local_path")
        )

        if self.release_year is not None:
            year = require_int(self.release_year, "release_year")
            if not _MIN_RELEASE_YEAR <= year <= _MAX_RELEASE_YEAR:
                raise ValueError(
                    f"release_year must be between {_MIN_RELEASE_YEAR} and {_MAX_RELEASE_YEAR}"
                )
            object.__setattr__(self, "release_year", year)

        if self.embedding is not None and not isinstance(
            self.embedding, EmbeddingVector
        ):
            raise TypeError("embedding must be an EmbeddingVector or None")

    @property
    def track_id(self) -> str:
        """Alias for ``id`` for call sites that prefer an explicit name."""
        return self.id

    @property
    def duration(self) -> float | None:
        """Alias for ``duration_seconds``."""
        return self.duration_seconds

    @property
    def display_name(self) -> str:
        """Human-readable ``Artist - Title`` label."""
        return f"{self.artist} - {self.title}"

    def with_embedding(self, embedding: EmbeddingVector) -> Track:
        """Return a copy carrying ``embedding`` without mutating this entity."""
        if not isinstance(embedding, EmbeddingVector):
            raise TypeError("embedding must be an EmbeddingVector")
        return replace(self, embedding=embedding)

    def with_local_path(self, local_path: str) -> Track:
        """Return a copy carrying ``local_path`` without mutating this entity."""
        return replace(self, local_path=require_str(local_path, "local_path"))


@dataclass(frozen=True, slots=True)
class SeedArtist:
    """An artist proposed as a catalog crawl seed.

    ``priority_score`` is normalized to ``[0.0, 1.0]`` so electronic and general
    seeds can be mixed deterministically.
    """

    name: str
    priority_score: float
    category: SeedCategory
    status: SeedStatus = "pending"
    source: str = "llm"
    external_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_str(self.name, "name"))
        priority = require_float(self.priority_score, "priority_score")
        if not 0.0 <= priority <= 1.0:
            raise ValueError("priority_score must be between 0.0 and 1.0")
        object.__setattr__(self, "priority_score", priority)

        if not isinstance(self.category, str) or self.category not in SEED_CATEGORIES:
            raise ValueError(
                f"category must be one of {sorted(SEED_CATEGORIES)}, got {self.category!r}"
            )
        if not isinstance(self.status, str) or self.status not in SEED_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(SEED_STATUSES)}, got {self.status!r}"
            )
        object.__setattr__(self, "source", require_str(self.source, "source"))
        object.__setattr__(
            self, "external_id", optional_str(self.external_id, "external_id")
        )

    @property
    def is_pending(self) -> bool:
        """True while the crawler still has to process this seed."""
        return self.status == "pending"

    def with_status(self, status: SeedStatus) -> SeedArtist:
        """Return a copy with a new crawl status."""
        return replace(self, status=status)


@dataclass(frozen=True, slots=True)
class AudioBuffer:
    """Raw mono PCM samples held in memory only for the duration of analysis."""

    pcm_bytes: bytes
    sample_rate: int

    def __post_init__(self) -> None:
        if isinstance(self.pcm_bytes, (bytearray, memoryview)):
            object.__setattr__(self, "pcm_bytes", bytes(self.pcm_bytes))
        elif not isinstance(self.pcm_bytes, bytes):
            raise TypeError("pcm_bytes must be bytes")
        if not self.pcm_bytes:
            raise ValueError("pcm_bytes must not be empty")

        sample_rate = require_int(self.sample_rate, "sample_rate")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        object.__setattr__(self, "sample_rate", sample_rate)

    @property
    def size_bytes(self) -> int:
        """Number of bytes held by the PCM buffer."""
        return len(self.pcm_bytes)


@dataclass(frozen=True, slots=True)
class TrackReference:
    """A lightweight artist/title reference extracted from free text."""

    artist: str
    title: str
    timestamp: TimeRange | None = None
    confidence: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "artist", require_str(self.artist, "artist"))
        object.__setattr__(self, "title", require_str(self.title, "title"))
        if self.timestamp is not None and not isinstance(self.timestamp, TimeRange):
            raise TypeError("timestamp must be a TimeRange or None")
        confidence = require_float(self.confidence, "confidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        object.__setattr__(self, "confidence", confidence)

    @property
    def display_name(self) -> str:
        """Human-readable ``Artist - Title`` label."""
        return f"{self.artist} - {self.title}"


@dataclass(frozen=True, slots=True)
class TrackVibe:
    """LLM-generated mood/vibe tags for a track."""

    tags: tuple[str, ...]
    mood: str
    energy: float
    description: str = ""

    def __post_init__(self) -> None:
        raw_tags = freeze_tuple(self.tags, "tags", str)
        normalized_tags: list[str] = []
        seen: set[str] = set()
        for tag in raw_tags:
            normalized = require_str(tag, "tag")
            key = normalized.casefold()
            if key not in seen:
                seen.add(key)
                normalized_tags.append(normalized)
        object.__setattr__(self, "tags", tuple(normalized_tags))

        object.__setattr__(self, "mood", require_str(self.mood, "mood"))
        energy = require_float(self.energy, "energy")
        if not 0.0 <= energy <= 1.0:
            raise ValueError("energy must be between 0.0 and 1.0")
        object.__setattr__(self, "energy", energy)
        object.__setattr__(
            self,
            "description",
            require_str(self.description, "description", allow_empty=True),
        )


BlacklistKind = Literal["artist", "track"]


@dataclass(frozen=True, slots=True)
class BlacklistEntry:
    """An artist or track blocked from crawling, indexing, or catalog display."""

    id: int | None
    kind: BlacklistKind
    normalized_key: str
    display_name: str
    artist_name: str | None = None
    track_title: str | None = None
    reason: str | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        if self.id is not None:
            object.__setattr__(self, "id", require_int(self.id, "id"))
        if self.kind not in ("artist", "track"):
            raise ValueError(f"kind must be 'artist' or 'track', got {self.kind!r}")
        object.__setattr__(self, "kind", self.kind)
        object.__setattr__(
            self, "normalized_key", require_str(self.normalized_key, "normalized_key")
        )
        object.__setattr__(
            self, "display_name", require_str(self.display_name, "display_name")
        )
        object.__setattr__(
            self, "artist_name", optional_str(self.artist_name, "artist_name")
        )
        object.__setattr__(
            self, "track_title", optional_str(self.track_title, "track_title")
        )
        object.__setattr__(self, "reason", optional_str(self.reason, "reason"))
        object.__setattr__(
            self, "created_at", optional_str(self.created_at, "created_at")
        )


@dataclass(frozen=True, slots=True)
class LikedArtist:
    """An artist liked by the user to steer recommendations and taste matching."""

    artist_name: str
    normalized_key: str
    created_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "artist_name", require_str(self.artist_name, "artist_name")
        )
        object.__setattr__(
            self, "normalized_key", require_str(self.normalized_key, "normalized_key")
        )
        object.__setattr__(
            self, "created_at", optional_str(self.created_at, "created_at")
        )
