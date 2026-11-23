"""Playwright browser + local ffmpeg track downloader adapter using am-dl.pages.dev."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

import httpx

from domain.entities.track import Track
from domain.interfaces.downloader import ITrackDownloader, TrackDownloadResult

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Playwright

LOGGER = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS: Final[re.Pattern[str]] = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_FONT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r".*\.(woff2?|ttf|otf|eot)(\?.*)?$", re.IGNORECASE
)
_ANALYTICS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r".*(cloudflareinsights|google-analytics|clarity|doubleclick).*", re.IGNORECASE
)


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use in Windows and Unix file paths."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip(". ")
    return cleaned if cleaned else "unnamed"


class AmdlHttpTrackDownloader(ITrackDownloader):
    """Resource-safe Playwright browser + ffmpeg downloader for full-length tracks.

    Runs browser-side audio assembly inside headless Chromium with:
    - Single concurrency lock (asyncio.Semaphore(1))
    - Persistent browser profile/cache (ffmpeg-core loads once)
    - 120s idle auto-shutdown to free all browser RAM
    - Strict duration sanity guard ensuring full-length audio
    """

    def __init__(
        self,
        base_url: str = "https://am-dl.pages.dev",
        timeout_seconds: float = 60.0,
        ffmpeg_binary: str = "ffmpeg",
        ffprobe_binary: str = "ffprobe",
        http_client: httpx.AsyncClient | None = None,
        playwright_storage_dir: Path | str | None = None,
        playwright_idle_timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._ffmpeg_binary = ffmpeg_binary
        self._ffprobe_binary = ffprobe_binary
        self._http_client = http_client
        self._playwright_storage_dir = (
            Path(playwright_storage_dir).resolve()
            if playwright_storage_dir
            else Path("storage/playwright_amdl").resolve()
        )
        self._playwright_idle_timeout = playwright_idle_timeout

        self._semaphore = asyncio.Semaphore(1)
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._idle_task: asyncio.Task[None] | None = None

    def _build_target_url(self, track: Track) -> str:
        """Derive the Apple Music song URL for single-track lookup."""
        if track.store_url and "music.apple.com" in track.store_url:
            return track.store_url

        if track.external_id:
            clean_id = re.sub(r"\D", "", track.external_id)
            if clean_id:
                return f"https://music.apple.com/us/song/{clean_id}"

        raise ValueError(
            f"Track {track.id} has no usable store_url or iTunes track ID for downloading"
        )

    async def _ensure_context(self) -> BrowserContext:
        """Initialize or reuse persistent Playwright context with route filtering."""
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            self._idle_task = None

        if self._playwright is None:
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
            except ImportError as exc:
                raise RuntimeError(
                    "Playwright is required for full-length track downloads. "
                    "Install with 'uv add playwright' and run 'playwright install chromium'."
                ) from exc

        if self._context is None:
            self._playwright_storage_dir.mkdir(parents=True, exist_ok=True)
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._playwright_storage_dir),
                headless=True,
                accept_downloads=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            # Filter non-essential routes (fonts, analytics) to minimize network & CPU
            await self._context.route(
                _FONT_PATTERN,
                lambda route: route.abort(),
            )
            await self._context.route(
                _ANALYTICS_PATTERN,
                lambda route: route.abort(),
            )

        return self._context

    def _schedule_idle_shutdown(self) -> None:
        """Schedule closing of the background browser after idle timeout."""
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()

        async def _idle_worker() -> None:
            try:
                await asyncio.sleep(self._playwright_idle_timeout)
                LOGGER.info(
                    "Closing idle Playwright Chromium context after %.0fs of inactivity",
                    self._playwright_idle_timeout,
                )
                await self.close()
            except asyncio.CancelledError:
                pass

        self._idle_task = asyncio.create_task(_idle_worker())

    async def close(self) -> None:
        """Close browser context and stop Playwright cleanly."""
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            self._idle_task = None

        if self._context is not None:
            try:
                await self._context.close()
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Error closing browser context: %s", exc)
            self._context = None

        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Error stopping Playwright: %s", exc)
            self._playwright = None

    async def _download_via_browser(
        self,
        target_url: str,
        output_path: Path,
    ) -> None:
        """Run headless Chromium to let am-dl.pages.dev assemble the full track."""
        async with self._semaphore:
            context = await self._ensure_context()
            page = await context.new_page()
            try:
                await page.goto(
                    self._base_url,
                    wait_until="networkidle",
                    timeout=int(self._timeout_seconds * 1000),
                )
                # Wait for fetch button to activate
                await page.wait_for_selector(
                    "#fetch-button:not([disabled])",
                    timeout=15000,
                )
                await page.fill("#urlInput", target_url)

                async with page.expect_download(
                    timeout=int(self._timeout_seconds * 1000)
                ) as download_info:
                    await page.click("#fetch-button")

                download = await download_info.value
                await download.save_as(str(output_path))
            finally:
                with contextlib.suppress(Exception):
                    await page.close()
                self._schedule_idle_shutdown()

    async def _verify_audio_file(self, file_path: Path, track: Track) -> float:
        """Verify audio file exists, decodes cleanly, and satisfies duration sanity."""
        if not file_path.exists() or file_path.stat().st_size == 0:
            file_path.unlink(missing_ok=True)
            raise RuntimeError(f"Output audio file {file_path} is empty or missing")

        # 1. ffprobe duration
        ffprobe_cmd = [
            self._ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        probe_proc = await asyncio.create_subprocess_exec(
            *ffprobe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        probe_out, probe_err = await asyncio.wait_for(
            probe_proc.communicate(),
            timeout=10.0,
        )
        if probe_proc.returncode != 0:
            file_path.unlink(missing_ok=True)
            err_msg = probe_err.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"ffprobe failed (code {probe_proc.returncode}) for {track.display_name}: {err_msg}"
            )

        raw_dur = probe_out.decode("utf-8", errors="replace").strip()
        try:
            duration = float(raw_dur)
        except ValueError as exc:
            file_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Could not parse duration from ffprobe ({raw_dur!r}) for {track.display_name}"
            ) from exc

        # 2. ffmpeg decode check
        decode_cmd = [
            self._ffmpeg_binary,
            "-v",
            "error",
            "-i",
            str(file_path),
            "-t",
            "5",
            "-f",
            "null",
            "-",
        ]
        dec_proc = await asyncio.create_subprocess_exec(
            *decode_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, dec_err = await asyncio.wait_for(
            dec_proc.communicate(),
            timeout=10.0,
        )
        if dec_proc.returncode != 0:
            file_path.unlink(missing_ok=True)
            err_msg = dec_err.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Audio file failed decode check for {track.display_name}: {err_msg[-300:]}"
            )

        # 3. Guard against short preview clips being saved for full tracks
        if track.duration_seconds is not None and track.duration_seconds >= 150.0:
            min_expected = track.duration_seconds * 0.65
            if duration < min_expected:
                file_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Downloaded audio duration ({duration:.1f}s) is less than 65% of catalog track duration "
                    f"({track.duration_seconds:.1f}s) for {track.display_name} (possible preview clip)"
                )

        return duration

    async def download_track(
        self,
        track: Track,
        output_dir: str,
    ) -> TrackDownloadResult:
        """Download full-length audio and remux into ``output_dir`` as an .m4a file."""
        target_url = self._build_target_url(track)
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_artist = sanitize_filename(track.artist)
        safe_title = sanitize_filename(track.title)
        dest_file = out_dir / f"{safe_artist} - {safe_title}.m4a"

        temp_fd, temp_raw_str = tempfile.mkstemp(suffix=".m4a", prefix="amdl_raw_")
        os.close(temp_fd)
        temp_raw = Path(temp_raw_str)

        try:
            # 1. Download via resource-safe Playwright browser engine
            await self._download_via_browser(target_url, temp_raw)

            # 2. Remux with faststart and inject any missing domain tags (BPM, initialKey)
            ffmpeg_cmd = [
                self._ffmpeg_binary,
                "-y",
                "-i",
                str(temp_raw),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
            ]
            if track.bpm is not None:
                ffmpeg_cmd.extend(["-metadata", f"BPM={track.bpm.value:.1f}"])
            if track.key is not None:
                key_notation = (
                    track.key.notation
                    if hasattr(track.key, "notation")
                    else str(track.key)
                )
                ffmpeg_cmd.extend(["-metadata", f"initialKey={key_notation}"])

            ffmpeg_cmd.append(str(dest_file))

            ff_proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, ff_stderr = await asyncio.wait_for(
                ff_proc.communicate(),
                timeout=60.0,
            )
            if ff_proc.returncode != 0:
                err_text = ff_stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    f"FFmpeg post-processing failed (code {ff_proc.returncode}) for {track.display_name}: {err_text[-300:]}"
                )

            # 3. Duration sanity guard & decode verification
            await self._verify_audio_file(dest_file, track)

        finally:
            if temp_raw.exists():
                with contextlib.suppress(Exception):
                    temp_raw.unlink(missing_ok=True)

        return TrackDownloadResult(
            track_id=track.id,
            file_path=str(dest_file.resolve()),
            format="m4a",
        )
