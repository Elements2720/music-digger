"""In-memory audio decoding through an ``ffmpeg`` subprocess.

30-second previews are downloaded straight into RAM (``httpx``) and piped via
stdin/stdout into ``ffmpeg`` — nothing is ever written to disk. The decoder
bounds its own download/decode concurrency with a semaphore so the indexing
pipeline never holds more previews in memory than configured.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import BinaryIO

import httpx

from domain.entities.track import AudioBuffer
from domain.interfaces.audio_engine import IAudioDecoder
from domain.value_objects.audio_features import TimeRange

from ..errors import AudioDecodeError, FFmpegNotFoundError, PreviewDownloadError

LOGGER = logging.getLogger(__name__)

FFmpegRunner = Callable[[str, Sequence[str], bytes], Awaitable[bytes]]
SleepFn = Callable[[float], Awaitable[None]]

_DEFAULT_SAMPLE_RATE = 48_000
_DEFAULT_CHANNELS = 1
_MAX_PAYLOAD_BYTES = 33_554_432  # 32 MiB is plenty for a 30 s preview


class FFmpegAudioDecoder(IAudioDecoder):
    """HTTP preview downloader plus stdin/stdout FFmpeg pipe decoder."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        ffmpeg_bin: str = "ffmpeg",
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        channels: int = _DEFAULT_CHANNELS,
        download_concurrency: int = 16,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        ffmpeg_timeout_seconds: float = 60.0,
        max_payload_bytes: int = _MAX_PAYLOAD_BYTES,
        process_runner: FFmpegRunner | None = None,
        sleep: SleepFn | None = None,
    ) -> None:
        if download_concurrency < 1:
            raise ValueError("download_concurrency must be at least 1")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if sample_rate < 1 or channels < 1:
            raise ValueError("sample_rate and channels must be positive")
        self._http = http_client
        self._ffmpeg_bin = ffmpeg_bin
        self._sample_rate = sample_rate
        self._channels = channels
        self._download_concurrency = download_concurrency
        self._semaphore = asyncio.Semaphore(download_concurrency)
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._ffmpeg_timeout = ffmpeg_timeout_seconds
        self._max_payload_bytes = max_payload_bytes
        self._runner: FFmpegRunner = process_runner or self._run_ffmpeg
        self._sleep: SleepFn = sleep or asyncio.sleep

    # ------------------------------------------------------------- properties

    @property
    def download_concurrency(self) -> int:
        """Current bound on simultaneous preview downloads/decodes."""
        return self._download_concurrency

    def set_concurrency(self, concurrency: int) -> None:
        """Replace the download/decode semaphore (turbo mode).

        In-flight downloads keep their old slots; queued work immediately uses
        the new bound. The previous semaphore is simply dropped.
        """
        if not isinstance(concurrency, int) or isinstance(concurrency, bool):
            raise TypeError("concurrency must be an int")
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._download_concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)

    # ------------------------------------------------------------------ decode

    async def _invoke_runner(self, args: Sequence[str], payload: bytes) -> bytes:
        """Run ffmpeg through the injectable runner with uniform error mapping.

        ``FileNotFoundError`` means the binary vanished from PATH (or was never
        there); every caller must surface it as ``FFmpegNotFoundError``.
        """
        try:
            return await self._runner(self._ffmpeg_bin, args, payload)
        except FileNotFoundError as exc:
            raise FFmpegNotFoundError(
                f"ffmpeg binary not found ({self._ffmpeg_bin!r}); install FFmpeg "
                "and make sure it is on PATH"
            ) from exc

    async def decode(
        self,
        source: BinaryIO,
        *,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        channels: int = _DEFAULT_CHANNELS,
    ) -> AudioBuffer:
        """Decode a compressed payload already held in memory."""
        payload = source.read()
        pcm = await self._invoke_runner(
            self._pipe_args(sample_rate, channels),
            payload,
        )
        return self._build_buffer(pcm, sample_rate)

    async def decode_url(
        self,
        url: str,
        *,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        channels: int = _DEFAULT_CHANNELS,
    ) -> AudioBuffer:
        """Download ``url`` into memory and decode it without touching disk."""
        async with self._semaphore:
            payload = await self._download(url)
            pcm = await self._invoke_runner(
                self._pipe_args(sample_rate, channels),
                payload,
            )
        return self._build_buffer(pcm, sample_rate)

    async def decode_segment(
        self,
        path: Path,
        time_range: TimeRange,
        *,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        channels: int = _DEFAULT_CHANNELS,
    ) -> AudioBuffer:
        """Decode only ``time_range`` from a file, using FFmpeg seek flags."""
        args = [
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{time_range.start_seconds:.3f}",
            "-i",
            str(path),
            "-t",
            f"{time_range.duration_seconds:.3f}",
            *self._output_args(sample_rate, channels),
        ]
        pcm = await self._invoke_runner(args, b"")
        return self._build_buffer(pcm, sample_rate)

    @staticmethod
    def _pipe_args(sample_rate: int, channels: int) -> list[str]:
        return [
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-vn",
            *FFmpegAudioDecoder._output_args(sample_rate, channels),
        ]

    @staticmethod
    def _output_args(sample_rate: int, channels: int) -> list[str]:
        return [
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "pipe:1",
        ]

    # ---------------------------------------------------------------- download

    async def _download(self, url: str) -> bytes:
        if self._http is None:
            raise PreviewDownloadError(
                "no HTTP client configured; pass http_client to use decode_url"
            )
        attempt = 0
        while True:
            try:
                response = await self._http.get(url, follow_redirects=True)
                status = response.status_code
                if status == 404:
                    raise PreviewDownloadError(f"preview not found (404): {url}")
                response.raise_for_status()
                payload = response.content
                if not payload:
                    raise PreviewDownloadError(f"empty preview payload: {url}")
                if len(payload) > self._max_payload_bytes:
                    raise PreviewDownloadError(
                        f"preview payload too large ({len(payload)} bytes): {url}"
                    )
                return payload
            except PreviewDownloadError:
                raise  # permanent failures are never retried
            except (
                httpx.TimeoutException,
                httpx.TransportError,
                httpx.HTTPStatusError,
            ) as exc:
                transient = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code >= 500 or exc.response.status_code == 429
                )
                if not transient or attempt >= self._max_retries:
                    raise PreviewDownloadError(
                        f"preview download failed after {attempt + 1} attempt(s): "
                        f"{url} ({exc})"
                    ) from exc
                attempt += 1
                backoff = min(2.0**attempt, 8.0)
                LOGGER.warning(
                    "Preview download attempt %d failed (%s); retrying in %.1fs",
                    attempt,
                    exc,
                    backoff,
                )
                await self._sleep(backoff)

    # ----------------------------------------------------------------- ffmpeg

    def _build_buffer(self, pcm: bytes, sample_rate: int) -> AudioBuffer:
        frame_bytes = 4 * self._channels
        remainder = len(pcm) % frame_bytes
        if remainder:
            pcm = pcm[:-remainder]
        if not pcm:
            raise AudioDecodeError("ffmpeg produced no usable PCM output")
        return AudioBuffer(pcm_bytes=pcm, sample_rate=sample_rate)

    async def _run_ffmpeg(
        self,
        ffmpeg_bin: str,
        args: Sequence[str],
        payload: bytes,
    ) -> bytes:
        """Pipe ``payload`` through one ffmpeg subprocess and return the PCM."""
        try:
            process = await asyncio.create_subprocess_exec(
                ffmpeg_bin,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise FFmpegNotFoundError(
                f"ffmpeg binary not found ({ffmpeg_bin!r}); install FFmpeg and "
                "make sure it is on PATH"
            ) from exc
        except OSError as exc:
            raise FFmpegNotFoundError(
                f"ffmpeg binary {ffmpeg_bin!r} could not be started: {exc}"
            ) from exc

        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None

        stdout_task: asyncio.Task[bytes] | None = None
        stderr_task: asyncio.Task[bytes] | None = None
        try:
            # Start draining stdout before writing: the OS pipe buffer is far
            # smaller than a 30 s PCM stream, so ffmpeg must consume while we
            # feed or write() would deadlock.
            stdout_task = asyncio.create_task(process.stdout.read())
            stderr_task = asyncio.create_task(process.stderr.read())

            async def feed() -> None:
                try:
                    process.stdin.write(payload)
                    await process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass  # ffmpeg exited early; the error surfaces below
                finally:
                    try:
                        # StreamWriter has no aclose(); close() + wait_closed()
                        # is the correct async shutdown on both platforms.
                        process.stdin.close()
                        await process.stdin.wait_closed()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass

            try:
                await asyncio.wait_for(feed(), timeout=self._ffmpeg_timeout)
                pcm = await asyncio.wait_for(stdout_task, timeout=self._ffmpeg_timeout)
                stderr = await asyncio.wait_for(
                    stderr_task, timeout=self._ffmpeg_timeout
                )
                returncode = await asyncio.wait_for(
                    process.wait(), timeout=self._ffmpeg_timeout
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                raise AudioDecodeError(
                    f"ffmpeg timed out after {self._ffmpeg_timeout:.0f}s"
                ) from None

            if returncode != 0 or not pcm:
                detail = stderr.decode("utf-8", "replace").strip().splitlines()
                tail = detail[-1] if detail else "no stderr output"
                raise AudioDecodeError(f"ffmpeg failed with code {returncode}: {tail}")
            return pcm
        except BaseException:
            for task in (stdout_task, stderr_task):
                if task is not None and not task.done():
                    task.cancel()
            raise


__all__ = ["FFmpegAudioDecoder", "FFmpegRunner"]
