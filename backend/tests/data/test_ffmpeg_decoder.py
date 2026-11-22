"""Tests for the FFmpeg preview decoder using fakes and MockTransport."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence

import httpx
import pytest

from data.errors import AudioDecodeError, FFmpegNotFoundError, PreviewDownloadError
from data.ml.ffmpeg_decoder import FFmpegAudioDecoder
from domain.value_objects.audio_features import TimeRange

FAKE_PREVIEW = b"\x00\x01\x02\x03" * 512  # a fake compressed payload
FAKE_PCM = bytes(4 * 1600)  # 1600 float32 mono samples


def make_client(
    handler: httpx.MockTransport,
    *,
    timeout: float = 5.0,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, timeout=timeout)


def fake_runner(output: bytes | Exception = FAKE_PCM) -> tuple[object, list[list[str]]]:
    """Return an injectable runner plus the list of arg-lists it received."""
    calls: list[list[str]] = []

    async def run(ffmpeg_bin: str, args: Sequence[str], payload: bytes) -> bytes:
        calls.append(list(args))
        if isinstance(output, Exception):
            raise output
        return output

    return run, calls


async def test_decode_url_success_pipes_payload_through_ffmpeg() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FAKE_PREVIEW)

    run, calls = fake_runner()
    decoder = FFmpegAudioDecoder(
        http_client=make_client(httpx.MockTransport(handler)),
        process_runner=run,  # type: ignore[arg-type]
    )

    buffer = await decoder.decode_url("https://example.test/a.m4a")

    assert buffer.sample_rate == 48_000
    assert buffer.pcm_bytes == FAKE_PCM
    assert len(calls) == 1
    args = calls[0]
    assert "pipe:0" in args and "pipe:1" in args
    assert args[args.index("-ar") + 1] == "48000"
    assert args[args.index("-ac") + 1] == "1"
    assert args[args.index("-f") + 1] == "f32le"


async def test_decode_from_memory_source() -> None:
    run, _calls = fake_runner()
    decoder = FFmpegAudioDecoder(process_runner=run)  # type: ignore[arg-type]

    buffer = await decoder.decode(io.BytesIO(FAKE_PREVIEW), sample_rate=22_050)

    assert buffer.pcm_bytes == FAKE_PCM
    assert buffer.sample_rate == 22_050


async def test_404_is_not_retried() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(404, text="not found")

    run, _ = fake_runner()
    decoder = FFmpegAudioDecoder(
        http_client=make_client(httpx.MockTransport(handler)),
        process_runner=run,  # type: ignore[arg-type]
    )

    with pytest.raises(PreviewDownloadError, match="404"):
        await decoder.decode_url("https://example.test/gone.m4a")

    assert len(attempts) == 1


async def test_server_errors_are_retried_then_succeed() -> None:
    sleeps: list[float] = []
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, content=FAKE_PREVIEW)

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    run, _ = fake_runner()
    decoder = FFmpegAudioDecoder(
        http_client=make_client(httpx.MockTransport(handler)),
        process_runner=run,  # type: ignore[arg-type]
        sleep=record_sleep,
    )

    buffer = await decoder.decode_url("https://example.test/flaky.m4a")

    assert buffer.pcm_bytes == FAKE_PCM
    assert len(attempts) == 3
    assert len(sleeps) == 2


async def test_transport_errors_exhaust_retries_then_raise() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("connection refused", request=request)

    run, _ = fake_runner()
    decoder = FFmpegAudioDecoder(
        http_client=make_client(httpx.MockTransport(handler)),
        process_runner=run,  # type: ignore[arg-type]
        max_retries=1,
        sleep=asyncio.sleep,
    )

    with pytest.raises(PreviewDownloadError, match="2 attempt"):
        await decoder.decode_url("https://example.test/down.m4a")

    assert len(attempts) == 2  # initial attempt + 1 retry


async def test_empty_payload_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    run, _ = fake_runner()
    decoder = FFmpegAudioDecoder(
        http_client=make_client(httpx.MockTransport(handler)),
        process_runner=run,  # type: ignore[arg-type]
    )

    with pytest.raises(PreviewDownloadError, match="empty"):
        await decoder.decode_url("https://example.test/empty.m4a")


async def test_missing_http_client_blocks_decode_url_only() -> None:
    run, _ = fake_runner()
    decoder = FFmpegAudioDecoder(process_runner=run)  # type: ignore[arg-type]

    with pytest.raises(PreviewDownloadError, match="HTTP client"):
        await decoder.decode_url("https://example.test/a.m4a")
    # In-memory decode still works.
    buffer = await decoder.decode(io.BytesIO(FAKE_PREVIEW))
    assert buffer.pcm_bytes == FAKE_PCM


async def test_missing_ffmpeg_binary_raises_clear_error() -> None:
    async def run(ffmpeg_bin: str, args: Sequence[str], payload: bytes) -> bytes:
        raise FileNotFoundError("ffmpeg not found")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FAKE_PREVIEW)

    decoder = FFmpegAudioDecoder(
        http_client=make_client(httpx.MockTransport(handler)),
        process_runner=run,  # type: ignore[arg-type]
    )

    with pytest.raises(FFmpegNotFoundError, match="PATH"):
        await decoder.decode_url("https://example.test/a.m4a")


async def test_ffmpeg_failure_raises_audio_decode_error() -> None:
    async def run(ffmpeg_bin: str, args: Sequence[str], payload: bytes) -> bytes:
        raise AudioDecodeError("ffmpeg failed with code 1: Invalid data")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FAKE_PREVIEW)

    decoder = FFmpegAudioDecoder(
        http_client=make_client(httpx.MockTransport(handler)),
        process_runner=run,  # type: ignore[arg-type]
    )

    with pytest.raises(AudioDecodeError, match="Invalid data"):
        await decoder.decode_url("https://example.test/corrupt.m4a")


async def test_empty_pcm_output_is_rejected() -> None:
    run, _ = fake_runner(output=b"")
    decoder = FFmpegAudioDecoder(process_runner=run)  # type: ignore[arg-type]

    with pytest.raises(AudioDecodeError, match="no usable PCM"):
        await decoder.decode(io.BytesIO(FAKE_PREVIEW))


async def test_partial_frame_is_trimmed() -> None:
    run, _ = fake_runner(output=FAKE_PCM + b"\x01")  # one stray byte
    decoder = FFmpegAudioDecoder(process_runner=run)  # type: ignore[arg-type]

    buffer = await decoder.decode(io.BytesIO(FAKE_PREVIEW))

    assert len(buffer.pcm_bytes) == len(FAKE_PCM)


async def test_decode_segment_uses_seek_flags(tmp_path) -> None:  # type: ignore[no-untyped-def]
    run, calls = fake_runner()
    decoder = FFmpegAudioDecoder(process_runner=run)  # type: ignore[arg-type]
    media = tmp_path / "set.mp3"
    media.write_bytes(b"x")

    buffer = await decoder.decode_segment(
        media, TimeRange(120.0, 150.0), sample_rate=48_000, channels=1
    )

    assert buffer.pcm_bytes == FAKE_PCM
    args = calls[0]
    assert args[args.index("-ss") + 1] == "120.000"
    assert args[args.index("-t") + 1] == "30.000"


async def test_concurrency_is_bounded_by_the_semaphore() -> None:
    """At most `download_concurrency` decodes run at the same time."""
    active = 0
    peak = 0

    async def run(ffmpeg_bin: str, args: Sequence[str], payload: bytes) -> bytes:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return FAKE_PCM

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FAKE_PREVIEW)

    decoder = FFmpegAudioDecoder(
        http_client=make_client(httpx.MockTransport(handler)),
        process_runner=run,  # type: ignore[arg-type]
        download_concurrency=3,
    )

    await asyncio.gather(
        *(decoder.decode_url(f"https://example.test/{i}.m4a") for i in range(10))
    )

    assert peak == 3


def _ffmpeg_missing() -> bool:
    import shutil

    return shutil.which("ffmpeg") is None


@pytest.mark.skipif(_ffmpeg_missing(), reason="real ffmpeg not installed")
async def test_real_ffmpeg_decodes_a_synthetic_wav() -> None:
    """Integration smoke test against the real binary (skipped if absent)."""
    import math
    import struct
    import wave

    sample_rate = 8000
    frames = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / sample_rate)))
        for i in range(sample_rate)  # one second of 440 Hz sine
    )
    payload = io.BytesIO()
    with wave.open(payload, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)

    decoder = FFmpegAudioDecoder()
    buffer = await decoder.decode(io.BytesIO(payload.getvalue()), sample_rate=8000)

    assert buffer.sample_rate == 8000
    assert len(buffer.pcm_bytes) == 8000 * 4  # float32 mono


async def test_set_concurrency_swaps_the_bound_and_validates() -> None:
    decoder = FFmpegAudioDecoder(download_concurrency=4)
    assert decoder.download_concurrency == 4

    decoder.set_concurrency(24)
    assert decoder.download_concurrency == 24

    with pytest.raises(ValueError):
        decoder.set_concurrency(0)
    with pytest.raises(TypeError):
        decoder.set_concurrency(True)  # type: ignore[arg-type]
