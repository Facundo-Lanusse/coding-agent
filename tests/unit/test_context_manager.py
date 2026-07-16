from datetime import UTC, datetime

from coding_agent.context import (
    ContextBudget,
    ContextCandidate,
    ContextKind,
    ContextManager,
    ExtractiveSummaryProvider,
    OmissionReason,
    StructuredSummary,
    SummaryProvider,
    SummaryRequest,
)


class FakeSummaryProvider(SummaryProvider):
    def __init__(self) -> None:
        self.requests: list[SummaryRequest] = []

    def summarize(self, request: SummaryRequest) -> StructuredSummary:
        self.requests.append(request)
        return StructuredSummary(
            content="Earlier sessions investigated routing and dependency versions.",
            preserved_decision_ids=request.protected_decision_ids,
            preserved_error_ids=request.protected_error_ids,
        )


def candidate(
    item_id: str,
    kind: ContextKind,
    content: str,
    *,
    relevance: float = 0.5,
) -> ContextCandidate:
    return ContextCandidate(
        item_id=item_id,
        kind=kind,
        content=content,
        source_reference=f"fixture:{item_id}",
        relevance=relevance,
        created_at=datetime(2026, 7, 14, tzinfo=UTC),
    )


def test_summary_preserves_decisions_and_open_errors() -> None:
    provider = FakeSummaryProvider()
    manager = ContextManager(
        budget=ContextBudget(max_chars=260, max_items=4, summary_max_chars=80),
        summary_provider=provider,
    )
    decision = candidate(
        "decision-1",
        ContextKind.DECISION,
        "Decision: keep the public endpoint backwards compatible.",
    )
    error = candidate(
        "error-1",
        ContextKind.OPEN_ERROR,
        "Open error: health check currently returns 404.",
    )
    old_history = candidate(
        "history-1",
        ContextKind.HISTORY,
        "routing " * 80,
        relevance=0.9,
    )

    selection = manager.build(
        query="routing health endpoint",
        candidates=(decision, error, old_history),
    )

    assert decision in selection.included
    assert error in selection.included
    assert selection.summary is not None
    assert selection.summary.preserved_decision_ids == ("decision-1",)
    assert selection.summary.preserved_error_ids == ("error-1",)
    assert selection.omitted[0].reason is OmissionReason.SUMMARIZED
    assert provider.requests[0].candidates == (old_history,)


def test_context_budget_is_respected_and_manifest_explains_omissions() -> None:
    manager = ContextManager(budget=ContextBudget(max_chars=90, max_items=2, minimum_relevance=0.2))
    candidates = (
        candidate("decision", ContextKind.DECISION, "Keep API compatibility."),
        candidate("useful", ContextKind.EVIDENCE, "FastAPI endpoint returns JSON.", relevance=0.9),
        candidate("large", ContextKind.EVIDENCE, "FastAPI " * 30, relevance=0.8),
        candidate("irrelevant", ContextKind.EVIDENCE, "CSS color palette.", relevance=0.0),
    )

    selection = manager.build(query="FastAPI endpoint", candidates=candidates)

    assert selection.used_chars <= selection.budget.max_chars
    assert len(selection.included) <= selection.budget.max_items
    omissions = {item.candidate.item_id: item.reason for item in selection.omitted}
    assert omissions["large"] is OmissionReason.BUDGET
    assert omissions["irrelevant"] is OmissionReason.IRRELEVANT
    assert [item.item_id for item in selection.included] == ["decision", "useful"]


def test_extractive_summary_is_bounded_and_does_not_add_facts() -> None:
    provider = ExtractiveSummaryProvider()
    request = SummaryRequest(
        candidates=(
            candidate("old", ContextKind.HISTORY, "FastAPI routers delegate to services."),
        ),
        protected_decision_ids=("decision-1",),
        protected_error_ids=("error-1",),
        max_chars=60,
    )

    summary = provider.summarize(request)

    assert len(summary.content) <= 60
    assert "FastAPI routers" in summary.content
    assert summary.preserved_decision_ids == ("decision-1",)
    assert summary.preserved_error_ids == ("error-1",)
