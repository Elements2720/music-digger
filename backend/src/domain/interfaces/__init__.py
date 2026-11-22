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
from .repositories import ISeedRepository, ISetRepository, ITrackRepository

__all__ = [
    "IAudioDecoder",
    "IAudioEmbedder",
    "IAudioSegmenter",
    "ICatalogProvider",
    "IFeatureExtractor",
    "IFingerprinter",
    "IHardwareProbe",
    "ILLMService",
    "ISeedCrawler",
    "ISeedDiscovery",
    "ISeedRepository",
    "ISetDownloader",
    "ISetRepository",
    "ITrackRepository",
]
