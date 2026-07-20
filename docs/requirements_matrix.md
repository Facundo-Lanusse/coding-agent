# Matriz requisito-evidencia

Esta matriz contiene sólo requisitos de la consigna. `PASS` significa que
existe código y prueba o artifact concreto.

| ID | Requisito | Evidencia principal | Estado |
|---|---|---|---|
| R01 | Evolucionar el coding agent previo sin framework de orquestación. | `harness/`, `orchestrator/`, dependencias de `pyproject.toml` | PASS |
| R02 | Agente principal y cinco subagentes con responsabilidades. | `agents/`, `orchestrator/main.py`, `test_orchestrator.py` | PASS |
| R03 | Estado compartido con pedido, avance, resultados, fuentes, cambios y observaciones. | `state/models.py`, artifacts A/B/C | PASS |
| R04 | Memoria persistente separada por proyecto. | `memory/sqlite.py`, `test_memory.py`, tarea B | PASS |
| R05 | Chunking, embeddings y almacenamiento vectorial. | `rag/`, `test_rag_*.py` | PASS |
| R06 | Recuperar y mostrar fuentes antes de decidir. | `ResearchService`, tarea A y corrida real | PASS |
| R07 | Separar repository, memory, RAG, web e inference. | `EvidenceSource`, `test_research_fallback.py` | PASS |
| R08 | RAG primero y web como fallback confiable. | `rag/research.py`, `tools/tavily.py` | PASS |
| R09 | Resumen y presupuesto de contexto. | `context/manager.py`, `test_context_manager.py` | PASS |
| R10 | Detectar repetición, cambiar estrategia o detenerse. | `context/progress.py`, tarea C | PASS |
| R11 | Explicar falta de evidencia. | estados `NO_EVIDENCE` y `STOPPED_NO_EVIDENCE` | PASS |
| R12 | Validar configuración antes de cada tool call. | `policies/gateway.py`, `test_tool_gateway.py` | PASS |
| R13 | Policies de lectura, escritura, comandos y aprobación. | `agent.config.yaml`, tests de policy | PASS |
| R14 | Integrar observabilidad y registrar el ciclo completo. | `observability/`, integración Langfuse verificada y corridas reales con trace id | PASS |
| R15 | Caso de uso concreto y verificable Python/FastAPI. | `docs/case_use.md`, fixture y diff real | PASS |
| R16 | Probar tarea RAG con fuentes. | tarea A | PASS |
| R17 | Probar memoria del proyecto. | tarea B, dos sesiones | PASS |
| R18 | Probar cambio de estrategia o detención. | tarea C | PASS |
| R19 | Agregar tools sin modificar el núcleo. | `ToolRegistry.discover`, `test_tool_registry.py` | PASS |
| D01 | Código completo funcionando. | `make check`, `make coverage` y `make build` verificados el 2026-07-20 | PASS |
| D02 | README de instalación, configuración y ejecución. | `README.md` | PASS |
| D03 | Descripción del caso y criterio de éxito. | `docs/case_use.md` | PASS |
| D04 | Explicación de arquitectura y estado. | `docs/architecture.md` | PASS |
| D05 | Documentación RAG. | `docs/rag.md` | PASS |
| D06 | Evidencia de al menos dos tareas. | `docs/evidence/README.md` | PASS |
| D07 | Captura de una traza completa. | `docs/evidence/screenshots/` | PASS |
| D08 | Reflexión breve. | `docs/reflection.md` | PASS |
