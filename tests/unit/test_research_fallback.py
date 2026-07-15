import hashlib
from collections.abc import Sequence

from coding_agent.agents import AgentContext, ResearcherAgent, ScopedToolbox
from coding_agent.rag import (
    RAGQueryResult,
    RAGSourceType,
    ResearchService,
    ResearchStatus,
    RetrievalHit,
    SourceDocument,
    TechnicalChunker,
)
from coding_agent.state import AgentName, AgentResult, EvidenceSource
from coding_agent.tools.web import SearchResult


class FakeRAG:
    def __init__(self, result: RAGQueryResult, order: list[str]) -> None:
        self.result = result
        self.order = order

    def query(
        self,
        query: str,
        *,
        required_details: Sequence[str] = (),
    ) -> RAGQueryResult:
        del query, required_details
        self.order.append("rag")
        return self.result


class NeverAgentBackend:
    def run(
        self,
        *,
        agent: AgentName,
        responsibility: str,
        context: AgentContext,
        tools: ScopedToolbox,
    ) -> AgentResult:
        del agent, responsibility, context, tools
        raise AssertionError("Research port must not invoke the LLM backend")


class FakeWeb:
    def __init__(self, results: tuple[SearchResult, ...], order: list[str]) -> None:
        self.results = results
        self.order = order
        self.calls = 0
        self.domains: tuple[str, ...] = ()

    def search(
        self,
        query: str,
        *,
        allowed_domains: tuple[str, ...],
        max_results: int,
    ) -> tuple[SearchResult, ...]:
        del query, max_results
        self.calls += 1
        self.order.append("web")
        self.domains = allowed_domains
        return self.results


def rag_result(*, sufficient: bool, hits: bool = True) -> RAGQueryResult:
    content = "# Dependencies\n\nFastAPI declares dependencies with Depends and Annotated."
    source = SourceDocument(
        source_id="fastapi-deps",
        source_type=RAGSourceType.OFFICIAL_URL,
        path_or_url="https://fastapi.tiangolo.com/tutorial/dependencies/",
        title="Dependencies",
        ecosystem="FastAPI",
        version="latest",
        content=content,
        checksum=hashlib.sha256(content.encode()).hexdigest(),
        content_type="text/markdown",
    )
    chunk = TechnicalChunker(max_tokens=100, overlap_tokens=10).chunk(source)[0]
    return RAGQueryResult(
        query="How are dependencies declared?",
        hits=(RetrievalHit(chunk=chunk, score=0.92),) if hits else (),
        sufficient=sufficient,
        reason="sufficient" if sufficient else "threshold or detail gap",
    )


def test_sufficient_rag_avoids_web_and_preserves_provenance() -> None:
    order: list[str] = []
    web = FakeWeb((), order)
    service = ResearchService(
        retriever=FakeRAG(rag_result(sufficient=True), order),
        web_provider=web,
        web_fallback=True,
        trusted_domains=("fastapi.tiangolo.com",),
    )

    response = service.research("How are dependencies declared?")

    assert order == ["rag"]
    assert web.calls == 0
    assert response.status is ResearchStatus.ANSWERED
    assert response.evidence[0].source is EvidenceSource.RAG
    assert "fastapi.tiangolo.com" in response.evidence[0].reference
    assert "Recovered evidence" in response.render()


def test_researcher_agent_exposes_rag_first_research_port() -> None:
    order: list[str] = []
    service = ResearchService(
        retriever=FakeRAG(rag_result(sufficient=True), order),
        web_provider=FakeWeb((), order),
        web_fallback=True,
        trusted_domains=("fastapi.tiangolo.com",),
    )
    researcher = ResearcherAgent(NeverAgentBackend(), research_provider=service)

    response = researcher.research("How are dependencies declared?")

    assert response.status is ResearchStatus.ANSWERED
    assert order == ["rag"]


def test_insufficient_threshold_uses_one_trusted_web_fallback() -> None:
    order: list[str] = []
    web = FakeWeb(
        (
            SearchResult(
                title="Official dependencies",
                url="https://fastapi.tiangolo.com/tutorial/dependencies/",
                snippet="Depends receives a callable dependency.",
            ),
        ),
        order,
    )
    service = ResearchService(
        retriever=FakeRAG(rag_result(sufficient=False, hits=False), order),
        web_provider=web,
        web_fallback=True,
        trusted_domains=("fastapi.tiangolo.com", "docs.pydantic.dev"),
    )

    response = service.research("How are dependencies declared?")

    assert order == ["rag", "web"]
    assert web.calls == 1
    assert web.domains[0] == "fastapi.tiangolo.com"
    assert response.used_web
    assert response.evidence[0].source is EvidenceSource.WEB


def test_evidence_types_remain_separate_and_inferences_are_not_fabricated() -> None:
    order: list[str] = []
    web = FakeWeb(
        (
            SearchResult(
                title="Pydantic models",
                url="https://docs.pydantic.dev/latest/concepts/models/",
                snippet="Models inherit from BaseModel.",
            ),
        ),
        order,
    )
    response = ResearchService(
        retriever=FakeRAG(rag_result(sufficient=False, hits=True), order),
        web_provider=web,
        web_fallback=True,
        trusted_domains=("docs.pydantic.dev",),
    ).research("models", required_details=("serialization",))

    groups = {group.source: group.items for group in response.evidence_groups}
    assert groups[EvidenceSource.RAG][0].source is EvidenceSource.RAG
    assert groups[EvidenceSource.WEB][0].source is EvidenceSource.WEB
    assert groups[EvidenceSource.INFERENCE] == ()


def test_query_without_any_evidence_explains_gap_instead_of_inventing() -> None:
    order: list[str] = []
    response = ResearchService(
        retriever=FakeRAG(rag_result(sufficient=False, hits=False), order),
        web_provider=FakeWeb((), order),
        web_fallback=True,
        trusted_domains=("fastapi.tiangolo.com",),
    ).research("Unknown behavior")

    assert response.status is ResearchStatus.NO_EVIDENCE
    assert response.evidence == ()
    assert "No se generó una respuesta técnica" in response.render()
