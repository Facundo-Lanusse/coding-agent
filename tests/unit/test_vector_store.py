import hashlib
from pathlib import Path

from coding_agent.rag import (
    CollectionSpec,
    DeterministicFakeEmbeddings,
    EmbeddedChunk,
    RAGSourceType,
    SourceDocument,
    SQLiteVectorStore,
    TechnicalChunker,
)


def embedded() -> tuple[CollectionSpec, EmbeddedChunk, tuple[float, ...]]:
    content = "# FastAPI dependencies\n\nUse Depends to declare a callable dependency."
    document = SourceDocument(
        source_id="fastapi-dependencies",
        source_type=RAGSourceType.OFFICIAL_URL,
        path_or_url="https://fastapi.tiangolo.com/tutorial/dependencies/",
        title="FastAPI dependencies",
        ecosystem="FastAPI",
        version="latest",
        content=content,
        checksum=hashlib.sha256(content.encode()).hexdigest(),
        content_type="text/markdown",
    )
    chunk = TechnicalChunker(max_tokens=100, overlap_tokens=10).chunk(document)[0]
    provider = DeterministicFakeEmbeddings(dimension=32)
    vector = provider.embed_query(chunk.text)
    spec = CollectionSpec(
        name="fastapi",
        version="v1",
        embedding_model=provider.model,
        dimension=provider.dimension,
    )
    return spec, EmbeddedChunk(chunk=chunk, embedding=vector), vector


def test_vector_store_deduplicates_by_source_checksum_and_chunk(tmp_path: Path) -> None:
    spec, item, _ = embedded()
    store = SQLiteVectorStore(tmp_path / "vectors.sqlite3")

    first = store.upsert(spec, (item,))
    second = store.upsert(spec, (item,))

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped_duplicates == 1
    assert store.count(spec) == 1
    store.close()


def test_vector_store_persists_and_retrieves_relevant_chunk(tmp_path: Path) -> None:
    database = tmp_path / "vectors.sqlite3"
    spec, item, vector = embedded()
    first = SQLiteVectorStore(database)
    first.upsert(spec, (item,))
    first.close()

    reopened = SQLiteVectorStore(database)
    hits = reopened.query(spec, vector, top_k=3, minimum_score=0.8)

    assert len(hits) == 1
    assert hits[0].score == 1.0
    assert hits[0].chunk.metadata.source_id == "fastapi-dependencies"
    assert hits[0].chunk.metadata.path_or_url.startswith("https://fastapi.tiangolo.com")
    reopened.close()
