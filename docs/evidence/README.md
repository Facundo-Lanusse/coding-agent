# Evidencias de ejecución

Los bundles son JSON/Markdown sanitizados. Cada directorio conserva `run.json`,
`task_state.json`, fuentes, comandos, memoria, eventos, diff y resumen. Las
rutas locales se reemplazan por marcadores y no contienen credenciales.

## Tarea A - RAG y endpoint de readiness

Directorio: [scenario-a-rag](runs/scenario-a-rag/).

Se observa la secuencia Explorer -> Researcher -> Implementer -> Tester ->
Reviewer. Researcher recupera documentación FastAPI antes del cambio, no usa web
porque el RAG es suficiente, Implementer agrega `GET /health/ready`, Tester
ejecuta checks con exit 0 y Reviewer acepta el diff.

Archivos clave:

- [resumen](runs/scenario-a-rag/summary.md)
- [fuentes](runs/scenario-a-rag/sources.json)
- [comandos](runs/scenario-a-rag/commands.json)
- [diff](runs/scenario-a-rag/diff.patch)

## Tarea B - memoria entre sesiones

Primera sesión: [scenario-b-session-1](runs/scenario-b-session-1/).

Registra arquitectura, convención de routers finos, comando de test y archivo
principal en memoria SQLite.

Segunda sesión: [scenario-b-session-2](runs/scenario-b-session-2/).

Otra instancia recupera esos cuatro registros antes de implementar
`GET /version`. El artifact separa evidencia de tipo `memory` y muestra el
cambio y los checks.

Archivos clave:

- [memoria recuperada](runs/scenario-b-session-2/memory.json)
- [resumen](runs/scenario-b-session-2/summary.md)
- [diff](runs/scenario-b-session-2/diff.patch)

## Tarea C - seguridad y no-progreso

Directorio: [scenario-c-safety](runs/scenario-c-safety/).

La policy deniega la escritura en `.github`, solicita aprobación para acciones
sensibles y el detector observa dos fallos iguales. El orquestador replantea una
vez y bloquea la tarea sin ejecutar un tercer intento idéntico.

- [eventos](runs/scenario-c-safety/events.json)
- [comandos](runs/scenario-c-safety/commands.json)
- [resumen](runs/scenario-c-safety/summary.md)

## Corrida externa completa

Directorio:
[real-openai-20260717-003912](runs/real-openai-20260717-003912/).

Resultado real:

- estado `completed`;
- cinco roles ejecutados con OpenAI Responses;
- memoria recuperada;
- RAG y fallback web registrados;
- diff esperado;
- `pytest -q`: 3 passed, exit 0;
- Reviewer acepta;
- trace id Langfuse: `cd6e9589a8074d1d52c738d79373c128`.

Consultar [run.json](runs/real-openai-20260717-003912/run.json),
[summary.md](runs/real-openai-20260717-003912/summary.md) y
[commands.json](runs/real-openai-20260717-003912/commands.json).

## Capturas pendientes

El trace id demuestra que la corrida fue instrumentada, pero la consigna exige
capturas de la UI. No se fabricaron. Seguir
[screenshots/README.md](screenshots/README.md) para obtenerlas y revisarlas antes
de agregarlas.
