"""Tests for the librosa BPM/key analyzer using synthetic PCM buffers.

No network, no disk: every signal is generated with ``wave``/``math`` and
analyzed either in-process or through a real single-worker process pool to
prove picklability.
"""

from __future__ import annotations

import math
import struct

import pytest

from data.ml.librosa_analyzer import (
    LibrosaFeatureExtractor,
    analyze_pcm,
    fold_tempo,
)
from domain.entities.track import AudioBuffer
from domain.value_objects.audio_features import (
    BPM_MAX,
    BPM_MIN,
    AudioFeatures,
    CamelotKey,
)

SAMPLE_RATE = 48_000
_SECONDS = 12


def _pcm_bytes(samples: list[float]) -> bytes:
    return struct.pack(f"<{len(samples)}f", *samples)


def _silence(seconds: float = 5.0) -> bytes:
    return bytes(int(SAMPLE_RATE * seconds) * 4)


def _click_track(bpm: float = 120.0, seconds: float = _SECONDS) -> bytes:
    """Mono PCM of short 1 kHz clicks on every beat at ``bpm``."""
    total = int(SAMPLE_RATE * seconds)
    samples = [0.0] * total
    beat_interval = SAMPLE_RATE * 60.0 / bpm
    click_length = int(SAMPLE_RATE * 0.03)
    position = 0.0
    while position < total - click_length:
        start = int(position)
        for i in range(click_length):
            envelope = 1.0 - i / click_length
            samples[start + i] = (
                0.9 * envelope * math.sin(2 * math.pi * 1000 * i / SAMPLE_RATE)
            )
        position += beat_interval
    return _pcm_bytes(samples)


def _chord(frequencies: list[float], seconds: float = 8.0) -> bytes:
    """A sustained chord of summed sine waves (for key detection)."""
    total = int(SAMPLE_RATE * seconds)
    samples = [0.0] * total
    for frequency in frequencies:
        for i in range(total):
            samples[i] += math.sin(2 * math.pi * frequency * i / SAMPLE_RATE)
    peak = max(abs(value) for value in samples)
    return _pcm_bytes([value * 0.9 / peak for value in samples])


