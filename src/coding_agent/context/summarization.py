"""Deterministic context summarization for production composition."""

from __future__ import annotations

from coding_agent.context.models import StructuredSummary, SummaryRequest


class ExtractiveSummaryProvider:
    """Bound old context without creating new facts or an extra LLM call."""

    def summarize(self, request: SummaryRequest) -> StructuredSummary:
        prefix = "Earlier context: "
        available = max(0, request.max_chars - len(prefix))
        fragments: list[str] = []
        used = 0
        for candidate in request.candidates:
            normalized = " ".join(candidate.content.split())
            separator = " | " if fragments else ""
            remaining = available - used - len(separator)
            if remaining <= 0:
                break
            fragment = normalized[:remaining]
            fragments.append(fragment)
            used += len(separator) + len(fragment)
        content = f"{prefix}{' | '.join(fragments)}"[: request.max_chars]
        if not content.strip() or content == prefix:
            content = "Earlier context omitted by the configured budget."[: request.max_chars]
        return StructuredSummary(
            content=content,
            preserved_decision_ids=request.protected_decision_ids,
            preserved_error_ids=request.protected_error_ids,
        )
