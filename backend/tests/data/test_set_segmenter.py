"""Tests for the streamed DJ set segmenter (synthetic PCM, no ffmpeg binary)."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Sequence
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from data.errors import FFmpegNotFoundError
from data.ml.set_segmenter import SetSegmenter
from domain.value_objects.audio_features import TimeRange

_SAMPLE_RATE = 16_000


def _tone(seconds: float, frequency: float) -> np.ndarray:
    t = np.arange(int(seconds * _SAMPLE_RATE), dtype=np.float32) / _SAMPLE_RATE
    return (0.5 * np.sin(2.0 * math.pi * frequency * t)).astype(np.float32)


def _pcm_bytes(block: np.ndarray) -> bytes:
    return block.astype(np.float32).tobytes()


def _factory(pcm: bytes) -> Callable[[Sequence[str]], Iterator[bytes]]:
    def stream(args: Sequence[str]) -> Iterator[bytes]:
        del args
        # Yield in 64 KB chunks like a real ffmpeg pipe would.
        for start in range(0, len(pcm), 65_536):
            yield pcm[start : start + 65_536]

    return stream


def _segmenter(**overrides: object) -> SetSegmenter:
    defaults: dict[str, object] = {
        "min_passage_seconds": 2.0,
        "max_passage_seconds": 8.0,
        "candidate_passage_seconds": (2.0, 4.0, 8.0),
        "stream_factory": _factory(b""),
    }
    defaults.update(overrides)
    return SetSegmenter(**defaults)  # type: ignore[arg-type]


def test_two_hard_transitions_produce_ordered_coverage() -> None:
    # Three distinct "tracks" of 8 s each: sine / silence "break" / other pitch.
    part_a = _tone(8.0, 110.0)
    part_b = np.zeros(int(8.0 * _SAMPLE_RATE), dtype=np.float32)
    part_c = _tone(8.0, 440.0)
    pcm = _pcm_bytes(np.concatenate([part_a, part_b, part_c]))
    segmenter = _segmenter(stream_factory=_factory(pcm))

    passages = segmenter.detect_passages(Path("fake.m4a"), 24.0)

    assert len(passages) >= 3
    # Ordered, contiguous, non-overlapping coverage of the whole set.
    assert passages[0].start_seconds == 0.0
    for first, second in pairwise(passages):
        assert first.end_seconds == pytest.approx(second.start_seconds)
    assert passages[-1].end_seconds == pytest.approx(24.0)
    # Every passage respects the configured maximum length.
    for passage in passages:
        assert passage.duration_seconds <= 8.0 + 1.0


def test_transitions_land_near_the_novelty_peaks() -> None:
    part_a = _tone(8.0, 110.0)
    part_b = np.zeros(int(8.0 * _SAMPLE_RATE), dtype=np.float32)
    part_c = _tone(8.0, 440.0)
    pcm = _pcm_bytes(np.concatenate([part_a, part_b, part_c]))
    segmenter = _segmenter(stream_factory=_factory(pcm))

    passages = segmenter.detect_passages(Path("fake.m4a"), 24.0)

    # The detected boundaries should be close to the true 8 s / 16 s cuts.
    boundaries = [passage.end_seconds for passage in passages[:-1]]
    for cut in (8.0, 16.0):
        assert any(abs(boundary - cut) <= 2.0 for boundary in boundaries), (
            f"no boundary near {cut} in {boundaries}"
        )


def test_flat_audio_falls_back_to_even_subdivision() -> None:
    pcm = _pcm_bytes(_tone(20.0, 110.0))
    segmenter = _segmenter(stream_factory=_factory(pcm))

    passages = segmenter.detect_passages(Path("fake.m4a"), 20.0)

    # No novelty peaks: subdivide the >max flat region evenly.
    assert len(passages) >= 2
    assert passages[0].start_seconds == 0.0
    assert passages[-1].end_seconds == pytest.approx(20.0)
    for passage in passages:
        assert passage.duration_seconds <= 8.0 + 1.0


def test_silent_audio_covers_the_whole_set() -> None:
    pcm = _pcm_bytes(np.zeros(int(15.0 * _SAMPLE_RATE), dtype=np.float32))
    segmenter = _segmenter(stream_factory=_factory(pcm))

    passages = segmenter.detect_passages(Path("fake.m4a"), 15.0)

    assert passages
    assert passages[0].start_seconds == 0.0
    assert passages[-1].end_seconds == pytest.approx(15.0)


def test_short_set_is_a_single_passage() -> None:
    pcm = _pcm_bytes(_tone(6.0, 110.0))
    segmenter = _segmenter(stream_factory=_factory(pcm))

    passages = segmenter.detect_passages(Path("fake.m4a"), 6.0)

    assert len(passages) == 1
    assert passages[0] == TimeRange(0.0, 6.0)


def test_missing_ffmpeg_raises_ffmpeg_not_found() -> None:
    def broken_factory(args: Sequence[str]) -> Iterator[bytes]:
        del args
        raise FFmpegNotFoundError("ffmpeg binary not found")
        yield b""  # pragma: no cover - generator formality

    segmenter = _segmenter(stream_factory=broken_factory)
    with pytest.raises(FFmpegNotFoundError):
        segmenter.detect_passages(Path("fake.m4a"), 30.0)


def test_plan_segments_windows_cover_the_set() -> None:
    segmenter = _segmenter()
    windows = segmenter.plan_segments(90.0, window_seconds=30.0, hop_seconds=15.0)
    assert [w.start_seconds for w in windows] == [0.0, 15.0, 30.0, 45.0, 60.0, 75.0]
    # Full windows are 30 s; the final one is clipped to the set's end.
    assert all(w.end_seconds - w.start_seconds == 30.0 for w in windows[:-1])
    assert windows[-1].end_seconds == 90.0
    assert windows[-1].duration_seconds == pytest.approx(15.0)


def test_plan_segments_clips_the_final_window() -> None:
    segmenter = _segmenter()
    windows = segmenter.plan_segments(50.0, window_seconds=30.0, hop_seconds=15.0)
    assert [w.start_seconds for w in windows] == [0.0, 15.0, 30.0, 45.0]
    assert [w.duration_seconds for w in windows] == pytest.approx(
        [30.0, 30.0, 20.0, 5.0]
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_passage_seconds": 0.0}, "passage bounds"),
        ({"min_passage_seconds": 10.0, "max_passage_seconds": 5.0}, "passage bounds"),
        ({"feature_fps": 0.0}, "feature_fps"),
        ({"sample_rate": 0}, "sample_rate"),
    ],
)
def test_invalid_configuration_raises(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _segmenter(**kwargs)


def test_invalid_duration_raises() -> None:
    segmenter = _segmenter()
    with pytest.raises(ValueError, match="total_duration_seconds"):
        segmenter.detect_passages(Path("fake.m4a"), 0.0)
    with pytest.raises(ValueError, match="total_duration_seconds"):
        segmenter.plan_segments(-1.0)
