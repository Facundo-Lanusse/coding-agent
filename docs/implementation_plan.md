# Plan de implementación

## 1. Baseline de Fase 00

Estado al 2026-07-14: planificación completa; no existe paquete productivo,
`src/`, suite de tests, demo FastAPI, memoria, RAG ni integración de
observabilidad. El notebook legado y `agent.config.yaml` son referencias, no
implementaciones reutilizables directamente.

El trabajo se ejecutará estrictamente en Fases 01 a 09. Cada fase comienza
releyendo `AGENTS.md`, la consigna, este plan y el estado dejado por la fase
anterior; antes de editar se declaran los archivos previstos. Cada fase termina
con tests relevantes, Ruff, mypy, diff/resumen, comandos con exit code,
actualización de este documento y de la matriz, y una detención explícita.

Estados usados en este plan: `PENDING`, `IN_PROGRESS`, `BLOCKED`, `DONE`. Las
Fases 01 a 09 están completadas; sus resultados históricos permanecen debajo.
El checkpoint posterior a la auditoría agrega únicamente la composición real
que había quedado pendiente y no reescribe resultados que no fueron ejecutados.

## 2. Dependencias

Las dependencias declaradas en Fase 01 fueron instaladas en `.venv` con
aprobación explícita mediante `pip install -e ".[dev]"`. Fase 02 no agregó ni
instaló dependencias directas: usa stdlib, Pydantic y los contratos existentes.

### 2.1 Runtime declarado en Fase 01

| Dependencia | Justificación | Límite de uso |
|---|---|---|
| `openai>=2.45,<3` | SDK oficial con Responses API. | Solo `llm.openai_client`; no Agents SDK ni imports desde el harness. |
| `pydantic>=2.13,<3` | Modelos inmutables y validación de requests, outputs, errores y configuración. | Sin efectos externos dentro de validators. |
| `pydantic-settings>=2.14,<3` | Carga tipada de secretos desde el entorno. | `env_file=None`; no lee `.env` ni persiste secretos. |
| `PyYAML>=6.0.3,<7` | Parseo seguro de `agent.config.yaml`. | `safe_load` seguido siempre por validación Pydantic. |
| `typer>=0.26,<1` | CLI tipada y adaptador de aprobación interactiva. | Solo capa CLI; no hay `input()` en el núcleo. |
| `langfuse>=4.7,<5` | Observabilidad requerida con API v4 y trace id real. | Sólo adapter/composición; no-op si está deshabilitado o falla. |
| `tavily-python>=0.7,<1` | Fallback web técnico autorizado para evidencia insuficiente. | Sólo búsqueda `basic`, dominios HTTPS permitidos y presupuesto máximo de una llamada en la demo. |

`setuptools>=77` es el backend PEP 517 de build y no se importa en runtime.

### 2.2 Development declarado en Fase 01

| Dependencia | Justificación |
|---|---|
| `pytest>=9.1,<10` | Tests unitarios deterministas. |
| `pytest-cov>=7.1,<8` | Cobertura verificable. |
| `ruff>=0.15,<1` | Lint y formato reproducibles. |
| `mypy>=2.3,<3` | Chequeo estricto de los contratos tipados. |
| `types-PyYAML>=6.0.12.20260518` | Stubs de PyYAML para mypy. |
| `build>=1.5,<2` | Verificación posterior de wheel y sdist. |

### 2.3 Dependencias diferidas

`httpx`, `pytest-timeout`, `fastapi`, `uvicorn` y `detect-secrets` no se agregan
al paquete principal. Langfuse y Tavily se declararon e instalaron el
2026-07-16 después de autorización explícita. No se usa ningún framework de
orquestación ni librería vectorial; el diseño mantiene SQLite y puertos
reemplazables.

## 3. Fases

### Fase 01 - Scaffold profesional y migración del harness

Estado: `IN_PROGRESS` - código y tests creados; ejecución de pytest, Ruff, mypy
y build pendiente de aprobación e instalación.

Objetivo: convertir los conceptos seguros del notebook en un paquete Python
instalable, con CLI mínima, configuración tipada, puerto LLM y adaptador OpenAI
Responses API, sin agentes especializados todavía.

Alcance previsto:

- crear `pyproject.toml`; se verificó que `.gitignore` y `.env.example` ya
  existían y eran adecuados, por lo que quedaron intactos;
