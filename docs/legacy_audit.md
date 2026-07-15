# Auditoría inicial del TP anterior

## Resumen

El notebook contiene 24 celdas y construye un coding agent básico en Google
Colab.

## Elementos reutilizables

- Cliente de OpenAI configurado mediante un secreto de Colab.
- Modelo configurable en una variable, actualmente `gpt-5-nano`.
- Clonado de un repositorio GitHub y definición de un workspace.
- Herramientas:
  - `read_file`
  - `write_file`
  - `list_files`
  - `run_command`
  - `web_search` mediante Tavily
- Definiciones de tools para function calling.
- Harness iterativo que devuelve los resultados de las tools al modelo.
- Historial de conversación.
- Plan mode con aprobación humana.
- Supervision mode para escritura y ejecución de comandos.
- Lista inicial de comandos prohibidos.
- Timeout de comandos.
- Límite de 15 iteraciones.

## Evidencia útil del informe del notebook

- Una tarea amplia de exploración llegó a 15 iteraciones y terminó con
  `Max iterations reached without a final answer`.
- Una tarea concreta creó una calculadora y tests.
- El primer `pytest -q` fue demasiado amplio y falló por tests ajenos.
- El agente cambió a un test dirigido y obtuvo cuatro tests aprobados.

Estos casos son buenos antecedentes para implementar detección de loops,
selección de checks y replanificación.

## Problemas a corregir

- La implementación está acoplada a Google Colab:
  `google.colab.userdata`, paths `/content/...`, comandos `!pip`, e `input()`.
- El código está concentrado en celdas y no tiene una estructura modular.
- Usa Chat Completions; el nuevo proyecto debe encapsular el proveedor y usar
  Responses API.
- No existen agente principal ni los cinco subagentes requeridos.
- No hay estado compartido estructurado.
- No hay memoria persistente por proyecto.
- No hay RAG, chunking, embeddings ni vector store.
- No se atribuyen claramente fuentes de repositorio, memoria, RAG, web e
  inferencias.
- No existe manejo de contexto ni resumen de sesiones.
- El límite de iteraciones corta la ejecución, pero no detecta no-progreso.
- La seguridad se basa en búsqueda de substrings y `shell=True`.
- `resolve_path` usa una comparación textual con `startswith`, insuficiente para
  validar containment de paths.
- No hay políticas configurables de lectura, escritura, comando y aprobación.
- Las políticas no se validan formalmente antes de cada tool call.
- No hay protección explícita frente a symlinks, traversal, outputs enormes o
  escritura atómica.
- No hay observabilidad ni trazas de LLM/tools/RAG/costo.
- No hay suite profesional de tests, lint, type checking ni CLI.
- La última celda redefine `read_file` de forma insegura, fuera del control del
  workspace.

## Recomendación de migración

No continuar desarrollando el notebook. Conservarlo en `legacy/` y migrar los
conceptos válidos a un paquete Python bajo `src/`, con interfaces testeables y
configuración externa.
