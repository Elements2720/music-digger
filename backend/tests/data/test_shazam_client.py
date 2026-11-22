"""Tests for the shazamio-backed fingerprinter (fake recognizers, no network)."""

from __future__ import annotations

import asyncio
import io
import struct
import wave
from typing import Any

import pytest

from data.datasources.remote.shazam_client import ShazamFingerprinter, pcm_to_wav
from data.errors import FingerprintError
from domain.entities.track import AudioBuffer


def _buffer(seconds: float = 0.5, sample_rate: int = 16_000) -> AudioBuffer:
    count = int(seconds * sample_rate)
    pcm = struct.pack(f"<{count}f", *([0.25] * count))
    return AudioBuffer(pcm_bytes=pcm, sample_rate=sample_rate)


def _fingerprinter(recognizer_factory: Any = None) -> ShazamFingerprinter:
    kwargs: dict[str, Any] = {"jitter_seconds": 0.0}
    if recognizer_factory is not None:
        kwargs["recognizer_factory"] = recognizer_factory
    return ShazamFingerprinter(**kwargs)


def test_identify_sync_is_documented_unsupported() -> None:
    fingerprinter = _fingerprinter()
    assert fingerprinter.identify(_buffer()) is None


async def test_identify_async_returns_a_track_reference() -> None:
    class FakeRecognizer:
        async def recognize(self, wav_bytes: bytes) -> dict[str, Any]:
            assert wav_bytes.startswith(b"RIFF"), "snippets must be wrapped in WAV"
            return {"track": {"title": "Deep Inside", "subtitle": "Hardrive"}}

    fingerprinter = _fingerprinter(FakeRecognizer)

    reference = await fingerprinter.identify_async(_buffer())

    assert reference is not None
    assert reference.title == "Deep Inside"
    assert reference.artist == "Hardrive"
    assert reference.confidence == 1.0


async def test_unrecognized_track_returns_none() -> None:
    class FakeRecognizer:
        async def recognize(self, wav_bytes: bytes) -> dict[str, Any]:
            return {"code": 0}  # Shazam's "no match" shape

    fingerprinter = _fingerprinter(FakeRecognizer)
    assert await fingerprinter.identify_async(_buffer()) is None


async def test_malformed_result_returns_none() -> None:
    class FakeRecognizer:
        async def recognize(self, wav_bytes: bytes) -> Any:
            return "not-a-dict"

    fingerprinter = _fingerprinter(FakeRecognizer)
    assert await fingerprinter.identify_async(_buffer()) is None


async def test_empty_track_fields_return_none() -> None:
    class FakeRecognizer:
        async def recognize(self, wav_bytes: bytes) -> dict[str, Any]:
            return {"track": {"title": "", "subtitle": "Someone"}}

    fingerprinter = _fingerprinter(FakeRecognizer)
    assert await fingerprinter.identify_async(_buffer()) is None


async def test_recognizer_failure_degrades_to_none() -> None:
    class FakeRecognizer:
        async def recognize(self, wav_bytes: bytes) -> bytes:
            raise RuntimeError("boom")

    fingerprinter = _fingerprinter(FakeRecognizer)
    assert await fingerprinter.identify_async(_buffer()) is None


async def test_missing_dependency_degrades_to_none() -> None:
    def broken_factory() -> Any:
        raise ImportError("shazamio not installed")

    fingerprinter = _fingerprinter(broken_factory)
    assert await fingerprinter.identify_async(_buffer()) is None


async def test_recognizer_is_created_once_and_reused() -> None:
    calls: list[int] = []

    class FakeRecognizer:
        def __init__(self) -> None:
            calls.append(1)

        async def recognize(self, wav_bytes: bytes) -> dict[str, Any]:
            return {"track": {"title": "X", "subtitle": "Y"}}

    fingerprinter = _fingerprinter(FakeRecognizer)
    await fingerprinter.identify_async(_buffer())
    await fingerprinter.identify_async(_buffer())
    assert len(calls) == 1


async def test_compute_hashes_pcm_bytes() -> None:
    fingerprinter = _fingerprinter()
    audio = _buffer()
    assert fingerprinter.compute(audio) == fingerprinter.compute(audio)
    other = AudioBuffer(
        pcm_bytes=audio.pcm_bytes + b"\x00\x00\x00\x00", sample_rate=16_000
    )
    assert fingerprinter.compute(other) != fingerprinter.compute(audio)


