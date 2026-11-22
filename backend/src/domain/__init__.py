"""Pure domain layer for DigDeeper Local.

This package must import only the Python standard library. See AGENTS.md for
the dependency rule enforced by ``tests/domain/test_domain_purity.py``.
"""

from .entities import (
    SEED_CATEGORIES,
    SEED_STATUSES,
    AudioBuffer,
    DJSet,
    Passage,
    SearchFilter,
    SeedArtist,
    SeedCategory,
    SeedStatus,
    Track,
    TrackMatch,
    TrackReference,
    TrackVibe,
)
from .interfaces import (
    IAudioDecoder,
    IAudioEmbedder,
    IAudioSegmenter,
    ICatalogProvider,
    IFeatureExtractor,
    IFingerprinter,
    ILLMService,
    ISeedCrawler,
    ISeedDiscovery,
    ISeedRepository,
    ISetDownloader,
    ISetRepository,
    ITrackRepository,
)
from .value_objects import (
    BPM,
    AudioFeatures,
    CamelotKey,
    EmbeddingVector,
    TimeRange,
)

__all__ = [
    "BPM",
    "SEED_CATEGORIES",
    "SEED_STATUSES",
    "AudioBuffer",
    "AudioFeatures",
    "CamelotKey",
    "DJSet",
    "EmbeddingVector",
    "IAudioDecoder",
    "IAudioEmbedder",
    "IAudioSegmenter",
    "ICatalogProvider",
    "IFeatureExtractor",
    "IFingerprinter",
    "ILLMService",
    "ISeedCrawler",
    "ISeedDiscovery",
    "ISeedRepository",
    "ISetDownloader",
    "ISetRepository",
    "ITrackRepository",
    "Passage",
    "SearchFilter",
    "SeedArtist",
    "SeedCategory",
    "SeedStatus",
    "TimeRange",
    "Track",
    "TrackMatch",
    "TrackReference",
    "TrackVibe",
]
