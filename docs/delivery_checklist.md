# Checklist final de entrega

Actualizado tras la integración real autorizada del 2026-07-16. `[x]` significa
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
- [x] Ejecución multiagente real completa registrada con trace id
  `8248244a2224f1dc099fff1240e5c040`.
- [x] Seis diagnósticos y una ejecución completa preservados; la última alcanzó
  los cinco roles, tests exitosos y Reviewer.
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

- [x] Suite completa offline: 142 passed, 1 skipped, exit 0.
- [x] Coverage: 85% global, alcanza el mínimo planificado de 85%.
- [ ] Cobertura crítica de 90%: `orchestrator/main.py` queda en 85% y módulos
  de policy quedan entre 62% y 89%.
- [x] Ruff sobre `src tests examples`: exit 0.
- [x] mypy sobre `src tests`: exit 0, 101 archivos.
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

- [x] Langfuse y Tavily agregados/instalados con autorización explícita.
- [x] Composición real OpenAI con los cinco subagentes implementada y protegida
  por límites/`--confirm-cost`.
- [x] Variables reales cargadas por el usuario sin copiarlas a la entrega.
- [x] Reejecución real completada con entorno demo en `PATH`, presupuesto 20 y
  2400 tokens; Reviewer aceptó y el proceso terminó con exit 0.
- [x] El usuario mantuvo disponibles en la shell `OPENAI_API_KEY`, `TAVILY_API_KEY`,
  `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY`; no copiar sus valores a docs.
- [ ] Tomar las capturas mediante `docs/evidence/screenshots/README.md`.
- [x] Decisión de distribución: el seed demo permanece bajo `examples/` y las
  demos se ejecutan desde el checkout; no se infla el wheel con una fixture.
- [ ] Decidir si el umbral crítico de cobertura se mantiene en 90% y, en ese
  caso, agregar tests dirigidos sin ampliar funcionalidades.
- [ ] Autorizar dependencias FastAPI del demo si se quieren ejecutar sus tests
  HTTP además de los checks de contrato ya entregados.

## Dictamen

La entrega queda `PARTIAL`: 39/44 requisitos están `PASS`, dos `PARTIAL`, tres
requieren acción humana y ninguno queda `FAIL` en la matriz funcional.
Los dos gates internos no satisfechos son la cobertura crítica de 90% y la demo
standalone desde el wheel. R29/R35/R43 no pueden cerrarse sin ejecutar Langfuse
real y tomar capturas humanas.

## Preparación posterior para GitHub

- [x] `.gitignore` cubre entornos, caches, coverage, DBs, builds, logs y secretos.
- [x] `.gitattributes` normaliza texto y marca artifacts binarios.
- [x] `.dockerignore` impide enviar estado local o credenciales al build context.
- [x] `Makefile` centraliza bootstrap, gates, build, config, RAG y demos.
- [x] Dockerfile multi-stage separa builder, runtime no-root y development.
- [x] Compose pasa sólo variables explícitas y aplica root filesystem read-only,
  `/tmp` efímero, `no-new-privileges` y cero capabilities Linux.
- [x] `.python-version` fija Python 3.11 como referencia mínima.
- [ ] Revalidar el build Docker después de agregar Langfuse/Tavily si se usará
  como método de entrega; para la demo real se recomienda el `.venv` local.
- [ ] Elegir licencia antes de publicar si se desea permitir reutilización.
