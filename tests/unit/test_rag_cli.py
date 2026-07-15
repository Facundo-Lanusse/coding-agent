from pathlib import Path

from conftest import ProjectFixture
from typer.testing import CliRunner

from coding_agent.cli import app


def test_rag_cli_ingest_and_query_are_reproducible_offline(
    project: ProjectFixture,
    tmp_path: Path,
) -> None:
    rag_config = project.config["rag"]
    assert isinstance(rag_config, dict)
    rag_config["persistence_path"] = str(tmp_path / "vector-store")
    rag_config["minimum_relevance"] = 0.05
    rag_config["embedding_dimension"] = 64
    config_path = project.write_config()
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "fastapi.md").write_text(
        "# FastAPI dependencies\n\nUse Depends to declare dependencies in routes.",
        encoding="utf-8",
    )
    runner = CliRunner()

    ingested = runner.invoke(
        app,
        [
            "rag",
            "ingest",
            str(sources),
            "--config",
            str(config_path),
            "--fake-embeddings",
        ],
    )
    queried = runner.invoke(
        app,
        [
            "rag",
            "query",
            "FastAPI dependencies Depends",
            "--config",
            str(config_path),
            "--fake-embeddings",
        ],
    )

    assert ingested.exit_code == 0, ingested.output
    assert '"inserted": 1' in ingested.output
    assert queried.exit_code == 0, queried.output
    assert '"sufficient": true' in queried.output
    assert '"path_or_url": "fastapi.md"' in queried.output
