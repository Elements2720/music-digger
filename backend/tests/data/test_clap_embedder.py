"""Tests for the CLAP embedder using a tiny injected model — no HF downloads."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest
import torch

from data.errors import EmbeddingError
from data.ml.clap_embedder import (
    DEFAULT_CLAP_MODEL_ID,
    MAX_BATCH_SIZE,
    ClapAudioEmbedder,
)
from domain.entities.track import AudioBuffer
from domain.value_objects.audio_features import EmbeddingVector

DIMENSION = 512
SAMPLE_RATE = 48_000


def test_default_model_id_excludes_the_broken_checkpoint() -> None:
    """Regression guard: `laion/larger_clap_music` ships an untrained tower.

    Its hub checkpoint stores an audio tower and projection MLP at their
    random-init values (all biases zero, logit_scale=0.027), which collapses
    every embedding onto one direction (~0.99 pairwise similarity). The
    default must stay on the canonical trained checkpoint.
    """
    assert DEFAULT_CLAP_MODEL_ID == "laion/clap-htsat-unfused"
    assert ClapAudioEmbedder().model_id == DEFAULT_CLAP_MODEL_ID


def make_buffer(seed: int = 0) -> AudioBuffer:
    # Content is irrelevant to the fake model; only the shape/rate matter.
    payload = bytes((seed + i) % 256 for i in range(64))
    return AudioBuffer(pcm_bytes=payload, sample_rate=SAMPLE_RATE)


def make_long_buffer(seconds: float = 30.0) -> AudioBuffer:
    """A deterministic 30 s (by default) float32 sine waveform."""
    import numpy as np

    count = int(SAMPLE_RATE * seconds)
    wave = (0.1 * np.sin(np.arange(count, dtype=np.float64) * 0.001)).astype(np.float32)
    return AudioBuffer(pcm_bytes=wave.tobytes(), sample_rate=SAMPLE_RATE)


@dataclass
class FakeBundle:
    model: Any
    processor: Any


@dataclass
class FakePoolerOutput:
    """Mimics transformers' ``BaseModelOutputWithPooling``."""

    pooler_output: Any


class FakeProcessor:
    """Mimics ClapProcessor: builds input tensors from raw waveforms."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        audio: Any = None,
        audios: Any = None,
        text: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        waveforms = audio if audio is not None else audios
        self.calls.append({"waveforms": waveforms, "text": text, **kwargs})
        if text is not None:
            return {
                "input_ids": torch.tensor([[1, 2, 3]]),
                "attention_mask": torch.tensor([[1, 1, 1]]),
            }
        count = len(waveforms)
        assert kwargs.get("sampling_rate") == SAMPLE_RATE
        return {
            "input_features": torch.zeros(count, 1, 64),
            "attention_mask": torch.ones(count, 64),
        }


class FakeModel:
    """Deterministic stand-in for ClapModel's feature towers."""

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []
        self.moved_to: list[Any] = []
        self.eval_called = False

    def to(self, device: Any) -> FakeModel:
        self.moved_to.append(device)
        return self

    def eval(self) -> FakeModel:
        self.eval_called = True
        return self

    def get_audio_features(self, **inputs: Any) -> torch.Tensor:
        count = inputs["input_features"].shape[0]
        self.batch_sizes.append(count)
        # Row i is a vector rotated by i degrees in the first two dims.
        rows = []
        for i in range(count):
            angle = math.radians(7.0 * i)
            rows.append([math.cos(angle), math.sin(angle)] + [0.1] * (DIMENSION - 2))
        return torch.tensor(rows, dtype=torch.float32)

    def get_text_features(self, **inputs: Any) -> torch.Tensor:
        return torch.tensor([[0.6, 0.8] + [0.05] * (DIMENSION - 2)])


def make_embedder(**kwargs: Any) -> tuple[ClapAudioEmbedder, FakeModel, FakeProcessor]:
    model = FakeModel()
    processor = FakeProcessor()
    embedder = ClapAudioEmbedder(
        model_factory=lambda: FakeBundle(model=model, processor=processor),
        **kwargs,
    )
    return embedder, model, processor