- crear `src/coding_agent/{cli,config,harness,llm}` y tests unitarios asociados;
- modelar requests, function calls, responses, usage, errores y aprobación;
- preservar plan mode, supervision mode, tool loop y límite de iteraciones;
- mantener `legacy/coding_agent_tp_anterior.ipynb` byte a byte sin cambios;
- documentar el checkpoint de aprobación de dependencias.

Criterios de aceptación objetivos:

1. `python -m build` descubre metadata válida cuando el entorno esté instalado.
2. `coding-agent --help` termina con exit code 0 sin credenciales.
3. Tests prueban configuración válida, modelo ausente, respuesta sin tools, una
   tool fake, límite de iteraciones y rechazo de aprobación.
4. Los unit tests no importan ni llaman al adaptador OpenAI real.
5. No existen paths de Colab, `input()` en dominio, claves hardcodeadas ni copia
   de la redefinición insegura de `read_file`.
6. Un escaneo de imports no encuentra frameworks prohibidos ni Agents SDK.
7. Tras aprobación explícita de dependencias: tests de fase, `ruff check` y
   `mypy src` terminan con exit code 0. Hasta entonces la fase queda pendiente
   de ese gate, no falsamente marcada `DONE`.

Evidencia disponible: código bajo `src/coding_agent/`, 13 tests unitarios en 4
archivos, `tomllib` parseó `pyproject.toml`, la compilación sintáctica terminó
con exit code 0 y se conservó el checksum SHA-256 del notebook
`f89f5477f4f8fe282b1c5bffdce84887c5eda5ba9d2478da039d44166a242176`.

Tras la instalación aprobada, la suite de Fase 01 terminó con 13 tests passing,
Ruff terminó con exit code 0 y mypy sin issues. Build y el entry point instalado
no fueron ejecutados por la instrucción de detenerse después de esos tres gates;
por eso siguen como evidencia histórica pendiente y no se inventa su resultado.

### Fase 02 - Tools, registry y políticas

Estado: `DONE`.

Objetivo: implementar tools estructuradas y un único gateway que valide
configuración y autorización inmediatamente antes de todo efecto.

Alcance previsto:

- contratos `Tool`, `ToolCall`, `ToolResult`, `ToolError` y metadata de permiso;
- `ToolRegistry` extensible;
- `read_file`, `write_file`, `list_files`, `search_files`, `run_command`,
  `repository_status` y `web_search`;
- `PolicyEngine`, policy decisions, approvals, redacción y auditoría;
- containment canónico, symlinks, globs, límites, atomicidad, timeout, cwd fijo
  y ejecución por argv sin `shell=True` arbitrario.

Criterios de aceptación objetivos:

1. Tests permiten un path normal y bloquean `../`, prefijo similar externo,
   symlink externo, `.env`, PEM y `secrets/**`.
2. Escritura a `.github/**` se deniega y una escritura permitida es atómica.
3. Comando prohibido no se ejecuta; comando sujeto a aprobación queda pendiente
   y solo una aprobación con fingerprint coincidente permite ejecutarlo.
4. Timeout y truncamiento producen status estructurado y conservan diagnóstico.
5. Configuración inválida bloquea la llamada y un test demuestra que la policy
   fue evaluada antes que la tool.
6. Ninguna tool productiva puede instanciarse por fuera del registry/gateway en
   la composición normal.
7. Tests de fase, Ruff y mypy terminan con exit code 0.

Evidencia ejecutada el 2026-07-14:

- suite completa: 41 tests passing con exit code 0;
- `ruff check src tests`: exit code 0;
- `mypy src tests`: exit code 0 sobre 33 archivos;
- tests específicos cubren containment normal, traversal, prefijo externo,
  symlink externo, secretos, globs de escritura, comando prohibido, comandos
  con aprobación, timeout, truncamiento, escritura atómica, configuración
  inválida, recarga por llamada, orden config -> policy -> tool, registry,
  descubrimiento, web fake y status de repositorio;
- decisiones registradas contienen argumentos redactados y fingerprints;
- `web_search` queda detrás de `WebSearchProvider`; no se agregó un proveedor
  real ni una dependencia no autorizada.

### Fase 03 - Estado compartido y coordinación multiagente

Estado: `COMPLETADA` (2026-07-14).

Objetivo: implementar Main/Orchestrator, Explorer, Researcher, Implementer,
Tester y Reviewer mediante máquina de estados propia y permisos distintos.

Alcance previsto:

- modelos `TaskRequest`, `TaskState`, `TaskStatus`, `AgentName`, `AgentResult`,
  `Evidence`, `ToolInvocationRecord`, `FileChange`, `Decision` y `TaskEvent`;
