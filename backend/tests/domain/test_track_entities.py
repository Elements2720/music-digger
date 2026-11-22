from __future__ import annotations

import dataclasses

import pytest

from domain.entities.track import (
    AudioBuffer,
    SeedArtist,
    Track,
    TrackReference,
    TrackVibe,
)
from domain.value_objects.audio_features import (
    BPM,
    CamelotKey,
    EmbeddingVector,
    TimeRange,
)


def test_track_minimal_construction_and_defaults() -> None:
    track = Track(id="track-1", title="Strobe", artist="deadmau5")
    assert track.id == "track-1"
    assert track.track_id == "track-1"
    assert track.display_name == "deadmau5 - Strobe"
    assert track.duration_seconds is None
    assert track.duration is None
    assert track.bpm is None
    assert track.key is None
    assert track.genre is None
    assert track.release_year is None
    assert track.isrc is None
    assert track.preview_url is None
    assert track.artwork_url is None
    assert track.source == "unknown"
    assert track.external_id is None
    assert track.embedding is None


def test_track_normalizes_raw_bpm_and_key() -> None:
    track = Track(id="t", title="Title", artist="Artist", bpm=128.0, key="8a")
    assert track.bpm == BPM(128.0)
    assert track.key == CamelotKey("8A")


def test_track_accepts_full_metadata() -> None:
    embedding = EmbeddingVector((0.1, 0.2, 0.3))
    track = Track(
        id="t",
        title="Title",
        artist="Artist",
        duration_seconds=360,
        bpm=BPM(124.0),
        key=CamelotKey("11B"),
        genre="Melodic Techno",
        release_year=2024,
        isrc="US1234567890",
        preview_url="https://example.test/preview.m4a",
        artwork_url="https://example.test/art.jpg",
        album="Album",
        store_url="https://example.test/store",
        source="itunes",
        external_id="12345",
        embedding=embedding,
    )
    assert track.duration_seconds == 360.0
    assert track.bpm == BPM(124.0)
    assert track.key == CamelotKey("11B")
    assert track.genre == "Melodic Techno"
    assert track.release_year == 2024
    assert track.album == "Album"
    assert track.store_url == "https://example.test/store"
    assert track.embedding == embedding


def test_track_rejects_blank_optional_strings() -> None:
    for field in ("album", "store_url"):
        with pytest.raises(ValueError, match=field):
            Track(id="t", title="Title", artist="Artist", **{field: "  "})  # type: ignore[arg-type]


def test_track_with_embedding_returns_a_new_entity() -> None:
    track = Track(id="t", title="Title", artist="Artist")
    embedding = EmbeddingVector((0.5, 0.5))
    updated = track.with_embedding(embedding)
    assert updated is not track
    assert updated.embedding == embedding
    assert track.embedding is None


def test_track_with_embedding_rejects_non_embedding() -> None:
    with pytest.raises(TypeError, match="EmbeddingVector"):
        Track(id="t", title="Title", artist="Artist").with_embedding((1.0, 2.0))  # type: ignore[arg-type]


def test_track_is_immutable() -> None:
    track = Track(id="t", title="Title", artist="Artist")
    with pytest.raises(dataclasses.FrozenInstanceError):
        track.title = "Other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    ["id", "title", "artist"],
)
def test_track_rejects_empty_required_strings(field: str) -> None:
    values = {"id": "t", "title": "Title", "artist": "Artist"}
    values[field] = "  "
    with pytest.raises(ValueError, match=field):
        Track(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("duration_seconds", 0),
        ("duration_seconds", -1),
        ("release_year", 1899),
        ("release_year", 2101),
        ("bpm", 300),
        ("key", "13A"),
        ("genre", " "),
        ("source", ""),
    ],
)
def test_track_rejects_invalid_values(field: str, value: object) -> None:
    kwargs: dict[str, object] = {"id": "t", "title": "Title", "artist": "Artist"}
    kwargs[field] = value
    with pytest.raises((TypeError, ValueError)):
        Track(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("duration_seconds", "300"),
        ("release_year", True),
        ("bpm", "128"),
        ("key", 8),
        ("embedding", (1.0, 2.0)),
    ],
)
def test_track_rejects_wrong_types(field: str, value: object) -> None:
    kwargs: dict[str, object] = {"id": "t", "title": "Title", "artist": "Artist"}
    kwargs[field] = value
    with pytest.raises(TypeError):
        Track(**kwargs)  # type: ignore[arg-type]


