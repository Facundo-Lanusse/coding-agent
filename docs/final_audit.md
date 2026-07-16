# Auditoría final integral — Fase 09

Fecha base: 2026-07-14. Actualización de providers reales: 2026-07-16. Alcance: consigna completa, código, configuración,
documentación, pruebas, paquetes y artifacts entregables. Se leyó íntegramente
`docs/consigna_tp_final.pdf`, se extrajeron sus cuatro páginas y se verificó
visualmente cada página renderizada. También se inspeccionaron las doce celdas
de código del notebook legado; `.env` no fue leído.

## 1. Dictamen

Estado general: **REQUIERE ACCIÓN HUMANA** únicamente para las capturas.

- Requisitos de la consigna: 43 `PASS`, 0 `PARTIAL`, 0 `FAIL` y 1
  `REQUIERE ACCIÓN HUMANA`.
- Decisiones vinculantes D01-D09: 9 `PASS`.
- Gates internos: suite, coverage global, Ruff, mypy, build, instalación limpia,
  ayuda CLI, demos, artifacts y escaneos pasan; no pasan el umbral de coverage
  de 90% para todos los módulos críticos ni la ejecución de una demo fuera del
  checkout usando solamente el wheel.

No se cierra como `PASS` únicamente por la captura Langfuse. La séptima ejecución externa,
`real-openai-20260716-231650`, terminó `completed`, exit 0, con trace id
`8248244a2224f1dc099fff1240e5c040`: completó los cinco roles, recuperó memoria,
consultó RAG/web, aplicó el diff, obtuvo `3 passed` y Reviewer aceptó. El seed
demo vive deliberadamente bajo `examples/` y se ejecuta desde el checkout; no
forma parte del paquete distribuible. La captura de la UI requiere acción humana.

## 2. PASS

| Requisito | Evidencia concreta |
|---|---|
| R03 | `orchestrator/main.py` y `state/machine.py` implementan coordinación propia; el escaneo de imports/dependencias no encuentra frameworks prohibidos. |
| R04 | `harness/loop.py`, siete tools y tests de harness/filesystem/shell/web preservan loop, lectura, escritura, listado, comando y web. |
| R05-R12 | `MainAgent`, Explorer, Researcher, Implementer, Tester y Reviewer, toolsets distintos, `TaskState` y E2E A/B/C; `test_agents.py`, `test_orchestrator.py` y `test_state_machine.py` pasan. |
| R13 | `SQLiteMemoryRepository`; tests de reapertura/aislamiento/stale y escenario B1/B2 entre instancias pasan. |
| R14-R20 | Corpus Python/FastAPI, loaders, chunker estructural, embeddings fake/OpenAI, `SQLiteVectorStore`, top-k/threshold y `ResearchService` RAG-first; tests RAG/fallback/provenance y escenario A pasan. |
| R21 | `MainAgent` carga memoria por proyecto y aplica `ContextManager`; tests verifican presupuesto, resumen, decisiones/errores e included/omitted. |
| R22-R23 | `NoProgressDetector` y escenario C registran dos errores iguales, replanificación, bloqueo y ausencia de tercer intento. |
| R24-R28 | `AuthorizedToolGateway` recarga/valida YAML antes de policy/tool; tests cubren traversal, symlink externo, secretos, globs, atomicidad, deny de comandos y approvals. |
| R29-R30, R35 | Langfuse adapter probado y ejecución real completa con trace id `8248244a2224f1dc099fff1240e5c040`, cinco roles, tools, RAG/web, test exit 0, Reviewer y resultado final. |
| R31-R34 | Caso FastAPI verificable y escenarios A, B y C con artifacts schema 1.0; siete tests E2E pasan. |
| R36 | `ToolRegistry` admite registro y descubrimiento opt-in; tests de duplicados y entry points pasan. |
| R37 | Suite, build, instalación limpia, demos desde checkout y ejecución OpenAI real completa pasan; el ejemplo se distribuye con el repositorio, no dentro del wheel. |
| R38-R42, R44 | README y documentación requerida, caso, arquitectura, RAG, cuatro bundles y reflexión; `test_documentation.py` valida links, rutas, schema y 44 filas. |
| D01-D09 | Paquete `src`, OpenAI Responses directo, SQLite memory/vector store, no-op tracing, CLI, demo, puertos/fakes y suite offline verificados por build, instalación y tests. |

