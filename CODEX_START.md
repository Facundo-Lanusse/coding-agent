# Guía exacta para ejecutar el proyecto con Codex

## 1. Abrir el proyecto

1. Descomprimir este starter pack.
2. Abrir la carpeta raíz `coding-agent-avanzado-starter` en Codex.
3. Verificar que Codex puede ver:
   - `AGENTS.md`
   - `docs/consigna_tp_final.pdf`
   - `legacy/coding_agent_tp_anterior.ipynb`
   - `prompts/`
4. Iniciar una sesión nueva para que Codex cargue `AGENTS.md`.

## 2. Ejecutar las fases

Copiar y pegar, en orden, el contenido de cada archivo:

1. `prompts/00_auditoria_y_plan.md`
2. `prompts/01_scaffold_y_migracion.md`
3. Revisar `pyproject.toml` y aprobar la instalación con el mensaje indicado
   más abajo.
4. `prompts/02_tools_y_politicas.md`
5. `prompts/03_estado_y_multiagente.md`
6. `prompts/04_memoria_contexto_y_loops.md`
7. `prompts/05_rag_y_fuentes.md`
8. `prompts/06_observabilidad.md`
9. `prompts/07_caso_de_uso_y_pruebas.md`
10. `prompts/08_documentacion_y_evidencias.md`
11. `prompts/09_auditoria_final.md`

No pegar el siguiente prompt hasta comprobar que la fase actual terminó y que
Codex mostró los tests ejecutados.

## 3. Mensaje para aprobar dependencias

Después de la fase 01, leer `pyproject.toml`. Si contiene solamente las
dependencias justificadas, enviar:

```text
Revisé pyproject.toml. Autorizo crear el entorno virtual del proyecto y ejecutar
la instalación editable con las dependencias de desarrollo declaradas allí.
No autorizo agregar ni instalar ninguna otra dependencia. Después de instalar,
ejecutá la suite de tests, Ruff y mypy, informá los resultados y detenete.
```

## 4. Variables de entorno

Cuando el código esté listo:

1. Copiar `.env.example` a `.env`.
2. Completar las claves localmente.
3. No pegar claves en Codex ni en el chat.
4. Confirmar que `.env` está ignorado por Git.

Las claves mínimas para la demo completa serán OpenAI, Tavily y Langfuse.

## 5. Controles después de cada fase

Comprobar que Codex informa:

- archivos modificados;
- comandos ejecutados;
- exit code;
- tests aprobados o fallidos;
- requisitos cubiertos;
- pendientes;
- confirmación de que se detuvo.

Si Codex empieza una fase no solicitada, interrumpirlo y enviar:

```text
Detenete. No avances a otra fase. Terminá únicamente la fase actual, ejecutá sus
validaciones y presentá el resumen requerido por AGENTS.md.
```

## 6. Ejecución final esperada

Al concluir, el README debe permitir realizar algo equivalente a:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

coding-agent rag ingest ./rag_sources
coding-agent run --task "Analizá el repositorio y generá un reporte"
coding-agent demo rag
coding-agent demo memory
coding-agent demo safety
```

Los nombres finales pueden variar si están documentados y son coherentes.

## 7. Evidencias que requieren acción humana

Codex debe generar las ejecuciones y archivos de evidencia, pero vos tenés que:

- abrir Langfuse;
- entrar a una traza completa;
- sacar capturas donde se vean agente, tools, RAG, errores, tokens y latencia;
- guardar las capturas en `docs/evidence/screenshots/`;
- verificar que no aparezcan secretos;
- incluirlas en la entrega.

No aceptar capturas inventadas ni placeholders como evidencia final.
