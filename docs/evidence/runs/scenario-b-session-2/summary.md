# scenario-b-session-2

Status: `completed`

Diff is limited to the requested endpoint, tests and delegated service changes.

## Sources

- [repository] README.md
- [memory] README.md#Architecture
- [memory] README.md#Convention
- [memory] README.md#Commands
- [memory] app/main.py

## Commands

- `${PYTHON} -m compileall -q app`: executed, exit=0
- `${PYTHON} -m pytest scripts/check_contract.py::test_version_contract -q`: executed, exit=0

## Pending real commands

- `export OPENAI_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_BASE_URL`
- `coding-agent demo real --scenario rag`