- transiciones nominales y terminales definidas en arquitectura;
- context slices por rol y toolsets mínimos;
- resultados finales con provenance separada.

Criterios de aceptación objetivos:

1. Un test con agentes fake recorre en orden Explorer -> Researcher ->
   Implementer -> Tester -> Reviewer y termina `COMPLETED`.
2. El estado final contiene pedido, objetivo, plan, resultados, fuentes,
   archivos, comandos, aprobaciones, errores, decisiones, iteraciones y salida.
3. Un rol no puede resolver ni ejecutar una tool no asignada.
4. Un Tester fallido lleva a `REPLANNING` dentro del presupuesto; Reviewer puede
   rechazar un cambio fuera del pedido.
5. Falta de evidencia termina `BLOCKED` o `STOPPED_NO_EVIDENCE` con explicación.
6. `WAITING_APPROVAL` pausa y reanuda sin perder eventos ni duplicar efectos.
7. Tests de fase, Ruff y mypy terminan con exit code 0 y no hay imports de
   frameworks prohibidos.

Evidencia ejecutada:

- `state/models.py` define los modelos inmutables del pedido, estado, resultados,
  evidencia, invocaciones, cambios, decisiones, aprobaciones, eventos y salida;
- `state/machine.py` contiene la tabla de transiciones permitidas y genera un
  evento append-only por cada cambio de estado;
- `agents/` implementa los cinco roles sobre `BaseAgent`, `AgentContext` acotado
  y `ScopedToolbox`; el backend queda como puerto reemplazable para no acoplar
  dominio, LLM ni tests;
- `orchestrator/main.py` implementa el flujo nominal, pausa/reanudación,
  replanificación por fallo de Tester o rechazo de Reviewer, presupuestos y
  terminal de evidencia insuficiente;
- 10 tests nuevos verifican transiciones, provenance de inferencias, orden,
  acumulación, permisos, tool no asignada, replanificación, rechazo, falta de
  evidencia y aprobación reanudable;
- `.venv/bin/pytest -q`: 51 tests pasaron, exit code 0;
- `.venv/bin/ruff check src tests`: sin hallazgos, exit code 0;
- `.venv/bin/mypy src tests`: sin issues en 48 archivos, exit code 0;
- el escaneo de `src` y `pyproject.toml` no encontró imports ni dependencias de
  frameworks de orquestación prohibidos.

Límites deliberados: `ResearcherAgent` solo expone el puerto/web fake vigente;
memoria y RAG persistentes continúan reservados para Fases 04 y 05. La Fase 03
no agrega proveedor, dependencia ni wiring nuevo en CLI.

### Fase 04 - Memoria, contexto y no-progreso

Estado: `COMPLETADA` (2026-07-14).

Objetivo: persistir conocimiento verificable por proyecto, presupuestar el
contexto y detectar loops antes de repetir una acción inútil.

Alcance previsto:

- repositorio SQLite transaccional y migración/versionado de schema;
- categorías, provenance, confidence, freshness y separación por proyecto;
- `ContextManager`, `SummaryProvider` y reporte de inclusión/omisión;
- fingerprints, progress deltas y acciones de cambio/replan/stop/help.

Criterios de aceptación objetivos:

1. Una entrada guardada se recupera tras cerrar y abrir otra instancia; dos
   `project_id` no se contaminan.
2. Entradas vencidas aparecen `stale` y no guían cambios sin revalidación.
3. El resumen conserva decisiones y errores abiertos y respeta un presupuesto
   comprobado en test.
4. Dos errores idénticos disparan `REPLANNING`; la tercera acción idéntica no se
   ejecuta.
5. Se detectan A-B-A-B, relectura sin información y fases sin delta; evidencia
   nueva reinicia solo el contador pertinente.
6. La salida de detención lista intentos, estrategia y dato/permiso faltante.
7. Tests de fase, Ruff y mypy terminan con exit code 0.

Evidencia ejecutada:

- `memory/` implementa `MemoryRepository` y `SQLiteMemoryRepository` con schema
  versionado, transacciones, clave compuesta por proyecto, provenance,
  categorías, clasificación observation/decision/inference, confidence,
  freshness, invalidación y recuperación lexical acotada;
- `context/manager.py` selecciona candidatos relevantes bajo límites de items y
  caracteres, preserva decisiones/errores, resume contexto antiguo mediante el
  puerto `SummaryProvider` y devuelve el manifiesto included/omitted;
