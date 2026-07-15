"""Provider-neutral models for ingestion, retrieval, and attributed research."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from coding_agent.models import FrozenModel
from coding_agent.state import Evidence, EvidenceGroup


def utc_now() -> datetime:
    return datetime.now(UTC)


class RAGSourceType(StrEnum):
    MARKDOWN = "markdown"
    TEXT = "text"
    CODE = "code"
    README = "readme"
    OFFICIAL_URL = "official_url"
    REFERENCE_PROJECT = "reference_project"


class SourceDocument(FrozenModel):
    source_id: str = Field(min_length=1)
    source_type: RAGSourceType
    path_or_url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    ecosystem: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content: str = Field(min_length=1)
    checksum: str = Field(min_length=64, max_length=64)
    content_type: str = Field(min_length=1)
    ingested_at: datetime = Field(default_factory=utc_now)


class ChunkMetadata(FrozenModel):
    source_id: str = Field(min_length=1)
    source_type: RAGSourceType
    path_or_url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    section: str = Field(min_length=1)
    ecosystem: str = Field(min_length=1)
    version: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    checksum: str = Field(min_length=64, max_length=64)
    ingested_at: datetime
    content_type: str = Field(min_length=1)


class DocumentChunk(FrozenModel):
    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    token_count: int = Field(gt=0)
    metadata: ChunkMetadata


class EmbeddedChunk(FrozenModel):
    chunk: DocumentChunk
    embedding: tuple[float, ...]


class CollectionSpec(FrozenModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    dimension: int = Field(gt=0)


class UpsertReport(FrozenModel):
    inserted: int = Field(ge=0)
    skipped_duplicates: int = Field(ge=0)


class IngestionReport(FrozenModel):
    documents: int = Field(ge=0)
    chunks: int = Field(ge=0)
    inserted: int = Field(ge=0)
    skipped_duplicates: int = Field(ge=0)


class RetrievalHit(FrozenModel):
    chunk: DocumentChunk
    score: float = Field(ge=-1.0, le=1.0)


class RAGQueryResult(FrozenModel):
    query: str = Field(min_length=1)
    hits: tuple[RetrievalHit, ...]
    sufficient: bool
    reason: str = Field(min_length=1)


class ResearchStatus(StrEnum):
    ANSWERED = "answered"
    NO_EVIDENCE = "no_evidence"


class ResearchResponse(FrozenModel):
    query: str = Field(min_length=1)
    status: ResearchStatus
    explanation: str = Field(min_length=1)
    evidence: tuple[Evidence, ...]
    evidence_groups: tuple[EvidenceGroup, ...]
    used_web: bool
    rag_reason: str = Field(min_length=1)

    def render(self) -> str:
        if not self.evidence:
            return self.explanation
        fragments = "\n\n".join(
            f"[{item.source.value}] {item.reference}\n{item.content}" for item in self.evidence
        )
        return f"{self.explanation}\n\nRecovered evidence:\n{fragments}"
