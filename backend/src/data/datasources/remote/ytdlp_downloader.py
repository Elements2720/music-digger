"""DJ set acquisition through ``yt-dlp`` plus local-file passthrough.

Remote sources (YouTube, SoundCloud, Mixcloud, ...) are downloaded as
``bestaudio`` into the cache directory with metadata and (optionally) the top
comments extracted — comments are the tracklist goldmine for unreleased IDs.
Existing local audio files are returned in place without copying, so users
can analyze their own recordings. ``yt_dlp`` is imported lazily inside the
download path: importing this module must stay cheap and dependency-optional.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from domain.entities.dj_set import DownloadedSet
from domain.interfaces.audio_engine import ISetDownloader

from ...errors import SetDownloadError

LOGGER = logging.getLogger(__name__)

#: Extensions accepted as pre-existing local audio (returned without copying).
SUPPORTED_LOCAL_SUFFIXES = frozenset(
    {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".alac"}
)

#: Number of top comments requested from platforms that expose them.
MAX_COMMENTS = 100

#: Lower-cased marker yt-dlp emits when YouTube demands a sign-in.
BOT_CHECK_MARKER = "sign in to confirm"

#: Friendly pointer shown when the YouTube bot gate blocks a download.
COOKIE_HINT = (
    "YouTube is asking to 'Sign in to confirm you're not a bot'. Export a "
    "Netscape cookies.txt from a logged-in browser and set "
    "YTDLP_COOKIES_FILE=/path/to/cookies.txt (or YTDLP_COOKIES_FROM_BROWSER="
    "firefox|edge|chrome|brave) in .env — or pass --cookies / "
    "--cookies-from-browser to `dig analyze-set` for this run only."
)

FfprobeRunner = Callable[[Sequence[str]], str]
YdlFactory = Callable[[dict[str, Any]], Any]


def _default_ydl_factory(options: dict[str, Any]) -> Any:
    import yt_dlp

    return yt_dlp.YoutubeDL(options)


class YtDlpSetDownloader(ISetDownloader):
    """Resolve set URLs to cached audio files, or pass local files through."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        ffmpeg_bin: str = "ffmpeg",
        max_comments: int = MAX_COMMENTS,
        socket_timeout_seconds: float = 30.0,
        retries: int = 3,
        cookies_file: Path | None = None,
        cookies_from_browser: str | None = None,
        ydl_factory: YdlFactory | None = None,
        ffprobe_runner: FfprobeRunner | None = None,
    ) -> None:
        if max_comments < 0:
            raise ValueError("max_comments must not be negative")
        self._cache_dir = cache_dir
        self._ffmpeg_bin = ffmpeg_bin
        self._max_comments = max_comments
        self._socket_timeout = socket_timeout_seconds
        self._retries = retries
        self._cookies_file = cookies_file
        self._cookies_from_browser = cookies_from_browser
        self._ydl_factory = ydl_factory or _default_ydl_factory
        self._ffprobe_runner = ffprobe_runner or self._run_ffprobe

    # ------------------------------------------------------------------ API

    def apply_cookie_overrides(
        self,
        *,
        cookies_file: Path | None = None,
        cookies_from_browser: str | None = None,
    ) -> None:
        """Apply one-off CLI overrides; ``None`` keeps the configured value.

        The same preference rule as :meth:`_ydl_options` applies: an existing
        cookies file wins over the browser name.
        """
        if cookies_file is not None:
            self._cookies_file = cookies_file
        if cookies_from_browser is not None:
            self._cookies_from_browser = cookies_from_browser

    def set_cookie_overrides(
        self,
        *,
        cookies_file: Path | None,
        cookies_from_browser: str | None,
    ) -> None:
        """Replace both cookie settings unconditionally.

        The API uses this to scope per-job overrides on the shared downloader
        and to restore the configured defaults afterwards (``None`` clears).
        """
        self._cookies_file = cookies_file
        self._cookies_from_browser = cookies_from_browser

    async def download(self, url: str, destination: Path) -> Path:
        """Legacy seam: fetch ``url`` and return the audio file path."""
        downloaded = await self.fetch_set(url, destination.parent)
        return downloaded.audio_path

    async def fetch_set(
        self,
        source: str,
        destination_dir: Path,
        *,
        fetch_comments: bool = True,
    ) -> DownloadedSet:
        """Resolve a URL or local path to a :class:`DownloadedSet`."""
        local = self._as_local_file(source)
        if local is not None:
            duration = await asyncio.to_thread(self._probe_duration, local)
            return DownloadedSet(
                audio_path=local,
                title=local.stem,
                duration_seconds=duration,
                source_url=None,
                description="",
                comments=(),
                is_temporary=False,
            )
        return await self._download_remote(
            source, destination_dir, fetch_comments=fetch_comments
        )

    # ---------------------------------------------------------------- local

    @staticmethod
    def _as_local_file(source: str) -> Path | None:
        candidate = Path(source)
        if candidate.suffix.lower() not in SUPPORTED_LOCAL_SUFFIXES:
            return None
        if candidate.is_file():
            return candidate.resolve()
        return None

    def _probe_duration(self, path: Path) -> float | None:
        """Return the container duration via ffprobe, or ``None``."""
        try:
            output = self._ffprobe_runner(
                [
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ]
            )
        except (OSError, subprocess.SubprocessError) as exc:
            LOGGER.warning("ffprobe failed for %s: %s", path, exc)
            return None
        try:
            duration = float(output.strip())
        except ValueError:
            return None
        return duration if duration > 0 else None

    @staticmethod
    def _run_ffprobe(args: Sequence[str]) -> str:
        result = subprocess.run(
            ["ffprobe", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return result.stdout

    # --------------------------------------------------------------- remote

    def _ydl_options(
        self, destination_dir: Path, job_id: str, *, fetch_comments: bool
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": str(destination_dir / f"{job_id}.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": self._retries,
            "socket_timeout": self._socket_timeout,
            # Comments are only fetched when the caller wants them AND the
            # platform exposes them; yt-dlp ignores `getcomments` elsewhere.
            "getcomments": fetch_comments and self._max_comments > 0,
        }
        options.update(self._cookie_options())
        return options

    def _cookie_options(self) -> dict[str, Any]:
        """yt-dlp cookie auth; an existing file wins over the browser name."""
        if self._cookies_file is not None:
            if self._cookies_file.is_file():
                return {"cookiefile": str(self._cookies_file)}
            LOGGER.warning(
                "YTDLP_COOKIES_FILE points at a missing file: %s",
                self._cookies_file,
            )
        if self._cookies_from_browser:
            return {"cookiesfrombrowser": (self._cookies_from_browser,)}
        return {}

    @staticmethod
    def _job_id(source: str) -> str:
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    async def _download_remote(
        self,
        source: str,
        destination_dir: Path,
        *,
        fetch_comments: bool,
    ) -> DownloadedSet:
        if not source.lower().startswith(("http://", "https://")):
            raise SetDownloadError(
                f"source is neither an existing audio file nor an http(s) URL: "
                f"{source!r}"
            )
        destination_dir.mkdir(parents=True, exist_ok=True)
        job_id = self._job_id(source)
        options = self._ydl_options(
            destination_dir, job_id, fetch_comments=fetch_comments
        )

        def _run() -> dict[str, Any]:
            with self._ydl_factory(options) as ydl:
                info = ydl.extract_info(source, download=True)
                if info is None:
                    raise SetDownloadError(f"yt-dlp returned no info for {source!r}")
                if isinstance(info, Sequence) and not isinstance(info, str):
                    entries = [entry for entry in info if entry]
                    if not entries:
                        raise SetDownloadError(
                            f"playlist {source!r} contained no entries"
                        )
                    info = entries[0]
                return {
                    "info": info,
                    "path": Path(ydl.prepare_filename(info)),
                }

        try:
            result = await asyncio.to_thread(_run)
        except SetDownloadError:
            raise
        except Exception as exc:
            message = str(exc)
            if BOT_CHECK_MARKER in message.lower():
                raise SetDownloadError(
                    f"downloading {source!r} failed: {message}\n\n{COOKIE_HINT}"
                ) from exc
            raise SetDownloadError(f"downloading {source!r} failed: {exc}") from exc

        info: Mapping[str, Any] = result["info"]
        audio_path: Path = result["path"]
        if not audio_path.is_file():
            # Some extractors change the container/extension during merge.
            candidates = sorted(
                destination_dir.glob(f"{job_id}.*"),
                key=lambda candidate: candidate.stat().st_size,
                reverse=True,
            )
            if not candidates:
                raise SetDownloadError(
                    f"yt-dlp reported success but no file exists for {source!r}"
                )
            audio_path = candidates[0]

        return DownloadedSet(
            audio_path=audio_path,
            title=str(info.get("title") or audio_path.stem),
            artist=(info.get("artist") or info.get("uploader") or info.get("channel"))
            or None,
            duration_seconds=(
                float(info["duration"])
                if isinstance(info.get("duration"), (int, float))
                else None
            ),
            source_url=str(info.get("webpage_url") or source),
            thumbnail_url=(
                str(info.get("thumbnail")) if info.get("thumbnail") else None
            ),
            description=str(info.get("description") or ""),
            comments=self._top_comments(info),
            is_temporary=True,
        )

    def _top_comments(self, info: Mapping[str, Any]) -> tuple[str, ...]:
        raw = info.get("comments")
        if not isinstance(raw, list):
            return ()
        texts: list[tuple[int, str]] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            likes = item.get("like_count")
            score = likes if isinstance(likes, (int, float)) else 0
            texts.append((int(score), text))
        texts.sort(key=lambda pair: pair[0], reverse=True)
        return tuple(text for _, text in texts[: self._max_comments])


__all__ = [
    "BOT_CHECK_MARKER",
    "COOKIE_HINT",
    "MAX_COMMENTS",
    "SUPPORTED_LOCAL_SUFFIXES",
    "YtDlpSetDownloader",
]
