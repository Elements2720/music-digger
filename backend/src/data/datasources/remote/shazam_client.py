"""Exact-ID fingerprinting through ``shazamio``.

Each passage contributes a ~12 s snippet; recognition runs under a semaphore
(default 3) with small jitter so Shazam's public endpoint is never hammered.
Unreleased IDs, unknown tracks, and network hiccups all degrade gracefully to
``None`` — "no match" must never abort an analysis. ``shazamio`` is imported
lazily inside the recognition path and snippets are wrapped into a WAV
container in memory (stdlib ``wave``) because raw PCM has no recognizable
container header.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import random
import struct
import wave
from collections.abc import Callable
from typing import Any

from domain.entities.track import AudioBuffer, TrackReference
from domain.interfaces.audio_engine import IFingerprinter

from ...errors import FingerprintError

LOGGER = logging.getLogger(__name__)

#: Parallel recognition ceiling — polite toward the public Shazam endpoint.
MAX_CONCURRENCY = 3
#: Extra delay between recognitions to space out bursts.
JITTER_SECONDS = 0.25


RecognizerFactory = Callable[[], Any]


class ShazamFingerprinter(IFingerprinter):
    """Async-only fingerprinter backed by the ``shazamio`` service."""

    def __init__(
        self,
        *,
        recognizer_factory: RecognizerFactory | None = None,
        max_concurrency: int = MAX_CONCURRENCY,
        jitter_seconds: float = JITTER_SECONDS,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if jitter_seconds < 0:
            raise ValueError("jitter_seconds must not be negative")
        self._recognizer_factory = recognizer_factory or self._default_factory
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._jitter_seconds = jitter_seconds
        self._recognizer: Any | None = None

    # ------------------------------------------------------------------ API

    def compute(self, audio: AudioBuffer) -> str:
        """Stable content fingerprint (sha256 of the PCM bytes)."""
        return hashlib.sha256(audio.pcm_bytes).hexdigest()

    def identify(self, audio: AudioBuffer) -> Any | None:
        """Sync seam: unsupported — Shazam recognition is async-only.

        The interface's :meth:`identify_async` is the real entry point; the
        sync variant returns ``None`` (documented "unidentified") instead of
        blocking or raising inside a running event loop.
        """
        LOGGER.debug(
            "ShazamFingerprinter.identify is sync-unsupported; use identify_async"
        )
        return None

    async def identify_async(self, audio: AudioBuffer) -> TrackReference | None:
        """Recognize one snippet; ``None`` means "no confident match"."""
        try:
            recognizer = self._ensure_recognizer()
        except Exception as exc:  # noqa: BLE001 - missing shazamio degrades to None
            LOGGER.warning("Shazam recognizer unavailable: %s", exc)
            return None

        wav_bytes = pcm_to_wav(audio)
        async with self._semaphore:
            if self._jitter_seconds:
                await asyncio.sleep(random.uniform(0.05, self._jitter_seconds))
            try:
                result = await self._recognize(recognizer, wav_bytes)
            except Exception as exc:  # noqa: BLE001 - one bad snippet must not fail the set
                LOGGER.debug("Shazam recognition failed: %s", exc)
                return None
        return self._reference_from_result(result)

    # ------------------------------------------------------------ internals

    @staticmethod
    def _default_factory() -> Any:
        from shazamio import Shazam  # lazy: heavy dependency graph

        return Shazam()

    def _ensure_recognizer(self) -> Any:
        if self._recognizer is None:
            self._recognizer = self._recognizer_factory()
        return self._recognizer

    @staticmethod
    async def _recognize(recognizer: Any, wav_bytes: bytes) -> Any:
        recognize = getattr(recognizer, "recognize", None)
        if recognize is None:
            recognize = recognizer.full_recognize
        return await recognize(wav_bytes)

    @staticmethod
    def _reference_from_result(result: Any) -> TrackReference | None:
        if not isinstance(result, dict):
            return None
        track = result.get("track")
        if not isinstance(track, dict):
            return None  # unrecognized or unreleased: Shazam found no track
        title = str(track.get("title") or "").strip()
        subtitle = str(track.get("subtitle") or "").strip()
        if not title or not subtitle:
            return None
        try:
            return TrackReference(
                artist=subtitle,
                title=title,
                confidence=1.0,
            )
        except (TypeError, ValueError):
            return None


def pcm_to_wav(audio: AudioBuffer) -> bytes:
    """Wrap mono float32 PCM into a 16-bit WAV container in memory."""
    if audio.sample_rate <= 0:
        raise FingerprintError("audio sample rate must be positive")
    count = len(audio.pcm_bytes) // 4
    samples = struct.unpack(f"<{count}f", audio.pcm_bytes[: count * 4])
    int16 = b"".join(
        struct.pack("<h", max(-32768, min(32767, int(sample * 32767.0))))
        for sample in samples
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(audio.sample_rate)
        handle.writeframes(int16)
    return buffer.getvalue()


__all__ = ["MAX_CONCURRENCY", "ShazamFingerprinter", "pcm_to_wav"]
