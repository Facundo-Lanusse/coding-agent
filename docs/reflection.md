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

La integración externa no se completó. Langfuse no está instalado y la prueba
real se saltó; no hay trace id ni screenshots. `demo real` valida prerrequisitos
pero nunca hace la llamada. Tampoco existe un proveedor web real compuesto.

La CLI tiene una brecha: `run` usa el harness OpenAI básico y `demo` usa cinco
agentes con backend scripted. No hay un camino real único que combine
MainAgent, memoria, RAG, OpenAI y Langfuse. Por lo tanto los artifacts prueban
la coordinación determinista, no autonomía con LLM.

Los tests HTTP propios de FastAPI no se ejecutaron porque sus dependencias no
fueron instaladas. `compileall` y los tests de contrato confirman sintaxis y
contenido esperado, pero dan menos confianza que levantar la app y usar
`TestClient`.

## Loops y falta de evidencia

El evento real de no-progreso está en escenario C: dos errores normalizados
iguales disparan `replan` y no hay tercer intento. La estrategia cambia, pero el
backend repite el mismo check después de implementar; al no aparecer nueva
evidencia ni una hipótesis diferente, se detiene.

Las otras variantes (acción repetida, relectura, A-B-A-B, fases estancadas y
límite) sólo están demostradas por unit tests. No deben presentarse como runs de
la fixture.

El sistema también tiene un terminal `STOPPED_NO_EVIDENCE` y tests de Research
sin fuentes, pero ninguna de las tres demos entregadas terminó allí. La falta de
evidencia observada en la entrega es externa: faltan credenciales/SDK/traza
Langfuse y no se simuló su existencia.

## Decisiones de estrategia

- Se eligió RAG local con snapshots y embeddings fake para que A fuera
  repetible y probara que web no se llama si hay evidencia.
- Se separó memoria lexical de RAG vectorial: las convenciones de proyecto no
  necesitan mezclarse con documentación externa.
- Se trató `blocked` como outcome válido de seguridad en lugar de forzar un
  “éxito”.
- Se guardaron digests y no output completo de comandos en artifacts para
  reducir payload, aunque esto limita el diagnóstico posterior.
- No se instaló Langfuse ni FastAPI sin una autorización explícita de
  dependencias.

## Limitaciones y mejoras futuras

Prioridades:

1. implementar un backend LLM de agentes y componerlo desde una CLI única con
   MainAgent, ContextManager, memoria, RAG y tracer;
2. agregar Langfuse como dependencia aprobada, ejecutar una tarea real acotada
   y guardar trace id/capturas verificadas;
3. instalar la fixture en un entorno aislado y ejecutar sus tests HTTP;
4. reemplazar el retrieval lineal por un índice adecuado si crece el corpus y
   evaluar precision/recall con un set de queries;
5. conectar todas las estrategias de `NoProgressDetector` al orquestador, no
   sólo al escenario scripted;
6. ampliar la sanitización portable aplicada en Fase 09 a cualquier nuevo tipo
   de locator que se agregue al schema de artifacts;
7. probar sobre un repositorio Git real para status/diff nativos.