- `context/fingerprints.py` normaliza tools, argumentos relevantes, comandos,
  lecturas, errores, resultados y deltas de progreso;
- `context/progress.py` detecta repetición, error idéntico, relectura, A-B-A-B,
  agotamiento y fases estancadas; devuelve razón, estrategia, intentos, faltante
  y `allow_execution=false` antes de una tercera repetición;
- 16 tests nuevos usan DBs temporales y fakes, sin red ni proveedor real;
- `.venv/bin/pytest -q`: 67 tests pasaron, exit code 0;
- `.venv/bin/ruff check src tests`: sin hallazgos, exit code 0;
- `.venv/bin/mypy src tests`: sin issues en 60 archivos, exit code 0.

Límites deliberados: Fase 04 entrega los puertos y componentes deterministas,
pero no conecta todavía memoria al flujo E2E/CLI ni implementa RAG. Esa
composición y sus evidencias de caso de uso permanecen en Fases 05 y 07.

### Fase 05 - RAG técnico y fallback web

Estado: `COMPLETADA` (2026-07-14).

Objetivo: implementar ingesta y recuperación persistente para
Python/FastAPI/Pydantic/pytest, con atribución de fuentes y fallback web solo por
insuficiencia RAG.

Alcance previsto:

- loaders locales y URL allowlisted; normalización y chunking por headings y
  bloques de código;
- puertos de embeddings/vector store, adaptador OpenAI y fake determinista;
- `SQLiteVectorStore`, colecciones/versiones, checksum, deduplicación, top-k y
  threshold;
- `rag_sources/` pequeño, versionado y reproducible;
- comandos CLI de ingesta/query y conexión de Researcher.

Criterios de aceptación objetivos:

1. Tests prueban preservación de headings/bloques, overlap y metadata completa.
2. Reingestar el mismo checksum no duplica; cerrar/reabrir conserva retrieval.
3. Fake embeddings recupera el fragmento esperado por encima del threshold.
4. Evidencia suficiente deja el contador web en cero; evidencia insuficiente
   llama una sola vez al fake web y registra el motivo.
5. Provenance llega sin mezclarse a la respuesta; ninguna inferencia se etiqueta
   como fuente.
6. Query sin evidencia produce una explicación y no una respuesta inventada.
7. CLI de ingest y query funciona sobre un directorio temporal con exit code 0.
8. Tests de fase, Ruff y mypy terminan con exit code 0; unit tests no usan red.

Evidencia ejecutada:

- `rag/` implementa loaders locales/URL, normalización, chunking estructural,
  conteo aproximado, overlap, puertos/adaptadores de embeddings, SQLite
  versionado, deduplicación, top-k, threshold y research RAG-first;
- `rag_sources/manifest.yaml` fija ids, URLs oficiales, versiones/canales y
  fecha para tres snapshots parafraseados de FastAPI, Pydantic y pytest;
- `ResearcherAgent` expone `ResearchProvider`; `ResearchService` evita web con
  RAG suficiente y hace un único fallback allowlisted ante threshold/cobertura;
- `coding-agent rag ingest` y `coding-agent rag query` funcionan con OpenAI o
  `--fake-embeddings` offline, sin llamadas reales en unit tests;
- `docs/rag.md` documenta corpus, metadata, chunking, embeddings, store,
  provenance, fallback y comandos reproducibles;
- 17 tests nuevos cubren loaders, manifest, containment URL/path y redirects,
  headings, fences, overlap, adaptador/fake, deduplicación, reapertura,
  retrieval, fallback, provenance, no-evidence y CLI;
- `.venv/bin/pytest -q`: 84 tests pasaron, exit code 0;
- `.venv/bin/ruff check src tests`: sin hallazgos, exit code 0;
- `.venv/bin/mypy src tests`: sin issues en 75 archivos, exit code 0.

Corrección surgida de evidencia: el primer test de chunking detectó que un fence
grande se duplicaba como overlap; se ajustó para no solapar bloques que exceden
el presupuesto. Límites: no se realizó llamada OpenAI real ni búsqueda web real;
la composición E2E con el caso FastAPI queda para Fase 07.

### Fase 06 - Observabilidad con Langfuse

Estado: `COMPLETADA` (2026-07-14, integración real pendiente de credenciales y
dependencia aprobada).

Objetivo: trazar el ciclo completo sin acoplar el dominio ni comprometer
secretos, y seguir funcionando con observabilidad deshabilitada.

