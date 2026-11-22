"""Pure domain use case for DJ set planning, transition scoring, and auto-sequencing."""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..entities.search import SearchFilter
from ..entities.set_plan import (
    BridgeSuggestion,
    FlowMode,
    NextTrackSuggestion,
    TransitionEvaluation,
)
from ..entities.track import Track
from ..interfaces.repositories import (
    IBlacklistRepository,
    IPlannedSetRepository,
    ITrackRepository,
)
from ..value_objects.audio_features import CamelotKey, EmbeddingVector
from .dig_similar_tracks import TrackNotEmbeddedError, TrackNotFoundError


def evaluate_transition(
    from_track: Track,
    to_track: Track,
    *,
    audio_similarity: float | None = None,
    flow: FlowMode = "steady",
) -> TransitionEvaluation:
    """Evaluate a musical transition between two tracks based on Camelot harmony, BPM flow, and audio similarity."""
    # 1. Camelot Harmonic Scoring (0..100)
    k1 = from_track.key
    k2 = to_track.key

    if k1 is None or k2 is None:
        harmonic_score = 60.0
        camelot_move = "unknown"
    else:
        try:
            # Ensure keys are valid CamelotKey objects
            ck1 = k1 if isinstance(k1, CamelotKey) else CamelotKey(str(k1))
            ck2 = k2 if isinstance(k2, CamelotKey) else CamelotKey(str(k2))
            if ck1.notation == ck2.notation:
                harmonic_score = 100.0
                camelot_move = "same"
            elif ck1.number == ck2.number and ck1.letter != ck2.letter:
                harmonic_score = 88.0
                camelot_move = "relative"
            elif ck1.letter == ck2.letter:
                diff = (ck2.number - ck1.number) % 12
                if diff == 1:
                    harmonic_score = 94.0
                    camelot_move = "+1"
                elif diff == 11:
                    harmonic_score = 92.0
                    camelot_move = "-1"
                elif diff == 2:
                    harmonic_score = 82.0
                    camelot_move = "+2"
                elif diff == 10:
                    harmonic_score = 76.0
                    camelot_move = "-2"
                elif diff == 7:
                    harmonic_score = 72.0
                    camelot_move = "+7"
                else:
                    harmonic_score = 28.0
                    camelot_move = "clash"
            else:
                harmonic_score = 28.0
                camelot_move = "clash"
        except (ValueError, TypeError):
            harmonic_score = 60.0
            camelot_move = "unknown"

    # 2. BPM Flow Scoring (0..100)
    b1 = from_track.bpm
    b2 = to_track.bpm

    if b1 is None or b2 is None:
        bpm_score = 50.0
        bpm_delta = 0.0
    else:
        bpm_delta = round(b2.value - b1.value, 1)
        if flow == "steady":
            bpm_score = max(0.0, min(100.0, 100.0 - abs(bpm_delta) * 15.0))
        elif flow == "ramp_up":
            bpm_score = max(0.0, min(100.0, 100.0 - (bpm_delta - 2.0) ** 2 * 12.0))
        elif flow == "cool_down":
            bpm_score = max(0.0, min(100.0, 100.0 - (bpm_delta + 2.0) ** 2 * 12.0))
        else:  # "any"
            bpm_score = max(0.0, min(100.0, 100.0 - abs(bpm_delta) * 8.0))

    # 3. Audio Similarity Scoring (0..100)
    if audio_similarity is not None:
        audio_score = max(0.0, min(100.0, float(audio_similarity)))
    else:
        audio_score = round(harmonic_score * 0.6 + bpm_score * 0.4, 1)

    # 4. Composite score: 40% harmony, 30% BPM, 30% audio
    total_score = round(
        0.40 * harmonic_score + 0.30 * bpm_score + 0.30 * audio_score, 1
    )

    return TransitionEvaluation(
        score=total_score,
        harmonic_score=round(harmonic_score, 1),
        bpm_score=round(bpm_score, 1),
        audio_score=round(audio_score, 1),
        camelot_move=camelot_move,
        bpm_delta=bpm_delta,
    )


