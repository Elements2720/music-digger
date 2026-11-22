from __future__ import annotations

import dataclasses

import pytest

from domain.value_objects.audio_features import BPM, AudioFeatures, CamelotKey


def test_audio_features_allows_partial_detection() -> None:
    features = AudioFeatures()
    assert features.bpm is None
    assert features.key is None


def test_audio_features_accepts_value_objects() -> None:
    features = AudioFeatures(bpm=BPM(128.0), key=CamelotKey("8A"))
    assert features.bpm == BPM(128.0)
    assert features.key == CamelotKey("8A")


def test_audio_features_normalizes_raw_values() -> None:
    features = AudioFeatures(bpm=128, key="8a")  # type: ignore[arg-type]
    assert features.bpm == BPM(128.0)
    assert features.key == CamelotKey("8A")


@pytest.mark.parametrize("bpm", ["128", True])
def test_audio_features_rejects_invalid_raw_bpm(bpm: object) -> None:
    with pytest.raises(TypeError):
        AudioFeatures(bpm=bpm)  # type: ignore[arg-type]


@pytest.mark.parametrize("key", [8, True])
def test_audio_features_rejects_invalid_raw_key(key: object) -> None:
    with pytest.raises(TypeError):
        AudioFeatures(key=key)  # type: ignore[arg-type]


def test_audio_features_is_immutable() -> None:
    features = AudioFeatures()
    with pytest.raises(dataclasses.FrozenInstanceError):
        features.bpm = BPM(128.0)  # type: ignore[misc]