Alcance previsto:

- puertos `Tracer` y context managers; `LangfuseTracer`, `RecordingTracer` y
  `NoOpTracer`;
- sanitizador central y límites de payload;
- instrumentación de configuración, memoria, agentes, LLM, policy/aprobación,
  tools, RAG, web, loops, checks, review, persistencia y resultado;
- integración opt-in condicionada a credenciales.

Criterios de aceptación objetivos:

1. No-op permite completar una tarea y fake Langfuse recibe jerarquía y eventos
   esperados.
2. Tests verifican redacción de claves, env, tokens y patrones sensibles antes
   de llegar al cliente fake.
3. Una excepción del tracer no cambia el estado funcional ni oculta el error
   original.
4. Metadata contiene modelo, iteración, latencia, tokens y costo cuando el
   proveedor los suministra.
5. La prueba real queda marcada/skippeada con razón explícita sin credenciales y
   se ejecuta solo con variables presentes.
6. Existe runbook para localizar la traza y obtener capturas reales.
7. Tests de fase, Ruff y mypy terminan con exit code 0.

Evidencia ejecutada:

- puerto `Tracer`, context managers y `NoOpTracer`, `RecordingTracer` y
  `LangfuseTracer` con API de observaciones v4;
- sanitización central, redacción de env/patrones/claves, payload cap y captura
  completa desactivable;
- instrumentación de configuración, memoria, agentes, LLM, policy/aprobación,
  tools, RAG/web, replanificación, loops, checks/review y resultado;
- 11 tests unitarios de fase pasan con fakes; integración real queda skippeada
  por ausencia de `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY`;
- `docs/observability.md` documenta seguridad, prueba opt-in y capturas reales;
- no se agregó el SDK Langfuse a dependencias por falta de aprobación explícita
  y no se fabricaron capturas;
- `.venv/bin/pytest -q`: 95 tests pasaron y 1 integración fue skippeada, exit code 0;
- `.venv/bin/ruff check src tests`: sin hallazgos, exit code 0;
- `.venv/bin/mypy src tests`: sin issues en 85 archivos, exit code 0.

### Fase 07 - Caso FastAPI y pruebas end-to-end

Estado: `COMPLETADA` (2026-07-14; demo externa Langfuse pendiente).

Objetivo: crear el repo demo y probar coordinación completa en escenarios RAG,
memoria entre sesiones y seguridad/no-progreso.

Alcance previsto:

- `examples/fastapi_demo/` con routers, services, schemas, tests, configuración
  y una convención no obvia;
- reset seguro y determinista de la fixture;
- demos `rag`, `memory` y `safety` con fakes; demo real pequeña opt-in;
- artifacts versionados bajo `docs/evidence/runs/` sin secretos.

Criterios de aceptación objetivos:

1. Reset ejecutado dos veces produce la misma huella y no toca paths externos.
2. Escenario A usa los cinco roles, RAG antes que web, implementa
   `/health/ready`, ejecuta tests dirigidos y Reviewer acepta el diff esperado.
3. Escenario B usa dos instancias/procesos y la segunda recupera arquitectura,
   convención y comando de test desde SQLite antes de crear `/version`.
4. Escenario C bloquea escritura prohibida, pide aprobación donde corresponde y
   no ejecuta una tercera repetición sin progreso.
5. Artifacts pasan validación de schema e incluyen estado, fuentes, diff,
   comandos/exit codes, memoria, policy/loop events y trace id nullable.
6. Reviewer detecta una mutación fuera del pedido.
7. Tests de demo, suite relevante, Ruff y mypy terminan con exit code 0.
8. Si faltan credenciales, se registra el comando real pendiente, no un
   resultado simulado.

Evidencia: tres directorios de ejecución determinista y, si hay credenciales,
trace id de una demo real.

Evidencia ejecutada:

- fixture FastAPI con app factory, routers, services, schemas, tests y
  dependencias declaradas bajo `examples/fastapi_demo/seed`;
- reset con containment, staging y checksum reproducible;
- `DemoScenarioRunner` compone los cinco agentes, orquestador, tools/policy,
  RAG, SQLite memory, no-progress y tracing recording;
- escenario A `completed`: RAG sin web, tres cambios, dos checks exit 0 y
  Reviewer aceptando;
- escenario B `completed` en dos instancias: cuatro memorias persistidas y
  recuperadas antes de implementar `/version`;
