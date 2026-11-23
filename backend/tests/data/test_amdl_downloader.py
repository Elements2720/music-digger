"""Unit tests for the AmdlHttpTrackDownloader adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from data.datasources.remote.amdl_http_downloader import (
    AmdlHttpTrackDownloader,
    sanitize_filename,
)
from domain.entities.track import Track
from domain.value_objects.audio_features import BPM, CamelotKey, EmbeddingVector


def _make_track(
    track_id: str = "itunes:123",
    title: str = "Deep Space",
    artist: str = "DJ Alpha",
    duration_seconds: float | None = 384.0,
    store_url: str | None = "https://music.apple.com/us/album/test/1?i=123",
    bpm: float | None = 126.0,
    key: str | None = "8A",
    preview_url: str | None = "https://preview.test/1.m4a",
) -> Track:
    return Track(
        id=track_id,
        title=title,
        artist=artist,
        duration_seconds=duration_seconds,
        bpm=BPM(bpm) if bpm else None,
        key=CamelotKey(key) if key else None,
        genre="Techno",
        preview_url=preview_url,
        artwork_url="https://art.test/1.jpg",
        store_url=store_url,
        embedding=EmbeddingVector(values=(1.0, 0.0), dimension=2),
    )


def test_sanitize_filename() -> None:
    assert (
        sanitize_filename('AC/DC: "Back in Black" *test?*')
        == "AC_DC_ _Back in Black_ _test__"
    )
    assert sanitize_filename("   ...   ") == "unnamed"
    assert (
        sanitize_filename("Clean Artist - Clean Title") == "Clean Artist - Clean Title"
    )


def test_build_target_url_variants() -> None:
    downloader = AmdlHttpTrackDownloader()

    # Direct Apple Music store URL preserved
    t1 = _make_track(
        store_url="https://music.apple.com/us/album/test/999?i=123456&uo=4"
    )
    assert (
        downloader._build_target_url(t1)
        == "https://music.apple.com/us/album/test/999?i=123456&uo=4"
    )

    # Direct song URL
    t2 = _make_track(store_url="https://music.apple.com/us/song/deep-space/654321")
    assert (
        downloader._build_target_url(t2)
        == "https://music.apple.com/us/song/deep-space/654321"
    )

    # External ID fallback
    t3 = Track(
        id="itunes:777888",
        title="T",
        artist="A",
        preview_url="https://preview.test/1.m4a",
        external_id="777888",
    )
    assert downloader._build_target_url(t3) == "https://music.apple.com/us/song/777888"

    # Missing both raises ValueError
    t4 = Track(
        id="missing", title="T", artist="A", preview_url="https://preview.test/1.m4a"
    )
    with pytest.raises(ValueError, match="no usable store_url or iTunes track ID"):
        downloader._build_target_url(t4)


@pytest.mark.asyncio
async def test_download_track_success_with_faststart_and_metadata(
    tmp_path: Path,
) -> None:
    downloader = AmdlHttpTrackDownloader(
        playwright_storage_dir=tmp_path / "pw_storage",
    )
    track = _make_track(bpm=128.5, key="7B", duration_seconds=384.0)

    # Mock _download_via_browser to simulate writing a temporary downloaded file
    async def fake_browser_download(url: str, output_path: Path) -> None:
        output_path.write_bytes(b"FAKE_RAW_M4A_BYTES")

    downloader._download_via_browser = fake_browser_download  # type: ignore[assignment]

    commands_executed = []

    # Mock subprocess for ffmpeg post-processing and ffprobe verification
    async def fake_create_subprocess_exec(*args, **kwargs):
        commands_executed.append(args)
        proc = AsyncMock()
        proc.returncode = 0
        if args[0] == downloader._ffprobe_binary:
            proc.communicate.return_value = (b"384.05\n", b"")
        elif args[0] == downloader._ffmpeg_binary:
            # If creating dest_file, write dummy content
            dest = args[-1]
            if dest.endswith(".m4a"):
                Path(dest).write_bytes(b"FAKE_OUTPUT_M4A")
            proc.communicate.return_value = (b"", b"")
        return proc

    with patch(
        "asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec
    ):
        res = await downloader.download_track(track, str(tmp_path))

    assert res.track_id == track.id
    assert res.file_path.endswith("DJ Alpha - Deep Space.m4a")
    assert res.format == "m4a"

    # Verify ffmpeg remux call
    remux_cmd = next(
        cmd
        for cmd in commands_executed
        if cmd[0] == downloader._ffmpeg_binary and "-movflags" in cmd
    )
    assert "-movflags" in remux_cmd
    assert "+faststart" in remux_cmd
    assert "-c" in remux_cmd
    assert "copy" in remux_cmd
    assert "BPM=128.5" in remux_cmd
    assert "initialKey=7B" in remux_cmd


@pytest.mark.asyncio
async def test_duration_sanity_guard_rejects_preview_clip(tmp_path: Path) -> None:
    downloader = AmdlHttpTrackDownloader(
        playwright_storage_dir=tmp_path / "pw_storage",
    )
    # Track is 384 seconds in catalog
    track = _make_track(duration_seconds=384.0)

    async def fake_browser_download(url: str, output_path: Path) -> None:
        output_path.write_bytes(b"FAKE_RAW_M4A")

    downloader._download_via_browser = fake_browser_download  # type: ignore[assignment]

    # Mock ffprobe returning only 90.0 seconds (preview clip!)
    async def fake_create_subprocess_exec(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        if args[0] == downloader._ffprobe_binary:
            proc.communicate.return_value = (b"90.0\n", b"")
        elif args[0] == downloader._ffmpeg_binary:
            dest = args[-1]
            if dest.endswith(".m4a"):
                Path(dest).write_bytes(b"FAKE_PREVIEW_M4A")
            proc.communicate.return_value = (b"", b"")
        return proc

    with (
        patch(
            "asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec
        ),
        pytest.raises(RuntimeError, match="less than 65% of catalog track duration"),
    ):
        await downloader.download_track(track, str(tmp_path))

    # Output file must be cleaned up / not left on disk
    dest_file = tmp_path / "DJ Alpha - Deep Space.m4a"
    assert not dest_file.exists()


@pytest.mark.asyncio
async def test_verify_audio_file_decode_failure_cleans_up(tmp_path: Path) -> None:
    downloader = AmdlHttpTrackDownloader()
    track = _make_track()
    dummy_file = tmp_path / "corrupt.m4a"
    dummy_file.write_bytes(b"corrupt data")

    # ffprobe succeeds, but ffmpeg decode check fails
    async def fake_create_subprocess_exec(*args, **kwargs):
        proc = AsyncMock()
        if args[0] == downloader._ffprobe_binary:
            proc.returncode = 0
            proc.communicate.return_value = (b"384.0\n", b"")
        else:
            proc.returncode = 1
            proc.communicate.return_value = (b"", b"Invalid data found in stream")
        return proc

    with (
        patch(
            "asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec
        ),
        pytest.raises(RuntimeError, match="failed decode check"),
    ):
        await downloader._verify_audio_file(dummy_file, track)

    assert not dummy_file.exists()


@pytest.mark.asyncio
async def test_playwright_idle_shutdown_and_close(tmp_path: Path) -> None:
    downloader = AmdlHttpTrackDownloader(
        playwright_idle_timeout=0.05,
        playwright_storage_dir=tmp_path / "pw_storage",
    )
    mock_context = AsyncMock()
    mock_playwright = AsyncMock()

    downloader._context = mock_context
    downloader._playwright = mock_playwright

    downloader._schedule_idle_shutdown()
    assert downloader._idle_task is not None

    # Wait for idle timeout
    await asyncio.sleep(0.1)

    # After idle shutdown, context is closed and references reset
    assert downloader._context is None
    assert downloader._playwright is None
    mock_context.close.assert_awaited_once()
    mock_playwright.stop.assert_awaited_once()
