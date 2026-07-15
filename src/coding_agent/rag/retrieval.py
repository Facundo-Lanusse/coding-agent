"""Top-k retrieval with minimum relevance and explicit sufficiency."""

from __future__ import annotations

from collections.abc import Sequence

from coding_agent.observability import NoOpTracer, ObservationKind, Tracer
from coding_agent.rag.embeddings import EmbeddingProvider
from coding_agent.rag.models import CollectionSpec, RAGQueryResult
from coding_agent.rag.vector_store import VectorStore


class RAGRetriever:
    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        store: VectorStore,
        collection: CollectionSpec,
        top_k: int,
        minimum_score: float,
        tracer: Tracer | None = None,
    ) -> None:
        self._embeddings = embeddings
        self._store = store
        self._collection = collection
        self._top_k = top_k
        self._minimum_score = minimum_score
        self._tracer = tracer or NoOpTracer()

    def query(
        self,
        query: str,
        *,
        required_details: Sequence[str] = (),
    ) -> RAGQueryResult:
        with self._tracer.observe(
            "rag.retrieval",
            kind=ObservationKind.RETRIEVER,
            input={"query": query, "required_details": required_details},
            metadata={
                "collection": self._collection.name,
                "version": self._collection.version,
                "top_k": self._top_k,
                "threshold": self._minimum_score,
            },
        ) as observation:
            result = self._query(query, required_details=required_details)
            observation.update(
                output={
                    "sufficient": result.sufficient,
                    "reason": result.reason,
                    "documents": [
                        {
                            "source_id": hit.chunk.metadata.source_id,
                            "source": hit.chunk.metadata.path_or_url,
                            "section": hit.chunk.metadata.section,
                            "score": hit.score,
                        }
                        for hit in result.hits
                    ],
                }
            )
            return result

    def _query(
        self,
        query: str,
        *,
        required_details: Sequence[str] = (),
    ) -> RAGQueryResult:
        vector = self._embeddings.embed_query(query)
        hits = self._store.query(
            self._collection,
            vector,
            top_k=self._top_k,
            minimum_score=self._minimum_score,
        )
        if not hits:
            return RAGQueryResult(
                query=query,
                hits=(),
                sufficient=False,
                reason=(
                    f"No chunk reached the configured relevance threshold "
                    f"{self._minimum_score:.2f}."
                ),
            )
        combined = " ".join(hit.chunk.text.casefold() for hit in hits)
        missing = tuple(detail for detail in required_details if detail.casefold() not in combined)
        if missing:
            return RAGQueryResult(
                query=query,
                hits=hits,
                sufficient=False,
                reason=f"Relevant chunks do not cover required details: {', '.join(missing)}.",
            )
        return RAGQueryResult(
            query=query,
            hits=hits,
            sufficient=True,
            reason="RAG evidence meets threshold and requested detail coverage.",
        )
