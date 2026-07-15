"""Evidence specialist with a RAG-first research port."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from coding_agent.agents.base import AgentBackend, BaseAgent
from coding_agent.harness.loop import ToolBinding
from coding_agent.rag.models import ResearchResponse
from coding_agent.state import AgentName
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
