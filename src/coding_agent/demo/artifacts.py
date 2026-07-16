"""Stable, sanitized artifacts for deterministic demo executions."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import Field

from coding_agent.models import FrozenModel
from coding_agent.observability import Sanitizer
from coding_agent.state import EvidenceSource, TaskState, TaskStatus

_RUN_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,80}")


class ArtifactCommand(FrozenModel):
    argv: tuple[str, ...]
    exit_code: int | None = None
    status: str = Field(min_length=1)
    output_digest: str | None = None


class ArtifactSource(FrozenModel):
    source: EvidenceSource
    reference: str = Field(min_length=1)
    locator: str | None = None
    excerpt: str = Field(min_length=1)


class ArtifactEvent(FrozenModel):
    event_type: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class RunArtifact(FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,80}$")
    scenario: Literal[
        "rag",
        "memory_session_1",
        "memory_session_2",
        "safety",
        "real_rag",
    ]
    task_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    status: TaskStatus
    provider_mode: Literal["deterministic_fake", "real"]
    observability: Literal["recording", "langfuse", "noop"]
    trace_id: str | None = None
    fixture_before: str = Field(min_length=64, max_length=64)
    fixture_after: str = Field(min_length=64, max_length=64)
    sources: tuple[ArtifactSource, ...] = ()
    files_modified: tuple[str, ...] = ()
    commands: tuple[ArtifactCommand, ...] = ()
    memory_retrieved: tuple[str, ...] = ()
    control_events: tuple[ArtifactEvent, ...] = ()
    diff: str = ""
    final_summary: str = Field(min_length=1)
    pending_commands: tuple[str, ...] = ()


class ArtifactWriter:
    def __init__(self, output_root: str | Path) -> None:
        self._root = Path(output_root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._sanitizer = Sanitizer(max_payload_chars=1_000_000, environment={})

    def write(self, artifact: RunArtifact, state: TaskState) -> Path:
        if _RUN_ID.fullmatch(artifact.run_id) is None:
            raise ValueError("Invalid artifact run id.")
        run_directory = (self._root / artifact.run_id).resolve()
        if run_directory.parent != self._root:
            raise ValueError("Artifact directory escaped its configured root.")
        run_directory.mkdir(parents=True, exist_ok=True)

        portable_artifact = self.portable(artifact, state)
        replacements = _path_replacements(state)
        payloads: dict[str, object] = {
            "run.json": portable_artifact.model_dump(mode="json"),
            "task_state.json": _portable(state.model_dump(mode="json"), replacements),
            "sources.json": [
                item.model_dump(mode="json") for item in portable_artifact.sources
            ],
            "commands.json": [
                item.model_dump(mode="json") for item in portable_artifact.commands
            ],
            "memory.json": list(portable_artifact.memory_retrieved),
            "events.json": [
                item.model_dump(mode="json") for item in portable_artifact.control_events
            ],
        }
        for name, payload in payloads.items():
            sanitized = self._sanitizer.sanitize(payload)
            _atomic_text(run_directory / name, json.dumps(sanitized, indent=2, sort_keys=True))
        _atomic_text(run_directory / "diff.patch", portable_artifact.diff)
        _atomic_text(run_directory / "summary.md", _summary(portable_artifact))
        return run_directory

    def portable(self, artifact: RunArtifact, state: TaskState) -> RunArtifact:
        """Replace machine-local paths without changing the executed task state."""

        payload = _portable(artifact.model_dump(mode="json"), _path_replacements(state))
        return RunArtifact.model_validate(payload)

    def load(self, run_id: str) -> RunArtifact:
        if _RUN_ID.fullmatch(run_id) is None:
            raise ValueError("Invalid artifact run id.")
        path = (self._root / run_id / "run.json").resolve()
        if path.parent.parent != self._root:
            raise ValueError("Artifact path escaped its configured root.")
        return RunArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def _atomic_text(path: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary_path = Path(temporary)
        if temporary_path.exists():
            temporary_path.unlink()


def _summary(artifact: RunArtifact) -> str:
    sources = "\n".join(f"- [{item.source.value}] {item.reference}" for item in artifact.sources)
    commands = "\n".join(
        f"- `{ ' '.join(item.argv) }`: {item.status}, exit={item.exit_code}"
        for item in artifact.commands
    )
    pending = "\n".join(f"- `{command}`" for command in artifact.pending_commands)
    return (
        f"# {artifact.run_id}\n\n"
        f"Status: `{artifact.status.value}`\n\n"
        f"{artifact.final_summary}\n\n"
        f"## Sources\n\n{sources or '- None'}\n\n"
        f"## Commands\n\n{commands or '- None'}\n\n"
        f"## Pending real commands\n\n{pending or '- None'}\n"
    )


def _path_replacements(state: TaskState) -> tuple[tuple[str, str], ...]:
    replacements = (
        (str(state.request.workspace.resolve()), "${WORKSPACE}"),
        (sys.executable, "${PYTHON}"),
        (str(Path(sys.executable).resolve()), "${PYTHON}"),
        (str(Path.home().resolve()), "${HOME}"),
    )
    return tuple(dict.fromkeys(replacements))


def _portable(value: object, replacements: tuple[tuple[str, str], ...]) -> object:
    if isinstance(value, str):
        result = value
        for local_path, marker in replacements:
            result = result.replace(local_path, marker)
        return result
    if isinstance(value, list):
        return [_portable(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _portable(item, replacements) for key, item in value.items()}
    return value
