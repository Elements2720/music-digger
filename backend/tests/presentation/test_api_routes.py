"""API route tests over injected fakes (no GPU, network, or real storage)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from api_fakes import make_container, make_set, make_track

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
    response = await client.get("/api/tracks/search", params={"q": "a", "limit": 31})
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
    mark = await client.patch("/api/tracks/itunes:1/heard", json={"heard": True})
    assert mark.status_code == 200
    assert mark.json() == {"id": "itunes:1", "is_heard": True}

    unmark = await client.patch("/api/tracks/itunes:1/heard", json={"heard": False})
    assert unmark.status_code == 200
    assert unmark.json() == {"id": "itunes:1", "is_heard": False}

    search = await client.get("/api/tracks/search", params={"q": "night"})
    assert search.json()["tracks"][0]["is_heard"] is False


async def test_heard_toggle_unknown_track_is_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.patch("/api/tracks/missing/heard", json={"heard": True})
    assert response.status_code == 404


async def test_reset_embeddings_requires_confirmation(
    client: httpx.AsyncClient,
) -> None:
    refused = await client.post("/api/reset-embeddings", json={})
    assert refused.status_code == 400

    accepted = await client.post("/api/reset-embeddings", json={"confirm": True})
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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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


async def test_get_track_audio_endpoint_and_preview_url(
    tmp_path: Path,
) -> None:
    audio_file = tmp_path / "test_track.mp3"
    audio_file.write_bytes(b"FAKE_MP3_STREAM_CONTENT")

    local_track = make_track(
        "local:1234567890ab",
        title="Local Techno",
        artist="Underground Artist",
    )
    # Add local_path to track
    from dataclasses import replace

    local_track = replace(local_track, local_path=str(audio_file), source="local")

    container = make_container(tracks=[local_track])
    app = create_app(container=container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # Check track payload preview_url is rewritten to local audio endpoint
        search_res = await c.get("/api/tracks/search", params={"q": "Local"})
        assert search_res.status_code == 200
        tr_data = search_res.json()["tracks"][0]
        assert (
            tr_data["preview_url"] == "/api/catalog/tracks/local%3A1234567890ab/audio"
        )
        assert tr_data["local_path"] == str(audio_file)

        # Stream audio via the preview_url endpoint
        audio_res = await c.get(tr_data["preview_url"])
        assert audio_res.status_code == 200
        assert audio_res.content == b"FAKE_MP3_STREAM_CONTENT"

        # Backwards-compatible route also works
        audio_res_compat = await c.get("/api/tracks/local:1234567890ab/audio")
        assert audio_res_compat.status_code == 200

        # Nonexistent track -> 404
        missing_res = await c.get("/api/catalog/tracks/local%3Anonexistent/audio")
        assert missing_res.status_code == 404

        # Non-local track (or iTunes track) -> 404 cleanly, never 500
        itunes_audio_res = await c.get("/api/catalog/tracks/itunes%3A123/audio")
        assert itunes_audio_res.status_code == 404

        # Missing file on disk -> 404
        audio_file.unlink()
        disk_missing_res = await c.get("/api/catalog/tracks/local%3A1234567890ab/audio")
        assert disk_missing_res.status_code == 404

        # Unmatched /api/... paths with colons return JSON 404, never 500 WinError
        catch_all_res = await c.get("/api/does-not-exist/foo:bar")
        assert catch_all_res.status_code == 404
        assert catch_all_res.json() == {"detail": "API endpoint not found"}


async def test_import_local_job_params_validation_and_start(
    client: httpx.AsyncClient,
) -> None:
    bad = await client.post(
        "/api/jobs",
        json={"kind": "import-local", "params": {"folder_path": ""}},
    )
    assert bad.status_code == 422

    good = await client.post(
        "/api/jobs",
        json={
            "kind": "import-local",
            "params": {"folder_path": "C:\\Music\\Techno", "batch_size": 16},
        },
    )
    assert good.status_code == 200
    assert good.json()["job"]["kind"] == "import-local"


async def test_catalog_analytics_endpoint(client: httpx.AsyncClient) -> None:
    res = await client.get("/api/catalog/analytics")
    assert res.status_code == 200
    body = res.json()
    assert body["total_tracks"] == 3
    assert body["total_artists"] >= 1
    assert "genres" in body
    assert "bpm_buckets" in body


async def test_catalog_artists_and_tracks_endpoints(client: httpx.AsyncClient) -> None:
    res = await client.get("/api/catalog/artists")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 3
    assert len(body["artists"]) == 3

    # Test genre presets
    presets_res = await client.get("/api/catalog/genre-presets")
    assert presets_res.status_code == 200
    presets_body = presets_res.json()
    assert "Techno" in presets_body["presets"]
    assert "techno" in presets_body["electronic_tokens"]

    artist_res = await client.get("/api/catalog/artists/Solomun/tracks")
    assert artist_res.status_code == 200
    artist_body = artist_res.json()
    assert artist_body["artist"] == "Solomun"
    assert len(artist_body["tracks"]) == 1


async def test_delete_track_endpoint(client: httpx.AsyncClient) -> None:
    res = await client.delete(
        "/api/catalog/tracks/itunes:1",
        params={"blacklist": "true", "reason": "Too slow"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["blacklisted"] is True


async def test_delete_artist_endpoint(client: httpx.AsyncClient) -> None:
    res = await client.delete(
        "/api/catalog/artists/ARTBAT", params={"blacklist": "true"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["artist"] == "ARTBAT"
    assert body["blacklisted"] is True


async def test_blacklist_crud_endpoints(client: httpx.AsyncClient) -> None:
    # Add artist
    add_artist_res = await client.post(
        "/api/catalog/blacklist",
        json={"kind": "artist", "name": "Boring DJ", "reason": "Not energetic"},
    )
    assert add_artist_res.status_code == 200
    entry_id = add_artist_res.json()["id"]
    assert add_artist_res.json()["normalized_key"] == "boring dj"

    # Add track
    add_track_res = await client.post(
        "/api/catalog/blacklist",
        json={"kind": "track", "name": "Boring DJ", "track_title": "Sleep Song"},
    )
    assert add_track_res.status_code == 200

    # List
    list_res = await client.get("/api/catalog/blacklist")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 2

    # Delete
    del_res = await client.delete(f"/api/catalog/blacklist/{entry_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


async def test_seeds_endpoints(client: httpx.AsyncClient) -> None:
    # 1. List all seeds and check breakdown
    res = await client.get("/api/catalog/seeds")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 7
    assert len(body["seeds"]) == 7
    assert body["breakdown"]["total"] == 7
    assert body["breakdown"]["pending"] == 3
    assert body["breakdown"]["failed"] == 1
    assert len(body["breakdown"]["by_source"]) >= 3

    # 2. Filter by status
    pending_res = await client.get("/api/catalog/seeds", params={"status": "pending"})
    assert pending_res.status_code == 200
    assert pending_res.json()["total"] == 3

    # 3. Filter by search query
    search_res = await client.get("/api/catalog/seeds", params={"q": "Tale"})
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1
    assert search_res.json()["seeds"][0]["name"] == "Tale of Us"

    # 4. Delete single seed
    del_res = await client.delete("/api/catalog/seeds/ARTBAT")
    assert del_res.status_code == 200
    assert del_res.json() == {"name": "ARTBAT", "deleted": True}

    # Verify deleted
    after_del = await client.get("/api/catalog/seeds", params={"q": "ARTBAT"})
    assert after_del.json()["total"] == 0

    # 5. Purge failed seeds
    purge_res = await client.post("/api/catalog/seeds/purge", json={"status": "failed"})
    assert purge_res.status_code == 200
    assert purge_res.json()["purged"] == 1


async def test_liked_artists_endpoints(client: httpx.AsyncClient) -> None:
    # 1. Initial list is empty
    res = await client.get("/api/catalog/liked-artists")
    assert res.status_code == 200
    assert res.json()["liked_artists"] == []
    assert res.json()["total"] == 0

    # 2. Like an artist
    like_res = await client.post("/api/catalog/liked-artists/Enrico%20Sangiuliano")
    assert like_res.status_code == 200
    body = like_res.json()
    assert body["liked"] is True
    assert body["artist"]["artist_name"] == "Enrico Sangiuliano"
    assert body["artist"]["normalized_key"] == "enrico sangiuliano"

    # 3. List shows the liked artist
    list_res = await client.get("/api/catalog/liked-artists")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1
    assert list_res.json()["liked_artists"][0]["artist_name"] == "Enrico Sangiuliano"

    # 4. Filter artists by liked_only
    artists_res = await client.get(
        "/api/catalog/artists", params={"liked_only": "true"}
    )
    assert artists_res.status_code == 200

    # 5. Unlike the artist
    unlike_res = await client.delete("/api/catalog/liked-artists/Enrico%20Sangiuliano")
    assert unlike_res.status_code == 200
    assert unlike_res.json()["deleted"] is True

    # 6. Verify list is empty again
    empty_res = await client.get("/api/catalog/liked-artists")
    assert empty_res.status_code == 200
    assert empty_res.json()["total"] == 0
    assert empty_res.json()["liked_artists"] == []


async def test_similar_liked_artists_endpoint(client: httpx.AsyncClient) -> None:
    # Query similar artists
    res = await client.get(
        "/api/catalog/liked-artists/similar",
        params={"artist": "Test Artist", "limit": 10},
    )
    assert res.status_code == 200
    data = res.json()
    assert "seed_artists" in data
    assert "items" in data


async def test_set_helper_endpoints(client: httpx.AsyncClient) -> None:
    # 1. Suggest next track
    suggest_res = await client.post(
        "/api/set-helper/suggest-next",
        json={"from_track_id": "itunes:1", "limit": 5, "flow": "steady"},
    )
    assert suggest_res.status_code == 200
    assert "suggestions" in suggest_res.json()

    # 2. Bridge between two tracks
    bridge_res = await client.post(
        "/api/set-helper/bridge",
        json={"track_a_id": "itunes:1", "track_b_id": "itunes:2", "limit": 5},
    )
    assert bridge_res.status_code == 200
    assert "bridges" in bridge_res.json()

    # 3. Auto-sequence
    auto_res = await client.post(
        "/api/set-helper/auto-sequence",
        json={"track_ids": ["itunes:2", "itunes:1"], "flow": "ramp_up"},
    )
    assert auto_res.status_code == 200
    assert len(auto_res.json()["ordered_track_ids"]) == 2

    # 4. Evaluate sequence
    eval_res = await client.post(
        "/api/set-helper/evaluate",
        json={"track_ids": ["itunes:1", "itunes:2"], "flow": "steady"},
    )
    assert eval_res.status_code == 200
    assert len(eval_res.json()["transitions"]) == 1

    # 5. CRUD Planned Sets
    # Create
    create_res = await client.post(
        "/api/set-helper/sets",
        json={"name": "Friday Peak", "track_ids": ["itunes:1", "itunes:2"]},
    )
    assert create_res.status_code == 200
    set_data = create_res.json()
    assert set_data["name"] == "Friday Peak"
    assert set_data["track_ids"] == ["itunes:1", "itunes:2"]
    set_id = set_data["id"]

    # List
    list_res = await client.get("/api/set-helper/sets")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # Get by ID
    get_res = await client.get(f"/api/set-helper/sets/{set_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == set_id
    assert len(get_res.json()["tracks"]) == 2

    # Update
    update_res = await client.put(
        f"/api/set-helper/sets/{set_id}",
        json={"name": "Friday Peak Rev 1", "track_ids": ["itunes:2", "itunes:1"]},
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Friday Peak Rev 1"
    assert update_res.json()["track_ids"] == ["itunes:2", "itunes:1"]

    # Export M3U8
    export_res = await client.get(f"/api/set-helper/sets/{set_id}/export.m3u8")
    assert export_res.status_code == 200
    assert "audio/x-mpegurl" in export_res.headers.get(
        "content-type", ""
    ) or "application/x-mpegurl" in export_res.headers.get("content-type", "")
    assert "#EXTM3U" in export_res.text

    # Delete
    del_res = await client.delete(f"/api/set-helper/sets/{set_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True


async def test_bulk_delete_artists_api(client: httpx.AsyncClient) -> None:
    res = await client.post(
        "/api/catalog/artists/bulk-delete",
        json={
            "artist_names": ["Solomun", "Tale Of Us"],
            "blacklist": True,
            "reason": "Test API bulk delete",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["artists_requested"] == 2
    assert data["artists_deleted"] == 2
    assert data["tracks_deleted"] == 2
    assert data["blacklisted_count"] == 2

    # Blacklist contains the artists
    bl_res = await client.get("/api/catalog/blacklist")
    assert bl_res.status_code == 200
    blocked_names = [e["artist_name"] for e in bl_res.json()["entries"]]
    assert "Solomun" in blocked_names
    assert "Tale Of Us" in blocked_names


async def test_bulk_cleanup_preview_and_execute_api(
    client: httpx.AsyncClient,
) -> None:
    # 422 when empty
    err_res = await client.post(
        "/api/catalog/artists/bulk-cleanup/preview",
        json={},
    )
    assert err_res.status_code == 422

    # Valid preview
    prev_res = await client.post(
        "/api/catalog/artists/bulk-cleanup/preview",
        json={"max_taste_percent": 90.0, "genre": None},
    )
    assert prev_res.status_code == 200
    prev_data = prev_res.json()
    assert "artist_count" in prev_data
    assert "track_count" in prev_data
    assert "sample_artists" in prev_data

    # Execute
    exec_res = await client.post(
        "/api/catalog/artists/bulk-cleanup",
        json={
            "max_taste_percent": 90.0,
            "blacklist": True,
            "reason": "Clean low taste",
        },
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["artists_deleted"] == prev_data["artist_count"]


async def test_download_track_endpoint_success(client: httpx.AsyncClient) -> None:
    res = await client.post("/api/catalog/tracks/itunes:1/download")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "itunes:1"
    assert data["has_local_file"] is True
    assert data["local_path"] is not None
    assert data["local_path"].endswith(".m4a")
    assert data["preview_url"] == "/api/catalog/tracks/itunes%3A1/audio"


async def test_download_track_endpoint_not_found(client: httpx.AsyncClient) -> None:
    res = await client.post("/api/catalog/tracks/nonexistent/download")
    assert res.status_code == 404


async def test_get_track_audio_stream_local_file(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    # First test 404 when track has no local file
    not_local = await client.get("/api/catalog/tracks/itunes:2/audio")
    assert not_local.status_code == 404

    # Now create real dummy file and set local_path on itunes:1
    test_audio = tmp_path / "test_track.m4a"
    test_audio.write_bytes(b"\x00\x00\x00\x20ftypM4A ")

    # We need to update the container's track repository directly
    # Using the downloader endpoint with a fake that writes the file:

    # Download itunes:1
    res = await client.post("/api/catalog/tracks/itunes:1/download")
    assert res.status_code == 200
    local_path = Path(res.json()["local_path"])
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(b"FAKE_M4A_DATA")

    # Now streaming it should return 200 with audio/mp4 media type
    stream_res = await client.get("/api/catalog/tracks/itunes:1/audio")
    assert stream_res.status_code == 200
    assert stream_res.content == b"FAKE_M4A_DATA"
    assert stream_res.headers["content-type"] == "audio/mp4"

    # Byte-range request should return 206 Partial Content
    range_res = await client.get(
        "/api/catalog/tracks/itunes:1/audio", headers={"Range": "bytes=0-3"}
    )
    assert range_res.status_code == 206
    assert range_res.content == b"FAKE"
    assert range_res.headers["content-type"] == "audio/mp4"
    assert "bytes 0-3/" in range_res.headers["content-range"]

    # Clean up
    if local_path.is_file():
        local_path.unlink()


def test_track_dto_from_domain() -> None:
    from presentation.api.schemas import TrackDTO

    remote_track = make_track("rem:1", preview_url="https://preview.test/1.m4a")
    dto_remote = TrackDTO.from_domain(remote_track)
    assert dto_remote.has_local_file is False
    assert dto_remote.preview_url == "https://preview.test/1.m4a"

    local_track = remote_track.with_local_path("storage/downloads/test.m4a")
    dto_local = TrackDTO.from_domain(local_track)
    assert dto_local.has_local_file is True
    assert dto_local.preview_url == "/api/catalog/tracks/rem%3A1/audio"
