# Reflexión basada en ejecuciones

## Qué funcionó

La separación por puertos hizo posible ejecutar una suite amplia sin red. Las
tools y policy se probaron con filesystem/subprocess reales en workspaces
temporales, mientras LLM, embeddings, web y tracing usaron fakes. Esto permitió
que los escenarios A/B modificaran sólo copias de la fixture y conservaran
estado, fuentes, diff y exit codes verificables.

La máquina de estados hizo visible el orden de roles. En A y B2, Reviewer sólo
aceptó después de Tester. En B, SQLite demostró valor fuera de un historial: la
segunda instancia recuperó cuatro observaciones y aplicó la convención de
routers finos.

La seguridad fue comprobable, no sólo declarativa. En C, instalar y commit
quedaron en `requires_approval`, `.github/**` quedó `denied`, no se modificaron
archivos y el artifact conservó las decisiones.

## Qué falló o quedó incompleto

El check de C falla intencionalmente dos veces. El primer fallo provoca un
replan; el segundo agota el presupuesto. El sistema termina `blocked`, que es
correcto para la prueba, pero no resuelve el pedido original.

La primera ejecución externa quedó registrada el 2026-07-16 con trace id
`e3e18abb93d9e4cbc427b6bdfc03caaa`, pero terminó `blocked` en Explorer. El
modelo hizo cuatro rondas útiles de tools y el límite se agotó antes del submit;
la primera lista estuvo además contaminada por un `.venv` de 43 MB y caches del
seed. No hubo escrituras ni comandos, por lo que el fallo fue seguro y
diagnosticable, no un falso éxito.

El segundo intento, trace id `fb1df898e7cbb0a88eebc6d3aa2c8cab`, confirmó
que el reset ya estaba limpio y permitió diez decisiones de policy. Falló
después porque una function call de OpenAI contenía argumentos que no eran JSON
válido. Tampoco modificó archivos ni ejecutó comandos. Este fallo reveló que el
boundary del provider trataba una salida recuperable como excepción fatal.

El tercer intento, trace id `3a3129ac11a8a4e0355bea72df2660e6`, avanzó más:
preservó ocho evidencias repository limpias y demostró que el parser ya no
abortaba. Terminó `blocked` porque Explorer usó una tool de lectura en el
cuarto turno aunque el prompt pedía submit. El problema no era falta de
evidencia sino que el runtime todavía ofrecía tools de trabajo en el turno de
cierre.

El cuarto intento, trace id `8a53e02921325eb21456671398423539`, completó
Explorer, Researcher e Implementer, recuperó RAG/web y produjo el diff correcto
para service, router y test. Tester detectó que FastAPI no estaba instalado en
el entorno principal; el replan posterior agotó 15/15 antes de Reviewer. La
misma copia modificada pasó sus tres tests con el entorno aislado del demo. Esto
separó un fallo de infraestructura de un fallo de implementación y evitó
modificar dependencias del agente.

El quinto intento, trace id `38413a02a1e66af00ec8d7de6fc26def`, demostró
memoria persistente real al recuperar el aprendizaje del cuarto intento. A la
vez reveló un riesgo de memoria: Researcher trató el fallo histórico de Tester
como condición vigente y se bloqueó aunque ya tenía evidencia RAG/web. El
contrato se ajustó para que la evidencia actual prevalezca y cada rol evalúe
sólo su propia responsabilidad. Esto conserva memoria sin convertirla en una
fuente de verdad inmutable.

El sexto intento, trace id `a237b059da41edb2fe38febbc160a693`, superó ese
bloqueo: Explorer, Researcher e Implementer completaron y el cambio mínimo quedó
aplicado. Tester usó `/usr/bin/env bash -lc "pytest -q"`; la policy lo rechazó
como debía y evitó abrir una vía de shell arbitrario. La mejora no amplía
permisos: enseña al rol a invocar `pytest -q` como argv directo, que es el
contrato real de `run_command`.

El diff del sexto intento pasó sus tres tests al ejecutarlo después sobre la
misma copia aislada, con exit 0. La prueba confirma la implementación, pero se
mantiene separada del resultado `blocked`: no se atribuye al Tester una acción
que no ocurrió dentro de la traza.

El séptimo intento, trace id `8248244a2224f1dc099fff1240e5c040`, completó el
objetivo: los cinco roles terminaron en orden, Tester ejecutó `pytest -q` con
`3 passed` y Reviewer aceptó el cambio. Esto confirmó que la policy estricta y
la ejecución real pueden convivir sin wrappers de shell ni permisos extra. La
única acción de evidencia restante es capturar esa traza desde Langfuse.

La estrategia cambió sin aumentar el costo: el reset excluye entornos, caches y
metadata generada; el prompt reserva el último turno, permite paralelismo en
lotes de hasta cuatro tools, el adaptador transforma argumentos malformados en
un error estructurado recuperable y el turno final sólo expone
`submit_agent_result`. `run` conserva deliberadamente el harness básico
migrado. El caso completo se ejecuta por `demo real`, con límites de llamadas e
iteraciones, en una copia de la fixture. Los artifacts A/B/C siguen probando
coordinación determinista; un bundle real completo será evidencia adicional, no
un reemplazo.

Los tests HTTP propios de FastAPI no se ejecutaron porque sus dependencias no
fueron instaladas. `compileall` y los tests de contrato confirman sintaxis y
contenido esperado, pero dan menos confianza que levantar la app y usar
`TestClient`.

## Loops y falta de evidencia

El evento real de no-progreso está en escenario C: dos errores normalizados
iguales disparan `replan` y no hay tercer intento. La estrategia cambia, pero el
backend repite el mismo check después de implementar; al no aparecer nueva
evidencia ni una hipótesis diferente, se detiene.

La primera corrida real demostró además el límite de iteraciones: emitió
`loop.no_progress`, explicó qué intentó y se detuvo. Acción repetida, relectura,
A-B-A-B y fases estancadas permanecen demostradas por unit tests.

El sistema también tiene un terminal `STOPPED_NO_EVIDENCE` y tests de Research
sin fuentes, pero ninguna de las tres demos deterministas terminó allí. La
ejecución real completa ya está preservada; quedan pendientes únicamente sus
capturas verificadas desde la UI. Los intentos bloqueados y sus trace ids no se
simularon ni se ocultaron.

## Decisiones de estrategia

- Se eligió RAG local con snapshots y embeddings fake para que A fuera
  repetible y probara que web no se llama si hay evidencia.
- Se separó memoria lexical de RAG vectorial: las convenciones de proyecto no
  necesitan mezclarse con documentación externa.
- Se trató `blocked` como outcome válido de seguridad en lugar de forzar un
  “éxito”.
- Se guardaron digests y no output completo de comandos en artifacts para
  reducir payload, aunque esto limita el diagnóstico posterior.
- Langfuse y Tavily se agregaron sólo después de autorización explícita; la demo
  limita Tavily a una búsqueda `basic` y exige `--confirm-cost`.

## Limitaciones y mejoras futuras

Prioridades:

1. reejecutar la tarea real corregida, revisar su resultado y guardar trace
   id/capturas verificadas;
2. instalar la fixture en un entorno aislado y ejecutar sus tests HTTP;
3. reemplazar el retrieval lineal por un índice adecuado si crece el corpus y
   evaluar precision/recall con un set de queries;
4. evaluar con corridas reales qué thresholds de no-progreso reducen costo sin
   cortar exploraciones útiles;
5. ampliar la sanitización portable aplicada en Fase 09 a cualquier nuevo tipo
   de locator que se agregue al schema de artifacts;
6. probar sobre un repositorio Git real para status/diff nativos.
