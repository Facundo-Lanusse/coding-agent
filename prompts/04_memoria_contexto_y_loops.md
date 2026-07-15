Implementá únicamente la Fase 04: memoria persistente, manejo de contexto,
resumen de sesiones y detección de loops/no-progreso.

## Memoria persistente

Usá SQLite y una capa repository desacoplada.

La memoria debe ser por proyecto, más allá del historial de conversación, y
poder guardar:

- arquitectura;
- archivos importantes;
- dependencias;
- comandos útiles;
- convenciones;
- decisiones;
- bugs investigados;
- resultados de checks;
- resumen de sesiones previas.

Cada registro debe incluir como mínimo:

- id;
- project_id;
- category;
- content;
- source_type;
- source_reference;
- confidence;
- session_id;
- created_at;
- updated_at;
- last_verified_at;
- stale_after;
- metadata JSON.

No guardar cualquier texto del modelo como hecho. Diferenciar observaciones,
decisiones e inferencias. Implementar invalidación o marcado stale.

## Context management

Implementá un `ContextManager` que:

- seleccione solo evidencia relevante;
- aplique presupuestos configurables;
- resuma información antigua;
- preserve decisiones y errores abiertos;
- no envíe todo el repositorio ni todo el historial en cada turno;
- permita inspeccionar qué contexto fue incluido y omitido.

La generación de resúmenes debe estar detrás de una interfaz para usar fake en
tests.

## Loop/no-progress detection

Implementá fingerprints normalizados de:

- tool + argumentos relevantes;
- comando;
- archivo leído;
- error;
- resultado.

Detectar al menos:

- misma acción repetida;
- mismo comando con mismo error;
- relectura sin nueva información;
- alternancia cíclica de dos acciones;
- agotamiento de iteraciones;
- múltiples fases sin nueva evidencia ni cambios.

Al detectar no-progreso, el sistema debe elegir explícitamente entre:

- cambiar estrategia;
- replanificar;
- detenerse;
- pedir ayuda;
- solicitar evidencia o permiso.

Registrar la razón y la estrategia.

Tests obligatorios:

- memoria persiste al cerrar y abrir otra instancia;
- separación por project_id;
- registro stale;
- recuperación por categoría y relevancia;
- resumen conserva decisiones;
- presupuesto de contexto respetado;
- mismo error dos veces dispara replanificación;
- tercera repetición no ejecuta otra vez;
- ciclo A-B-A-B detectado;
- relectura sin evidencia detectada;
- nueva evidencia reinicia no-progreso;
- resultado final explica qué se intentó y qué falta.

Ejecutá tests, Ruff y mypy. Actualizá documentación y matriz. No implementes RAG
todavía. Detenete.