def test_pcm_to_wav_wraps_int16_frames() -> None:
    pcm = struct.pack("<3f", 0.0, 1.0, -1.0)
    audio = AudioBuffer(pcm_bytes=pcm, sample_rate=8000)

    wav_bytes = pcm_to_wav(audio)

    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 8000
        frames = handle.readframes(3)
    assert struct.unpack("<3h", frames) == (0, 32767, -32767)


def test_pcm_to_wav_rejects_bad_sample_rate() -> None:
    with pytest.raises(FingerprintError):
        pcm_to_wav(_BrokenSampleRateBuffer())


class _BrokenSampleRateBuffer:
    """Duck-typed AudioBuffer with an impossible sample rate."""

    @property
    def pcm_bytes(self) -> bytes:
        return b"\x00\x00\x00\x00"

    @property
    def sample_rate(self) -> int:
        return -1


def test_invalid_construction_parameters_rejected() -> None:
    with pytest.raises(ValueError, match="max_concurrency"):
        ShazamFingerprinter(max_concurrency=0)
    with pytest.raises(ValueError, match="jitter"):
        ShazamFingerprinter(jitter_seconds=-1.0)
    with pytest.raises(ValueError, match="timeout"):
        ShazamFingerprinter(timeout_seconds=0.0)
    with pytest.raises(ValueError, match="consecutive"):
        ShazamFingerprinter(max_consecutive_failures=0)


async def test_timeout_degrades_cleanly_to_none() -> None:
    class HangingRecognizer:
        async def recognize(self, wav_bytes: bytes) -> dict[str, Any]:
            await asyncio.sleep(1.0)
            return {"track": {"title": "X", "subtitle": "Y"}}

    fingerprinter = ShazamFingerprinter(
        recognizer_factory=HangingRecognizer,
        jitter_seconds=0.0,
        timeout_seconds=0.05,
    )

    result = await fingerprinter.identify_async(_buffer())
    assert result is None


async def test_circuit_breaker_triggers_after_consecutive_failures() -> None:
    calls: list[int] = []

    class FailingRecognizer:
        async def recognize(self, wav_bytes: bytes) -> dict[str, Any]:
            calls.append(len(calls) + 1)
            raise RuntimeError("API rate limited")

    fingerprinter = ShazamFingerprinter(
        recognizer_factory=FailingRecognizer,
        jitter_seconds=0.0,
        timeout_seconds=0.1,
        max_consecutive_failures=3,
    )

    # 3 failures should trigger the circuit breaker
    for _ in range(3):
        assert await fingerprinter.identify_async(_buffer()) is None

    assert len(calls) == 3
    assert fingerprinter.is_circuit_open is True

    # 4th call is skipped immediately without invoking recognizer
    assert await fingerprinter.identify_async(_buffer()) is None
    assert len(calls) == 3  # not called!


async def test_circuit_breaker_resets_on_success_or_manual_reset() -> None:
    calls: list[int] = []

    class FlakyRecognizer:
        should_fail = True

        async def recognize(self, wav_bytes: bytes) -> dict[str, Any]:
            calls.append(1)
            if self.should_fail:
                raise RuntimeError("temporary outage")
            return {"track": {"title": "Working", "subtitle": "Artist"}}

    recognizer = FlakyRecognizer()
    fingerprinter = ShazamFingerprinter(
        recognizer_factory=lambda: recognizer,
        jitter_seconds=0.0,
        timeout_seconds=0.1,
        max_consecutive_failures=2,
    )

    # Fail twice to trip the circuit breaker
    await fingerprinter.identify_async(_buffer())
    await fingerprinter.identify_async(_buffer())
    assert fingerprinter.is_circuit_open is True

    # Manual reset closes the breaker
    fingerprinter.reset_circuit_breaker()
    assert fingerprinter.is_circuit_open is False

    # Now make it succeed
    recognizer.should_fail = False
    result = await fingerprinter.identify_async(_buffer())
    assert result is not None
    assert result.title == "Working"
    assert fingerprinter.is_circuit_open is False


async def test_cancelled_error_is_never_swallowed() -> None:
    class CancelledRecognizer:
        async def recognize(self, wav_bytes: bytes) -> dict[str, Any]:
            raise asyncio.CancelledError()

    fingerprinter = ShazamFingerprinter(
        recognizer_factory=CancelledRecognizer,
        jitter_seconds=0.0,
    )

    with pytest.raises(asyncio.CancelledError):
        await fingerprinter.identify_async(_buffer())
