Implementá únicamente la Fase 03: estado compartido, agente principal y cinco
subagentes coordinados con código propio.

Restricción absoluta:

- no usar LangChain, LangGraph, CrewAI, AutoGen, OpenAI Agents SDK ni un
  framework de orquestación;
- la coordinación debe ser una máquina de estados explícita del proyecto.

Modelos mínimos:

- `TaskRequest`
- `TaskState`
- `TaskStatus`
- `AgentName`
- `AgentResult`
- `Evidence`
- `EvidenceSource`
- `ToolInvocationRecord`
- `FileChange`
- `Decision`
- `TaskEvent`

El estado compartido debe registrar como mínimo:

- pedido original;
- objetivo normalizado;
- plan;
- estado y fase actual;
- resultados de cada subagente;
- fuentes consultadas;
- archivos leídos y modificados;
- comandos;
- aprobaciones;
- errores;
- observaciones;
- decisiones;
- iteraciones;
- resultado final.

Implementá:

- `BaseAgent`;
- `ExplorerAgent`;
- `ResearcherAgent`;
- `ImplementerAgent`;
- `TesterAgent`;
- `ReviewerAgent`;
- `MainAgent` u `Orchestrator`.

Responsabilidades:

- Explorer entiende estructura, arquitectura, dependencias, convenciones y
  archivos relevantes.
- Researcher recupera evidencia; inicialmente puede usar adaptadores fake o
  interfaces que se completarán en RAG/memoria.
- Implementer propone/aplica cambios autorizados.
- Tester ejecuta checks concretos y no inventa resultados.
- Reviewer inspecciona el diff y valida el pedido y los criterios.

Flujo mínimo:

```text
RECEIVED
-> PLANNING
-> EXPLORING
-> RESEARCHING
-> IMPLEMENTING
-> TESTING
-> REVIEWING
-> COMPLETED
```

Agregar transiciones explícitas para:

- `WAITING_APPROVAL`;
- `REPLANNING`;
- `BLOCKED`;
- `FAILED`;
- `STOPPED_NO_EVIDENCE`.

Cada subagente debe recibir solamente el contexto necesario y un conjunto de
tools acorde a sus permisos.

La respuesta final debe diferenciar evidencia de:

- repositorio;
- memoria;
- RAG;
- web;
- tool output;
- inferencia.

Tests obligatorios:

- flujo exitoso completo con agentes fake;
- orden correcto de subagentes;
- permisos diferentes;
- estado acumulado;
- tester fallido vuelve a replanificación dentro del límite;
- reviewer rechaza un cambio que no cumple el pedido;
- falta de evidencia produce estado bloqueado;
- aprobación pendiente pausa y luego reanuda;
- ningún agente puede usar una tool no asignada.

Ejecutá tests, Ruff y mypy. Actualizá docs y matriz. No implementes memoria ni
RAG todavía. Detenete.
