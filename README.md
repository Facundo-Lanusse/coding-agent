# Coding Agent Avanzado para Python/FastAPI

Proyecto final de IA: un sistema de agentes que analiza un repositorio Python/FastAPI,
recupera evidencia técnica, implementa un cambio verificable, ejecuta tests y revisa
el diff. La coordinación es propia y usa el SDK oficial de OpenAI Responses; no usa
frameworks de orquestación.

## Capacidades obligatorias

- agente principal y cinco roles: Explorer, Researcher, Implementer, Tester y Reviewer;
- estado compartido tipado con evidencia, fuentes, cambios, checks y decisiones;
- tools locales con permisos por rol y policy validada antes de cada invocación;
- memoria persistente por proyecto en SQLite;
- RAG con chunking, embeddings, almacenamiento vectorial SQLite y provenance;
- búsqueda Tavily sólo como fallback cuando el RAG es insuficiente;
- resumen de contexto, límite de iteraciones y detección de acciones sin progreso;
- traza Langfuse con prompts, modelo, llamadas LLM, tools, RAG/web, errores,
  latencia, tokens, costo estimado y resultado.

## Caso de uso

El agente trabaja sobre una copia contenida de
[examples/fastapi_demo/seed](examples/fastapi_demo/seed). La tarea de referencia
analiza el proyecto y agrega `GET /health/ready`, tests y revisión del diff. Se
considera completa sólo si los cinco roles terminan, existe evidencia RAG, pasa un
check real y Reviewer acepta cambios limitados al pedido.

La descripción y los criterios están en [docs/case_use.md](docs/case_use.md).

## Requisitos

- Python 3.11 o posterior.
- Credenciales sólo para la demo real: OpenAI, Tavily y Langfuse.
- Ninguna credencial se guarda ni se carga automáticamente desde `.env`.

## Instalación

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

También se puede usar:

```bash
make bootstrap
```

## Configuración

`agent.config.yaml` define workspace, límites, modelos y políticas. Validarlo no
realiza llamadas externas:

```bash
coding-agent config validate --config agent.config.yaml
```

La policy se recarga y valida dentro de `AuthorizedToolGateway` antes de cada
tool call. Bloquea secretos, escapes del workspace, escrituras prohibidas y
comandos como `git push`; instalaciones y commits requieren aprobación.

## RAG reproducible sin red

```bash
coding-agent rag ingest rag_sources \
  --config agent.config.yaml \
  --fake-embeddings

coding-agent rag query "dependencies en FastAPI" \
  --config agent.config.yaml \
  --fake-embeddings
```

La base se guarda en `data/vector_store/`, ignorada por Git. El corpus,
chunking, embeddings y almacenamiento están documentados en
[docs/rag.md](docs/rag.md).

## Harness heredado

El harness base continúa disponible con plan mode, supervisión, tools y límite de
iteraciones:

```bash
coding-agent run \
  --config agent.config.yaml \
  --task "Analizá la estructura del proyecto" \
  --plan \
  --supervision
```

Requiere `OPENAI_API_KEY`. La demo que prueba la arquitectura completa es la
siguiente.

## Demo real de cinco agentes

Cargar las variables en la shell sin versionarlas:

```bash
export OPENAI_API_KEY="..."
export TAVILY_API_KEY="..."
export LANGFUSE_PUBLIC_KEY="..."
export LANGFUSE_SECRET_KEY="..."
export LANGFUSE_BASE_URL="https://cloud.langfuse.com"
```

Preparar el entorno aislado del repositorio FastAPI si todavía no existe:

```bash
python3.11 -m venv examples/fastapi_demo/seed/.venv
examples/fastapi_demo/seed/.venv/bin/python -m pip install -e \
  "examples/fastapi_demo/seed[dev]"
```

Ejecutar la tarea con límites explícitos:

```bash
make demo-real
```

El comando exige confirmación de costo, limita la ejecución a 20 llamadas LLM,
seis turnos por rol, 2400 tokens de salida y una búsqueda Tavily. El margen por
rol permite recuperar una tool call malformada sin dejar al Implementer sin un
turno de escritura y otro de cierre. Trabaja sólo
sobre `tmp/demo-runtime/` y escribe un bundle sanitizado bajo
`docs/evidence/runs/real-openai-<fecha>/`.

## Tests y controles

```bash
make check
make coverage
make build
```

Equivalentes principales:

```bash
pytest -q
ruff check src tests examples
mypy src tests
```

Los tests unitarios usan fakes y no llaman a OpenAI, Tavily ni Langfuse. La
integración Langfuse se omite con una razón explícita cuando faltan credenciales.

## Extender tools sin modificar el núcleo

Una tool implementa `Tool` o `StructuredTool` y declara nombre, descripción,
schema Pydantic y permisos. Puede registrarse en `ToolRegistry` o publicarse como
entry point del grupo `coding_agent.tools`. El harness, el orquestador y el
gateway dependen de la interfaz común, no de clases concretas. Los tests en
`tests/unit/test_tool_registry.py` muestran registro y descubrimiento.

## Evidencia entregada

[docs/evidence/README.md](docs/evidence/README.md) describe:

- tarea A: RAG y cambio `/health/ready`;
- tarea B: memoria persistente entre dos sesiones y cambio `/version`;
- tarea C: denegación, aprobación y detención por no-progreso;
- corrida real completa con trace id Langfuse.

Las capturas de la UI todavía son una acción humana y no se presentan como
completadas. El procedimiento está en
[docs/evidence/screenshots/README.md](docs/evidence/screenshots/README.md).

## Documentación mínima de entrega

- [Caso de uso](docs/case_use.md)
- [Arquitectura](docs/architecture.md)
- [RAG](docs/rag.md)
- [Testing](docs/testing.md)
- [Evidencias](docs/evidence/README.md)
- [Reflexión](docs/reflection.md)
- [Matriz de requisitos](docs/requirements_matrix.md)

## Limitaciones honestas

- La única corrida externa completa conservada tiene trace id
  `cd6e9589a8074d1d52c738d79373c128`; falta guardar capturas de su UI.
- Tavily puede registrar cero búsquedas si el RAG ya aporta evidencia suficiente.
- Los bundles reproducibles A/B/C son evidencia histórica sanitizada; la branch
  de entrega conserva el runtime real y los tests deterministas, no su generador
  hardcodeado.
