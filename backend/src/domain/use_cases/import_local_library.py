"""Use case: import local music library into catalog and seed discoveries."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..entities.track import AudioBuffer, SeedArtist, Track
from ..interfaces.audio_engine import IAudioDecoder, IAudioEmbedder, IFeatureExtractor
from ..interfaces.local_library import ILocalLibraryScanner
from ..interfaces.repositories import ISeedRepository, ITrackRepository
from ..value_objects.audio_features import TimeRange

LOGGER = logging.getLogger(__name__)


def _default_artist_parser(artist_name: str, track_title: str = "") -> tuple[str, ...]:
    cleaned = artist_name.strip()
    return (cleaned,) if cleaned else ()


@dataclass(frozen=True, slots=True)
class ImportLocalProgress:
    """Progress event emitted during local library importing."""

    stage: str
    completed: int
    total: int | None = None
    failed: int = 0
    message: str = ""


@dataclass(frozen=True, slots=True)
class ImportLocalResult:
    """Summary of a local library import run."""

    scanned: int
    imported: int
    embedded: int
    failed: int
    artists_seeded: int


class ImportLocalLibrary:
    """Scan local directory, decode core windows, extract features, embed, and seed artists."""

    def __init__(
        self,
        *,
        scanner: ILocalLibraryScanner,
        audio_decoder: IAudioDecoder,
        feature_extractor: IFeatureExtractor,
        audio_embedder: IAudioEmbedder,
        track_repository: ITrackRepository,
        seed_repository: ISeedRepository,
        artist_parser: Callable[[str, str], Sequence[str]] | None = None,
        cpu_executor: Executor | None = None,
        cpu_workers: int = 4,
    ) -> None:
        if cpu_workers < 1:
            raise ValueError("cpu_workers must be at least 1")
        self._scanner = scanner
        self._audio_decoder = audio_decoder
        self._feature_extractor = feature_extractor
        self._audio_embedder = audio_embedder
        self._track_repository = track_repository
        self._seed_repository = seed_repository
        self._artist_parser = artist_parser or _default_artist_parser
        self._cpu_executor = cpu_executor
        self._cpu_workers = cpu_workers

    async def execute(
        self,
        folder_path: str | Path,
        *,
        recursive: bool = True,
        batch_size: int = 16,
        reindex: bool = False,
        seed_artists: bool = True,
        min_duration: float = 60.0,
        max_duration: float = 900.0,
        progress: Callable[[ImportLocalProgress], None] | None = None,
    ) -> ImportLocalResult:
        """Scan, decode, feature-extract, embed, and seed artists from local tracks."""
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        loop = asyncio.get_running_loop()
        own_executor = self._cpu_executor is None
        executor = self._cpu_executor or ProcessPoolExecutor(
            max_workers=self._cpu_workers
        )

        try:
            if progress is not None:
                progress(
                    ImportLocalProgress(
                        stage="scanning",
                        completed=0,
                        message=f"Scanning {folder_path}...",
                    )
                )

            scanned_tracks = await self._scanner.scan(
                folder_path,
                recursive=recursive,
                min_duration_seconds=min_duration,
                max_duration_seconds=max_duration,
            )
            scanned_count = len(scanned_tracks)
            if scanned_count == 0:
                return ImportLocalResult(
                    scanned=0,
                    imported=0,
                    embedded=0,
                    failed=0,
                    artists_seeded=0,
                )

            if not reindex:
                embedded_ids = await self._track_repository.get_embedded_ids(
                    [track.id for track in scanned_tracks]
                )
                tracks_to_process = [
                    track for track in scanned_tracks if track.id not in embedded_ids
                ]
            else:
                tracks_to_process = list(scanned_tracks)

            total_to_process = len(tracks_to_process)
            if progress is not None:
                progress(
                    ImportLocalProgress(
                        stage="found",
                        completed=0,
                        total=total_to_process,
                        message=f"Found {scanned_count} tracks ({total_to_process} to index)",
                    )
                )

            processed_count = 0
            failed_count = 0
            all_hydrated_tracks: list[Track] = []
            batch: list[tuple[Track, Any, AudioBuffer]] = []

            for track in tracks_to_process:
                try:
                    if not track.local_path:
                        raise ValueError(f"Track {track.id} has no local_path")

                    duration = track.duration_seconds or 180.0
                    if duration <= 30.0:
                        start_sec = 0.0
                        win_dur = duration
                    else:
                        start_sec = max(0.0, duration * 0.40)
                        start_sec = min(start_sec, duration - 30.0)
                        win_dur = 30.0

                    time_range = TimeRange(
                        start_seconds=round(start_sec, 3),
                        end_seconds=round(start_sec + win_dur, 3),
                    )

                    buffer = await self._audio_decoder.decode_segment(
                        Path(track.local_path),
                        time_range,
                        sample_rate=48_000,
                        channels=1,
                    )

                    features = await loop.run_in_executor(
                        executor,
                        self._feature_extractor.extract,
                        buffer,
                    )
                    batch.append((track, features, buffer))
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("Processing local track %s failed: %s", track.id, exc)
                    failed_count += 1
                    if progress is not None:
                        progress(
                            ImportLocalProgress(
                                stage="extracting",
                                completed=processed_count,
                                total=total_to_process,
                                failed=failed_count,
                                message=f"Failed: {track.display_name}",
                            )
                        )
                    continue

                if len(batch) >= batch_size:
                    persisted = await self._flush_batch(batch)
                    all_hydrated_tracks.extend(persisted)
                    processed_count += len(persisted)
                    if progress is not None:
                        progress(
                            ImportLocalProgress(
                                stage="indexing",
                                completed=processed_count,
                                total=total_to_process,
                                failed=failed_count,
                                message=persisted[-1].display_name if persisted else "",
                            )
                        )

            if batch:
                persisted = await self._flush_batch(batch)
                all_hydrated_tracks.extend(persisted)
                processed_count += len(persisted)
                if progress is not None:
                    progress(
                        ImportLocalProgress(
                            stage="indexing",
                            completed=processed_count,
                            total=total_to_process,
                            failed=failed_count,
                            message=persisted[-1].display_name if persisted else "",
                        )
                    )

            # Taste-based artist seeding
            artists_seeded_count = 0
            if seed_artists:
                source_tracks = all_hydrated_tracks or scanned_tracks
                unique_artists: set[str] = set()
                for tr in source_tracks:
                    names = self._artist_parser(tr.artist, tr.title)
                    for name in names:
                        cleaned = name.strip()
                        if cleaned:
                            unique_artists.add(cleaned)

                if unique_artists:
                    seeds = [
                        SeedArtist(
                            name=name,
                            priority_score=1.0,
                            category="electronic",
                            source="local-library",
                        )
                        for name in sorted(unique_artists)
                    ]
                    artists_seeded_count = await self._seed_repository.record_discovery(
                        seeds
                    )

            if progress is not None:
                progress(
                    ImportLocalProgress(
                        stage="completed",
                        completed=processed_count,
                        total=total_to_process,
                        failed=failed_count,
                        message=f"Imported {processed_count} tracks, seeded {artists_seeded_count} artists",
                    )
                )

            return ImportLocalResult(
                scanned=scanned_count,
                imported=processed_count,
                embedded=processed_count,
                failed=failed_count,
                artists_seeded=artists_seeded_count,
            )
        finally:
            if own_executor:
                executor.shutdown(wait=False, cancel_futures=True)

    async def _flush_batch(
        self,
        batch: list[tuple[Track, Any, AudioBuffer]],
    ) -> list[Track]:
        if not batch:
            return []
        buffers = [b for _, _, b in batch]
        vectors = await asyncio.to_thread(self._audio_embedder.embed_batch, buffers)
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"embedder returned {len(vectors)} vectors for {len(batch)} items"
            )
        hydrated: list[Track] = []
        for (track, features, _), vector in zip(batch, vectors):
            hydrated.append(
                replace(
                    track,
                    bpm=features.bpm,
                    key=features.key,
                    embedding=vector,
                )
            )
        await self._track_repository.upsert_many(hydrated)
        batch.clear()
        return hydrated


__all__ = [
    "ImportLocalLibrary",
    "ImportLocalProgress",
    "ImportLocalResult",
]
