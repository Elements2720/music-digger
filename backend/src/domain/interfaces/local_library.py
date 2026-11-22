"""Local audio library scanner interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from ..entities.track import Track


class ILocalLibraryScanner(ABC):
    """Recursively scans local directories for audio files and extracts metadata."""

    @abstractmethod
    async def scan(
        self,
        folder_path: Path | str,
        *,
        recursive: bool = True,
        min_duration_seconds: float = 60.0,
        max_duration_seconds: float = 900.0,
    ) -> Sequence[Track]:
        """Scan folder for audio tracks within the given duration bounds."""
