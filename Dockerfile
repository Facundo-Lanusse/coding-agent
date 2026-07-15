# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

FROM base AS builder

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install "build>=1.5,<2"

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m build --wheel --outdir /wheelhouse

FROM base AS runtime-base

ARG APP_UID=10001
ARG APP_GID=10001

RUN groupadd --gid "${APP_GID}" coding-agent \
    && useradd --uid "${APP_UID}" --gid coding-agent --create-home coding-agent

RUN --mount=type=bind,from=builder,source=/wheelhouse,target=/wheelhouse \
    python -m pip install /wheelhouse/*.whl

COPY --chown=coding-agent:coding-agent agent.config.yaml ./agent.config.yaml
COPY --chown=coding-agent:coding-agent rag_sources ./rag_sources
COPY --chown=coding-agent:coding-agent examples/fastapi_demo ./examples/fastapi_demo

RUN mkdir -p data tmp docs/evidence/runs \
    && chown -R coding-agent:coding-agent /workspace

USER coding-agent

FROM runtime-base AS development

USER root

COPY --chown=coding-agent:coding-agent pyproject.toml README.md CONTRIBUTING.md ./
COPY --chown=coding-agent:coding-agent src ./src
COPY --chown=coding-agent:coding-agent tests ./tests
COPY --chown=coding-agent:coding-agent docs ./docs

RUN python -m pip install -e ".[dev]"

ENV PYTHONPATH=/workspace/src

USER coding-agent
ENTRYPOINT []
CMD ["/bin/sh"]

FROM runtime-base AS runtime

ENTRYPOINT ["coding-agent"]
CMD ["--help"]