def _note(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


# C4, E4, G4 — a clean C major triad.
_C_MAJOR_TRIAD = [_note(60), _note(64), _note(67)]


def test_fold_tempo_folds_into_the_club_band() -> None:
    assert fold_tempo(120.0) == 120.0
    assert fold_tempo(150.0) == 150.0
    assert fold_tempo(174.0) == 174.0  # drum & bass stays put
    assert fold_tempo(65.0) == 130.0  # half-tempo detection
    assert fold_tempo(32.0) == 128.0  # extreme half
    assert fold_tempo(240.0) == 120.0  # double-time detection
    assert fold_tempo(360.0) == 90.0  # extreme double


def test_fold_tempo_clamps_to_domain_bounds() -> None:
    assert BPM_MIN <= fold_tempo(0.5) <= BPM_MAX
    assert BPM_MIN <= fold_tempo(9999.0) <= BPM_MAX


@pytest.mark.parametrize("bad", [0.0, -90.0, float("nan"), float("inf")])
def test_fold_tempo_rejects_invalid_input(bad: float) -> None:
    with pytest.raises(ValueError):
        fold_tempo(bad)


@pytest.mark.parametrize(
    ("root", "mode", "expected"),
    [
        (0, "major", "8B"),  # C major
        (9, "minor", "8A"),  # A minor (relative of C)
        (4, "major", "12B"),  # E major
        (1, "minor", "12A"),  # C# minor (relative of E)
        (11, "major", "1B"),  # B major
        (5, "minor", "4A"),  # F minor
        (10, "minor", "3A"),  # Bb minor
        (2, "major", "10B"),  # D major
        (7, "minor", "6A"),  # G minor
    ],
)
def test_camelot_mapping(root: int, mode: str, expected: str) -> None:
    from data.ml import librosa_analyzer

    chroma = [0.0] * 12
    # Energy on the tonic, third, and fifth of the requested key.
    intervals = (0, 4, 7) if mode == "major" else (0, 3, 7)
    for interval in intervals:
        chroma[(root + interval) % 12] = 1.0
    key = librosa_analyzer._detect_key_from_chroma(chroma)
    assert key == CamelotKey(expected)


def test_detect_key_prefers_a_clean_major_triad() -> None:
    chroma_major = [0.0] * 12
    for pitch in (0, 4, 7):
        chroma_major[pitch] = 1.0
    from data.ml import librosa_analyzer

    assert librosa_analyzer._detect_key_from_chroma(chroma_major) == CamelotKey("8B")


def test_analyze_pcm_detects_click_track_tempo() -> None:
    features = analyze_pcm(_click_track(120.0), SAMPLE_RATE)

    assert features.bpm is not None
    assert features.bpm.value == pytest.approx(120.0, abs=3.0)


@pytest.mark.parametrize("target_bpm", [124.0, 125.0, 126.0])
def test_bpm_resolution_distinguishes_neighbouring_tempos(target_bpm: float) -> None:
    """Regression: the old 48 kHz / hop-512 grid snapped 124-126 to 125."""
    features = analyze_pcm(_click_track(target_bpm), SAMPLE_RATE)

    assert features.bpm is not None
    assert features.bpm.value == pytest.approx(target_bpm, abs=1.0)


def test_neighbouring_tempos_resolve_to_distinct_values() -> None:
    """124 / 125 / 126 BPM clicks must not all quantize to the same value."""
    tempos = [
        analyze_pcm(_click_track(target), SAMPLE_RATE).bpm
        for target in (124.0, 125.0, 126.0)
    ]

    assert all(tempo is not None for tempo in tempos)
    values = {tempo.value for tempo in tempos}
    assert len(values) == 3


def test_analyze_pcm_rounds_bpm_to_one_decimal() -> None:
    features = analyze_pcm(_click_track(125.0), SAMPLE_RATE)

    assert features.bpm is not None
    assert features.bpm.value == round(features.bpm.value, 1)


def test_analyze_pcm_detects_half_tempo_clicks_via_folding() -> None:
    """A 60 BPM click track is folded up into the club band."""
    features = analyze_pcm(_click_track(60.0), SAMPLE_RATE)

    assert features.bpm is not None
    assert features.bpm.value == pytest.approx(120.0, abs=4.0)


def test_analyze_pcm_detects_key_of_c_major_chord() -> None:
    features = analyze_pcm(_chord(_C_MAJOR_TRIAD), SAMPLE_RATE)

    assert features.key is not None
    assert features.key.notation == "8B"


def test_analyze_pcm_returns_empty_features_for_silence() -> None:
    features = analyze_pcm(_silence(6.0), SAMPLE_RATE)

    assert features == AudioFeatures()


def test_analyze_pcm_returns_empty_features_for_short_audio() -> None:
    features = analyze_pcm(_click_track(120.0, seconds=1.0), SAMPLE_RATE)

    assert features.bpm is None
    assert features.key is None


def test_analyze_pcm_rejects_bad_sample_rate() -> None:
    with pytest.raises(ValueError):
        analyze_pcm(_silence(1.0), 0)


def test_extractor_wraps_analyze_pcm() -> None:
    extractor = LibrosaFeatureExtractor()
    buffer = AudioBuffer(pcm_bytes=_click_track(120.0), sample_rate=SAMPLE_RATE)

    features = extractor.extract(buffer)

    assert features.bpm is not None
    assert features.bpm.value == pytest.approx(120.0, abs=3.0)


def test_extractor_is_picklable_for_process_pools() -> None:
    import pickle

    extractor = LibrosaFeatureExtractor()
    clone = pickle.loads(pickle.dumps(extractor))

    assert clone.tempo_low == extractor.tempo_low
    assert clone.tempo_high == extractor.tempo_high
    assert clone.min_duration_seconds == extractor.min_duration_seconds


def test_extractor_runs_inside_a_real_process_pool() -> None:
    """End-to-end picklability proof: extract in a spawned worker process."""
    from concurrent.futures import ProcessPoolExecutor

    extractor = LibrosaFeatureExtractor()
    # A short buffer keeps worker startup cheap; silence means no features.
    buffer = AudioBuffer(pcm_bytes=_silence(4.0), sample_rate=16_000)

    with ProcessPoolExecutor(max_workers=1) as pool:
        future = pool.submit(extractor.extract, buffer)
        features = future.result(timeout=120)

    assert features == AudioFeatures()
