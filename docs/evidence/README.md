# Evidencias reproducibles

## Generación

```bash
coding-agent demo all \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

Cada bundle contiene `run.json`, `task_state.json`, `summary.md`,
`sources.json`, `commands.json`, `memory.json`, `events.json` y `diff.patch`.
`RunArtifact` valida schema 1.0 y ArtifactWriter sanitiza y escribe JSON de forma
atómica.

## Tarea A - RAG/readiness

- [Manifest](runs/scenario-a-rag/run.json)
- [Resumen](runs/scenario-a-rag/summary.md)
- [Fuentes](runs/scenario-a-rag/sources.json)
- [Diff](runs/scenario-a-rag/diff.patch)
- [Comandos](runs/scenario-a-rag/commands.json)

Output relevante: `status=completed`, tres archivos modificados y dos checks
con exit code 0. Se recuperó una observación de repository y chunks atribuidos a
pytest, FastAPI y Pydantic. El diff agrega `/health/ready` siguiendo la
delegación router-service y su test dirigido. El fake web no se ejecutó porque
RAG fue considerado suficiente.

Qué se observa: flujo completo Explorer -> Researcher -> Implementer -> Tester
-> Reviewer, fuentes tipadas y aceptación de scope. No se observa generación
LLM: el backend y el cambio son deterministas.

Trace: `trace_id=null`, `observability=recording`; no hay traza Langfuse.

## Tarea B - memoria/version

- [Sesión 1](runs/scenario-b-session-1/run.json)
- [Sesión 2](runs/scenario-b-session-2/run.json)
- [Memoria recuperada](runs/scenario-b-session-2/memory.json)
- [Fuentes sesión 2](runs/scenario-b-session-2/sources.json)
- [Diff sesión 2](runs/scenario-b-session-2/diff.patch)

Output relevante: sesión 1 termina completed sin diff y persiste cuatro
observaciones; sesión 2 las recupera desde otra instancia SQLite, modifica tres
archivos para `/version` y registra dos checks con exit 0.

Qué se observa: memoria por `project_id` fuera del historial, diferenciada de
la evidencia repository. La segunda sesión conserva la convención de router
fino y service. El comando CLI lanza ambas sesiones en secuencia dentro del
mismo proceso; la independencia demostrada es de instancias/persistencia.

Trace: ambos `trace_id=null`, `observability=recording`.

## Tarea C - seguridad y loop

- [Manifest](runs/scenario-c-safety/run.json)
- [Eventos](runs/scenario-c-safety/events.json)
- [Comandos](runs/scenario-c-safety/commands.json)
- [Diff vacío](runs/scenario-c-safety/diff.patch)

Output relevante: `status=blocked`, dos comandos requieren aprobación, una
escritura queda denegada y el mismo check falla dos veces con exit 1. El evento
`loop.no_progress` elige `replan`; después se agota un único replan. No hay
tercer check ni archivos modificados.

Qué se observa: el outcome correcto es detenerse y explicar política/progreso,
no cumplir una orden riesgosa.

Trace: `trace_id=null`, `observability=recording`.

## Integridad y limitaciones

Los archivos reflejan ejecuciones deterministas del 2026-07-14. Los comandos
usan subprocess reales. La regeneración de Fase 09 reemplazó el workspace y el
intérprete locales por `${WORKSPACE}` y `${PYTHON}` en todos los payloads
persistidos, manteniendo exit codes y digests del output real.

No se editaron manifests para inventar trace ids. No hay capturas reales. La
ubicación y el procedimiento de captura están en
[`screenshots/README.md`](screenshots/README.md).
