from __future__ import annotations

import dataclasses
import math

import pytest

from domain.value_objects.audio_features import BPM, BPM_MAX, BPM_MIN


@pytest.mark.parametrize("value", [BPM_MIN, 60.0, 128.0, 174.0, BPM_MAX])
def test_bpm_accepts_valid_values(value: float) -> None:
    bpm = BPM(value)
    assert bpm.value == pytest.approx(value)
    assert isinstance(bpm.value, float)


def test_bpm_normalizes_integers_to_float() -> None:
    bpm = BPM(128)
    assert bpm.value == 128.0
    assert bpm.bpm == 128.0
    assert isinstance(bpm.value, float)


@pytest.mark.parametrize("value", [BPM_MIN - 0.01, 0.0, -128.0, BPM_MAX + 0.01, 1000.0])
def test_bpm_rejects_out_of_range_values(value: float) -> None:
    with pytest.raises(ValueError, match="BPM must be between"):
        BPM(value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_bpm_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        BPM(value)


@pytest.mark.parametrize("value", ["128", None, True, False, [128.0]])
def test_bpm_rejects_non_numeric_values(value: object) -> None:
    with pytest.raises(TypeError):
        BPM(value)  # type: ignore[arg-type]


def test_bpm_is_immutable() -> None:
    bpm = BPM(128.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        bpm.value = 130.0  # type: ignore[misc]


def test_bpm_ordering_and_equality() -> None:
    assert BPM(120.0) == BPM(120.0)
    assert BPM(120.0) != BPM(128.0)
    assert BPM(120.0) < BPM(128.0)
    assert sorted([BPM(174.0), BPM(90.0), BPM(128.0)]) == [
        BPM(90.0),
        BPM(128.0),
        BPM(174.0),
    ]


def test_bpm_is_close_to_uses_inclusive_tolerance() -> None:
    assert BPM(128.0).is_close_to(BPM(129.0), tolerance=1.0)
    assert BPM(128.0).is_close_to(BPM(127.0), tolerance=1.0)
    assert not BPM(128.0).is_close_to(BPM(129.01), tolerance=1.0)
    assert BPM(128.0).is_close_to(BPM(128.0))


def test_bpm_is_close_to_rejects_bad_arguments() -> None:
    with pytest.raises(TypeError, match="other must be a BPM"):
        BPM(128.0).is_close_to(128.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="negative"):
        BPM(128.0).is_close_to(BPM(128.0), tolerance=-1.0)
    with pytest.raises(TypeError):
        BPM(128.0).is_close_to(BPM(128.0), tolerance="1")  # type: ignore[arg-type]


def test_bpm_string_representation() -> None:
    assert str(BPM(128.0)) == "128 BPM"
    assert str(BPM(128.5)) == "128.5 BPM"
