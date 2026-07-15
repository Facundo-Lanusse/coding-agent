# Contexto, resúmenes y detección de no-progreso

## Selección de contexto

`ContextManager` recibe una consulta, candidatos tipados y un
`ContextBudget`. No lee un repositorio ni un historial completo: selecciona
datos que el llamador ya clasificó.

Tipos de candidato:

- decisiones y errores abiertos;
- evidencia y memoria;
- historial y resúmenes de sesión;
- resumen generado.

El presupuesto limita `max_chars`, `max_items`, tamaño de resumen y relevancia
mínima. Decisiones y errores abiertos están protegidos. Si no caben, se lanza
`ContextBudgetError` en vez de truncarlos silenciosamente.

El resto se ordena por el máximo entre relevancia declarada y solapamiento
lexical con la consulta. Cada elemento no incluido queda en el manifest con
razón `irrelevant`, `budget` o `summarized`. `ContextSelection` expone incluidos,
omitidos, summary, caracteres usados y presupuesto original.

## Resúmenes

`SummaryProvider` es una interfaz. Sólo historial, memoria y resúmenes de sesión
omitidos por presupuesto son resumibles. `SummaryRequest` enumera decisiones y
errores protegidos; la respuesta debe declarar que los preservó. Si omite uno,
se lanza `SummaryContractError`. Los unit tests usan un fake determinista; no
hay adaptador LLM productivo de summaries compuesto en la CLI.

## Contexto de subagentes

Por separado, `MainAgent._build_context` produce una vista por rol:

- Explorer no ve resultados previos;
- Researcher ve Explorer;
- Implementer ve Explorer y Researcher;
- Tester ve Implementer y cambios;
- Reviewer ve los cuatro roles, evidencia, cambios y checks.

Esta minimización está integrada en el orquestador. El `ContextManager`
presupuestado no está conectado a `_build_context`; por eso los budgets y
summaries están implementados/probados, pero no se observan en las demos.

## Fingerprints

`FingerprintFactory` normaliza y hashea:

- nombre de tool más argumentos relevantes;
- comando como string o secuencia argv;
- path leído más digest del contenido;
- código/mensaje de error y comando;
- resultado/status/output digest;
- conjunto de ids de evidencia y cambios.

La normalización ordena mappings, uniforma paths/texto y elimina variaciones de
mensajes que no representan progreso. El fingerprint no reemplaza el detalle
auditable del intento.

## Señales de no-progreso

`NoProgressDetector` detecta:

| Razón | Condición | Estrategia predeterminada |
|---|---|---|
| `repeated_action` | misma tool normalizada alcanza el umbral | `stop` |
| `repeated_error` | mismo comando/código/error alcanza el umbral | `replan` |
| `repeated_read` | mismo archivo/digest sin evidencia o cambios nuevos | `request_evidence_or_permission` |
| `alternating_cycle` | secuencia A-B-A-B | `change_strategy` |
| `iteration_limit` | se consume el máximo | `stop` |
| `stagnant_phases` | fases consecutivas sin delta | `ask_help` |

Cada `NoProgressSignal` registra explicación, intentos, información faltante,
estrategia y si permite ejecutar. `before_tool` puede bloquear una tercera
acción repetida antes del efecto. `note_progress` reinicia contadores cuando
aparecen ids nuevos de evidencia o cambios.

## Integración y resultado final

La clase emite `loop.no_progress` mediante `Tracer`. Los tests unitarios
verifican las seis familias de señales y que el reporte final enumere qué se
intentó y qué falta.

La demo C integra específicamente errores repetidos: el mismo test intencional
falla dos veces, se registra estrategia `replan`, `MainAgent` consume un replan
y termina `blocked`. El archivo
[`evidence/runs/scenario-c-safety/commands.json`](evidence/runs/scenario-c-safety/commands.json)
tiene exactamente dos ejecuciones del check fallido, no tres.

Limitación: `MainAgent` genérico no instancia `NoProgressDetector` ni traduce
todas sus estrategias automáticamente. La integración completa está scripted
en la demo C; el harness básico conserva sólo su máximo de iteraciones.

