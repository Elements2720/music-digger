"""Local folder audio scanner using ffprobe."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from domain.entities.track import Track
from domain.interfaces.local_library import ILocalLibraryScanner

LOGGER = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".flac", ".wav", ".m4a", ".aiff", ".ogg"}
)

FfprobeRunner = Callable[[Sequence[str]], str]
_YEAR_REGEX = re.compile(r"\b(19\d\d|20\d\d)\b")


def _default_ffprobe_runner(args: Sequence[str]) -> str:
    result = subprocess.run(
        ["ffprobe", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return result.stdout


class LocalLibraryScanner(ILocalLibraryScanner):
    """Scan local directory trees for audio tracks and read tags via ffprobe."""

    def __init__(
        self,
        *,
        ffprobe_runner: FfprobeRunner | None = None,
    ) -> None:
        self._runner = ffprobe_runner or _default_ffprobe_runner

    async def scan(
        self,
        folder_path: Path | str,
        *,
        recursive: bool = True,
        min_duration_seconds: float = 60.0,
        max_duration_seconds: float = 900.0,
    ) -> Sequence[Track]:
        """Scan folder for audio tracks within duration bounds."""
        root = Path(folder_path).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Directory not found: {root}")

        if min_duration_seconds < 0:
            raise ValueError("min_duration_seconds must not be negative")
        if max_duration_seconds < min_duration_seconds:
            raise ValueError("max_duration_seconds must be >= min_duration_seconds")

        iterator = root.rglob("*") if recursive else root.glob("*")
        audio_files = sorted(
            p
            for p in iterator
            if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        )

        tracks: list[Track] = []
        for file_path in audio_files:
            track = self._probe_file(
                file_path,
                min_duration=min_duration_seconds,
                max_duration=max_duration_seconds,
            )
            if track is not None:
                tracks.append(track)

        return tuple(tracks)

    def _probe_file(
        self,
        file_path: Path,
        *,
        min_duration: float,
        max_duration: float,
    ) -> Track | None:
        resolved_path = file_path.resolve()
        args = [
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(resolved_path),
        ]
        try:
            output = self._runner(args)
            data: dict[str, Any] = json.loads(output)
        except Exception as exc:  # noqa: BLE001 - one corrupt file should not abort scan
            LOGGER.warning("ffprobe failed on %s: %s", resolved_path, exc)
            return None

        format_info = data.get("format", {})
        try:
            duration = float(format_info.get("duration", 0.0))
        except (ValueError, TypeError):
            LOGGER.warning("Could not parse duration for %s", resolved_path)
            return None

        if duration < min_duration or duration > max_duration:
            LOGGER.debug(
                "Skipping %s with duration %.1fs (allowed [%.1f, %.1f])",
                resolved_path,
                duration,
                min_duration,
                max_duration,
            )
            return None

        tags: dict[str, Any] = {
            k.lower(): v for k, v in format_info.get("tags", {}).items()
        }

        # Filename fallback
        stem = resolved_path.stem
        fallback_artist = "Unknown Artist"
        fallback_title = stem

        if " - " in stem:
            parts = [part.strip() for part in stem.split(" - ") if part.strip()]
            if len(parts) == 2:
                fallback_artist, fallback_title = parts[0], parts[1]
            elif len(parts) >= 3 and parts[0].isdigit():
                fallback_artist, fallback_title = parts[1], " - ".join(parts[2:])
            elif len(parts) >= 3:
                fallback_artist, fallback_title = parts[0], " - ".join(parts[1:])

        artist = (tags.get("artist") or fallback_artist).strip()
        title = (tags.get("title") or fallback_title).strip()
        album = (tags.get("album") or "").strip() or None
        genre = (tags.get("genre") or "").strip() or None

        date_val = tags.get("date") or tags.get("year")
        release_year: int | None = None
        if date_val:
            match = _YEAR_REGEX.search(str(date_val))
            if match:
                release_year = int(match.group(1))

        # Track ID deterministic from resolved local path
        path_str = str(resolved_path)
        sha1 = hashlib.sha1(path_str.encode("utf-8")).hexdigest()[:12]
        track_id = f"local:{sha1}"

        return Track(
            id=track_id,
            title=title or fallback_title,
            artist=artist or fallback_artist,
            duration_seconds=duration,
            album=album,
            genre=genre,
            release_year=release_year,
            source="local",
            local_path=path_str,
        )


__all__ = ["SUPPORTED_AUDIO_EXTENSIONS", "LocalLibraryScanner"]