- escenario C `blocked`: dos `requires_approval`, un `denied`, dos fallos
  iguales, un replan y cero tercer intento;
- cuatro bundles schema 1.0 bajo `docs/evidence/runs/`, con `trace_id: null` y
  comandos reales pendientes documentados;
- 7 tests E2E pasan sin red. FastAPI no se instaló; los tests HTTP de la fixture
  están listos, mientras los E2E autorizados ejecutan compile y pytest de
  contrato reales;
- `.venv/bin/pytest -q`: 102 tests pasaron y 1 integración Langfuse fue
  skippeada, exit code 0;
- `.venv/bin/ruff check src tests examples`: sin hallazgos, exit code 0;
- `.venv/bin/mypy src tests`: sin issues en 93 archivos, exit code 0.

### Fase 08 - Documentación y preparación de entrega

Estado: `COMPLETED`.

Objetivo: documentar únicamente comportamiento comprobado y organizar las
evidencias que exige la consigna.

Alcance previsto:

- completar README, caso de uso, arquitectura, estado/memoria, RAG, seguridad,
  contexto/loops, observabilidad, testing, runbook, reflexión y checklist;
- actualizar matriz requisito por requisito con evidencia concreta;
- referenciar al menos dos tareas completas y reservar ubicación para capturas
  humanas reales.

Criterios de aceptación objetivos:

1. Una persona puede instalar, configurar, validar, ingerir RAG, ejecutar las
   tres demos y correr gates siguiendo solo README/runbook.
2. Todos los comandos documentados existen y `--help` termina con exit code 0.
3. Links y rutas locales se validan automáticamente y no hay referencias a
   artifacts inexistentes como si fueran reales.
4. Al menos dos tareas muestran output, fuentes y explicación; los trace ids
   coinciden con artifacts.
5. La reflexión se deriva de eventos reales de falla/no-evidencia.
6. Suite completa, Ruff y mypy terminan con exit code 0.

Evidencia: documentación navegable, link checker y checklist actualizado. Las
capturas Langfuse siguen siendo acción humana hasta que archivos reales y
revisados existan.

Evidencia ejecutada:

- README y doce documentos temáticos describen instalación, configuración,
  RAG, agente básico, demos, estado/memoria, seguridad, contexto/loops,
  observabilidad, testing, reflexión y entrega contra el código real;
- la arquitectura separa expresamente `coding-agent run` (harness OpenAI
  básico) de las demos de cinco roles (backend determinista), y no presenta
  `demo real` como implementado;
- la narrativa de evidencia cubre A, B1/B2 y C con links a output, fuentes,
  diff, comandos y `trace_id=null` real;
- `docs/evidence/screenshots/README.md` documenta el bloqueo y el procedimiento
  de captura sin fabricar imágenes;
- `tests/unit/test_documentation.py`: 17 passed, exit code 0; valida documentos,
  links/rutas, bundles, 44 filas de matriz y catorce rutas CLI `--help`;
- `.venv/bin/pytest -q`: 119 passed, 1 integración Langfuse skipped por falta
  de credenciales, exit code 0;
- `.venv/bin/ruff check src tests examples`: sin hallazgos, exit code 0;
- `.venv/bin/mypy src tests`: sin issues en 94 archivos, exit code 0.

Pendientes históricos de ese checkpoint: no había traza/capturas Langfuse, no
había composición real OpenAI con cinco agentes y no se ejecutaron tests HTTP
FastAPI. La sección posterior documenta el cierre del código, no una corrida
externa inexistente.

### Fase 09 - Auditoría final

Estado: `COMPLETED` (dictamen general `PARTIAL`, 2026-07-14).

Objetivo: comparar el producto final contra cada fila de la matriz, corregir
solo incumplimientos y preparar un dictamen PASS/FAIL/PARTIAL/acción humana.

Alcance previsto:

- confirmar migración, roles, permisos, estado, memoria, RAG, provenance,
  contexto, loops, políticas, observabilidad, caso y entregables;
- escanear frameworks prohibidos, Agents SDK, secretos, paths del autor y
  evidencia falsa;
- ejecutar build, instalación limpia temporal, CLI y demos deterministas;
- generar `docs/final_audit.md` y cerrar matriz/checklist.

Criterios de aceptación objetivos:

1. Suite completa y coverage terminan con exit code 0; cobertura global mínima
   acordada de 85% y módulos críticos (`policies`, `orchestrator`, `context`) de
   90%, salvo decisión humana registrada que ajuste esos umbrales.
