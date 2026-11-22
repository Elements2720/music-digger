"""Tests for the OpenAI-compatible LLM client with mocked HTTP."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from data.errors import LLMError
from data.llm.multi_llm_client import MultiLLMClient
from domain.entities.track import Track


def _chat_response(payload: Any) -> dict[str, Any]:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _make_client(handler: httpx.MockTransport) -> MultiLLMClient:
    return MultiLLMClient(
        base_url="http://llm.test/v1",
        api_key="local",
        model="test-model",
        http_client=httpx.AsyncClient(transport=handler, timeout=5.0),
        max_retries=1,
    )


async def test_generate_seed_artists_parses_and_deduplicates() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200,
            json=_chat_response(
                {
                    "artists": [
                        {
                            "name": "Anyma",
                            "category": "electronic",
                            "priority_score": 0.8,
                        },
                        {"name": "anyma", "category": "electronic"},
                        {"name": "Dua Lipa", "category": "general"},
                        {"name": "No Category", "category": "jazz"},
                        {"name": ""},
                    ]
                }
            ),
        )

    client = _make_client(httpx.MockTransport(handler))
    try:
        seeds = await client.generate_seed_artists(
            genres=("Melodic Techno",),
            count=5,
            exclude_artists=("Dua Lipa",),
        )
    finally:
        await client.aclose()

    names = [seed.name for seed in seeds]
    assert names == ["Anyma", "No Category"]
    assert seeds[0].category == "electronic"
    assert seeds[0].priority_score == pytest.approx(0.8)
    assert seeds[1].category == "electronic", "unknown categories fall back to genre"
    assert seen[0]["model"] == "test-model"
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert client.endpoint == "http://llm.test/v1/chat/completions"


async def test_generate_seed_artists_requires_genres() -> None:
    client = _make_client(
        httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )
    try:
        with pytest.raises(ValueError, match="genre"):
            await client.generate_seed_artists(genres=(), count=5)
        with pytest.raises(ValueError, match="count"):
            await client.generate_seed_artists(genres=("Techno",), count=0)
    finally:
        await client.aclose()


async def test_generate_seed_artists_raises_on_invalid_json() -> None:
    client = _make_client(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json=_chat_response("no json here"))
        )
    )
    try:
        with pytest.raises(LLMError):
            await client.generate_seed_artists(genres=("Techno",), count=1)
    finally:
        await client.aclose()


async def test_chat_retries_without_response_format_on_400() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "unsupported"})
        return httpx.Response(
            200,
            json=_chat_response(
                {"artists": [{"name": "Bicep", "category": "electronic"}]}
            ),
        )

    client = _make_client(httpx.MockTransport(handler))
    try:
        seeds = await client.generate_seed_artists(genres=("Techno",), count=1)
    finally:
        await client.aclose()
    assert len(calls) == 2
    assert "response_format" not in calls[1]
    assert [seed.name for seed in seeds] == ["Bicep"]


async def test_extract_tracklist_builds_references() -> None:
    client = _make_client(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=_chat_response(
                    {
                        "tracks": [
                            {
                                "artist": "Bicep",
                                "title": "Glue",
                                "start_seconds": 120,
                                "end_seconds": 180,
                                "confidence": 0.9,
                            },
                            {"artist": "Anyma", "title": "Explore"},
                        ]
                    }
                ),
            )
        )
    )
    try:
        references = await client.extract_tracklist_from_comments(
            ["00:02 Bicep - Glue", "Anyma - Explore"]
        )
    finally:
        await client.aclose()
    assert references[0].display_name == "Bicep - Glue"
    assert references[0].timestamp is not None
    assert references[0].timestamp.start_seconds == 120.0
    assert references[1].timestamp is None
    assert references[1].confidence == pytest.approx(0.5)


async def test_tag_track_vibe_parses_response() -> None:
    client = _make_client(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=_chat_response(
                    {
                        "tags": ["peak time", "melodic"],
                        "mood": "Euphoric",
                        "energy": 0.85,
                        "description": "Big room closer.",
                    }
                ),
            )
        )
    )
    try:
        vibe = await client.tag_track_vibe(
            Track(id="t", title="Song", artist="Artist", genre="Techno")
        )
    finally:
        await client.aclose()
    assert vibe.mood == "Euphoric"
    assert vibe.energy == pytest.approx(0.85)
    assert vibe.tags == ("peak time", "melodic")


async def test_client_validates_configuration() -> None:
    with pytest.raises(ValueError, match="base_url"):
        MultiLLMClient(base_url="  ", model="m")
    with pytest.raises(ValueError, match="model"):
        MultiLLMClient(base_url="http://x", model=" ")
