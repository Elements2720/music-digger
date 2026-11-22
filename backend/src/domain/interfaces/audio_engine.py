"""Audio decoding, feature extraction, embedding, segmentation, and downloading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Coroutine, Sequence
from pathlib import Path
from typing import Any, BinaryIO

from ..entities.dj_set import DownloadedSet
from ..entities.track import AudioBuffer, Track, TrackReference
from ..value_objects.audio_features import (
    AudioFeatures,
    EmbeddingVector,
    TimeRange,
)


class IAudioDecoder(ABC):
    """Turns compressed audio into raw PCM held in RAM only for analysis."""

    @abstractmethod
    async def decode(
        self,
        source: BinaryIO,
        *,
        sample_rate: int = 48_000,
        channels: int = 1,
    ) -> AudioBuffer:
        """Decode a complete short stream already held in memory."""

    @abstractmethod
    async def decode_url(
        self,
        url: str,
        *,
        sample_rate: int = 48_000,
        channels: int = 1,
    ) -> AudioBuffer:
        """Download a short remote preview into memory and decode it.

        Implementations must never spill audio bytes to disk and must bound
        their download concurrency internally.
        """

    @abstractmethod
    async def decode_segment(
        self,
        path: Path,
        time_range: TimeRange,
        *,
        sample_rate: int = 48_000,
        channels: int = 1,
    ) -> AudioBuffer:
        """Decode only ``time_range`` from a file on disk.

        This is the RAM-safe path for full DJ sets: implementations must use
        FFmpeg seek/duration flags instead of decoding the entire file.
        """


class IFeatureExtractor(ABC):
    """Extracts tempo and key from one decoded audio window."""

    @abstractmethod
    def extract(self, audio: AudioBuffer) -> AudioFeatures:
        """Return detected features; individual fields may be ``None``."""


class IAudioEmbedder(ABC):
    """Produces CLAP audio embeddings for similarity search."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Hugging Face model identifier, for example ``laion/clap-htsat-unfused``."""

    @property
    @abstractmethod
    def embedding_dimension(self) -> int:
        """Width of the vectors returned by this embedder."""

    @abstractmethod
    def embed(self, audio: AudioBuffer) -> EmbeddingVector:
        """Embed one audio window."""

    @abstractmethod
    def embed_batch(self, audios: Sequence[AudioBuffer]) -> Sequence[EmbeddingVector]:
        """Embed a bounded batch.

        Implementations must cap batches at 32, use CUDA FP16 when available,
        and keep peak VRAM below 4 GB.
        """

    def embed_text(self, query: str) -> EmbeddingVector:
        """Embed a free-text query into the same space as audio embeddings.

        Only multimodal models can implement this; the default raises so
        single-modality embedders stay honest about their capabilities.
        """
        raise NotImplementedError("this embedder does not support text queries")


class IAudioSegmenter(ABC):
    """Plans overlapping analysis windows across a DJ set."""

    @abstractmethod
    def plan_segments(
        self,
        total_duration_seconds: float,
        *,
        window_seconds: float = 30.0,
        hop_seconds: float = 15.0,
    ) -> Sequence[TimeRange]:
        """Return analysis windows without loading audio into memory."""

    @abstractmethod
    def detect_passages(
        self,
        path: Path,
        total_duration_seconds: float,
    ) -> Sequence[TimeRange]:
        """Detect musically coherent passages in a set file on disk.

        Implementations must stream (16 kHz mono is plenty) so a three-hour
        set never loads fully into RAM, and must return ordered, non-overlapping
        ranges covering the set, each within a realistic DJ passage length.
        """


class IFingerprinter(ABC):
    """Computes and resolves exact audio fingerprints."""

    @abstractmethod
    def compute(self, audio: AudioBuffer) -> str:
        """Return a stable fingerprint string for an audio window."""

    @abstractmethod
    def identify(self, audio: AudioBuffer) -> Track | None:
        """Return an exact catalog match, or ``None`` when unidentified."""

    def identify_async(
        self, audio: AudioBuffer
    ) -> Coroutine[Any, Any, TrackReference | None]:
        """Async identification seam for async-only services (e.g. shazamio).

        Returns a lightweight :class:`TrackReference` on match or ``None``.
        The default runs the synchronous :meth:`identify` on a worker thread;
        implementations backed by async services override it.
        """
        import asyncio

        async def _run() -> TrackReference | None:
            track = await asyncio.to_thread(self.identify, audio)
            if track is None:
                return None
            return TrackReference(artist=track.artist, title=track.title)

        return _run()


class ISetDownloader(ABC):
    """Downloads a full DJ set to disk for window-by-window analysis."""

    @abstractmethod
    async def download(self, url: str, destination: Path) -> Path:
        """Download ``url`` to ``destination`` and return the final path.

        Implementations must stream to disk, never buffer the whole set in RAM.
        """

    @abstractmethod
    async def fetch_set(
        self,
        source: str,
        destination_dir: Path,
        *,
        fetch_comments: bool = True,
    ) -> DownloadedSet:
        """Resolve a DJ set source (URL or local file path) to a file on disk.

        Remote sources are downloaded into ``destination_dir`` and the returned
        :class:`DownloadedSet` is marked temporary so the caller can delete the
        audio after analysis. Existing local files are returned in place with
        ``is_temporary=False``. ``description``/``comments`` are populated when
        ``fetch_comments`` is True and the source exposes them.
        """
