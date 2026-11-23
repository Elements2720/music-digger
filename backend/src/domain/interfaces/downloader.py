"""Domain interface for downloading full tracks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .._validation import require_str
from ..entities.track import Track


@dataclass(frozen=True, slots=True)
class TrackDownloadResult:
    """Result of downloading a single track to local storage."""

    track_id: str
    file_path: str
    format: str = "m4a"

    def __post_init__(self) -> None:
        object.__setattr__(self, "track_id", require_str(self.track_id, "track_id"))
        object.__setattr__(self, "file_path", require_str(self.file_path, "file_path"))
        object.__setattr__(self, "format", require_str(self.format, "format"))


class ITrackDownloader(ABC):
    """Port for downloading a full-length track file to disk."""

    @abstractmethod
    async def download_track(
        self,
        track: Track,
        output_dir: str,
    ) -> TrackDownloadResult:
        """Download and remux ``track`` into ``output_dir``."""
