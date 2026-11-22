"""GPU audio embeddings via HuggingFace CLAP (``laion/clap-htsat-unfused``).

The model is **lazy-loaded on first use** so fast CLI commands (``dig stats``,
``dig list-tracks``) never pay the load cost. Inference runs under
``torch.inference_mode()`` with ``torch.amp.autocast("cuda", dtype=float16)``
whenever CUDA is available, vectors are L2-normalized, cast to ``float16`` and
returned as domain :class:`EmbeddingVector` objects. If CUDA is requested but
unavailable (CI, CPU-only machine) the embedder falls back to CPU.

The checkpoint truncates longer audio to a *random* 10 s crop
(``truncation="rand_trunc"``). To keep embeddings deterministic and
representative of the full 30 s preview, audio is sliced into fixed
non-overlapping 10 s windows (up to 3 for a 30 s preview); the window
embeddings are averaged per track and re-normalized.

Checkpoint note: ``laion/clap-htsat-unfused`` is the default because the
``laion/larger_clap_music`` checkpoint on the Hugging Face hub ships an
**untrained audio tower** (verified 2026-11: all 151 audio-side biases and the
whole projection MLP are at their initial values, logit_scale=0.027, and real
techno previews score ~0.0 cosine against "techno music"). ``htsat-unfused``
is the canonical checkpoint used throughout the transformers docs: 48 kHz,
512-dim, trained, and its zero-shot audio-text discrimination and audio-audio
spread (0.3-0.8 for unrelated music) are healthy.

torch and transformers are imported *inside* the load path only: importing
this module must stay cheap.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Any

from domain.entities.track import AudioBuffer
from domain.interfaces.audio_engine import IAudioEmbedder
from domain.value_objects.audio_features import EmbeddingVector

from ..errors import EmbeddingError

LOGGER = logging.getLogger(__name__)

# The canonical trained CLAP checkpoint. Do NOT use `laion/larger_clap_music`:
# its hub checkpoint contains an untrained audio tower (see module docstring).
DEFAULT_CLAP_MODEL_ID = "laion/clap-htsat-unfused"
CLAP_EMBEDDING_DIMENSION = 512
CLAP_SAMPLE_RATE = 48_000
MAX_BATCH_SIZE = 48
#: The model's native input length (``max_length_s=10`` at 48 kHz). Longer
#: audio is split into deterministic non-overlapping windows of this size.
MAX_WINDOW_SAMPLES = 480_000


class ClapAudioEmbedder(IAudioEmbedder):
    """Bounded, FP16, L2-normalized CLAP audio embedder."""

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_CLAP_MODEL_ID,
        device: str = "cuda",
        batch_size: int = 16,
        embedding_dimension: int = CLAP_EMBEDDING_DIMENSION,
        model_factory: Any | None = None,
        cuda_available: bool | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._model_id = model_id
        self._requested_device = device
        self._batch_size = min(batch_size, MAX_BATCH_SIZE)
        self._embedding_dimension = embedding_dimension
        self._model_factory = model_factory
        # Test seam: None defers to torch.cuda.is_available() at load time.
        self._cuda_available = cuda_available
        self._lock = threading.Lock()
        self._torch: Any | None = None
        self._model: Any | None = None
        self._processor: Any | None = None
        self._device: Any | None = None

    # ------------------------------------------------------------- properties

    @property
    def model_id(self) -> str:
        """Hugging Face model identifier."""
        return self._model_id

    @property
    def embedding_dimension(self) -> int:
        """Width of the returned vectors (512 for CLAP)."""
        return self._embedding_dimension

    @property
    def resolved_device(self) -> Any | None:
        """The torch device picked at load time, or ``None`` before loading."""
        return self._device

    @property
    def batch_size(self) -> int:
        """Configured micro-batch size, clamped to :data:`MAX_BATCH_SIZE`."""
        return self._batch_size

    @batch_size.setter
    def batch_size(self, value: int) -> None:
        """Adjust the micro-batch size at runtime (turbo mode).

        Raises ``TypeError``/``ValueError`` for invalid input and clamps larger
        values to :data:`MAX_BATCH_SIZE` so a job can never exceed the VRAM
        budget this class was designed around.
        """
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("batch_size must be an int")
        if value < 1:
            raise ValueError("batch_size must be at least 1")
        self._batch_size = min(value, MAX_BATCH_SIZE)

    # ----------------------------------------------------------------- public

    def embed(self, audio: AudioBuffer) -> EmbeddingVector:
        """Embed one audio window."""
        return self.embed_batch([audio])[0]

    def embed_batch(self, audios: Sequence[AudioBuffer]) -> Sequence[EmbeddingVector]:
        """Embed a batch, averaging deterministic 10 s windows per track.

        The checkpoint uses ``truncation="rand_trunc"`` (a random 10 s crop of
        longer audio), so a raw 30 s preview would embed a *random* third of
        the music — different on every run. Instead, audio longer than 10 s is
        sliced into non-overlapping 10 s windows (30 s → exactly 3), embedded
        in FP16 micro-batches, and the per-track window embeddings are averaged
        and re-normalized. Same audio in, same vector out.
        """
        if not audios:
            return ()
        torch, model, processor, device = self._ensure_loaded()
        import numpy as np

        waveforms = [
            np.frombuffer(audio.pcm_bytes, dtype=np.float32) for audio in audios
        ]
        sample_rates = {audio.sample_rate for audio in audios}
        if len(sample_rates) > 1:
            raise EmbeddingError(
                f"batch mixes sample rates {sorted(sample_rates)}; resample first"
            )
        sample_rate = sample_rates.pop()

        windows, window_counts = self._split_into_windows(waveforms)

        window_vectors: list[EmbeddingVector] = []
        with torch.inference_mode():
            for start in range(0, len(windows), self._batch_size):
                chunk = windows[start : start + self._batch_size]
                window_vectors.extend(
                    self._embed_chunk_backoff(
                        torch, model, processor, device, chunk, sample_rate
                    )
                )
        return self._average_windows(window_vectors, window_counts)

    @staticmethod
    def _split_into_windows(
        waveforms: Sequence[Any],
    ) -> tuple[list[Any], list[int]]:
        """Slice each waveform into ≤3 non-overlapping 10 s windows.

        Returns the flat window list plus one count per input waveform so
        window embeddings can be regrouped per track.
        """
        windows: list[Any] = []
        counts: list[int] = []
        for waveform in waveforms:
            total = len(waveform)
            if total <= MAX_WINDOW_SAMPLES:
                windows.append(waveform)
                counts.append(1)
                continue
            slices = [
                waveform[start : start + MAX_WINDOW_SAMPLES]
                for start in range(0, total, MAX_WINDOW_SAMPLES)
            ]
            windows.extend(slices)
            counts.append(len(slices))
        return windows, counts

    @staticmethod
    def _average_windows(
        vectors: Sequence[EmbeddingVector], counts: Sequence[int]
    ) -> list[EmbeddingVector]:
        """Mean-pool each track's window vectors and L2-normalize."""
        import numpy as np

        if len(vectors) != sum(counts):
            raise EmbeddingError(
                f"got {len(vectors)} window embeddings for {sum(counts)} windows"
            )
        averaged: list[EmbeddingVector] = []
        offset = 0
        for count in counts:
            block = vectors[offset : offset + count]
            offset += count
            if count == 1:
                averaged.append(block[0])
                continue
            stack = np.asarray([v.values for v in block], dtype=np.float32)
            mean = stack.mean(axis=0)
            norm = float(np.linalg.norm(mean))
            if norm <= 0.0:
                raise EmbeddingError("window embeddings cancelled out to zero")
            mean = (mean / norm).astype(np.float16)
            averaged.append(
                EmbeddingVector(
                    values=tuple(float(x) for x in mean),
                    dimension=len(mean),
                )
            )
        return averaged

    def embed_text(self, query: str) -> EmbeddingVector:
        """Embed a free-text query into the audio-embedding space."""
        if not query.strip():
            raise ValueError("query must not be empty")
        torch, model, processor, device = self._ensure_loaded()
        try:
            inputs = processor(text=query.strip(), return_tensors="pt", padding=True)
        except TypeError:
            inputs = processor(texts=[query.strip()], return_tensors="pt", padding=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            if device.type == "cuda":
                with torch.amp.autocast("cuda", dtype=torch.float16):
                    features = model.get_text_features(**inputs)
            else:
                features = model.get_text_features(**inputs)
            features = self._extract_projection(torch, features, batch_size=1)
            features = torch.nn.functional.normalize(features, p=2, dim=-1)
            features = features.to(torch.float16).cpu()
        rows = features.tolist()
        return EmbeddingVector(
            values=tuple(rows[0]), dimension=self._embedding_dimension
        )

    # ------------------------------------------------------------------ infra

    def _extract_projection(self, torch: Any, features: Any, *, batch_size: int) -> Any:
        """Pull the projected ``(batch, dim)`` tensor out of a CLAP output.

        ``ClapModel.get_audio_features``/``get_text_features`` return either a
        bare tensor or a ``BaseModelOutputWithPooling`` whose ``pooler_output``
        holds the projected features (transformers >= 4.x behaviour, and the
        default in transformers 5.x). Accept both, plus tuple-shaped returns.
        """
        tensor = features
        if not isinstance(tensor, torch.Tensor):
            tensor = getattr(tensor, "pooler_output", None)
            if tensor is None and isinstance(features, (tuple, list)) and features:
                tensor = features[0]
            if not isinstance(tensor, torch.Tensor):
                raise EmbeddingError(
                    f"CLAP model returned {type(features).__name__} without a "
                    "usable pooler_output tensor"
                )
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        expected = (batch_size, self._embedding_dimension)
        if tuple(tensor.shape) != expected:
            raise EmbeddingError(
                f"CLAP projection has shape {tuple(tensor.shape)}, expected {expected}"
            )
        return tensor

    def _embed_chunk_backoff(
        self,
        torch: Any,
        model: Any,
        processor: Any,
        device: Any,
        chunk: Sequence[Any],
        sample_rate: int,
    ) -> list[EmbeddingVector]:
        """Embed one chunk, halving it on CUDA OOM until it fits (floor 8)."""
        try:
            return self._embed_chunk(
                torch, model, processor, device, chunk, sample_rate
            )
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            if len(chunk) <= 8:
                raise
            midpoint = len(chunk) // 2
            LOGGER.warning(
                "CUDA OOM at batch %d; retrying as %d + %d",
                len(chunk),
                midpoint,
                len(chunk) - midpoint,
            )
            return self._embed_chunk_backoff(
                torch, model, processor, device, chunk[:midpoint], sample_rate
            ) + self._embed_chunk_backoff(
                torch, model, processor, device, chunk[midpoint:], sample_rate
            )

    def _embed_chunk(
        self,
        torch: Any,
        model: Any,
        processor: Any,
        device: Any,
        chunk: Sequence[Any],
        sample_rate: int,
    ) -> list[EmbeddingVector]:
        inputs = self._prepare_inputs(processor, chunk, sample_rate)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        if device.type == "cuda":
            # FP16 autocast keeps peak VRAM well under 4 GB on a 6 GB card.
            with torch.amp.autocast("cuda", dtype=torch.float16):
                features = model.get_audio_features(**inputs)
        else:
            features = model.get_audio_features(**inputs)
        features = self._extract_projection(torch, features, batch_size=len(chunk))
        features = torch.nn.functional.normalize(features, p=2, dim=-1)
        features = features.to(torch.float16).cpu()
        return [
            EmbeddingVector(values=tuple(row), dimension=self._embedding_dimension)
            for row in features.tolist()
        ]

    @staticmethod
    def _prepare_inputs(
        processor: Any,
        chunk: Sequence[Any],
        sample_rate: int,
    ) -> dict[str, Any]:
        """Call the processor with whichever keyword it accepts."""
        try:
            inputs = processor(
                audio=list(chunk),
                sampling_rate=sample_rate,
                return_tensors="pt",
                padding=True,
            )
        except TypeError:
            inputs = processor(
                audios=list(chunk),
                sampling_rate=sample_rate,
                return_tensors="pt",
                padding=True,
            )
        if not hasattr(inputs, "items"):
            inputs = inputs.data  # BatchEncoding → dict-like
        return dict(inputs)

    def _ensure_loaded(self) -> tuple[Any, Any, Any, Any]:
        """Load torch/model/processor once; safe under concurrency."""
        if self._torch is not None:
            return self._torch, self._model, self._processor, self._device
        with self._lock:
            if self._torch is not None:
                return self._torch, self._model, self._processor, self._device
            import torch

            device = self._resolve_device(torch)
            LOGGER.info("Loading CLAP model %s on %s", self._model_id, device)
            if self._model_factory is not None:
                bundle = self._model_factory()
                model = bundle.model
                processor = bundle.processor
            else:
                from transformers import ClapModel, ClapProcessor

                model = ClapModel.from_pretrained(self._model_id)
                processor = ClapProcessor.from_pretrained(self._model_id)
            model = model.to(device)
            model.eval()
            if device.type == "cuda":
                # Fixed shapes every batch: let cuDNN pick the fastest kernels.
                torch.backends.cudnn.benchmark = True
            self._torch = torch
            self._model = model
            self._processor = processor
            self._device = device
            return torch, model, processor, device

    def _resolve_device(self, torch: Any) -> Any:
        cuda_ready = (
            torch.cuda.is_available()
            if self._cuda_available is None
            else self._cuda_available
        )
        requested = self._requested_device
        if requested in (None, "", "auto"):
            requested = "cuda" if cuda_ready else "cpu"
        device = torch.device(requested)
        if device.type == "cuda" and not cuda_ready:
            LOGGER.warning(
                "DEVICE=cuda requested but CUDA is unavailable; falling back to CPU"
            )
            device = torch.device("cpu")
        return device


__all__ = [
    "CLAP_EMBEDDING_DIMENSION",
    "CLAP_SAMPLE_RATE",
    "DEFAULT_CLAP_MODEL_ID",
    "MAX_BATCH_SIZE",
    "MAX_WINDOW_SAMPLES",
    "ClapAudioEmbedder",
]
