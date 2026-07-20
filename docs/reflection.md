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

Las corridas externas fallidas fueron útiles para endurecer el límite entre el
modelo y las tools: argumentos JSON inválidos se devuelven como error
estructurado, el turno final sólo permite `submit_agent_result`, Tester usa argv
directo y la evidencia actual prevalece sobre memoria histórica contradictoria.
Todos esos fallos terminaron de forma explícita, sin presentarse como éxitos.

Una corrida posterior quedó `blocked` porque cuatro turnos no alcanzaron para
que Implementer inspeccionara, editara y cerrara. Se mantuvo el tope global de
20 llamadas, se amplió a seis turnos por rol y se aclaró que Researcher entrega
evidencia a Implementer y que Implementer es dueño de las escrituras.

La corrida corregida `real-openai-20260717-003912`, trace id
`cd6e9589a8074d1d52c738d79373c128`, completó el objetivo: los cinco roles
terminaron en orden, Tester ejecutó `pytest -q` con `3 passed` y Reviewer aceptó
el diff mínimo. El reset mantuvo el workspace aislado y la memoria recuperó
resultados históricos sin desplazar la evidencia actual. La traza y su metadata
quedaron preservadas mediante capturas verificadas de la UI Langfuse.

El 2026-07-18 se conservaron cinco corridas reales adicionales: dos terminaron
`blocked`, dos `stopped_no_evidence` y `real-openai-20260718-215957` volvió a
completar los cinco roles, ejecutar `pytest -q` con exit 0 y obtener aceptación
de Reviewer. Mantener también los intentos fallidos permite auditar los límites
de evidencia y ejecución sin presentarlos como éxitos.

Los escenarios deterministas usan `compileall` y un contrato estático para no
depender del entorno FastAPI. La corrida real sí ejecutó los tres tests HTTP con
`TestClient` en el entorno aislado del demo.

## Loops y falta de evidencia

El evento real de no-progreso está en escenario C: dos errores normalizados
iguales disparan `replan` y no hay tercer intento. La estrategia cambia, pero el
backend repite el mismo check después de implementar; al no aparecer nueva
evidencia ni una hipótesis diferente, se detiene.

La primera corrida real demostró además el límite de iteraciones: emitió
`loop.no_progress`, explicó qué intentó y se detuvo. Acción repetida, relectura,
A-B-A-B y fases estancadas permanecen demostradas por unit tests.

El sistema también tiene un terminal `STOPPED_NO_EVIDENCE` y tests de Research
sin fuentes. Ninguna de las tres demos deterministas terminó allí, pero las
corridas reales `real-openai-20260718-213510` y
`real-openai-20260718-213701` sí lo hicieron. Las capturas verificadas de la
primera ejecución completa y los bundles con trace ids de todos los intentos
están preservados; los fallos no se simularon ni se ocultaron.

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

1. reemplazar el retrieval lineal por un índice adecuado si crece el corpus y
   evaluar precision/recall con un set de queries;
2. evaluar con corridas reales qué thresholds de no-progreso reducen costo sin
   cortar exploraciones útiles;
3. ampliar la sanitización portable a cualquier nuevo tipo
   de locator que se agregue al schema de artifacts;
4. probar sobre un repositorio Git real para status/diff nativos.
