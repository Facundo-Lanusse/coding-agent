# Estrategia de testing

## Principio

Los tests unitarios y end-to-end no realizan llamadas reales a OpenAI, Tavily ni
Langfuse. Los proveedores externos están detrás de interfaces y se reemplazan por
fakes. Sólo la prueba marcada `langfuse_integration` puede usar red y se omite
con una razón explícita si faltan credenciales.

## Capas

| Capa | Qué verifica |
|---|---|
| Unit | modelos, config, tools, policy, estado, memoria, RAG, contexto, backend y tracing |
| E2E focalizado | containment de fixture y escritura portable de artifacts |
| Integración opt-in | creación y flush de una observación Langfuse real |
| Demo real | coordinación de cinco roles sobre el seed FastAPI |

## Gates locales

```bash
make check
```

Ejecuta:

```bash
pytest -q
ruff check src tests examples
mypy src tests
```

Cobertura y build:

```bash
make coverage
make build
```

## Pruebas directamente asociadas a la consigna

- `test_orchestrator.py`: orden de cinco roles, estado, replanificación,
  aprobación, falta de evidencia y memoria/contexto.
- `test_tool_gateway.py`, `test_policy_paths.py` y
  `test_policy_commands.py`: validación previa, containment, secretos,
  escrituras, comandos y approvals.
- `test_memory.py`: persistencia, separación por proyecto y freshness.
- `test_rag_*.py`, `test_vector_store.py` y
  `test_research_fallback.py`: chunking, embeddings, persistencia, provenance
  y fallback web.
- `test_context_manager.py` y `test_no_progress.py`: resumen, presupuesto,
  ciclos, repetición y detención.
- `test_openai_agent_backend.py`: tool loop real, submission estructurada,
  límites y checks no inventados.
- `test_observability.py`: jerarquía, tokens, costo, redacción y tolerancia a
  fallos del tracer.
- `test_tool_registry.py`: nueva tool y descubrimiento por entry point sin
  modificar el núcleo.
- `test_real_runtime.py`: guardas de credenciales/costo, composición de
  artifacts y memoria verificada.
- `test_documentation.py`: documentos, links, artifacts y rutas CLI.

## Integración Langfuse

```bash
pytest -m langfuse_integration -q
```

Sin `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY` debe verse un skip, no un
PASS inventado. Con credenciales, conservar el output y el trace id para la
evidencia final.

## Fixture FastAPI

La fixture declara sus propias dependencias en
`examples/fastapi_demo/seed/pyproject.toml`. Para ejecutar sus tests HTTP:

```bash
python3.11 -m venv examples/fastapi_demo/seed/.venv
examples/fastapi_demo/seed/.venv/bin/python -m pip install -e \
  "examples/fastapi_demo/seed[dev]"
examples/fastapi_demo/seed/.venv/bin/python -m pytest \
  examples/fastapi_demo/seed/tests -q
```

La demo real usa ese binario desde `make demo-real`.

## Evidencia a conservar

Para la presentación posterior hacen falta los outputs completos de:

1. `git branch --show-current`;
2. `make check`;
3. `make coverage`;
4. tests HTTP de la fixture;
5. `make build`;
6. `git diff --stat main...entrega-tp`;
7. `git diff --name-status main...entrega-tp`;
8. una corrida `make demo-real` o el bundle real ya existente;
9. capturas de la traza Langfuse completa.
