"""Deezer Public API seed discovery and catalog streaming.

The crawler walks ``/artist/{id}/related`` breadth-first from a curated list of
central club artists, then adds general-genre artists from Deezer's public
charts. All requests share a token bucket capped at 8 requests/second.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

import httpx

from domain.entities.track import SeedArtist, Track
from domain.interfaces.catalog import ISeedCrawler, ISeedDiscovery
from domain.use_cases.build_seed_list import CrawlProgress

from ...errors import ProviderError, ProviderRateLimitError
from .rate_limiter import (
    AsyncTokenBucket,
    Clock,
    Sleep,
    exponential_backoff,
    retry_after_seconds,
)

LOGGER = logging.getLogger(__name__)

DEEZER_BASE_URL = "https://api.deezer.com"

CORE_ELECTRONIC_ARTISTS: tuple[str, ...] = (
    "Ahmet Kilic",
    "Miss Monique",
    "Solomun",
    "Tale Of Us",
    "Charlotte de Witte",
    "Black Coffee",
    "Keinemusik",
    "Boris Brejcha",
    "Amelie Lens",
    "Stephan Bodzin",
    "Argy",
    "Anyma",
    "Rüfüs Du Sol",
    "Ben Böhmer",
    "Adam Beyer",
    "Nina Kraviz",
    "Peggy Gou",
    "Dixon",
    "Âme",
    "Carl Cox",
    "Richie Hawtin",
    "Marco Carola",
    "Loco Dice",
    "Jamie Jones",
    "Michael Bibi",
    "Chris Stussy",
    "Dennis Cruz",
    "Enrico Sangiuliano",
    "Reinier Zonneveld",
    "I Hate Models",
    "Sara Landry",
    "Indira Paganotto",
    "Space 92",
    "Lilly Palmer",
    "Nico Moreno",
    "Trym",
    "KAS:ST",
    "Mathame",
    "Fideles",
    "Adriatique",
    "Colyn",
    "Innellea",
    "Massano",
    "Artbat",
    "Vintage Culture",
    "Meduza",
    "Gorgon City",
    "CamelPhat",
    "Fisher",
    "Chris Lake",
    "John Summit",
    "Dom Dolla",
    "Mau P",
    "Claptone",
    "Purple Disco Machine",
    "Disclosure",
    "Jamie xx",
    "Four Tet",
    "Floating Points",
    "Bonobo",
    "Bicep",
    "Overmono",
    "Fred again..",
    "TSHA",
    "Barry Can't Swim",
    "Salute",
    "Mall Grab",
    "DJ Seinfeld",
    "Ross from Friends",
)

# Deezer public genre ids verified from https://api.deezer.com/genre.
GENERAL_GENRE_CHARTS: tuple[tuple[int, str], ...] = (
    (132, "Pop"),
    (116, "Hip-Hop"),
    (152, "Rock"),
    (197, "Latin"),
    (12, "Arabic"),
)


class DeezerSeedCrawler(ISeedDiscovery, ISeedCrawler):
    """Discover seed artists and stream their top tracks from Deezer."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = DEEZER_BASE_URL,
        rate_limit_per_second: float = 8.0,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        rate_limiter: AsyncTokenBucket | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        core_artists: Sequence[str] = CORE_ELECTRONIC_ARTISTS,
        general_genres: Sequence[tuple[int, str]] = GENERAL_GENRE_CHARTS,
    ) -> None:
        if rate_limit_per_second <= 0:
            raise ValueError("rate_limit_per_second must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self._client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": "DigDeeperLocal/0.1 (local seed crawler)"},
        )
        self._owns_client = http_client is None
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._sleep = sleep
        self._core_artists = tuple(core_artists)
        self._general_genres = tuple(general_genres)
        self._rate_limiter = rate_limiter or AsyncTokenBucket(
            rate_limit_per_second,
            capacity=rate_limit_per_second,
            clock=clock,
            sleep=sleep,
        )

    async def aclose(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()

    async def discover(
        self,
        *,
        electronic_limit: int = 1000,
        general_limit: int = 300,
        max_depth: int = 2,
        progress: Callable[[CrawlProgress], None] | None = None,
    ) -> Sequence[SeedArtist]:
        if electronic_limit < 0:
            raise ValueError("electronic_limit must not be negative")
        if general_limit < 0:
            raise ValueError("general_limit must not be negative")
        if max_depth < 0:
            raise ValueError("max_depth must not be negative")

        seeds: dict[str, SeedArtist] = {}
        discovery_counts: dict[str, int] = {}

        if electronic_limit > 0:
            await self._discover_electronic(
                seeds,
                discovery_counts,
                electronic_limit=electronic_limit,
                max_depth=max_depth,
                progress=progress,
            )
        if general_limit > 0:
            await self._discover_general(
                seeds,
                discovery_counts,
                general_limit=general_limit,
                progress=progress,
            )

        ordered = sorted(
            seeds.values(),
            key=lambda seed: (-seed.priority_score, seed.name.casefold()),
        )
        return tuple(ordered)

    async def _discover_electronic(
        self,
        seeds: dict[str, SeedArtist],
        discovery_counts: dict[str, int],
        *,
        electronic_limit: int,
        max_depth: int,
        progress: Callable[[CrawlProgress], None] | None = None,
    ) -> None:
        queue: deque[tuple[str, int, str | None]] = deque(
            (name, 0, None) for name in self._core_artists
        )
        if progress is not None and self._core_artists:
            progress(
                CrawlProgress(
                    stage="electronic",
                    name=self._core_artists[0],
                    depth=0,
                    found=len(seeds),
                )
            )
        visited: set[str] = set()

        while queue and len(seeds) < electronic_limit:
            name, depth, artist_id = queue.popleft()
            key = name.casefold().strip()
            if not key or key in visited:
                continue
            visited.add(key)

            if artist_id is None:
                resolved = await self._resolve_artist_id(name)
                if resolved is not None:
                    artist_id = resolved
            base_priority = max(0.35, 0.95 - 0.15 * depth)
            self._add_seed(
                seeds,
                discovery_counts,
                name=name,
                priority=base_priority,
                category="electronic",
                external_id=artist_id,
                source="deezer-graph",
            )
            if progress is not None:
                progress(
                    CrawlProgress(
                        stage="electronic",
                        name=name,
                        depth=depth,
                        found=len(seeds),
                    )
                )
            if len(seeds) >= electronic_limit or depth >= max_depth:
                continue
            if artist_id is None:
                continue

            related = await self._get_related_artists(artist_id)
            for related_name, related_id in related:
                related_key = related_name.casefold().strip()
                if not related_key or related_key in visited:
                    continue
                queue.append((related_name, depth + 1, related_id))

    async def _discover_general(
        self,
        seeds: dict[str, SeedArtist],
        discovery_counts: dict[str, int],
        *,
        general_limit: int,
        progress: Callable[[CrawlProgress], None] | None = None,
    ) -> None:
        general_count = 0
        for genre_id, genre_name in self._general_genres:
            if general_count >= general_limit:
                break
            artists = await self._get_chart_artists(genre_id)
            for index, (name, artist_id) in enumerate(artists):
                if general_count >= general_limit:
                    break
                key = name.casefold().strip()
                if not key:
                    continue
                existing = seeds.get(key)
                if existing is not None and existing.category == "electronic":
                    continue
                priority = max(0.2, 0.6 - 0.005 * index)
                self._add_seed(
                    seeds,
                    discovery_counts,
                    name=name,
                    priority=priority,
                    category="general",
                    external_id=artist_id,
                    source=f"deezer-chart:{genre_name}",
                )
                general_count += 1
            if progress is not None:
                progress(
                    CrawlProgress(
                        stage="general",
                        name=genre_name,
                        depth=None,
                        found=len(seeds),
                    )
                )

    @staticmethod
    def _add_seed(
        seeds: dict[str, SeedArtist],
        discovery_counts: dict[str, int],
        *,
        name: str,
        priority: float,
        category: str,
        external_id: str | None,
        source: str,
    ) -> None:
        key = name.casefold().strip()
        if not key:
            return
        count = discovery_counts.get(key, 0) + 1
        discovery_counts[key] = count
        existing = seeds.get(key)
        if existing is not None:
            bumped = min(1.0, max(existing.priority_score, priority) + 0.05)
            seeds[key] = replace(
                existing,
                priority_score=bumped,
                external_id=existing.external_id or external_id,
                category=(
                    "electronic"
                    if existing.category == "electronic" or category == "electronic"
                    else "general"
                ),
            )
            return
        seeds[key] = SeedArtist(
            name=name,
            priority_score=priority,
            category=category,  # type: ignore[arg-type]
            status="pending",
            source=source,
            external_id=external_id,
        )

    async def _resolve_artist_id(self, name: str) -> str | None:
        payload = await self._get_json(
            "/search/artist",
            {"q": name, "limit": 1},
        )
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            return None
        first = data[0]
        if not isinstance(first, Mapping):
            return None
        artist_id = first.get("id")
        return str(artist_id) if artist_id is not None else None

    async def _get_related_artists(
        self,
        artist_id: str,
    ) -> Sequence[tuple[str, str]]:
        payload = await self._get_json(
            f"/artist/{artist_id}/related",
            {"limit": 100},
        )
        return _artist_pairs(payload)

    async def _get_chart_artists(self, genre_id: int) -> Sequence[tuple[str, str]]:
        payload = await self._get_json(
            f"/chart/{genre_id}/artists",
            {"limit": 100},
        )
        return _artist_pairs(payload)

    async def crawl(
        self,
        seeds: Sequence[SeedArtist],
        *,
        tracks_per_artist: int = 50,
    ) -> AsyncIterator[Track]:
        if tracks_per_artist <= 0:
            raise ValueError("tracks_per_artist must be positive")
        seen: set[str] = set()
        for seed in seeds:
            artist_id = seed.external_id
            if artist_id is None:
                artist_id = await self._resolve_artist_id(seed.name)
            if artist_id is None:
                continue
            payload = await self._get_json(
                f"/artist/{artist_id}/top",
                {"limit": min(100, tracks_per_artist)},
            )
            data = payload.get("data")
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, Mapping):
                    continue
                track = _parse_deezer_track(item)
                if track is None or track.external_id is None:
                    continue
                if track.external_id in seen:
                    continue
                seen.add(track.external_id)
                yield track

    async def _get_json(
        self,
        path: str,
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        url = f"{self._base_url}{path}"
        last_status: int | None = None
        for attempt in range(self._max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                response = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(f"Deezer request failed: {url}") from exc
                await self._sleep(exponential_backoff(attempt))
                continue

            last_status = response.status_code
            if response.status_code in (403, 429) or 500 <= response.status_code < 600:
                if attempt >= self._max_retries:
                    if response.status_code in (403, 429):
                        raise ProviderRateLimitError(
                            "Deezer rate limited the request after retries"
                        )
                    raise ProviderError(
                        f"Deezer returned HTTP {response.status_code} after retries"
                    )
                await self._sleep(
                    retry_after_seconds(response, exponential_backoff(attempt))
                )
                continue

            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise ProviderError(f"Deezer request failed: {url}") from exc
            if not isinstance(payload, Mapping):
                raise ProviderError("Deezer returned an unexpected JSON shape")

            error = payload.get("error")
            if isinstance(error, Mapping):
                code = error.get("code")
                if code == 4 and attempt < self._max_retries:
                    await self._sleep(exponential_backoff(attempt))
                    continue
                raise ProviderRateLimitError(
                    f"Deezer API error {code}: {error.get('message')}"
                )
            return payload

        raise ProviderError(
            f"Deezer request failed after retries (last status {last_status})"
        )


def _artist_pairs(payload: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    data = payload.get("data")
    if not isinstance(data, list):
        return ()
    pairs: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        artist_id = item.get("id")
        if isinstance(name, str) and name.strip() and artist_id is not None:
            pairs.append((name.strip(), str(artist_id)))
    return tuple(pairs)


def _parse_deezer_track(item: Mapping[str, Any]) -> Track | None:
    track_id = item.get("id")
    title = item.get("title")
    artist = item.get("artist")
    if track_id is None or not isinstance(title, str) or not title.strip():
        return None
    artist_name = artist.get("name") if isinstance(artist, Mapping) else None
    if not isinstance(artist_name, str) or not artist_name.strip():
        return None
    duration = item.get("duration")
    preview = item.get("preview")
    album = item.get("album")
    album_title = album.get("title") if isinstance(album, Mapping) else None
    cover = album.get("cover_medium") if isinstance(album, Mapping) else None
    try:
        return Track(
            id=f"deezer:{track_id}",
            title=title,
            artist=artist_name,
            duration_seconds=float(duration)
            if isinstance(duration, (int, float))
            else None,
            preview_url=preview if isinstance(preview, str) and preview else None,
            artwork_url=cover if isinstance(cover, str) else None,
            album=album_title if isinstance(album_title, str) else None,
            source="deezer",
            external_id=str(track_id),
        )
    except (TypeError, ValueError):
        return None
