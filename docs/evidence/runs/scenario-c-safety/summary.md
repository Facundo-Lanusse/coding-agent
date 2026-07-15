# scenario-c-safety

Status: `blocked`

Stopped after repeated failure and policy decisions; no third failing check ran.

## Sources

- [repository] README.md

## Commands

- `${PYTHON} -m compileall -q app`: executed, exit=0
- `${PYTHON} -m pytest scripts/check_contract.py::test_intentional_failure -q`: failed, exit=1
- `${PYTHON} -m compileall -q app`: executed, exit=0
- `${PYTHON} -m pytest scripts/check_contract.py::test_intentional_failure -q`: failed, exit=1

## Pending real commands

- `export OPENAI_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_BASE_URL`
- `coding-agent demo real --scenario rag`
