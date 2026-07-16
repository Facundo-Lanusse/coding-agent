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
wrapper LLM agrega latencia y usage. Langfuse puede calcular costo a partir del
modelo y los tokens; si se inyecta un estimador propio, también se envía
`cost_details`. Un campo no disponible no se inventa.

La cobertura es composicional: `coding-agent demo real` crea una traza raíz e
inyecta el mismo `Tracer` en configuración, memoria, orquestador, cinco agentes,
LLM, gateway de tools, RAG/web y detector de no-progreso. Los unit tests siguen
usando un cliente Langfuse fake; la evidencia externa sólo existe después de
ejecutar la demo con credenciales y obtener un trace id auténtico.

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

`langfuse>=4.7,<5` está declarado e instalado con autorización explícita. El
adaptador usa la API v4 (`get_client`, `start_as_current_observation`,
`trace_context`, `usage_details` y `cost_details`). Las variables esperadas son:

```bash
export LANGFUSE_PUBLIC_KEY='...'
export LANGFUSE_SECRET_KEY='...'
export LANGFUSE_BASE_URL='https://cloud.langfuse.com'
export LANGFUSE_TRACING_ENVIRONMENT='development'
```

La integración opt-in disponible es un smoke test:

```bash
pytest -m langfuse_integration -q
```

Sin claves se marca skip. Con prerrequisitos crea y hace flush de una observación
`coding-agent.integration-smoke`; sirve para diagnosticar conectividad, pero no
reemplaza el caso completo.

La demo real exige una confirmación visible y aplica límites duros:

```bash
coding-agent demo real \
  --scenario rag \
  --config agent.config.yaml \
  --max-llm-calls 20 \
  --max-iterations-per-agent 4 \
  --max-output-tokens 2400 \
  --confirm-cost
```

Coordina Explorer, Researcher, Implementer, Tester y Reviewer con OpenAI
Responses, embeddings OpenAI, RAG-first, una búsqueda Tavily `basic` como
máximo, memoria SQLite, policies y Langfuse. Sin `--confirm-cost` termina antes
de crear providers o consumir APIs. El límite de 2400 reduce truncamientos de
function calls observados con 1800 sin cambiar el máximo de 20 llamadas.

## Evidencia entregada

Los bundles bajo `docs/evidence/runs` declaran:

```text
provider_mode = deterministic_fake
observability = recording
trace_id = null
```

Existen seis artifacts reales de diagnóstico y una ejecución completa.
`real-openai-20260716-223318`,
trace id `e3e18abb93d9e4cbc427b6bdfc03caaa`, registra cuatro llamadas de tool,
sus policies y `loop.no_progress`. `real-openai-20260716-224029`, trace id
`fb1df898e7cbb0a88eebc6d3aa2c8cab`, registra diez policies permitidas y el
fallo por argumentos JSON inválidos de una function call. El tercero,
`real-openai-20260716-224955`, trace id
`3a3129ac11a8a4e0355bea72df2660e6`, preserva ocho evidencias repository y el
stop por límite de iteraciones. Los primeros tres no alcanzaron el flujo
completo. El cuarto,
`real-openai-20260716-225405`, trace id
`8a53e02921325eb21456671398423539`, alcanzó RAG, web, implementación, diff y
Tester; no llegó a Reviewer por entorno de test y presupuesto global. Sirven
como evidencia de diagnóstico. El quinto,
`real-openai-20260716-230132`, trace id
`38413a02a1e66af00ec8d7de6fc26def`, demuestra memoria entre sesiones y el
bloqueo de Researcher por memoria histórica. El sexto,
`real-openai-20260716-230907`, trace id
`a237b059da41edb2fe38febbc160a693`, alcanzó nuevamente Tester y registró la
denegación segura del wrapper `/usr/bin/env bash -lc`; no llegó a Reviewer. La
ejecución `real-openai-20260716-231650`, trace id
`8248244a2224f1dc099fff1240e5c040`, completó los cinco roles, registró
repository/memory/RAG/web, el diff, `pytest -q` con exit 0, Reviewer y resultado
final. Sólo quedan pendientes las capturas humanas de esa traza.

El procedimiento exacto para crear y verificar evidencia humana está en
[`evidence/screenshots/README.md`](evidence/screenshots/README.md). Nunca debe
copiarse una imagen de otra ejecución ni rellenarse `trace_id` manualmente sin
la traza correspondiente.
