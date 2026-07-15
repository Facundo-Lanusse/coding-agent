# Project instructions — Advanced Coding Agent

## Objective

Evolve the legacy coding-agent notebook into a professional Python project that
satisfies `docs/consigna_tp_final.pdf`.

The concrete use case is an agent specialized in Python/FastAPI repositories. It
must analyze an unfamiliar repository, retrieve technical evidence, implement a
verifiable change, test it, review the diff, and preserve project memory across
sessions.

## Mandatory constraints

- Do not use LangChain, LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, or any
  other agent orchestration framework.
- Use the official OpenAI Python SDK directly, preferably through the Responses
  API, and implement orchestration explicitly in this repository.
- Preserve the useful concepts from
  `legacy/coding_agent_tp_anterior.ipynb`: tool loop, workspace isolation,
  read/write/list/command/web tools, plan mode, human supervision, iteration
  limit, and real test execution.
- Do not keep the final implementation inside a notebook.
- Never claim that a command or test passed unless it was actually executed.
- Never put API keys or secrets in source code, tests, logs, traces, fixtures,
  screenshots, or documentation.
- Do not read `.env`, private keys, PEM files, or `secrets/**`.
- Do not run `git push`, destructive filesystem commands, `sudo`, or hard resets.
- Do not commit unless the user explicitly asks.
- Do not add or install a production dependency without first explaining why it
  is needed and receiving explicit approval.
- Do not silently broaden the scope of a phase.
- Stop and report missing evidence when a requirement cannot be verified.

## Work protocol

At the beginning of every phase:

1. Read this file.
2. Read `docs/consigna_tp_final.pdf`.
3. Read `docs/implementation_plan.md` when it exists.
4. Inspect the current repository state and the previous phase results.
5. State the exact files expected to change.

During implementation:

- Make small cohesive changes.
- Keep domain logic independent from CLI and external providers.
- Use type hints and structured Pydantic models.
- Keep LLM, embeddings, web search, vector store, and observability behind
  interfaces so tests can use fakes.
- Validate `agent.config.yaml` before every tool invocation.
- Return structured results rather than relying only on free-form text.
- Add tests in the same phase as the implementation.
- Prefer deterministic unit tests and a small number of explicit integration or
  end-to-end tests.

At the end of every phase:

1. Run the phase tests.
2. Run the relevant lint and type checks.
3. Summarize the diff.
4. List commands executed and their exit codes.
5. Update `docs/implementation_plan.md`.
6. State any failures or unverified assumptions.
7. Stop before starting another phase.

## Target architecture

The implementation should converge toward these modules:

- `orchestrator`: explicit state machine and task coordination.
- `agents`: main agent plus Explorer, Researcher, Implementer, Tester, Reviewer.
- `tools`: common interface, registry, filesystem, shell, repository, web.
- `policies`: configuration validation and pre-execution authorization.
- `state`: shared task state, evidence, events, results.
- `memory`: persistent project memory in SQLite.
- `rag`: ingestion, chunking, embeddings, persistent vector retrieval.
- `context`: summarization, context budgeting, no-progress and loop detection.
- `observability`: Langfuse integration with a no-op fallback.
- `cli`: commands for running tasks, ingesting RAG, inspecting memory and demos.

## Quality gates

A phase is not complete unless:

- relevant tests pass;
- errors are not swallowed;
- the code can run without real API calls in unit tests;
- sensitive values are redacted;
- the implementation corresponds to an explicit requirement;
- documentation reflects the code that actually exists.
