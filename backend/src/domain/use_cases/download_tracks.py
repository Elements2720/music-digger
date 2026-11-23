"""Use case for downloading full track audio files and updating local catalog records."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .._validation import require_int, require_str
from ..interfaces.downloader import ITrackDownloader, TrackDownloadResult
from ..interfaces.repositories import ITrackRepository


@dataclass(frozen=True, slots=True)
class BatchDownloadProgress:
    """Progress snapshot emitted during batch downloads."""

    processed: int
    total: int
    downloaded: int
    skipped: int
    failed: int
    current_track: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "processed", require_int(self.processed, "processed"))
        object.__setattr__(self, "total", require_int(self.total, "total"))
        object.__setattr__(
            self, "downloaded", require_int(self.downloaded, "downloaded")
        )
        object.__setattr__(self, "skipped", require_int(self.skipped, "skipped"))
        object.__setattr__(self, "failed", require_int(self.failed, "failed"))
        object.__setattr__(
            self, "current_track", require_str(self.current_track, "current_track")
        )


@dataclass(frozen=True, slots=True)
class BatchDownloadResult:
    """Final result of a batch track download run."""

    total: int
    downloaded: int
    skipped: int
    failed: int
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "total", require_int(self.total, "total"))
        object.__setattr__(
            self, "downloaded", require_int(self.downloaded, "downloaded")
        )
        object.__setattr__(self, "skipped", require_int(self.skipped, "skipped"))
        object.__setattr__(self, "failed", require_int(self.failed, "failed"))
        if not isinstance(self.errors, tuple):
            object.__setattr__(self, "errors", tuple(self.errors))


class DownloadTracks:
    """Orchestrates single-track and batch track downloads."""

    def __init__(
        self,
        track_repository: ITrackRepository,
        downloader: ITrackDownloader,
        output_dir: str,
    ) -> None:
        self._track_repository = track_repository
        self._downloader = downloader
        self._output_dir = output_dir

    async def download_one(
        self,
        track_id: str,
        *,
        force: bool = False,
    ) -> TrackDownloadResult:
        """Download a single track by id and persist its local_path."""
        track = await self._track_repository.get_by_id(track_id)
        if track is None:
            raise ValueError(f"Track not found: {track_id}")

        if not force and track.local_path:
            return TrackDownloadResult(
                track_id=track.id,
                file_path=track.local_path,
                format="m4a",
            )

        result = await self._downloader.download_track(track, self._output_dir)
        updated_track = track.with_local_path(result.file_path)
        await self._track_repository.upsert_many([updated_track])
        return result

    async def download_many(
        self,
        track_ids: Sequence[str],
        *,
        skip_existing: bool = True,
        progress: Callable[[BatchDownloadProgress], None] | None = None,
    ) -> BatchDownloadResult:
        """Download multiple tracks sequentially, persisting local_path on the fly."""
        deduped: list[str] = []
        seen: set[str] = set()
        for tid in track_ids:
            if tid not in seen:
                seen.add(tid)
                deduped.append(tid)

        total = len(deduped)
        downloaded = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        for idx, track_id in enumerate(deduped):
            track_label = track_id
            try:
                track = await self._track_repository.get_by_id(track_id)
                if track is None:
                    raise ValueError(f"Track not found: {track_id}")
                track_label = track.display_name

                if skip_existing and track.local_path:
                    skipped += 1
                else:
                    result = await self._downloader.download_track(
                        track, self._output_dir
                    )
                    updated_track = track.with_local_path(result.file_path)
                    await self._track_repository.upsert_many([updated_track])
                    downloaded += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                errors.append(f"{track_label}: {exc}")

            if progress is not None:
                progress(
                    BatchDownloadProgress(
                        processed=idx + 1,
                        total=total,
                        downloaded=downloaded,
                        skipped=skipped,
                        failed=failed,
                        current_track=track_label,
                    )
                )

        return BatchDownloadResult(
            total=total,
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            errors=tuple(errors),
        )
