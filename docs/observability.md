# Observabilidad y Langfuse

## Contrato

`Tracer.observe()` devuelve un context manager seguro y recibe nombre, tipo,
input y metadata. La observación acepta output, metadata adicional y error.
Tipos implementados: task, span, agent, generation, tool, retriever y event.

Adaptadores:

- `NoOpTracer`: siempre disponible y sin efectos;
- `RecordingTracer`: jerarquía y payloads en memoria para tests/demos;
- `LangfuseTracer`: mapea observaciones a
  `start_as_current_observation` de un cliente Langfuse compatible.

`create_tracer` devuelve no-op si tracing está deshabilitado, faltan
credenciales, no está el módulo `langfuse` o falla su inicialización. Errores al
abrir, actualizar, cerrar o `flush` no reemplazan el resultado funcional.

## Instrumentación disponible

Hay hooks en:

- `config.load_validate`;
- `task.run`, `task.resume` y cada `agent.<role>`;
- `llm.response` mediante `TracedLLMClient`;
- policy, tool y aprobación mediante el gateway;
- `memory.load` y `memory.persist`;
- `rag.retrieval` y `web.fallback`;
- `orchestrator.replan` y `loop.no_progress`;
- `checks`, `review` y `result.final`.

Cuando existen, metadata incluye task/project/session, agente, iteración,
modelo, documentos/fuentes, archivos modificados, errores y resultado. El
wrapper LLM agrega latencia y usage; costo sólo se registra si se inyecta un
estimador y el proveedor reporta tokens. Un campo “no disponible” no se inventa.

La cobertura es composicional: el código emite esos eventos cuando el mismo
`Tracer` se inyecta en cada componente. La CLI básica no crea hoy un tracer y la
demo usa RecordingTracer sólo en los componentes que compone. Los unit tests
verifican el conjunto completo con fakes, pero eso no equivale a una traza
Langfuse de una tarea real.

## Sanitización

`Sanitizer` se aplica antes del adaptador remoto o recording:

- redacta keys sensibles y patrones de tokens/credenciales;
- redacta valores de variables de entorno cuyo nombre es sensible;
- serializa modelos/datos a valores JSON seguros;
- limita payload a `max_payload_chars`;
- con `capture_content=false`, reemplaza inputs/outputs por
  `[CONTENT_CAPTURE_DISABLED]`.

Tokens de uso (`input_tokens`, `output_tokens`, `total_tokens`) no se tratan
como credenciales. Aun así, la primera barrera es no leer ni enviar secretos;
sanitizar no autoriza capturarlos.

Configuración root:

```yaml
observability:
  provider: langfuse
  enabled: true
  redact_sensitive_data: true
  capture_content: false
  max_payload_chars: 20000
```

## Estado real de la integración

El adaptador existe, pero `langfuse` no está declarado en `pyproject.toml` ni
instalado. Agregarlo requiere una decisión/aprobación de dependencia. Las
variables esperadas son:

```bash
export LANGFUSE_PUBLIC_KEY='...'
export LANGFUSE_SECRET_KEY='...'
export LANGFUSE_BASE_URL='https://cloud.langfuse.com'
```

La integración opt-in disponible es un smoke test:

```bash
pytest -m langfuse_integration -q
```

Sin claves o SDK se marca skip. Con prerrequisitos crea y hace flush de una
observación `coding-agent.integration-smoke`; no devuelve un trace id al
artifact y no representa el flujo multiagente completo.

`coding-agent demo real --scenario rag` tampoco ejecuta aún la demo: valida
claves y SDK y luego se detiene solicitando aprobación explícita de costo y la
composición de proveedor todavía ausente.

## Evidencia entregada

Los bundles bajo `docs/evidence/runs` declaran:

```text
provider_mode = deterministic_fake
observability = recording
trace_id = null
```

No hay screenshots reales. Por eso los requisitos de “ejecución registrada en
la herramienta” y “captura de una traza completa” siguen pendientes, aunque el
adaptador y los tests fake estén implementados.

El procedimiento exacto para crear y verificar evidencia humana está en
[`evidence/screenshots/README.md`](evidence/screenshots/README.md). Nunca debe
copiarse una imagen de otra ejecución ni rellenarse `trace_id` manualmente sin
la traza correspondiente.

