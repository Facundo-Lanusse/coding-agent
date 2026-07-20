"""Artifact and memory persistence for the real FastAPI demonstration."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from coding_agent.agents import OpenAIAgentBackend
from coding_agent.demo.artifacts import (
    ArtifactCommand,
    ArtifactEvent,
    ArtifactSource,
    RunArtifact,
)
from coding_agent.memory import (
    MemoryCategory,
    MemoryKind,
    MemoryRecord,
    MemoryRepository,
    MemorySourceType,
)
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.state import EvidenceSource, TaskState, TaskStatus


def build_real_artifact(
    *,
    run_id: str,
    state: TaskState,
    before_checksum: str,
    after_checksum: str,
    trace_id: str | None,
    gateway: AuthorizedToolGateway,
    backend: OpenAIAgentBackend,
) -> RunArtifact:
    command_invocations = [
        item for item in state.tool_invocations if item.tool_name == "run_command"
    ]
    commands = tuple(
        ArtifactCommand(
            argv=argv,
            exit_code=(
                command_invocations[index].exit_code
                if index < len(command_invocations)
                else None
            ),
            status=(
                command_invocations[index].status.value
                if index < len(command_invocations)
                else "recorded"
            ),
            output_digest=(
                command_invocations[index].output_digest
                if index < len(command_invocations)
                else None
            ),
        )
        for index, argv in enumerate(state.commands)
    )
    sources = tuple(
        ArtifactSource(
            source=item.source,
            reference=item.reference,
            locator=item.locator,
            excerpt=item.content[:500],
        )
        for item in state.evidence
    )
    events = [
        ArtifactEvent(
            event_type=event.event_type,
            outcome=event.to_status.value,
            detail=f"{event.from_status.value} -> {event.to_status.value}",
        )
        for event in state.events
    ]
    events.extend(
        ArtifactEvent(
            event_type="policy",
            outcome=decision.outcome.value,
            detail=f"{decision.rule}: {decision.reason}",
        )
        for decision in gateway.decisions
    )
    events.extend(
        ArtifactEvent(
            event_type="loop.no_progress",
            outcome=signal.strategy.value,
            detail=signal.explanation,
        )
        for signal in backend.no_progress_signals
    )
    return RunArtifact(
        run_id=run_id,
        scenario="real_rag",
        task_id=state.request.task_id,
        project_id=state.request.project_id,
        session_id=state.request.session_id,
        status=state.status,
        provider_mode="real",
        observability="langfuse",
        trace_id=trace_id,
        fixture_before=before_checksum,
        fixture_after=after_checksum,
        sources=sources,
        files_modified=tuple(str(item.path) for item in state.files_modified),
        commands=commands,
        memory_retrieved=tuple(
            item.content for item in state.evidence if item.source is EvidenceSource.MEMORY
        ),
        control_events=tuple(events),
        diff="".join(item.diff or "" for item in state.files_modified),
        final_summary=final_summary(state),
        pending_commands=(),
    )


def persist_verified_memory(repository: MemoryRepository, state: TaskState) -> None:
    if state.status is not TaskStatus.COMPLETED:
        return
    now = datetime.now(UTC)
    stale_after = now + timedelta(days=30)
    records: list[MemoryRecord] = []
    for path in state.files_read:
        records.append(
            _memory_record(
                state,
                category=MemoryCategory.IMPORTANT_FILE,
                kind=MemoryKind.OBSERVATION,
                content=f"Verified relevant project file: {path.as_posix()}.",
                source_type=MemorySourceType.REPOSITORY,
                source_reference=path.as_posix(),
                now=now,
                stale_after=stale_after,
            )
        )
    for result in state.agent_results:
        for check in result.checks:
            records.append(
                _memory_record(
                    state,
                    category=MemoryCategory.CHECK_RESULT,
                    kind=MemoryKind.OBSERVATION,
                    content=(
                        f"Check {'passed' if check.passed else 'failed'}: "
                        f"{' '.join(check.command) or check.name}."
                    ),
                    source_type=MemorySourceType.TOOL_OUTPUT,
                    source_reference=check.output_digest or check.name,
                    now=now,
                    stale_after=stale_after,
                )
            )
    for decision in state.decisions:
        records.append(
            _memory_record(
                state,
                category=MemoryCategory.DECISION,
                kind=MemoryKind.DECISION,
                content=decision.reason,
                source_type=MemorySourceType.TOOL_OUTPUT,
                source_reference=decision.decision_id,
                now=now,
                stale_after=stale_after,
                metadata={"evidence_ids": list(decision.evidence_ids)},
            )
        )
    records.append(
        _memory_record(
            state,
            category=MemoryCategory.SESSION_SUMMARY,
            kind=MemoryKind.SESSION_SUMMARY,
            content=final_summary(state),
            source_type=MemorySourceType.TOOL_OUTPUT,
            source_reference=state.request.task_id,
            now=now,
            stale_after=stale_after,
        )
    )
    for record in records:
        repository.save(record)


def final_summary(state: TaskState) -> str:
    if state.final_result is not None:
        return state.final_result.summary
    if state.errors:
        return f"Task ended in {state.status.value}: {state.errors[-1].message}"
    return f"Task ended in {state.status.value}."


def _memory_record(
    state: TaskState,
    *,
    category: MemoryCategory,
    kind: MemoryKind,
    content: str,
    source_type: MemorySourceType,
    source_reference: str,
    now: datetime,
    stale_after: datetime,
    metadata: dict[str, object] | None = None,
) -> MemoryRecord:
    identifier = hashlib.sha256(
        f"{state.request.project_id}:{category.value}:{source_reference}:{content}".encode()
    ).hexdigest()
    return MemoryRecord(
        id=identifier,
        project_id=state.request.project_id,
        category=category,
        kind=kind,
        content=content,
        source_type=source_type,
        source_reference=source_reference,
        confidence=1.0,
        session_id=state.request.session_id,
        created_at=now,
        updated_at=now,
        last_verified_at=now,
        stale_after=stale_after,
        metadata=metadata or {"verified": True},
    )
