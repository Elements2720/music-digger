"""Async token-bucket rate limiting shared by remote providers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class AsyncTokenBucket:
    """A concurrency-safe token bucket.

    ``capacity`` controls burst size. iTunes uses ``capacity=1`` so metadata
    requests are serialized, while Deezer can use a small burst up to 8 req/s.
    """

    def __init__(
        self,
        rate_per_second: float,
        *,
        capacity: float = 1.0,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rate = rate_per_second
        self._capacity = capacity
        self._clock = clock
        self._sleep = sleep
        self._tokens = capacity
        self._last_refill = clock()
        self._lock = asyncio.Lock()

    @property
    def rate_per_second(self) -> float:
        """Refill rate."""
        return self._rate

    @property
    def capacity(self) -> float:
        """Maximum burst size."""
        return self._capacity

    async def acquire(self, tokens: float = 1.0) -> float:
        """Wait until ``tokens`` are available and return the waited seconds."""
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        if tokens > self._capacity:
            raise ValueError("tokens must not exceed the bucket capacity")

        async with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._last_refill)
            self._tokens = min(
                self._capacity,
                self._tokens + elapsed * self._rate,
            )
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            deficit = tokens - self._tokens
            wait_seconds = deficit / self._rate
            await self._sleep(wait_seconds)
            self._last_refill = self._clock()
            self._tokens = 0.0
            return wait_seconds


def retry_after_seconds(response: httpx.Response, default: float) -> float:
    """Read ``Retry-After`` as seconds, accepting both numeric and HTTP dates."""
    value = response.headers.get("Retry-After")
    if not value:
        return default
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return default
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def exponential_backoff(
    attempt: int,
    *,
    base_seconds: float = 1.0,
    factor: float = 2.0,
    max_seconds: float = 60.0,
) -> float:
    """Return a deterministic exponential delay for zero-based ``attempt``."""
    if attempt < 0:
        raise ValueError("attempt must not be negative")
    return min(max_seconds, base_seconds * (factor**attempt))
