# FastAPI demo fixture

`seed/` is the immutable initial repository. Demo commands copy it into a
contained runtime workspace before every scenario; agents never mutate the
seed. The project intentionally keeps HTTP routers thin: routers delegate to
services, while services construct the response schema. This non-obvious
convention is persisted by the memory scenario.

The declared FastAPI dependencies are not installed by the parent project.
Offline demo checks use only Python, pytest and static source inspection.