def test_seed_artist_defaults_and_priority_boundaries() -> None:
    seed = SeedArtist(name="Adam Beyer", priority_score=0.9, category="electronic")
    assert seed.status == "pending"
    assert seed.source == "llm"
    assert seed.external_id is None
    assert seed.is_pending
    assert SeedArtist("A", 0.0, "general").priority_score == 0.0
    assert SeedArtist("B", 1.0, "general").priority_score == 1.0


def test_seed_artist_accepts_optional_external_id() -> None:
    seed = SeedArtist(
        "Solomun",
        0.9,
        "electronic",
        source="deezer-graph",
        external_id="42",
    )
    assert seed.external_id == "42"
    with pytest.raises(TypeError):
        SeedArtist("Solomun", 0.9, "electronic", external_id=42)  # type: ignore[arg-type]


def test_seed_artist_with_status_returns_a_new_entity() -> None:
    seed = SeedArtist("Adam Beyer", 0.9, "electronic")
    fetched = seed.with_status("fetched")
    assert fetched is not seed
    assert fetched.status == "fetched"
    assert seed.status == "pending"
    assert not fetched.is_pending


@pytest.mark.parametrize("score", [-0.01, 1.01, float("nan"), float("inf")])
def test_seed_artist_rejects_invalid_priority(score: float) -> None:
    with pytest.raises(ValueError):
        SeedArtist("Artist", score, "electronic")


@pytest.mark.parametrize("score", ["0.5", None, True])
def test_seed_artist_rejects_non_numeric_priority(score: object) -> None:
    with pytest.raises(TypeError):
        SeedArtist("Artist", score, "electronic")  # type: ignore[arg-type]


@pytest.mark.parametrize("category", ["rock", "Electronic", "", None])
def test_seed_artist_rejects_invalid_category(category: object) -> None:
    with pytest.raises(ValueError):
        SeedArtist("Artist", 0.5, category)  # type: ignore[arg-type]


@pytest.mark.parametrize("status", ["done", "PENDING", "", None])
def test_seed_artist_rejects_invalid_status(status: object) -> None:
    with pytest.raises(ValueError):
        SeedArtist("Artist", 0.5, "electronic", status=status)  # type: ignore[arg-type]


def test_seed_artist_rejects_empty_name_and_source() -> None:
    with pytest.raises(ValueError, match="name"):
        SeedArtist(" ", 0.5, "electronic")
    with pytest.raises(ValueError, match="source"):
        SeedArtist("Artist", 0.5, "electronic", source=" ")


def test_audio_buffer_valid_and_normalizes_bytearrays() -> None:
    buffer = AudioBuffer(pcm_bytes=b"\x00\x01\x02\x03", sample_rate=48_000)
    assert buffer.pcm_bytes == b"\x00\x01\x02\x03"
    assert buffer.sample_rate == 48_000
    assert buffer.size_bytes == 4

    from_bytearray = AudioBuffer(pcm_bytes=bytearray(b"\x01\x02"), sample_rate=44_100)  # type: ignore[arg-type]
    assert from_bytearray.pcm_bytes == b"\x01\x02"
    assert isinstance(from_bytearray.pcm_bytes, bytes)

    from_memoryview = AudioBuffer(pcm_bytes=memoryview(b"\x03\x04"), sample_rate=44_100)  # type: ignore[arg-type]
    assert from_memoryview.pcm_bytes == b"\x03\x04"


