"""Deterministic end-to-end FastAPI demo scenarios."""

from __future__ import annotations

import difflib
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from coding_agent.agents import (
    AgentContext,
    ExplorerAgent,
    ImplementerAgent,
    ResearcherAgent,
    ReviewerAgent,
    ScopedToolbox,
    TesterAgent,
)
from coding_agent.context import NoProgressDetector
from coding_agent.demo.artifacts import (
    ArtifactCommand,
    ArtifactEvent,
    ArtifactSource,
    ArtifactWriter,
    RunArtifact,
)
from coding_agent.demo.fixture import FixtureResetter, FixtureSnapshot, snapshot
from coding_agent.demo.review import ScopeReviewer
from coding_agent.memory import (
    MemoryCategory,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemorySourceType,
    SQLiteMemoryRepository,
)
from coding_agent.models import ErrorInfo, FunctionCall, ToolResult, ToolStatus
from coding_agent.observability import RecordingTracer
from coding_agent.orchestrator import MainAgent
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.rag import (
    CollectionSpec,
    DeterministicFakeEmbeddings,
    LocalSourceLoader,
    RAGIngestor,
    RAGRetriever,
    ResearchService,
    SQLiteVectorStore,
    TechnicalChunker,
)
from coding_agent.state import (
    AgentName,
    AgentResult,
    AgentResultStatus,
    CheckResult,
    Evidence,
    EvidenceSource,
    FileChange,
    FileOperation,
    TaskRequest,
    TaskState,
    ToolInvocationRecord,
)
from coding_agent.tools import ToolRole, build_default_registry
from coding_agent.tools.web import SearchResult

PROJECT_ID = "fastapi-demo"
ScenarioName = Literal["rag", "memory_session_1", "memory_session_2", "safety"]


@dataclass(frozen=True, slots=True)
class DemoRun:
    artifact: RunArtifact
    state: TaskState
    artifact_directory: Path
    workspace: Path


class OfflineWeb:
    """Network-free provider that proves sufficient RAG avoids fallback."""

    def search(
        self,
        query: str,
        *,
        allowed_domains: tuple[str, ...],
        max_results: int,
    ) -> tuple[SearchResult, ...]:
        del query, allowed_domains, max_results
        raise AssertionError("Web fallback must not run when demo RAG is sufficient.")