def make_modeloutput_embedder(
    **kwargs: Any,
) -> tuple[ClapAudioEmbedder, FakeModel, FakeProcessor]:
    """Fake model whose feature getters return ``BaseModelOutputWithPooling``.

    This mirrors transformers >= 4.40 / 5.x, where ``get_audio_features``
    returns the full output object instead of a bare tensor.
    """

    class ModelOutputFakeModel(FakeModel):
        def get_audio_features(self, **inputs: Any) -> Any:
            return FakePoolerOutput(pooler_output=super().get_audio_features(**inputs))

        def get_text_features(self, **inputs: Any) -> Any:
            return FakePoolerOutput(pooler_output=super().get_text_features(**inputs))

    model = ModelOutputFakeModel()
    processor = FakeProcessor()
    embedder = ClapAudioEmbedder(
        model_factory=lambda: FakeBundle(model=model, processor=processor),
        **kwargs,
    )
    return embedder, model, processor


def test_lazy_loading_defers_all_model_work() -> None:
    embedder, model, _ = make_embedder()

    assert embedder.resolved_device is None
    assert model.batch_sizes == []
    assert embedder.model_id == "laion/clap-htsat-unfused"
    assert embedder.embedding_dimension == DIMENSION


def test_embed_batch_normalizes_and_returns_domain_vectors() -> None:
    embedder, model, _ = make_embedder(batch_size=4)

    vectors = embedder.embed_batch([make_buffer(0), make_buffer(1), make_buffer(2)])

    assert len(vectors) == 3
    assert model.eval_called
    for vector in vectors:
        assert isinstance(vector, EmbeddingVector)
        assert vector.dimension == DIMENSION
        norm = math.sqrt(sum(value * value for value in vector.values))
        assert norm == pytest.approx(1.0, abs=1e-2)  # fp16 rounding tolerance


def test_long_audio_is_split_into_exact_10s_windows() -> None:
    """A 30 s preview must become exactly 3 deterministic 10 s windows."""
    embedder, model, processor = make_embedder()

    embedder.embed(make_long_buffer(30.0))

    audio_calls = [
        call for call in processor.calls if call.get("waveforms") is not None
    ]
    assert len(audio_calls) == 1
    waveforms = audio_calls[0]["waveforms"]
    assert len(waveforms) == 3
    assert all(len(w) == 480_000 for w in waveforms)
    # The three windows are the three disjoint slices in order.
    assert model.batch_sizes == [3]


def test_partial_trailing_window_is_kept() -> None:
    """25 s of audio → two full windows plus one 5 s window."""
    embedder, _, processor = make_embedder()

    embedder.embed(make_long_buffer(25.0))

    waveforms = processor.calls[0]["waveforms"]
    assert [len(w) for w in waveforms] == [480_000, 480_000, 240_000]


def test_audio_shorter_than_10s_is_a_single_window() -> None:
    embedder, model, processor = make_embedder()

    embedder.embed(make_long_buffer(5.0))

    waveforms = processor.calls[0]["waveforms"]
    assert len(waveforms) == 1
    assert len(waveforms[0]) == 240_000
    assert model.batch_sizes == [1]


def test_embed_is_deterministic_for_long_audio() -> None:
    """Same 30 s waveform in, identical vector out — twice (regression)."""
    embedder, _, _ = make_embedder()
    buffer = make_long_buffer(30.0)

    first = embedder.embed(buffer)
    second = embedder.embed(buffer)

    assert first.values == second.values
    assert first.dimension == second.dimension


def test_window_embeddings_are_averaged_and_renormalized() -> None:
    """The final vector is the L2-normalized mean of the window vectors."""
    embedder, _, _ = make_embedder()

    vector = embedder.embed(make_long_buffer(30.0))

    # FakeModel rows rotate by 7 degrees per batch position, then each row is
    # L2-normalized by _embed_chunk. Expected: normalize(mean of those three).
    rows = []
    for i in range(3):
        angle = math.radians(7.0 * i)
        raw = [math.cos(angle), math.sin(angle)] + [0.1] * (DIMENSION - 2)
        norm = math.sqrt(sum(x * x for x in raw))
        rows.append([x / norm for x in raw])
    mean = [sum(column) / 3 for column in zip(*rows)]
    mean_norm = math.sqrt(sum(x * x for x in mean))
    expected = [x / mean_norm for x in mean]

    assert vector.dimension == DIMENSION
    assert vector.values == pytest.approx(tuple(expected), abs=1e-3)
    norm = math.sqrt(sum(x * x for x in vector.values))
    assert norm == pytest.approx(1.0, abs=1e-2)


