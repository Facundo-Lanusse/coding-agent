"""RAG-first research with one attributed web fallback."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Protocol
from urllib.parse import urlparse

from coding_agent.observability import NoOpTracer, Tracer
from coding_agent.rag.models import (
    DocumentChunk,
    RAGQueryResult,
    ResearchResponse,
    ResearchStatus,
)
from coding_agent.state import Evidence, EvidenceGroup, EvidenceSource
from coding_agent.tools.web import WebSearchProvider


class RAGProvider(Protocol):
    def query(
        self,
        query: str,
        *,
        required_details: Sequence[str] = (),
    ) -> RAGQueryResult: ...


class ResearchService:
    def __init__(
        self,
        *,
        retriever: RAGProvider,
        web_provider: WebSearchProvider,
        web_fallback: bool,
        trusted_domains: tuple[str, ...],
        max_web_results: int = 3,
        tracer: Tracer | None = None,
    ) -> None:
        self._retriever = retriever
        self._web = web_provider
        self._web_fallback = web_fallback
        self._domains = trusted_domains
        self._max_web_results = max_web_results
        self._tracer = tracer or NoOpTracer()

    def research(
        self,
        query: str,
        *,
        required_details: Sequence[str] = (),
    ) -> ResearchResponse:
        rag_result = self._retriever.query(query, required_details=required_details)
        evidence = tuple(_rag_evidence(hit.chunk, hit.score) for hit in rag_result.hits)
        used_web = False
        trusted_web_evidence: tuple[Evidence, ...] = ()
        if not rag_result.sufficient and self._web_fallback:
            with self._tracer.observe(
                "web.fallback",
                input={"query": query},
                metadata={"allowed_domains": self._domains, "rag_reason": rag_result.reason},
            ) as web_observation:
                web_results = self._web.search(
                    query,
                    allowed_domains=self._domains,
                    max_results=self._max_web_results,
                )
                used_web = True
                trusted_web_evidence = tuple(
                    _web_evidence(item.title, item.url, item.snippet)
                    for item in web_results
                    if _trusted_url(item.url, self._domains)
                )
                evidence = (*evidence, *trusted_web_evidence)
                web_observation.update(
                    output={
                        "sources": [item.reference for item in trusted_web_evidence],
                        "result_count": len(trusted_web_evidence),
                    }
                )

        can_answer = rag_result.sufficient or bool(trusted_web_evidence)
        if not can_answer:
            explanation = (
                "No hay evidencia suficiente en el RAG ni en las fuentes web permitidas. "
                "No se generó una respuesta técnica; hace falta documentación "
                "o una fuente autorizada."
            )
            status = ResearchStatus.NO_EVIDENCE
        else:
            explanation = (
                "La respuesta se limita a los fragmentos recuperados con provenance explícita."
            )
            status = ResearchStatus.ANSWERED
        groups = tuple(
            EvidenceGroup(
                source=source,
                items=tuple(item for item in evidence if item.source is source),
            )
            for source in EvidenceSource
        )
        return ResearchResponse(
            query=query,
            status=status,
            explanation=explanation,
            evidence=evidence,
            evidence_groups=groups,
            used_web=used_web,
            rag_reason=rag_result.reason,
        )


def _rag_evidence(chunk: DocumentChunk, score: float) -> Evidence:
    metadata = chunk.metadata
    return Evidence(
        evidence_id=f"rag-{chunk.chunk_id}",
        source=EvidenceSource.RAG,
        reference=metadata.path_or_url,
        locator=f"{metadata.title} > {metadata.section} > chunk {metadata.chunk_index}",
        content=chunk.text,
        confidence=max(0.0, min(1.0, score)),
    )


def _web_evidence(title: str, url: str, snippet: str) -> Evidence:
    identifier = hashlib.sha256(f"{url}:{snippet}".encode()).hexdigest()
    return Evidence(
        evidence_id=f"web-{identifier}",
        source=EvidenceSource.WEB,
        reference=url,
        locator=title,
        content=snippet,
        confidence=0.7,
    )


def _trusted_url(url: str, domains: tuple[str, ...]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and any(
        host == domain.casefold() or host.endswith(f".{domain.casefold()}") for domain in domains
    )
