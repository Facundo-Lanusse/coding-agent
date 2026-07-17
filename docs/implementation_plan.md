# Plan de implementación de la entrega

## Objetivo

Mantener en `main` el proyecto profesional completo y producir en
`entrega-tp` una versión enfocada exclusivamente en la consigna.

## Baseline verificado

Commit base: `c3f882b`.

Antes de la simplificación se ejecutó `make check`:

- 142 tests pasaron;
- 1 integración Langfuse se omitió por falta de credenciales;
- Ruff pasó;
- mypy pasó sobre 101 archivos.

No se encontraron patrones de claves ni rutas absolutas del usuario en el
commit.

## Alcance de la simplificación

Estado: `DONE`.

- eliminar Docker, prompts de desarrollo, notebook legado e informes históricos;
- conservar código productivo requerido, corpus RAG, fixture FastAPI y evidencia;
- conservar sólo la corrida real completa y los bundles A/B/C relevantes;
- retirar el generador determinista hardcodeado del paquete productivo;
- dividir backend OpenAI, slicing de contexto y persistencia de artifacts;
- reducir README y documentación a los ocho entregables;
- mantener registry y descubrimiento de tools sin acoplar el núcleo;
- ejecutar suite, Ruff, mypy, build, CLI y escaneos finales.

## Capacidades que deben permanecer

1. Harness base con tools, plan, supervisión y límite.
2. MainAgent más Explorer, Researcher, Implementer, Tester y Reviewer.
3. Estado compartido estructurado y máquina de estados.
4. Memoria SQLite por proyecto.
5. RAG con chunking, embeddings, vector store y provenance.
6. Web sólo como fallback.
7. Context budget, resumen, replanificación y no-progreso.
8. Configuración validada antes de cada tool.
9. Langfuse real con sanitización y no-op para tests.
10. CLI de configuración, RAG, harness y demo real.
11. Tests deterministas sin red.
12. Evidencia de RAG, memoria, seguridad y una traza real.

## Cierre de fase

Resultados ejecutados el 2026-07-16:

- `make check`: exit 0; 134 tests pasaron, 1 integración Langfuse omitida por
  falta de credenciales, Ruff sin hallazgos y mypy sin issues;
- `make coverage`: exit 0; cobertura global 84%, sin umbral obligatorio en la
  consigna;
- primer `make build`: exit 2 por DNS restringido al crear el entorno aislado;
- segundo `make build` con red aprobada: exit 0; wheel y sdist construidos;
- `coding-agent --help`: exit 0;
- `coding-agent config validate`: exit 0;
- ingesta y query RAG con embeddings fake: exit 0, tres documentos y evidencia
  FastAPI suficiente;
- tests HTTP del seed FastAPI: 2 pasaron, exit 0, con una advertencia de
  deprecación de Starlette sobre HTTPX;
- guard de demo real sin `--confirm-cost`: exit 2 esperado y cero llamadas API;
- `git diff --check`: exit 0;
- escaneos de frameworks prohibidos, patrones de claves, rutas absolutas y
  referencias eliminadas: sin coincidencias.

Diff de trabajo respecto de `main` antes del commit de entrega: 92 paths
trackeados modificados/eliminados más tres módulos nuevos. Git informa 647
inserciones trackeadas y 18.041 eliminaciones; los tres módulos nuevos suman 718
líneas. Se retiraron seis corridas fallidas, pero se conservó la corrida real
completa y los bundles A/B/C.

Supuesto no verificado: no se abrió la UI Langfuse en esta fase. La captura de
la traza completa sigue siendo una acción humana explícita.

## Estabilización de la demo real en `entrega-tp`

El 2026-07-17 una nueva corrida real (`real-openai-20260717-003010`) alcanzó
OpenAI, memoria, RAG, Tavily y Langfuse, pero terminó bloqueada en Implementer.
El rol consumió sus cuatro turnos leyendo archivos y delegó incorrectamente la
edición; además, Researcher recuperó correctamente una tool call con argumentos
JSON inválidos. No hubo cambios de fixture ni tests ejecutados en esa corrida.

Se mantuvo el límite global de 20 llamadas y se amplió de cuatro a seis turnos
por rol para reservar margen de escritura y cierre. Los contratos indican ahora
que Researcher entrega evidencia a Implementer y que Implementer aplica el
cambio cuando dispone de `write_file`, sin delegarlo a Reviewer o CI. La salida
estructurada también debe ser breve.

Verificación offline posterior:

- tests focalizados de backend y runtime: 12 pasaron;
- `make check`: 136 tests pasaron y 1 integración Langfuse se omitió por falta
  de credenciales; Ruff y mypy pasaron;
- la corrida real `real-openai-20260717-003912` terminó `completed`: los cinco
  roles finalizaron, `pytest -q` tuvo exit 0, Reviewer aceptó y Langfuse emitió
  el trace `cd6e9589a8074d1d52c738d79373c128`;
- se guardaron capturas verificadas del grafo completo y su metadata desde la
  UI Langfuse.
