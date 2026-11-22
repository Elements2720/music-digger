"""Mapping between ``SeedArtist`` and the ``seed_artists`` table."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domain.entities.track import SeedArtist

from ..normalization import normalize_seed_name


def seed_to_row(seed: SeedArtist) -> dict[str, Any]:
    """Return the column values for an upsert."""
    return {
        "name": seed.name,
        "name_normalized": normalize_seed_name(seed.name),
        "deezer_id": seed.external_id,
        "priority_score": seed.priority_score,
        "category": seed.category,
        "status": seed.status,
        "source": seed.source,
    }


def row_to_seed(row: Mapping[str, Any]) -> SeedArtist:
    """Build a domain seed from a SQLite row."""
    return SeedArtist(
        name=row["name"],
        priority_score=float(row["priority_score"]),
        category=row["category"],
        status=row["status"],
        source=row["source"],
        external_id=row["deezer_id"],
    )
