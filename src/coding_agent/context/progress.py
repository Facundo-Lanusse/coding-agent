"""Deterministic loop and no-progress detection with explicit strategies."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping, Sequence
from enum import StrEnum

from pydantic import Field

from coding_agent.context.fingerprints import FingerprintFactory
from coding_agent.models import FrozenModel
from coding_agent.observability import NoOpTracer, Tracer


class ProgressStrategy(StrEnum):
    CHANGE_STRATEGY = "change_strategy"
    REPLAN = "replan"
    STOP = "stop"
    ASK_HELP = "ask_help"
    REQUEST_EVIDENCE_OR_PERMISSION = "request_evidence_or_permission"


class NoProgressReason(StrEnum):
    REPEATED_ACTION = "repeated_action"
    REPEATED_ERROR = "repeated_error"
    REPEATED_READ = "repeated_read"
    ALTERNATING_CYCLE = "alternating_cycle"
    ITERATION_LIMIT = "iteration_limit"
    STAGNANT_PHASES = "stagnant_phases"


class NoProgressSignal(FrozenModel):
    reason: NoProgressReason
    strategy: ProgressStrategy
    explanation: str = Field(min_length=1)
    attempts: tuple[str, ...]
    missing_information: tuple[str, ...]
    allow_execution: bool
    fingerprint: str = Field(min_length=1)


class NoProgressReport(FrozenModel):
    reason: NoProgressReason
    strategy: ProgressStrategy
    attempts: tuple[str, ...]
    missing_information: tuple[str, ...]
    explanation: str = Field(min_length=1)

    @classmethod
    def from_signal(cls, signal: NoProgressSignal) -> NoProgressReport:
        return cls(
            reason=signal.reason,
            strategy=signal.strategy,
            attempts=signal.attempts,
            missing_information=signal.missing_information,
            explanation=signal.explanation,
        )

    def render(self) -> str:
        attempted = "; ".join(self.attempts) or "No actions were recorded."
        missing = "; ".join(self.missing_information) or "No missing item was identified."
        return (
            f"Attempted: {attempted}\n"
            f"No-progress reason: {self.explanation}\n"
            f"Chosen strategy: {self.strategy.value}\n"
            f"Missing to continue: {missing}"
        )


class NoProgressDetector:
    """Track progress deltas and block a repeated action before its next effect."""

    def __init__(
        self,
        *,
        max_identical_actions: int = 2,
        max_identical_errors: int = 2,
        max_stagnant_phases: int = 2,
        tracer: Tracer | None = None,
    ) -> None:
        if min(max_identical_actions, max_identical_errors, max_stagnant_phases) < 1:
            raise ValueError("No-progress thresholds must be positive.")
        self._max_identical_actions = max_identical_actions
        self._max_identical_errors = max_identical_errors
        self._max_stagnant_phases = max_stagnant_phases
        self._action_counts: Counter[str] = Counter()
        self._error_counts: Counter[str] = Counter()
        self._recent_actions: deque[tuple[str, str]] = deque(maxlen=4)
        self._reads: dict[str, tuple[str, str]] = {}
        self._attempts: list[str] = []
        self._evidence_ids: set[str] = set()
        self._change_ids: set[str] = set()
        self._last_phase_progress: str | None = None
        self._stagnant_phases = 0
        self._tracer = tracer or NoOpTracer()

    @property
    def attempts(self) -> tuple[str, ...]:
        return tuple(self._attempts)

    def before_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
        *,
        relevant_keys: Sequence[str] = (),
    ) -> NoProgressSignal | None:
        fingerprint = FingerprintFactory.tool(
            name,
            arguments,
            relevant_keys=relevant_keys,
        )
        if self._action_counts[fingerprint] < self._max_identical_actions:
            return None
        return self._signal(
            reason=NoProgressReason.REPEATED_ACTION,
            strategy=ProgressStrategy.STOP,
            explanation="The same normalized tool action already ran without new progress.",
            missing=("new evidence, different arguments, or explicit human direction",),
            allow_execution=False,
            fingerprint=fingerprint,
        )

    def record_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
        *,
        relevant_keys: Sequence[str] = (),
    ) -> NoProgressSignal | None:
        fingerprint = FingerprintFactory.tool(
            name,
            arguments,
            relevant_keys=relevant_keys,
        )
        label = f"tool:{name}"
        self._action_counts[fingerprint] += 1
        self._recent_actions.append((fingerprint, label))
        self._attempts.append(label)
        return self._detect_cycle()

    def record_command_error(
        self,
        command: str | Sequence[str],
        *,
        code: str,
        message: str,
    ) -> NoProgressSignal | None:
        fingerprint = FingerprintFactory.error(code, message, command=command)
        label = f"command-error:{' '.join(command) if not isinstance(command, str) else command}"
        self._error_counts[fingerprint] += 1
        self._attempts.append(label)
        if self._error_counts[fingerprint] < self._max_identical_errors:
            return None
        return self._signal(
            reason=NoProgressReason.REPEATED_ERROR,
            strategy=ProgressStrategy.REPLAN,
            explanation="The same normalized command error occurred repeatedly.",
            missing=("a new diagnosis or an alternative implementation hypothesis",),
            allow_execution=False,
            fingerprint=fingerprint,
        )

    def record_file_read(
        self,
        path: str,
        *,
        content_digest: str,
    ) -> NoProgressSignal | None:
        fingerprint = FingerprintFactory.file_read(path, content_digest)
        progress = FingerprintFactory.progress(tuple(self._evidence_ids), tuple(self._change_ids))
        previous = self._reads.get(path.casefold())
        self._reads[path.casefold()] = (fingerprint, progress)
        self._attempts.append(f"read:{path}")
        if previous != (fingerprint, progress):
            return None
        return self._signal(
            reason=NoProgressReason.REPEATED_READ,
            strategy=ProgressStrategy.REQUEST_EVIDENCE_OR_PERMISSION,
            explanation="The file was reread unchanged and yielded no new evidence.",
            missing=(
                "a different source, changed file content, or permission to inspect another path",
            ),
            allow_execution=False,
            fingerprint=fingerprint,
        )

    def record_iteration(self, iteration: int, *, maximum: int) -> NoProgressSignal | None:
        if iteration < maximum:
            return None
        fingerprint = FingerprintFactory.result("iteration_limit", output_digest=str(iteration))
        return self._signal(
            reason=NoProgressReason.ITERATION_LIMIT,
            strategy=ProgressStrategy.STOP,
            explanation=f"The iteration budget of {maximum} was exhausted.",
            missing=("human direction or a larger explicitly approved budget",),
            allow_execution=False,
            fingerprint=fingerprint,
        )

    def record_phase(
        self,
        phase: str,
        *,
        evidence_ids: Sequence[str],
        change_ids: Sequence[str],
    ) -> NoProgressSignal | None:
        progress = FingerprintFactory.progress(evidence_ids, change_ids)
        if self._last_phase_progress == progress:
            self._stagnant_phases += 1
        else:
            self._stagnant_phases = 0
            self._last_phase_progress = progress
        self._attempts.append(f"phase:{phase}")
        if self._stagnant_phases < self._max_stagnant_phases:
            return None
        return self._signal(
            reason=NoProgressReason.STAGNANT_PHASES,
            strategy=ProgressStrategy.ASK_HELP,
            explanation="Multiple phases completed without new evidence or file changes.",
            missing=("evidence, a safe change, or clarification of the objective",),
            allow_execution=False,
            fingerprint=progress,
        )

    def note_progress(
        self,
        *,
        evidence_ids: Sequence[str] = (),
        change_ids: Sequence[str] = (),
    ) -> bool:
        new_evidence = set(evidence_ids).difference(self._evidence_ids)
        new_changes = set(change_ids).difference(self._change_ids)
        self._evidence_ids.update(evidence_ids)
        self._change_ids.update(change_ids)
        if not new_evidence and not new_changes:
            return False
        self._action_counts.clear()
        self._error_counts.clear()
        self._recent_actions.clear()
        self._reads.clear()
        self._last_phase_progress = None
        self._stagnant_phases = 0
        return True

    def _detect_cycle(self) -> NoProgressSignal | None:
        if len(self._recent_actions) < 4:
            return None
        first, second, third, fourth = self._recent_actions
        if first[0] != third[0] or second[0] != fourth[0] or first[0] == second[0]:
            return None
        fingerprint = FingerprintFactory.result(
            "alternating_cycle",
            output_digest=f"{first[0]}:{second[0]}",
        )
        return self._signal(
            reason=NoProgressReason.ALTERNATING_CYCLE,
            strategy=ProgressStrategy.CHANGE_STRATEGY,
            explanation="Two normalized actions are alternating in an A-B-A-B cycle.",
            missing=("a third strategy or new evidence that breaks the cycle",),
            allow_execution=False,
            fingerprint=fingerprint,
        )

    def _signal(
        self,
        *,
        reason: NoProgressReason,
        strategy: ProgressStrategy,
        explanation: str,
        missing: tuple[str, ...],
        allow_execution: bool,
        fingerprint: str,
    ) -> NoProgressSignal:
        signal = NoProgressSignal(
            reason=reason,
            strategy=strategy,
            explanation=explanation,
            attempts=tuple(self._attempts),
            missing_information=missing,
            allow_execution=allow_execution,
            fingerprint=fingerprint,
        )
        with self._tracer.observe(
            "loop.no_progress",
            input={"attempts": self._attempts, "fingerprint": fingerprint},
            metadata={"reason": reason.value, "strategy": strategy.value},
        ) as observation:
            observation.update(output=signal)
        return signal
