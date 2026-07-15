# Estrategia de pruebas

## Objetivo

La suite prioriza comportamiento determinista y prueba los puertos con fakes.
Por defecto no usa OpenAI, web ni Langfuse, y no necesita leer `.env`.

## Capas

### Unitarias

`tests/unit/` cubre:

- configuración tipada, variables y errores explícitos;
- harness y adaptador Responses con SDK falso;
- registry, tools, containment, comandos, policy y aprobación;
- agentes, permisos, state machine y replanificación;
- memoria SQLite temporal, freshness y separación por proyecto;
- selección de contexto, summary fake y no-progreso;
- loaders, chunking, embeddings fake, vector store y RAG/web fallback;
- sanitización, no-op, recording y adaptador Langfuse con cliente fake;
- CLI y documentación/rutas locales.

### Integración opt-in

`tests/integration/test_langfuse_integration.py` requiere variables Langfuse,
SDK y red. Sin ellas se salta. Es un smoke de una observación, no una demo
multiagente completa.

### End-to-end deterministas

`tests/e2e/` valida reset de fixture, escenarios A/B/C, schemas de artifacts,
containment y Reviewer. Usa copias bajo un temporary directory, fakes de
providers y subprocess reales para `compileall`/tests de contrato.

## Comandos

```bash
pytest -q
ruff check src tests examples
mypy src tests
```

Ejecuciones focalizadas:

```bash
pytest tests/unit -q
pytest tests/e2e -q
pytest -m langfuse_integration -q
pytest tests/unit/test_documentation.py -q
```

`mypy` valida `src` y `tests`, tal como declara `pyproject.toml`; el código de la
fixture bajo `examples` sólo entra en Ruff en el gate principal.

## Qué se ejecuta realmente en las demos

Los artifacts registran argv, status, exit code y digest. A/B ejecutan
`python -m compileall -q app` y un test dirigido de
`scripts/check_contract.py`. C ejecuta el check intencionalmente fallido dos
veces. Son subprocess reales dentro de la copia runtime.

Los tests HTTP de `examples/fastapi_demo/seed/tests` importan FastAPI/HTTPX,
pero no se ejecutaron porque las dependencias opcionales de la fixture no están
instaladas en el entorno principal. Instalar el paquete demo es una acción
separada que debe aprobarse:

```bash
python -m pip install -e "examples/fastapi_demo/seed[dev]"
pytest examples/fastapi_demo/seed/tests -q
```

Esos comandos son pendientes, no resultados entregados.

## Evidencia de resultados

La corrida de auditoría de Fase 09 fue:

```text
pytest --cov=coding_agent --cov-branch -q  -> 119 passed, 1 skipped; 87%
ruff check src tests examples                -> exit 0
mypy src tests                               -> exit 0, 94 source files
python -m build                              -> exit 0
clean wheel install + coding-agent --help   -> exit 0
coding-agent demo all                       -> exit 0
```

El coverage global supera el mínimo de 85%, pero no todos los módulos críticos
alcanzan el 90% planificado: orquestación queda en 83% y los módulos de policy
entre 62% y 89%. El skip corresponde a Langfuse sin SDK/credenciales y no se
contabiliza como prueba real de observabilidad. El detalle está en
[`final_audit.md`](final_audit.md).

## Validación de documentación

`tests/unit/test_documentation.py` comprueba que existan los documentos
obligatorios, que los links/rutas Markdown locales resuelvan y que los cuatro
bundles tengan los ocho archivos del schema de evidencia. Ignora URLs HTTP(S),
porque su disponibilidad no es determinista ni se debe confundir con una
validación de provenance.

## Criterio para afirmar “pasó”

Sólo se documenta un resultado cuando el comando fue ejecutado en este
workspace y devolvió el exit code indicado. Un fake prueba lógica de
integración, no disponibilidad del proveedor. Un skip no satisface un requisito
externo. Un escenario esperado `blocked` puede ser una prueba exitosa si sus
asserts demuestran que los efectos riesgosos no ocurrieron.
