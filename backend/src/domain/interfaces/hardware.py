"""Hardware probing port.

Implementations live in ``data/ml`` and may import torch or spawn helper
processes. The domain only sees the resulting :class:`HardwareInfo` snapshot.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.hardware import HardwareInfo


class IHardwareProbe(ABC):
    """Reports the local compute environment (GPU, RAM, ffmpeg, torch)."""

    @abstractmethod
    def probe(self) -> HardwareInfo:
        """Return a fresh snapshot of the machine's compute capabilities."""
