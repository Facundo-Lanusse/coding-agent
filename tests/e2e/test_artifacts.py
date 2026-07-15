import json
import sys
from pathlib import Path

from coding_agent.demo import ArtifactWriter, RunArtifact
from coding_agent.demo.scenarios import DemoScenarioRunner


def test_artifact_bundle_has_valid_schema_and_required_files(tmp_path: Path) -> None:
    output = tmp_path / "artifacts"
    runner = DemoScenarioRunner(
        seed_root=Path("examples/fastapi_demo/seed"),
        runtime_root=tmp_path / "runtime",
        rag_sources=Path("rag_sources"),
        output_root=output,
    )

    run = runner.run_rag()
    loaded = ArtifactWriter(output).load(run.artifact.run_id)

    assert isinstance(loaded, RunArtifact)
    assert loaded == run.artifact
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
    assert {path.name for path in run.artifact_directory.iterdir()} == expected
    state = json.loads((run.artifact_directory / "task_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["request"]["workspace"] == "${WORKSPACE}"
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in run.artifact_directory.iterdir()
        if path.suffix in {".json", ".md", ".patch"}
    )
    assert str(tmp_path) not in persisted
    assert sys.executable not in persisted
    assert str(Path(sys.executable).resolve()) not in persisted
    assert "${PYTHON}" in persisted
    assert loaded.trace_id is None
    assert loaded.observability == "recording"
