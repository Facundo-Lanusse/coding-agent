# Arquitectura

## Objetivo de diseño

La solución separa dominio, infraestructura y composición. El dominio no conoce
Typer, OpenAI, Tavily, Langfuse ni SQLite concretos: consume protocolos y modelos
Pydantic. Esto permite probar todo el flujo con fakes y reemplazar proveedores sin
modificar la coordinación.

```text
CLI / runtime
    |
    v
MainAgent -> Explorer -> Researcher -> Implementer -> Tester -> Reviewer
    |            |           |             |            |          |
    +------------+-----------+-------------+------------+----------+
                         TaskState
    |
    +-> ContextManager / NoProgressDetector
    +-> MemoryRepository
    +-> ResearchService -> RAG -> Web fallback
    +-> AuthorizedToolGateway -> PolicyEngine -> ToolRegistry
    +-> Tracer -> Langfuse o NoOp
```

## Agente principal y roles

`MainAgent` es el único coordinador. Normaliza el pedido, crea el plan, mantiene
`TaskState`, entrega a cada rol sólo su slice de contexto y decide transiciones,
replanificación, aprobación o detención.

| Rol | Responsabilidad | Capacidades principales |
|---|---|---|
| Explorer | Entender estructura, dependencias y archivos relevantes. | lectura, listado, búsqueda y estado Git |
| Researcher | Recuperar evidencia RAG y, si falta, web oficial. | RAG y web |
| Implementer | Aplicar el cambio mínimo autorizado. | lectura, búsqueda y escritura |
| Tester | Ejecutar checks reales. | lectura y comandos allowlisted |
| Reviewer | Revisar diff, checks y alcance. | lectura y estado Git |

Los roles implementan la misma interfaz `Agent`; el backend real
`OpenAIAgentBackend` usa un loop Responses acotado y devuelve `AgentResult`
estructurado.

## Estado compartido

`TaskState` registra como mínimo:

- pedido, objetivo normalizado, plan, fase e iteraciones;
- resultados de los cinco roles;
- evidencia separada por repository, memory, RAG, web, tool output e inference;
- archivos leídos y modificados, comandos, checks y aprobaciones;
- errores, observaciones, decisiones y eventos append-only;
- resultado final y aceptación del Reviewer.

`TaskStateMachine` valida todas las transiciones. Los agentes nunca mutan el
estado: retornan resultados inmutables que el orquestador acumula.

## Memoria y contexto

`SQLiteMemoryRepository` persiste datos por `project_id`, categoría,
provenance, confidence y freshness. La composición real carga memoria antes de
Explorer y persiste sólo archivos, checks, decisiones y resumen verificados.

`ContextManager` prioriza evidencia, decisiones y errores abiertos dentro de un
presupuesto. `ExtractiveSummaryProvider` resume sin inventar hechos.
`NoProgressDetector` usa fingerprints para detectar comandos repetidos,
relecturas, ciclos A-B-A-B y fases sin delta; la tercera acción idéntica puede
bloquearse antes de ejecutarse.

## RAG y fallback web

`ResearchService` aplica esta secuencia:

1. embedding de la consulta;
2. recuperación top-k desde `SQLiteVectorStore`;
3. evaluación de threshold y cobertura;
4. si es insuficiente, una búsqueda Tavily limitada a dominios confiables;
5. devolución de evidencia con tipo y locator, sin mezclar inferencias.

Los proveedores de embeddings, vector store y web son interfaces reemplazables.

## Tools y políticas

Cada tool expone un `ToolSpec`: definición OpenAI, parámetros tipados y permisos
por rol. `ToolRegistry` registra implementaciones y puede descubrir entry points
del grupo `coding_agent.tools`. Agregar una tool no requiere modificar el loop,
el orquestador ni el gateway.

Toda ejecución pasa por `AuthorizedToolGateway`:

```text
Agent -> ScopedToolbox -> Gateway
                         -> reload + validate agent.config.yaml
                         -> PolicyEngine
                         -> approval when required
                         -> Tool.execute
```

La policy aplica containment canónico, denegación de secretos, escrituras
prohibidas, comandos bloqueados, approvals, timeout y límites de output.

## Observabilidad

`Tracer` es un puerto. `LangfuseTracer` y `NoOpTracer` implementan el mismo
contrato. La jerarquía registra tarea, agentes, generaciones, RAG/web, tools,
policy, checks, review y resultado. `Sanitizer` redacta claves, patrones
sensibles y rutas locales antes de persistir o enviar payloads.

## Composición real

`run_real_demo` es el composition root:

- copia el seed FastAPI a un workspace contenido;
- crea providers OpenAI, Tavily y Langfuse;
- ingiere el corpus RAG;
- conecta memoria, contexto, gateway y los cinco roles;
- ejecuta la tarea con presupuestos;
- persiste memoria verificada y un artifact portable.

El código auxiliar de artifact/memoria vive en
`demo/real_artifacts.py`; el slicing de contexto en
`orchestrator/context.py`; el mapeo de resultados OpenAI en
`agents/openai_support.py`. Así los módulos principales no mezclan demasiadas
responsabilidades.
