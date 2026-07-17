PYTHON ?= python3
VENV ?= .venv
DEMO_PROJECT ?= examples/fastapi_demo/seed
DEMO_VENV ?= $(DEMO_PROJECT)/.venv
PYTHON_BIN := $(VENV)/bin/python
CLI := $(VENV)/bin/coding-agent
DEMO_BIN := $(DEMO_VENV)/bin
DEMO_PYTHON_BIN := $(DEMO_BIN)/python

.PHONY: bootstrap doctor test demo-test coverage lint typecheck check build config rag-ingest demo-real

bootstrap: $(PYTHON_BIN) $(DEMO_PYTHON_BIN)
	$(PYTHON_BIN) -m pip install -e ".[dev]"
	$(DEMO_PYTHON_BIN) -m pip install -e "$(abspath $(DEMO_PROJECT))[dev]"
	@$(MAKE) --no-print-directory doctor

$(PYTHON_BIN):
	$(PYTHON) -m venv $(VENV)

$(DEMO_PYTHON_BIN):
	$(PYTHON) -m venv $(DEMO_VENV)

doctor:
	@test -x "$(PYTHON_BIN)" || (echo "Main environment missing: run make bootstrap."; exit 1)
	@test -x "$(CLI)" || (echo "CLI missing: run make bootstrap."; exit 1)
	@test -x "$(DEMO_BIN)/pytest" || (echo "FastAPI demo environment missing: run make bootstrap."; exit 1)
	@$(CLI) --help >/dev/null
	@$(DEMO_PYTHON_BIN) -m pytest --version >/dev/null
	@echo "Ready. Virtualenv activation is optional; use make check, make config or make demo-real."

test:
	$(PYTHON_BIN) -m pytest -q

demo-test:
	@test -x "$(DEMO_BIN)/pytest" || (echo "FastAPI demo environment missing: run make bootstrap."; exit 1)
	$(DEMO_PYTHON_BIN) -m pytest $(DEMO_PROJECT)/tests -q

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
	@test -x "$(DEMO_BIN)/pytest" || (echo "Demo environment missing: run make bootstrap."; exit 1)
	PATH="$(abspath $(DEMO_BIN)):$$PATH" $(CLI) demo real --scenario rag \
		--confirm-cost --max-llm-calls 20 \
		--max-iterations-per-agent 6 --max-output-tokens 2400 \
		--runtime-root tmp/demo-runtime --output-root docs/evidence/runs
