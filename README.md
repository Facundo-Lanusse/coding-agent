# Coding Agent Avanzado

Paquete Python para un coding agent especializado en repositorios Python/FastAPI.
La coordinación de `MainAgent`, Explorer, Researcher, Implementer, Tester y
Reviewer es una máquina de estados propia: no usa LangChain, LangGraph, CrewAI,
AutoGen ni OpenAI Agents SDK.

## Qué está implementado

- harness modelo-tool con plan mode, supervisión, límite de iteraciones y OpenAI
  Responses API;
- siete tools detrás de registry, permisos y validación de `agent.config.yaml`
  antes de cada ejecución;
- orquestador y estado compartido tipado con cinco subagentes;
- memoria por proyecto en SQLite, contexto presupuestado y detector de
  no-progreso;
- RAG técnico persistente en SQLite, embeddings OpenAI o fake determinista y
  fallback web detrás de una interfaz;
- tracing no-op, recording para tests y adaptador opcional Langfuse;
- fixture FastAPI y tres demos deterministas con artifacts reproducibles.

Hay una limitación de integración relevante: `coding-agent run` ejecuta el
harness básico con el adaptador OpenAI, no la composición de cinco agentes. Las
demos coordinadas sí recorren los cinco roles, pero usan un backend determinista
y cambios predefinidos. `coding-agent demo real` sólo valida prerrequisitos y se
detiene: todavía no realiza una corrida real multiagente ni genera un trace id
Langfuse. Esta diferencia no se oculta en la evidencia.

## Inicio rápido recomendado

El flujo principal de desarrollo es local: consume menos recursos que Docker y
permite iterar más rápido. Python queda fijado en `.python-version` y todos los
comandos habituales están centralizados en el `Makefile`:

```bash
make bootstrap
make check
```

El entorno queda en `.venv/`, ignorado por Git. `make bootstrap` no instala nada
fuera de las dependencias runtime y development declaradas en `pyproject.toml`.

## Requisitos e instalación limpia

Se requiere Python 3.11 o posterior. Desde la raíz del proyecto:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

La instalación editable incluye sólo las dependencias declaradas en
`pyproject.toml`. Langfuse y las dependencias HTTP de la fixture FastAPI no son
dependencias del paquete principal; su situación se explica en
[`docs/observability.md`](docs/observability.md) y
[`docs/testing.md`](docs/testing.md).

## Docker reproducible

Docker no es obligatorio para desarrollar, pero es el camino más simple para
onboarding y entornos homogéneos. El build es multi-stage:

- `builder` construye el wheel;
- `runtime` instala sólo el paquete y sus dependencias runtime, incluye la
  configuración, el corpus RAG y la fixture, y usa un usuario no-root;
- `development` agrega `.[dev]` para tests, lint, mypy y demos.

```bash
cp .env.example .env
docker compose build agent
docker compose run --rm agent --help
docker compose run --rm agent config validate --config agent.config.yaml
docker compose --profile dev run --rm dev python -m pytest -q
```

Las demos ejecutan checks con pytest y por eso usan la etapa development:

```bash
docker compose --profile dev run --rm dev \
  coding-agent demo all \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

`.dockerignore` excluye secretos, `.venv`, caches, DBs y outputs locales. En
Linux, ajustá `LOCAL_UID`/`LOCAL_GID` en `.env` para que los bind mounts conserven
tu usuario. La explicación completa está en
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Variables de entorno

La aplicación no lee `.env` implícitamente. Esto evita que el agente abra un
archivo que su propia política clasifica como secreto. Prepará el archivo local,
completalo y cargalo explícitamente en la shell:

```bash
cp .env.example .env
${EDITOR:-vi} .env
set -a
source .env
set +a
```

No versiones `.env`. Para el harness y embeddings reales se necesita
`OPENAI_API_KEY`; `OPENAI_MODEL` debe identificar un modelo disponible para la
cuenta. Langfuse usa `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` y, si
corresponde, `LANGFUSE_BASE_URL`. `TAVILY_API_KEY` está reservado en el ejemplo,
pero el proyecto no incluye un adaptador Tavily productivo.

## Validar la configuración

```bash
coding-agent config validate --config agent.config.yaml
```

El comando no usa red. El YAML es estricto: campos desconocidos, valores fuera
de rango o variables requeridas ausentes producen exit code 2. El workspace se
resuelve respecto del archivo de configuración. Además, el gateway recarga y
valida ese archivo antes de cada tool call.

## Ingerir y consultar el RAG

La variante reproducible no usa red ni credenciales:

```bash
coding-agent rag ingest ./rag_sources \
  --config agent.config.yaml \
  --fake-embeddings
coding-agent rag query "¿Cómo se declaran dependencies en FastAPI?" \
  --config agent.config.yaml \
  --fake-embeddings
```

La ingesta persiste en `data/vector_store/vectors.sqlite3`. Ingest y query deben
usar el mismo proveedor, dimensión, nombre y versión de colección. Para OpenAI,
omití `--fake-embeddings` y usá una colección/path separados de los vectores
fake. Más detalles: [`docs/rag.md`](docs/rag.md).

## Ejecutar el agente básico

Con `OPENAI_API_KEY` cargada:

```bash
coding-agent run \
  --config agent.config.yaml \
  --task "Analizá la estructura del proyecto" \
  --plan \
  --supervision
