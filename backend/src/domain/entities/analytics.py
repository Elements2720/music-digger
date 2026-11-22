"""Pure-domain analytics and summary entities for the catalog."""

from __future__ import annotations

from dataclasses import dataclass

from .._validation import (
    freeze_tuple,
    optional_str,
    require_int,
    require_str,
)


@dataclass(frozen=True, slots=True)
class GenreStat:
    """Track count and embedded count per genre."""

    genre: str
    track_count: int
    embedded_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "genre", require_str(self.genre, "genre"))
        track_cnt = require_int(self.track_count, "track_count")
        if track_cnt < 0:
            raise ValueError("track_count must be non-negative")
        object.__setattr__(self, "track_count", track_cnt)
        emb_cnt = require_int(self.embedded_count, "embedded_count")
        if emb_cnt < 0:
            raise ValueError("embedded_count must be non-negative")
        object.__setattr__(self, "embedded_count", emb_cnt)


@dataclass(frozen=True, slots=True)
class BpmBucketStat:
    """Track count within a BPM range bucket."""

    label: str
    track_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", require_str(self.label, "label"))
        cnt = require_int(self.track_count, "track_count")
        if cnt < 0:
            raise ValueError("track_count must be non-negative")
        object.__setattr__(self, "track_count", cnt)


@dataclass(frozen=True, slots=True)
class SourceStat:
    """Track count and embedded count per ingestion source."""

    source: str
    track_count: int
    embedded_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", require_str(self.source, "source"))
        track_cnt = require_int(self.track_count, "track_count")
        if track_cnt < 0:
            raise ValueError("track_count must be non-negative")
        object.__setattr__(self, "track_count", track_cnt)
        emb_cnt = require_int(self.embedded_count, "embedded_count")
        if emb_cnt < 0:
            raise ValueError("embedded_count must be non-negative")
        object.__setattr__(self, "embedded_count", emb_cnt)


@dataclass(frozen=True, slots=True)
class KeyStat:
    """Track count for a Camelot harmonic key."""

    camelot_key: str
    track_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "camelot_key", require_str(self.camelot_key, "camelot_key")
        )
        cnt = require_int(self.track_count, "track_count")
        if cnt < 0:
            raise ValueError("track_count must be non-negative")
        object.__setattr__(self, "track_count", cnt)


@dataclass(frozen=True, slots=True)
class ArtistSummary:
    """Aggregated statistics and sample track for an artist in the catalog."""

    artist: str
    track_count: int
    embedded_count: int
    genres: tuple[str, ...]
    sources: tuple[str, ...]
    sample_track_id: str | None = None
    sample_track_title: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artist", require_str(self.artist, "artist"))
        track_cnt = require_int(self.track_count, "track_count")
        if track_cnt < 0:
            raise ValueError("track_count must be non-negative")
        object.__setattr__(self, "track_count", track_cnt)
        emb_cnt = require_int(self.embedded_count, "embedded_count")
        if emb_cnt < 0:
            raise ValueError("embedded_count must be non-negative")
        object.__setattr__(self, "embedded_count", emb_cnt)
        object.__setattr__(self, "genres", freeze_tuple(self.genres, "genres", str))
        object.__setattr__(self, "sources", freeze_tuple(self.sources, "sources", str))
        object.__setattr__(
            self,
            "sample_track_id",
            optional_str(self.sample_track_id, "sample_track_id"),
        )
        object.__setattr__(
            self,
            "sample_track_title",
            optional_str(self.sample_track_title, "sample_track_title"),
        )


@dataclass(frozen=True, slots=True)
class CatalogAnalytics:
    """High-level analytics and distributions across the full catalog."""

    total_tracks: int
    total_embedded: int
    total_artists: int
    total_local: int
    total_itunes: int
    genres: tuple[GenreStat, ...]
    bpm_buckets: tuple[BpmBucketStat, ...]
    sources: tuple[SourceStat, ...]
    top_keys: tuple[KeyStat, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "total_tracks",
            "total_embedded",
            "total_artists",
            "total_local",
            "total_itunes",
        ):
            val = require_int(getattr(self, field_name), field_name)
            if val < 0:
                raise ValueError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, val)

        object.__setattr__(
            self, "genres", freeze_tuple(self.genres, "genres", GenreStat)
        )
        object.__setattr__(
            self,
            "bpm_buckets",
            freeze_tuple(self.bpm_buckets, "bpm_buckets", BpmBucketStat),
        )
        object.__setattr__(
            self, "sources", freeze_tuple(self.sources, "sources", SourceStat)
        )
        object.__setattr__(
            self, "top_keys", freeze_tuple(self.top_keys, "top_keys", KeyStat)
        )
