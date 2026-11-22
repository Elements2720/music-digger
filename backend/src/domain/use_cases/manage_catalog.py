"""Use case: manage catalog contents, deletions, and blacklist entries.

All file references on disk are preserved; deletion removes rows from SQLite
and LanceDB only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .._validation import (
    normalize_artist_key,
    normalize_track_key,
    require_str,
)
from ..entities.track import BlacklistEntry
from ..interfaces.repositories import (
    IBlacklistRepository,
    ISeedRepository,
    ITrackRepository,
)


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
    ) -> None:
        self._track_repository = track_repository
        self._seed_repository = seed_repository
        self._blacklist_repository = blacklist_repository

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
