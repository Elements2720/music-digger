"""Pure value object describing the local compute environment.

Probing hardware requires third-party libraries (torch, subprocess); the
*result* is a plain immutable record so the domain and presentation layers can
reason about it without importing ML or OS libraries.
"""

from __future__ import annotations

from dataclasses import dataclass

from .._validation import optional_str, require_bool


@dataclass(frozen=True, slots=True)
class HardwareInfo:
    """A snapshot of compute capabilities relevant to audio analysis.

    ``None`` means "not determinable on this machine" — every consumer must
    treat the fields as advisory, never as hard requirements.
    """

    torch_version: str | None = None
    cuda_available: bool = False
    cuda_version: str | None = None
    gpu_name: str | None = None
    vram_total_mb: int | None = None
    vram_free_mb: int | None = None
    ram_total_mb: int | None = None
    ram_free_mb: int | None = None
    ffmpeg_path: str | None = None
    ffmpeg_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "torch_version", optional_str(self.torch_version, "torch_version")
        )
        object.__setattr__(
            self, "cuda_version", optional_str(self.cuda_version, "cuda_version")
        )
        object.__setattr__(self, "gpu_name", optional_str(self.gpu_name, "gpu_name"))
        object.__setattr__(
            self, "ffmpeg_path", optional_str(self.ffmpeg_path, "ffmpeg_path")
        )
        object.__setattr__(
            self, "ffmpeg_version", optional_str(self.ffmpeg_version, "ffmpeg_version")
        )
        object.__setattr__(
            self, "cuda_available", require_bool(self.cuda_available, "cuda_available")
        )

    @property
    def has_ffmpeg(self) -> bool:
        """True when an ``ffmpeg`` binary was found on this machine."""
        return self.ffmpeg_path is not None

    @property
    def gpu_ready(self) -> bool:
        """True when CUDA inference is available on this machine."""
        return self.cuda_available

    def vram_summary(self) -> str:
        """Human-readable one-line VRAM summary, for CLI tables."""
        if not self.cuda_available:
            return "n/a"
        if self.vram_total_mb is None:
            return "unknown"
        free = "unknown" if self.vram_free_mb is None else f"{self.vram_free_mb}"
        return f"{free}/{self.vram_total_mb} MB free"

    def ram_summary(self) -> str:
        """Human-readable one-line RAM summary, for CLI tables."""
        if self.ram_total_mb is None:
            return "unknown"
        free = "unknown" if self.ram_free_mb is None else f"{self.ram_free_mb}"
        return f"{free}/{self.ram_total_mb} MB free"