def test_embed_batch_accepts_modeloutput_with_pooler_output() -> None:
    """transformers 5.x returns BaseModelOutputWithPooling, not a bare tensor."""
    embedder, model, _ = make_modeloutput_embedder(batch_size=4)

    vectors = embedder.embed_batch([make_buffer(0), make_buffer(1)])

    assert len(vectors) == 2
    assert all(isinstance(v, EmbeddingVector) for v in vectors)
    assert model.batch_sizes == [2]


def test_embed_text_accepts_modeloutput_with_pooler_output() -> None:
    embedder, _, processor = make_modeloutput_embedder()
    embedder.embed(make_buffer())  # force load

    vector = embedder.embed_text("deep melodic techno")

    assert vector.dimension == DIMENSION
    norm = math.sqrt(sum(value * value for value in vector.values))
    assert norm == pytest.approx(1.0, abs=1e-2)
    assert processor.calls[-1]["text"] == "deep melodic techno"


def test_unsupported_model_output_type_is_rejected() -> None:
    class GarbageFakeModel(FakeModel):
        def get_audio_features(self, **inputs: Any) -> Any:
            return "not a tensor"

    embedder = ClapAudioEmbedder(
        model_factory=lambda: FakeBundle(
            model=GarbageFakeModel(), processor=FakeProcessor()
        )
    )

    with pytest.raises(EmbeddingError, match="str"):
        embedder.embed(make_buffer())


def test_wrong_projection_shape_is_rejected() -> None:
    """A misconfigured embedding_dimension must fail loudly, not corrupt rows."""
    embedder, _, _ = make_embedder(embedding_dimension=8)

    with pytest.raises(EmbeddingError, match="shape"):
        embedder.embed(make_buffer())


def test_single_vector_output_is_reshaped() -> None:
    """A 1-D projection (one row, no batch dim) is accepted as batch size 1."""

    class FlatFakeModel(FakeModel):
        def get_audio_features(self, **inputs: Any) -> Any:
            return super().get_audio_features(**inputs)[0]

    embedder = ClapAudioEmbedder(
        model_factory=lambda: FakeBundle(
            model=FlatFakeModel(), processor=FakeProcessor()
        )
    )

    vector = embedder.embed(make_buffer())

    assert vector.dimension == DIMENSION


def test_embed_single_matches_batch_of_one() -> None:
    embedder, _, _ = make_embedder()

    single = embedder.embed(make_buffer(5))

    assert single.dimension == DIMENSION


def test_embed_batch_splits_into_micro_batches() -> None:
    embedder, model, _ = make_embedder(batch_size=2)

    embedder.embed_batch([make_buffer(i) for i in range(5)])

    assert model.batch_sizes == [2, 2, 1]


def test_batch_size_is_clamped_to_hard_cap() -> None:
    embedder, _, _ = make_embedder(batch_size=128)

    assert embedder.batch_size == MAX_BATCH_SIZE


class OomAboveThresholdModel(FakeModel):
    """FakeModel that raises CUDA OOM for batches above a threshold."""

    def __init__(self, fail_above: int) -> None:
        super().__init__()
        self.fail_above = fail_above
        self.oom_count = 0

    def get_audio_features(self, **inputs: Any) -> torch.Tensor:
        count = inputs["input_features"].shape[0]
        if count > self.fail_above:
            self.oom_count += 1
            raise torch.cuda.OutOfMemoryError("simulated CUDA OOM")
        return super().get_audio_features(**inputs)


def _oom_embedder(model: OomAboveThresholdModel) -> ClapAudioEmbedder:
    return ClapAudioEmbedder(
        model_factory=lambda: FakeBundle(model=model, processor=FakeProcessor()),
        batch_size=16,
        device="cpu",
    )


def test_cuda_oom_halves_the_batch_and_recovers() -> None:
    """A batch-16 OOM is retried as 8 + 8 instead of failing the whole run."""
    model = OomAboveThresholdModel(fail_above=8)
    embedder = _oom_embedder(model)

    vectors = embedder.embed_batch([make_long_buffer(20.0) for _ in range(8)])

    assert len(vectors) == 8
    assert model.oom_count == 1
    assert model.batch_sizes == [8, 8]


