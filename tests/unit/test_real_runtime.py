from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest
from pydantic import SecretStr

from coding_agent.agents import LLMCallBudget, OpenAIAgentBackend
from coding_agent.approval import DenyAllApprovalProvider
from coding_agent.demo.scenarios import DemoScenarioRunner
from coding_agent.llm import LLMClient
from coding_agent.memory import MemoryQuery, SQLiteMemoryRepository
from coding_agent.models import LLMRequest
from coding_agent.observability import NoOpTracer
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.runtime import (
    ProjectMemoryEvidenceProvider,
    RealDemoError,
    _configured_path,
    _final_summary,
    _persist_verified_memory,
    _real_artifact,
    _secret,
    run_real_demo,
)
from coding_agent.state import EvidenceSource
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
    run = DemoScenarioRunner(
        seed_root=ROOT / "examples/fastapi_demo/seed",
        runtime_root=tmp_path / "runtime",
        rag_sources=ROOT / "rag_sources",
        output_root=tmp_path / "baseline-evidence",
    ).run_rag()
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=ROOT / "agent.config.yaml",
        approval_provider=DenyAllApprovalProvider(),
    )
    backend = OpenAIAgentBackend(NeverLLM(), call_budget=LLMCallBudget(5))

    artifact = _real_artifact(
        run_id="real-openai-unit",
        state=run.state,
        before_checksum=run.artifact.fixture_before,
        after_checksum=run.artifact.fixture_after,
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
        _persist_verified_memory(repository, run.state)
        matches = repository.search(
            MemoryQuery(project_id=run.state.request.project_id, text="check", limit=50)
        )
        recovered = ProjectMemoryEvidenceProvider(repository).load(run.state.request)
    finally:
        repository.close()

    assert matches
    assert recovered
    assert all(item.source is EvidenceSource.MEMORY for item in recovered)
    assert run.state.final_result is not None
    assert _final_summary(run.state) == run.state.final_result.summary
    assert _configured_path(Path("data/test.sqlite3"), ROOT / "agent.config.yaml") == (
        ROOT / "data/test.sqlite3"
    )
    assert _secret(SecretStr("hidden")) == "hidden"
    with pytest.raises(RealDemoError, match="unavailable"):
        _secret(object())
