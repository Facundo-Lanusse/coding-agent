"""Deterministic scope review used by the demo Reviewer."""

from __future__ import annotations

from pathlib import Path

from coding_agent.models import FrozenModel
from coding_agent.state import FileChange


class ReviewVerdict(FrozenModel):
    accepted: bool
    findings: tuple[str, ...] = ()
    inspected_paths: tuple[str, ...] = ()


class ScopeReviewer:
    def __init__(self, allowed_paths: frozenset[str]) -> None:
        self._allowed = allowed_paths

    def review(self, changes: tuple[FileChange, ...]) -> ReviewVerdict:
        inspected = tuple(_relative(change.path) for change in changes)
        unexpected = tuple(path for path in inspected if path not in self._allowed)
        findings = tuple(f"Change outside requested scope: {path}" for path in unexpected)
        return ReviewVerdict(
            accepted=not findings,
            findings=findings,
            inspected_paths=inspected,
        )


def _relative(path: Path) -> str:
    value = path.as_posix()
    return value.removeprefix("./")

