Implementá únicamente la Fase 01 definida en
`docs/implementation_plan.md`: scaffold profesional y migración del harness
básico. No implementes todavía subagentes, memoria, RAG ni Langfuse.

Antes de modificar:

1. Releé `AGENTS.md`.
2. Releé la consigna y la documentación de arquitectura.
3. Informá los archivos que vas a crear.
4. Verificá que no exista código productivo que pueda ser sobrescrito.

Objetivos:

- Crear un paquete instalable con layout `src/`.
- Crear `pyproject.toml` con dependencias runtime y development separadas.
- Crear un CLI mínimo.
- Crear configuración tipada y carga de variables de entorno.
- Crear una interfaz `LLMClient` desacoplada.
- Implementar un adaptador OpenAI mediante Responses API, sin Agents SDK.
- Migrar el loop básico del notebook a clases y funciones testeables.
- Preservar conceptualmente plan mode, supervision mode, máximo de
  iteraciones y ejecución real de tools.
- Crear modelos estructurados para requests, function calls y outputs básicos.
- No hardcodear API keys ni modelos.
- Mantener el notebook sin cambios dentro de `legacy/`.

Estructura mínima esperada:

```text
src/coding_agent/
  __init__.py
  cli.py
  config.py
  llm/
    __init__.py
    base.py
    openai_client.py
  harness/
    __init__.py
    loop.py
tests/
  unit/
  integration/
```

Requisitos de diseño:

- Los tests unitarios no pueden llamar a OpenAI.
- El adaptador real debe poder desactivarse o reemplazarse con un fake.
- La API pública debe tener type hints.
- Los errores deben modelarse explícitamente.
- No usar `input()` dentro del núcleo; la aprobación debe ser una interfaz.
- No usar paths de Colab.
- No copiar la celda insegura que redefine `read_file`.

Creá tests para:

- carga de configuración;
- modelo requerido ausente;
- harness con fake LLM sin tools;
- harness con una tool fake;
- límite de iteraciones;
- rechazo de aprobación.

En esta fase podés crear `pyproject.toml`, pero NO instales dependencias.
Al terminar:

1. Mostrá el contenido relevante de `pyproject.toml`.
2. Justificá cada dependencia.
3. Mostrá los tests creados, aunque todavía no puedan ejecutarse por falta de
   instalación.
4. Actualizá la documentación.
5. Pedí aprobación explícita para instalar.
6. Detenete.