class DJSetHelper:
    """Use case orchestrating set building, transition recommendations, and set optimization."""

    def __init__(
        self,
        track_repository: ITrackRepository,
        planned_set_repository: IPlannedSetRepository | None = None,
        blacklist_repository: IBlacklistRepository | None = None,
    ) -> None:
        self._track_repo = track_repository
        self._set_repo = planned_set_repository
        self._blacklist_repo = blacklist_repository

    async def suggest_next(
        self,
        from_track_id: str,
        *,
        limit: int = 15,
        flow: FlowMode = "steady",
        local_only: bool = False,
        bpm_max_delta: float = 6.0,
        candidate_pool_limit: int = 200,
    ) -> Sequence[NextTrackSuggestion]:
        """Suggest candidate tracks to follow ``from_track_id`` in a DJ set."""
        from_track = await self._track_repo.get_by_id(from_track_id)
        if from_track is None:
            raise TrackNotFoundError(f"Track '{from_track_id}' not found")
        if from_track.embedding is None:
            raise TrackNotEmbeddedError(
                f"Track '{from_track_id}' has not been embedded yet"
            )

        # Set up candidate search filter with BPM window if available
        bpm_min = None
        bpm_max = None
        if from_track.bpm is not None and bpm_max_delta > 0:
            bpm_min = max(40.0, from_track.bpm.value - bpm_max_delta)
            bpm_max = min(220.0, from_track.bpm.value + bpm_max_delta)

        search_filter = SearchFilter(
            limit=candidate_pool_limit,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
        )

        matches = await self._track_repo.find_similar(
            from_track.embedding, search_filter=search_filter
        )

        # Fallback to broader search if BPM window produced too few matches
        if len(matches) < limit and bpm_min is not None:
            broad_filter = SearchFilter(limit=candidate_pool_limit)
            matches = await self._track_repo.find_similar(
                from_track.embedding, search_filter=broad_filter
            )

        blocked_artists = frozenset()
        blocked_tracks = frozenset()
        if self._blacklist_repo:
            blocked_artists = await self._blacklist_repo.get_blocked_artist_keys()
            blocked_tracks = await self._blacklist_repo.get_blocked_track_keys()

        suggestions: list[NextTrackSuggestion] = []
        for m in matches:
            t = m.track
            if t.id == from_track_id:
                continue
            if local_only and t.source != "local":
                continue
            if blocked_artists and t.artist.strip().lower() in blocked_artists:
                continue
            norm_track_key = f"{t.artist.strip().lower()}|{t.title.strip().lower()}"
            if blocked_tracks and norm_track_key in blocked_tracks:
                continue

            evaluation = evaluate_transition(
                from_track,
                t,
                audio_similarity=m.similarity_score,
                flow=flow,
            )
            suggestions.append(NextTrackSuggestion(track=t, evaluation=evaluation))

        suggestions.sort(
            key=lambda s: (s.evaluation.score, s.evaluation.audio_score),
            reverse=True,
        )
        return tuple(suggestions[:limit])

    async def find_bridge(
        self,
        track_a_id: str,
        track_b_id: str,
        *,
        limit: int = 10,
        local_only: bool = False,
    ) -> Sequence[BridgeSuggestion]:
        """Find stepping-stone tracks bridging two musically distant tracks."""
        track_a = await self._track_repo.get_by_id(track_a_id)
        if track_a is None:
            raise TrackNotFoundError(f"Track '{track_a_id}' not found")
        track_b = await self._track_repo.get_by_id(track_b_id)
        if track_b is None:
            raise TrackNotFoundError(f"Track '{track_b_id}' not found")

        if track_a.embedding is None:
            raise TrackNotEmbeddedError(f"Track '{track_a_id}' is not embedded")
        if track_b.embedding is None:
            raise TrackNotEmbeddedError(f"Track '{track_b_id}' is not embedded")

        va = track_a.embedding.values
        vb = track_b.embedding.values
        midpoint_vec = tuple((a + b) / 2.0 for a, b in zip(va, vb))
        norm = math.sqrt(sum(x * x for x in midpoint_vec))
        if norm > 0:
            midpoint_vec = tuple(x / norm for x in midpoint_vec)
        midpoint_embedding = EmbeddingVector(midpoint_vec)

        # BPM bracket around both tracks
        bpm_min = None
        bpm_max = None
        if track_a.bpm and track_b.bpm:
            bpm_min = max(40.0, min(track_a.bpm.value, track_b.bpm.value) - 2.0)
            bpm_max = min(220.0, max(track_a.bpm.value, track_b.bpm.value) + 2.0)

        search_filter = SearchFilter(limit=100, bpm_min=bpm_min, bpm_max=bpm_max)
        matches = await self._track_repo.find_similar(
            midpoint_embedding, search_filter=search_filter
        )

        blocked_artists = frozenset()
        blocked_tracks = frozenset()
        if self._blacklist_repo:
            blocked_artists = await self._blacklist_repo.get_blocked_artist_keys()
            blocked_tracks = await self._blacklist_repo.get_blocked_track_keys()

        bridges: list[BridgeSuggestion] = []
        for m in matches:
            c = m.track
            if c.id in (track_a_id, track_b_id):
                continue
            if local_only and c.source != "local":
                continue
            if blocked_artists and c.artist.strip().lower() in blocked_artists:
                continue
            norm_track_key = f"{c.artist.strip().lower()}|{c.title.strip().lower()}"
            if blocked_tracks and norm_track_key in blocked_tracks:
                continue

            eval_a = evaluate_transition(track_a, c, flow="steady")
            eval_b = evaluate_transition(c, track_b, flow="steady")
            combined_score = round((eval_a.score + eval_b.score) / 2.0, 1)

            bridges.append(
                BridgeSuggestion(
                    bridge_track=c,
                    eval_from_a=eval_a,
                    eval_to_b=eval_b,
                    combined_score=combined_score,
                )
            )

        bridges.sort(key=lambda b: b.combined_score, reverse=True)
        return tuple(bridges[:limit])

    async def auto_sequence(
        self,
        track_ids: Sequence[str],
        *,
        flow: FlowMode = "ramp_up",
        lock_first: bool = False,
    ) -> tuple[Sequence[str], float]:
        """Re-order tracks to maximize overall transition smoothness using nearest-neighbor + 2-opt search."""
        if len(track_ids) <= 1:
            return (tuple(track_ids), 100.0)

        # Resolve tracks
        tracks_map: dict[str, Track] = {}
        for tid in track_ids:
            t = await self._track_repo.get_by_id(tid)
            if t is not None:
                tracks_map[tid] = t

        valid_ids = [tid for tid in track_ids if tid in tracks_map]
        n = len(valid_ids)
        if n <= 1:
            return (tuple(valid_ids), 100.0)
        if n == 2:
            ev = evaluate_transition(
                tracks_map[valid_ids[0]], tracks_map[valid_ids[1]], flow=flow
            )
            return (tuple(valid_ids), ev.score)

        # Precompute transition score matrix
        matrix: dict[tuple[str, str], float] = {}
        for i in range(n):
            id_i = valid_ids[i]
            t_i = tracks_map[id_i]
            for j in range(n):
                if i == j:
                    continue
                id_j = valid_ids[j]
                t_j = tracks_map[id_j]
                ev = evaluate_transition(t_i, t_j, flow=flow)
                matrix[(id_i, id_j)] = ev.score

        # Multi-start nearest-neighbor construction
        start_candidates = [valid_ids[0]] if lock_first else valid_ids
        best_path: list[str] = []
        best_total_score = -1.0

        for start_id in start_candidates:
            current_path = [start_id]
            remaining = set(valid_ids)
            remaining.remove(start_id)

            while remaining:
                curr = current_path[-1]
                next_id = max(remaining, key=lambda cand: matrix.get((curr, cand), 0.0))
                current_path.append(next_id)
                remaining.remove(next_id)

            score = sum(
                matrix.get((current_path[k], current_path[k + 1]), 0.0)
                for k in range(n - 1)
            )
            if score > best_total_score:
                best_total_score = score
                best_path = current_path

        # 2-opt local search optimization (bounded to 200 swaps)
        path = list(best_path)
        start_idx = 1 if lock_first else 0
        swaps = 0
        improved = True

        while improved and swaps < 200:
            improved = False
            for i in range(start_idx, n - 2):
                for j in range(i + 1, n - 1):
                    # Check if reversing path[i+1 : j+1] improves total score
                    before_cost = 0.0
                    after_cost = 0.0

                    if i >= 0:
                        before_cost += matrix.get((path[i], path[i + 1]), 0.0)
                        after_cost += matrix.get((path[i], path[j]), 0.0)

                    if j + 1 < n:
                        before_cost += matrix.get((path[j], path[j + 1]), 0.0)
                        after_cost += matrix.get((path[i + 1], path[j + 1]), 0.0)

                    # Transitions inside the reversed section
                    for k in range(i + 1, j):
                        before_cost += matrix.get((path[k], path[k + 1]), 0.0)
                        after_cost += matrix.get((path[k + 1], path[k]), 0.0)

                    if after_cost - before_cost > 0.01:
                        path[i + 1 : j + 1] = reversed(path[i + 1 : j + 1])
                        improved = True
                        swaps += 1
                        break
                if improved:
                    break

        avg_score = round(
            sum(matrix.get((path[k], path[k + 1]), 0.0) for k in range(n - 1))
            / max(1, n - 1),
            1,
        )
        return (tuple(path), avg_score)

    async def evaluate_sequence(
        self,
        track_ids: Sequence[str],
        *,
        flow: FlowMode = "steady",
    ) -> Sequence[TransitionEvaluation]:
        """Compute transition evaluations for every adjacent pair in the sequence."""
        if len(track_ids) < 2:
            return ()

        tracks_map: dict[str, Track] = {}
        for tid in track_ids:
            t = await self._track_repo.get_by_id(tid)
            if t is not None:
                tracks_map[tid] = t

        evaluations: list[TransitionEvaluation] = []
        for i in range(len(track_ids) - 1):
            t1 = tracks_map.get(track_ids[i])
            t2 = tracks_map.get(track_ids[i + 1])
            if t1 is None or t2 is None:
                evaluations.append(
                    TransitionEvaluation(
                        score=0.0,
                        harmonic_score=0.0,
                        bpm_score=0.0,
                        audio_score=0.0,
                        camelot_move="unknown",
                        bpm_delta=0.0,
                    )
                )
            else:
                evaluations.append(evaluate_transition(t1, t2, flow=flow))

        return tuple(evaluations)

    async def export_m3u8(self, name: str, track_ids: Sequence[str]) -> str:
        """Generate a valid UTF-8 #EXTM3U playlist file content."""
        tracks_map: dict[str, Track] = {}
        for tid in track_ids:
            t = await self._track_repo.get_by_id(tid)
            if t is not None:
                tracks_map[tid] = t

        clean_name = name.strip() or "DJ Set Plan"
        lines = [
            "#EXTM3U",
            f"#PLAYLIST:{clean_name}",
        ]

        for tid in track_ids:
            t = tracks_map.get(tid)
            if t is None:
                continue
            dur = 30
            if t.duration_seconds:
                dur = round(t.duration_seconds)
            lines.append(f"#EXTINF:{dur},{t.artist} - {t.title}")
            file_ref = t.local_path or t.preview_url or f"track:{t.id}"
            lines.append(file_ref)

        return "\n".join(lines) + "\n"
