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

`tests/integration/test_langfuse_integration.py` requiere variables Langfuse y
red. Sin ellas se salta. Es un smoke de una observación, no una demo
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

Tras integrar los providers reales autorizados, el checkpoint local fue:

```text
pytest -q                                    -> 142 passed, 1 skipped
ruff check src tests examples               -> exit 0
mypy src tests                               -> exit 0, 101 source files
coverage                                     -> 85% global, exit 0
coding-agent demo real --scenario rag       -> exit 2 sin --confirm-cost;
                                                cero llamadas externas
```

Después de los intentos reales se agregaron regresiones offline para el parsing
recuperable de JSON, la devolución del error sin ejecutar la tool y la
exposición exclusiva de `submit_agent_result` en el último turno. `make check`
volvió a terminar con exit 0. El cuarto intento externo llegó a Tester; su
`pytest -q` terminó 4 por ausencia de FastAPI en el entorno principal. El mismo
workspace modificado terminó `3 passed`, exit 0, con el entorno aislado del
demo. Los seis primeros intentos externos permanecen documentados como
`blocked`/`failed`, no como tareas completas.

El quinto intento recuperó memoria del cuarto y llegó a Researcher, que se
bloqueó al usar como vigente un fallo histórico de Tester. La prueba
`test_researcher_contract_does_not_require_downstream_tests` fija el contrato:
evidencia repository actual prevalece y Researcher no exige implementación ni
checks de roles posteriores.

El séptimo intento `real-openai-20260716-231650` terminó `completed`, exit 0:
Tester ejecutó `pytest -q` con `3 passed` y Reviewer aceptó. El trace id real es
`8248244a2224f1dc099fff1240e5c040`. Las regresiones adicionales comprueban argv
directo y sustitución del home local por `${HOME}` en artifacts/tracing.

El comando real con `--confirm-cost` no pertenece a la suite automática: usa
OpenAI, eventualmente Tavily y Langfuse, y debe ejecutarse manualmente con el
entorno del usuario. Sus instrucciones están en
[`demo_runbook.md`](demo_runbook.md).

El coverage global supera el mínimo de 85%, pero no todos los módulos críticos
alcanzan el 90% planificado: orquestación queda en 85% y los módulos de policy
entre 62% y 89%. El skip corresponde a Langfuse sin credenciales/red y no se
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
