# Checklist final de entrega

Actualizado en la auditoría de Fase 09 del 2026-07-14. `[x]` significa
evidencia local inspeccionada o comando ejecutado; `[ ]` identifica una acción
humana o un gate no satisfecho.

## Entregables de la consigna

- [x] Paquete Python, wheel, sdist y suite determinista.
- [x] README de instalación, configuración, RAG, agente, demos y gates.
- [x] Caso de uso, fixture y criterio verificable documentados.
- [x] Arquitectura, agente principal, cinco roles y estado compartido.
- [x] Fuentes, chunking, embeddings y SQLite vector store documentados.
- [x] Cuatro bundles de evidencia para A, B1/B2 y C con schema 1.0.
- [x] Reflexión basada en artifacts y resultados observados.
- [ ] Ejecución multiagente real registrada en Langfuse con trace id.
- [ ] Captura real de una traza completa en `docs/evidence/screenshots/`.

## Reproducibilidad

- [x] `demo reset`, `demo rag`, `demo memory`, `demo safety` y `demo all`.
- [x] Escenario A termina `completed`, B1/B2 `completed` y C `blocked` por
  diseño, sin loop infinito.
- [x] Artifacts contienen estado, fuentes, diff, comandos, memoria y eventos.
- [x] Fuentes repository/memory/RAG/web/inference permanecen tipadas.
- [x] Workspace e intérprete están sustituidos por `${WORKSPACE}` y
  `${PYTHON}` en los artifacts entregados.
- [x] `trace_id=null` declara honestamente la ausencia de Langfuse.
- [x] La ingesta y query RAG offline documentadas terminan con exit code 0.
- [ ] La demo incluida en el wheel puede ejecutarse fuera del checkout; hoy el
  seed vive en `examples/` y no está dentro del wheel.

## Quality gates finales

- [x] Suite completa: 119 passed, 1 skipped, exit 0.
- [x] Coverage: 87% global, por encima del mínimo planificado de 85%.
- [ ] Cobertura crítica de 90%: `orchestrator/main.py` queda en 83% y módulos
  de policy quedan entre 62% y 89%.
- [x] Ruff sobre `src tests examples`: exit 0.
- [x] mypy sobre `src tests`: exit 0, 94 archivos.
- [x] Build de wheel/sdist: exit 0.
- [x] Instalación limpia del wheel y ayudas CLI: exit 0.
- [x] Demos deterministas e inspección de los cuatro artifacts: exit 0.
- [x] Links, rutas y 44 filas R01-R44 validados por test.

## Seguridad e integridad

- [x] No se leyó `.env` ni se persistieron valores de credenciales.
- [x] Escaneo razonable sin credenciales reales, PEM ni secrets literales.
- [x] Los valores `Bearer` en tests son fixtures deliberadamente falsas para
  validar redacción.
- [x] No hay imports ni dependencias de frameworks de orquestación prohibidos.
- [x] No hay paths del autor en código, documentación o artifacts entregables.
- [x] Notebook legado conserva su checksum SHA-256 esperado.
- [x] No se fabricaron trace ids, capturas ni resultados de proveedor.

## Acciones humanas pendientes

- [ ] Aprobar o rechazar agregar la dependencia runtime `langfuse`.
- [ ] Proveer `OPENAI_API_KEY`, `LANGFUSE_PUBLIC_KEY` y
  `LANGFUSE_SECRET_KEY`; configurar `LANGFUSE_BASE_URL` sólo si corresponde.
- [ ] Aprobar el costo y completar/conectar una ejecución real OpenAI con los
  cinco subagentes; `demo real` hoy declara que no está implementada.
- [ ] Ejecutar la tarea real, revisar sanitización y registrar el trace id.
- [ ] Tomar las capturas mediante `docs/evidence/screenshots/README.md`.
- [ ] Decidir si se empaqueta el seed demo dentro del wheel o se documenta el
  checkout como requisito operativo definitivo.
- [ ] Decidir si el umbral crítico de cobertura se mantiene en 90% y, en ese
  caso, agregar tests dirigidos sin ampliar funcionalidades.
- [ ] Autorizar dependencias FastAPI del demo si se quieren ejecutar sus tests
  HTTP además de los checks de contrato ya entregados.

## Dictamen

La entrega queda `PARTIAL`: 36/44 requisitos están `PASS`, cinco `PARTIAL`,
tres requieren acción humana y ninguno queda `FAIL` en la matriz funcional.
Los dos gates internos no satisfechos son la cobertura crítica de 90% y la demo
standalone desde el wheel. R29/R35/R43 no pueden cerrarse sin Langfuse real y
capturas humanas.

## Preparación posterior para GitHub

- [x] `.gitignore` cubre entornos, caches, coverage, DBs, builds, logs y secretos.
- [x] `.gitattributes` normaliza texto y marca artifacts binarios.
- [x] `.dockerignore` impide enviar estado local o credenciales al build context.
- [x] `Makefile` centraliza bootstrap, gates, build, config, RAG y demos.
- [x] Dockerfile multi-stage separa builder, runtime no-root y development.
- [x] Compose pasa sólo variables explícitas y aplica root filesystem read-only,
  `/tmp` efímero, `no-new-privileges` y cero capabilities Linux.
- [x] `.python-version` fija Python 3.11 como referencia mínima.
- [ ] Build Docker no ejecutado: Docker no está disponible en el host auditado.
- [ ] Elegir licencia antes de publicar si se desea permitir reutilización.
