"""Relevant context selection with explicit inclusion and omission manifests."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

from coding_agent.context.models import (
    ContextBudget,
    ContextBudgetError,
    ContextCandidate,
    ContextKind,
    ContextOmission,
    ContextSelection,
    OmissionReason,
    StructuredSummary,
    SummaryContractError,
    SummaryRequest,
)

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_./-]+")
_PROTECTED_KINDS = frozenset({ContextKind.DECISION, ContextKind.OPEN_ERROR})
_SUMMARIZABLE_KINDS = frozenset(
    {ContextKind.HISTORY, ContextKind.MEMORY, ContextKind.SESSION_SUMMARY}
)


class SummaryProvider(Protocol):
    def summarize(self, request: SummaryRequest) -> StructuredSummary:
        """Summarize old context while reporting protected facts retained."""


class ContextManager:
    """Build a bounded envelope instead of forwarding full history or repository."""

    def __init__(
        self,
        *,
        budget: ContextBudget,
        summary_provider: SummaryProvider | None = None,
    ) -> None:
        self._budget = budget
        self._summary_provider = summary_provider

    def build(
        self,
        *,
        query: str,
        candidates: Iterable[ContextCandidate],
    ) -> ContextSelection:
        all_candidates = tuple(candidates)
        protected = tuple(item for item in all_candidates if item.kind in _PROTECTED_KINDS)
        optional = tuple(item for item in all_candidates if item.kind not in _PROTECTED_KINDS)
        protected_chars = sum(len(item.content) for item in protected)
        if len(protected) > self._budget.max_items or protected_chars > self._budget.max_chars:
            raise ContextBudgetError(
                "Context budget cannot preserve all decisions and open errors."
            )

        included = list(protected)
        used_chars = protected_chars
        omitted: list[ContextOmission] = []
        scored = sorted(
            ((_score(query, item), item) for item in optional),
            key=lambda pair: (pair[0], pair[1].created_at),
            reverse=True,
        )
        budget_omitted: list[ContextCandidate] = []
        for score, candidate in scored:
            if score < self._budget.minimum_relevance:
                omitted.append(
                    ContextOmission(candidate=candidate, reason=OmissionReason.IRRELEVANT)
                )
                continue
            if (
                len(included) >= self._budget.max_items
                or used_chars + len(candidate.content) > self._budget.max_chars
            ):
                budget_omitted.append(candidate)
                continue
            included.append(candidate)
            used_chars += len(candidate.content)

        summary: StructuredSummary | None = None
        summarizable = tuple(item for item in budget_omitted if item.kind in _SUMMARIZABLE_KINDS)
        remaining_chars = self._budget.max_chars - used_chars
        if (
            summarizable
            and self._summary_provider is not None
            and len(included) < self._budget.max_items
            and remaining_chars > 0
        ):
            summary_limit = min(remaining_chars, self._budget.summary_max_chars)
            request = SummaryRequest(
                candidates=summarizable,
                protected_decision_ids=tuple(
                    item.item_id for item in protected if item.kind is ContextKind.DECISION
                ),
                protected_error_ids=tuple(
                    item.item_id for item in protected if item.kind is ContextKind.OPEN_ERROR
                ),
                max_chars=summary_limit,
            )
            summary = self._summary_provider.summarize(request)
            self._validate_summary(summary, request)
            if len(summary.content) <= summary_limit:
                included.append(
                    ContextCandidate(
                        item_id="generated-summary",
                        kind=ContextKind.GENERATED_SUMMARY,
                        content=summary.content,
                        source_reference="SummaryProvider",
                        relevance=1.0,
                    )
                )
                used_chars += len(summary.content)
                summarized_ids = {item.item_id for item in summarizable}
                omitted.extend(
                    ContextOmission(
                        candidate=item,
                        reason=(
                            OmissionReason.SUMMARIZED
                            if item.item_id in summarized_ids
                            else OmissionReason.BUDGET
                        ),
                    )
                    for item in budget_omitted
                )
            else:
                summary = None
                omitted.extend(
                    ContextOmission(candidate=item, reason=OmissionReason.BUDGET)
                    for item in budget_omitted
                )
        else:
            omitted.extend(
                ContextOmission(candidate=item, reason=OmissionReason.BUDGET)
                for item in budget_omitted
            )

        return ContextSelection(
            included=tuple(included),
            omitted=tuple(omitted),
            summary=summary,
            used_chars=used_chars,
            budget=self._budget,
        )

    @staticmethod
    def _validate_summary(summary: StructuredSummary, request: SummaryRequest) -> None:
        missing_decisions = set(request.protected_decision_ids).difference(
            summary.preserved_decision_ids
        )
        missing_errors = set(request.protected_error_ids).difference(summary.preserved_error_ids)
        if missing_decisions or missing_errors:
            raise SummaryContractError(
                "Summary provider omitted protected decisions or open errors."
            )


def _score(query: str, candidate: ContextCandidate) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return candidate.relevance
    candidate_tokens = _tokens(candidate.content)
    lexical = len(query_tokens.intersection(candidate_tokens)) / len(query_tokens)
    return max(candidate.relevance, lexical)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN_PATTERN.findall(value))
