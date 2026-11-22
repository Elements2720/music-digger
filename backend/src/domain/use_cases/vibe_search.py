"""Use case: natural-language ("vibe") search over the local catalog.

The CLAP model embeds text and audio into the same space, so a free-text
description such as ``"dark hypnotic peak-time techno"`` can be compared
directly against stored track embeddings. The query is embedded once, then the
disk-backed vector index is searched with the caller's
:class:`~domain.entities.search.SearchFilter` (BPM bounds, Camelot allow-list,
heard/genre filters).
"""

from __future__ import annotations

from collections.abc import Sequence

from ..entities.dj_set import TrackMatch
from ..entities.search import SearchFilter
from ..interfaces.audio_engine import IAudioEmbedder
from ..interfaces.repositories import ITrackRepository


class VibeSearch:
    """Text-to-audio similarity search over the local catalog."""

    def __init__(
        self,
        *,
        embedder: IAudioEmbedder,
        track_repository: ITrackRepository,
    ) -> None:
        self._embedder = embedder
        self._track_repository = track_repository

    async def execute(
        self,
        query: str,
        search_filter: SearchFilter | None = None,
    ) -> Sequence[TrackMatch]:
        """Return the catalog tracks whose sound best matches ``query``.

        ``query`` is stripped and must not be empty. Only the absolute filter
        fields apply here: without a reference track there is no BPM tolerance
        window or relative harmonic allow-list to derive.
        """
        text = query.strip()
        if not text:
            raise ValueError("query must not be empty")

        embedding = self._embedder.embed_text(text)
        return await self._track_repository.find_similar(
            embedding,
            search_filter or SearchFilter(),
        )


__all__ = ["VibeSearch"]