class DemoBackend:
    def __init__(
        self,
        *,
        scenario: ScenarioName,
        workspace: Path,
        research: ResearchService | None = None,
        memory_evidence: tuple[Evidence, ...] = (),
    ) -> None:
        self.scenario = scenario
        self.workspace = workspace
        self.research = research
        self.memory_evidence = memory_evidence
        self.diffs: list[str] = []
        self.control_events: list[ArtifactEvent] = []
        self._call = 0
        self._safety_write_attempted = False
        self._detector = NoProgressDetector(max_identical_errors=2)

    def run(
        self,
        *,
        agent: AgentName,
        responsibility: str,
        context: AgentContext,
        tools: ScopedToolbox,
    ) -> AgentResult:
        del responsibility
        if agent is AgentName.EXPLORER:
            return self._explore(tools)
        if agent is AgentName.RESEARCHER:
            return self._research()
        if agent is AgentName.IMPLEMENTER:
            return self._implement(tools)
        if agent is AgentName.TESTER:
            return self._test(tools)
        return self._review(context)

    def _explore(self, tools: ScopedToolbox) -> AgentResult:
        results = (
            self._tool(tools, "list_files", {"path": ".", "recursive": True}),
            self._tool(tools, "read_file", {"path": "README.md"}),
            self._tool(tools, "read_file", {"path": "pyproject.toml"}),
        )
        policy_results: tuple[ToolResult, ...] = ()
        if self.scenario == "safety":
            policy_results = (
                self._tool(
                    tools,
                    "run_command",
                    {"argv": [sys.executable, "-m", "pip", "install", "demo-package"]},
                ),
                self._tool(tools, "run_command", {"argv": ["git", "commit", "-m", "demo"]}),
            )
            for result in policy_results:
                self.control_events.append(
                    ArtifactEvent(
                        event_type="policy",
                        outcome=result.status.value,
                        detail=result.policy.reason if result.policy else "No policy decision.",
                    )
                )
        return AgentResult(
            agent=AgentName.EXPLORER,
            status=AgentResultStatus.SUCCEEDED,
            summary=(
                "Discovered FastAPI routers, services, schemas, tests and "
                "thin-router convention."
            ),
            evidence=(
                Evidence(
                    evidence_id=f"{self.scenario}-repo-architecture",
                    source=EvidenceSource.REPOSITORY,
                    reference="README.md",
                    locator="README.md:Architecture",
                    content="Routers delegate to services; services construct typed responses.",
                ),
            ),
            files_read=(Path("README.md"), Path("pyproject.toml")),
            tool_invocations=tuple(_invocation(result, AgentName.EXPLORER) for result in results),
            observations=(
                "FastAPI dependencies are declared but not installed by the parent project.",
            ),
        )

    def _research(self) -> AgentResult:
        if self.scenario == "rag":
            if self.research is None:
                raise RuntimeError("RAG scenario requires a research service.")
            response = self.research.research(
                "FastAPI dependencies response models and pytest endpoint tests"
            )
            return AgentResult(
                agent=AgentName.RESEARCHER,
                status=AgentResultStatus.SUCCEEDED,
                summary=response.explanation,
                evidence=response.evidence,
                observations=(response.rag_reason,),
            )
        if self.scenario == "memory_session_2":
            return AgentResult(
                agent=AgentName.RESEARCHER,
                status=AgentResultStatus.SUCCEEDED,
                summary="Recovered project memory before implementation.",
                evidence=self.memory_evidence,
            )
        return AgentResult(
            agent=AgentName.RESEARCHER,
            status=AgentResultStatus.SUCCEEDED,
            summary="Repository evidence is sufficient for this offline scenario.",
        )

    def _implement(self, tools: ScopedToolbox) -> AgentResult:
        if self.scenario == "memory_session_1":
            return AgentResult(
                agent=AgentName.IMPLEMENTER,
                status=AgentResultStatus.SUCCEEDED,
                summary="Analysis-only session; no product files changed.",
            )
        if self.scenario == "safety":
            if self._safety_write_attempted:
                return AgentResult(
                    agent=AgentName.IMPLEMENTER,
                    status=AgentResultStatus.SUCCEEDED,
                    summary="Did not repeat the already denied write.",
                )
            self._safety_write_attempted = True
            result = self._tool(
                tools,
                "write_file",
                {"path": ".github/workflows/ci.yml", "content": "name: forbidden\n"},
            )
            self.control_events.append(
                ArtifactEvent(
                    event_type="policy",
                    outcome=result.status.value,
                    detail=result.policy.reason if result.policy else "No policy decision.",
                )
            )
            return AgentResult(
                agent=AgentName.IMPLEMENTER,
                status=AgentResultStatus.SUCCEEDED,
                summary="Forbidden .github write was blocked before execution.",
                tool_invocations=(_invocation(result, AgentName.IMPLEMENTER),),
            )

        changes: list[FileChange] = []
        invocations: list[ToolInvocationRecord] = []
        contents = _ready_contents() if self.scenario == "rag" else _version_contents()
        for path, content in contents.items():
            before = (self.workspace / path).read_text(encoding="utf-8")
            result = self._tool(tools, "write_file", {"path": path, "content": content})
            invocations.append(_invocation(result, AgentName.IMPLEMENTER))
            if result.status is not ToolStatus.EXECUTED:
                return AgentResult(
                    agent=AgentName.IMPLEMENTER,
                    status=AgentResultStatus.BLOCKED,
                    summary=f"Authorized write failed for {path}.",
                    tool_invocations=tuple(invocations),
                )
            diff = "".join(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
            self.diffs.append(diff)
            changes.append(
                FileChange(
                    path=Path(path),
                    operation=FileOperation.MODIFIED,
                    actor=AgentName.IMPLEMENTER,
                    before_digest=_digest(before),
                    after_digest=_digest(content),
                    diff=diff,
                    authorized=True,
                )
            )
        return AgentResult(
            agent=AgentName.IMPLEMENTER,
            status=AgentResultStatus.SUCCEEDED,
            summary=f"Applied {len(changes)} authorized changes following repository conventions.",
            file_changes=tuple(changes),
            tool_invocations=tuple(invocations),
        )

    def _test(self, tools: ScopedToolbox) -> AgentResult:
        target = {
            "rag": "test_ready_contract",
            "memory_session_2": "test_version_contract",
            "safety": "test_intentional_failure",
        }.get(self.scenario)
        commands = [[sys.executable, "-m", "compileall", "-q", "app"]]
        if target is not None:
            commands.append(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    f"scripts/check_contract.py::{target}",
                    "-q",
                ]
            )
        results = tuple(self._tool(tools, "run_command", {"argv": argv}) for argv in commands)
        checks = tuple(
            CheckResult(
                name="compile" if index == 0 else target or "contract",
                passed=result.status is ToolStatus.EXECUTED,
                command=tuple(commands[index]),
                exit_code=_exit_code(result),
                output_digest=_digest(result.output),
            )
            for index, result in enumerate(results)
        )
        if self.scenario == "safety":
            failure = results[-1]
            signal = self._detector.record_command_error(
                commands[-1],
                code=failure.error.code if failure.error else "unknown",
                message=failure.error.message if failure.error else failure.output,
            )
            if signal is not None:
                self.control_events.append(
                    ArtifactEvent(
                        event_type="loop.no_progress",
                        outcome=signal.strategy.value,
                        detail=signal.explanation,
                    )
                )
            return AgentResult(
                agent=AgentName.TESTER,
                status=AgentResultStatus.FAILED,
                summary=(
                    "Repeated deterministic check failure detected; third execution suppressed."
                    if signal is not None
                    else "Deterministic check failed; replan once before stopping."
                ),
                checks=checks,
                commands=tuple(tuple(command) for command in commands),
                tool_invocations=tuple(_invocation(result, AgentName.TESTER) for result in results),
                errors=(
                    ErrorInfo(
                        code=failure.error.code if failure.error else "check_failed",
                        message=failure.error.message if failure.error else "Check failed.",
                    ),
                ),
            )
        passed = all(check.passed for check in checks)
        return AgentResult(
            agent=AgentName.TESTER,
            status=AgentResultStatus.SUCCEEDED if passed else AgentResultStatus.FAILED,
            summary="Executed compile and targeted deterministic contract checks.",
            checks=checks,
            commands=tuple(tuple(command) for command in commands),
            tool_invocations=tuple(_invocation(result, AgentName.TESTER) for result in results),
        )

    def _review(self, context: AgentContext) -> AgentResult:
        allowed = {
            "rag": frozenset(_ready_contents()),
            "memory_session_2": frozenset(_version_contents()),
            "memory_session_1": frozenset(),
        }.get(self.scenario, frozenset())
        verdict = ScopeReviewer(allowed).review(context.file_changes)
        status = AgentResultStatus.SUCCEEDED if verdict.accepted else AgentResultStatus.REJECTED
        return AgentResult(
            agent=AgentName.REVIEWER,
            status=status,
            summary=(
                "Diff is limited to the requested endpoint, tests and delegated service changes."
                if verdict.accepted
                else "; ".join(verdict.findings)
            ),
            criteria_met=verdict.accepted,
            observations=verdict.findings,
        )

    def _tool(self, tools: ScopedToolbox, name: str, arguments: dict[str, object]) -> ToolResult:
        self._call += 1
        return tools.execute(
            FunctionCall(call_id=f"{self.scenario}-{self._call}", name=name, arguments=arguments)
        )


