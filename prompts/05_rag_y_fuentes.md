Implementá únicamente la Fase 05: RAG técnico, atribución de fuentes y web como
fallback.

El agente está especializado en Python/FastAPI. El RAG debe poder ingerir
documentación técnica, READMEs, ejemplos y proyectos de referencia.

Implementá:

- loader local de Markdown, texto y archivos de código permitidos;
- loader de URLs oficiales, sujeto a configuración;
- normalización;
- chunking consciente de headings y bloques de código;
- conteo aproximado por tokens;
- overlap configurable;
- embeddings detrás de una interfaz;
- adaptador OpenAI embeddings;
- fake embeddings determinista para tests;
- vector store local persistente;
- colección y versionado;
- deduplicación por checksum;
- retrieval top-k;
- threshold mínimo;
- metadatos completos;
- CLI para ingest y query.

Metadatos mínimos:

- source_id;
- source_type;
- path_or_url;
- title;
- section;
- ecosystem;
- version;
- chunk_index;
- checksum;
- ingested_at;
- content_type.

Reglas de comportamiento:

1. Researcher consulta RAG antes de web.
2. Si hay evidencia suficiente, no usa web.
3. Si no alcanza el threshold o faltan detalles, puede usar web como fallback.
4. Web debe priorizar documentación oficial y fuentes técnicas confiables.
5. Cada afirmación técnica usada debe conservar provenance.
6. La respuesta debe mostrar documentos o fragmentos recuperados.
7. Debe distinguir repository, memory, rag, web e inference.
8. No atribuir una inferencia a una fuente.
9. No enviar chunks irrelevantes al modelo.

Crear `rag_sources/` con un conjunto pequeño y reproducible de documentación
para FastAPI/Pydantic/pytest. Usar fuentes oficiales o READMEs claramente
identificados. Documentar URL, fecha y versión. No guardar secretos.

Tests obligatorios:

- chunking conserva headings y bloques;
- overlap;
- deduplicación;
- persistencia del vector store;
- retrieval relevante con fake embeddings;
- threshold insuficiente activa fallback;
- evidencia suficiente evita web;
- provenance se conserva hasta la respuesta;
- fuentes de distinto tipo no se mezclan;
- query sin evidencia produce explicación, no invención.

Agregar un comando reproducible similar a:

```bash
coding-agent rag ingest ./rag_sources
coding-agent rag query "¿Cómo se declaran dependencies en FastAPI?"
```

No dependas de una llamada real en unit tests. Ejecutá tests, Ruff y mypy.
Actualizá documentación y detenete.
