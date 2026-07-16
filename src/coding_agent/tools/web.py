"""Provider-neutral web search tool; Tavily is composed only by the real demo."""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from coding_agent.tools.base import (
    PermissionKind,
    StructuredTool,
    ToolContext,
    ToolExecution,
    ToolExecutionFailure,
    ToolParameters,
    ToolPermissions,
    ToolRole,
)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    snippet: str = Field(min_length=1)


class WebSearchProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        allowed_domains: tuple[str, ...],
        max_results: int,
    ) -> tuple[SearchResult, ...]:
        """Search without exposing provider-specific types."""


class WebSearchUnavailableError(Exception):
    pass


class UnavailableWebSearchProvider:
    def search(
        self,
        query: str,
        *,
        allowed_domains: tuple[str, ...],
        max_results: int,
    ) -> tuple[SearchResult, ...]:
        raise WebSearchUnavailableError("No real web search provider is configured.")


class WebSearchParameters(ToolParameters):
    query: str = Field(min_length=1)
    allowed_domains: tuple[str, ...] = ()
    max_results: int = Field(default=5, ge=1, le=20)


class WebSearchTool(StructuredTool[WebSearchParameters]):
    def __init__(self, provider: WebSearchProvider | None = None) -> None:
        super().__init__(
            name="web_search",
            description=(
                "Search the web through an injected provider and return attributed results."
            ),
            parameters_model=WebSearchParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.WEB,
                allowed_roles=frozenset({ToolRole.RESEARCHER}),
            ),
        )
        self._provider = provider or UnavailableWebSearchProvider()

    def _execute(
        self,
        context: ToolContext,
        parameters: WebSearchParameters,
    ) -> ToolExecution:
        try:
            results = self._provider.search(
                parameters.query,
                allowed_domains=parameters.allowed_domains,
                max_results=parameters.max_results,
            )
        except WebSearchUnavailableError as exc:
            raise ToolExecutionFailure("web_search_unavailable", str(exc)) from exc
        except Exception as exc:
            raise ToolExecutionFailure(
                "web_search_failed",
                f"Web search provider failed ({type(exc).__name__}).",
                retryable=True,
            ) from exc

        payload = [result.model_dump(mode="json") for result in results]
        return ToolExecution(
            output=json.dumps(payload, ensure_ascii=False),
            metadata={"count": len(payload), "source": "web"},
        )