```

Este comando usa OpenAI Responses API y las tools del rol Implementer mediante
el policy gateway. La aprobación interactiva vive en la CLI; el núcleo no usa
`input()`. No lo presentes como la demo multiagente: esa integración real sigue
pendiente.

## Ejecutar las tres demos reproducibles

Ejecutar todo y regenerar cuatro bundles (A, B sesión 1, B sesión 2 y C):

```bash
coding-agent demo all \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

O ejecutar cada escenario:

```bash
coding-agent demo rag --runtime-root tmp/demo-runtime --output-root docs/evidence/runs
coding-agent demo memory --runtime-root tmp/demo-runtime --output-root docs/evidence/runs
coding-agent demo safety --runtime-root tmp/demo-runtime --output-root docs/evidence/runs
```

El reset seguro de una fixture manual es:

```bash
coding-agent demo reset --name manual --runtime-root tmp/demo-runtime
```

El escenario C termina correctamente en `blocked`; un exit code 0 de la CLI
significa que la demostración produjo ese estado esperado, no que el pedido
riesgoso haya sido ejecutado. El procedimiento y los criterios están en
[`docs/demo_runbook.md`](docs/demo_runbook.md).

## Tests y quality gates

Con el entorno activado:

```bash
pytest -q
ruff check src tests examples
mypy src tests
```

Los tests unitarios y E2E deterministas no llaman a OpenAI, web ni Langfuse. La
integración Langfuse está marcada y se salta si faltan SDK o credenciales:

```bash
pytest -m langfuse_integration -q
```

La fixture declara FastAPI, Uvicorn, HTTPX y pytest en su propio
`examples/fastapi_demo/seed/pyproject.toml`, pero esas dependencias no fueron
instaladas como parte del proyecto principal. Por eso las demos ejecutadas usan
`compileall` y tests de contrato estáticos, no los tests HTTP de FastAPI.

## Artifacts y trazas

Los resultados versionados están en [`docs/evidence/runs`](docs/evidence/runs):

- `run.json`: manifest schema 1.0 y `trace_id` nullable;
- `task_state.json`: estado completo;
- `summary.md`, `sources.json`, `commands.json`, `memory.json`, `events.json`;
- `diff.patch`: cambio observado en la copia runtime.

Las ejecuciones entregadas usan `provider_mode=deterministic_fake`,
`observability=recording` y `trace_id=null`. No existen capturas Langfuse reales.
Las instrucciones para obtenerlas sin fabricarlas están en
[`docs/evidence/screenshots/README.md`](docs/evidence/screenshots/README.md).

## Mapa de documentación

- [Caso de uso](docs/case_use.md)
- [Arquitectura](docs/architecture.md)
- [Estado y memoria](docs/state_and_memory.md)
- [RAG](docs/rag.md)
- [Políticas de seguridad](docs/security_policies.md)
- [Contexto y no-progreso](docs/context_and_loop_detection.md)
- [Observabilidad](docs/observability.md)
- [Testing](docs/testing.md)
- [Runbook de demos](docs/demo_runbook.md)
- [Reflexión](docs/reflection.md)
- [Checklist de entrega](docs/delivery_checklist.md)
- [Matriz requisito-evidencia](docs/requirements_matrix.md)
- [Desarrollo y contribución](CONTRIBUTING.md)

## Higiene del repositorio

Git excluye entornos, caches, coverage, builds, bases SQLite, `data/`, `tmp/`,
logs y secretos. Los artifacts requeridos del TP bajo `docs/evidence/runs/` no
se ignoran. `dist/` se reconstruye con `make build` y debe publicarse como asset
de un GitHub Release si se necesita distribuirlo, no como contenido versionado.

## Limitaciones conocidas

- no hay composición real OpenAI + cinco agentes desde la CLI;
- no hay ejecución Langfuse entregada, trace id ni screenshots;
- no existe proveedor web real compuesto por defecto;
- `ContextManager` y memoria están implementados y probados, pero el
  `MainAgent` genérico no los carga automáticamente; la demo B compone memoria
  explícitamente;
- los cambios de las demos A/B son deterministas y predefinidos, adecuados para
  reproducibilidad, no una demostración de generación autónoma;
- el umbral RAG de la demo es deliberadamente bajo y recupera las tres fuentes
  del corpus pequeño; no es una evaluación de calidad semántica de producción;
- los artifacts serializan workspace e intérprete como `${WORKSPACE}` y
  `${PYTHON}`; los digests conservan evidencia del output sin filtrar paths de
  la máquina que los produjo;
- el repositorio local quedó inicializado sobre `main`, pero no se creó un
  commit inicial: hasta que el responsable lo haga, no existe baseline para un
  diff Git completo;
- la imagen `python:3.11-slim` no agrega el binario Git porque sería una nueva
  dependencia de sistema no aprobada; las demos funcionan sin él, pero
  `repository_status` dentro del contenedor requiere autorizar esa incorporación.
