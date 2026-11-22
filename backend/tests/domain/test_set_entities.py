"""Entity tests for the Phase 4 extensions: Passage IDs, SetMatch, DownloadedSet."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.entities.dj_set import (
    DJSet,
    DownloadedSet,
    Passage,
    SetMatch,
    TrackMatch,
)
from domain.entities.track import Track
from domain.value_objects.audio_features import BPM, EmbeddingVector, TimeRange


def _track(track_id: str = "itunes:1") -> Track:
    return Track(id=track_id, title="Song", artist="Artist")


def _match(track_id: str = "itunes:1", score: float = 0.9) -> TrackMatch:
    return TrackMatch(track=_track(track_id), similarity_score=score)


# ----------------------------------------------------------------- Passage


def test_passage_exactly_matches_require_a_known_source() -> None:
    with pytest.raises(ValueError, match="exact_id_source"):
        Passage(
            time_range=TimeRange(0.0, 30.0),
            exact_id_source="friend-told-me",  # type: ignore[arg-type]
        )


def test_passage_accepts_the_documented_sources() -> None:
    for source in ("shazam", "comments"):
        passage = Passage(
            time_range=TimeRange(0.0, 30.0),
            exact_id_match=True,
            exact_id_title="Song",
            exact_id_artist="Artist",
            exact_id_source=source,
        )
        assert passage.exact_id_source == source


def test_passage_exact_id_display_name() -> None:
    with_artist = Passage(
        time_range=TimeRange(0.0, 30.0),
        exact_id_match=True,
        exact_id_title="Song",
        exact_id_artist="Artist",
        exact_id_source="shazam",
    )
    title_only = Passage(
        time_range=TimeRange(0.0, 30.0),
        exact_id_match=True,
        exact_id_title="Song",
        exact_id_source="comments",
    )
    unnamed = Passage(time_range=TimeRange(0.0, 30.0))
    assert with_artist.exact_id_display_name == "Artist - Song"
    assert title_only.exact_id_display_name == "Song"
    assert unnamed.exact_id_display_name is None


def test_passage_with_embedding_returns_a_copy() -> None:
    passage = Passage(time_range=TimeRange(0.0, 30.0))
    embedding = EmbeddingVector(values=(0.1, 0.2))
    updated = passage.with_embedding(embedding)
    assert updated.embedding == embedding
    assert passage.embedding is None


def test_passage_rejects_wrong_embedding_type() -> None:
    with pytest.raises(TypeError, match="EmbeddingVector"):
        Passage(time_range=TimeRange(0.0, 30.0), embedding=(0.1, 0.2))  # type: ignore[arg-type]


# ------------------------------------------------------------------- DJSet


def test_djset_bpm_range_is_validated() -> None:
    with pytest.raises(ValueError, match="bpm_min"):
        DJSet(id="set-1", title="Set", bpm_min=BPM(140.0), bpm_max=BPM(120.0))
    fine = DJSet(id="set-1", title="Set", bpm_min=BPM(120.0), bpm_max=BPM(120.0))
    assert fine.bpm_min == fine.bpm_max


def test_djset_accepts_raw_bpm_values() -> None:
    dj_set = DJSet(id="set-1", title="Set", bpm_min=120, bpm_max=130)  # type: ignore[arg-type]
    assert dj_set.bpm_min == BPM(120.0)
    assert dj_set.bpm_max == BPM(130.0)


def test_djset_rejects_wrong_embedding_type() -> None:
    with pytest.raises(TypeError, match="EmbeddingVector"):
        DJSet(id="set-1", title="Set", embedding=[0.1, 0.2])  # type: ignore[arg-type]


def test_djset_with_embedding_returns_a_copy() -> None:
    dj_set = DJSet(id="set-1", title="Set")
    embedding = EmbeddingVector(values=(0.5,) * 8)
    updated = dj_set.with_embedding(embedding)
    assert updated.embedding == embedding
    assert dj_set.embedding is None


# ---------------------------------------------------------------- SetMatch


def test_setmatch_similarity_percent_matches_trackmatch_semantics() -> None:
    dj_set = DJSet(id="set-1", title="Set")
    assert SetMatch(dj_set=dj_set, similarity_score=0.9956).similarity_percent == 99.6
    assert SetMatch(dj_set=dj_set, similarity_score=0.5).similarity_percent == 50.0
    # Negative cosine is clamped to zero, not leaked as a negative percent.
    assert SetMatch(dj_set=dj_set, similarity_score=-0.5).similarity_percent == 0.0


def test_setmatch_validates_score_range_and_type() -> None:
    dj_set = DJSet(id="set-1", title="Set")
    with pytest.raises(ValueError, match="similarity_score"):
        SetMatch(dj_set=dj_set, similarity_score=1.5)
    with pytest.raises(TypeError, match="dj_set"):
        SetMatch(dj_set="set-1", similarity_score=0.5)  # type: ignore[arg-type]


# ------------------------------------------------------------ DownloadedSet


def test_downloadedset_requires_a_path() -> None:
    with pytest.raises(TypeError, match="audio_path"):
        DownloadedSet(audio_path="cache/set.m4a", title="Set")  # type: ignore[arg-type]


def test_downloadedset_defaults_to_temporary_false() -> None:
    downloaded = DownloadedSet(audio_path=Path("cache/set.m4a"), title="Set")
    assert downloaded.is_temporary is False
    assert downloaded.comments == ()
    assert downloaded.description == ""


def test_downloadedset_validates_duration() -> None:
    with pytest.raises(ValueError, match="duration_seconds"):
        DownloadedSet(
            audio_path=Path("cache/set.m4a"), title="Set", duration_seconds=0.0
        )


def test_downloadedset_keeps_comment_order() -> None:
    downloaded = DownloadedSet(
        audio_path=Path("cache/set.m4a"),
        title="Set",
        comments=("first", "second"),
    )
    assert downloaded.comments == ("first", "second")