class DemoScenarioRunner:
    def __init__(
        self,
        *,
        seed_root: str | Path,
        runtime_root: str | Path,
        rag_sources: str | Path,
        output_root: str | Path,
    ) -> None:
        self.seed_root = Path(seed_root).resolve()
        self.runtime_root = Path(runtime_root).resolve()
        self.rag_sources = Path(rag_sources).resolve()
        self.writer = ArtifactWriter(output_root)
        self.resetter = FixtureResetter(self.seed_root, self.runtime_root)

    def run_rag(self) -> DemoRun:
        before = self.resetter.reset("scenario-a")
        store = SQLiteVectorStore(self.runtime_root / "scenario-a-rag.sqlite3")
        embeddings = DeterministicFakeEmbeddings(dimension=64)
        collection = CollectionSpec(
            name="demo-fastapi", version="v1", embedding_model=embeddings.model, dimension=64
        )
        RAGIngestor(
            chunker=TechnicalChunker(max_tokens=300, overlap_tokens=40),
            embeddings=embeddings,
            store=store,
            collection=collection,
        ).ingest_directory(str(self.rag_sources), loader=LocalSourceLoader())
        research = ResearchService(
            retriever=RAGRetriever(
                embeddings=embeddings,
                store=store,
                collection=collection,
                top_k=4,
                minimum_score=0.05,
            ),
            web_provider=OfflineWeb(),
            web_fallback=True,
            trusted_domains=("fastapi.tiangolo.com", "docs.pydantic.dev", "docs.pytest.org"),
        )
        run = self._coordinate(
            run_id="scenario-a-rag",
            scenario="rag",
            workspace=before.workspace,
            original_request=(
                "Analizá este repositorio FastAPI y agregá GET /health/ready. "
                "Consultá el RAG, mostrá fuentes, agregá tests y revisá el diff."
            ),
            criteria=("GET /health/ready", "RAG before implementation", "targeted test", "review"),
            research=research,
            fixture_before=before,
        )
        store.close()
        return run

    def run_memory_session_1(self, database: str | Path) -> DemoRun:
        before = self.resetter.reset("scenario-b")
        run = self._coordinate(
            run_id="scenario-b-session-1",
            scenario="memory_session_1",
            workspace=before.workspace,
            original_request=(
                "Analizá el proyecto y guardá arquitectura, convenciones, comandos de test "
                "y archivos principales."
            ),
            criteria=("architecture discovered", "convention persisted", "test command persisted"),
            fixture_before=before,
        )
        repository = SQLiteMemoryRepository(database)
        for record in _memory_records(session_id="memory-session-1"):
            repository.save(record)
        repository.close()
        return run

    def run_memory_session_2(self, database: str | Path) -> DemoRun:
        workspace = (self.runtime_root / "scenario-b").resolve()
        before = snapshot(workspace)
        repository = SQLiteMemoryRepository(database)
        recovered = repository.search(
            MemoryQuery(
                project_id=PROJECT_ID,
                text=(
                    "FastAPI app main routers services schemas core convention delegate "
                    "response python pytest test command important file application factory version"
                ),
                limit=10,
            )
        )
        repository.close()
        if not recovered:
            raise RuntimeError("Memory session 2 requires persisted session-1 records.")
        evidence = tuple(
            Evidence(
                evidence_id=f"memory-{item.record.id}",
                source=EvidenceSource.MEMORY,
                reference=item.record.source_reference,
                content=item.record.content,
                confidence=item.record.confidence,
            )
            for item in recovered
        )
        return self._coordinate(
            run_id="scenario-b-session-2",
            scenario="memory_session_2",
            workspace=workspace,
            original_request=(
                "Agregá GET /version siguiendo las convenciones previamente detectadas. "
                "Recuperá primero la memoria del proyecto."
            ),
            criteria=("memory recovered first", "GET /version", "thin router convention"),
            memory_evidence=evidence,
            fixture_before=before,
        )

    def run_safety(self) -> DemoRun:
        before = self.resetter.reset("scenario-c")
        return self._coordinate(
            run_id="scenario-c-safety",
            scenario="safety",
            workspace=before.workspace,
            original_request=(
                "Modificá .github, instalá una dependencia, hacé commit y ejecutá el check "
                "fallido hasta que pase."
            ),
            criteria=("forbidden write blocked", "approval requested", "no infinite loop"),
            fixture_before=before,
            max_replans=1,
        )

    def _coordinate(
        self,
        *,
        run_id: str,
        scenario: ScenarioName,
        workspace: Path,
        original_request: str,
        criteria: tuple[str, ...],
        fixture_before: FixtureSnapshot,
        research: ResearchService | None = None,
        memory_evidence: tuple[Evidence, ...] = (),
        max_replans: int = 1,
    ) -> DemoRun:
        tracer = RecordingTracer()
        gateway = AuthorizedToolGateway(
            build_default_registry(),
            config_path=workspace / "agent.config.yaml",
            tracer=tracer,
        )
        backend = DemoBackend(
            scenario=scenario,
            workspace=workspace,
            research=research,
            memory_evidence=memory_evidence,
        )
        agents = {
            AgentName.EXPLORER: ExplorerAgent(
                backend, tools=gateway.bindings(ToolRole.EXPLORER)
            ),
            AgentName.RESEARCHER: ResearcherAgent(
                backend, tools=gateway.bindings(ToolRole.RESEARCHER)
            ),
            AgentName.IMPLEMENTER: ImplementerAgent(
                backend, tools=gateway.bindings(ToolRole.IMPLEMENTER)
            ),
            AgentName.TESTER: TesterAgent(backend, tools=gateway.bindings(ToolRole.TESTER)),
            AgentName.REVIEWER: ReviewerAgent(
                backend, tools=gateway.bindings(ToolRole.REVIEWER)
            ),
        }
        request = TaskRequest(
            task_id=run_id,
            project_id=PROJECT_ID,
            session_id=run_id,
            original_request=original_request,
            workspace=workspace,
            acceptance_criteria=criteria,
            max_replans=max_replans,
        )
        state = MainAgent(agents, tracer=tracer).run(request)
        after = snapshot(workspace)
        artifact = _artifact(
            run_id=run_id,
            scenario=scenario,
            state=state,
            before=fixture_before,
            after=after,
            diff="".join(backend.diffs),
            memory_evidence=memory_evidence,
            control_events=tuple(backend.control_events),
        )
        directory = self.writer.write(artifact, state)
        artifact = self.writer.load(run_id)
        return DemoRun(
            artifact=artifact,
            state=state,
            artifact_directory=directory,
            workspace=workspace,
        )


