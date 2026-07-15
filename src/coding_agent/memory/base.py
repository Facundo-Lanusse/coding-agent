"""Persistence port for project memory."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from coding_agent.memory.models import MemoryQuery, MemoryRecord, MemorySearchResult


class MemoryRepository(Protocol):
    def save(self, record: MemoryRecord) -> MemoryRecord:
        """Insert or update one explicitly classified record."""

    def get(self, *, project_id: str, record_id: str) -> MemoryRecord | None:
        """Get a record without crossing project boundaries."""

    def search(
        self,
        query: MemoryQuery,
        *,
        now: datetime | None = None,
    ) -> tuple[MemorySearchResult, ...]:
        """Retrieve category-filtered records ranked by lexical relevance."""

    def mark_stale(
        self,
        *,
        project_id: str,
        record_id: str,
        at: datetime | None = None,
    ) -> MemoryRecord:
        """Invalidate a record while preserving audit history."""

    def verify(
        self,
        *,
        project_id: str,
        record_id: str,
        verified_at: datetime,
        stale_after: datetime | None,
    ) -> MemoryRecord:
        """Refresh verification time and freshness deadline."""

    def close(self) -> None:
        """Release repository resources."""
