from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

import pytest
from conftest import ProjectFixture

from coding_agent.agents import AgentContext
from coding_agent.config import ObservabilityConfig, load_config
from coding_agent.context import NoProgressDetector
from coding_agent.memory import SQLiteMemoryRepository
from coding_agent.models import (
    ApprovalDecision,
    FunctionCall,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    MessageInput,
    MessageRole,
)
from coding_agent.observability import (
    REDACTED,
    LangfuseTracer,
    NoOpTracer,
    ObservationKind,
    RecordingTracer,
    Sanitizer,
    TracedLLMClient,
    create_tracer,
)
from coding_agent.observability.langfuse import LangfuseObservationHandle
from coding_agent.orchestrator import MainAgent
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.rag import (
    CollectionSpec,
    EmbeddedChunk,
    RAGRetriever,
    ResearchService,
    RetrievalHit,
    UpsertReport,
)
from coding_agent.state import (
    AgentName,
    AgentResult,
    AgentResultStatus,
    CheckResult,
    TaskRequest,
)
from coding_agent.tools import (
    PermissionKind,
    StructuredTool,
    ToolContext,
    ToolExecution,
    ToolParameters,
    ToolPermissions,
    ToolRegistry,
    ToolRole,
)
from coding_agent.tools.web import SearchResult


class FakeHandle:
    def __init__(self, entry: dict[str, object]) -> None:
        self.entry = entry

    def update(self, **kwargs: object) -> object:
        updates = self.entry.setdefault("updates", [])
        assert isinstance(updates, list)
        updates.append(kwargs)
        return None

    @property
    def trace_id(self) -> str | None:
        context = self.entry.get("trace_context")
        if not isinstance(context, dict):
            return None
        value = context.get("trace_id")
        return value if isinstance(value, str) else None


class FakeManager(AbstractContextManager[LangfuseObservationHandle]):
    def __init__(self, client: FakeLangfuseClient, entry: dict[str, object]) -> None:
        self.client = client
        self.entry = entry

    def __enter__(self) -> LangfuseObservationHandle:
        self.client.stack.append(str(self.entry["id"]))
        return FakeHandle(self.entry)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.client.stack.pop()


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []
        self.stack: list[str] = []
        self.flushed = False

    def start_as_current_observation(
        self, **kwargs: object
    ) -> AbstractContextManager[LangfuseObservationHandle]:
        entry = {
            "id": f"lf-{len(self.entries) + 1}",
            "parent": self.stack[-1] if self.stack else None,
            **kwargs,
        }
        self.entries.append(entry)
        return FakeManager(self, entry)

    def flush(self) -> object:
        self.flushed = True
        return None

    def create_trace_id(self, *, seed: str | None = None) -> str:
        del seed
        return "a" * 32


class ExplodingLangfuseClient:
    def start_as_current_observation(
        self, **kwargs: object
    ) -> AbstractContextManager[LangfuseObservationHandle]:
        del kwargs
        raise RuntimeError("telemetry unavailable")

    def flush(self) -> object:
        raise RuntimeError("flush unavailable")


def test_noop_accepts_observations_without_swallowing_domain_errors() -> None:
    tracer = NoOpTracer()

    with (
        pytest.raises(ValueError, match="domain failure"),
        tracer.observe("task", input={"value": "safe"}) as observation,
    ):
        observation.update(output={"ok": True})
        raise ValueError("domain failure")

    tracer.flush()


def test_langfuse_adapter_sanitizes_and_preserves_hierarchy() -> None:
    client = FakeLangfuseClient()
    sanitizer = Sanitizer(environment={"OPENAI_API_KEY": "real-secret-value"})
    tracer = LangfuseTracer(client, sanitizer)

    with (
        tracer.observe(
            "task.run",
            kind=ObservationKind.TASK,
            input={"api_key": "real-secret-value"},
        ),
        tracer.observe(
            "llm.response",
            kind=ObservationKind.GENERATION,
            metadata={"authorization": "Bearer unsafe-token-value"},
        ) as generation,
    ):
        generation.update(output="real-secret-value")

    assert [entry["name"] for entry in client.entries] == ["task.run", "llm.response"]
    assert client.entries[1]["parent"] == client.entries[0]["id"]
    serialized = repr(client.entries)
    assert "real-secret-value" not in serialized
    assert REDACTED in serialized


