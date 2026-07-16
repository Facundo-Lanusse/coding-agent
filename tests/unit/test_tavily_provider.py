from __future__ import annotations

from coding_agent.tools import TavilySearchBudgetError, TavilyWebSearchProvider


class FakeTavilyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def search(self, query: str, **kwargs: object) -> object:
        self.calls.append((query, kwargs))
        return {
            "results": [
                {
                    "title": "FastAPI dependencies",
                    "url": "https://fastapi.tiangolo.com/tutorial/dependencies/",
                    "content": "Use Depends to declare dependencies.",
                },
                {
                    "title": "Untrusted mirror",
                    "url": "https://example.invalid/copied-docs",
                    "content": "This result must be removed.",
                },
            ]
        }


def test_tavily_provider_uses_basic_search_and_filters_domains() -> None:
    client = FakeTavilyClient()
    provider = TavilyWebSearchProvider(client=client, max_searches=1)

    results = provider.search(
        "FastAPI dependencies",
        allowed_domains=("fastapi.tiangolo.com",),
        max_results=3,
    )

    assert len(results) == 1
    assert results[0].url.startswith("https://fastapi.tiangolo.com/")
    assert provider.searches == 1
    _, options = client.calls[0]
    assert options["search_depth"] == "basic"
    assert options["include_answer"] is False
    assert options["include_raw_content"] is False
    assert options["auto_parameters"] is False


def test_tavily_provider_enforces_hard_search_budget() -> None:
    provider = TavilyWebSearchProvider(client=FakeTavilyClient(), max_searches=1)
    provider.search(
        "FastAPI",
        allowed_domains=("fastapi.tiangolo.com",),
        max_results=1,
    )

    try:
        provider.search(
            "Pydantic",
            allowed_domains=("docs.pydantic.dev",),
            max_results=1,
        )
    except TavilySearchBudgetError as exc:
        assert "budget exhausted" in str(exc)
    else:
        raise AssertionError("Second Tavily search should have been blocked.")
