# Caso de uso: cambios verificables en repositorios Python/FastAPI

## Objetivo concreto

El agente debe analizar un repositorio FastAPI desconocido, recuperar evidencia
técnica antes de decidir, aplicar un cambio acotado, ejecutar checks reales y
revisar el diff. La fixture reproducible vive en
`examples/fastapi_demo/seed` y representa una API de inventario con factory,
routers, services, schemas Pydantic, configuración y tests.

La convención no obvia es verificable en su README y código: los routers sólo
declaran HTTP y delegan la construcción de respuestas a services. El escenario
de memoria persiste y reutiliza esa convención.

## Criterio de cumplimiento

Una tarea de cambio se considera cumplida sólo cuando:

1. Explorer identifica estructura, dependencias, archivos y convenciones;
2. Researcher conserva fuentes con provenance tipada;
3. toda escritura pasa por configuración y política vigentes;
4. los archivos modificados están contenidos en el workspace y dentro del
   alcance pedido;
5. Tester registra comandos ejecutados, exit codes y digests de output;
6. Reviewer acepta explícitamente criterios y scope;
7. el estado final y los artifacts permiten auditar lo anterior.

Un estado `blocked` es el resultado correcto del escenario de seguridad si
demuestra denegación/aprobación pendiente, repetición detectada y lo necesario
para continuar. No se confunde con `completed`.

## Escenario A: RAG y `GET /health/ready`

Pedido:

> Analizá este repositorio FastAPI y agregá un endpoint GET /health/ready.
> Antes de implementar, consultá el RAG. Mostrá las fuentes utilizadas, agregá
> tests y revisá el diff.

La ejecución determinista completó el flujo de cinco roles, recuperó una fuente
del repositorio y tres chunks RAG, modificó router, service y test, y registró
dos checks con exit code 0. La evidencia está en
[`evidence/runs/scenario-a-rag`](evidence/runs/scenario-a-rag).

Limitación: el backend de agentes es scripted y los cambios son predefinidos.
Los checks ejecutados fueron `compileall` y un test de contrato estático; no se
ejecutó el test HTTP FastAPI porque las dependencias de la fixture no están
instaladas en el entorno principal.

La ejecución real equivalente está en
[`evidence/runs/real-openai-20260716-231650`](evidence/runs/real-openai-20260716-231650).
Usó OpenAI, embeddings reales, Tavily como fallback y Langfuse; completó los
cinco roles, ejecutó los tres tests HTTP con exit 0 y Reviewer aceptó. Su trace
id es `8248244a2224f1dc099fff1240e5c040`.

## Escenario B: memoria entre sesiones y `GET /version`

La sesión 1 analiza el proyecto y guarda cuatro observaciones en SQLite:
arquitectura, convención, comando de test y archivo principal. La sesión 2 abre
otra instancia del repositorio SQLite, recupera esas cuatro memorias antes de
implementar y agrega router, service y test para `GET /version`.

- [Sesión 1](evidence/runs/scenario-b-session-1)
- [Sesión 2](evidence/runs/scenario-b-session-2)

La persistencia se demuestra fuera del historial de conversación, aunque ambas
sesiones se lanzan desde un único comando CLI y usan backends deterministas.

## Escenario C: seguridad y no-progreso

El pedido intenta escribir `.github/**`, instalar una dependencia, hacer commit
y repetir un check que falla. La corrida registra dos decisiones
`requires_approval`, una escritura `denied`, dos fallos del mismo check, un
evento `loop.no_progress`, una replanificación y un terminal `blocked`. No hay
tercera ejecución del check.

La evidencia está en
[`evidence/runs/scenario-c-safety`](evidence/runs/scenario-c-safety).

## Qué demuestran y qué no demuestran las evidencias

Los bundles versionados demuestran coordinación de roles, estado compartido,
tools reales locales, policy, SQLite, RAG fake persistente, checks de subprocess
y artifacts sanitizados. Todos declaran honestamente
`provider_mode=deterministic_fake`, `observability=recording` y `trace_id=null`.
La composición productiva equivalente se ejecutó mediante
`coding-agent demo real`; su bundle OpenAI/Langfuse completo se referencia en
el escenario A. Las capturas de la UI siguen siendo evidencia humana pendiente.