def test_tracing_failure_never_breaks_domain_work() -> None:
    tracer = LangfuseTracer(ExplodingLangfuseClient(), Sanitizer(environment={}))

    with tracer.observe("task.run") as observation:
        observation.update(output={"result": 42})
        result = 42
    tracer.flush()

    assert result == 42


def test_langfuse_status_message_is_always_text() -> None:
    client = FakeLangfuseClient()
    tracer = LangfuseTracer(client, Sanitizer(environment={}))

    with tracer.observe("task.run") as observation:
        observation.update(error={"code": "failed"})

    updates = client.entries[0]["updates"]
    assert isinstance(updates, list)
    assert updates[0]["status_message"] == "{'code': 'failed'}"


def test_factory_uses_noop_without_credentials_or_sdk() -> None:
    config = ObservabilityConfig(
        provider="langfuse",
        enabled=True,
        redact_sensitive_data=True,
        capture_content=False,
        max_payload_chars=1_000,
    )

    tracer = create_tracer(config, environment={})

    assert isinstance(tracer, NoOpTracer)


def test_factory_sets_trace_id_and_maps_generation_usage_for_langfuse() -> None:
    client = FakeLangfuseClient()
    config = ObservabilityConfig(
        provider="langfuse",
        enabled=True,
        redact_sensitive_data=True,
        capture_content=False,
        max_payload_chars=1_000,
    )
    tracer = create_tracer(
        config,
        environment={
            "LANGFUSE_PUBLIC_KEY": "public-test-placeholder",
            "LANGFUSE_SECRET_KEY": "secret-test-placeholder",
        },
        client=client,
        trace_seed="task-1",
    )
    assert isinstance(tracer, LangfuseTracer)

    with (
        tracer.observe("task.run", kind=ObservationKind.TASK),
        tracer.observe(
            "llm.response",
            kind=ObservationKind.GENERATION,
            metadata={"model": "test-model"},
        ) as generation,
    ):
        generation.update(
            output="done",
            metadata={
                "input_tokens": 10,
                "output_tokens": 4,
                "total_tokens": 14,
                "cost": 0.01,
            },
        )

    assert tracer.trace_id == "a" * 32
    assert client.entries[0]["trace_context"] == {"trace_id": "a" * 32}
    assert "trace_context" not in client.entries[1]
    assert client.entries[1]["model"] == "test-model"
    updates = client.entries[1]["updates"]
    assert isinstance(updates, list)
    assert updates[0]["usage_details"] == {"input": 10, "output": 4, "total": 14}
    assert updates[0]["cost_details"] == {"total": 0.01}


class FakeLLM:
    def respond(self, request: LLMRequest) -> LLMResponse:
        del request
        return LLMResponse(
            response_id="response-1",
            model="test-model",
            text="done",
            usage=LLMUsage(input_tokens=10, output_tokens=4, total_tokens=14),
        )


def test_generation_records_tokens_latency_and_estimated_cost() -> None:
    tracer = RecordingTracer()
    client = TracedLLMClient(
        FakeLLM(),
        tracer,
        configured_model="test-model",
        cost_estimator=lambda model, input_tokens, output_tokens: 0.012,
    )

    client.respond(
        LLMRequest(
            instructions="Use evidence.",
            input=(MessageInput(role=MessageRole.USER, content="Question"),),
        )
    )

    record = tracer.records[0]
    assert record.kind is ObservationKind.GENERATION
    assert record.metadata["model"] == "test-model"
    assert record.metadata["input_tokens"] == 10
    assert record.metadata["output_tokens"] == 4
    assert record.metadata["cost"] == 0.012
    assert record.metadata["cost_source"] == "estimated"
    latency = record.metadata["latency_ms"]
    assert isinstance(latency, int | float)
    assert latency >= 0


