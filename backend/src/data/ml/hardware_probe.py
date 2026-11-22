"""Local hardware probe: torch/CUDA/VRAM/RAM/ffmpeg, via stdlib only where possible.

The result is a domain :class:`HardwareInfo`; probing itself imports torch
lazily and shells out to ``ffmpeg -version`` once (cached).
"""

from __future__ import annotations

import ctypes
import logging
import shutil
import subprocess
import sys
from typing import Any

from domain.interfaces.hardware import IHardwareProbe
from domain.value_objects.hardware import HardwareInfo

LOGGER = logging.getLogger(__name__)


class HardwareProbe(IHardwareProbe):
    """Answers "can this machine run the GPU pipeline?" for the CLI."""

    def __init__(self, *, ffmpeg_bin: str = "ffmpeg") -> None:
        self._ffmpeg_bin = ffmpeg_bin
        self._ffmpeg_version: str | None | Exception = None

    def probe(self) -> HardwareInfo:
        torch_version, cuda_available, cuda_version, gpu_name, vram = (
            self._probe_torch()
        )
        ram_total, ram_free = _system_memory_mb()
        ffmpeg_path, ffmpeg_version = self._probe_ffmpeg()
        return HardwareInfo(
            torch_version=torch_version,
            cuda_available=cuda_available,
            cuda_version=cuda_version,
            gpu_name=gpu_name,
            vram_total_mb=vram[0] if vram else None,
            vram_free_mb=vram[1] if vram else None,
            ram_total_mb=ram_total,
            ram_free_mb=ram_free,
            ffmpeg_path=ffmpeg_path,
            ffmpeg_version=ffmpeg_version,
        )

    def _probe_torch(
        self,
    ) -> tuple[str | None, bool, str | None, str | None, tuple[int, int] | None]:
        try:
            import torch
        except Exception:
            LOGGER.debug("torch is not importable", exc_info=True)
            return None, False, None, None, None
        try:
            cuda_available = bool(torch.cuda.is_available())
            cuda_version = (
                str(getattr(torch.version, "cuda", None)) if cuda_available else None
            )
            gpu_name = torch.cuda.get_device_name(0) if cuda_available else None
            vram: tuple[int, int] | None = None
            if cuda_available:
                free, total = torch.cuda.mem_get_info(0)
                vram = (int(total) // (1024 * 1024), int(free) // (1024 * 1024))
            return str(torch.__version__), cuda_available, cuda_version, gpu_name, vram
        except Exception:
            LOGGER.warning("CUDA probe failed", exc_info=True)
            return str(torch.__version__), False, None, None, None

    def _probe_ffmpeg(self) -> tuple[str | None, str | None]:
        path = shutil.which(self._ffmpeg_bin)
        if path is None:
            return None, None
        if isinstance(self._ffmpeg_version, Exception):
            return path, None
        if self._ffmpeg_version is None:
            try:
                completed = subprocess.run(
                    [path, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )
                first_line = completed.stdout.splitlines()
                self._ffmpeg_version = first_line[0].strip() if first_line else ""
            except Exception as exc:
                LOGGER.debug("ffmpeg -version failed", exc_info=True)
                self._ffmpeg_version = exc
                return path, None
        return path, str(self._ffmpeg_version) or None


def _system_memory_mb() -> tuple[int | None, int | None]:
    """Return ``(total_mb, available_mb)`` using stdlib only, or ``(None, None)``."""
    if sys.platform == "win32":

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            kernel32: Any = ctypes.windll.kernel32  # type: ignore[attr-defined]
            if kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                total = int(status.ullTotalPhys) // (1024 * 1024)
                free = int(status.ullAvailPhys) // (1024 * 1024)
                return total, free
        except Exception:
            LOGGER.debug("GlobalMemoryStatusEx failed", exc_info=True)
        return None, None
    if sys.platform == "linux":
        try:
            info: dict[str, int] = {}
            with open("/proc/meminfo", encoding="ascii") as handle:
                for line in handle:
                    key, _, value = line.partition(":")
                    parts = value.split()
                    if parts:
                        info[key.strip()] = int(parts[0])
            if "MemTotal" in info:
                free = info.get("MemAvailable", info.get("MemFree"))
                return info["MemTotal"] // 1024, (free or 0) // 1024
        except Exception:
            LOGGER.debug("Reading /proc/meminfo failed", exc_info=True)
        return None, None
    return None, None


__all__ = ["HardwareProbe"]
