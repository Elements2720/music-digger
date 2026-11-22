"""Tests for the yt-dlp set downloader (fake yt-dlp + fake ffprobe)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Self

import pytest

from data.datasources.remote.ytdlp_downloader import YtDlpSetDownloader
from data.errors import SetDownloadError


def _downloader(
    tmp_path: Path,
    *,
    ydl_factory: Any = None,
    ffprobe_runner: Any = None,
    max_comments: int = 100,
    cookies_file: Path | None = None,
    cookies_from_browser: str | None = None,
) -> YtDlpSetDownloader:
    return YtDlpSetDownloader(
        cache_dir=tmp_path / "cache",
        ydl_factory=ydl_factory,
        ffprobe_runner=ffprobe_runner or (lambda args: "0"),
        max_comments=max_comments,
        cookies_file=cookies_file,
        cookies_from_browser=cookies_from_browser,
    )


def _fake_ffprobe(duration: float) -> Any:
    return lambda args: f"{duration}\n"


async def test_local_file_passes_through_without_copying(tmp_path) -> None:
    audio = tmp_path / "boiler-room-set.mp3"
    audio.write_bytes(b"not really an mp3")
    downloader = _downloader(tmp_path, ffprobe_runner=_fake_ffprobe(3721.5))

    result = await downloader.fetch_set(str(audio), tmp_path / "cache")

    assert result.audio_path == audio.resolve()
    assert result.is_temporary is False
    assert result.title == "boiler-room-set"
    assert result.duration_seconds == pytest.approx(3721.5)
    assert result.source_url is None
    assert result.comments == ()


async def test_local_file_without_duration_probe_still_works(tmp_path) -> None:
    audio = tmp_path / "set.flac"
    audio.write_bytes(b"x")
    downloader = _downloader(tmp_path, ffprobe_runner=lambda args: "not-a-number")

    result = await downloader.fetch_set(str(audio), tmp_path / "cache")

    assert result.duration_seconds is None
    assert result.is_temporary is False


def _fake_ydl(info: dict[str, Any] | Exception, create_file: Path | None = None):
    created = {"file": create_file}

    class FakeYDL:
        def __init__(self, options: dict[str, Any]) -> None:
            self.options = options

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def extract_info(self, source: str, download: bool) -> dict[str, Any]:
            assert download is True
            if isinstance(info, Exception):
                raise info
            if created["file"] is not None:
                created["file"].parent.mkdir(parents=True, exist_ok=True)
                created["file"].write_bytes(b"audio")
            return dict(info)

        def prepare_filename(self, info: dict[str, Any]) -> str:
            return str(created["file"])

    return FakeYDL


async def test_remote_download_returns_temporary_set(tmp_path) -> None:
    job_id = hashlib.sha256(b"https://sound.test/set").hexdigest()[:16]
    target = tmp_path / "cache" / f"{job_id}.m4a"
    ydl_factory = _fake_ydl(
        {
            "title": "Peak Time Set",
            "uploader": "Test DJ",
            "duration": 3600,
            "webpage_url": "https://sound.test/set",
            "thumbnail": "https://img.test/thumb.jpg",
            "description": "tracklist in comments",
            "comments": [
                {"text": "33:00 Great Track", "like_count": 5},
                {"text": "top set!", "like_count": 100},
                {"text": "12:00 Another Track", "like_count": 50},
            ],
        },
        create_file=target,
    )
    downloader = _downloader(tmp_path, ydl_factory=ydl_factory)

    result = await downloader.fetch_set("https://sound.test/set", tmp_path / "cache")

    assert result.is_temporary is True
    assert result.title == "Peak Time Set"
    assert result.artist == "Test DJ"
    assert result.duration_seconds == pytest.approx(3600.0)
    assert result.source_url == "https://sound.test/set"
    assert result.thumbnail_url == "https://img.test/thumb.jpg"
    # Comments are ordered by likes, descending.
    assert result.comments == ("top set!", "12:00 Another Track", "33:00 Great Track")


async def test_max_comments_caps_the_comment_list(tmp_path) -> None:
    job_id = hashlib.sha256(b"https://sound.test/set").hexdigest()[:16]
    target = tmp_path / "cache" / f"{job_id}.m4a"
    comments = [{"text": f"comment {i}", "like_count": i} for i in range(10)]
    ydl_factory = _fake_ydl(
        {"title": "Set", "duration": 60, "comments": comments},
        create_file=target,
    )
    downloader = _downloader(tmp_path, ydl_factory=ydl_factory, max_comments=2)

    result = await downloader.fetch_set("https://sound.test/set", tmp_path / "cache")

    assert result.comments == ("comment 9", "comment 8")


async def test_download_failure_wraps_in_set_download_error(tmp_path) -> None:
    ydl_factory = _fake_ydl(RuntimeError("network down"))
    downloader = _downloader(tmp_path, ydl_factory=ydl_factory)

    with pytest.raises(SetDownloadError, match="network down"):
        await downloader.fetch_set("https://sound.test/set", tmp_path / "cache")


async def test_yt_dlp_success_without_file_raises(tmp_path) -> None:
    ydl_factory = _fake_ydl({"title": "Ghost Set", "duration": 60}, create_file=None)
    downloader = _downloader(tmp_path, ydl_factory=ydl_factory)

    with pytest.raises(SetDownloadError, match="no file exists"):
        await downloader.fetch_set("https://sound.test/set", tmp_path / "cache")


async def test_unknown_source_neither_file_nor_url_raises(tmp_path) -> None:
    downloader = _downloader(tmp_path)
    with pytest.raises(SetDownloadError, match="neither an existing audio file"):
        await downloader.fetch_set("not-a-url", tmp_path / "cache")


async def test_unsupported_suffix_that_is_missing_raises(tmp_path) -> None:
    downloader = _downloader(tmp_path)
    with pytest.raises(SetDownloadError, match="neither an existing audio file"):
        await downloader.fetch_set(str(tmp_path / "missing.mp3"), tmp_path / "cache")


async def test_legacy_download_seam_returns_the_audio_path(tmp_path) -> None:
    audio = tmp_path / "local" / "set.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"x")
    downloader = _downloader(tmp_path, ffprobe_runner=_fake_ffprobe(12.0))

    path = await downloader.download(str(audio), tmp_path / "elsewhere")

    assert path == audio.resolve()


async def test_comments_getcomments_flag_follows_fetch_comments(tmp_path) -> None:
    job_id = hashlib.sha256(b"https://sound.test/set").hexdigest()[:16]
    target = tmp_path / "cache" / f"{job_id}.m4a"
    captured_options: dict[str, Any] = {}

    class CapturingYDL:
        def __init__(self, options: dict[str, Any]) -> None:
            captured_options.update(options)

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def extract_info(self, source: str, download: bool) -> dict[str, Any]:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"audio")
            return {"title": "Set", "duration": 60}

        def prepare_filename(self, info: dict[str, Any]) -> str:
            return str(target)

    downloader = _downloader(tmp_path, ydl_factory=CapturingYDL)
    await downloader.fetch_set(
        "https://sound.test/set", tmp_path / "cache", fetch_comments=False
    )
    assert captured_options["getcomments"] is False


def test_negative_max_comments_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="max_comments"):
        YtDlpSetDownloader(
            cache_dir=tmp_path,
            ffprobe_runner=lambda args: "0",
            max_comments=-1,
        )


# --------------------------------------------------------------------------
# Cookie authentication (YouTube bot-gate bypass)
# --------------------------------------------------------------------------


def _capturing_ydl_factory(captured: list[dict[str, Any]], exc: Exception) -> Any:
    """Records the options yt-dlp would receive, then always fails."""

    class CapturingYDL:
        def __init__(self, options: dict[str, Any]) -> None:
            captured.append(options)

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def extract_info(self, source: str, download: bool) -> dict[str, Any]:
            raise exc

        def prepare_filename(self, info: dict[str, Any]) -> str:
            return ""

    return CapturingYDL


async def _options_for_doomed_fetch(
    tmp_path: Path, downloader: YtDlpSetDownloader
) -> None:
    """Run a remote fetch that always fails; inspect the shared capture list."""
    with pytest.raises(SetDownloadError, match="boom"):
        await downloader.fetch_set("https://sound.test/set", tmp_path / "cache")


async def test_cookies_file_is_wired_into_options(tmp_path) -> None:
    captured: list[dict[str, Any]] = []
    cookies = tmp_path / "cookies.txt"
    cookies.write_bytes(b"# Netscape HTTP Cookie File\n")
    downloader = _downloader(
        tmp_path,
        cookies_file=cookies,
        ydl_factory=_capturing_ydl_factory(captured, RuntimeError("boom")),
    )

    await _options_for_doomed_fetch(tmp_path, downloader)

    assert captured[0]["cookiefile"] == str(cookies)
    assert "cookiesfrombrowser" not in captured[0]


async def test_cookies_from_browser_is_wired_into_options(tmp_path) -> None:
    captured: list[dict[str, Any]] = []
    downloader = _downloader(
        tmp_path,
        cookies_from_browser="firefox",
        ydl_factory=_capturing_ydl_factory(captured, RuntimeError("boom")),
    )

    await _options_for_doomed_fetch(tmp_path, downloader)

    assert captured[0]["cookiesfrombrowser"] == ("firefox",)
    assert "cookiefile" not in captured[0]


async def test_existing_cookies_file_wins_over_browser(tmp_path) -> None:
    captured: list[dict[str, Any]] = []
    cookies = tmp_path / "cookies.txt"
    cookies.write_bytes(b"# Netscape HTTP Cookie File\n")
    downloader = _downloader(
        tmp_path,
        cookies_file=cookies,
        cookies_from_browser="edge",
        ydl_factory=_capturing_ydl_factory(captured, RuntimeError("boom")),
    )

    await _options_for_doomed_fetch(tmp_path, downloader)

    assert captured[0]["cookiefile"] == str(cookies)
    assert "cookiesfrombrowser" not in captured[0]


async def test_missing_cookies_file_falls_back_to_browser(tmp_path) -> None:
    captured: list[dict[str, Any]] = []
    downloader = _downloader(
        tmp_path,
        cookies_file=tmp_path / "missing.txt",
        cookies_from_browser="brave",
        ydl_factory=_capturing_ydl_factory(captured, RuntimeError("boom")),
    )

    await _options_for_doomed_fetch(tmp_path, downloader)

    assert captured[0]["cookiesfrombrowser"] == ("brave",)
    assert "cookiefile" not in captured[0]


async def test_missing_cookies_file_without_browser_sends_no_cookies(
    tmp_path,
) -> None:
    captured: list[dict[str, Any]] = []
    downloader = _downloader(
        tmp_path,
        cookies_file=tmp_path / "missing.txt",
        ydl_factory=_capturing_ydl_factory(captured, RuntimeError("boom")),
    )

    await _options_for_doomed_fetch(tmp_path, downloader)

    assert "cookiefile" not in captured[0]
    assert "cookiesfrombrowser" not in captured[0]


async def test_no_cookie_configuration_sends_no_cookie_options(tmp_path) -> None:
    captured: list[dict[str, Any]] = []
    downloader = _downloader(
        tmp_path, ydl_factory=_capturing_ydl_factory(captured, RuntimeError("boom"))
    )

    await _options_for_doomed_fetch(tmp_path, downloader)

    assert "cookiefile" not in captured[0]
    assert "cookiesfrombrowser" not in captured[0]


async def test_bot_check_error_surfaces_cookie_hint(tmp_path) -> None:
    downloader = _downloader(
        tmp_path,
        ydl_factory=_capturing_ydl_factory(
            [],
            RuntimeError(
                "ERROR: [youtube] abc: Sign in to confirm you're not a bot. "
                "This helps protect our community."
            ),
        ),
    )

    with pytest.raises(SetDownloadError) as exc_info:
        await downloader.fetch_set("https://youtube.com/watch?v=abc", tmp_path)

    message = str(exc_info.value)
    assert "YTDLP_COOKIES_FILE" in message
    assert "YTDLP_COOKIES_FROM_BROWSER" in message
    assert "--cookies" in message


async def test_other_download_errors_do_not_mention_cookies(tmp_path) -> None:
    downloader = _downloader(
        tmp_path,
        ydl_factory=_capturing_ydl_factory([], RuntimeError("HTTP 404")),
    )

    with pytest.raises(SetDownloadError) as exc_info:
        await downloader.fetch_set("https://sound.test/set", tmp_path / "cache")

    assert "YTDLP_COOKIES_FILE" not in str(exc_info.value)


async def test_apply_cookie_overrides_fill_in_for_cli_flags(tmp_path) -> None:
    cookies = tmp_path / "one-off.txt"
    cookies.write_bytes(b"# Netscape HTTP Cookie File\n")
    captured: list[dict[str, Any]] = []
    downloader = _downloader(
        tmp_path, ydl_factory=_capturing_ydl_factory(captured, RuntimeError("boom"))
    )

    # No flags: nothing configured, no cookie options sent.
    await _options_for_doomed_fetch(tmp_path, downloader)
    assert "cookiefile" not in captured[0]

    # `--cookies-from-browser` only: fills the unset slot.
    downloader.apply_cookie_overrides(cookies_from_browser="chrome")
    await _options_for_doomed_fetch(tmp_path, downloader)
    assert captured[1]["cookiesfrombrowser"] == ("chrome",)

    # `--cookies` only: the file wins over the still-configured browser slot.
    downloader.apply_cookie_overrides(cookies_file=cookies)
    await _options_for_doomed_fetch(tmp_path, downloader)
    assert captured[2]["cookiefile"] == str(cookies)
    assert "cookiesfrombrowser" not in captured[2]
