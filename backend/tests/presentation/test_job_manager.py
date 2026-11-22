"""JobManager tests: validation, turbo scoping, progress, cancel, cookies."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from api_fakes import FakeIndexCatalog, make_container

from presentation.api.job_manager import (
    JobConflictError,
    JobManager,
    JobParamError,
)


class FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


def parse_frame(frame: str) -> dict | None:
    if not frame.startswith("data: "):
        return None
    return json.loads(frame[len("data: ") :])


def make_manager(container, **kwargs) -> JobManager:
    return JobManager(lambda: container, **kwargs)


async def test_index_job_streams_progress_and_finishes() -> None:
    container = make_container()
    manager = make_manager(container)
    stream = manager.stream(FakeRequest())

    first = parse_frame(await stream.__anext__())
    assert first == {"type": "state", "job": None}

    await manager.start("index", {"limit": 2})
    events = []
    async for frame in stream:
        event = parse_frame(frame)
        if event is not None:
            events.append(event)

    assert [event["type"] for event in events][-1] == "done"
    progress = [event for event in events if event["type"] == "progress"]
    assert [event["job"]["processed"] for event in progress] == [1, 2]
    assert progress[-1]["job"]["failed"] == 1
    assert progress[-1]["speed"] is not None
    assert progress[-1]["memory"]["vram_total_mb"] == 6144

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "done"
    assert snapshot["result"] == {
        "processed": 2,
        "failed": 1,
        "embedded_total": 9,
    }
    assert manager.active is False


async def test_seed_crawl_job_streams_progress_and_finishes() -> None:
    container = make_container()
    manager = make_manager(container)
    stream = manager.stream(FakeRequest())
    await stream.__anext__()  # initial state

    await manager.start("seed-crawl", {"electronic_limit": 50, "general_limit": 10})
    events = []
    async for frame in stream:
        event = parse_frame(frame)
        if event is not None:
            events.append(event)

    assert [event["type"] for event in events][-1] == "done"
    progress = [event for event in events if event["type"] == "progress"]
    assert len(progress) == 2
    assert progress[0]["job"]["stage"] == "crawling Deezer"
    assert progress[0]["job"]["message"] == "Solomun"
    assert progress[0]["job"]["total"] == 60
    assert progress[0]["job"]["processed"] == 1
    assert progress[1]["job"]["stage"] == "writing"
    assert progress[1]["job"]["total"] == 60
    assert progress[1]["job"]["processed"] == 15

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "done"
    assert snapshot["result"] == {
        "discovered": 10,
        "llm_generated": 5,
        "written": 15,
        "electronic_total": 100,
        "general_total": 40,
    }
    assert manager.active is False


async def test_only_one_job_at_a_time_and_cancel() -> None:
    catalog = FakeIndexCatalog()
    container = make_container(index_catalog=catalog)
    manager = make_manager(container)

    await manager.start("index", {"limit": 1})
    with pytest.raises(JobConflictError):
        await manager.start("index", {"limit": 1})

    assert await manager.cancel() is True
    await manager.wait()

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "cancelled"
    assert manager.active is False
    assert await manager.cancel() is False


async def test_invalid_parameters_are_rejected_before_starting() -> None:
    manager = make_manager(make_container())

    with pytest.raises(JobParamError):
        await manager.start("index", {"batch_size": 99})
    with pytest.raises(JobParamError):
        await manager.start("seed-llm", {"genre": "   "})
    with pytest.raises(JobParamError):
        await manager.start("seed-itunes", {"tracks_per_term": 500})
    with pytest.raises(JobParamError):
        await manager.start("seed-itunes", {"terms": []})
    with pytest.raises(JobParamError):
        await manager.start("seed-itunes", {"terms": "   "})
    with pytest.raises(JobParamError):
        await manager.start("nope", {})


async def test_turbo_overrides_shared_instances_then_restores_them() -> None:
    container = make_container()
    FakeIndexCatalog.instances.clear()
    manager = make_manager(container, index_factory=FakeIndexCatalog)

    await manager.start("index", {"limit": 5, "turbo": True})
    await manager.wait()

    assert FakeIndexCatalog.instances[0]["cpu_workers"] == 10
    assert FakeIndexCatalog.instances[0]["queue_maxsize"] == 128
    assert container.clap_embedder.batch_size == 16, "batch size is restored"
    assert container.audio_decoder.concurrency == 16, "concurrency is restored"

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "done"


async def test_non_turbo_uses_the_shared_index_catalog() -> None:
    catalog = FakeIndexCatalog()
    container = make_container(index_catalog=catalog)
    FakeIndexCatalog.instances.clear()
    manager = make_manager(container, index_factory=FakeIndexCatalog)

    await manager.start("index", {"limit": 5, "batch_size": 8})
    await manager.wait()

    assert FakeIndexCatalog.instances == [], "no fresh catalog for a normal run"
    assert container.clap_embedder.batch_size == 16
    assert container.audio_decoder.concurrency == 16


async def test_analyze_set_cookie_overrides_are_scoped_and_restored() -> None:
    container = make_container()
    manager = make_manager(container)

    await manager.start(
        "analyze-set",
        {
            "source": "https://youtube.test/watch?v=1",
            "cookies_file": "C:/secrets/cookies.txt",
            "cookies_from_browser": "firefox",
        },
    )
    await manager.wait()

    assert container.set_downloader.calls == [
        (Path("C:/secrets/cookies.txt"), "firefox"),
        (None, None),
    ]
    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "done"
    assert snapshot["result"]["set"]["id"] == "set:1"


async def test_analyze_set_progress_emits_speed_and_failed() -> None:
    container = make_container()
    manager = make_manager(container)
    stream = manager.stream(FakeRequest())
    await stream.__anext__()  # initial state

    await manager.start(
        "analyze-set",
        {"source": "https://youtube.test/watch?v=1"},
    )
    events = []
    async for frame in stream:
        event = parse_frame(frame)
        if event is not None:
            events.append(event)

    assert [event["type"] for event in events][-1] == "done"
    progress = [event for event in events if event["type"] == "progress"]
    assert progress
    p = progress[0]
    assert "speed" in p
    assert p["job"]["stage"] == "analyze"
    assert p["job"]["processed"] == 1
    assert p["job"]["total"] == 2
    assert p["job"]["failed"] == 0


async def test_analyze_set_resets_circuit_breaker_on_start() -> None:
    class FakeShazamWithBreaker:
        def __init__(self) -> None:
            self.reset_called = False

        def reset_circuit_breaker(self) -> None:
            self.reset_called = True

    shazam = FakeShazamWithBreaker()
    container = make_container()
    container.shazam_fingerprinter = shazam
    manager = make_manager(container)

    await manager.start(
        "analyze-set",
        {"source": "https://youtube.test/watch?v=1"},
    )
    await manager.wait()
    assert shazam.reset_called is True


async def test_seed_llm_job_reports_seed_counts() -> None:
    container = make_container()
    manager = make_manager(container)

    await manager.start(
        "seed-llm", {"genre": "Melodic Techno, Afro House", "count": 100}
    )
    await manager.wait()

    call = container.build_seed_list.calls[0]
    assert call["llm_genres"] == ("Melodic Techno", "Afro House")
    assert call["llm_count"] == 100
    assert call["use_deezer"] is False

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["result"] == {
        "discovered": 10,
        "llm_generated": 5,
        "written": 15,
        "electronic_total": 100,
        "general_total": 40,
    }


async def test_job_failure_is_captured_as_an_error_event() -> None:
    class ExplodingCatalog(FakeIndexCatalog):
        async def execute(self, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("CUDA out of memory")

    container = make_container(index_catalog=ExplodingCatalog())
    manager = make_manager(container)
    stream = manager.stream(FakeRequest())
    await stream.__anext__()  # initial state

    await manager.start("index", {"limit": 1})
    events = [parse_frame(frame) async for frame in stream]
    events = [event for event in events if event is not None]

    assert events[-1]["type"] == "error"
    assert events[-1]["message"] == "CUDA out of memory"
    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "error"
    assert snapshot["error"] == "CUDA out of memory"


async def test_missing_container_is_reported_not_crashed() -> None:
    manager = JobManager(lambda: None)
    await manager.start("index", {})
    await manager.wait()

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "error"
    assert "not ready" in (snapshot["error"] or "")


async def test_wait_is_safe_when_no_job_ran() -> None:
    manager = make_manager(make_container())
    await asyncio.wait_for(manager.wait(), timeout=1)
    assert manager.snapshot() is None


async def test_seed_itunes_job_streams_progress_and_finishes() -> None:
    container = make_container()
    manager = make_manager(container)
    stream = manager.stream(FakeRequest())
    await stream.__anext__()  # initial state

    await manager.start(
        "seed-itunes",
        {"terms": ["hypnotic techno", "Drumcode"], "tracks_per_term": 50},
    )
    events = []
    async for frame in stream:
        event = parse_frame(frame)
        if event is not None:
            events.append(event)

    assert [event["type"] for event in events][-1] == "done"
    progress = [event for event in events if event["type"] == "progress"]
    assert len(progress) == 2
    assert progress[0]["job"]["stage"] == "crawling iTunes keywords"
    assert progress[0]["job"]["total"] == 2
    assert progress[0]["job"]["processed"] == 0
    assert "hypnotic techno" in progress[0]["job"]["message"]
    assert progress[1]["job"]["processed"] == 1
    assert "Drumcode" in progress[1]["job"]["message"]

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "done"
    assert snapshot["result"] == {
        "terms_processed": 2,
        "terms_failed": 0,
        "tracks_found": 20,
        "tracks_saved": 16,
        "artists_discovered": 8,
    }


async def test_import_local_job_streams_progress_and_finishes() -> None:
    container = make_container()
    manager = make_manager(container)
    stream = manager.stream(FakeRequest())
    await stream.__anext__()  # initial state

    await manager.start(
        "import-local",
        {
            "folder_path": "C:\\Music\\Techno",
            "recursive": True,
            "seed_artists": True,
            "batch_size": 16,
            "reindex": False,
        },
    )
    events = []
    async for frame in stream:
        event = parse_frame(frame)
        if event is not None:
            events.append(event)

    assert [event["type"] for event in events][-1] == "done"
    progress = [event for event in events if event["type"] == "progress"]
    assert progress
    p = progress[0]
    assert p["job"]["stage"] == "indexing"
    assert p["job"]["processed"] == 8
    assert p["job"]["total"] == 10
    assert "speed" in p

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "done"
    assert snapshot["result"] == {
        "scanned": 10,
        "imported": 8,
        "embedded": 8,
        "failed": 0,
        "artists_seeded": 5,
    }


async def test_seed_crawl_with_local_seeds() -> None:
    container = make_container()
    manager = make_manager(container)

    await manager.start(
        "seed-crawl",
        {
            "electronic_limit": 500,
            "general_limit": 100,
            "max_depth": 1,
            "use_local_seeds": True,
        },
    )
    await manager.wait()

    assert len(container.build_seed_list.calls) == 1
    call = container.build_seed_list.calls[0]
    assert call["use_local_seeds"] is True
    assert call["electronic_limit"] == 500
    assert call["general_limit"] == 100


async def test_fetch_artist_job_validates_and_executes() -> None:
    container = make_container()
    manager = make_manager(container)

    with pytest.raises(JobParamError, match="artist must be a non-empty string"):
        await manager.start("fetch-artist", {"artist": "  "})

    await manager.start(
        "fetch-artist",
        {
            "artist": "Enrico Sangiuliano",
            "tracks_per_artist": 40,
            "auto_index": True,
            "discover_related": True,
            "related_limit": 5,
        },
    )
    await manager.wait()

    snapshot = manager.snapshot()
    assert snapshot is not None
    assert snapshot["status"] == "done"
    assert snapshot["result"] == {
        "artists_processed": 1,
        "tracks_found": 10,
        "tracks_saved": 8,
        "tracks_indexed": 8,
        "related_seeds_found": 5,
    }
    assert len(container.fetch_artist_tracks.calls) == 1
    call = container.fetch_artist_tracks.calls[0]
    assert call["artist_name"] == "Enrico Sangiuliano"
    assert call["tracks_limit"] == 40
    assert call["auto_index"] is True
    assert call["discover_related"] is True
    assert call["related_limit"] == 5
