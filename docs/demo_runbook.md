# Runbook de las demos

## 1. Preparación

Desde la raíz:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
coding-agent config validate --config agent.config.yaml
```

Las demos deterministas no requieren `.env`, OpenAI, FastAPI instalado ni red.
No ejecutes sobre un workspace que contenga trabajo propio: el reset opera sólo
bajo el `runtime_root` elegido, pero cada escenario reemplaza su copia nombrada.

## 2. Ejecutar todo

```bash
coding-agent demo all \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

Resultado esperado:

```text
["scenario-a-rag", "scenario-b-session-1", "scenario-b-session-2", "scenario-c-safety"]
```

La CLI debe terminar con exit 0. Después, validá manifests:

```bash
python -m json.tool docs/evidence/runs/scenario-a-rag/run.json
python -m json.tool docs/evidence/runs/scenario-b-session-2/run.json
python -m json.tool docs/evidence/runs/scenario-c-safety/run.json
pytest tests/e2e/test_artifacts.py -q
```

## 3. Escenario A - RAG

```bash
coding-agent demo rag \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

Inspeccionar:

- [`scenario-a-rag/run.json`](evidence/runs/scenario-a-rag/run.json):
  `status=completed`, cuatro fuentes y tres archivos;
- [`sources.json`](evidence/runs/scenario-a-rag/sources.json): repository y RAG
  permanecen separados;
- [`diff.patch`](evidence/runs/scenario-a-rag/diff.patch): sólo router, service y
  test de readiness;
- [`commands.json`](evidence/runs/scenario-a-rag/commands.json): dos exit codes
  0.

Qué se observa: Explorer descubre la convención; Researcher consulta el corpus
persistente antes de implementar; el fake web lanzaría una excepción si fuera
invocado; Tester ejecuta checks; Reviewer acepta el alcance.

## 4. Escenario B - memoria

```bash
coding-agent demo memory \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

El comando crea una DB SQLite en `tmp/demo-runtime`, ejecuta sesión 1 y luego
abre otra instancia para sesión 2. Inspeccionar:

- [`scenario-b-session-1/run.json`](evidence/runs/scenario-b-session-1/run.json):
  análisis sin cambios;
- [`scenario-b-session-2/memory.json`](evidence/runs/scenario-b-session-2/memory.json):
  cuatro recuerdos recuperados;
- [`scenario-b-session-2/sources.json`](evidence/runs/scenario-b-session-2/sources.json):
  una fuente repository y cuatro memory;
- [`scenario-b-session-2/diff.patch`](evidence/runs/scenario-b-session-2/diff.patch):
  `/version` respeta router fino/service/schema.

Qué se observa: la segunda sesión no recibe el historial de la primera; usa
registros persistidos por `project_id` antes del cambio.

## 5. Escenario C - seguridad/no-progreso

```bash
coding-agent demo safety \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

`run.json` debe terminar `status=blocked`; es el resultado esperado. Verificar:

- [`events.json`](evidence/runs/scenario-c-safety/events.json): dos approvals,
  un deny, `loop.no_progress`, replan y budget agotado;
- [`commands.json`](evidence/runs/scenario-c-safety/commands.json): dos, no tres,
  ejecuciones del test fallido;
- [`diff.patch`](evidence/runs/scenario-c-safety/diff.patch): vacío;
- `files_modified` en `run.json`: vacío.

Qué se observa: instalar/commit no se ejecutan sin aprobación, `.github/**` se
deniega y la repetición cambia estrategia antes de un loop infinito.

## 6. Reset manual

```bash
coding-agent demo reset --name manual --runtime-root tmp/demo-runtime
```

El comando imprime el checksum del seed. La copia resultante está en
`tmp/demo-runtime/manual`; traversal, nombres anidados y symlinks externos se
rechazan.

## 7. Reproducibilidad y comparación

Los timestamps del estado pueden cambiar. Los checksums before/after, diffs,
fuentes y estados deben ser semánticamente iguales para la misma versión del
seed. Los bundles persistidos reemplazan el workspace por `${WORKSPACE}` y el
intérprete por `${PYTHON}` para evitar datos propios de la máquina.

No ejecutes `git commit` sobre los artifacts generados. Aunque el workspace ya
fue inicializado como repositorio Git, la revisión de la demo usa diffs
construidos desde before/after y no depende de `git diff`.

## 8. Demo real y Langfuse

La composición real está implementada, pero es deliberadamente opt-in. Cargá
las variables sin mostrar sus valores:

```bash
set -a
source .env
set +a
coding-agent config validate --config agent.config.yaml
```

Primero comprobá el guard sin costo; debe terminar con exit 2 y el mensaje
`No API call made`:

```bash
coding-agent demo real --scenario rag
```

Después verificá que exista el entorno aislado del demo y ejecutá una sola
corrida acotada. Anteponerlo al `PATH` permite que Tester encuentre
FastAPI/HTTPX sin instalarlos en el agente:

```bash
DEMO_BIN="$PWD/examples/fastapi_demo/seed/.venv/bin"
PATH="$DEMO_BIN:$PATH" .venv/bin/coding-agent demo real \
  --scenario rag \
  --confirm-cost \
  --max-llm-calls 20 \
  --max-iterations-per-agent 4 \
  --max-output-tokens 2400 \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

También existe `make demo-real`, que hace el preflight del entorno sin instalar
nada. Veinte llamadas permiten hasta cuatro turnos por cada uno de los cinco
roles; los tokens siguen limitados y Tavily admite como máximo una búsqueda
`basic`. La demo crea una copia nueva
`tmp/demo-runtime/real-openai-<fecha>`, nunca modifica `seed/`.

Al finalizar, la CLI imprime el directorio y el trace id. Verificá:

```bash
RUN_DIR="$(ls -dt docs/evidence/runs/real-openai-* | head -1)"
python -m json.tool "$RUN_DIR/run.json"
python -m json.tool "$RUN_DIR/task_state.json"
python -m json.tool "$RUN_DIR/sources.json"
python -m json.tool "$RUN_DIR/commands.json"
```

`run.json` debe mostrar `provider_mode=real`, `observability=langfuse` y
`trace_id` no vacío. `status=completed` sólo es válido si Tester guardó un check
real y Reviewer aceptó. Si termina con exit 2, no borres el artifact: inspeccioná
`task_state.json` y `events.json` antes de decidir si repetir. Las capturas se
guardan siguiendo
[`evidence/screenshots/README.md`](evidence/screenshots/README.md).
