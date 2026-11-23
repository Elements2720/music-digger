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
from .dj_set_helper import DJSetHelper, evaluate_transition
from .fetch_artist_tracks import (
    FetchArtistProgress,
    FetchArtistResult,
    FetchArtistTracks,
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
from .manage_catalog import (
    BulkCleanupCriteria,
    BulkCleanupPreview,
    BulkDeleteArtistsResult,
    DeleteArtistResult,
    DeleteTrackResult,
    ManageCatalog,
)
from .vibe_search import VibeSearch

__all__ = [
    "DEFAULT_TECHNO_TERMS",
    "AnalyzeDJSet",
    "AnalyzeEvent",
    "BuildSeedList",
    "BuildSeedListResult",
    "BulkCleanupCriteria",
    "BulkCleanupPreview",
    "BulkDeleteArtistsResult",
    "CrawlITunesResult",
    "CrawlITunesSeeds",
    "CrawlProgress",
    "DJSetHelper",
    "DeleteArtistResult",
    "DeleteTrackResult",
    "DigLookupError",
    "DigResult",
    "DigSimilarTracks",
    "FetchArtistProgress",
    "FetchArtistResult",
    "FetchArtistTracks",
    "FetchCatalogMetadata",
    "FetchMetadataResult",
    "FindSimilarForSet",
    "ImportLocalLibrary",
    "ImportLocalProgress",
    "ImportLocalResult",
    "IndexCatalog",
    "IndexProgress",
    "IndexResult",
    "ManageCatalog",
    "SetDigError",
    "SetDigResult",
    "SetNotEmbeddedError",
    "SetNotFoundError",
    "TrackNotEmbeddedError",
    "TrackNotFoundError",
    "VibeSearch",
    "evaluate_transition",
]
