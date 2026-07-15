from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml


@dataclass
class ProjectFixture:
    workspace: Path
    config_path: Path
    config: dict[str, object]

    def write_config(
        self,
        mutate: Callable[[dict[str, object]], None] | None = None,
    ) -> Path:
        data = deepcopy(self.config)
        if mutate is not None:
            mutate(data)
        self.config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return self.config_path


@pytest.fixture
def project(tmp_path: Path) -> ProjectFixture:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config: dict[str, object] = {
        "workspace": str(workspace),
        "llm": {
            "provider": "openai",
            "model": "configured-test-model",
            "max_output_tokens": 500,
            "store_responses": False,
        },
        "permissions": {
            "read": {"deny": [".env", ".env.*", "**/*.pem", "**/*.key", "secrets/**"]},
            "write": {
                "deny": [
                    ".env",
                    ".env.*",
                    ".github/**",
                    "**/*.lock",
                    "secrets/**",
                ]
            },
        },
        "commands": {
            "deny": ["rm -rf", "git push", "git reset --hard", "sudo"],
            "require_approval": ["python -m pip install", "git commit"],
            "allow_by_role": {
                "explorer": ["git status", "git diff", "rg", "find", "ls", "pwd"],
                "researcher": [],
                "implementer": [],
                "tester": ["pytest", "ruff", "mypy", "git status", "git diff"],
                "reviewer": ["git status", "git diff"],
            },
        },
        "execution": {
            "timeout_seconds": 1,
            "max_output_chars": 1_000,
            "max_read_bytes": 10_000,
            "max_list_entries": 100,
            "max_agent_iterations": 5,
            "max_identical_actions": 2,
            "max_identical_failures": 2,
        },
        "rag": {
            "enabled": False,
            "collection_name": "test",
            "collection_version": "test-v1",
            "persistence_path": str(tmp_path / "vectors"),
            "embedding_model": "test-embedding-model",
            "embedding_dimension": 16,
            "chunk_size_tokens": 100,
            "chunk_overlap_tokens": 10,
            "top_k": 3,
            "minimum_relevance": 0.5,
            "web_fallback": True,
            "allowed_url_domains": ["fastapi.tiangolo.com"],
        },
        "memory": {
            "enabled": False,
            "database_path": str(tmp_path / "memory.sqlite"),
        },
        "observability": {
            "provider": "langfuse",
            "enabled": False,
            "redact_sensitive_data": True,
            "capture_content": False,
            "max_payload_chars": 2_000,
        },
    }
    fixture = ProjectFixture(
        workspace=workspace,
        config_path=tmp_path / "agent.config.yaml",
        config=config,
    )
    fixture.write_config()
    return fixture
