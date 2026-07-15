"""Persistent technical RAG for Python and FastAPI repositories."""

from coding_agent.rag.chunking import TechnicalChunker, approximate_token_count, normalize_text
from coding_agent.rag.embeddings import (
    DeterministicFakeEmbeddings,
    EmbeddingError,
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from coding_agent.rag.ingestion import RAGIngestor
from coding_agent.rag.loaders import LocalSourceLoader, OfficialURLLoader, SourceLoadError
from coding_agent.rag.models import (
    ChunkMetadata,
    CollectionSpec,
    DocumentChunk,
    EmbeddedChunk,
    IngestionReport,
    RAGQueryResult,
    RAGSourceType,
    ResearchResponse,
    ResearchStatus,
    RetrievalHit,
    SourceDocument,
    UpsertReport,
)
from coding_agent.rag.research import ResearchService
from coding_agent.rag.retrieval import RAGRetriever
from coding_agent.rag.vector_store import SQLiteVectorStore, VectorStore, VectorStoreError

__all__ = [
    "ChunkMetadata",
    "CollectionSpec",
    "DeterministicFakeEmbeddings",
    "DocumentChunk",
    "EmbeddedChunk",
    "EmbeddingError",
    "EmbeddingProvider",
    "IngestionReport",
    "LocalSourceLoader",
    "OfficialURLLoader",
    "OpenAIEmbeddingProvider",
    "RAGIngestor",
    "RAGQueryResult",
    "RAGRetriever",
    "RAGSourceType",
    "ResearchResponse",
    "ResearchService",
    "ResearchStatus",
    "RetrievalHit",
    "SQLiteVectorStore",
    "SourceDocument",
    "SourceLoadError",
    "TechnicalChunker",
    "UpsertReport",
    "VectorStore",
    "VectorStoreError",
    "approximate_token_count",
    "normalize_text",
]