2. Ruff, mypy y build terminan con exit code 0.
3. Wheel instalado en entorno temporal ejecuta `coding-agent --help` y una demo
   fake sin depender del checkout.
4. Las tres demos deterministas terminan en el estado esperado y sus artifacts
   validan.
5. Escaneos no encuentran secretos, imports prohibidos ni paths absolutos del
   autor en artifacts/documentación entregable.
6. Cada requisito tiene evidencia concreta y estado honesto; ninguna ausencia
   de credenciales/captura se marca PASS.
7. `final_audit.md` separa PASS, FAIL, PARTIAL y acción humana, y enumera
   comandos con exit codes.

Evidencia: logs de gates, wheel/sdist, artifacts auditados, matriz final y lista
exacta de entrega.

Evidencia ejecutada:

- la consigna completa y las doce celdas de código del notebook fueron
  inspeccionadas; el checksum del notebook permanece sin cambios;
- 119 tests pasaron, una integración Langfuse se omitió justificadamente y el
  coverage global fue 87%; el gate crítico de 90% no se alcanzó en
  orquestación/policies;
- Ruff y mypy terminaron con exit 0;
- wheel/sdist se construyeron e instalaron en un entorno temporal limpio; las
  ayudas CLI terminaron con exit 0;
- las demos A/B/C se regeneraron y sus cuatro artifacts validaron; el writer
  ahora sustituye workspace/intérprete por marcadores portables;
- la demo desde un wheel aislado no encuentra el seed externo y queda como gate
  interno fallido, sin ocultarlo;
- los escaneos no encontraron frameworks prohibidos, secretos reales ni paths
  del autor;
- `docs/final_audit.md`, matriz y checklist separan PASS, FAIL, PARTIAL y acción
  humana. En ese momento R29/R35/R43 seguían pendientes de Langfuse real/capturas.

### Checkpoint posterior a Fase 09 — providers reales autorizados

Estado: `DONE`; ejecución externa completa, capturas Langfuse pendientes.

Con autorización explícita del 2026-07-16 se agregaron únicamente `langfuse` y
`tavily-python`. Se implementaron el provider Tavily acotado, un backend OpenAI
Responses compartido por los cinco roles y `coding-agent demo real`. La
composición incluye memoria, contexto presupuestado, RAG-first, policy antes de
cada tool, no-progreso y una traza Langfuse raíz. Los límites por defecto son 15
llamadas LLM, cuatro iteraciones por rol, 1800 tokens de salida y una búsqueda
Tavily `basic`; la CLI exige `--confirm-cost`.

Evidencia local del checkpoint:

- suite offline: 137 passed y 1 integración Langfuse omitida sin entorno;
- Ruff: exit 0;
- mypy: exit 0 en 101 archivos;
- guard de costo sin `--confirm-cost`: exit 2 antes de crear providers;
- no se leyó `.env` ni se realizó una llamada externa durante la implementación.

Primer intento humano: `real-openai-20260716-223318` quedó `blocked` en Explorer
con trace id `e3e18abb93d9e4cbc427b6bdfc03caaa`. La causa fue un seed contaminado
por entorno/caches y ausencia de un turno reservado para submit. La corrección
filtra generados y ajusta el protocolo de turnos sin aumentar los límites.

Segundo intento humano: `real-openai-20260716-224029` verificó el seed limpio y
registró diez policies permitidas, pero quedó `failed` cuando OpenAI devolvió
argumentos de function call que no eran JSON válido; trace id
`fb1df898e7cbb0a88eebc6d3aa2c8cab`. Se agregó recuperación estructurada de
`invalid_tool_arguments`, cero ejecución para la llamada malformada y máximo
cuatro work tools por respuesta. El gate posterior terminó con 139 passed, 1
skip condicional, Ruff y mypy en exit 0. Pendiente: reejecutar, revisar el nuevo
artifact/trace id y guardar capturas auténticas.

Tercer intento humano: `real-openai-20260716-224955` quedó `blocked` con exit
2 y trace id `3a3129ac11a8a4e0355bea72df2660e6`. Explorer preservó ocho
evidencias limpias, pero en el cuarto turno volvió a usar una tool porque las
definitions de trabajo seguían disponibles. La corrección expone sólo
`submit_agent_result` en el último turno y está cubierta por el test del
backend, sin aumentar iteraciones, tokens ni llamadas.

