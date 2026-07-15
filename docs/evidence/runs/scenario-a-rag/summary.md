# scenario-a-rag

Status: `completed`

Diff is limited to the requested endpoint, tests and delegated service changes.

## Sources

- [repository] README.md
- [rag] https://docs.pytest.org/en/stable/how-to/fixtures.html
- [rag] https://fastapi.tiangolo.com/tutorial/dependencies/
- [rag] https://pydantic.dev/docs/validation/latest/concepts/models/

## Commands

- `${PYTHON} -m compileall -q app`: executed, exit=0
- `${PYTHON} -m pytest scripts/check_contract.py::test_ready_contract -q`: executed, exit=0

## Pending real commands

- `export OPENAI_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_BASE_URL`
- `coding-agent demo real --scenario rag`
