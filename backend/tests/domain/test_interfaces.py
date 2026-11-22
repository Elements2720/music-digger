from __future__ import annotations

import inspect
from abc import ABC

import pytest

from domain.interfaces import (
    IAudioDecoder,
    IAudioEmbedder,
    IAudioSegmenter,
    ICatalogProvider,
    IFeatureExtractor,
    IFingerprinter,
    IHardwareProbe,
    ILLMService,
    ISeedCrawler,
    ISeedDiscovery,
    ISeedRepository,
    ISetDownloader,
    ISetRepository,
    ITrackRepository,
)

ALL_INTERFACES = [
    IAudioDecoder,
    IAudioEmbedder,
    IAudioSegmenter,
    ICatalogProvider,
    IFeatureExtractor,
    IFingerprinter,
    IHardwareProbe,
    ILLMService,
    ISeedCrawler,
    ISeedDiscovery,
    ISeedRepository,
    ISetDownloader,
    ISetRepository,
    ITrackRepository,
]


@pytest.mark.parametrize("interface", ALL_INTERFACES, ids=lambda cls: cls.__name__)
def test_interface_is_an_abstract_base_class(interface: type[ABC]) -> None:
    assert issubclass(interface, ABC)
    assert inspect.isabstract(interface)
    assert interface.__abstractmethods__
    with pytest.raises(TypeError):
        interface()  # type: ignore[abstract]


def test_llm_interface_exposes_the_required_operations() -> None:
    assert {
        "extract_tracklist_from_comments",
        "generate_seed_artists",
        "tag_track_vibe",
    } <= ILLMService.__abstractmethods__


def test_seed_discovery_interface_exposes_discover() -> None:
    assert {"discover"} <= ISeedDiscovery.__abstractmethods__


def test_repository_interfaces_expose_expected_operations() -> None:
    assert {
        "upsert_many",
        "get_by_id",
        "get_by_external_id",
        "find_similar",
        "find_by_filter",
        "search_tracks",
        "mark_heard",
        "set_heard",
        "get_heard_ids",
        "count",
    } <= ITrackRepository.__abstractmethods__
    assert {
        "save",
        "get_by_id",
        "list_all",
        "delete",
        "count",
        "find_similar_sets",
    } <= ISetRepository.__abstractmethods__
    assert {
        "upsert_many",
        "get_by_name",
        "list_by_status",
        "update_status",
        "count_by_category",
    } <= ISeedRepository.__abstractmethods__


def test_audio_interfaces_expose_expected_operations() -> None:
    assert {
        "decode",
        "decode_url",
        "decode_segment",
    } <= IAudioDecoder.__abstractmethods__
    assert {"extract"} <= IFeatureExtractor.__abstractmethods__
    assert {"embed", "embed_batch"} <= IAudioEmbedder.__abstractmethods__
    assert {"plan_segments", "detect_passages"} <= IAudioSegmenter.__abstractmethods__
    assert {"compute", "identify"} <= IFingerprinter.__abstractmethods__
    assert {"download", "fetch_set"} <= ISetDownloader.__abstractmethods__
    assert {"probe"} <= IHardwareProbe.__abstractmethods__
    assert {"search_tracks", "lookup_track", "list_artist_tracks", "fetch_preview"} <= (
        ICatalogProvider.__abstractmethods__
    )
    assert {"crawl"} <= ISeedCrawler.__abstractmethods__


def test_embed_text_is_optional_with_a_sane_default() -> None:
    assert "embed_text" not in IAudioEmbedder.__abstractmethods__


def test_identify_async_is_optional_with_a_working_default() -> None:
    """Sync fingerprinters get a thread-based async default for free."""

    from domain.entities.track import AudioBuffer, Track
    from domain.interfaces.audio_engine import IFingerprinter

    class SyncOnlyFingerprinter(IFingerprinter):
        def compute(self, audio: AudioBuffer) -> str:  # pragma: no cover
            return "fingerprint"

        def identify(self, audio: AudioBuffer) -> Track | None:
            return Track(id="itunes:1", title="Song", artist="Artist")

    import asyncio

    audio = AudioBuffer(pcm_bytes=b"\x00\x00\x00\x00", sample_rate=8000)
    reference = asyncio.run(SyncOnlyFingerprinter().identify_async(audio))
    assert reference is not None
    assert reference.display_name == "Artist - Song"


def test_repository_interfaces_expose_phase3_operations() -> None:
    assert {
        "list_unembedded",
        "list_embedded",
        "mark_index_failed",
        "list_reindexable",
        "reset_embeddings",
    } <= ITrackRepository.__abstractmethods__