@pytest.mark.parametrize("pcm", [b"", bytearray(), memoryview(b"")])
def test_audio_buffer_rejects_empty_pcm(pcm: object) -> None:
    with pytest.raises(ValueError, match="pcm_bytes must not be empty"):
        AudioBuffer(pcm_bytes=pcm, sample_rate=48_000)  # type: ignore[arg-type]


@pytest.mark.parametrize("pcm", ["abc", 123, None])
def test_audio_buffer_rejects_non_bytes_pcm(pcm: object) -> None:
    with pytest.raises(TypeError, match="pcm_bytes"):
        AudioBuffer(pcm_bytes=pcm, sample_rate=48_000)  # type: ignore[arg-type]


@pytest.mark.parametrize("sample_rate", [0, -1])
def test_audio_buffer_rejects_non_positive_sample_rate(sample_rate: int) -> None:
    with pytest.raises(ValueError, match="sample_rate must be positive"):
        AudioBuffer(pcm_bytes=b"\x00", sample_rate=sample_rate)


@pytest.mark.parametrize("sample_rate", ["48000", 48000.0, True, None])
def test_audio_buffer_rejects_non_integer_sample_rate(sample_rate: object) -> None:
    with pytest.raises(TypeError, match="sample_rate"):
        AudioBuffer(pcm_bytes=b"\x00", sample_rate=sample_rate)  # type: ignore[arg-type]


def test_track_reference_valid_and_confidence_bounds() -> None:
    reference = TrackReference(
        artist="Bicep",
        title="Glue",
        timestamp=TimeRange(120.0, 180.0),
        confidence=0.9,
    )
    assert reference.display_name == "Bicep - Glue"
    assert reference.timestamp == TimeRange(120.0, 180.0)
    assert TrackReference("A", "T", confidence=0.0).confidence == 0.0
    assert TrackReference("A", "T", confidence=1.0).confidence == 1.0


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan")])
def test_track_reference_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValueError):
        TrackReference("A", "T", confidence=confidence)


def test_track_reference_rejects_bad_types() -> None:
    with pytest.raises(ValueError, match="artist"):
        TrackReference(" ", "T")
    with pytest.raises(ValueError, match="title"):
        TrackReference("A", " ")
    with pytest.raises(TypeError, match="timestamp"):
        TrackReference("A", "T", timestamp=(0.0, 10.0))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="confidence"):
        TrackReference("A", "T", confidence="0.5")  # type: ignore[arg-type]


def test_track_vibe_normalizes_and_deduplicates_tags() -> None:
    vibe = TrackVibe(
        tags=(" Peak Time ", "peak time", "Melodic", "melodic", "Driving"),
        mood="Euphoric",
        energy=0.85,
        description="  Big room closer.  ",
    )
    assert vibe.tags == ("Peak Time", "Melodic", "Driving")
    assert vibe.mood == "Euphoric"
    assert vibe.energy == 0.85
    assert vibe.description == "Big room closer."


def test_track_vibe_allows_empty_tags_and_description() -> None:
    vibe = TrackVibe(tags=(), mood="Dark", energy=0.2)
    assert vibe.tags == ()
    assert vibe.description == ""


@pytest.mark.parametrize("energy", [-0.01, 1.01, float("nan")])
def test_track_vibe_rejects_invalid_energy(energy: float) -> None:
    with pytest.raises(ValueError):
        TrackVibe(tags=(), mood="Dark", energy=energy)


def test_track_vibe_rejects_bad_types() -> None:
    with pytest.raises(ValueError, match="mood"):
        TrackVibe(tags=(), mood=" ", energy=0.5)
    with pytest.raises(ValueError, match="tag"):
        TrackVibe(tags=("ok", " "), mood="Dark", energy=0.5)
    with pytest.raises(TypeError, match="tags"):
        TrackVibe(tags="peak-time", mood="Dark", energy=0.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="energy"):
        TrackVibe(tags=(), mood="Dark", energy="0.5")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="description"):
        TrackVibe(tags=(), mood="Dark", energy=0.5, description=1)  # type: ignore[arg-type]
