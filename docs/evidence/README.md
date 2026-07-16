# Evidencias reproducibles

## Generación

```bash
coding-agent demo all \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

Cada bundle contiene `run.json`, `task_state.json`, `summary.md`,
`sources.json`, `commands.json`, `memory.json`, `events.json` y `diff.patch`.
`RunArtifact` valida schema 1.0 y ArtifactWriter sanitiza y escribe JSON de forma
atómica.

## Tarea A - RAG/readiness

- [Manifest](runs/scenario-a-rag/run.json)
- [Resumen](runs/scenario-a-rag/summary.md)
- [Fuentes](runs/scenario-a-rag/sources.json)
- [Diff](runs/scenario-a-rag/diff.patch)
- [Comandos](runs/scenario-a-rag/commands.json)

Output relevante: `status=completed`, tres archivos modificados y dos checks
con exit code 0. Se recuperó una observación de repository y chunks atribuidos a
pytest, FastAPI y Pydantic. El diff agrega `/health/ready` siguiendo la
delegación router-service y su test dirigido. El fake web no se ejecutó porque
RAG fue considerado suficiente.

Qué se observa: flujo completo Explorer -> Researcher -> Implementer -> Tester
-> Reviewer, fuentes tipadas y aceptación de scope. No se observa generación
LLM: el backend y el cambio son deterministas.

Trace: `trace_id=null`, `observability=recording`; no hay traza Langfuse.

## Tarea B - memoria/version

- [Sesión 1](runs/scenario-b-session-1/run.json)
- [Sesión 2](runs/scenario-b-session-2/run.json)
- [Memoria recuperada](runs/scenario-b-session-2/memory.json)
- [Fuentes sesión 2](runs/scenario-b-session-2/sources.json)
- [Diff sesión 2](runs/scenario-b-session-2/diff.patch)

Output relevante: sesión 1 termina completed sin diff y persiste cuatro
observaciones; sesión 2 las recupera desde otra instancia SQLite, modifica tres
archivos para `/version` y registra dos checks con exit 0.

Qué se observa: memoria por `project_id` fuera del historial, diferenciada de
la evidencia repository. La segunda sesión conserva la convención de router
fino y service. El comando CLI lanza ambas sesiones en secuencia dentro del
mismo proceso; la independencia demostrada es de instancias/persistencia.

Trace: ambos `trace_id=null`, `observability=recording`.

## Tarea C - seguridad y loop

- [Manifest](runs/scenario-c-safety/run.json)
- [Eventos](runs/scenario-c-safety/events.json)
- [Comandos](runs/scenario-c-safety/commands.json)
- [Diff vacío](runs/scenario-c-safety/diff.patch)

Output relevante: `status=blocked`, dos comandos requieren aprobación, una
escritura queda denegada y el mismo check falla dos veces con exit 1. El evento
`loop.no_progress` elige `replan`; después se agota un único replan. No hay
tercer check ni archivos modificados.

Qué se observa: el outcome correcto es detenerse y explicar política/progreso,
no cumplir una orden riesgosa.

Trace: `trace_id=null`, `observability=recording`.

## Intento real OpenAI/Langfuse 1 — diagnóstico reproducible

- [Manifest](runs/real-openai-20260716-223318/run.json)
- [Estado](runs/real-openai-20260716-223318/task_state.json)
- [Eventos](runs/real-openai-20260716-223318/events.json)
- [Fuentes](runs/real-openai-20260716-223318/sources.json)

El 2026-07-16 se ejecutó la composición real con OpenAI y Langfuse. Terminó
`blocked` en Explorer después de cuatro iteraciones, sin modificar archivos ni
ejecutar comandos. El trace id generado fue
`e3e18abb93d9e4cbc427b6bdfc03caaa`. El artifact demuestra provider real,
policies y `loop.no_progress`, pero no constituye todavía la tarea completa de
cinco roles.

La causa fue concreta: el seed contenía un `.venv` local de 43 MB y caches que
entraron en la copia, y el modelo consumió el presupuesto explorándolos. La
corrección excluye entornos/caches/metadatos generados durante el reset y reserva
el último turno de cada rol para el resultado estructurado. El intento fallido
se conserva como evidencia honesta del cambio de estrategia.

## Intento real OpenAI/Langfuse 2 — JSON de tool incompleto

- [Manifest](runs/real-openai-20260716-224029/run.json)
- [Estado](runs/real-openai-20260716-224029/task_state.json)
- [Eventos](runs/real-openai-20260716-224029/events.json)
- [Resumen](runs/real-openai-20260716-224029/summary.md)

El segundo intento verificó la corrección del reset: los checksums before/after
fueron iguales y la copia ya no expuso el `.venv` ni caches. Explorer alcanzó
diez tool calls permitidas, pero una respuesta posterior incluyó argumentos de
function call que no formaban JSON válido. El adaptador antiguo elevó
`LLMResponseError`, por lo que la tarea terminó `failed` de forma segura, sin
fuentes consolidadas, comandos ni archivos modificados. Langfuse asignó el trace
id `fb1df898e7cbb0a88eebc6d3aa2c8cab`.

La corrección posterior preserva el `call_id`, devuelve
`invalid_tool_arguments` como `function_call_output`, impide ejecutar la tool
malformada y permite al modelo corregirse. Explorer limita además cada lote a
cuatro tools para reducir la probabilidad de truncamiento con 1800 tokens. Las
pruebas de regresión son offline; todavía hace falta una tercera ejecución
humana completa antes de cerrar la evidencia Langfuse.

## Intento real OpenAI/Langfuse 3 — cierre del último turno

- [Manifest](runs/real-openai-20260716-224955/run.json)
- [Estado](runs/real-openai-20260716-224955/task_state.json)
- [Fuentes](runs/real-openai-20260716-224955/sources.json)
- [Eventos](runs/real-openai-20260716-224955/events.json)

El tercer intento terminó `blocked` con exit 2 y trace id
`3a3129ac11a8a4e0355bea72df2660e6`. Confirmó que las correcciones anteriores
funcionan: workspace limpio, ocho tool calls permitidas, seis archivos leídos y
ocho evidencias repository preservadas. No hubo comandos, cambios ni diferencia
entre los checksums before/after.

La brecha fue el protocolo del último turno: aunque el prompt ordenaba enviar el
resultado estructurado, las tools de exploración seguían expuestas y el modelo
realizó otra lectura. La corrección posterior ofrece únicamente
`submit_agent_result` en el último turno. Esto fuerza el cierre del rol sin
aumentar las cuatro iteraciones ni el presupuesto de API. Todavía falta
reejecutar y alcanzar los cinco roles.

## Intento real OpenAI/Langfuse 4 — implementación y entorno de test

- [Manifest](runs/real-openai-20260716-225405/run.json)
- [Estado](runs/real-openai-20260716-225405/task_state.json)
- [Fuentes](runs/real-openai-20260716-225405/sources.json)
- [Diff](runs/real-openai-20260716-225405/diff.patch)

El cuarto intento alcanzó Explorer, Researcher, Implementer y Tester. Consultó
RAG y web con provenance, modificó exactamente service, router y test para
`GET /health/ready`, y preservó el diff. Terminó `blocked` con exit 2 y trace
id `8a53e02921325eb21456671398423539`.

Tester bloqueó correctamente `bash -lc` y luego ejecutó `pytest -q`, que
terminó 4 porque el entorno principal no tenía FastAPI. Esa falla activó
replanificación y agotó el límite global de 15 llamadas antes de Reviewer. Para
separar código de entorno, se ejecutó el mismo test sobre la misma copia con el
`.venv` del demo ya existente: 3 passed, una advertencia, exit 0. No se instaló
ninguna dependencia. La corrida final debe exponer ese entorno por `PATH` y
usar un máximo global explícito de 20 llamadas, equivalente a cinco roles por
cuatro turnos.

## Intento real OpenAI/Langfuse 5 — memoria histórica y contrato de Researcher

- [Manifest](runs/real-openai-20260716-230132/run.json)
- [Estado](runs/real-openai-20260716-230132/task_state.json)
- [Memoria recuperada](runs/real-openai-20260716-230132/memory.json)
- [Fuentes](runs/real-openai-20260716-230132/sources.json)

El quinto intento terminó `blocked` con exit 2 y trace id
`38413a02a1e66af00ec8d7de6fc26def`. El workspace quedó sin cambios y con
checksums iguales. Demostró memoria real entre sesiones: recuperó resultados de
Explorer, Researcher, Implementer, Tester y replan del intento anterior antes de
consultar repository, RAG y web.

Una function call malformada fue recuperada, pero Researcher tomó la falla
histórica de pytest como bloqueo actual y se declaró `blocked`. Esa decisión
mezclaba responsabilidades: Researcher debe determinar si hay evidencia para
implementar, mientras Tester valida después. La corrección hace prevalecer
evidencia repository actual ante memoria histórica, prohíbe bloquear por trabajo
pendiente de roles posteriores y eleva la salida a 2400 tokens para reducir
truncamientos, manteniendo 20 llamadas máximas.

## Intento real OpenAI/Langfuse 6 — política de comandos del Tester

- [Manifest](runs/real-openai-20260716-230907/run.json)
- [Estado](runs/real-openai-20260716-230907/task_state.json)
- [Fuentes](runs/real-openai-20260716-230907/sources.json)
- [Diff](runs/real-openai-20260716-230907/diff.patch)

El sexto intento terminó `blocked` con exit 2 y trace id
`a237b059da41edb2fe38febbc160a693`. Completó Explorer, Researcher e
Implementer, recuperó memoria y evidencia repository/RAG/web, y produjo el diff
correcto en los tres archivos previstos. Tester intentó ejecutar
`/usr/bin/env bash -lc "pytest -q"`; la policy lo denegó correctamente porque
los comandos arbitrarios no admiten wrappers de shell. Tras replanificar, no
volvió a solicitar el comando directo y se bloqueó antes de Reviewer.

No se amplió la allowlist ni se debilitó `shell=False`. El contrato de Tester
ahora exige `run_command` con argv directo, por ejemplo `['pytest', '-q']`, y
prohíbe expresamente `/usr/bin/env`, `bash`, `sh`, `-c` y `-lc`. Un test
unitario verifica esa instrucción sin llamar a proveedores reales.

Como verificación separada de la traza, el diff exacto preservado en
`tmp/demo-runtime/real-openai-20260716-230907` se ejecutó con el entorno aislado
del demo: `3 passed`, una advertencia de deprecación, exit 0. Esto comprueba el
cambio, pero no se presenta como si el Tester lo hubiera ejecutado dentro de la
traza.

## Ejecución real completa OpenAI/Langfuse 7

- [Manifest](runs/real-openai-20260716-231650/run.json)
- [Estado compartido](runs/real-openai-20260716-231650/task_state.json)
- [Fuentes](runs/real-openai-20260716-231650/sources.json)
- [Comandos](runs/real-openai-20260716-231650/commands.json)
- [Diff](runs/real-openai-20260716-231650/diff.patch)
- [Resumen](runs/real-openai-20260716-231650/summary.md)

La séptima ejecución terminó `completed`, exit 0, con trace id
`8248244a2224f1dc099fff1240e5c040`. Completó en orden Explorer, Researcher,
Implementer, Tester y Reviewer. Recuperó memoria de sesiones anteriores,
consultó repository/RAG/web, modificó solamente service/router/test, ejecutó
`pytest -q` directamente y obtuvo `3 passed`, exit 0. Reviewer aceptó el diff y
los criterios; el estado registró `reviewing -> completed`.

El bundle conserva 87 evidencias tipadas y el diff completo. Una advertencia de
pytest contenía el home local; el exportador y el artifact se sanitizaron a
`${HOME}` sin cambiar resultado, comando, digests, estado ni trace id. El
escaneo posterior no encontró paths del autor, claves ni material PEM.

## Integridad y limitaciones

Los archivos reflejan ejecuciones deterministas del 2026-07-14. Los comandos
usan subprocess reales. La regeneración de Fase 09 reemplazó el workspace y el
intérprete locales por `${WORKSPACE}` y `${PYTHON}` en todos los payloads
persistidos, manteniendo exit codes y digests del output real.

No se editaron manifests para inventar trace ids. No hay capturas guardadas. La
ubicación y el procedimiento de captura están en
[`screenshots/README.md`](screenshots/README.md).
