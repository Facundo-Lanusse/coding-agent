Actuá como arquitecto de software senior. Esta es la Fase 00: auditoría y
planificación. No implementes todavía el código productivo.

Leé completamente:

- `AGENTS.md`
- `docs/consigna_tp_final.pdf`
- `docs/legacy_audit.md`
- `legacy/coding_agent_tp_anterior.ipynb`
- `agent.config.yaml`

Objetivo de esta fase:

1. Verificar por tu cuenta la arquitectura y el comportamiento del notebook.
2. Identificar exactamente qué partes se preservarán y cuáles se reemplazarán.
3. Comparar cada requisito de la consigna con el estado inicial.
4. Definir un caso de uso concreto y verificable:
   coding agent especializado en repositorios Python/FastAPI.
5. Diseñar una arquitectura sin frameworks de orquestación.
6. Diseñar el flujo coordinado del agente principal y:
   Explorer, Researcher, Implementer, Tester y Reviewer.
7. Diseñar estado compartido, memoria SQLite, RAG persistente, políticas,
   contexto, loop detection y observabilidad con Langfuse.
8. Definir interfaces para LLM, embeddings, web search, vector store y tracing,
   de modo que los tests usen fakes.
9. Definir una estrategia de pruebas y evidencias reproducibles.
10. Enumerar dependencias propuestas, separando runtime y development.

Creá únicamente documentación:

- `docs/implementation_plan.md`
- `docs/requirements_matrix.md`
- `docs/architecture.md`

`docs/requirements_matrix.md` debe contener una fila por cada requisito de la
consigna con estas columnas:

- requisito;
- evidencia esperada;
- estado inicial;
- módulo responsable;
- prueba que lo verificará;
- fase;
- estado.

`docs/implementation_plan.md` debe dividir el trabajo en las fases 01 a 09 y
tener criterios de aceptación objetivos por fase.

`docs/architecture.md` debe incluir:

- diagrama Mermaid;
- límites de cada módulo;
- modelo del estado compartido;
- permisos por subagente;
- flujo normal;
- flujo ante fallo;
- flujo de RAG primero y web como fallback;
- flujo de aprobación humana;
- estrategia de no-progreso.

Decisiones obligatorias:

- implementación como paquete Python, no notebook;
- OpenAI SDK directo con Responses API;
- no usar OpenAI Agents SDK;
- memoria persistente en SQLite;
- vector store local persistente;
- Langfuse con implementación no-op cuando esté deshabilitado;
- CLI reproducible;
- repositorio FastAPI de demostración bajo `examples/`.

No instales dependencias, no crees `src/` y no implementes funcionalidades.

Al terminar, mostrámelo en este formato:

A. Hallazgos verificados del notebook.
B. Requisitos faltantes.
C. Arquitectura propuesta.
D. Dependencias propuestas con justificación.
E. Plan por fases.
F. Riesgos y decisiones humanas pendientes.
G. Archivos creados.
H. Confirmación explícita de que no se modificó código productivo.

Después, detenete.
