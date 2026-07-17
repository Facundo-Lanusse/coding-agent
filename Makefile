PYTHON ?= python3
VENV ?= .venv
DEMO_VENV ?= examples/fastapi_demo/seed/.venv
PYTHON_BIN := $(VENV)/bin/python
CLI := $(VENV)/bin/coding-agent
DEMO_BIN := $(DEMO_VENV)/bin

.PHONY: bootstrap test coverage lint typecheck check build config rag-ingest demo-real

bootstrap: $(PYTHON_BIN)
	$(PYTHON_BIN) -m pip install -e ".[dev]"

$(PYTHON_BIN):
	$(PYTHON) -m venv $(VENV)

test:
	$(PYTHON_BIN) -m pytest -q

coverage:
	$(PYTHON_BIN) -m pytest --cov=coding_agent --cov-branch --cov-report=term-missing -q

lint:
	$(VENV)/bin/ruff check src tests examples

typecheck:
	$(VENV)/bin/mypy src tests

check: test lint typecheck

build:
	$(PYTHON_BIN) -m build

config:
	$(CLI) config validate --config agent.config.yaml

rag-ingest:
	$(CLI) rag ingest ./rag_sources --config agent.config.yaml --fake-embeddings

demo-real:
	@test -x "$(DEMO_BIN)/pytest" || (echo "Demo environment missing: prepare $(DEMO_VENV) with the demo dev dependencies."; exit 1)
	PATH="$(abspath $(DEMO_BIN)):$$PATH" $(CLI) demo real --scenario rag \
		--confirm-cost --max-llm-calls 20 \
		--max-iterations-per-agent 6 --max-output-tokens 2400 \
		--runtime-root tmp/demo-runtime --output-root docs/evidence/runs
