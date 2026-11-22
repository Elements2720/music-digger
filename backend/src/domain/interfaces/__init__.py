"""Abstract ports implemented by the data layer."""

from .audio_engine import (
    IAudioDecoder,
    IAudioEmbedder,
    IAudioSegmenter,
    IFeatureExtractor,
    IFingerprinter,
    ISetDownloader,
)
from .catalog import ICatalogProvider, ISeedCrawler, ISeedDiscovery
from .hardware import IHardwareProbe
from .llm import ILLMService
from .local_library import ILocalLibraryScanner
from .repositories import (
    IBlacklistRepository,
    ISeedRepository,
    ISetRepository,
    ITrackRepository,
)

__all__ = [
    "IAudioDecoder",
    "IAudioEmbedder",
    "IAudioSegmenter",
    "IBlacklistRepository",
    "ICatalogProvider",
    "IFeatureExtractor",
    "IFingerprinter",
    "IHardwareProbe",
    "ILLMService",
    "ILocalLibraryScanner",
    "ISeedCrawler",
    "ISeedDiscovery",
    "ISeedRepository",
    "ISetDownloader",
    "ISetRepository",
    "ITrackRepository",
]
