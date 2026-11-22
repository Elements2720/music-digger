"""Unit tests for LocalLibraryScanner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from data.datasources.local.local_library_scanner import (
    LocalLibraryScanner,
)


def _make_probe_output(
    duration: float = 360.0,
    *,
    artist: str | None = "Tale Of Us",
    title: str | None = "Astral",
    album: str | None = "Afterlife",
    genre: str | None = "Melodic Techno",
    date: str | None = "2021-04-16",
) -> str:
    tags: dict[str, Any] = {}
    if artist:
        tags["artist"] = artist
    if title:
        tags["title"] = title
    if album:
        tags["album"] = album
    if genre:
        tags["genre"] = genre
    if date:
        tags["date"] = date

    return json.dumps(
        {
            "format": {
                "duration": str(duration),
                "tags": tags,
            }
        }
    )


@pytest.mark.asyncio
async def test_scan_finds_supported_extensions_and_parses_tags(tmp_path: Path) -> None:
    track1 = tmp_path / "track1.mp3"
    track1.write_bytes(b"dummy")
    track2 = tmp_path / "track2.flac"
    track2.write_bytes(b"dummy")
    ignored = tmp_path / "notes.txt"
    ignored.write_bytes(b"text")

    def fake_ffprobe(args: list[str]) -> str:
        filepath = args[-1]
        if "track1.mp3" in filepath:
            return _make_probe_output(
                duration=320.0,
                artist="Solomun",
                title="Customer Is King",
                album="Diynamic",
                genre="Deep House",
                date="2018",
            )
        return _make_probe_output(
            duration=400.0,
            artist="Stephan Bodzin",
            title="Singularity",
            date="2015-11-20",
        )

    scanner = LocalLibraryScanner(ffprobe_runner=fake_ffprobe)
    tracks = await scanner.scan(tmp_path, recursive=False)

    assert len(tracks) == 2
    t1 = next(t for t in tracks if t.artist == "Solomun")
    assert t1.title == "Customer Is King"
    assert t1.album == "Diynamic"
    assert t1.genre == "Deep House"
    assert t1.release_year == 2018
    assert t1.duration_seconds == 320.0
    assert t1.source == "local"
    assert t1.id.startswith("local:")
    assert len(t1.id) == 18  # "local:" + 12 chars
    assert t1.local_path == str(track1.resolve())

    t2 = next(t for t in tracks if t.artist == "Stephan Bodzin")
    assert t2.title == "Singularity"
    assert t2.release_year == 2015
    assert t2.duration_seconds == 400.0


@pytest.mark.asyncio
async def test_scan_filename_fallback_when_tags_empty(tmp_path: Path) -> None:
    f1 = tmp_path / "Enrico Sangiuliano - Moon Rocks.mp3"
    f1.write_bytes(b"dummy")
    f2 = tmp_path / "01 - ARTBAT - Horizon.wav"
    f2.write_bytes(b"dummy")
    f3 = tmp_path / "SingleTitleOnly.aiff"
    f3.write_bytes(b"dummy")

    def empty_tags_ffprobe(args: list[str]) -> str:
        return json.dumps({"format": {"duration": "300.0", "tags": {}}})

    scanner = LocalLibraryScanner(ffprobe_runner=empty_tags_ffprobe)
    tracks = await scanner.scan(tmp_path, recursive=False)

    assert len(tracks) == 3
    by_path = {t.local_path: t for t in tracks}

    assert by_path[str(f1.resolve())].artist == "Enrico Sangiuliano"
    assert by_path[str(f1.resolve())].title == "Moon Rocks"

    assert by_path[str(f2.resolve())].artist == "ARTBAT"
    assert by_path[str(f2.resolve())].title == "Horizon"

    assert by_path[str(f3.resolve())].artist == "Unknown Artist"
    assert by_path[str(f3.resolve())].title == "SingleTitleOnly"


@pytest.mark.asyncio
async def test_scan_filters_duration_and_skips_short_or_long(tmp_path: Path) -> None:
    short_file = tmp_path / "short.mp3"
    short_file.write_bytes(b"dummy")
    valid_file = tmp_path / "valid.mp3"
    valid_file.write_bytes(b"dummy")
    dj_set_file = tmp_path / "full_dj_set.mp3"
    dj_set_file.write_bytes(b"dummy")

    def duration_ffprobe(args: list[str]) -> str:
        path = args[-1]
        if "short.mp3" in path:
            return _make_probe_output(duration=45.0)  # < 60s
        if "full_dj_set.mp3" in path:
            return _make_probe_output(duration=7200.0)  # > 900s
        return _make_probe_output(duration=360.0)

    scanner = LocalLibraryScanner(ffprobe_runner=duration_ffprobe)
    tracks = await scanner.scan(
        tmp_path,
        min_duration_seconds=60.0,
        max_duration_seconds=900.0,
    )

    assert len(tracks) == 1
    assert tracks[0].local_path == str(valid_file.resolve())


@pytest.mark.asyncio
async def test_scan_skips_corrupted_file_cleanly(tmp_path: Path) -> None:
    good = tmp_path / "good.mp3"
    good.write_bytes(b"dummy")
    corrupt = tmp_path / "corrupt.mp3"
    corrupt.write_bytes(b"corrupt")

    def throwing_ffprobe(args: list[str]) -> str:
        if "corrupt.mp3" in args[-1]:
            raise RuntimeError("Corrupt bitstream")
        return _make_probe_output(duration=180.0)

    scanner = LocalLibraryScanner(ffprobe_runner=throwing_ffprobe)
    tracks = await scanner.scan(tmp_path)

    assert len(tracks) == 1
    assert tracks[0].local_path == str(good.resolve())


@pytest.mark.asyncio
async def test_scan_recursive_subfolders(tmp_path: Path) -> None:
    sub = tmp_path / "Melodic Techno" / "2024"
    sub.mkdir(parents=True)
    track = sub / "track.mp3"
    track.write_bytes(b"dummy")

    def dummy_ffprobe(args: list[str]) -> str:
        return _make_probe_output(duration=240.0)

    scanner = LocalLibraryScanner(ffprobe_runner=dummy_ffprobe)
    non_rec = await scanner.scan(tmp_path, recursive=False)
    assert len(non_rec) == 0

    rec = await scanner.scan(tmp_path, recursive=True)
    assert len(rec) == 1
    assert rec[0].local_path == str(track.resolve())


@pytest.mark.asyncio
async def test_scan_nonexistent_directory_raises(tmp_path: Path) -> None:
    scanner = LocalLibraryScanner(ffprobe_runner=lambda _: "")
    with pytest.raises(FileNotFoundError):
        await scanner.scan(tmp_path / "nonexistent")
