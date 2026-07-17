"""Command-line composition for the explicit harness and policy gateway."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from coding_agent.approval import ApprovalProvider
from coding_agent.config import (
    AgentConfig,
    ConfigurationError,
    RuntimeSettings,
    load_config,
    resolve_workspace,
)
from coding_agent.demo import FixtureResetter
from coding_agent.harness import CodingAgentHarness
from coding_agent.llm.openai_client import OpenAIResponsesClient
from coding_agent.models import (
    AgentRunRequest,
    ApprovalDecision,
    ApprovalRequest,
    RunStatus,
)
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.rag import (
    CollectionSpec,
    DeterministicFakeEmbeddings,
    EmbeddingError,
    EmbeddingProvider,
    LocalSourceLoader,
    OpenAIEmbeddingProvider,
    RAGIngestor,
    RAGRetriever,
    SourceLoadError,
    SQLiteVectorStore,
    TechnicalChunker,
    VectorStoreError,
)
from coding_agent.runtime import RealDemoError, run_real_demo
from coding_agent.tools import ToolRole, build_default_registry

app = typer.Typer(
    name="coding-agent",
    help="Explicit coding-agent harness for Python and FastAPI repositories.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Inspect and validate agent configuration.", no_args_is_help=True)
rag_app = typer.Typer(help="Ingest and query the persistent technical RAG.", no_args_is_help=True)
demo_app = typer.Typer(help="Run the bounded FastAPI delivery scenario.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(rag_app, name="rag")
app.add_typer(demo_app, name="demo")

ConfigPath = Annotated[
    Path,
    typer.Option("--config", help="Path to agent.config.yaml."),
]


class TyperApprovalProvider(ApprovalProvider):
    """Interactive approval adapter kept outside the core harness."""

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        typer.echo(f"\nApproval required: {request.action}")
        typer.echo(request.description)
        if request.arguments:
            typer.echo(json.dumps(request.arguments, indent=2, ensure_ascii=False))
        approved = typer.confirm("Approve?", default=False)
        return ApprovalDecision(
            approved=approved,
            reason="Approved by CLI user." if approved else "Rejected by CLI user.",
        )


@config_app.command("validate")
def validate_config(config: ConfigPath = Path("agent.config.yaml")) -> None:
    """Parse and validate configuration without contacting external providers."""

    try:
        loaded = load_config(config)
    except ConfigurationError as exc:
        _configuration_failure(exc)

    typer.echo("Configuration valid.")
    typer.echo(f"Provider: {loaded.llm.provider}")
    typer.echo(f"Model: {loaded.llm.model}")
    typer.echo(f"Workspace: {resolve_workspace(loaded, config)}")


@app.command("run")
def run_agent(
    task: Annotated[str, typer.Option("--task", help="Natural-language coding task.")],
    config: ConfigPath = Path("agent.config.yaml"),
    plan: Annotated[bool, typer.Option("--plan/--no-plan")] = True,
    supervision: Annotated[
        bool,
        typer.Option("--supervision/--no-supervision"),
    ] = True,
) -> None:
    """Run the basic harness through the Phase 02 authorized tool gateway."""

    try:
        loaded = load_config(config)
    except ConfigurationError as exc:
        _configuration_failure(exc)

    settings = RuntimeSettings()
    if settings.openai_api_key is None:
        typer.echo("OPENAI_API_KEY is required to use the real OpenAI adapter.", err=True)
        raise typer.Exit(code=2)

    llm = OpenAIResponsesClient(
        model=loaded.llm.model,
        max_output_tokens=loaded.llm.max_output_tokens,
        store_responses=loaded.llm.store_responses,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    approval_provider = TyperApprovalProvider()
    registry = build_default_registry()
    gateway = AuthorizedToolGateway(
        registry,
        config_path=config,
        approval_provider=approval_provider,
    )
    harness = CodingAgentHarness(
        llm,
        tools=gateway.bindings(ToolRole.IMPLEMENTER),
        approval_provider=approval_provider,
    )
    result = harness.run(
        AgentRunRequest(
            task=task,
            plan_mode=plan,
            supervision_mode=supervision,
            max_iterations=loaded.execution.max_agent_iterations,
        )
    )
    typer.echo(result.model_dump_json(indent=2))
    if result.status is not RunStatus.COMPLETED:
        raise typer.Exit(code=2)


@rag_app.command("ingest")
def rag_ingest(
    source: Annotated[Path, typer.Argument(help="Directory with local RAG sources.")],
    config: ConfigPath = Path("agent.config.yaml"),
    fake_embeddings: Annotated[
        bool,
        typer.Option("--fake-embeddings", help="Use deterministic offline embeddings."),
    ] = False,
) -> None:
    """Normalize, chunk, embed, and persist an allowlisted local corpus."""

    loaded, embeddings, store, collection = _rag_runtime(config, fake_embeddings)
    try:
        ingestor = RAGIngestor(
            chunker=TechnicalChunker(
                max_tokens=loaded.rag.chunk_size_tokens,
                overlap_tokens=loaded.rag.chunk_overlap_tokens,
            ),
            embeddings=embeddings,
            store=store,
            collection=collection,
        )
        report = ingestor.ingest_directory(
            str(source),
            loader=LocalSourceLoader(max_bytes=loaded.execution.max_read_bytes),
        )
        typer.echo(report.model_dump_json(indent=2))
    except (EmbeddingError, SourceLoadError, VectorStoreError) as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    finally:
        store.close()


@rag_app.command("query")
def rag_query(
    query: Annotated[str, typer.Argument(help="Technical question to retrieve.")],
    config: ConfigPath = Path("agent.config.yaml"),
    fake_embeddings: Annotated[
        bool,
        typer.Option("--fake-embeddings", help="Use deterministic offline embeddings."),
    ] = False,
) -> None:
    """Retrieve only chunks meeting the configured top-k threshold."""

    loaded, embeddings, store, collection = _rag_runtime(config, fake_embeddings)
    try:
        result = RAGRetriever(
            embeddings=embeddings,
            store=store,
            collection=collection,
            top_k=loaded.rag.top_k,
            minimum_score=loaded.rag.minimum_relevance,
        ).query(query)
        typer.echo(result.model_dump_json(indent=2))
        if not result.hits:
            raise typer.Exit(code=3)
    except (EmbeddingError, VectorStoreError) as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    finally:
        store.close()


@demo_app.command("reset")
def demo_reset(
    name: Annotated[str, typer.Option("--name")] = "manual",
    runtime_root: Annotated[Path, typer.Option("--runtime-root")] = Path("tmp/demo-runtime"),
) -> None:
    """Reset one contained workspace from the immutable FastAPI seed."""

    snapshot = FixtureResetter(_demo_seed(), runtime_root).reset(name)
    typer.echo(snapshot.checksum)


@demo_app.command("real")
def demo_real(
    scenario: Annotated[str, typer.Option("--scenario")] = "rag",
    config: ConfigPath = Path("agent.config.yaml"),
    runtime_root: Annotated[Path, typer.Option("--runtime-root")] = Path(
        "tmp/demo-runtime"
    ),
    output_root: Annotated[Path, typer.Option("--output-root")] = Path(
        "docs/evidence/runs"
    ),
    max_llm_calls: Annotated[
        int,
        typer.Option("--max-llm-calls", min=5, max=25),
    ] = 15,
    max_iterations_per_agent: Annotated[
        int,
        typer.Option("--max-iterations-per-agent", min=1, max=6),
    ] = 4,
    max_output_tokens: Annotated[
        int,
        typer.Option("--max-output-tokens", min=256, max=4_000),
    ] = 1_800,
    confirm_cost: Annotated[
        bool,
        typer.Option(
            "--confirm-cost",
            help="Explicitly allow bounded OpenAI/Tavily API usage for this run.",
        ),
    ] = False,
) -> None:
    """Run the real five-agent RAG scenario with hard provider-call limits."""

    if scenario != "rag":
        typer.echo("Only --scenario rag is implemented for the bounded real demo.", err=True)
        raise typer.Exit(code=2)
    if not confirm_cost:
        typer.echo(
            "No API call made. Re-run with --confirm-cost after reviewing the limits.",
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        run = run_real_demo(
            config_path=config,
            seed_root=_demo_seed(),
            rag_sources=Path("rag_sources"),
            runtime_root=runtime_root,
            output_root=output_root,
            approval_provider=TyperApprovalProvider(),
            max_llm_calls=max_llm_calls,
            max_iterations_per_agent=max_iterations_per_agent,
            max_output_tokens=max_output_tokens,
        )
    except (ConfigurationError, RealDemoError) as exc:
        typer.echo(f"{getattr(exc, 'code', 'real_demo_error')}: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(run.artifact.model_dump_json(indent=2))
    typer.echo(f"Artifacts: {run.artifact_directory}")
    typer.echo(f"Langfuse trace id: {run.artifact.trace_id}")
    if run.state.status.value != "completed":
        raise typer.Exit(code=2)


def _rag_runtime(
    config_path: Path,
    fake_embeddings: bool,
) -> tuple[AgentConfig, EmbeddingProvider, SQLiteVectorStore, CollectionSpec]:
    try:
        loaded = load_config(config_path)
    except ConfigurationError as exc:
        _configuration_failure(exc)
    if fake_embeddings:
        embeddings: EmbeddingProvider = DeterministicFakeEmbeddings(
            dimension=loaded.rag.embedding_dimension,
            model=f"fake::{loaded.rag.embedding_model}",
        )
    else:
        settings = RuntimeSettings()
        if settings.openai_api_key is None:
            typer.echo(
                "OPENAI_API_KEY is required; use --fake-embeddings for an offline run.",
                err=True,
            )
            raise typer.Exit(code=2)
        embeddings = OpenAIEmbeddingProvider(
            model=loaded.rag.embedding_model,
            dimension=loaded.rag.embedding_dimension,
            api_key=settings.openai_api_key.get_secret_value(),
        )
    persistence = loaded.rag.persistence_path
    if not persistence.is_absolute():
        persistence = config_path.resolve().parent / persistence
    database = persistence if persistence.suffix else persistence / "vectors.sqlite3"
    collection = CollectionSpec(
        name=loaded.rag.collection_name,
        version=loaded.rag.collection_version,
        embedding_model=embeddings.model,
        dimension=embeddings.dimension,
    )
    return loaded, embeddings, SQLiteVectorStore(database), collection


def _demo_seed() -> Path:
    return Path("examples/fastapi_demo/seed")


def _configuration_failure(error: ConfigurationError) -> NoReturn:
    typer.echo(f"{error.code}: {error}", err=True)
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
