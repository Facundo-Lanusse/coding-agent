# Capturas Langfuse de la ejecución completa

Las capturas fueron tomadas el 2026-07-16 desde la UI Langfuse v3.218.0 para la
ejecución `real-openai-20260717-003912`, cuyo trace id es
`cd6e9589a8074d1d52c738d79373c128`.

- [Vista completa](cd6e9589a8074d1d52c738d79373c128-full-trace.png): grafo
  agregado con Main, Explorer, Researcher, Implementer, Tester y Reviewer;
  incluye RAG, fallback web, policy, tools, memoria, checks y `result.final`.
- [Metadata](cd6e9589a8074d1d52c738d79373c128-metadata.png): grafo expandido,
  archivos modificados, modelo `gpt-5-mini`, 14 llamadas LLM, límite global de
  20 llamadas, 133.472 tokens, latencia de 1m33s y costo de USD 0,047863.

La traza alcanzó Reviewer, ejecutó `pytest -q` con exit 0 y terminó
`completed`, según el
[bundle sanitizado](../runs/real-openai-20260717-003912/run.json). La UI muestra
`CONTENT_CAPTURE_DISABLED`, por lo que las capturas no exponen prompts ni
respuestas del modelo.

## Smoke test disponible

Con SDK/credenciales aprobados puede ejecutarse:

```bash
pytest -m langfuse_integration -q
```

Sólo crea `coding-agent.integration-smoke`; sirve para diagnosticar
conectividad y sanitización, pero no reemplaza las capturas del caso de uso.