### Verificación de los puntos obligatorios 1-13, 15-16, 19-20

1. El notebook contiene tool loop, workspace, read/write/list/command/web,
   plan mode, supervision, máximo 15 y ejecución real. El paquete conserva esos
   conceptos sin copiar `shell=True`, `input()` de dominio ni el `read_file`
   inseguro final.
2. Existen el agente principal y exactamente los cinco roles pedidos.
3. `ScopedToolbox` y las capability sets prueban permisos distintos.
4. `TaskState` contiene pedido, objetivo, plan, fase/status, resultados,
   fuentes, archivos, comandos, approvals, errores, observaciones, decisiones,
   iteraciones y resultado final.
5. SQLite conserva memoria por `project_id` entre repositorios/sesiones.
6. El RAG implementa chunking, embeddings y vector store SQLite persistente.
7. `Evidence` y los bundles conservan locator, fragmento, score y provenance.
8. Tests prueban RAG primero, web sólo por insuficiencia y cero web si alcanza.
9. El manejo de contexto y resumen pasa sus tests y está compuesto
   automáticamente por `MainAgent` en la demo real.
10. Fingerprints y detección de repetición, A-B-A-B, relectura, errores y
    estancamiento están probados.
11. La falta de evidencia produce estado explícito y pedido de ayuda/dato.
12. La configuración se recarga y valida antes de cada tool invocation.
13. Policies cubren lectura, escritura, comandos, approvals, límites y logs
    redactados.
15. `examples/fastapi_demo/` materializa el caso Python/FastAPI.
16. Hay pruebas específicas y E2E para RAG, memoria y estrategia/detención.
19. El escaneo de `src`, `tests`, `examples` y `pyproject.toml` no encuentra
    imports ni dependencias de LangChain, LangGraph, CrewAI, AutoGen u OpenAI
    Agents SDK.
20. El escaneo razonable no encuentra credenciales reales, PEM, paths del
    autor ni outputs falsificados; los dos Bearer de tests son fixtures falsas
    destinadas a comprobar redacción.

## 3. FAIL

No queda un requisito funcional R01-R44 clasificado como `FAIL`. Sí fallan dos
criterios internos definidos en el plan:

| Gate | Evidencia del fallo |
|---|---|
| Coverage crítico >=90% | Coverage posterior global 85%, pero `orchestrator/main.py` 85%, `policies/engine.py` 86%, `policies/gateway.py` 89% y `policies/redaction.py` 62%. No se ajustó el umbral ni se inventó cobertura. |
| Demo standalone desde wheel | El wheel se instala y la ayuda funciona fuera del checkout, pero `coding-agent demo reset` termina 1 porque `examples/fastapi_demo/seed` no está empaquetado. La ejecución documentada de demos requiere el checkout. |

El primer intento de build también terminó 1 por bloqueo de red del sandbox; la
repetición autorizada terminó 0. Una query RAG con el threshold anterior 0.68
terminó 3 y reveló que el ejemplo documentado no era reproducible; se corrigió
la configuración a 0.10 y la query final recuperó únicamente la fuente FastAPI
con exit 0.

## 4. PARTIAL

No queda ningún requisito R01-R44 clasificado como `PARTIAL`.

## 5. REQUIERE ACCIÓN HUMANA

| Requisito | Acción pendiente |
|---|---|
| R43 | Abrir la traza `8248244a2224f1dc099fff1240e5c040`, revisar sanitización y guardar capturas reales siguiendo `evidence/screenshots/README.md`. |

Variables necesarias sólo para repetir la ejecución, sin exponer valores:

```text
OPENAI_API_KEY
TAVILY_API_KEY
LANGFUSE_PUBLIC_KEY
LANGFUSE_SECRET_KEY
LANGFUSE_BASE_URL  # opcional, sólo si no se usa el host por defecto
```

El runner está implementado y exige `--confirm-cost`. El runbook final usa un
tope global de 20 llamadas (cinco roles por cuatro turnos), 2400 tokens de
salida y una búsqueda Tavily `basic`; esos límites pueden reducirse dentro de
los rangos de la CLI.

## 6. Comandos y exit codes

