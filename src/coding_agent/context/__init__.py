"""Context budgeting, summarization, fingerprints, and progress detection."""

from coding_agent.context.fingerprints import FingerprintFactory
from coding_agent.context.manager import ContextManager, SummaryProvider
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
from coding_agent.context.progress import (
    NoProgressDetector,
    NoProgressReason,
    NoProgressReport,
    NoProgressSignal,
    ProgressStrategy,
)
from coding_agent.context.summarization import ExtractiveSummaryProvider

__all__ = [
    "ContextBudget",
    "ContextBudgetError",
    "ContextCandidate",
    "ContextKind",
    "ContextManager",
    "ContextOmission",
    "ContextSelection",
    "ExtractiveSummaryProvider",
    "FingerprintFactory",
    "NoProgressDetector",
    "NoProgressReason",
    "NoProgressReport",
    "NoProgressSignal",
    "OmissionReason",
    "ProgressStrategy",
    "StructuredSummary",
    "SummaryContractError",
    "SummaryProvider",
    "SummaryRequest",
]