Cuarto intento humano: `real-openai-20260716-225405` llegó a Tester después de
RAG/web e implementación; trace id `8a53e02921325eb21456671398423539`. El
`pytest -q` registrado terminó 4 por ausencia de FastAPI en el entorno
principal y el replan agotó 15/15 antes de Reviewer. El mismo workspace pasó
`3 passed`, exit 0, usando el `.venv` aislado ya existente del demo. No se
agregaron dependencias. Pendiente: una ejecución con ese binario en `PATH` y
presupuesto global 20 para permitir hasta cuatro turnos en cada uno de los cinco
roles.

Quinto intento humano: `real-openai-20260716-230132` recuperó memoria real del
intento anterior y consultó repository/RAG/web; trace id
`38413a02a1e66af00ec8d7de6fc26def`. Researcher se bloqueó al confundir el fallo
histórico de Tester con su propio criterio. Se reforzó el contrato para priorizar
evidencia actual, no exigir trabajo downstream y usar 2400 tokens de salida para
reducir JSON truncado. La regresión focalizada pasa sin providers reales.

Sexto intento humano: `real-openai-20260716-230907` completó Explorer,
Researcher e Implementer y preservó el diff esperado; trace id
`a237b059da41edb2fe38febbc160a693`. Tester solicitó
`/usr/bin/env bash -lc "pytest -q"`, que la policy denegó correctamente. Se
mantuvo la allowlist estricta y se aclaró el contrato del rol para usar argv
directo `['pytest', '-q']`, sin wrappers de shell. La regresión queda cubierta
por un test unitario y no requiere dependencias nuevas.

Séptimo intento humano: `real-openai-20260716-231650` terminó `completed`, exit
0, con trace id `8248244a2224f1dc099fff1240e5c040`. Completó los cinco roles,
recuperó memoria, consultó repository/RAG/web, produjo el diff esperado,
ejecutó `pytest -q` con `3 passed` y Reviewer aceptó. El exportador se reforzó
para sustituir el home local por `${HOME}` y el bundle se revalidó sin cambiar
resultados ni ids. Sólo resta la captura humana de la traza.

## 4. Reglas de secuencia y gates globales

- No iniciar una fase hasta cerrar o declarar bloqueada la anterior.
- Ninguna dependencia de producción se agrega o instala sin justificación y
  aprobación explícita.
- Un test unitario nunca realiza llamadas reales a OpenAI, Tavily o Langfuse.
- Tests de integración real se marcan y requieren opt-in/credenciales.
- Ningún comando se declara exitoso sin ejecución y exit code 0.
- Toda configuración se valida antes de cada tool call, no solo al arrancar.
- Estado, logs, DB, artifacts y trazas se sanitizan antes de persistir/salir.
- Cada fase actualiza `docs/requirements_matrix.md` con archivo, test, comando o
  artifact real; los planes futuros no cuentan como evidencia de cumplimiento.

## 5. Preparación posterior para GitHub

Estado: `COMPLETED` con validación Docker pendiente por falta del ejecutable.

Sin agregar funcionalidades ni dependencias del paquete, se incorporaron:

- exclusiones Git/Docker para secretos y outputs reconstruibles;
- Python 3.11 de referencia y targets Make reproducibles;
- Docker multi-stage con builder, runtime mínimo no-root y development;
- Compose con variables explícitas, capabilities eliminadas y bind mounts;
- guía de contribución y comandos de onboarding.

La suite, Ruff y mypy deben permanecer verdes. El Dockerfile se valida
estáticamente en este host; el build real queda pendiente en una máquina con
Docker. No se creó CI bajo `.github/**` porque la policy lo prohíbe y requiere
una decisión humana explícita.

Evidencia ejecutada:

- `git init -b main`: exit 0; sin add, commit, remoto ni push;
- `make bootstrap`: primer intento exit 2 por DNS restringido; repetición
  autorizada exit 0, sin dependencias nuevas;
- `make check`: exit 0, 119 tests passed, 1 integración Langfuse skipped, Ruff y
  mypy sin hallazgos;
- `python -m pip check`: exit 0, sin requirements rotos;
- `make build`: exit 0, wheel y sdist regenerados;
- parseo de Compose, etapas/non-root del Dockerfile y dry-run de Make: exit 0;
- `docker --version`: exit 127; no existe Docker/Podman/Nerdctl/Finch en este
  host, por lo que no se inventa un resultado de build;
- Git confirma que `.env`, `.venv`, caches, DBs, `data`, `tmp`, `dist` y
  `*.egg-info` se ignoran, mientras código, docs, corpus y evidencia no.
