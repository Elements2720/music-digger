"""Application configuration settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DownloaderSettings:
    """Settings specific to track downloads."""

    download_dir: str = "storage/downloads"
    amdl_base_url: str = "https://am-dl.pages.dev"
    amdl_timeout_seconds: int = 60
    playwright_storage_dir: str = "storage/playwright_amdl"
    playwright_idle_timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> DownloaderSettings:
        return cls(
            download_dir=os.getenv("DOWNLOAD_DIR", "storage/downloads"),
            amdl_base_url=os.getenv("AMDL_BASE_URL", "https://am-dl.pages.dev"),
            amdl_timeout_seconds=int(os.getenv("AMDL_TIMEOUT_SECONDS", "60")),
            playwright_storage_dir=os.getenv(
                "PLAYWRIGHT_STORAGE_DIR", "storage/playwright_amdl"
            ),
            playwright_idle_timeout_seconds=float(
                os.getenv("PLAYWRIGHT_IDLE_TIMEOUT_SECONDS", "120.0")
            ),
        )
