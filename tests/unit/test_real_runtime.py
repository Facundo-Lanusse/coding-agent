from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest
from pydantic import SecretStr

from coding_agent.agents import LLMCallBudget, OpenAIAgentBackend
from coding_agent.approval import DenyAllApprovalProvider
from coding_agent.demo.real_artifacts import (
    build_real_artifact,
    final_summary,
    persist_verified_memory,
)
from coding_agent.llm import LLMClient
from coding_agent.memory import MemoryQuery, SQLiteMemoryRepository
from coding_agent.models import LLMRequest, ToolStatus
from coding_agent.observability import NoOpTracer
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.runtime import (
    ProjectMemoryEvidenceProvider,
    RealDemoError,
    _configured_path,
    _secret,
    run_real_demo,
)
from coding_agent.state import (
    AgentName,
    AgentResult,
    AgentResultStatus,
    CheckResult,
    Evidence,
    EvidenceGroup,
    EvidenceSource,
    FileChange,
    FileOperation,
    TaskFinalResult,
    TaskRequest,
    TaskState,
    TaskStatus,
    ToolInvocationRecord,
)
from coding_agent.tools import build_default_registry

ROOT = Path(__file__).resolve().parents[2]


class NeverLLM(LLMClient):
    def respond(self, request: LLMRequest) -> NoReturn:
        raise AssertionError(f"No LLM call expected: {request.instructions}")


def test_real_runtime_fails_before_reset_or_api_calls_without_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "TAVILY_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    runtime_root = tmp_path / "runtime"

    with pytest.raises(RealDemoError, match="Missing required environment variables"):
        run_real_demo(
            config_path=ROOT / "agent.config.yaml",
            seed_root=ROOT / "examples/fastapi_demo/seed",
            rag_sources=ROOT / "rag_sources",
            runtime_root=runtime_root,
            output_root=tmp_path / "evidence",
            approval_provider=DenyAllApprovalProvider(),
            max_llm_calls=10,
            max_iterations_per_agent=3,
            max_output_tokens=1_000,
        )

    assert not runtime_root.exists()


def test_real_runtime_rejects_output_budget_before_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "TAVILY_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.setenv(name, "configured-for-test")

    with pytest.raises(RealDemoError, match="max_output_tokens"):
        run_real_demo(
            config_path=ROOT / "agent.config.yaml",
            seed_root=ROOT / "examples/fastapi_demo/seed",
            rag_sources=ROOT / "rag_sources",
            runtime_root=tmp_path / "runtime",
            output_root=tmp_path / "evidence",
            approval_provider=DenyAllApprovalProvider(),
            max_llm_calls=10,
            max_iterations_per_agent=3,
            max_output_tokens=10,
        )

    assert not (tmp_path / "runtime").exists()


def test_real_runtime_stops_before_providers_if_langfuse_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "TAVILY_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.setenv(name, "configured-for-test")
    monkeypatch.setattr("coding_agent.runtime.create_tracer", lambda *args, **kwargs: NoOpTracer())

    with pytest.raises(RealDemoError, match="Langfuse"):
        run_real_demo(
            config_path=ROOT / "agent.config.yaml",
            seed_root=ROOT / "examples/fastapi_demo/seed",
            rag_sources=ROOT / "rag_sources",
            runtime_root=tmp_path / "runtime",
            output_root=tmp_path / "evidence",
            approval_provider=DenyAllApprovalProvider(),
            max_llm_calls=10,
            max_iterations_per_agent=3,
            max_output_tokens=1_000,
        )

    assert tuple((tmp_path / "runtime").glob("real-openai-*"))


def test_runtime_builds_artifact_and_persists_only_classified_memory(tmp_path: Path) -> None:
    request = TaskRequest(
        task_id="real-openai-unit",
        project_id="fastapi-demo",
        session_id="session",
        original_request="Add a verified FastAPI endpoint.",
        workspace=tmp_path,
    )
    check = CheckResult(
        name="pytest",
        passed=True,
        command=("pytest", "-q"),
        exit_code=0,
        output_digest="check-output",
    )
    state = TaskState(
        request=request,
        status=TaskStatus.COMPLETED,
        evidence=(
            Evidence(
                evidence_id="rag-fastapi",
                source=EvidenceSource.RAG,
                reference="rag_sources/fastapi_dependencies.md",
                content="Verified FastAPI evidence.",
            ),
        ),
        files_read=(Path("app/main.py"),),
        files_modified=(
            FileChange(
                path=Path("app/routers/health.py"),
                operation=FileOperation.MODIFIED,
                actor=AgentName.IMPLEMENTER,
                diff="--- a/app/routers/health.py\n+++ b/app/routers/health.py\n",
                authorized=True,
            ),
        ),
        commands=(("pytest", "-q"),),
        tool_invocations=(
            ToolInvocationRecord(
                call_id="test-call",
                tool_name="run_command",
                actor=AgentName.TESTER,
                status=ToolStatus.EXECUTED,
                exit_code=0,
                output_digest="check-output",
            ),
        ),
        agent_results=(
            AgentResult(
                agent=AgentName.TESTER,
                status=AgentResultStatus.SUCCEEDED,
                summary="Focused tests passed.",
                checks=(check,),
            ),
        ),
        final_result=TaskFinalResult(
            summary="Verified endpoint delivered.",
            evidence=(EvidenceGroup(source=EvidenceSource.RAG, items=()),),
            reviewer_accepted=True,
        ),
    )
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=ROOT / "agent.config.yaml",
        approval_provider=DenyAllApprovalProvider(),
    )
    backend = OpenAIAgentBackend(NeverLLM(), call_budget=LLMCallBudget(5))

    artifact = build_real_artifact(
        run_id="real-openai-unit",
        state=state,
        before_checksum="a" * 64,
        after_checksum="b" * 64,
        trace_id="trace-unit",
        gateway=gateway,
        backend=backend,
    )

    assert artifact.provider_mode == "real"
    assert artifact.trace_id == "trace-unit"
    assert artifact.sources
    assert artifact.commands
    assert artifact.diff

    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    try:
        persist_verified_memory(repository, state)
        matches = repository.search(
            MemoryQuery(project_id=state.request.project_id, text="check", limit=50)
        )
        recovered = ProjectMemoryEvidenceProvider(repository).load(state.request)
    finally:
        repository.close()

    assert matches
    assert recovered
    assert all(item.source is EvidenceSource.MEMORY for item in recovered)
    assert state.final_result is not None
    assert final_summary(state) == state.final_result.summary
    assert _configured_path(Path("data/test.sqlite3"), ROOT / "agent.config.yaml") == (
        ROOT / "data/test.sqlite3"
    )
    assert _secret(SecretStr("hidden")) == "hidden"
    with pytest.raises(RealDemoError, match="unavailable"):
        _secret(object())
