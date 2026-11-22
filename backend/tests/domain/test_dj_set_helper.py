"""Tests for evaluate_transition and DJSetHelper pure domain logic."""

from __future__ import annotations

from domain.entities.track import Track
from domain.use_cases.dj_set_helper import DJSetHelper, evaluate_transition
from domain.value_objects.audio_features import BPM, CamelotKey, EmbeddingVector


def _make_track(
    track_id: str,
    title: str = "Track",
    artist: str = "Artist",
    bpm: float | None = 126.0,
    key: str | None = "8A",
    source: str = "local",
    local_path: str | None = "/music/track.mp3",
    embedding: tuple[float, ...] = (1.0, 0.0),
) -> Track:
    return Track(
        id=track_id,
        title=title,
        artist=artist,
        bpm=BPM(bpm) if bpm is not None else None,
        key=CamelotKey(key) if key is not None else None,
        source=source,
        local_path=local_path,
        embedding=EmbeddingVector(embedding) if embedding else None,
    )


def test_evaluate_transition_same_key() -> None:
    t1 = _make_track("1", key="8A", bpm=126.0)
    t2 = _make_track("2", key="8A", bpm=126.0)

    ev = evaluate_transition(t1, t2, flow="steady")
    assert ev.harmonic_score == 100.0
    assert ev.camelot_move == "same"
    assert ev.bpm_score == 100.0
    assert ev.bpm_delta == 0.0
    assert ev.score == 100.0


def test_evaluate_transition_smooth_plus_one_with_wrap() -> None:
    # 8A -> 9A
    t1 = _make_track("1", key="8A")
    t2 = _make_track("2", key="9A")
    ev1 = evaluate_transition(t1, t2)
    assert ev1.harmonic_score == 94.0
    assert ev1.camelot_move == "+1"

    # 12B -> 1B (wrap-around)
    t3 = _make_track("3", key="12B")
    t4 = _make_track("4", key="1B")
    ev2 = evaluate_transition(t3, t4)
    assert ev2.harmonic_score == 94.0
    assert ev2.camelot_move == "+1"


def test_evaluate_transition_smooth_minus_one_with_wrap() -> None:
    # 8A -> 7A
    t1 = _make_track("1", key="8A")
    t2 = _make_track("2", key="7A")
    ev1 = evaluate_transition(t1, t2)
    assert ev1.harmonic_score == 92.0
    assert ev1.camelot_move == "-1"

    # 1A -> 12A (wrap-around)
    t3 = _make_track("3", key="1A")
    t4 = _make_track("4", key="12A")
    ev2 = evaluate_transition(t3, t4)
    assert ev2.harmonic_score == 92.0
    assert ev2.camelot_move == "-1"


def test_evaluate_transition_relative_major_minor() -> None:
    t1 = _make_track("1", key="8A")
    t2 = _make_track("2", key="8B")
    ev = evaluate_transition(t1, t2)
    assert ev.harmonic_score == 88.0
    assert ev.camelot_move == "relative"


def test_evaluate_transition_energy_boost_and_drop() -> None:
    # +2 Energy boost: 8A -> 10A
    t1 = _make_track("1", key="8A")
    t2 = _make_track("2", key="10A")
    ev_boost = evaluate_transition(t1, t2)
    assert ev_boost.harmonic_score == 82.0
    assert ev_boost.camelot_move == "+2"

    # -2 Energy drop: 8A -> 6A
    t3 = _make_track("3", key="6A")
    ev_drop = evaluate_transition(t1, t3)
    assert ev_drop.harmonic_score == 76.0
    assert ev_drop.camelot_move == "-2"


def test_evaluate_transition_modulation_plus_seven() -> None:
    # +7 Modulation: 8A -> 3A ((8+7-1)%12 + 1 = 3)
    t1 = _make_track("1", key="8A")
    t2 = _make_track("2", key="3A")
    ev = evaluate_transition(t1, t2)
    assert ev.harmonic_score == 72.0
    assert ev.camelot_move == "+7"


def test_evaluate_transition_clash() -> None:
    # Clash: 8A -> 2A
    t1 = _make_track("1", key="8A")
    t2 = _make_track("2", key="2A")
    ev = evaluate_transition(t1, t2)
    assert ev.harmonic_score == 28.0
    assert ev.camelot_move == "clash"


def test_evaluate_transition_unknown_key() -> None:
    t1 = _make_track("1", key=None)
    t2 = _make_track("2", key="8A")
    ev = evaluate_transition(t1, t2)
    assert ev.harmonic_score == 60.0
    assert ev.camelot_move == "unknown"


def test_evaluate_transition_bpm_flow_modes() -> None:
    t_126 = _make_track("1", bpm=126.0)
    t_128 = _make_track("2", bpm=128.0)
    t_124 = _make_track("3", bpm=124.0)

    # Steady: 126 -> 128 (delta = +2)
    ev_steady = evaluate_transition(t_126, t_128, flow="steady")
    assert ev_steady.bpm_delta == 2.0
    assert ev_steady.bpm_score == 70.0  # 100 - 2 * 15

    # Ramp up: optimum at +2
    ev_ramp = evaluate_transition(t_126, t_128, flow="ramp_up")
    assert ev_ramp.bpm_score == 100.0  # 100 - (2-2)^2 * 12

    # Cool down: optimum at -2 (126 -> 124)
    ev_cool = evaluate_transition(t_126, t_124, flow="cool_down")
    assert ev_cool.bpm_delta == -2.0
    assert ev_cool.bpm_score == 100.0  # 100 - (-2+2)^2 * 12


async def test_auto_sequence_and_export_m3u8() -> None:
    tracks = {
        "t1": _make_track("t1", title="Intro", artist="A", bpm=124.0, key="8A"),
        "t2": _make_track("t2", title="Peak", artist="B", bpm=128.0, key="10A"),
        "t3": _make_track("t3", title="Build", artist="C", bpm=126.0, key="9A"),
    }

    class FakeRepo:
        async def get_by_id(self, tid: str) -> Track | None:
            return tracks.get(tid)

    helper = DJSetHelper(FakeRepo())  # type: ignore

    # Auto-sequence with ramp_up should order t1 (124, 8A) -> t3 (126, 9A) -> t2 (128, 10A)
    ordered_ids, score = await helper.auto_sequence(
        ["t2", "t1", "t3"], flow="ramp_up", lock_first=False
    )
    assert ordered_ids == ("t1", "t3", "t2")
    assert score > 80.0

    # Evaluate sequence
    evals = await helper.evaluate_sequence(ordered_ids, flow="ramp_up")
    assert len(evals) == 2
    assert evals[0].camelot_move == "+1"
    assert evals[1].camelot_move == "+1"

    # Export M3U8
    m3u8 = await helper.export_m3u8("My Set", ordered_ids)
    assert "#EXTM3U" in m3u8
    assert "#PLAYLIST:My Set" in m3u8
    assert "#EXTINF:30,A - Intro" in m3u8
    assert "/music/track.mp3" in m3u8