| Comando/check | Exit | Resultado observado |
|---|---:|---|
| `pytest --cov=coding_agent --cov-branch --cov-report=term-missing -q` | 0 | Resultado base Fase 09: 119 passed, 1 skipped; 87% total. |
| `pytest tests/e2e -q` | 0 | 7 passed. |
| `ruff check src tests examples` | 0 | Sin hallazgos. |
| `mypy src tests` | 0 | Sin issues en 94 archivos. |
| `python -m build` dentro del sandbox | 1 | Backend no pudo descargarse por DNS/red restringida. |
| `python -m build --no-isolation` | 1 | El entorno editable no tenía `setuptools.build_meta`; no se instaló nada adicional. |
| `python -m build` con red autorizada | 0 | Wheel y sdist creados. |
| Crear venv temporal e instalar el wheel | 0 | Instalación limpia con dependencias runtime declaradas. |
| `coding-agent --help`, `config --help`, `rag --help`, `demo --help` desde el wheel | 0 | Entry point e imports resuelven desde `site-packages`. |
| `coding-agent demo reset` sólo desde el wheel | 1 | Seed demo no empaquetado; gate standalone fallido. |
| `coding-agent demo all --output-root docs/evidence/runs` | 0 | A/B1/B2 `completed`; C `blocked` esperado. |
| Primer intento de `demo all` con opción `--config` inexistente | 2 | Error de invocación corregido; el comando válido siguiente terminó 0. |
| Parseo Pydantic de los cuatro `run.json` | 0 | Cuatro artifacts schema 1.0 válidos. |
| `coding-agent rag ingest ./rag_sources --fake-embeddings` | 0 | 3 documentos, 3 chunks insertados. |
| Query RAG final con fake embeddings | 0 | Fuente FastAPI relevante, threshold suficiente. |
| Escaneo de frameworks prohibidos | 1 | `rg` sin matches; exit 1 significa cero hallazgos. |
| Escaneo de paths del autor | 1 | `rg` sin matches; exit 1 significa cero hallazgos. |
| Escaneo de firmas de secretos | 1 | Sin credenciales reales; fixtures falsas revisadas aparte. |
| `pip install -e ".[dev]"` tras autorización | 0 | Instaló sólo dependencias declaradas, incluidas Langfuse 4.14.0 y Tavily 0.7.26. |
| `pytest -q` posterior | 0 | 142 passed, 1 integración Langfuse omitida sin entorno. |
| Coverage posterior | 0 | 85% global con el runtime real incluido. |
| `ruff check src tests examples` posterior | 0 | Sin hallazgos. |
| `mypy src tests` posterior | 0 | Sin issues en 101 archivos. |
| `coding-agent demo real --scenario rag` sin confirmación | 2 | Guard de costo; cero providers/llamadas externas. |
| Segundo `demo real` con confirmación | No registrado | El usuario aportó el artifact `real-openai-20260716-224029`: fallo seguro por argumentos JSON inválidos; sin comandos ni cambios. |
| Tercer `demo real` con confirmación | 2 | Artifact `real-openai-20260716-224955`: ocho evidencias repository y stop seguro en Explorer; sin comandos ni cambios. |
| Cuarto `demo real` con confirmación | 2 | Artifact `real-openai-20260716-225405`: llegó a Tester, pero pytest terminó 4 y el replan agotó 15/15. |
| Test del diff con el entorno demo | 0 | Misma copia de runtime: 3 passed y una advertencia de deprecación. |
| Quinto `demo real` con confirmación | 2 | Artifact `real-openai-20260716-230132`: memoria recuperada; Researcher bloqueado por memoria histórica. |
| Sexto `demo real` con confirmación | 2 | Artifact `real-openai-20260716-230907`: llegó a Tester con el diff correcto; policy denegó `/usr/bin/env bash -lc` antes de ejecutar pytest. |
| Test del sexto diff con el entorno demo | 0 | Misma copia aislada preservada: 3 passed y una advertencia; verificación externa a la traza. |
| Séptimo `demo real` con confirmación | 0 | Artifact `real-openai-20260716-231650`: cinco roles completos, `pytest -q` 3 passed, Reviewer aceptó y trace id real. |
| Validación/sanitización del séptimo bundle | 0 | Schema 1.0 válido: `completed`, 87 fuentes, un comando; sin secretos ni paths del autor. |

La integración `tests/integration/test_langfuse_integration.py` es el único
skip en el entorno de validación: faltan variables cargadas/red. Un skip no se
cuenta como observabilidad real.

## 7. Evidencias disponibles

