"""Models for inspectable, budgeted context assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from coding_agent.models import FrozenModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class ContextKind(StrEnum):
    DECISION = "decision"
    OPEN_ERROR = "open_error"
    EVIDENCE = "evidence"
    MEMORY = "memory"
    HISTORY = "history"
    SESSION_SUMMARY = "session_summary"
    GENERATED_SUMMARY = "generated_summary"


class OmissionReason(StrEnum):
    IRRELEVANT = "irrelevant"
    BUDGET = "budget"
    SUMMARIZED = "summarized"


class ContextCandidate(FrozenModel):
    item_id: str = Field(min_length=1)
    kind: ContextKind
    content: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)


class ContextBudget(FrozenModel):
    max_chars: int = Field(gt=0)
    max_items: int = Field(gt=0)
    summary_max_chars: int = Field(default=1_000, gt=0)
    minimum_relevance: float = Field(default=0.1, ge=0.0, le=1.0)


class ContextOmission(FrozenModel):
    candidate: ContextCandidate
    reason: OmissionReason


class SummaryRequest(FrozenModel):
    candidates: tuple[ContextCandidate, ...]
    protected_decision_ids: tuple[str, ...]
    protected_error_ids: tuple[str, ...]
    max_chars: int = Field(gt=0)


class StructuredSummary(FrozenModel):
    content: str = Field(min_length=1)
    preserved_decision_ids: tuple[str, ...] = ()
    preserved_error_ids: tuple[str, ...] = ()


class ContextSelection(FrozenModel):
    included: tuple[ContextCandidate, ...]
    omitted: tuple[ContextOmission, ...]
    summary: StructuredSummary | None = None
    used_chars: int = Field(ge=0)
    budget: ContextBudget


class ContextBudgetError(Exception):
    code = "context_budget_error"


class SummaryContractError(Exception):
    code = "summary_contract_error"
