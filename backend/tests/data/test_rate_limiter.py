"""Tests for the async token bucket and retry helpers."""

from __future__ import annotations

import httpx
import pytest
from fakes import FakeClock

from data.datasources.remote.rate_limiter import (
    AsyncTokenBucket,
    exponential_backoff,
    retry_after_seconds,
)


async def test_itunes_bucket_serializes_requests_to_18_per_minute(
    fake_clock: FakeClock,
) -> None:
    bucket = AsyncTokenBucket(
        18 / 60.0,
        capacity=1.0,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )
    waits = [await bucket.acquire() for _ in range(3)]
    spacing = 60 / 18
    assert waits[0] == 0.0
    assert waits[1] == pytest.approx(spacing, rel=1e-6)
    assert waits[2] == pytest.approx(spacing, rel=1e-6)
    assert fake_clock.now == pytest.approx(2 * spacing, rel=1e-6)


async def test_deezer_bucket_allows_burst_of_eight_per_second(
    fake_clock: FakeClock,
) -> None:
    bucket = AsyncTokenBucket(
        8.0,
        capacity=8.0,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )
    waited = [await bucket.acquire() for _ in range(9)]
    assert waited[:8] == [0.0] * 8
    assert waited[8] == pytest.approx(1 / 8)


async def test_bucket_refills_over_time(fake_clock: FakeClock) -> None:
    bucket = AsyncTokenBucket(
        2.0,
        capacity=1.0,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )
    await bucket.acquire()
    await bucket.acquire()
    assert fake_clock.now == pytest.approx(0.5)
    # Nothing is consumed while the bucket sits idle.
    assert await bucket.acquire() == pytest.approx(0.5)


def test_bucket_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="rate_per_second"):
        AsyncTokenBucket(0)
    with pytest.raises(ValueError, match="capacity"):
        AsyncTokenBucket(1.0, capacity=0)


async def test_bucket_rejects_oversized_and_nonpositive_requests() -> None:
    bucket = AsyncTokenBucket(1.0, capacity=2.0)
    with pytest.raises(ValueError, match="capacity"):
        await bucket.acquire(3.0)
    with pytest.raises(ValueError, match="positive"):
        await bucket.acquire(0)


def test_retry_after_seconds_parses_numeric_and_falls_back() -> None:
    numeric = httpx.Response(
        429,
        headers={"Retry-After": "7"},
        request=httpx.Request("GET", "https://example.test"),
    )
    empty = httpx.Response(
        429,
        request=httpx.Request("GET", "https://example.test"),
    )
    garbage = httpx.Response(
        429,
        headers={"Retry-After": "not-a-number"},
        request=httpx.Request("GET", "https://example.test"),
    )
    assert retry_after_seconds(numeric, 1.0) == pytest.approx(7.0)
    assert retry_after_seconds(empty, 1.0) == 1.0
    assert retry_after_seconds(garbage, 1.0) == 1.0


def test_exponential_backoff_grows_and_is_capped() -> None:
    assert exponential_backoff(0) == 1.0
    assert exponential_backoff(1) == 2.0
    assert exponential_backoff(3) == 8.0
    assert exponential_backoff(20) == 60.0
    with pytest.raises(ValueError):
        exponential_backoff(-1)
