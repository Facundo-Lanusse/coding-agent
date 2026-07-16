"""Cost-bounded Tavily implementation of the web-search port."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast
from urllib.parse import urlparse

from coding_agent.tools.web import SearchResult, WebSearchUnavailableError


class TavilyClientProtocol(Protocol):
    def search(self, query: str, **kwargs: object) -> object: ...


class TavilyConfigurationError(WebSearchUnavailableError):
    code = "tavily_configuration_error"


class TavilySearchBudgetError(WebSearchUnavailableError):
    code = "tavily_search_budget_exhausted"


class TavilyWebSearchProvider:
    """Use basic Tavily searches only, with a hard per-process request budget."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: TavilyClientProtocol | None = None,
        max_searches: int = 1,
    ) -> None:
        if max_searches < 1:
            raise TavilyConfigurationError("Tavily max_searches must be positive.")
        if client is None:
            if not api_key:
                raise TavilyConfigurationError("TAVILY_API_KEY is required.")
            try:
                from tavily import TavilyClient  # type: ignore[import-untyped]
            except ImportError as exc:
                raise TavilyConfigurationError(
                    "The tavily-python package is required for real web search."
                ) from exc
            client = cast(TavilyClientProtocol, TavilyClient(api_key=api_key))
        self._client = client
        self._max_searches = max_searches
        self._searches = 0

    @property
    def searches(self) -> int:
        return self._searches

    def search(
        self,
        query: str,
        *,
        allowed_domains: tuple[str, ...],
        max_results: int,
    ) -> tuple[SearchResult, ...]:
        if self._searches >= self._max_searches:
            raise TavilySearchBudgetError(
                f"Tavily search budget exhausted ({self._max_searches})."
            )
        if not query.strip() or not allowed_domains:
            raise TavilyConfigurationError(
                "Tavily searches require a query and an official-domain allowlist."
            )
        self._searches += 1
        response = self._client.search(
            query,
            search_depth="basic",
            max_results=max_results,
            include_domains=list(allowed_domains),
            include_answer=False,
            include_raw_content=False,
            auto_parameters=False,
        )
        if not isinstance(response, Mapping):
            raise TavilyConfigurationError("Tavily returned an invalid response.")
        raw_results = response.get("results", ())
        if not isinstance(raw_results, list | tuple):
            raise TavilyConfigurationError("Tavily results must be a sequence.")
        results: list[SearchResult] = []
        for raw in raw_results:
            if not isinstance(raw, Mapping):
                continue
            title = raw.get("title")
            url = raw.get("url")
            content = raw.get("content")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (title, url, content)
            ):
                continue
            assert isinstance(title, str) and isinstance(url, str) and isinstance(content, str)
            if not _allowed_url(url, allowed_domains):
                continue
            results.append(SearchResult(title=title, url=url, snippet=content))
        return tuple(results[:max_results])


def _allowed_url(url: str, domains: tuple[str, ...]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and any(
        host == domain.casefold() or host.endswith(f".{domain.casefold()}")
        for domain in domains
    )
