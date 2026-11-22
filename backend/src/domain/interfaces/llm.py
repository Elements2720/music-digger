"""Local LLM interface for tracklist extraction, seeds, and vibe tagging."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..entities.track import SeedArtist, Track, TrackReference, TrackVibe


class ILLMService(ABC):
    """An OpenAI-compatible local LLM (Ollama, LM Studio, vLLM, llama.cpp)."""

    @abstractmethod
    async def extract_tracklist_from_comments(
        self,
        comments: Sequence[str],
        *,
        context: str | None = None,
    ) -> Sequence[TrackReference]:
        """Extract artist/title references from comments and timestamps.

        Implementations must return only confidently parsed references and must
        not invent tracks. ``context`` can carry a set title or known DJ name.
        """

    @abstractmethod
    async def generate_seed_artists(
        self,
        *,
        genres: Sequence[str],
        count: int = 25,
        exclude_artists: Sequence[str] = (),
    ) -> Sequence[SeedArtist]:
        """Generate crawl seeds weighted toward the requested genres.

        The use case is responsible for enforcing the ~75% electronic / 25%
        general catalog mix across the combined seed set.
        """

    @abstractmethod
    async def tag_track_vibe(self, track: Track) -> TrackVibe:
        """Return mood, energy, and descriptive tags for a track."""