class EmptyParameters(ToolParameters):
    pass


class InspectionTool(StructuredTool[EmptyParameters]):
    def __init__(self) -> None:
        super().__init__(
            name="inspection",
            description="Return an inspection result.",
            parameters_model=EmptyParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.REPOSITORY,
                allowed_roles=frozenset({ToolRole.EXPLORER}),
            ),
        )

    def _execute(self, context: ToolContext, parameters: EmptyParameters) -> ToolExecution:
        del context, parameters
        return ToolExecution(output="ok")


class EmptyStore:
    def ensure_collection(self, spec: CollectionSpec) -> None:
        del spec

    def upsert(
        self, spec: CollectionSpec, chunks: Sequence[EmbeddedChunk]
    ) -> UpsertReport:
        del spec, chunks
        return UpsertReport(inserted=0, skipped_duplicates=0)

    def query(
        self,
        collection: CollectionSpec,
        query_embedding: Sequence[float],
        *,
        top_k: int,
        minimum_score: float,
    ) -> tuple[RetrievalHit, ...]:
        del collection, query_embedding, top_k, minimum_score
        return ()

    def close(self) -> None:
        return None


class FakeEmbeddings:
    model = "fake"
    dimension = 2

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple((1.0, 0.0) for _ in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        del text
        return (1.0, 0.0)


class FakeWeb:
    def search(
        self,
        query: str,
        *,
        allowed_domains: tuple[str, ...],
        max_results: int,
    ) -> tuple[SearchResult, ...]:
        del query, allowed_domains, max_results
        return (
            SearchResult(
                title="FastAPI",
                url="https://fastapi.tiangolo.com/tutorial/dependencies/",
                snippet="Use Depends to declare dependencies.",
            ),
        )


def test_tool_rag_web_and_loop_are_recorded(project: ProjectFixture) -> None:
    tracer = RecordingTracer()
    gateway = AuthorizedToolGateway(
        ToolRegistry((InspectionTool(),)),
        config_path=project.config_path,
        tracer=tracer,
    )
    result = gateway.execute(
        FunctionCall(call_id="tool-1", name="inspection", arguments={}),
        role=ToolRole.EXPLORER,
    )
    collection = CollectionSpec(name="docs", version="v1", embedding_model="fake", dimension=2)
    retriever = RAGRetriever(
        embeddings=FakeEmbeddings(),
        store=EmptyStore(),
        collection=collection,
        top_k=3,
        minimum_score=0.8,
        tracer=tracer,
    )
    service = ResearchService(
        retriever=retriever,
        web_provider=FakeWeb(),
        web_fallback=True,
        trusted_domains=("fastapi.tiangolo.com",),
        tracer=tracer,
    )
    response = service.research("dependencies")
    detector = NoProgressDetector(max_identical_errors=1, tracer=tracer)
    signal = detector.record_command_error("pytest", code="failed", message="same")

    assert result.output == "ok"
    assert response.used_web
    assert signal is not None
    names = {record.name for record in tracer.records}
    assert {"tool.inspection", "policy.evaluate", "rag.retrieval", "web.fallback"} <= names
    assert "loop.no_progress" in names


class SuccessfulAgent:
    def __init__(self, name: AgentName) -> None:
        self.name = name
        self.role = ToolRole(name.value)

    @property
    def tool_names(self) -> frozenset[str]:
        return frozenset()

    def run(self, context: AgentContext) -> AgentResult:
        del context
        if self.name is AgentName.TESTER:
            return AgentResult(
                agent=self.name,
                status=AgentResultStatus.SUCCEEDED,
                summary="Checks passed.",
                checks=(CheckResult(name="pytest", passed=True, exit_code=0),),
            )
        if self.name is AgentName.REVIEWER:
            return AgentResult(
                agent=self.name,
                status=AgentResultStatus.SUCCEEDED,
                summary="Review accepted.",
                criteria_met=True,
            )
        return AgentResult(
            agent=self.name,
            status=AgentResultStatus.SUCCEEDED,
            summary=f"{self.name.value} completed.",
        )


def test_task_hierarchy_includes_agents_checks_review_and_result() -> None:
    tracer = RecordingTracer()
    names = (
        AgentName.EXPLORER,
        AgentName.RESEARCHER,
        AgentName.IMPLEMENTER,
        AgentName.TESTER,
        AgentName.REVIEWER,
    )
    request = TaskRequest(
        task_id="trace-task",
        project_id="demo",
        session_id="session",
        original_request="Inspect and verify the repository.",
        workspace=Path("/workspace"),
    )

    state = MainAgent({name: SuccessfulAgent(name) for name in names}, tracer=tracer).run(request)

    root = tracer.records[0]
    assert root.name == "task.run"
    assert root.parent_id is None
    assert all(
        record.parent_id == root.observation_id
        for record in tracer.records[1:]
        if record.name.startswith("agent.")
    )
    recorded_names = [record.name for record in tracer.records]
    assert "checks" in recorded_names
    assert "review" in recorded_names
    assert "result.final" in recorded_names
    assert root.metadata["task_id"] == "trace-task"
    assert root.metadata["project_id"] == "demo"
    assert root.metadata["session_id"] == "session"
    assert root.output is not None
    assert state.final_result is not None


def test_plan_approval_pause_and_resume_are_recorded() -> None:
    tracer = RecordingTracer()
    names = (
        AgentName.EXPLORER,
        AgentName.RESEARCHER,
        AgentName.IMPLEMENTER,
        AgentName.TESTER,
        AgentName.REVIEWER,
    )
    request = TaskRequest(
        task_id="approval-task",
        project_id="demo",
        session_id="session",
        original_request="Apply an approved change.",
        workspace=Path("/workspace"),
        require_plan_approval=True,
    )
    agent = MainAgent({name: SuccessfulAgent(name) for name in names}, tracer=tracer)

    paused = agent.run(request)
    completed = agent.resume(
        paused,
        ApprovalDecision(approved=True, reason="Approved by test."),
    )

    recorded_names = [record.name for record in tracer.records]
    assert "approval.plan" in recorded_names
    assert "approval.decision" in recorded_names
    assert completed.final_result is not None


def test_memory_load_is_recorded(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3", tracer=tracer)

    record = repository.get(project_id="demo", record_id="missing")
    repository.close()

    assert record is None
    assert tracer.records[0].name == "memory.load"
    assert tracer.records[0].output == {"found": False}


def test_configuration_load_is_traced(project: ProjectFixture) -> None:
    tracer = RecordingTracer()

    config = load_config(project.config_path, tracer=tracer)

    assert config.workspace == project.workspace
    assert tracer.records[0].name == "config.load_validate"
    assert tracer.records[0].output == {
        "valid": True,
        "llm_provider": "openai",
        "observability_enabled": False,
    }


def test_sanitizer_limits_payload_and_redacts_pattern_secrets() -> None:
    sanitizer = Sanitizer(max_payload_chars=128, environment={})

    credential = "Bearer fake-credential-for-redaction-test"
    sanitized = sanitizer.sanitize({"text": credential + "x" * 300})

    assert credential not in str(sanitized)
    assert len(str(sanitized)) <= 130


def test_sanitizer_replaces_local_home_path() -> None:
    sanitizer = Sanitizer(environment={})
    local_path = f"{Path.home()}/project/tests"

    sanitized = sanitizer.sanitize({"output": local_path})

    assert str(Path.home()) not in str(sanitized)
    assert "${HOME}/project/tests" in str(sanitized)
