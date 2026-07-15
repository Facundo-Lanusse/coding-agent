# RAG técnico para Python/FastAPI

## Pipeline implementado

El pipeline no usa framework de orquestación:

```text
loader -> normalize -> TechnicalChunker -> EmbeddingProvider
       -> SQLiteVectorStore -> RAGRetriever -> ResearchService
       -> web fallback opcional
```

`EmbeddingProvider`, `VectorStore`, `RAGProvider`, `URLFetcher` y
`WebSearchProvider` son puertos. Tests y demos usan implementaciones
deterministas sin red.

## Corpus reproducible

[`../rag_sources/manifest.yaml`](../rag_sources/manifest.yaml) identifica tres
paráfrasis locales breves, no copias completas:

| Source id | Fuente atribuida | Canal/version | Snapshot |
|---|---|---|---|
| `fastapi-official-dependencies` | <https://fastapi.tiangolo.com/tutorial/dependencies/> | latest | 2026-07-14 |
| `pydantic-official-models` | <https://pydantic.dev/docs/validation/latest/concepts/models/> | latest | 2026-07-14 |
| `pytest-official-fixtures` | <https://docs.pytest.org/en/stable/how-to/fixtures.html> | stable | 2026-07-14 |

El manifest fija URL, title, ecosystem, versión, content type y fecha. La
ingesta reproducible lee los snapshots locales; no descarga esas URLs durante
la demo. Por lo tanto las fechas/versiones son metadata declarada del snapshot,
no una verificación online hecha en cada corrida.

## Loaders

`LocalSourceLoader` admite `.md`, `.markdown`, `.txt`, `.py`, `.toml`, `.yaml` y
`.yml`; resuelve containment, bloquea nombres sensibles, limita tamaño, exige
UTF-8 y usa el manifest cuando existe.

`OfficialURLLoader` exige HTTPS y hostname incluido en
`rag.allowed_url_domains`. Valida URL inicial y final tras redirects, limita
bytes y convierte HTML básico a texto. El fetcher usa `urllib` o un fake. La CLI
actual sólo expone ingesta de directorios locales; el loader URL es una API de
Python probada, no un comando CLI.

## Normalización y chunking

La normalización usa Unicode NFC, unifica newlines y elimina espacios finales
sin destruir indentación interna. `TechnicalChunker` analiza headings,
párrafos y fences Markdown:

- un bloque fenced se mantiene entero;
- los chunks respetan `chunk_size_tokens` salvo una unidad indivisible mayor;
- el overlap reutiliza bloques completos que caben en
  `chunk_overlap_tokens`;
- el conteo es una aproximación regex de palabras/puntuación, no el tokenizer
  exacto del modelo.

Cada chunk conserva `source_id`, `source_type`, `path_or_url`, `title`,
`section`, `ecosystem`, `version`, `chunk_index`, checksum SHA-256,
`ingested_at` y `content_type`.

## Embeddings

`OpenAIEmbeddingProvider` usa `client.embeddings.create` del SDK oficial con
modelo y dimensión de configuración. No hay key/model hardcodeados en el
adaptador.

`DeterministicFakeEmbeddings` genera vectores normalizados desde features
léxicas hasheadas. Sirve para tests y demo, no es una medición semántica de
calidad ni compatible con vectores OpenAI.

## Vector store local

`SQLiteVectorStore` tiene dos tablas: colecciones y chunks/vectores. Una
colección queda identificada por nombre+versión y valida modelo/dimensión. La
primary key de chunks incluye colección, versión, source id, checksum e índice,
lo que hace idempotente una reingesta sin cambios.

Los embeddings se guardan como JSON. Query calcula similitud coseno en el
proceso, descarta scores bajo `minimum_relevance`, ordena descendente y devuelve
`top_k`. Es apropiado para el corpus pequeño; no escala como un índice ANN.

## Suficiencia, RAG primero y web

`ResearchService` llama siempre al retriever antes de web. `RAGRetriever`
considera suficiente una consulta cuando:

1. hay al menos un hit sobre threshold; y
2. cada string de `required_details` está presente en el texto combinado.

Si no es suficiente y `web_fallback=true`, hace una única llamada al
`WebSearchProvider`, entrega el allowlist y descarta resultados que no sean
HTTPS en esos dominios. Si RAG fue suficiente, web no se invoca. Si ninguna
fuente alcanza, retorna `NO_EVIDENCE` y una explicación, sin generar afirmación
técnica.

Cada hit se convierte a `EvidenceSource.RAG`; cada resultado web válido a
`EvidenceSource.WEB`. `ResearchResponse` mantiene grupos separados para
repository, memory, RAG, web, tool output e inference. Una inferencia no se crea
ni se atribuye automáticamente a una fuente recuperada.

## CLI

Offline y reproducible:

```bash
coding-agent rag ingest ./rag_sources --config agent.config.yaml --fake-embeddings
coding-agent rag query "¿Cómo se declaran dependencies en FastAPI?" \
  --config agent.config.yaml --fake-embeddings
```

Real, con `OPENAI_API_KEY` en el entorno:

```bash
coding-agent rag ingest ./rag_sources --config agent.config.yaml
coding-agent rag query "¿Cómo se declaran dependencies en FastAPI?" \
  --config agent.config.yaml
```

No mezclar fake y OpenAI en la misma colección: deben cambiarse
`collection_version` o `persistence_path` y reingestar. Query sin hits termina
con exit code 3; errores de fuente/store/embedding terminan con exit code 2.

## Evidencia y limitaciones

El escenario A conserva fragmentos y locators en
[`evidence/runs/scenario-a-rag/sources.json`](evidence/runs/scenario-a-rag/sources.json).
Usa dimensión 64, threshold `0.05` y corpus de tres documentos, distintos de los
valores root de `agent.config.yaml`. Recuperó los tres documentos. Esto prueba
provenance y orden RAG-before-web (el fake web falla si se llama), pero no prueba
precision/recall ni que todos los hits sean necesarios para el endpoint.

No hay proveedor web productivo compuesto; sólo puerto, adaptador no disponible
y fakes. Tampoco se envían los chunks automáticamente a `coding-agent run`, que
sigue siendo el harness básico.

