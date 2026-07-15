"""Ingestion pipeline from normalized documents to persistent embeddings."""

from __future__ import annotations

from collections.abc import Sequence

from coding_agent.rag.chunking import TechnicalChunker
from coding_agent.rag.embeddings import EmbeddingProvider
from coding_agent.rag.loaders import LocalSourceLoader
from coding_agent.rag.models import (
    CollectionSpec,
    EmbeddedChunk,
    IngestionReport,
    SourceDocument,
)
from coding_agent.rag.vector_store import VectorStore


class RAGIngestor:
    def __init__(
        self,
        *,
        chunker: TechnicalChunker,
        embeddings: EmbeddingProvider,
        store: VectorStore,
        collection: CollectionSpec,
    ) -> None:
        self._chunker = chunker
        self._embeddings = embeddings
        self._store = store
        self._collection = collection

    def ingest_directory(
        self,
        directory: str,
        *,
        loader: LocalSourceLoader,
    ) -> IngestionReport:
        return self.ingest_documents(loader.load_directory(directory))

    def ingest_documents(self, documents: Sequence[SourceDocument]) -> IngestionReport:
        chunks = tuple(chunk for document in documents for chunk in self._chunker.chunk(document))
        if not chunks:
            return IngestionReport(
                documents=len(documents),
                chunks=0,
                inserted=0,
                skipped_duplicates=0,
            )
        vectors = self._embeddings.embed_documents(tuple(chunk.text for chunk in chunks))
        embedded = tuple(
            EmbeddedChunk(chunk=chunk, embedding=vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        )
        report = self._store.upsert(self._collection, embedded)
        return IngestionReport(
            documents=len(documents),
            chunks=len(chunks),
            inserted=report.inserted,
            skipped_duplicates=report.skipped_duplicates,
        )
