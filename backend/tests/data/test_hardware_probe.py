"""Tests for the local hardware probe (no GPU required)."""

from __future__ import annotations

from data.ml.hardware_probe import HardwareProbe
from domain.value_objects.hardware import HardwareInfo


def test_probe_returns_a_coherent_snapshot() -> None:
    info = HardwareProbe(ffmpeg_bin="definitely-not-a-real-binary").probe()

    assert isinstance(info, HardwareInfo)
    # torch is installed in this environment (CPU fallback in CI).
    assert info.torch_version is not None
    if not info.cuda_available:
        assert info.gpu_name is None
        assert info.vram_summary() == "n/a"
    assert info.ffmpeg_path is None  # bogus binary name must not be found
    assert not info.has_ffmpeg


def test_probe_reports_ram_when_the_os_supports_it() -> None:
    info = HardwareProbe().probe()

    if info.ram_total_mb is not None:
        assert info.ram_total_mb > 0
        if info.ram_free_mb is not None:
            assert info.ram_free_mb <= info.ram_total_mb
        assert info.ram_summary().endswith("MB free")


def test_missing_ffmpeg_is_reported_clearly() -> None:
    info = HardwareProbe(ffmpeg_bin="no-such-ffmpeg").probe()

    assert info.ffmpeg_path is None
    assert info.ffmpeg_version is None
    assert not info.has_ffmpeg


def test_hardware_info_defaults_are_advisory() -> None:
    info = HardwareInfo()

    assert info.torch_version is None
    assert not info.cuda_available
    assert not info.gpu_ready
    assert info.ram_summary() == "unknown"
