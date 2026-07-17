import json
import sys
from pathlib import Path

from coding_agent.demo import ArtifactCommand, ArtifactSource, ArtifactWriter, RunArtifact
from coding_agent.state import EvidenceSource, TaskRequest, TaskState, TaskStatus


def test_artifact_bundle_has_valid_schema_and_required_files(tmp_path: Path) -> None:
    output = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = TaskState(
        request=TaskRequest(
            task_id="artifact-test",
            project_id="fastapi-demo",
            session_id="session",
            original_request="Test artifact portability.",
            workspace=workspace,
        ),
        status=TaskStatus.COMPLETED,
    )
    artifact = RunArtifact(
        run_id="artifact-test",
        scenario="rag",
        task_id="artifact-test",
        project_id="fastapi-demo",
        session_id="session",
        status=TaskStatus.COMPLETED,
        provider_mode="deterministic_fake",
        observability="recording",
        fixture_before="a" * 64,
        fixture_after="b" * 64,
        sources=(
            ArtifactSource(
                source=EvidenceSource.RAG,
                reference="rag_sources/fastapi_dependencies.md",
                excerpt="FastAPI dependency evidence.",
            ),
        ),
        commands=(
            ArtifactCommand(
                argv=(sys.executable, "-m", "pytest", "-q"),
                exit_code=0,
                status="executed",
            ),
        ),
        memory_retrieved=(f"{Path.home()}/private/project",),
        final_summary="Artifact created.",
    )
    writer = ArtifactWriter(output)
    artifact_directory = writer.write(artifact, state)
    loaded = writer.load(artifact.run_id)

    assert isinstance(loaded, RunArtifact)
    assert loaded.run_id == artifact.run_id
    expected = {
        "run.json",
        "task_state.json",
        "summary.md",
        "sources.json",
        "commands.json",
        "memory.json",
        "events.json",
        "diff.patch",
    }
    assert {path.name for path in artifact_directory.iterdir()} == expected
    state_payload = json.loads(
        (artifact_directory / "task_state.json").read_text(encoding="utf-8")
    )
    assert state_payload["status"] == "completed"
    assert state_payload["request"]["workspace"] == "${WORKSPACE}"
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in artifact_directory.iterdir()
        if path.suffix in {".json", ".md", ".patch"}
    )
    assert str(tmp_path) not in persisted
    assert sys.executable not in persisted
    assert str(Path(sys.executable).resolve()) not in persisted
    assert "${PYTHON}" in persisted
    assert loaded.trace_id is None
    assert loaded.observability == "recording"

    memory_payload = (artifact_directory / "memory.json").read_text(encoding="utf-8")
    assert str(Path.home()) not in memory_payload
    assert "${HOME}/private/project" in memory_payload
