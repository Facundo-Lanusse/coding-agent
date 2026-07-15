"""Persistent, project-scoped memory API."""

from coding_agent.memory.base import MemoryRepository
from coding_agent.memory.models import (
    MemoryCategory,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    MemorySourceType,
)
from coding_agent.memory.sqlite import (
    MemoryRecordNotFoundError,
    MemoryRepositoryError,
    SQLiteMemoryRepository,
)

__all__ = [
    "MemoryCategory",
    "MemoryKind",
    "MemoryQuery",
    "MemoryRecord",
    "MemoryRecordNotFoundError",
    "MemoryRepository",
    "MemoryRepositoryError",
    "MemorySearchResult",
    "MemorySourceType",
    "SQLiteMemoryRepository",
]
