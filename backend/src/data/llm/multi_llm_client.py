"""OpenAI-compatible local LLM client.

Works with Ollama, LM Studio, vLLM, llama.cpp, or any server exposing
``POST {LLM_BASE_URL}/chat/completions``. The client asks for JSON and parses it
defensively because small local models often wrap JSON in prose or fences.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from domain.entities.track import (
    SEED_CATEGORIES,
    SeedArtist,
    Track,
    TrackReference,
    TrackVibe,
)
from domain.interfaces.llm import ILLMService
from domain.value_objects.audio_features import TimeRange

from ..datasources.remote.rate_limiter import Sleep, exponential_backoff
from ..errors import LLMError

LOGGER = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.IGNORECASE)


class MultiLLMClient(ILLMService):
    """Async client for an OpenAI-compatible local chat-completions endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "local",
        model: str,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if not base_url or not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not model or not model.strip():
            raise ValueError("model must not be empty")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        # Sent per request, never merged into a shared http_client's default
        # headers: that client may also serve iTunes/Deezer and must never
        # leak the LLM credentials to third parties.
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers=self._headers,
        )
        self._owns_client = http_client is None

    @property
    def endpoint(self) -> str:
        """Full chat-completions URL."""
        if self._base_url.endswith("/chat/completions"):
            return self._base_url
        return f"{self._base_url}/chat/completions"

    async def aclose(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()

    async def generate_seed_artists(
        self,
        *,
        genres: Sequence[str],
        count: int = 25,
        exclude_artists: Sequence[str] = (),
    ) -> Sequence[SeedArtist]:
        if count <= 0:
            raise ValueError("count must be positive")
        genre_list = tuple(genre.strip() for genre in genres if genre.strip())
        if not genre_list:
            raise ValueError("at least one genre is required")
        excluded = {name.casefold().strip() for name in exclude_artists}
        prompt = (
            "You are curating a local DJ music catalog. Return ONLY a JSON object "
            'with an "artists" array. Each item must have "name", "category" '
            '("electronic" or "general"), and "priority_score" (0.0-1.0).\n'
            f"Genres: {', '.join(genre_list)}\n"
            f"Requested count: {count}\n"
            "Aim for roughly 75% electronic/club artists and 25% general-genre "
            "artists. Include underground artists, not only headliners.\n"
        )
        if excluded:
            prompt += "Exclude these artists: " + ", ".join(sorted(excluded)) + "\n"
        content = await self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        payload = self._parse_json(content)
        raw_items = payload.get("artists") if isinstance(payload, Mapping) else payload
        if not isinstance(raw_items, list):
            raise LLMError("LLM seed response did not contain an artist list")

        seeds: list[SeedArtist] = []
        seen: set[str] = set()
        for item in raw_items:
            seed = self._seed_from_item(item, genre_list)
            if seed is None:
                continue
            key = seed.name.casefold()
            if key in excluded or key in seen:
                continue
            seen.add(key)
            seeds.append(seed)
            if len(seeds) >= count:
                break
        return tuple(seeds)

    async def extract_tracklist_from_comments(
        self,
        comments: Sequence[str],
        *,
        context: str | None = None,
    ) -> Sequence[TrackReference]:
        if not comments:
            return ()
        prompt = (
            "Extract only confidently stated artist/title references from these "
            'comments. Return ONLY a JSON object with a "tracks" array. Each '
            'item: {"artist": str, "title": str, "start_seconds": number|null, '
            '"end_seconds": number|null, "confidence": 0.0-1.0}. Do not invent '
            "tracks.\n"
        )
        if context:
            prompt += f"Context: {context}\n"
        prompt += "Comments:\n" + "\n".join(f"- {comment}" for comment in comments)
        content = await self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        payload = self._parse_json(content)
        raw_items = payload.get("tracks") if isinstance(payload, Mapping) else payload
        if not isinstance(raw_items, list):
            raise LLMError("LLM tracklist response did not contain a track list")

        references: list[TrackReference] = []
        for item in raw_items:
            if not isinstance(item, Mapping):
                continue
            artist = item.get("artist")
            title = item.get("title")
            if not isinstance(artist, str) or not isinstance(title, str):
                continue
            timestamp = self._time_range(
                item.get("start_seconds"),
                item.get("end_seconds"),
            )
            confidence = _clamp_float(item.get("confidence", 0.5))
            try:
                references.append(
                    TrackReference(
                        artist=artist,
                        title=title,
                        timestamp=timestamp,
                        confidence=confidence,
                    )
                )
            except (TypeError, ValueError):
                continue
        return tuple(references)

    async def tag_track_vibe(self, track: Track) -> TrackVibe:
        if not isinstance(track, Track):
            raise TypeError("track must be a Track")
        prompt = (
            "Describe the vibe of this track for a DJ library. Return ONLY a JSON "
            'object: {"tags": [str], "mood": str, "energy": 0.0-1.0, '
            '"description": str}.\n'
            f"Artist: {track.artist}\nTitle: {track.title}\n"
            f"Genre: {track.genre or 'unknown'}\n"
        )
        content = await self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        payload = self._parse_json(content)
        if not isinstance(payload, Mapping):
            raise LLMError("LLM vibe response was not a JSON object")
        tags = payload.get("tags", ())
        if isinstance(tags, str):
            tags = [tags]
        if not isinstance(tags, list):
            tags = []
        return TrackVibe(
            tags=tuple(str(tag) for tag in tags if str(tag).strip()),
            mood=str(payload.get("mood", "Unknown")).strip() or "Unknown",
            energy=_clamp_float(payload.get("energy", 0.5)),
            description=str(payload.get("description", "")).strip(),
        )

    async def _chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        temperature: float,
        response_format: Mapping[str, str] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "temperature": temperature,
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = dict(response_format)

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    self.endpoint,
                    json=payload,
                    headers=self._headers,
                    # Per-request override: a shared client may carry a much
                    # shorter timeout (e.g. the iTunes one) than LLM calls
                    # need — a reasoning model can easily exceed 30 s.
                    timeout=self._timeout_seconds,
                )
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise LLMError("LLM request failed") from exc
                await self._sleep(exponential_backoff(attempt))
                continue

            if response.status_code == 400 and "response_format" in payload:
                # Some local servers reject response_format. Retry once without it.
                payload.pop("response_format", None)
                continue
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt >= self._max_retries:
                    raise LLMError(
                        f"LLM returned HTTP {response.status_code} after retries"
                    )
                await self._sleep(exponential_backoff(attempt))
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LLMError(f"LLM returned HTTP {response.status_code}") from exc
            try:
                body = response.json()
            except ValueError as exc:
                raise LLMError("LLM returned invalid JSON") from exc
            content = _extract_content(body)
            if not content:
                raise LLMError("LLM returned an empty message")
            return content

        raise LLMError("LLM request failed after retries")

    @staticmethod
    def _parse_json(content: str) -> Any:
        cleaned = _CODE_FENCE.sub("", content.strip()).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        start_candidates = [
            index for index in (cleaned.find("{"), cleaned.find("[")) if index >= 0
        ]
        if not start_candidates:
            raise LLMError("LLM response did not contain JSON")
        start = min(start_candidates)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if end <= start:
            raise LLMError("LLM response contained incomplete JSON")
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("Could not parse LLM JSON response") from exc

    @staticmethod
    def _seed_from_item(
        item: object,
        genres: Sequence[str],
    ) -> SeedArtist | None:
        if isinstance(item, str):
            name = item.strip()
            category = _infer_category(genres)
            priority = 0.6
        elif isinstance(item, Mapping):
            name = str(item.get("name", "")).strip()
            category = str(item.get("category", _infer_category(genres))).strip()
            priority = _clamp_float(item.get("priority_score", 0.6))
        else:
            return None
        if not name:
            return None
        if category not in SEED_CATEGORIES:
            category = _infer_category(genres)
        try:
            return SeedArtist(
                name=name,
                priority_score=priority,
                category=category,  # type: ignore[arg-type]
                status="pending",
                source="llm",
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _time_range(start: object, end: object) -> TimeRange | None:
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            return None
        if isinstance(start, bool) or isinstance(end, bool):
            return None
        try:
            return TimeRange(float(start), float(end))
        except ValueError:
            return None


def _extract_content(body: object) -> str:
    if not isinstance(body, Mapping):
        return ""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message")
    if not isinstance(message, Mapping):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _clamp_float(value: object, default: float = 0.5) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    if math.isnan(number):
        return default
    return max(0.0, min(1.0, number))


def _infer_category(genres: Sequence[str]) -> str:
    electronic_hints = {
        "techno",
        "house",
        "trance",
        "electronic",
        "club",
        "dance",
        "drum",
        "bass",
        "minimal",
        "disco",
        "afro",
    }
    for genre in genres:
        lowered = genre.casefold()
        if any(hint in lowered for hint in electronic_hints):
            return "electronic"
    return "general"
