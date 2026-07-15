# Capturas Langfuse - acción humana pendiente

Este directorio no contiene capturas porque no hubo una ejecución Langfuse
completa. No agregar placeholders con apariencia de resultado, screenshots de
otra tarea ni ids escritos manualmente.

## Bloqueo actual

- `langfuse` no está declarado/instalado;
- no hay credenciales disponibles en la ejecución entregada;
- `coding-agent demo real --scenario rag` valida prerrequisitos y termina con
  exit 2: todavía no compone los cinco agentes con OpenAI/Langfuse;
- los artifacts deterministas tienen `trace_id=null`.

Por eso no existe hoy un comando que produzca honestamente la captura completa
exigida por la consigna. El smoke test Langfuse disponible no cubre agentes,
tools, RAG, checks y review, así que no alcanza.

## Procedimiento cuando se resuelva el bloqueo

1. Obtener aprobación explícita para agregar/instalar una versión compatible
   del SDK Langfuse y para el costo de una corrida OpenAI pequeña.
2. Implementar y probar la composición real detrás de
   `coding-agent demo real --scenario rag`; el comando debe devolver exit 0,
   escribir `provider_mode=real`, `observability=langfuse` y un `trace_id` no
   vacío en su `run.json`.
3. Exportar credenciales sólo en la shell:

   ```bash
   export OPENAI_API_KEY='...'
   export LANGFUSE_PUBLIC_KEY='...'
   export LANGFUSE_SECRET_KEY='...'
   export LANGFUSE_BASE_URL='https://cloud.langfuse.com'
   ```

4. Mantener `capture_content=false`, ejecutar:

   ```bash
   coding-agent demo real --scenario rag
   ```

5. Abrir el proyecto Langfuse y filtrar `task.run` por `task_id`, `project_id`,
   `session_id` y el intervalo de ejecución. Comparar el id visible con
   `docs/evidence/runs/scenario-a-rag/run.json`.
6. Verificar una raíz y descendientes para agentes, LLM generation,
   policy/tool, RAG/web si aplica, checks, review y `result.final`. Confirmar
   tokens/latencia/costo cuando estén disponibles y ausencia de secrets.
7. Guardar capturas PNG reales, sin editar valores:

   ```text
   docs/evidence/screenshots/<trace-id>-full-trace.png
   docs/evidence/screenshots/<trace-id>-metadata.png
   ```

8. Actualizar este README con fecha, task id, trace id, filenames y qué muestra
   cada imagen. Actualizar también `run.json`, matriz y checklist mediante el
   flujo generador, no edición manual ad hoc.

## Smoke test disponible

Con SDK/credenciales aprobados puede ejecutarse:

```bash
pytest -m langfuse_integration -q
```

Sólo crea `coding-agent.integration-smoke`. Puede servir para diagnosticar
conectividad y sanitización, pero no satisface la captura de traza completa del
caso de uso.

