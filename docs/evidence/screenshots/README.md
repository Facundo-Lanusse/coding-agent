# Capturas Langfuse de la ejecución completa

Este directorio todavía no contiene capturas. No agregar placeholders con
apariencia de resultado, screenshots de otra tarea ni ids escritos manualmente.

## Estado actual

La ejecución completa es `real-openai-20260716-231650`, con trace id
`8248244a2224f1dc099fff1240e5c040`: alcanzó Reviewer, ejecutó tests con exit 0
y terminó `completed`. Aún no se guardó una captura. Los artifacts
deterministas conservan `trace_id=null` honestamente y cada demo real crea un directorio separado
`docs/evidence/runs/real-openai-<fecha>/`.

## Procedimiento de captura

1. Abrir el proyecto Langfuse y buscar
   `8248244a2224f1dc099fff1240e5c040`; como alternativa, filtrar
   por `task_id`, `project_id`, `session_id` y el intervalo de ejecución.
2. Verificar una raíz y descendientes para cinco agentes, LLM generation,
   policy/tool, RAG/web si aplica, checks, review y `result.final`. Confirmar
   tokens/latencia/costo cuando estén disponibles y ausencia de secrets.
3. Guardar capturas PNG reales, sin editar valores:

   ```text
   docs/evidence/screenshots/<trace-id>-full-trace.png
   docs/evidence/screenshots/<trace-id>-metadata.png
   ```

4. Actualizar este README con fecha, task id, trace id, filenames y qué muestra
   cada imagen. No editar a mano el trace id generado en `run.json`.

## Smoke test disponible

Con SDK/credenciales aprobados puede ejecutarse:

```bash
pytest -m langfuse_integration -q
```

Sólo crea `coding-agent.integration-smoke`. Puede servir para diagnosticar
conectividad y sanitización, pero no satisface la captura de traza completa del
caso de uso.
