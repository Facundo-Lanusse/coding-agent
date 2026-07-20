"""Production composition for one cost-bounded real multi-agent demo."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from coding_agent.agents import (
    ExplorerAgent,
    ImplementerAgent,
    LLMCallBudget,
    OpenAIAgentBackend,
    ResearcherAgent,
    ReviewerAgent,
    TesterAgent,
)
from coding_agent.approval import ApprovalProvider
from coding_agent.config import AgentConfig, RuntimeSettings, load_config
from coding_agent.context import ContextBudget, ContextManager, ExtractiveSummaryProvider
from coding_agent.demo import DemoRun, FixtureResetter, snapshot
from coding_agent.demo.artifacts import ArtifactWriter
from coding_agent.demo.real_artifacts import (
    build_real_artifact,
    final_summary,
    persist_verified_memory,
)
from coding_agent.llm import OpenAIResponsesClient
from coding_agent.memory import MemoryQuery, MemoryRepository, SQLiteMemoryRepository
from coding_agent.observability import (
    LangfuseTracer,
    ObservationKind,
    TracedLLMClient,
    create_tracer,
)
from coding_agent.orchestrator import InitialEvidenceProvider, MainAgent
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.rag import (
    CollectionSpec,
    LocalSourceLoader,
    OpenAIEmbeddingProvider,
    RAGIngestor,
    RAGRetriever,
    ResearchService,
    SQLiteVectorStore,
    TechnicalChunker,
)
from coding_agent.state import (
    AgentName,
    Evidence,
    EvidenceSource,
    TaskRequest,
    TaskState,
)
from coding_agent.tools import TavilyWebSearchProvider, ToolRole, build_default_registry


class RealDemoError(Exception):
    code = "real_demo_error"


class ProjectMemoryEvidenceProvider(InitialEvidenceProvider):
    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    def load(self, request: TaskRequest) -> tuple[Evidence, ...]:
        results = self._repository.search(
            MemoryQuery(
                project_id=request.project_id,
                text=request.original_request,
                limit=10,
            )
        )
        return tuple(
            Evidence(
                evidence_id=f"memory-{item.record.id}",
                source=EvidenceSource.MEMORY,
                reference=item.record.source_reference,
                content=item.record.content,
                confidence=item.record.confidence,
            )
            for item in results
        )


def run_real_demo(
    *,
    config_path: Path,
    seed_root: Path,
    rag_sources: Path,
    runtime_root: Path,
    output_root: Path,
    approval_provider: ApprovalProvider,
    max_llm_calls: int,
    max_iterations_per_agent: int,
    max_output_tokens: int,
) -> DemoRun:
    """Run scenario A with OpenAI, real embeddings, Tavily fallback, and Langfuse."""

    config = load_config(config_path)
    settings = RuntimeSettings()
    missing = _missing_settings(settings)
    if missing:
        raise RealDemoError(f"Missing required environment variables: {', '.join(missing)}.")
    if max_output_tokens < 256 or max_output_tokens > config.llm.max_output_tokens:
        raise RealDemoError(
            "max_output_tokens must be between 256 and the configured LLM maximum."
        )

    run_id = f"real-openai-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    before = FixtureResetter(seed_root, runtime_root).reset(run_id)
    tracer = create_tracer(config.observability, trace_seed=run_id)
    if not isinstance(tracer, LangfuseTracer) or tracer.trace_id is None:
        raise RealDemoError(
            "Langfuse is enabled but its real client could not be initialized. "
            "No API call was made."
        )

    api_key = _secret(settings.openai_api_key)
    tavily_key = _secret(settings.tavily_api_key)
    web = TavilyWebSearchProvider(api_key=tavily_key, max_searches=1)
    embeddings = OpenAIEmbeddingProvider(
        model=config.rag.embedding_model,
        dimension=config.rag.embedding_dimension,
        api_key=api_key,
    )
    cache_root = runtime_root.resolve() / ".real-provider-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    store = SQLiteVectorStore(cache_root / "vectors.sqlite3")
    collection = CollectionSpec(
        name=f"{config.rag.collection_name}-real",
        version=config.rag.collection_version,
        embedding_model=embeddings.model,
        dimension=embeddings.dimension,
    )
    memory_path = _configured_path(config.memory.database_path, config_path)
    memory = SQLiteMemoryRepository(memory_path, tracer=tracer)
    gateway: AuthorizedToolGateway | None = None
    backend: OpenAIAgentBackend | None = None
    state: TaskState | None = None
    try:
        with tracer.observe(
            "demo.real.multiagent",
            kind=ObservationKind.TASK,
            input={"scenario": "rag", "workspace": str(before.workspace)},
            metadata={
                "task_id": run_id,
                "project_id": "fastapi-demo-real",
                "session_id": run_id,
                "model": config.llm.model,
                "max_llm_calls": max_llm_calls,
                "max_output_tokens": max_output_tokens,
            },
        ) as root_observation:
            RAGIngestor(
                chunker=TechnicalChunker(
                    max_tokens=config.rag.chunk_size_tokens,
                    overlap_tokens=config.rag.chunk_overlap_tokens,
                ),
                embeddings=embeddings,
                store=store,
                collection=collection,
            ).ingest_directory(
                str(rag_sources),
                loader=LocalSourceLoader(max_bytes=config.execution.max_read_bytes),
            )
            research = ResearchService(
                retriever=RAGRetriever(
                    embeddings=embeddings,
                    store=store,
                    collection=collection,
                    top_k=config.rag.top_k,
                    minimum_score=config.rag.minimum_relevance,
                    tracer=tracer,
                ),
                web_provider=web,
                web_fallback=config.rag.web_fallback,
                trusted_domains=config.rag.allowed_url_domains,
                max_web_results=3,
                tracer=tracer,
            )
            registry = build_default_registry(web_provider=web)

            def workspace_config(path: str | Path) -> AgentConfig:
                return load_config(path).model_copy(update={"workspace": before.workspace})

            gateway = AuthorizedToolGateway(
                registry,
                config_path=config_path,
                approval_provider=approval_provider,
                config_loader=workspace_config,
                tracer=tracer,
            )
            raw_llm = OpenAIResponsesClient(
                model=config.llm.model,
                max_output_tokens=max_output_tokens,
                store_responses=config.llm.store_responses,
                api_key=api_key,
            )
            backend = OpenAIAgentBackend(
                TracedLLMClient(raw_llm, tracer, configured_model=config.llm.model),
                call_budget=LLMCallBudget(max_llm_calls),
                max_iterations_per_agent=max_iterations_per_agent,
                max_identical_actions=config.execution.max_identical_actions,
                max_identical_failures=config.execution.max_identical_failures,
                tracer=tracer,
            )
            agents = {
                AgentName.EXPLORER: ExplorerAgent(
                    backend, tools=gateway.bindings(ToolRole.EXPLORER)
                ),
                AgentName.RESEARCHER: ResearcherAgent(
                    backend,
                    tools=gateway.bindings(ToolRole.RESEARCHER),
                    research_provider=research,
                ),
                AgentName.IMPLEMENTER: ImplementerAgent(
                    backend, tools=gateway.bindings(ToolRole.IMPLEMENTER)
                ),
                AgentName.TESTER: TesterAgent(
                    backend, tools=gateway.bindings(ToolRole.TESTER)
                ),
                AgentName.REVIEWER: ReviewerAgent(
                    backend, tools=gateway.bindings(ToolRole.REVIEWER)
                ),
            }
            request = TaskRequest(
                task_id=run_id,
                project_id="fastapi-demo-real",
                session_id=run_id,
                original_request=(
                    "Analizá este repositorio FastAPI y agregá un endpoint GET /health/ready. "
                    "Antes de implementar, consultá el RAG. Mostrá las fuentes utilizadas, "
                    "agregá tests y revisá el diff."
                ),
                workspace=before.workspace,
                acceptance_criteria=(
                    "GET /health/ready returns 200",
                    "RAG evidence is retrieved before implementation",
                    "a concrete targeted test passes",
                    "Reviewer accepts only in-scope changes",
                ),
                max_replans=1,
            )
            state = MainAgent(
                agents,
                tracer=tracer,
                initial_evidence_provider=ProjectMemoryEvidenceProvider(memory),
                context_manager=ContextManager(
                    budget=ContextBudget(
                        max_chars=14_000,
                        max_items=30,
                        summary_max_chars=1_200,
                        minimum_relevance=0.05,
                    ),
                    summary_provider=ExtractiveSummaryProvider(),
                ),
            ).run(request)
            persist_verified_memory(memory, state)
            root_observation.update(
                output={"status": state.status.value, "summary": final_summary(state)},
                metadata={
                    "llm_calls": backend.llm_calls,
                    "web_searches": web.searches,
                    "files_modified": [str(item.path) for item in state.files_modified],
                },
            )
    finally:
        store.close()
        memory.close()
        tracer.flush()

    if state is None or gateway is None or backend is None:
        raise RealDemoError("The real demo stopped before creating task state.")
    after = snapshot(before.workspace)
    artifact = build_real_artifact(
        run_id=run_id,
        state=state,
        before_checksum=before.checksum,
        after_checksum=after.checksum,
        trace_id=tracer.trace_id,
        gateway=gateway,
        backend=backend,
    )
    writer = ArtifactWriter(output_root)
    directory = writer.write(artifact, state)
    return DemoRun(
        artifact=writer.load(run_id),
        state=state,
        artifact_directory=directory,
        workspace=before.workspace,
    )
def _configured_path(value: Path, config_path: Path) -> Path:
    return value if value.is_absolute() else config_path.resolve().parent / value


def _secret(value: object) -> str:
    getter = getattr(value, "get_secret_value", None)
    if not callable(getter):
        raise RealDemoError("A required secret is unavailable.")
    result = getter()
    if not isinstance(result, str) or not result:
        raise RealDemoError("A required secret is empty.")
    return result


def _missing_settings(settings: RuntimeSettings) -> tuple[str, ...]:
    values = {
        "OPENAI_API_KEY": settings.openai_api_key,
        "TAVILY_API_KEY": settings.tavily_api_key,
        "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key,
        "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key,
    }
    return tuple(name for name, value in values.items() if value is None)
