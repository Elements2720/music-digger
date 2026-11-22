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
    ILikedArtistRepository,
    IPlannedSetRepository,
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
    "ILikedArtistRepository",
    "ILocalLibraryScanner",
    "IPlannedSetRepository",
    "ISeedCrawler",
    "ISeedDiscovery",
    "ISeedRepository",
    "ISetDownloader",
    "ISetRepository",
    "ITrackRepository",
]
