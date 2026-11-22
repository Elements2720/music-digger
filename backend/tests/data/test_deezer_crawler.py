"""Tests for Deezer seed discovery and crawling with mocked HTTP."""

from __future__ import annotations

import httpx
import pytest
from fakes import FakeClock

from data.datasources.remote.deezer_seed_crawler import DeezerSeedCrawler
from domain.entities.track import SeedArtist
from domain.use_cases.build_seed_list import CrawlProgress


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/search/artist":
        return httpx.Response(
            200,
            json={"data": [{"id": "1", "name": "Seed DJ"}]},
        )
    if path == "/artist/1/related":
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "2", "name": "Related A"},
                    {"id": "3", "name": "Related B"},
                ]
            },
        )
    if path == "/chart/999/artists":
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "10", "name": "Chart Pop"},
                    {"id": "11", "name": "Chart Rock"},
                ]
            },
        )
    if path == "/artist/1/top":
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 900,
                        "title": "Track A",
                        "duration": 300,
                        "preview": "https://example.test/a.mp3",
                        "artist": {"name": "Seed DJ"},
                        "album": {
                            "title": "Album A",
                            "cover_medium": "https://x/a.jpg",
                        },
                    },
                    {
                        "id": 900,
                        "title": "Track A",
                        "duration": 300,
                        "preview": "https://example.test/a.mp3",
                        "artist": {"name": "Seed DJ"},
                        "album": {"title": "Album A"},
                    },
                    {
                        "id": 901,
                        "title": "Track B",
                        "duration": 200,
                        "preview": "https://example.test/b.mp3",
                        "artist": {"name": "Seed DJ"},
                        "album": {"title": "Album A"},
                    },
                ]
            },
        )
    return httpx.Response(404, json={"error": "not found"})


def _make_crawler(
    fake_clock: FakeClock,
    *,
    core_artists: tuple[str, ...] = ("Seed DJ",),
) -> DeezerSeedCrawler:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler), timeout=5.0)
    return DeezerSeedCrawler(
        http_client=client,
        core_artists=core_artists,
        general_genres=((999, "Pop"),),
        rate_limiter=None,
        rate_limit_per_second=8.0,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )


async def test_discover_walks_related_artists_and_charts(
    fake_clock: FakeClock,
) -> None:
    crawler = _make_crawler(fake_clock)
    try:
        seeds = await crawler.discover(
            electronic_limit=10,
            general_limit=2,
            max_depth=1,
        )
    finally:
        await crawler.aclose()

    by_name = {seed.name: seed for seed in seeds}
    assert set(by_name) == {
        "Seed DJ",
        "Related A",
        "Related B",
        "Chart Pop",
        "Chart Rock",
    }
    assert by_name["Seed DJ"].category == "electronic"
    assert by_name["Seed DJ"].external_id == "1"
    assert by_name["Related A"].category == "electronic"
    assert by_name["Related A"].external_id == "2"
    assert by_name["Chart Pop"].category == "general"
    # Seeds are ordered by descending priority.
    priorities = [seed.priority_score for seed in seeds]
    assert priorities == sorted(priorities, reverse=True)
    assert by_name["Seed DJ"].priority_score == pytest.approx(0.95)
    assert by_name["Related A"].priority_score == pytest.approx(0.8)


async def test_discover_respects_max_depth(fake_clock: FakeClock) -> None:
    crawler = _make_crawler(fake_clock)
    try:
        seeds = await crawler.discover(
            electronic_limit=10,
            general_limit=0,
            max_depth=0,
        )
    finally:
        await crawler.aclose()
    assert [seed.name for seed in seeds] == ["Seed DJ"]


async def test_discover_respects_limits(fake_clock: FakeClock) -> None:
    crawler = _make_crawler(fake_clock)
    try:
        seeds = await crawler.discover(
            electronic_limit=2,
            general_limit=1,
            max_depth=2,
        )
    finally:
        await crawler.aclose()
    electronic = [seed for seed in seeds if seed.category == "electronic"]
    general = [seed for seed in seeds if seed.category == "general"]
    assert len(electronic) == 2
    assert len(general) == 1


async def test_discover_stays_within_eight_requests_per_second(
    fake_clock: FakeClock,
) -> None:
    crawler = _make_crawler(fake_clock)
    try:
        await crawler.discover(
            electronic_limit=10,
            general_limit=2,
            max_depth=1,
        )
    finally:
        await crawler.aclose()
    # 1 search + 1 related + 1 chart = 3 requests, comfortably inside the burst.
    assert fake_clock.sleeps == []


async def test_crawl_streams_deduplicated_tracks(fake_clock: FakeClock) -> None:
    crawler = _make_crawler(fake_clock)
    try:
        seeds = [
            SeedArtist(
                "Seed DJ",
                0.9,
                "electronic",
                external_id="1",
                source="deezer-graph",
            )
        ]
        tracks = [track async for track in crawler.crawl(seeds, tracks_per_artist=10)]
    finally:
        await crawler.aclose()

    assert [track.external_id for track in tracks] == ["900", "901"]
    assert all(track.source == "deezer" for track in tracks)
    assert tracks[0].preview_url == "https://example.test/a.mp3"
    assert tracks[0].duration_seconds == 300.0


async def test_crawl_rejects_nonpositive_tracks_per_artist(
    fake_clock: FakeClock,
) -> None:
    crawler = _make_crawler(fake_clock)
    try:
        with pytest.raises(ValueError, match="tracks_per_artist"):
            async for _ in crawler.crawl([], tracks_per_artist=0):
                pass
    finally:
        await crawler.aclose()


async def test_discover_rejects_negative_limits(fake_clock: FakeClock) -> None:
    crawler = _make_crawler(fake_clock)
    try:
        with pytest.raises(ValueError, match="electronic_limit"):
            await crawler.discover(electronic_limit=-1)
    finally:
        await crawler.aclose()


async def test_discover_emits_progress_events(fake_clock: FakeClock) -> None:
    crawler = _make_crawler(fake_clock)
    events: list[CrawlProgress] = []
    try:
        await crawler.discover(
            electronic_limit=10,
            general_limit=2,
            max_depth=1,
            progress=events.append,
        )
    finally:
        await crawler.aclose()

    assert len(events) >= 3
    assert events[0].stage == "electronic"
    assert events[0].name == "Seed DJ"
    assert events[0].depth == 0
    electronic_events = [e for e in events if e.stage == "electronic"]
    assert any(e.name == "Related A" for e in electronic_events)
    assert any(e.name == "Related B" for e in electronic_events)
    general_events = [e for e in events if e.stage == "general"]
    assert len(general_events) == 1
    assert general_events[0].name == "Pop"
    founds = [e.found for e in events]
    assert founds == sorted(founds)