| Escenario | Estado | Evidencia |
|---|---|---|
| A — RAG/readiness | `completed` | `evidence/runs/scenario-a-rag/`: estado, 4 fuentes, 3 cambios, diff y 2 comandos exitosos. |
| B1 — memoria | `completed` | `evidence/runs/scenario-b-session-1/`: arquitectura, convención, archivos y comando persistidos. |
| B2 — nueva sesión | `completed` | `evidence/runs/scenario-b-session-2/`: 4 memorias recuperadas antes de `/version`, cambios y checks. |
| C — seguridad/no-progreso | `blocked` esperado | `evidence/runs/scenario-c-safety/`: approvals, deny, 2 errores iguales, replan y stop sin tercer intento. |
| Real — OpenAI/Langfuse | `completed` | `evidence/runs/real-openai-20260716-231650/`: cinco roles, memoria, RAG/web, diff, pytest exit 0, Reviewer y trace id. |

Los cuatro manifests deterministas declaran `provider_mode=deterministic_fake`,
`observability=recording` y `trace_id=null`. Esto prueba comportamiento local,
mientras el bundle real declara `provider_mode=real`,
`observability=langfuse` y un trace id no vacío.

## 8. Riesgos residuales

1. Las demos versionadas aplican cambios deterministas; la composición autónoma
   existe pero aún no tiene un artifact real revisado.
2. La calidad de una corrida real depende del modelo disponible y puede terminar
   bloqueada dentro de los límites de costo.
3. El vector store hace búsqueda lineal; es apropiado para el corpus pequeño.
4. Tavily sólo se usa en `demo real`, como fallback y con presupuesto uno.
5. La policy reduce riesgos, pero no reemplaza un sandbox del sistema operativo.
6. No se ejecutaron tests HTTP FastAPI porque esas dependencias no fueron
   autorizadas; sí se ejecutaron compile y checks de contrato de la fixture.
7. Después de la auditoría se inicializó Git sobre `main`, pero no existe un
   commit baseline; status funciona y el diff completo queda para el primer
   commit autorizado.
8. Faltan tests para alcanzar el umbral interno de coverage crítico.

## 9. Lista exacta para entregar

Incluir:

- raíz: `.env.example`, `.gitignore`, `.gitattributes`, `.dockerignore`, `.python-version`,
  `README.md`, `CONTRIBUTING.md`, `Makefile`, `Dockerfile`, `compose.yaml`,
  `pyproject.toml`, `agent.config.yaml`, `AGENTS.md`, `CODEX_START.md`;
- `src/coding_agent/**/*.py`;
- `tests/**/*.py` y `tests/integration/README.md`;
- `examples/fastapi_demo/**`;
- `rag_sources/**`;
- `docs/consigna_tp_final.pdf`, `docs/*.md`, `docs/evidence/README.md`, los
  cuatro directorios `docs/evidence/runs/scenario-*`, los seis diagnósticos y
  la ejecución completa bajo `docs/evidence/runs/real-openai-20260716-*`, y
  `docs/evidence/screenshots/README.md`;
- `legacy/coding_agent_tp_anterior.ipynb`;
- `prompts/*.md` como historial reproducible del proceso;
- wheel y sdist como assets de la entrega o de un GitHub Release; `dist/` queda
  correctamente ignorado para no versionar outputs reconstruibles.

Excluir: `.env`, `.venv/`, `data/`, `tmp/`, `.coverage`, `htmlcov/`, `build/`,
`*.egg-info/`, caches, bases locales de ejecución y cualquier credencial real.

Checksums SHA-256 del build final:

- wheel: `582adeaa5380cdaee2aa6a6ee5ab4bd180cdf119c89ce96123c7b6192dff58c5`;
- sdist: `b12dfd01dd652696d97820d33819a14364d1575bc24ddfbe812725e4f4514997`;
- notebook legado: `f89f5477f4f8fe282b1c5bffdce84887c5eda5ba9d2478da039d44166a242176`.

## 10. Conclusión de seguridad e integridad

No se encontraron secretos reales ni frameworks de orquestación prohibidos en
el alcance entregable. No se leyó `.env`. Los artifacts finales no contienen
paths del autor y usan `${WORKSPACE}`/`${PYTHON}`/`${HOME}`. No se fabricaron
resultados ni trace ids. La ejecución Langfuse está preservada; únicamente su
captura desde la UI permanece como acción humana.
