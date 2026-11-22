"""API route tests over injected fakes (no GPU, network, or real storage)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from api_fakes import make_container, make_set

from domain.entities.dj_set import SetMatch
from presentation.api import create_app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(container=make_container())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_stats_reports_seed_track_and_set_counts(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["seeds"]["total"] == 7
    assert body["seeds"]["pending"] == 3
    assert body["tracks"] == {"total": 3, "embedded": 2}
    assert body["sets"]["total"] == 1


async def test_search_is_case_insensitive_and_marks_heard(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/tracks/search", params={"q": "night"})
    assert response.status_code == 200
    tracks = response.json()["tracks"]
    assert [track["id"] for track in tracks] == ["itunes:1"]
    assert tracks[0]["bpm"] == 126.0
    assert tracks[0]["key"] == "8A"
    assert tracks[0]["is_heard"] is False


async def test_search_limit_is_capped_at_thirty(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/tracks/search", params={"q": "a", "limit": 31}
    )
    assert response.status_code == 422


async def test_recent_tracks_lists_only_embedded(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/tracks/recent")
    assert response.status_code == 200
    body = response.json()
    assert {track["id"] for track in body["tracks"]} == {"itunes:1", "itunes:2"}
    assert body["embedded_total"] == 2


async def test_dig_returns_reference_and_similar_tracks(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/dig/itunes:1", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["reference"]["id"] == "itunes:1"
    assert [match["track"]["id"] for match in body["matches"]] == ["itunes:2"]
    assert 0 <= body["matches"][0]["similarity"] <= 100


async def test_dig_unknown_track_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/dig/missing")
    assert response.status_code == 404


async def test_vibe_search_returns_ranked_matches(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/vibe-search",
        json={"query": "dark hypnotic techno", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "dark hypnotic techno"
    assert body["matches"][0]["track"]["id"] == "itunes:1"


async def test_vibe_search_blank_query_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/vibe-search", json={"query": "   "})
    assert response.status_code == 422


async def test_heard_toggle_works_both_ways(client: httpx.AsyncClient) -> None:
    mark = await client.patch(
        "/api/tracks/itunes:1/heard", json={"heard": True}
    )
    assert mark.status_code == 200
    assert mark.json() == {"id": "itunes:1", "is_heard": True}

    unmark = await client.patch(
        "/api/tracks/itunes:1/heard", json={"heard": False}
    )
    assert unmark.status_code == 200
    assert unmark.json() == {"id": "itunes:1", "is_heard": False}

    search = await client.get("/api/tracks/search", params={"q": "night"})
    assert search.json()["tracks"][0]["is_heard"] is False


async def test_heard_toggle_unknown_track_is_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.patch(
        "/api/tracks/missing/heard", json={"heard": True}
    )
    assert response.status_code == 404


async def test_reset_embeddings_requires_confirmation(
    client: httpx.AsyncClient,
) -> None:
    refused = await client.post("/api/reset-embeddings", json={})
    assert refused.status_code == 400

    accepted = await client.post(
        "/api/reset-embeddings", json={"confirm": True}
    )
    assert accepted.status_code == 200
    assert accepted.json() == {"cleared": 2}


async def test_sets_list_and_tracklist(client: httpx.AsyncClient) -> None:
    listing = await client.get("/api/sets")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["sets"]] == ["set:1"]

    detail = await client.get("/api/sets/set:1")
    assert detail.status_code == 200
    body = detail.json()
    assert body["set"]["passage_count"] == 1
    passage = body["passages"][0]
    assert passage["exact_id_display_name"] == "Solomun - Night Drive"
    assert passage["matches"][0]["track"]["id"] == "itunes:1"


async def test_set_tracks_view_returns_dig_matches(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        "/api/sets/set:1", params={"view": "tracks", "limit": 5}
    )
    assert response.status_code == 200
    matches = response.json()["matches"]
    assert matches[0]["track"]["id"] == "itunes:1"


async def test_set_similar_sets_view_excludes_itself() -> None:
    other = make_set("set:2")
    container = make_container(
        similar_sets=(
            SetMatch(dj_set=make_set("set:1"), similarity_score=1.0),
            SetMatch(dj_set=other, similarity_score=0.81),
        )
    )
    transport = httpx.ASGITransport(app=create_app(container=container))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get("/api/sets/set:1", params={"view": "sets"})
    assert response.status_code == 200
    similar = response.json()["sets"]
    assert [item["set"]["id"] for item in similar] == ["set:2"]
    assert similar[0]["similarity"] == 81.0


async def test_unknown_set_and_view_errors(client: httpx.AsyncClient) -> None:
    missing = await client.get("/api/sets/missing")
    assert missing.status_code == 404

    bad_view = await client.get("/api/sets/set:1", params={"view": "nope"})
    assert bad_view.status_code == 422


async def test_hardware_probe_is_exposed(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/hardware")
    assert response.status_code == 200
    body = response.json()
    assert body["gpu_name"] == "GTX 1660 Super"
    assert body["gpu_ready"] is True
    assert body["has_ffmpeg"] is True


async def test_seed_itunes_job_params_validation_and_start(
    client: httpx.AsyncClient,
) -> None:
    bad = await client.post(
        "/api/jobs",
        json={"kind": "seed-itunes", "params": {"tracks_per_term": 500}},
    )
    assert bad.status_code == 422

    good = await client.post(
        "/api/jobs",
        json={"kind": "seed-itunes", "params": {"tracks_per_term": 50}},
    )
    assert good.status_code == 200
    assert good.json()["job"]["kind"] == "seed-itunes"

