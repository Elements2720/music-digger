"""Local disk-backed adapters."""

from .lancedb_client import CLAP_DIMENSION, LanceDBClient, VectorMatch
from .sqlite_client import SQLiteClient

__all__ = ["CLAP_DIMENSION", "LanceDBClient", "SQLiteClient", "VectorMatch"]
