Implementá únicamente la Fase 08: documentación, evidencias y preparación de la
entrega.

Revisá el código real y la consigna. No documentes funcionalidades inexistentes.

Completar como mínimo:

- `README.md`
- `docs/case_use.md`
- `docs/architecture.md`
- `docs/state_and_memory.md`
- `docs/rag.md`
- `docs/security_policies.md`
- `docs/context_and_loop_detection.md`
- `docs/observability.md`
- `docs/testing.md`
- `docs/demo_runbook.md`
- `docs/reflection.md`
- `docs/delivery_checklist.md`
- `docs/requirements_matrix.md`

El README debe permitir que otra persona:

1. cree un entorno limpio;
2. instale;
3. configure `.env`;
4. valide `agent.config.yaml`;
5. ingiera RAG;
6. ejecute el agente;
7. ejecute las tres demos;
8. corra tests, lint y type checking;
9. encuentre artifacts y trazas;
10. entienda limitaciones.

Documentar explícitamente:

- caso de uso y criterio de cumplimiento;
- rol del principal y cada subagente;
- estructura del estado compartido;
- esquema de memoria;
- fuentes RAG;
- chunking;
- embeddings;
- vector store;
- prioridad RAG y fallback web;
- políticas y aprobaciones;
- contexto y summaries;
- loop detection;
- observabilidad;
- qué información es repository/memory/RAG/web/inference.

Crear una reflexión honesta basada en las ejecuciones:

- qué funcionó;
- qué falló;
- cuándo hubo loops/no evidencia;
- qué estrategia cambió;
- limitaciones;
- mejoras futuras.

Evidencias requeridas:

- al menos dos tareas completas, preferentemente las tres;
- output relevante;
- fuentes recuperadas;
- explicación de qué se observa;
- trace ids;
- lugar reservado para capturas reales.

No inventes capturas ni resultados. Crear instrucciones precisas para que el
usuario guarde las capturas de Langfuse en
`docs/evidence/screenshots/`.

Ejecutá validaciones de links/rutas si existe una herramienta apropiada,
además de tests, Ruff y mypy. Actualizá matriz y detenete.
