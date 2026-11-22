"""Disk-backed LanceDB wrapper for CLAP embedding vectors.

Vectors are stored as fixed-size ``float16`` lists. The table is never loaded
into memory as a whole; searches use LanceDB's on-disk index.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lancedb
import numpy as np
import pyarrow as pa
from lancedb.index import IvfPq

LOGGER = logging.getLogger(__name__)

CLAP_DIMENSION = 512
INDEX_THRESHOLD = 10_000

#: Schema for the whole-set similarity table: one L2-normalized mean embedding
#: per analyzed DJ set, plus the set's tempo range for metadata filtering.
SET_VECTOR_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string()),
        pa.field("bpm_min", pa.float32()),
        pa.field("bpm_max", pa.float32()),
        pa.field(
            "vector",
            pa.list_(pa.float16(), CLAP_DIMENSION),
        ),
    ]
)


@dataclass(frozen=True, slots=True)
class VectorMatch:
    """A vector-search hit before SQLite metadata hydration."""

    track_id: str
    similarity: float


def _build_track_vector_schema(dimension: int) -> Any:
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("bpm", pa.float32()),
            pa.field("camelot_key", pa.string()),
            pa.field("genre", pa.string()),
            pa.field(
                "vector",
                pa.list_(pa.float16(), dimension),
            ),
        ]
    )


class LanceDBClient:
    """Owns one LanceDB database directory and its track-vector table."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        table_name: str = "track_vectors",
        vector_dimension: int = CLAP_DIMENSION,
        schema: Any | None = None,
    ) -> None:
        self._path = Path(db_path)
        self._table_name = table_name
        self._vector_dimension = vector_dimension
        self._schema = schema
        self._db: Any | None = None
        self._table: Any | None = None

    @property
    def path(self) -> Path:
        """Filesystem path of the LanceDB directory."""
        return self._path

    @property
    def vector_dimension(self) -> int:
        """Expected embedding width."""
        return self._vector_dimension

    async def connect(self) -> None:
        """Open the database and prepare the table if it already exists."""
        if self._db is not None:
            return
        self._path.mkdir(parents=True, exist_ok=True)
        self._db = await asyncio.to_thread(lancedb.connect, str(self._path))
        table_names = await asyncio.to_thread(self._list_tables)
        if self._table_name in table_names:
            self._table = await asyncio.to_thread(self._db.open_table, self._table_name)

    def _list_tables(self) -> list[str]:
        list_tables = getattr(self._db, "list_tables", None)
        if callable(list_tables):
            return list(list_tables())
        return list(self._db.table_names())

    async def close(self) -> None:
        """Release references. LanceDB has no explicit connection close."""
        self._table = None
        self._db = None

    async def upsert_many(self, rows: Sequence[dict[str, Any]]) -> int:
        """Insert or update vector rows keyed by ``id``."""
        if not rows:
            return 0
        for row in rows:
            vector = row.get("vector")
            if not isinstance(vector, (list, tuple)):
                raise TypeError("vector row must contain a list of numbers")
            if len(vector) != self._vector_dimension:
                raise ValueError(
                    "embedding dimension mismatch: expected "
                    f"{self._vector_dimension}, got {len(vector)}"
                )

        table = await self._ensure_table()
        try:
            merge = table.merge_insert("id")
            merge = merge.when_matched_update_all()
            merge = merge.when_not_matched_insert_all()
            await asyncio.to_thread(merge.execute, list(rows))
        except Exception:  # noqa: BLE001 - fallback for older LanceDB releases
            # Older LanceDB builds may not expose merge_insert. Deleting and
            # appending keeps the operation idempotent at the cost of a rewrite.
            ids = [str(row["id"]) for row in rows]
            quoted = ", ".join(self._quote(value) for value in ids)
            await asyncio.to_thread(table.delete, f"id IN ({quoted})")
            await asyncio.to_thread(table.add, list(rows))

        await self.maybe_create_index()
        return len(rows)

    async def search(
        self,
        vector: Sequence[float],
        *,
        limit: int = 50,
        where: str | None = None,
    ) -> Sequence[VectorMatch]:
        """Return nearest neighbours using cosine distance."""
        if len(vector) != self._vector_dimension:
            raise ValueError(
                "embedding dimension mismatch: expected "
                f"{self._vector_dimension}, got {len(vector)}"
            )
        if limit <= 0:
            return ()
        table = await self._ensure_table()
        query = table.search(list(vector)).metric("cosine").limit(limit)
        if where:
            query = query.where(where)
        rows = await asyncio.to_thread(query.to_list)
        matches: list[VectorMatch] = []
        for row in rows:
            distance = float(row.get("_distance", 1.0))
            if not math.isfinite(distance):
                # NaN would silently survive `min(1.0, 1.0 - NaN)` as 1.0 and
                # show up as a bogus 100% match.
                LOGGER.warning("LanceDB returned a non-finite distance; skipping row")
                continue
            similarity = max(-1.0, min(1.0, 1.0 - distance))
            matches.append(VectorMatch(track_id=str(row["id"]), similarity=similarity))
        return tuple(matches)

    async def get_vector(self, track_id: str) -> tuple[float, ...] | None:
        """Return one stored vector, or ``None`` when the id is absent."""
        table = await self._ensure_table()
        try:
            arrow = await asyncio.to_thread(
                table.to_lance().to_table,
                filter=f"id = {self._quote(track_id)}",
                columns=["vector"],
            )
        except Exception:  # noqa: BLE001 - a missing row is a normal lookup miss
            return None
        rows = arrow.to_pylist()
        if not rows:
            return None
        return tuple(float(value) for value in rows[0]["vector"])

    async def compute_similarity_to_seed_ids(
        self,
        seed_track_ids: Sequence[str],
        batch_size: int = 2048,
    ) -> dict[str, float]:
        """Compute cosine similarity percent against the mean vector of ``seed_track_ids``.

        Streams dataset batches so peak RAM usage remains small and bounded.
        Returns a mapping of track_id to similarity percentage (0.0 to 100.0).
        """
        if not seed_track_ids:
            return {}
        if await self.count() == 0:
            return {}
        table = await self._ensure_table()
        return await asyncio.to_thread(
            self._compute_similarity_sync, table, seed_track_ids, batch_size
        )

    def _compute_similarity_sync(
        self,
        table: Any,
        seed_track_ids: Sequence[str],
        batch_size: int,
    ) -> dict[str, float]:
        lance_ds = table.to_lance()
        seed_vecs: list[list[float]] = []
        for i in range(0, len(seed_track_ids), 500):
            chunk = seed_track_ids[i : i + 500]
            quoted_chunk = ", ".join(self._quote(tid) for tid in chunk)
            try:
                seed_table = lance_ds.to_table(
                    filter=f"id IN ({quoted_chunk})",
                    columns=["id", "vector"],
                )
                rows = seed_table.to_pylist()
                for r in rows:
                    if r.get("vector") is not None:
                        seed_vecs.append(r["vector"])
            except Exception:  # noqa: BLE001, S112
                continue

        if not seed_vecs:
            return {}

        arr = np.array(seed_vecs, dtype=np.float32)
        mean_vec = np.mean(arr, axis=0)
        norm = np.linalg.norm(mean_vec)
        if norm <= 1e-9:
            return {}
        taste_vec = mean_vec / norm

        results: dict[str, float] = {}
        scanner = lance_ds.scanner(columns=["id", "vector"], batch_size=batch_size)
        for record_batch in scanner.to_batches():
            ids = record_batch.column("id").to_pylist()
            raw_vectors = record_batch.column("vector").to_pylist()
            if not ids or not raw_vectors:
                continue
            batch_arr = np.array(raw_vectors, dtype=np.float32)
            row_norms = np.linalg.norm(batch_arr, axis=1, keepdims=True)
            row_norms[row_norms <= 1e-9] = 1.0
            normed_batch = batch_arr / row_norms
            dots = np.dot(normed_batch, taste_vec)
            for track_id, dot in zip(ids, dots, strict=False):
                pct = round(float(max(0.0, min(1.0, dot))) * 100.0, 1)
                results[str(track_id)] = pct

        return results

    async def count(self) -> int:
        """Return the number of vector rows without loading them."""
        table = await self._ensure_table()
        return int(await asyncio.to_thread(table.count_rows))

    async def clear_all(self) -> None:
        """Drop the whole vector table; it is recreated empty on next use."""
        if self._db is None:
            raise RuntimeError("LanceDBClient is not connected")
        if self._table is None:
            return  # Nothing stored yet.
        try:
            await asyncio.to_thread(self._db.drop_table, self._table_name)
        except Exception:
            LOGGER.debug("Dropping the vector table failed", exc_info=True)
        self._table = None

    async def delete_ids(self, ids: Sequence[str]) -> int:
        """Delete the rows for ``ids``; returns how many were requested."""
        if not ids or self._db is None:
            return 0
        if self._table is None:
            table_names = await asyncio.to_thread(self._list_tables)
            if self._table_name not in table_names:
                return 0
            self._table = await asyncio.to_thread(self._db.open_table, self._table_name)

        batch_size = 500
        total_deleted = 0
        for i in range(0, len(ids), batch_size):
            chunk = ids[i : i + batch_size]
            quoted = ", ".join(self._quote(value) for value in chunk)
            await asyncio.to_thread(self._table.delete, f"id IN ({quoted})")
            total_deleted += len(chunk)
        return total_deleted

    async def maybe_create_index(self) -> bool:
        """Create an IVF-PQ index once the table exceeds 10,000 rows.

        Returns ``True`` when an index was created during this call.
        """
        table = await self._ensure_table()
        row_count = int(await asyncio.to_thread(table.count_rows))
        if row_count <= INDEX_THRESHOLD:
            return False
        try:
            existing = await asyncio.to_thread(table.list_indices)
            if existing:
                return False
        except Exception:
            LOGGER.debug("LanceDB list_indices is unavailable", exc_info=True)

        num_partitions = max(1, min(256, row_count // 1000))
        num_sub_vectors = 32 if self._vector_dimension >= 64 else 1
        try:
            await asyncio.to_thread(
                table.create_index,
                "vector",
                config=IvfPq(
                    distance_type="cosine",
                    num_partitions=num_partitions,
                    num_sub_vectors=num_sub_vectors,
                ),
            )
            return True
        except Exception:
            LOGGER.warning("Could not create LanceDB IVF-PQ index", exc_info=True)
            return False

    async def _ensure_table(self) -> Any:
        if self._db is None:
            raise RuntimeError("LanceDBClient is not connected")
        if self._table is not None:
            return self._table
        schema = self._schema or _build_track_vector_schema(self._vector_dimension)
        self._table = await asyncio.to_thread(
            self._db.create_table,
            self._table_name,
            schema=schema,
        )
        return self._table

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"
