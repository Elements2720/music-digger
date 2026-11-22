from __future__ import annotations

import dataclasses
import math

import pytest

from domain.value_objects.audio_features import TimeRange


def test_time_range_accepts_valid_bounds() -> None:
    time_range = TimeRange(0.0, 30.0)
    assert time_range.start_seconds == 0.0
    assert time_range.end_seconds == 30.0
    assert time_range.duration_seconds == 30.0


def test_time_range_normalizes_integers_to_floats() -> None:
    time_range = TimeRange(10, 40)
    assert isinstance(time_range.start_seconds, float)
    assert isinstance(time_range.end_seconds, float)
    assert time_range.duration_seconds == 30.0


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (-0.01, 10.0),
        (10.0, 10.0),
        (10.0, 9.99),
        (math.nan, 10.0),
        (0.0, math.nan),
        (math.inf, math.inf),
    ],
)
def test_time_range_rejects_invalid_bounds(start: float, end: float) -> None:
    with pytest.raises(ValueError):
        TimeRange(start, end)


@pytest.mark.parametrize(
    ("start", "end"), [("0", 10.0), (0.0, "10"), (None, 10.0), (True, 10.0)]
)
def test_time_range_rejects_non_numeric_bounds(start: object, end: object) -> None:
    with pytest.raises(TypeError):
        TimeRange(start, end)  # type: ignore[arg-type]


def test_time_range_is_immutable() -> None:
    time_range = TimeRange(0.0, 30.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        time_range.start_seconds = 1.0  # type: ignore[misc]


def test_time_range_contains_is_half_open() -> None:
    time_range = TimeRange(10.0, 20.0)
    assert time_range.contains(10.0)
    assert time_range.contains(19.999)
    assert not time_range.contains(20.0)
    assert not time_range.contains(9.999)


@pytest.mark.parametrize("point", [math.nan, math.inf, "15"])
def test_time_range_contains_rejects_invalid_points(point: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        TimeRange(10.0, 20.0).contains(point)  # type: ignore[arg-type]


def test_time_range_overlaps() -> None:
    base = TimeRange(10.0, 20.0)
    assert base.overlaps(TimeRange(15.0, 25.0))
    assert base.overlaps(TimeRange(5.0, 15.0))
    assert base.overlaps(TimeRange(12.0, 18.0))
    assert base.overlaps(TimeRange(0.0, 100.0))
    assert not base.overlaps(TimeRange(20.0, 30.0))
    assert not base.overlaps(TimeRange(0.0, 10.0))
    assert not base.overlaps(TimeRange(30.0, 40.0))


def test_time_range_overlaps_rejects_non_range() -> None:
    with pytest.raises(TypeError, match="other must be a TimeRange"):
        TimeRange(0.0, 10.0).overlaps((0.0, 10.0))  # type: ignore[arg-type]


def test_time_range_ordering() -> None:
    ranges = [TimeRange(30.0, 40.0), TimeRange(0.0, 10.0), TimeRange(10.0, 20.0)]
    assert sorted(ranges) == [
        TimeRange(0.0, 10.0),
        TimeRange(10.0, 20.0),
        TimeRange(30.0, 40.0),
    ]


def test_time_range_string_representation() -> None:
    assert str(TimeRange(0.0, 30.5)) == "[0s, 30.5s)"
