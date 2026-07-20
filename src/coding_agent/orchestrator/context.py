"""Context slicing and final evidence grouping for orchestration."""

from __future__ import annotations

from collections.abc import Mapping

from coding_agent.agents import AgentContext, PriorAgentSummary
from coding_agent.context import ContextCandidate, ContextKind, ContextManager
from coding_agent.state import (
    AgentName,
    AgentResult,
    Evidence,
    EvidenceGroup,
    EvidenceSource,
    TaskFinalResult,
    TaskState,
)

_VISIBLE_AGENTS: Mapping[AgentName, frozenset[AgentName]] = {
    AgentName.EXPLORER: frozenset(),
    AgentName.RESEARCHER: frozenset({AgentName.EXPLORER}),
    AgentName.IMPLEMENTER: frozenset({AgentName.EXPLORER, AgentName.RESEARCHER}),
    AgentName.TESTER: frozenset({AgentName.IMPLEMENTER}),
    AgentName.REVIEWER: frozenset(
        {AgentName.EXPLORER, AgentName.RESEARCHER, AgentName.IMPLEMENTER, AgentName.TESTER}
    ),
}


def build_agent_context(
    state: TaskState,
    agent_name: AgentName,
    manager: ContextManager | None,
) -> AgentContext:
    prior = tuple(
        PriorAgentSummary(agent=result.agent, summary=result.summary)
        for result in state.agent_results
        if result.agent in _VISIBLE_AGENTS[agent_name]
    )
    evidence = () if agent_name is AgentName.EXPLORER else state.evidence
    included: tuple[str, ...] = ()
    omitted: tuple[str, ...] = ()
    selected_context: tuple[str, ...] = ()
    if manager is not None and agent_name is not AgentName.EXPLORER:
        selection = manager.build(
            query=state.normalized_objective,
            candidates=_context_candidates(state, evidence),
        )
        included_ids = {item.item_id for item in selection.included}
        evidence = tuple(
            item for item in evidence if f"evidence:{item.evidence_id}" in included_ids
        )
        selected_context = tuple(
            item.content
            for item in selection.included
            if not item.item_id.startswith("evidence:")
        )
        included = tuple(item.item_id for item in selection.included)
        omitted = tuple(item.candidate.item_id for item in selection.omitted)
    return AgentContext(
        task_id=state.request.task_id,
        original_request=state.request.original_request,
        normalized_objective=state.normalized_objective,
        plan=state.plan,
        acceptance_criteria=state.request.acceptance_criteria,
        prior_results=prior,
        evidence=evidence,
        relevant_files=tuple(str(path) for path in state.files_read),
        file_changes=(
            state.files_modified
            if agent_name in {AgentName.TESTER, AgentName.REVIEWER}
            else ()
        ),
        checks=(
            tuple(check for result in state.agent_results for check in result.checks)
            if agent_name is AgentName.REVIEWER
            else ()
        ),
        observations=(
            *(state.observations if agent_name is AgentName.REVIEWER else ()),
            *selected_context,
        ),
        errors=(
            state.errors if agent_name in {AgentName.TESTER, AgentName.REVIEWER} else ()
        ),
        context_included=included,
        context_omitted=omitted,
    )


def build_final_result(state: TaskState, reviewer: AgentResult) -> TaskFinalResult:
    groups = tuple(
        EvidenceGroup(
            source=source,
            items=tuple(item for item in state.evidence if item.source is source),
        )
        for source in EvidenceSource
    )
    return TaskFinalResult(
        summary=reviewer.summary,
        evidence=groups,
        reviewer_accepted=reviewer.criteria_met is True,
    )


def _context_candidates(
    state: TaskState,
    evidence: tuple[Evidence, ...],
) -> tuple[ContextCandidate, ...]:
    candidates = [
        ContextCandidate(
            item_id=f"evidence:{item.evidence_id}",
            kind=(
                ContextKind.MEMORY
                if item.source is EvidenceSource.MEMORY
                else ContextKind.EVIDENCE
            ),
            content=item.content,
            source_reference=item.reference,
            relevance=item.confidence,
            created_at=item.observed_at,
        )
        for item in evidence
    ]
    candidates.extend(
        ContextCandidate(
            item_id=f"decision:{item.decision_id}",
            kind=ContextKind.DECISION,
            content=item.reason,
            source_reference=item.kind,
            relevance=1.0,
            created_at=item.made_at,
        )
        for item in state.decisions
    )
    candidates.extend(
        ContextCandidate(
            item_id=f"error:{index}",
            kind=ContextKind.OPEN_ERROR,
            content=f"{item.code}: {item.message}",
            source_reference=item.code,
            relevance=1.0,
        )
        for index, item in enumerate(state.errors)
    )
    return tuple(candidates)