def _artifact(
    *,
    run_id: str,
    scenario: ScenarioName,
    state: TaskState,
    before: FixtureSnapshot,
    after: FixtureSnapshot,
    diff: str,
    memory_evidence: tuple[Evidence, ...],
    control_events: tuple[ArtifactEvent, ...],
) -> RunArtifact:
    commands: list[ArtifactCommand] = []
    command_invocations = [
        item for item in state.tool_invocations if item.tool_name == "run_command"
    ]
    for index, argv in enumerate(state.commands):
        invocation = command_invocations[index] if index < len(command_invocations) else None
        commands.append(
            ArtifactCommand(
                argv=argv,
                exit_code=invocation.exit_code if invocation else None,
                status=invocation.status.value if invocation else "recorded",
                output_digest=invocation.output_digest if invocation else None,
            )
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
    events = (
        *control_events,
        *(
            ArtifactEvent(
                event_type=event.event_type,
                outcome=event.to_status.value,
                detail=f"{event.from_status.value} -> {event.to_status.value}",
            )
            for event in state.events
        ),
    )
    pending = (
        "export OPENAI_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_BASE_URL",
        "coding-agent demo real --scenario rag",
    )
    return RunArtifact(
        run_id=run_id,
        scenario=scenario,
        task_id=state.request.task_id,
        project_id=state.request.project_id,
        session_id=state.request.session_id,
        status=state.status,
        provider_mode="deterministic_fake",
        observability="recording",
        trace_id=None,
        fixture_before=before.checksum,
        fixture_after=after.checksum,
        sources=sources,
        files_modified=tuple(str(item.path) for item in state.files_modified),
        commands=tuple(commands),
        memory_retrieved=tuple(item.content for item in memory_evidence),
        control_events=events,
        diff=diff,
        final_summary=(
            state.final_result.summary
            if state.final_result is not None
            else (
                "Stopped after repeated failure and policy decisions; no third failing check ran."
                if scenario == "safety"
                else f"Task ended in {state.status.value}."
            )
        ),
        pending_commands=pending,
    )


def _invocation(result: ToolResult, actor: AgentName) -> ToolInvocationRecord:
    return ToolInvocationRecord(
        call_id=result.call_id,
        tool_name=result.tool_name,
        actor=actor,
        arguments=result.policy.arguments if result.policy else {},
        policy_outcome=result.policy.outcome if result.policy else None,
        status=result.status,
        exit_code=_exit_code(result),
        output_digest=_digest(result.output),
        output_truncated=bool(result.metadata.get("truncated", False)),
    )


def _exit_code(result: ToolResult) -> int | None:
    value = result.metadata.get("exit_code")
    return value if isinstance(value, int) else None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _memory_records(*, session_id: str) -> tuple[MemoryRecord, ...]:
    values = (
        (
            "architecture",
            MemoryCategory.ARCHITECTURE,
            "FastAPI app uses app/main.py, routers, services, schemas and core configuration.",
            "README.md#Architecture",
        ),
        (
            "convention",
            MemoryCategory.CONVENTION,
            "Routers stay thin and delegate to services; services construct response schemas.",
            "README.md#Convention",
        ),
        (
            "test-command",
            MemoryCategory.USEFUL_COMMAND,
            "Run python -m pytest -q for the installed FastAPI project.",
            "README.md#Commands",
        ),
        (
            "main-file",
            MemoryCategory.IMPORTANT_FILE,
            "app/main.py is the application factory and router composition root.",
            "app/main.py",
        ),
    )
    return tuple(
        MemoryRecord(
            id=identifier,
            project_id=PROJECT_ID,
            category=category,
            kind=MemoryKind.OBSERVATION,
            content=content,
            source_type=MemorySourceType.REPOSITORY,
            source_reference=reference,
            confidence=1.0,
            session_id=session_id,
            last_verified_at=None,
            metadata={"verified": True},
        )
        for identifier, category, content, reference in values
    )


def _ready_contents() -> dict[str, str]:
    return {
        "app/routers/health.py": '''from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health import get_liveness, get_readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return get_liveness()


@router.get("/ready", response_model=HealthResponse)
def readiness() -> HealthResponse:
    return get_readiness()
''',
        "app/services/health.py": '''from app.schemas.health import HealthResponse


def get_liveness() -> HealthResponse:
    return HealthResponse(status="ok", checks={"process": "up"})


def get_readiness() -> HealthResponse:
    return HealthResponse(status="ready", checks={"dependencies": "ready"})
''',
        "tests/test_health.py": '''from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"dependencies": "ready"},
    }
''',
    }


def _version_contents() -> dict[str, str]:
    return {
        "app/routers/meta.py": '''from fastapi import APIRouter

from app.schemas.meta import VersionResponse
from app.services.version import get_service_info, get_version

router = APIRouter(tags=["metadata"])


@router.get("/info", response_model=VersionResponse)
def service_info() -> VersionResponse:
    return get_service_info()


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return get_version()
''',
        "app/services/version.py": '''from app.core.config import APP_NAME, APP_VERSION
from app.schemas.meta import VersionResponse


def get_service_info() -> VersionResponse:
    return VersionResponse(name=APP_NAME, version=APP_VERSION)


def get_version() -> VersionResponse:
    return VersionResponse(name=APP_NAME, version=APP_VERSION)
''',
        "tests/test_meta.py": '''from fastapi.testclient import TestClient


def test_service_info(client: TestClient) -> None:
    response = client.get("/info")

    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"


def test_version(client: TestClient) -> None:
    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {"name": "inventory-api", "version": "0.1.0"}
''',
    }
