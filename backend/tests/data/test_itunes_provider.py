"""Tests for the iTunes catalog provider using mocked HTTP responses."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fakes import FakeClock, InMemorySeedRepository

from data.datasources.remote.itunes_provider import ITunesProvider
from data.datasources.remote.rate_limiter import AsyncTokenBucket
from data.errors import ProviderRateLimitError
from domain.entities.track import Track


def _track_item(
    track_id: int,
    *,
    title: str = "Song",
    artist: str = "Artist",
    duration_ms: int = 300_000,
    genre: str = "Techno",
    preview_url: str | None = "https://example.test/preview.m4a",
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "wrapperType": "track",
        "kind": "song",
        "trackId": track_id,
        "trackName": title,
        "artistName": artist,
        "collectionName": "Album",
        "primaryGenreName": genre,
        "trackTimeMillis": duration_ms,
        "previewUrl": preview_url,
        "artworkUrl100": "https://example.test/art.jpg",
        "trackViewUrl": "https://example.test/view",
        "releaseDate": "2024-01-01T00:00:00Z",
    }
    item.update(extra)
    return item


def _fast_limiter(fake_clock: FakeClock) -> AsyncTokenBucket:
    """A capacity-1 bucket fast enough that tests never really sleep."""
    return AsyncTokenBucket(
        1000.0,
        capacity=1.0,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )


def _make_provider(
    handler: httpx.MockTransport,
    *,
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository | None = None,
    rate_limiter: AsyncTokenBucket | None = None,
) -> ITunesProvider:
    client = httpx.AsyncClient(transport=handler, timeout=5.0)
    return ITunesProvider(
        http_client=client,
        seed_repository=seed_repository,
        rate_limiter=rate_limiter or _fast_limiter(fake_clock),
        clock=fake_clock,
        sleep=fake_clock.sleep,
        rate_limit_per_minute=18,
    )


def _ok_handler(
    results: list[dict[str, Any]],
    requests: list[httpx.Request],
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"resultCount": len(results), "results": results}
        )

    return httpx.MockTransport(handler)


async def test_search_filters_duration_preview_and_genre(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    requests: list[httpx.Request] = []
    results = [
        _track_item(1),
        _track_item(2, preview_url=None),
        _track_item(3, duration_ms=60_000),
        _track_item(4, duration_ms=1_000_000),
        _track_item(5, genre="Podcasts"),
        _track_item(6, title="Too Short", duration_ms=119_999),
        _track_item(7, title="Edge", duration_ms=120_000),
        _track_item(8, title="Edge Max", duration_ms=900_000),
        _track_item(9, title="Too Long", duration_ms=900_001),
        _track_item(10, kind="podcast"),
    ]
    provider = _make_provider(
        _ok_handler(results, requests),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
    )
    try:
        tracks = await provider.search_tracks("Artist", limit=25)
    finally:
        await provider.aclose()

    assert [track.external_id for track in tracks] == ["1", "7", "8"]
    assert all(track.preview_url for track in tracks)
    assert all(track.duration_seconds is not None for track in tracks)
    assert requests[0].url.params["limit"] == "200"
    assert requests[0].url.params["entity"] == "song"
    assert requests[0].url.params["attribute"] == "artistTerm"
    assert requests[0].url.params["term"] == "Artist"


async def test_search_dedups_by_track_id_and_normalized_key(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    results = [
        _track_item(1),
        _track_item(1),
        _track_item(2, title="SONG", artist="  artist  "),
        _track_item(3, title="Different"),
    ]
    provider = _make_provider(
        _ok_handler(results, []),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
    )
    try:
        tracks = await provider.search_tracks("Artist")
    finally:
        await provider.aclose()
    assert [track.external_id for track in tracks] == ["1", "3"]


async def test_search_snowballs_collaborators_into_pending_seeds(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    results = [
        _track_item(
            1,
            title="Together (Miss Monique Remix)",
            artist="Solomun & Tale Of Us",
        ),
        _track_item(2, title="Solo", artist="Solomun"),
        _track_item(3, title="Crossover", artist="Dua Lipa", genre="Pop"),
    ]
    provider = _make_provider(
        _ok_handler(results, []),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
    )
    try:
        await provider.search_tracks("Solomun")
    finally:
        await provider.aclose()

    discovered = {seed.name for seed in seed_repository.discovery_calls}
    assert "Miss Monique" in discovered
    assert "Tale Of Us" in discovered
    assert "Solomun" not in discovered
    assert all(seed.status == "pending" for seed in seed_repository.discovery_calls)
    assert all(
        seed.source == "itunes-snowball" for seed in seed_repository.discovery_calls
    )
    categories = {seed.name: seed.category for seed in seed_repository.discovery_calls}
    assert categories["Dua Lipa"] == "general"
    assert categories["Miss Monique"] == "electronic"


async def test_metadata_requests_are_serialized_to_18_per_minute(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    limiter = AsyncTokenBucket(
        18 / 60.0,
        capacity=1.0,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )
    provider = _make_provider(
        _ok_handler([_track_item(1)], []),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
        rate_limiter=limiter,
    )
    try:
        await provider.search_tracks("A")
        await provider.search_tracks("B")
    finally:
        await provider.aclose()
    assert fake_clock.sleeps == [pytest.approx(60 / 18, rel=1e-6)]


async def test_provider_backs_off_on_429_and_retries(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={})
        return httpx.Response(200, json={"resultCount": 1, "results": [_track_item(1)]})

    provider = _make_provider(
        httpx.MockTransport(handler),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
    )
    try:
        tracks = await provider.search_tracks("Artist")
    finally:
        await provider.aclose()
    assert len(requests) == 2
    assert fake_clock.sleeps == [2.0]
    assert tracks[0].external_id == "1"


async def test_provider_raises_after_repeated_rate_limits(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    provider = _make_provider(
        httpx.MockTransport(handler),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
    )
    try:
        with pytest.raises(ProviderRateLimitError):
            await provider.search_tracks("Artist")
    finally:
        await provider.aclose()


async def test_lookup_track_returns_filtered_track(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    requests: list[httpx.Request] = []
    provider = _make_provider(
        _ok_handler([_track_item(42)], requests),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
    )
    try:
        track = await provider.lookup_track("42")
        missing = await provider.lookup_track("999")
    finally:
        await provider.aclose()
    assert track is not None and track.external_id == "42"
    assert missing is None
    assert requests[0].url.path.endswith("/lookup")


async def test_fetch_preview_downloads_bytes(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={"resultCount": 1, "results": [_track_item(1)]},
            )
        if request.url.path.endswith("preview.m4a"):
            return httpx.Response(200, content=b"\x00\x01\x02")
        return httpx.Response(404)

    provider = _make_provider(
        httpx.MockTransport(handler),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
    )
    try:
        tracks = await provider.search_tracks("Artist")
        payload = await provider.fetch_preview(tracks[0])
        missing = await provider.fetch_preview(Track(id="x", title="t", artist="a"))
    finally:
        await provider.aclose()
    assert payload == b"\x00\x01\x02"
    assert missing is None


async def test_search_requires_non_empty_query(
    fake_clock: FakeClock,
    seed_repository: InMemorySeedRepository,
) -> None:
    provider = _make_provider(
        _ok_handler([], []),
        fake_clock=fake_clock,
        seed_repository=seed_repository,
    )
    try:
        with pytest.raises(ValueError, match="query"):
            await provider.search_tracks("   ")
    finally:
        await provider.aclose()
