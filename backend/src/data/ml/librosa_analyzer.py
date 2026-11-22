"""CPU tempo and key extraction with librosa, safe for process pools.

``analyze_pcm`` is a module-level worker function: it imports librosa/numpy
*inside* the call so parent processes never pay the import cost and workers
spawned on Windows can pickle/re-import the module cleanly.

Tempo handling: the preview is resampled to 22.05 kHz once and the same copy
feeds both tempo and key extraction. The tempo grid step is ``60 * fps / lag``
on the onset-envelope frame rate, so the estimator refines its discrete lag
peak with parabolic interpolation (sub-0.2 BPM resolution at club tempos,
without the ~20k-frame onset envelopes that ``hop_length=32`` produced). The
estimate is folded by doubling/halving into the club-music band ``[70, 175]``
BPM (a raw 65 becomes 130, a raw 240 becomes 120), clamped to the domain's
hard ``[40, 220]`` bounds, and rounded to one decimal place.

Key handling: a constant-Q chromagram (``chroma_cqt``) is averaged over time and
correlated (Pearson) against the Krumhansl–Schmuckler major/minor profiles
rotated over the 12 pitch classes. The winning root/mode maps onto the
standard Camelot wheel (C major → 8B, A minor → 8A, ...).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from typing import Any

from domain.entities.track import AudioBuffer
from domain.interfaces.audio_engine import IFeatureExtractor
from domain.value_objects.audio_features import (
    BPM,
    BPM_MAX,
    BPM_MIN,
    AudioFeatures,
    CamelotKey,
)

LOGGER = logging.getLogger(__name__)

#: Fold band for raw tempo estimates (see module docstring).
TEMPO_FOLD_LOW = 70.0
TEMPO_FOLD_HIGH = 175.0

# Tempo and key extraction share ONE resampled copy of the waveform at this
# rate: 22.05 kHz keeps all musically relevant content, and soxr_lq resampling
# costs ~10 ms for a 30 s preview instead of re-resampling per feature.
ANALYSIS_SAMPLE_RATE = 22_050
#: Onset-envelope hop. The frame rate (sr / hop ~ 86 Hz) fixes the discrete
#: tempo grid; sub-grid precision comes from parabolic interpolation of the
#: autocorrelation peak, not from shrinking the hop.
TEMPO_HOP_LENGTH = 256
#: Auto-correlation window for the tempogram, in seconds (librosa default).
TEMPO_AC_SECONDS = 8.0
#: Chroma hop for key extraction: the key is averaged over the whole clip, so
#: a coarse hop (4 frames/s) cuts the CQT cost ~16x with no accuracy change.
KEY_HOP_LENGTH = 2048

#: Minimum audio length for a meaningful analysis, in seconds.
MIN_ANALYSIS_SECONDS = 3.0

# Krumhansl–Schmuckler key profiles, index 0 = tonic.
_KRUMHANSL_MAJOR: tuple[float, ...] = (
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
)
_KRUMHANSL_MINOR: tuple[float, ...] = (
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
)

# Camelot wheel: pitch-class index (0 = C) → major-key notation.
_MAJOR_CAMELOT: Mapping[int, str] = {
    0: "8B",  # C
    1: "3B",  # C#/Db
    2: "10B",  # D
    3: "5B",  # D#/Eb
    4: "12B",  # E
    5: "7B",  # F
    6: "2B",  # F#/Gb
    7: "9B",  # G
    8: "4B",  # G#/Ab
    9: "11B",  # A
    10: "6B",  # A#/Bb
    11: "1B",  # B
}

# The relative minor of a major key keeps the same Camelot number: minor root
# r has its relative major at r + 3 semitones.
_MINOR_CAMELOT: Mapping[int, str] = {
    root: f"{_MAJOR_CAMELOT[(root + 3) % 12][:-1]}A" for root in range(12)
}

_PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def fold_tempo(
    raw_tempo: float,
    *,
    low: float = TEMPO_FOLD_LOW,
    high: float = TEMPO_FOLD_HIGH,
    hard_min: float = BPM_MIN,
    hard_max: float = BPM_MAX,
) -> float:
    """Fold a raw tempo estimate into ``[low, high]`` by doubling or halving.

    Raises ``ValueError`` for non-positive or non-finite input.
    """
    tempo = float(raw_tempo)
    if not math.isfinite(tempo) or tempo <= 0:
        raise ValueError(f"raw_tempo must be positive and finite, got {raw_tempo}")
    while tempo < low:
        tempo *= 2.0
    while tempo > high:
        tempo /= 2.0
    return min(hard_max, max(hard_min, tempo))


def analyze_pcm(
    pcm_bytes: bytes,
    sample_rate: int,
    *,
    tempo_low: float = TEMPO_FOLD_LOW,
    tempo_high: float = TEMPO_FOLD_HIGH,
    min_duration_seconds: float = MIN_ANALYSIS_SECONDS,
) -> AudioFeatures:
    """Extract BPM and musical key from mono float32 PCM.

    The waveform is resampled to :data:`ANALYSIS_SAMPLE_RATE` once and the
    same copy feeds tempo and key extraction. Individual features degrade to
    ``None`` when the audio is too short, silent, or the analysis fails —
    partial results must never abort a batch.
    """
    import numpy as np

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    samples = np.frombuffer(pcm_bytes, dtype=np.float32)
    if samples.size < int(sample_rate * min_duration_seconds):
        return AudioFeatures()

    analysis_samples = _to_analysis_rate(samples, sample_rate)

    bpm: BPM | None = None
    key: Any | None = None
    try:
        raw_tempo = _detect_raw_tempo(analysis_samples, ANALYSIS_SAMPLE_RATE)
        if raw_tempo is not None:
            # One decimal place: the estimator's residual error is well below
            # 0.2 BPM, and finer digits are noise, not information.
            bpm = BPM(round(fold_tempo(raw_tempo, low=tempo_low, high=tempo_high), 1))
    except Exception:
        LOGGER.debug("Tempo detection failed", exc_info=True)
    try:
        key = _detect_key(analysis_samples, ANALYSIS_SAMPLE_RATE)
    except Exception:
        LOGGER.debug("Key detection failed", exc_info=True)
    return AudioFeatures(bpm=bpm, key=key)


def _to_analysis_rate(samples: Any, sample_rate: int) -> Any:
    """Resample once to :data:`ANALYSIS_SAMPLE_RATE` with a fast resampler."""
    import librosa

    if sample_rate == ANALYSIS_SAMPLE_RATE:
        return samples
    return librosa.resample(
        samples,
        orig_sr=sample_rate,
        target_sr=ANALYSIS_SAMPLE_RATE,
        res_type="soxr_lq",
    )


def _detect_raw_tempo(samples: Any, sample_rate: int) -> float | None:
    """Return the raw tempo estimate (before folding), or ``None``.

    Mirrors ``librosa.feature.tempo`` (median-aggregated autocorrelation
    tempogram weighted by the pseudo-log-normal 120 BPM prior) but refines
    the winning lag with parabolic interpolation, giving sub-0.2 BPM
    resolution at club tempos without tiny (slow) onset hops.
    """
    import librosa
    import numpy as np

    hop = TEMPO_HOP_LENGTH
    onset_envelope = librosa.onset.onset_strength(
        y=samples, sr=sample_rate, hop_length=hop
    )
    if onset_envelope.size == 0 or not np.any(onset_envelope):
        return None

    win_length = max(
        int(librosa.time_to_frames(TEMPO_AC_SECONDS, sr=sample_rate, hop_length=hop)),
        1,
    )
    tempogram = librosa.feature.tempogram(
        onset_envelope=onset_envelope,
        sr=sample_rate,
        hop_length=hop,
        win_length=win_length,
    )
    curve = np.median(tempogram, axis=-1)

    # Same weighting as librosa.feature.tempo: pseudo-log-normal prior around
    # 120 BPM, and nothing above 250 BPM.
    bpms = librosa.tempo_frequencies(win_length, hop_length=hop, sr=sample_rate)
    logprior = -0.5 * ((np.log2(bpms) - np.log2(120.0)) / 1.0) ** 2
    above_max = int(np.argmax(bpms < 250.0))
    logprior[:above_max] = -np.inf
    score = np.log1p(1e6 * curve) + logprior

    best = int(np.argmax(score))
    if not math.isfinite(score[best]):
        return None
    # Interpolate the prior-weighted score: it is smooth around the winning
    # lag, while the raw autocorrelation curve is asymmetric (its vertex sits
    # up to 0.35 BPM off, empirically ~0.2 BPM on the score curve).
    lag = best + _parabolic_offset(score, best)
    if lag <= 0:
        return None
    raw = 60.0 * (sample_rate / hop) / lag
    return raw if math.isfinite(raw) and raw > 0 else None


def _parabolic_offset(curve: Any, index: int) -> float:
    """Sub-bin peak offset at ``index`` (0 when at an edge or degenerate)."""
    if index <= 0 or index >= len(curve) - 1:
        return 0.0
    left = float(curve[index - 1])
    center = float(curve[index])
    right = float(curve[index + 1])
    denominator = left - 2.0 * center + right
    if denominator == 0.0 or not math.isfinite(denominator):
        return 0.0
    offset = 0.5 * (left - right) / denominator
    return max(-0.5, min(0.5, offset))


def _detect_key(samples: Any, sample_rate: int) -> Any | None:
    """Match the mean chromagram against Krumhansl–Schmuckler profiles."""
    import librosa

    # Constant-Q chroma: unlike chroma_stft, its log-frequency bins keep a
    # pure tone's energy inside one semitone (stft leakage into neighbours
    # can flip a C-major triad to E minor). Runs on the shared 22.05 kHz
    # analysis copy with a coarse hop — the key is averaged over the whole
    # clip, so fine time resolution buys nothing.
    chroma = librosa.feature.chroma_cqt(
        y=samples, sr=sample_rate, hop_length=KEY_HOP_LENGTH
    )
    if chroma.size == 0:
        return None
    chroma_mean = [float(value) for value in chroma.mean(axis=1)]
    return _detect_key_from_chroma(chroma_mean)


def _detect_key_from_chroma(chroma: Any) -> CamelotKey | None:
    """Correlate a 12-bin chroma vector (index 0 = C) against KS profiles."""
    import numpy as np

    chroma_mean = np.asarray(chroma, dtype=np.float64)
    if chroma_mean.shape != (12,) or not np.any(chroma_mean):
        return None

    best_score = -2.0
    best_root = 0
    best_mode = "major"
    for root in range(12):
        rotated = np.array([chroma_mean[(root + step) % 12] for step in range(12)])
        for mode, profile in (
            ("major", _KRUMHANSL_MAJOR),
            ("minor", _KRUMHANSL_MINOR),
        ):
            score = _pearson(rotated, np.array(profile))
            if score > best_score:
                best_score = score
                best_root = root
                best_mode = mode

    if not math.isfinite(best_score):
        return None
    LOGGER.debug(
        "Detected key %s %s (score %.3f)",
        _PITCH_CLASSES[best_root],
        best_mode,
        best_score,
    )
    if best_mode == "major":
        return CamelotKey(_MAJOR_CAMELOT[best_root])
    return CamelotKey(_MINOR_CAMELOT[best_root])


def _pearson(left: Any, right: Any) -> float:
    """Pearson correlation without numpy.corrcoef (avoids NaN amplification)."""
    import numpy as np

    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = math.sqrt(
        float(np.dot(left_centered, left_centered))
        * float(np.dot(right_centered, right_centered))
    )
    if denominator == 0.0:
        return float("nan")
    return float(np.dot(left_centered, right_centered)) / denominator


class LibrosaFeatureExtractor(IFeatureExtractor):
    """Runs :func:`analyze_pcm` on decoded buffers.

    Instances hold only plain configuration values so they can be pickled and
    shipped to a ``ProcessPoolExecutor`` worker. The heavy librosa import
    happens inside the worker, never in the event-loop process.
    """

    def __init__(
        self,
        *,
        tempo_low: float = TEMPO_FOLD_LOW,
        tempo_high: float = TEMPO_FOLD_HIGH,
        min_duration_seconds: float = MIN_ANALYSIS_SECONDS,
    ) -> None:
        if tempo_low <= 0 or tempo_high < tempo_low:
            raise ValueError("tempo band must satisfy 0 < low <= high")
        if min_duration_seconds <= 0:
            raise ValueError("min_duration_seconds must be positive")
        self.tempo_low = tempo_low
        self.tempo_high = tempo_high
        self.min_duration_seconds = min_duration_seconds

    def extract(self, audio: AudioBuffer) -> AudioFeatures:
        """Return ``(bpm, key)`` for one decoded window; fields may be ``None``."""
        return analyze_pcm(
            audio.pcm_bytes,
            audio.sample_rate,
            tempo_low=self.tempo_low,
            tempo_high=self.tempo_high,
            min_duration_seconds=self.min_duration_seconds,
        )


__all__ = [
    "MIN_ANALYSIS_SECONDS",
    "TEMPO_FOLD_HIGH",
    "TEMPO_FOLD_LOW",
    "LibrosaFeatureExtractor",
    "analyze_pcm",
    "fold_tempo",
]
