"""Transition segmentation for long DJ sets.

Plays the DigDeeper role of splitting a multi-hour recording into musically
coherent passages. The audio is decoded **once** as a 16 kHz mono stream in
bounded blocks (a 3 h set peaks at ~40 MB of PCM per block instead of the
~690 MB a full decode would need), pooled into a tiny ~2 fps feature matrix
(spectral flux + chroma + MFCC, ≤ ~25 MB even for 3 h), and a Foote-style
**checkerboard kernel** novelty score is evaluated over candidate passage
lengths (90-360 s). Peaks in the novelty curve become passage boundaries;
passages are then normalized to realistic DJ lengths (short ones merged,
long flat regions subdivided evenly).

All heavy work is synchronous and safe to run through ``asyncio.to_thread``
from the use case; ffmpeg runs as a subprocess via an injectable stream
factory so tests can feed synthetic PCM without touching the network.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterator, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from domain.interfaces.audio_engine import IAudioSegmenter
from domain.value_objects.audio_features import TimeRange

from ..errors import AudioDecodeError, FFmpegNotFoundError

LOGGER = logging.getLogger(__name__)

#: Segmentation only needs spectral shape, not pitch fidelity: 16 kHz mono
#: keeps peak RAM under ~600 MB even for a 3-hour set.
SEGMENT_SAMPLE_RATE = 16_000
#: Novelty features per second. ~2 fps is plenty for 90-360 s passages and
#: keeps the whole-set feature matrix in the low megabytes.
FEATURE_FPS = 2.0
#: Audio block decoded at once (streamed through ffmpeg stdout).
BLOCK_SECONDS = 600.0
#: Realistic DJ passage bounds: transitions every 1.5-6 minutes.
MIN_PASSAGE_SECONDS = 90.0
MAX_PASSAGE_SECONDS = 360.0
#: Candidate passage lengths for the checkerboard kernel, in seconds.
CANDIDATE_PASSAGE_SECONDS: tuple[float, ...] = (90.0, 120.0, 180.0, 240.0, 300.0, 360.0)
#: Blocks are processed with a small lookback so STFT frames spanning block
#: edges are not double counted or dropped.
BLOCK_OVERLAP_SECONDS = 4.0

StftHop = 512
StftNfft = 2048
PoolGroup = int(SEGMENT_SAMPLE_RATE / StftHop / FEATURE_FPS)  # ~15.6 -> 16 frames
_FLUX_DIM = 1
_CHROMA_DIM = 12
_MFCC_DIM = 13

StreamFactory = Callable[[Sequence[str]], Iterator[bytes]]


def default_stream_factory(ffmpeg_bin: str) -> StreamFactory:
    """Spawn one blocking ffmpeg subprocess and yield its PCM stdout."""

    def factory(args: Sequence[str]) -> Iterator[bytes]:
        import subprocess

        try:
            process = subprocess.Popen(
                [ffmpeg_bin, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise FFmpegNotFoundError(
                f"ffmpeg binary not found ({ffmpeg_bin!r}); install FFmpeg and "
                "make sure it is on PATH"
            ) from exc
        except OSError as exc:
            raise AudioDecodeError(f"ffmpeg could not be started: {exc}") from exc

        assert process.stdout is not None
        try:
            while True:
                chunk = process.stdout.read(1_048_576)
                if not chunk:
                    break
                yield chunk
            returncode = process.wait(timeout=30)
            if returncode != 0:
                stderr = process.stderr.read() if process.stderr else b""
                detail = stderr.decode("utf-8", "replace").strip().splitlines()
                tail = detail[-1] if detail else "no stderr output"
                raise AudioDecodeError(f"ffmpeg failed with code {returncode}: {tail}")
        finally:
            if process.stderr:
                process.stderr.close()
            if process.stdout:
                process.stdout.close()
            if process.poll() is None:
                process.kill()

    return factory


class SetSegmenter(IAudioSegmenter):
    """Stream-based novelty segmentation of a DJ set file on disk."""

    def __init__(
        self,
        *,
        ffmpeg_bin: str = "ffmpeg",
        sample_rate: int = SEGMENT_SAMPLE_RATE,
        feature_fps: float = FEATURE_FPS,
        block_seconds: float = BLOCK_SECONDS,
        min_passage_seconds: float = MIN_PASSAGE_SECONDS,
        max_passage_seconds: float = MAX_PASSAGE_SECONDS,
        candidate_passage_seconds: Sequence[float] = CANDIDATE_PASSAGE_SECONDS,
        stream_factory: StreamFactory | None = None,
    ) -> None:
        if sample_rate < 1:
            raise ValueError("sample_rate must be positive")
        if feature_fps <= 0:
            raise ValueError("feature_fps must be positive")
        if min_passage_seconds <= 0 or max_passage_seconds < min_passage_seconds:
            raise ValueError("passage bounds must satisfy 0 < min <= max")
        self._ffmpeg_bin = ffmpeg_bin
        self._sample_rate = sample_rate
        self._feature_fps = feature_fps
        self._block_seconds = block_seconds
        self._min_passage = min_passage_seconds
        self._max_passage = max_passage_seconds
        self._candidates = tuple(candidate_passage_seconds)
        self._stream_factory = stream_factory or default_stream_factory(ffmpeg_bin)

    # ------------------------------------------------------------------ API

    def plan_segments(
        self,
        total_duration_seconds: float,
        *,
        window_seconds: float = 30.0,
        hop_seconds: float = 15.0,
    ) -> Sequence[TimeRange]:
        """Return fixed analysis windows covering the set (interface method)."""
        if total_duration_seconds <= 0:
            raise ValueError("total_duration_seconds must be positive")
        if window_seconds <= 0 or hop_seconds <= 0:
            raise ValueError("window_seconds and hop_seconds must be positive")
        windows: list[TimeRange] = []
        start = 0.0
        while start < total_duration_seconds - 1e-9:
            end = min(start + window_seconds, total_duration_seconds)
            if end - start <= 0:
                break
            windows.append(TimeRange(start, end))
            start += hop_seconds
        return tuple(windows)

    def detect_passages(
        self,
        path: Path,
        total_duration_seconds: float,
    ) -> Sequence[TimeRange]:
        """Detect ordered, non-overlapping passages in ``path``."""
        if total_duration_seconds <= 0:
            raise ValueError("total_duration_seconds must be positive")
        features, feature_times = self._stream_features(path, total_duration_seconds)
        if len(features) == 0:
            return (TimeRange(0.0, total_duration_seconds),)

        boundaries = self._pick_boundaries(
            self._novelty_curve(features), feature_times, total_duration_seconds
        )
        return self._build_passages(boundaries, total_duration_seconds)

    # -------------------------------------------------------------- features

    def _ffmpeg_args(self, path: Path) -> list[str]:
        return [
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vn",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ac",
            "1",
            "-ar",
            str(self._sample_rate),
            "pipe:1",
        ]

    def _stream_features(
        self, path: Path, total_duration_seconds: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Stream the file through ffmpeg and return pooled features + times.

        Returns ``(features, times)`` where ``features`` has shape
        ``(frames, dims)`` (L2-normalized rows) and ``times[i]`` is the time of
        the frame start in seconds.
        """
        block_samples = int(self._block_seconds * self._sample_rate)
        overlap_samples = int(BLOCK_OVERLAP_SECONDS * self._sample_rate)

        feature_blocks: list[np.ndarray] = []
        time_blocks: list[np.ndarray] = []
        covered_until = 0.0  # seconds fully processed so far
        buffer = bytearray()
        bytes_per_sample = 4

        for chunk in self._stream_factory(self._ffmpeg_args(path)):
            buffer.extend(chunk)
            while len(buffer) >= (block_samples + overlap_samples) * bytes_per_sample:
                block = np.frombuffer(
                    buffer[: (block_samples + overlap_samples) * bytes_per_sample],
                    dtype=np.float32,
                )
                frames, frame_times = self._block_features(block)
                if frames.size:
                    # `frame_times` are block-relative; the +overlap lookahead
                    # only exists so frames near the block edge are complete.
                    keep = frame_times < self._block_seconds
                    feature_blocks.append(frames[keep])
                    time_blocks.append(frame_times[keep] + covered_until)
                covered_until += self._block_seconds
                del buffer[: block_samples * bytes_per_sample]

        if buffer:
            block = np.frombuffer(buffer, dtype=np.float32)
            frames, frame_times = self._block_features(block)
            if frames.size:
                # The final block was never processed, so keep every frame;
                # its start is exactly `covered_until` (== samples dropped so
                # far), which the +offset already accounts for.
                feature_blocks.append(frames)
                time_blocks.append(frame_times + covered_until)

        if not feature_blocks:
            return np.zeros((0, 0), dtype=np.float32), np.zeros(0)

        features = np.concatenate(feature_blocks, axis=0)
        times = np.concatenate(time_blocks)
        norms = np.linalg.norm(features, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        features = features / norms
        # A declared duration longer than the actual audio must not leave the
        # tail uncovered; clamp frame times to the declared duration.
        return features.astype(np.float32), np.minimum(
            times, max(total_duration_seconds, 0.0)
        )

    def _block_features(self, block: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Compute pooled flux+chroma+mfcc features for one PCM block."""
        import librosa

        samples = np.asarray(block, dtype=np.float32)
        if samples.size < StftNfft:
            return np.zeros((0, 0), dtype=np.float32), np.zeros(0)

        common: dict[str, Any] = {
            "y": samples,
            "sr": self._sample_rate,
            "n_fft": StftNfft,
            "hop_length": StftHop,
            "center": False,
        }
        flux = librosa.onset.onset_strength(
            y=samples, sr=self._sample_rate, hop_length=StftHop, n_fft=StftNfft
        )
        chroma = librosa.feature.chroma_stft(**common)
        mfcc = librosa.feature.mfcc(**common, n_mfcc=_MFCC_DIM)

        frame_count = min(flux.size, chroma.shape[1], mfcc.shape[1])
        stacked = np.vstack(
            [
                flux[np.newaxis, :frame_count],
                chroma[:, :frame_count],
                mfcc[:, :frame_count],
            ]
        ).T.astype(np.float32)  # (frame_count, dims)

        # Pool ~16 STFT frames (0.5 s) into one novelty frame (~2 fps).
        groups = max(1, frame_count // PoolGroup)
        pooled = stacked[: groups * PoolGroup].reshape(
            groups, PoolGroup, stacked.shape[1]
        )
        features = pooled.mean(axis=1)
        frame_times = np.arange(groups, dtype=np.float64) * (
            PoolGroup * StftHop / self._sample_rate
        )
        return features, frame_times

    # --------------------------------------------------------------- novelty

    def _novelty_curve(self, features: np.ndarray) -> np.ndarray:
        """Checkerboard-kernel novelty, maximized over candidate lags.

        For a candidate passage length ``L`` (half-window ``h = L/2`` frames)
        and boundary position ``t``, the checkerboard score is

            Nov(t) = sum_{i,j} K(i,j) * S(t-h+i, t-h+j)

        with ``+1`` for same-side kernel cells and ``-1`` across the boundary.
        Expanding the similarity ``S(a, b) = X[a] . X[b]`` by lag collapses the
        double sum into weighted boxcar sums of the lag correlation ``R(l, t)``,
        which keeps memory at O(frames) instead of materializing a self-
        similarity matrix.
        """
        total_frames = features.shape[0]
        novelty = np.full(total_frames, -np.inf, dtype=np.float64)
        frame_duration = 1.0 / self._feature_fps

        for candidate in self._candidates:
            half = round(candidate * self._feature_fps / 2.0)
            if half < 2 or 2 * half > total_frames:
                continue
            score = self._checkerboard_scores(features, half)
            if score.size == 0:
                continue
            valid = novelty[half : half + score.size]
            np.maximum(valid, score, out=valid)
            novelty[half : half + score.size] = valid

        novelty[~np.isfinite(novelty)] = 0.0
        # Candidate lags overlap; the max over lags can be noisy at the very
        # edges, so smooth with a small centered moving average (~5 s).
        return _moving_average(novelty, round(5.0 / frame_duration))

    @staticmethod
    def _checkerboard_scores(features: np.ndarray, half: int) -> np.ndarray:
        """Checkerboard novelty for one half-window size, all valid positions."""
        total_frames = features.shape[0]
        span = 2 * half
        # Per-lag local correlation R(l, t) = X[t] . X[t + l].
        lag_weights = np.empty(span, dtype=np.float64)
        novelty = np.zeros(total_frames - span + 1, dtype=np.float64)
        for lag in range(1, span):
            if lag >= half:
                lag_weights[lag] = -(span - lag)
            else:
                lag_weights[lag] = 2.0 * half - 3.0 * lag
            correlation = np.einsum(
                "ft,ft->f",
                features[: total_frames - lag],
                features[lag:],
                optimize=True,
            )
            cumulative = np.concatenate(([0.0], np.cumsum(correlation)))
            # Boxcar sum of correlation over positions [t, t + span - lag):
            # Nov(j) += c_l * (cum[j + span - lag] - cum[j]).
            positions = np.arange(0, len(novelty))
            box = cumulative[positions + span - lag] - cumulative[positions]
            novelty += lag_weights[lag] * box
        # The lag-0 diagonal is constant (L2-normalized rows) and drops out.
        return novelty

    # -------------------------------------------------------------- passages

    def _pick_boundaries(
        self,
        novelty: np.ndarray,
        feature_times: np.ndarray,
        total_duration_seconds: float,
    ) -> list[float]:
        """Pick novelty peaks, separated by at least ``min_passage``."""
        if novelty.size < 3 or float(novelty.std()) < 1e-9:
            return []  # flat/degenerate audio: rely on subdivision only
        # 3 sigma: stationary material produces tiny numerical ripples that
        # must not be mistaken for transitions.
        threshold = float(novelty.mean() + 3.0 * novelty.std())
        min_gap = max(1, round(self._min_passage * self._feature_fps))
        candidates = [
            index
            for index in range(1, novelty.size - 1)
            if novelty[index] >= novelty[index - 1]
            and novelty[index] >= novelty[index + 1]
            and novelty[index] >= threshold
        ]
        selected: list[int] = []
        for index in sorted(candidates, key=lambda i: novelty[i], reverse=True):
            if all(abs(index - chosen) >= min_gap for chosen in selected):
                selected.append(index)
        times = [
            float(feature_times[index])
            for index in sorted(selected)
            if 0.0 < float(feature_times[index]) < total_duration_seconds
        ]
        return times

    def _build_passages(
        self,
        boundaries: Sequence[float],
        total_duration_seconds: float,
    ) -> tuple[TimeRange, ...]:
        """Turn boundaries into passages honoring the min/max passage bounds."""
        edges = [0.0]
        for boundary in boundaries:
            r_b = round(boundary, 3)
            if 0.0 < r_b < total_duration_seconds:
                edges.append(r_b)
        # Always use unrounded total_duration_seconds for the terminal edge;
        # never round upward past total_duration_seconds.
        edges.append(total_duration_seconds)
        edges = sorted(set(edges))

        # Merge sections shorter than the minimum into their weaker neighbour
        # (greedily into the previous section; the first into the next).
        sections = list(edges)
        changed = True
        while changed and len(sections) > 2:
            changed = False
            for index in range(len(sections) - 1):
                if sections[index + 1] - sections[index] < self._min_passage:
                    if index == 0:
                        del sections[1]
                    elif index + 2 == len(sections):
                        del sections[-2]
                    else:
                        # Drop the boundary of the shorter adjacent section.
                        left = sections[index] - sections[index - 1]
                        right = sections[index + 2] - sections[index + 1]
                        del sections[index + 1 if right >= left else index]
                    changed = True
                    break

        # Subdivide long flat regions evenly; equal splits of a >max region
        # always stay >= min because max >= 2 * min by construction.
        passages: list[TimeRange] = []
        for s_idx, (start, end) in enumerate(pairwise(sections)):
            span = end - start
            if span <= 0:
                continue
            parts = max(1, math.ceil(span / self._max_passage - 1e-9))
            step = span / parts
            is_last_section = s_idx == len(sections) - 2
            for part in range(parts):
                piece_start = start + part * step
                piece_end = piece_start + step if part < parts - 1 else end
                is_last_piece = is_last_section and (part == parts - 1)

                p_start = round(piece_start, 3)
                if is_last_piece:
                    # NEVER round upward past total_duration_seconds
                    p_end = min(round(piece_end, 3), total_duration_seconds)
                    if p_end <= p_start:
                        p_start = round(max(0.0, p_end - 0.001), 3)
                else:
                    p_end = min(round(piece_end, 3), total_duration_seconds)

                if p_end > p_start:
                    passages.append(TimeRange(p_start, p_end))
        return tuple(passages)


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average with edge truncation (no padding)."""
    if window <= 1 or values.size <= window:
        return values
    half = window // 2
    kernel = np.ones(window, dtype=np.float64) / window
    smoothed = np.convolve(values, kernel, mode="same")
    smoothed[:half] = values[:half]
    smoothed[-half:] = values[-half:]
    return smoothed


__all__ = [
    "SEGMENT_SAMPLE_RATE",
    "SetSegmenter",
]
