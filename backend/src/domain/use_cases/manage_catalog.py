"""Use case: manage catalog contents, deletions, and blacklist entries.

All file references on disk are preserved; deletion removes rows from SQLite
and LanceDB only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .._validation import (
    normalize_artist_key,
    normalize_track_key,
    require_str,
)
from ..entities.analytics import ArtistSummary
from ..entities.track import BlacklistEntry, LikedArtist, SeedArtist
from ..interfaces.repositories import (
    IBlacklistRepository,
    ILikedArtistRepository,
    ISeedRepository,
    ITrackRepository,
)


@dataclass(frozen=True, slots=True)
class BulkDeleteArtistsResult:
    """Outcome of bulk deleting artists from the catalog."""

    artists_requested: int
    artists_deleted: int
    tracks_deleted: int
    seeds_removed: int
    blacklisted_count: int
    skipped_protected: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "artists_requested",
            "artists_deleted",
            "tracks_deleted",
            "seeds_removed",
            "blacklisted_count",
            "skipped_protected",
        ):
            val = getattr(self, field_name)
            if not isinstance(val, int) or val < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class BulkCleanupCriteria:
    """Rules for filtering catalog artists for bulk deletion."""

    max_taste_percent: float | None = None
    taste_mode: Literal["both", "local", "liked"] = "both"
    genre: str | None = None
    source: str | None = None
    protect_liked: bool = True
    protect_local: bool = True

    def __post_init__(self) -> None:
        has_taste = self.max_taste_percent is not None
        has_genre = self.genre is not None and bool(self.genre.strip())
        if not has_taste and not has_genre:
            raise ValueError(
                "At least one criteria (max_taste_percent or genre) must be provided"
            )
        if self.max_taste_percent is not None:
            val = float(self.max_taste_percent)
            if not (0.0 <= val <= 100.0):
                raise ValueError("max_taste_percent must be between 0.0 and 100.0")
            object.__setattr__(self, "max_taste_percent", val)

        if self.taste_mode not in ("both", "local", "liked"):
            raise ValueError(f"Invalid taste_mode: {self.taste_mode}")

        if self.genre is not None:
            clean_genre = self.genre.strip() or None
            object.__setattr__(self, "genre", clean_genre)

        if self.source is not None:
            clean_source = self.source.strip() or None
            object.__setattr__(self, "source", clean_source)

        object.__setattr__(self, "protect_liked", bool(self.protect_liked))
        object.__setattr__(self, "protect_local", bool(self.protect_local))


@dataclass(frozen=True, slots=True)
class BulkCleanupPreview:
    """Preview of artists that would be deleted by bulk cleanup criteria."""

    artist_count: int
    track_count: int
    sample_artists: tuple[ArtistSummary, ...]
    skipped_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.artist_count, int) or self.artist_count < 0:
            raise ValueError("artist_count must be a non-negative integer")
        if not isinstance(self.track_count, int) or self.track_count < 0:
            raise ValueError("track_count must be a non-negative integer")
        if not isinstance(self.skipped_count, int) or self.skipped_count < 0:
            raise ValueError("skipped_count must be a non-negative integer")
        object.__setattr__(self, "sample_artists", tuple(self.sample_artists))


@dataclass(frozen=True, slots=True)
class DeleteTrackResult:
    """Outcome of deleting a single track."""

    track_id: str
    deleted: bool
    blacklisted: bool


@dataclass(frozen=True, slots=True)
class DeleteArtistResult:
    """Outcome of deleting an artist and their tracks from the catalog."""

    artist_name: str
    tracks_deleted: int
    seed_removed: bool
    blacklisted: bool


class ManageCatalog:
    """Orchestrate safe catalog track/artist deletion and blacklist lifecycle."""

    def __init__(
        self,
        *,
        track_repository: ITrackRepository,
        seed_repository: ISeedRepository,
        blacklist_repository: IBlacklistRepository,
        liked_artist_repository: ILikedArtistRepository | None = None,
    ) -> None:
        self._track_repository = track_repository
        self._seed_repository = seed_repository
        self._blacklist_repository = blacklist_repository
        self._liked_artist_repository = liked_artist_repository

    async def like_artist(self, artist_name: str) -> LikedArtist:
        clean = require_str(artist_name, "artist_name").strip()
        blocked = await self._blacklist_repository.get_blocked_artist_keys()
        if normalize_artist_key(clean) in blocked:
            raise ValueError(
                f"Cannot like blacklisted artist '{clean}'. Unblock first."
            )
        if self._liked_artist_repository is None:
            raise RuntimeError("LikedArtistRepository not configured")
        liked = await self._liked_artist_repository.like(clean)
        # Bump in seed_artists with priority_score=1.0, category="electronic", source="liked-artist"
        await self._seed_repository.record_discovery(
            [SeedArtist(clean, 1.0, "electronic", source="liked-artist")],
            priority_increment=0.5,
        )
        return liked

    async def unlike_artist(self, artist_name: str) -> bool:
        clean = require_str(artist_name, "artist_name").strip()
        if self._liked_artist_repository is None:
            return False
        return await self._liked_artist_repository.unlike(clean)

    async def delete_track(
        self,
        track_id: str,
        *,
        blacklist: bool = False,
        reason: str | None = None,
    ) -> DeleteTrackResult:
        """Delete a track by id and optionally blacklist it.

        Never touches user audio files on disk (only DB rows).
        """
        clean_id = require_str(track_id, "track_id")
        track = await self._track_repository.get_by_id(clean_id)
        if track is None:
            return DeleteTrackResult(
                track_id=clean_id, deleted=False, blacklisted=False
            )

        if blacklist:
            norm_key = normalize_track_key(track.artist, track.title)
            display_name = f"{track.artist} - {track.title}"
            entry = BlacklistEntry(
                id=None,
                kind="track",
                normalized_key=norm_key,
                display_name=display_name,
                artist_name=track.artist,
                track_title=track.title,
                reason=reason,
            )
            await self._blacklist_repository.add(entry)

        deleted_count = await self._track_repository.delete_by_ids([clean_id])
        return DeleteTrackResult(
            track_id=clean_id,
            deleted=deleted_count > 0,
            blacklisted=blacklist,
        )

    async def delete_artist(
        self,
        artist_name: str,
        *,
        blacklist: bool = False,
        reason: str | None = None,
    ) -> DeleteArtistResult:
        """Delete all tracks and seeds for an artist, optionally blacklisting them."""
        clean_artist = require_str(artist_name, "artist_name")
        if blacklist:
            norm_key = normalize_artist_key(clean_artist)
            entry = BlacklistEntry(
                id=None,
                kind="artist",
                normalized_key=norm_key,
                display_name=clean_artist,
                artist_name=clean_artist,
                reason=reason,
            )
            await self._blacklist_repository.add(entry)

        tracks_deleted, _ = await self._track_repository.delete_by_artist(clean_artist)
        seed_removed = await self._seed_repository.delete_by_name(clean_artist)
        return DeleteArtistResult(
            artist_name=clean_artist,
            tracks_deleted=tracks_deleted,
            seed_removed=seed_removed,
            blacklisted=blacklist,
        )

    async def bulk_delete_artists(
        self,
        artist_names: Sequence[str],
        *,
        blacklist: bool = False,
        reason: str | None = None,
        protect_liked: bool = False,
        protect_local: bool = False,
    ) -> BulkDeleteArtistsResult:
        """Bulk delete multiple artists, their tracks and seeds.

        Never touches user audio files on disk (only DB rows).
        """
        seen: dict[str, str] = {}
        for name in artist_names:
            if not name or not isinstance(name, str):
                continue
            clean = name.strip()
            if not clean:
                continue
            norm_k = normalize_artist_key(clean)
            if norm_k not in seen:
                seen[norm_k] = clean

        if not seen:
            return BulkDeleteArtistsResult(
                artists_requested=0,
                artists_deleted=0,
                tracks_deleted=0,
                seeds_removed=0,
                blacklisted_count=0,
                skipped_protected=0,
            )

        liked_keys: frozenset[str] = frozenset()
        if protect_liked and self._liked_artist_repository is not None:
            liked_keys = await self._liked_artist_repository.get_liked_keys()

        local_keys: frozenset[str] = frozenset()
        if protect_local:
            local_keys = await self._track_repository.get_artists_with_local_tracks()

        to_delete: list[str] = []
        skipped_protected = 0

        for norm_k, original_name in seen.items():
            if protect_liked and norm_k in liked_keys:
                skipped_protected += 1
                continue
            if protect_local and norm_k in local_keys:
                skipped_protected += 1
                continue
            to_delete.append(original_name)

        if not to_delete:
            return BulkDeleteArtistsResult(
                artists_requested=len(seen),
                artists_deleted=0,
                tracks_deleted=0,
                seeds_removed=0,
                blacklisted_count=0,
                skipped_protected=skipped_protected,
            )

        tracks_deleted, _ = await self._track_repository.delete_by_artists(to_delete)
        seeds_removed = await self._seed_repository.delete_by_names(to_delete)

        blacklisted_count = 0
        if blacklist:
            for artist in to_delete:
                norm_key = normalize_artist_key(artist)
                entry = BlacklistEntry(
                    id=None,
                    kind="artist",
                    normalized_key=norm_key,
                    display_name=artist,
                    artist_name=artist,
                    reason=reason,
                )
                await self._blacklist_repository.add(entry)
                blacklisted_count += 1

        if not protect_liked and self._liked_artist_repository is not None:
            for artist in to_delete:
                await self._liked_artist_repository.unlike(artist)

        return BulkDeleteArtistsResult(
            artists_requested=len(seen),
            artists_deleted=len(to_delete),
            tracks_deleted=tracks_deleted,
            seeds_removed=seeds_removed,
            blacklisted_count=blacklisted_count,
            skipped_protected=skipped_protected,
        )

    async def _resolve_cleanup_matches(
        self, criteria: BulkCleanupCriteria
    ) -> tuple[list[ArtistSummary], int]:
        """Return (matched_artists, total_in_scope_artists)."""
        liked_keys: frozenset[str] = frozenset()
        if self._liked_artist_repository is not None:
            liked_keys = await self._liked_artist_repository.get_liked_keys()

        if criteria.max_taste_percent is not None:
            taste_scores, _ = await self._track_repository.get_artist_taste_scores(
                mode=criteria.taste_mode, liked_artist_keys=liked_keys
            )
            candidates = [
                name
                for name, pct in taste_scores.items()
                if pct < criteria.max_taste_percent
            ]
            (
                summaries,
                in_scope,
            ) = await self._track_repository.list_artists_summary_by_names(
                candidates,
                genre=criteria.genre,
                source=criteria.source,
                taste_scores=taste_scores,
                liked_artist_keys=liked_keys,
            )
        else:
            summaries, in_scope = await self._track_repository.list_artists_summary(
                genre=criteria.genre,
                source=criteria.source,
                taste_mode=criteria.taste_mode,
                liked_artist_keys=liked_keys,
                sort="tracks_desc",
                limit=100_000,
                offset=0,
            )

        matched: list[ArtistSummary] = []
        for artist in summaries:
            if criteria.max_taste_percent is not None and (
                artist.taste_match_percent is None
                or artist.taste_match_percent >= criteria.max_taste_percent
            ):
                continue
            if criteria.protect_liked and (
                artist.is_liked or normalize_artist_key(artist.artist) in liked_keys
            ):
                continue
            if criteria.protect_local and "local" in artist.sources:
                continue
            matched.append(artist)

        return matched, in_scope

    async def preview_bulk_cleanup(
        self, criteria: BulkCleanupCriteria, *, sample_limit: int = 25
    ) -> BulkCleanupPreview:
        """Preview artists matching cleanup criteria without deleting anything."""
        matched, in_scope = await self._resolve_cleanup_matches(criteria)
        return BulkCleanupPreview(
            artist_count=len(matched),
            track_count=sum(a.track_count for a in matched),
            sample_artists=tuple(matched[:sample_limit]),
            skipped_count=max(in_scope - len(matched), 0),
        )

    async def execute_bulk_cleanup(
        self,
        criteria: BulkCleanupCriteria,
        *,
        blacklist: bool = True,
        reason: str | None = None,
    ) -> BulkDeleteArtistsResult:
        """Execute bulk cleanup for artists matching criteria."""
        matched, _ = await self._resolve_cleanup_matches(criteria)
        if not matched:
            return BulkDeleteArtistsResult(
                artists_requested=0,
                artists_deleted=0,
                tracks_deleted=0,
                seeds_removed=0,
                blacklisted_count=0,
                skipped_protected=0,
            )

        if not reason or not reason.strip():
            parts: list[str] = []
            if criteria.max_taste_percent is not None:
                parts.append(f"Taste < {criteria.max_taste_percent:.0f}%")
            if criteria.genre:
                parts.append(f"Genre: {criteria.genre}")
            reason = f"Bulk cleanup: {', '.join(parts)}"

        return await self.bulk_delete_artists(
            [a.artist for a in matched],
            blacklist=blacklist,
            reason=reason,
            protect_liked=criteria.protect_liked,
            protect_local=criteria.protect_local,
        )

    async def add_blacklist_artist(
        self,
        artist_name: str,
        *,
        reason: str | None = None,
    ) -> BlacklistEntry:
        """Directly add an artist to the blacklist."""
        clean_artist = require_str(artist_name, "artist_name")
        norm_key = normalize_artist_key(clean_artist)
        entry = BlacklistEntry(
            id=None,
            kind="artist",
            normalized_key=norm_key,
            display_name=clean_artist,
            artist_name=clean_artist,
            reason=reason,
        )
        return await self._blacklist_repository.add(entry)

    async def add_blacklist_track(
        self,
        artist: str,
        title: str,
        *,
        reason: str | None = None,
    ) -> BlacklistEntry:
        """Directly add a track to the blacklist."""
        clean_artist = require_str(artist, "artist")
        clean_title = require_str(title, "title")
        norm_key = normalize_track_key(clean_artist, clean_title)
        display_name = f"{clean_artist} - {clean_title}"
        entry = BlacklistEntry(
            id=None,
            kind="track",
            normalized_key=norm_key,
            display_name=display_name,
            artist_name=clean_artist,
            track_title=clean_title,
            reason=reason,
        )
        return await self._blacklist_repository.add(entry)

    async def remove_blacklist_entry(self, entry_id: int) -> bool:
        """Remove an entry from the blacklist by ID."""
        return await self._blacklist_repository.remove(entry_id)

    async def list_blacklist(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BlacklistEntry]:
        """List blacklist entries with optional filters."""
        return await self._blacklist_repository.list_all(
            kind=kind,
            query=query,
            limit=limit,
            offset=offset,
        )

    async def count_blacklist(self, *, kind: str | None = None) -> int:
        """Return the count of blacklist entries."""
        return await self._blacklist_repository.count(kind=kind)
