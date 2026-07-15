# Estado compartido y memoria persistente

## Dos niveles distintos

El estado compartido describe una tarea en curso. La memoria conserva
conocimiento por proyecto entre sesiones. No son intercambiables:

- `TaskState` es un snapshot inmutable, coordinado por `MainAgent` y
  `TaskStateMachine`;
- `SQLiteMemoryRepository` persiste registros verificables por `project_id`;
- el historial conversacional no se usa como sustituto de ninguno de los dos.

## Estado de tarea

### Identidad y pedido

`TaskRequest` incluye `task_id`, `project_id`, `session_id`, pedido original,
workspace, criterios de aceptación, aprobación opcional del plan, máximo de
replans y timestamp.

### Acumulación

`TaskState` conserva:

- objetivo normalizado, plan y `plan_version`;
- `status`, `current_phase`, `revision` y eventos;
- `AgentResult` de cada invocación;
- evidencias y tipos de fuente consultados;
- archivos leídos y `FileChange` con digests/diff/autorización;
- tools, comandos, exit codes y output digests;
- aprobaciones pendientes/resueltas;
- errores, observaciones y decisiones;
- iteraciones, `replan_count` y resultado final.

Los agentes reciben un `AgentContext` acotado y devuelven un `AgentResult`;
nunca reciben una referencia al estado completo. `TaskStateMachine.accumulate`
agrega resultados y `transition` valida el grafo, incrementa revisión y genera
un `TaskEvent` append-only.

### Evidencia y provenance

`EvidenceSource` distingue `repository`, `memory`, `rag`, `web`, `tool_output` e
`inference`. Cada `Evidence` tiene id, referencia, contenido, locator opcional,
claims, confidence, supports y timestamp. Una inferencia es inválida sin ids en
`supports`; conservar soporte no la reclasifica como fuente externa.

`TaskFinalResult` agrupa todos los items por source y registra si Reviewer
aceptó. Un terminal `BLOCKED`, `FAILED` o `STOPPED_NO_EVIDENCE` puede no tener
resultado final.

## Modelo de memoria

`MemoryRecord` contiene:

| Campo | Significado |
|---|---|
| `id`, `project_id` | Identidad compuesta; el mismo id puede existir en proyectos diferentes. |
| `category` | Tipo de conocimiento recuperable. |
| `kind` | Observación, decisión, inferencia o resumen de sesión. |
| `content` | Texto persistido. |
| `source_type`, `source_reference` | Provenance que permite revalidar. |
| `confidence` | Valor entre 0 y 1, no una garantía de verdad. |
| `session_id` | Sesión que creó/actualizó el registro. |
| `created_at`, `updated_at` | Timestamps del registro. |
| `last_verified_at`, `stale_after`, `invalidated_at` | Freshness e invalidación. |
| `metadata` | Objeto JSON tipado como datos libres. |

Categorías implementadas: arquitectura, archivo importante, dependencia,
comando útil, convención, decisión, bug investigado, resultado de check y
resumen de sesión.

Los `kind` son:

- `observation`: dato observado en una fuente;
- `decision`: elección explícita, no hecho externo;
- `inference`: conclusión derivada;
- `session_summary`: síntesis de una sesión.

Una inferencia debe usar `source_type=inference` y enumerar soportes no vacíos
en `metadata.supports`. Esta validación impide guardar cualquier texto del
modelo como hecho sin clasificarlo, pero el llamador sigue siendo responsable
de decidir qué merece persistencia.

## SQLite y operaciones

La implementación usa `sqlite3` de la biblioteca estándar, tabla de versión de
schema y tabla `project_memory`:

```text
id, project_id, category, kind, content, source_type, source_reference,
confidence, session_id, created_at, updated_at, last_verified_at,
stale_after, metadata_json, invalidated_at
```

La primary key es `(project_id, id)` y existe un índice por proyecto/categoría.
El repository ofrece `save`, `get`, `search`, `mark_stale`, `verify`, `close` y
context manager.

`MemoryQuery` filtra por proyecto, categorías, kinds, freshness y límite. La
relevancia es lexical y se pondera por confidence; no usa embeddings. Por
defecto se excluyen registros stale. Un registro es stale si venció
`stale_after` o tiene `invalidated_at`; `verify` puede renovar verificación y
fecha de vencimiento.

## Evidencia entre sesiones

El escenario B guarda cuatro observaciones en la primera instancia y abre la
misma DB desde otra instancia para la sesión 2. Los cuatro textos recuperados
están en
[`evidence/runs/scenario-b-session-2/memory.json`](evidence/runs/scenario-b-session-2/memory.json)
y aparecen como `EvidenceSource.MEMORY` en el estado y las fuentes.

Esto prueba persistencia independiente del historial. No prueba selección
automática de memoria en cualquier tarea: `MainAgent` no consulta el repository
por sí mismo; la composición de demo recupera y convierte los registros a
evidencia antes de construir los agentes.

## Seguridad y operación

- el path de DB sale de configuración/composición, no de contenido del modelo;
- metadata debe ser JSON serializable;
- no deben persistirse secretos ni contenido de paths denegados;
- stale no se borra: queda disponible para auditoría si se consulta de forma
  explícita;
- tracing de `memory.load`/`memory.persist` es tolerante a fallos.