def test_cuda_oom_at_the_floor_raises() -> None:
    """Chunks of 8 that still OOM propagate instead of halving forever."""
    model = OomAboveThresholdModel(fail_above=0)
    embedder = _oom_embedder(model)

    with pytest.raises(torch.cuda.OutOfMemoryError):
        embedder.embed_batch([make_long_buffer(20.0) for _ in range(8)])


def test_empty_batch_returns_empty_tuple() -> None:
    embedder, model, _ = make_embedder()

    assert embedder.embed_batch([]) == ()
    assert model.batch_sizes == []


def test_cuda_falls_back_to_cpu_when_unavailable() -> None:
    embedder, model, _ = make_embedder(device="cuda", cuda_available=False)
    embedder.embed(make_buffer())

    assert embedder.resolved_device is not None
    assert embedder.resolved_device.type == "cpu"
    assert model.moved_to == [embedder.resolved_device]


def test_cuda_is_selected_when_available() -> None:
    """The injected seam lets the CUDA branch be tested without a GPU."""
    import torch as _torch

    embedder, _, _ = make_embedder(device="auto", cuda_available=True)

    assert embedder._resolve_device(_torch).type == "cuda"


def test_explicit_cpu_device_is_honored() -> None:
    embedder, _, _ = make_embedder(device="cpu")
    embedder.embed(make_buffer())

    assert embedder.resolved_device is not None
    assert embedder.resolved_device.type == "cpu"


def test_auto_device_resolves_without_cuda() -> None:
    embedder, _, _ = make_embedder(device="auto", cuda_available=False)
    embedder.embed(make_buffer())

    assert embedder.resolved_device is not None
    assert embedder.resolved_device.type == "cpu"


def test_mixed_sample_rates_are_rejected() -> None:
    embedder, _, _ = make_embedder()
    buffers = [
        AudioBuffer(pcm_bytes=bytes(64), sample_rate=48_000),
        AudioBuffer(pcm_bytes=bytes(64), sample_rate=44_100),
    ]

    with pytest.raises(EmbeddingError, match="sample rates"):
        embedder.embed_batch(buffers)


def test_embed_text_produces_a_normalized_vector() -> None:
    embedder, _model, processor = make_embedder()
    embedder.embed(make_buffer())  # force load

    vector = embedder.embed_text("deep melodic techno")

    assert vector.dimension == DIMENSION
    norm = math.sqrt(sum(value * value for value in vector.values))
    assert norm == pytest.approx(1.0, abs=1e-2)
    assert processor.calls[-1]["text"] == "deep melodic techno"


def test_embed_text_rejects_empty_query() -> None:
    embedder, _, _ = make_embedder()

    with pytest.raises(ValueError):
        embedder.embed_text("   ")


def test_default_embedder_uses_configured_defaults() -> None:
    embedder = ClapAudioEmbedder()

    assert embedder.batch_size == 16
    assert embedder.model_id == "laion/clap-htsat-unfused"


def test_base_embedder_interface_refuses_text() -> None:
    from domain.interfaces.audio_engine import IAudioEmbedder

    class AudioOnly(IAudioEmbedder):
        @property
        def model_id(self) -> str:  # type: ignore[override]
            return "audio-only"

        @property
        def embedding_dimension(self) -> int:
            return 2

        def embed(self, audio: AudioBuffer) -> EmbeddingVector:
            return EmbeddingVector(values=(1.0, 0.0), dimension=2)

        def embed_batch(
            self, audios: Sequence[AudioBuffer]
        ) -> Sequence[EmbeddingVector]:
            return [self.embed(audio) for audio in audios]

    with pytest.raises(NotImplementedError):
        AudioOnly().embed_text("hello")


def test_batch_size_setter_clamps_and_validates() -> None:
    embedder = ClapAudioEmbedder()

    embedder.batch_size = 32
    assert embedder.batch_size == 32

    embedder.batch_size = 999
    assert embedder.batch_size == 48, "values above the hard cap are clamped"

    with pytest.raises(ValueError):
        embedder.batch_size = 0
    with pytest.raises(TypeError):
        embedder.batch_size = True  # type: ignore[assignment]
    with pytest.raises(TypeError):
        embedder.batch_size = "16"  # type: ignore[assignment]
