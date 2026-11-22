"""iTunes Search API catalog provider.

Hard constraints enforced here:

* at most 18 metadata requests per minute, serialized through a token bucket;
* one search request per artist with ``limit=200`` and ``attribute=artistTerm``;
* strict preview/duration/genre filters before anything is persisted;
* deduplication by iTunes id and normalized ``artist + title``;
* collaborator/remixer snowballing into ``seed_artists``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from domain.entities.track import SeedArtist, Track
from domain.interfaces.catalog import ICatalogProvider
from domain.interfaces.repositories import ISeedRepository

from ...errors import ProviderError, ProviderRateLimitError
from ...normalization import normalize_artist_title
from .artist_parser import parse_collaborators
from .rate_limiter import (
    AsyncTokenBucket,
    Clock,
    Sleep,
    exponential_backoff,
    retry_after_seconds,
)

LOGGER = logging.getLogger(__name__)

ITUNES_BASE_URL = "https://itunes.apple.com"
ITUNES_SEARCH_LIMIT = 200
MIN_DURATION_SECONDS = 120.0
MAX_DURATION_SECONDS = 900.0

NON_MUSIC_GENRES = frozenset(
    {
        "podcasts",
        "podcast",
        "spoken word",
        "comedy",
        "audiobooks",
        "audiobook",
        "children's music",
        "childrens music",
        "kids",
    }
)

ELECTRONIC_GENRE_HINTS = frozenset(
    {
        "afro house",
        "bass",
        "dance",
        "deep house",
        "disco",
        "drum & bass",
        "drum and bass",
        "dubstep",
        "electro",
        "electronic",
        "hardstyle",
        "house",
        "indie dance",
        "melodic techno",
        "minimal",
        "nu disco",
        "progressive house",
        "psytrance",
        "tech house",
        "techno",
        "trance",
    }
)

_YEAR_PATTERN = re.compile(r"^(?P<year>\d{4})")


class ITunesProvider(ICatalogProvider):
    """Catalog provider backed by the public iTunes Search API."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        seed_repository: ISeedRepository | None = None,
        country: str = "US",
        rate_limit_per_minute: int = 18,
        timeout_seconds: float = 30.0,
        max_retries: int = 4,
        base_url: str = ITUNES_BASE_URL,
        rate_limiter: AsyncTokenBucket | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        cache_ttl_seconds: float = 3600.0,
        discovery_limit: int = 100,
    ) -> None:
        if rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if discovery_limit < 0:
            raise ValueError("discovery_limit must not be negative")

        self._client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": "DigDeeperLocal/0.1 (local catalog fetcher)"},
        )
        self._owns_client = http_client is None
        self._seed_repository = seed_repository
        self._country = country.upper()
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._clock = clock
        self._sleep = sleep
        self._cache_ttl_seconds = cache_ttl_seconds
        self._discovery_limit = discovery_limit
        self._rate_limiter = rate_limiter or AsyncTokenBucket(
            rate_limit_per_minute / 60.0,
            capacity=1.0,
            clock=clock,
            sleep=sleep,
        )
        self._search_cache: dict[tuple[str, str], tuple[float, tuple[Track, ...]]] = {}
        self._lookup_cache: dict[tuple[str, str], tuple[float, Track | None]] = {}

    @property
    def provider_id(self) -> str:
        return "itunes"

    async def aclose(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()

    async def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if limit <= 0:
            return ()
        tracks = await self._search_all(query)
        return tracks[:limit]

    async def lookup_track(self, provider_track_id: str) -> Track | None:
        if not isinstance(provider_track_id, str):
            raise TypeError("provider_track_id must be a string")
        provider_track_id = provider_track_id.strip()
        if not provider_track_id:
            raise ValueError("provider_track_id must not be empty")

        cache_key = (provider_track_id, self._country)
        cached = self._cache_get(self._lookup_cache, cache_key)
        if cached is not None:
            return cached

        payload = await self._request_json(
            f"{self._base_url}/lookup",
            {
                "id": provider_track_id,
                "entity": "song",
                "country": self._country,
            },
        )
        track: Track | None = None
        for item in payload.get("results", []):
            if not isinstance(item, Mapping):
                continue
            candidate = self._parse_track(item)
            if candidate is None:
                continue
            if candidate.external_id == provider_track_id:
                track = candidate
                break
        if track is not None:
            await self._discover_from_tracks((track,), seed_name=None)
        self._cache_set(self._lookup_cache, cache_key, track)
        return track

    async def list_artist_tracks(
        self,
        artist_name: str,
        *,
        limit: int = 50,
    ) -> Sequence[Track]:
        if not isinstance(artist_name, str):
            raise TypeError("artist_name must be a string")
        artist_name = artist_name.strip()
        if not artist_name:
            raise ValueError("artist_name must not be empty")
        if limit <= 0:
            return ()
        tracks = await self._search_all(artist_name)
        return tracks[:limit]

    async def fetch_preview(self, track: Track) -> bytes | None:
        if not isinstance(track, Track):
            raise TypeError("track must be a Track")
        if not track.preview_url:
            return None
        try:
            response = await self._client.get(track.preview_url)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"could not download preview for {track.display_name}"
            ) from exc
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.content
        return payload or None

    async def _search_all(self, query: str) -> tuple[Track, ...]:
        cache_key = (query.casefold(), self._country)
        cached = self._cache_get(self._search_cache, cache_key)
        if cached is not None:
            return cached

        payload = await self._request_json(
            f"{self._base_url}/search",
            {
                "term": query,
                "entity": "song",
                "attribute": "artistTerm",
                "limit": ITUNES_SEARCH_LIMIT,
                "country": self._country,
            },
        )
        tracks = self._filter_and_dedup(payload.get("results", []))
        await self._discover_from_tracks(tracks, seed_name=query)
        result = tuple(tracks)
        self._cache_set(self._search_cache, cache_key, result)
        return result

    def _filter_and_dedup(self, results: object) -> list[Track]:
        if not isinstance(results, list):
            return []
        tracks: list[Track] = []
        seen_ids: set[str] = set()
        seen_keys: set[str] = set()
        for item in results:
            if not isinstance(item, Mapping):
                continue
            track = self._parse_track(item)
            if track is None or not self._passes_filters(track):
                continue
            if track.external_id is None:
                continue
            if track.external_id in seen_ids:
                continue
            key = normalize_artist_title(track.artist, track.title)
            if key in seen_keys:
                continue
            seen_ids.add(track.external_id)
            seen_keys.add(key)
            tracks.append(track)
        return tracks

    @staticmethod
    def _passes_filters(track: Track) -> bool:
        if not track.preview_url:
            return False
        if track.duration_seconds is None:
            return False
        if not MIN_DURATION_SECONDS <= track.duration_seconds <= MAX_DURATION_SECONDS:
            return False
        if track.genre is not None:
            genre = track.genre.casefold().strip()
            if genre in NON_MUSIC_GENRES:
                return False
        return True

    @staticmethod
    def _parse_track(item: Mapping[str, Any]) -> Track | None:
        kind = item.get("kind")
        if kind is not None and str(kind).casefold() != "song":
            return None
        track_id = item.get("trackId")
        if isinstance(track_id, bool) or not isinstance(track_id, (int, str)):
            return None
        track_id_text = str(track_id).strip()
        if not track_id_text:
            return None
        title = item.get("trackName")
        artist = item.get("artistName")
        preview_url = item.get("previewUrl")
        if not isinstance(title, str) or not title.strip():
            return None
        if not isinstance(artist, str) or not artist.strip():
            return None
        if not isinstance(preview_url, str) or not preview_url.strip():
            return None

        duration = _duration_seconds(item.get("trackTimeMillis"))
        if duration is None:
            return None

        genre = item.get("primaryGenreName")
        album = item.get("collectionName")
        artwork_url = (
            item.get("artworkUrl100")
            or item.get("artworkUrl60")
            or item.get("artworkUrl30")
        )
        store_url = item.get("trackViewUrl")
        isrc = item.get("isrc")
        release_year = _release_year(item.get("releaseDate"))

        try:
            return Track(
                id=f"itunes:{track_id_text}",
                title=title,
                artist=artist,
                duration_seconds=duration,
                genre=genre if isinstance(genre, str) else None,
                release_year=release_year,
                isrc=isrc if isinstance(isrc, str) else None,
                preview_url=preview_url,
                artwork_url=artwork_url if isinstance(artwork_url, str) else None,
                album=album if isinstance(album, str) else None,
                store_url=store_url if isinstance(store_url, str) else None,
                source="itunes",
                external_id=track_id_text,
            )
        except (TypeError, ValueError):
            return None

    async def _discover_from_tracks(
        self,
        tracks: Sequence[Track],
        *,
        seed_name: str | None,
    ) -> None:
        if self._seed_repository is None or self._discovery_limit == 0:
            return
        seed_key = seed_name.casefold().strip() if seed_name else None
        counts: dict[str, list[Any]] = {}
        for track in tracks:
            for name in parse_collaborators(track.artist, track.title):
                key = name.casefold()
                if seed_key is not None and key == seed_key:
                    continue
                if key not in counts:
                    counts[key] = [name, 0, track.genre]
                counts[key][1] += 1

        discovered: list[SeedArtist] = []
        for name, count, genre in counts.values():
            if len(discovered) >= self._discovery_limit:
                break
            category = "electronic" if _is_electronic_genre(genre) else "general"
            base = 0.55 if category == "electronic" else 0.35
            priority = min(0.9, base + 0.05 * max(0, int(count) - 1))
            discovered.append(
                SeedArtist(
                    name=str(name),
                    priority_score=priority,
                    category=category,
                    status="pending",
                    source="itunes-snowball",
                )
            )
        if not discovered:
            return
        try:
            await self._seed_repository.record_discovery(discovered)
        except Exception:
            # Snowballing is a side effect; never fail the metadata fetch because
            # the seed table is temporarily unavailable.
            LOGGER.warning(
                "Could not persist iTunes snowball discoveries", exc_info=True
            )

    async def _request_json(
        self,
        url: str,
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        last_status: int | None = None
        for attempt in range(self._max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                response = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(f"iTunes request failed: {url}") from exc
                await self._sleep(exponential_backoff(attempt))
                continue

            last_status = response.status_code
            if response.status_code in (403, 429) or 500 <= response.status_code < 600:
                if attempt >= self._max_retries:
                    if response.status_code in (403, 429):
                        raise ProviderRateLimitError(
                            f"iTunes rate limited the request after "
                            f"{self._max_retries + 1} attempts"
                        )
                    raise ProviderError(
                        f"iTunes returned HTTP {response.status_code} after "
                        f"{self._max_retries + 1} attempts"
                    )
                delay = retry_after_seconds(
                    response,
                    exponential_backoff(attempt),
                )
                await self._sleep(delay)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ProviderError(
                    f"iTunes returned HTTP {response.status_code}: {url}"
                ) from exc
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderError("iTunes returned invalid JSON") from exc
            if not isinstance(payload, Mapping):
                raise ProviderError("iTunes returned an unexpected JSON shape")
            return payload

        raise ProviderError(
            f"iTunes request failed after retries (last status {last_status})"
        )

    def _cache_get(
        self,
        cache: dict[Any, tuple[float, Any]],
        key: Any,
    ) -> Any | None:
        entry = cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            cache.pop(key, None)
            return None
        return value

    def _cache_set(
        self,
        cache: dict[Any, tuple[float, Any]],
        key: Any,
        value: Any,
    ) -> None:
        cache[key] = (self._clock() + self._cache_ttl_seconds, value)


def _duration_seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    seconds = float(value) / 1000.0
    if seconds <= 0:
        return None
    return seconds


def _release_year(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = _YEAR_PATTERN.match(value.strip())
    if match is None:
        return None
    year = int(match.group("year"))
    return year if 1900 <= year <= 2100 else None


def _is_electronic_genre(genre: object) -> bool:
    if not isinstance(genre, str):
        return False
    normalized = genre.casefold()
    return any(hint in normalized for hint in ELECTRONIC_GENRE_HINTS)
