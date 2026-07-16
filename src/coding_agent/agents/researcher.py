"""Evidence specialist with a RAG-first research port."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from coding_agent.agents.base import AgentBackend, AgentContext, BaseAgent
from coding_agent.harness.loop import ToolBinding
from coding_agent.rag.models import ResearchResponse
from coding_agent.state import AgentName, AgentResult, AgentResultStatus
from coding_agent.tools.base import ToolRole


class ResearchProvider(Protocol):
    def research(
        self,
        query: str,
        *,
        required_details: Sequence[str] = (),
    ) -> ResearchResponse: ...


class ResearchUnavailableError(Exception):
    code = "research_provider_unavailable"


class ResearcherAgent(BaseAgent):
    name = AgentName.RESEARCHER
    role = ToolRole.RESEARCHER
    responsibility = (
        "Retrieve attributable technical evidence and report gaps; never write production files."
    )
    allowed_tool_names = frozenset({"web_search"})

    def __init__(
        self,
        backend: AgentBackend,
        *,
        tools: Iterable[ToolBinding] = (),
        research_provider: ResearchProvider | None = None,
    ) -> None:
        super().__init__(backend, tools=tools)
        self._research_provider = research_provider

    def research(
        self,
        query: str,
        *,
        required_details: Sequence[str] = (),
    ) -> ResearchResponse:
        if self._research_provider is None:
            raise ResearchUnavailableError("No RAG research provider is configured.")
        return self._research_provider.research(query, required_details=required_details)

    def run(self, context: AgentContext) -> AgentResult:
        """Retrieve RAG/web evidence before asking the backend to synthesize it."""

        if self._research_provider is None:
            return super().run(context)
        response = self.research(
            context.normalized_objective,
            required_details=context.acceptance_criteria,
        )
        if not response.evidence:
            return AgentResult(
                agent=self.name,
                status=AgentResultStatus.NO_EVIDENCE,
                summary=response.explanation,
                observations=(response.rag_reason,),
            )
        augmented = context.model_copy(
            update={
                "evidence": (*context.evidence, *response.evidence),
                "observations": (*context.observations, response.rag_reason),
            }
        )
        result = super().run(augmented)
        existing = {item.evidence_id for item in result.evidence}
        recovered = tuple(item for item in response.evidence if item.evidence_id not in existing)
        return result.model_copy(
            update={
                "evidence": (*recovered, *result.evidence),
                "observations": (*result.observations, response.rag_reason),
            }
        )
