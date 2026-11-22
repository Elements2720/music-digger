"""Application use cases.

Use cases orchestrate domain entities and interfaces. They contain no I/O and
import only the Python standard library plus the domain layer.
"""

from .analyze_dj_set import AnalyzeDJSet, AnalyzeEvent
from .build_seed_list import BuildSeedList, BuildSeedListResult, CrawlProgress
from .crawl_itunes_seeds import (
    DEFAULT_TECHNO_TERMS,
    CrawlITunesResult,
    CrawlITunesSeeds,
)
from .dig_similar_tracks import (
    DigLookupError,
    DigResult,
    DigSimilarTracks,
    TrackNotEmbeddedError,
    TrackNotFoundError,
)
from .fetch_catalog_metadata import FetchCatalogMetadata, FetchMetadataResult
from .find_similar_for_set import (
    FindSimilarForSet,
    SetDigError,
    SetDigResult,
    SetNotEmbeddedError,
    SetNotFoundError,
)
from .import_local_library import (
    ImportLocalLibrary,
    ImportLocalProgress,
    ImportLocalResult,
)
from .index_catalog import IndexCatalog, IndexProgress, IndexResult
from .vibe_search import VibeSearch

__all__ = [
    "DEFAULT_TECHNO_TERMS",
    "AnalyzeDJSet",
    "AnalyzeEvent",
    "BuildSeedList",
    "BuildSeedListResult",
    "CrawlITunesResult",
    "CrawlITunesSeeds",
    "CrawlProgress",
    "DigLookupError",
    "DigResult",
    "DigSimilarTracks",
    "FetchCatalogMetadata",
    "FetchMetadataResult",
    "FindSimilarForSet",
    "ImportLocalLibrary",
    "ImportLocalProgress",
    "ImportLocalResult",
    "IndexCatalog",
    "IndexProgress",
    "IndexResult",
    "SetDigError",
    "SetDigResult",
    "SetNotEmbeddedError",
    "SetNotFoundError",
    "TrackNotEmbeddedError",
    "TrackNotFoundError",
    "VibeSearch",
]
