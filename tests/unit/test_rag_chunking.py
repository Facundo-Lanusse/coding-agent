import hashlib
from itertools import pairwise

from coding_agent.rag import RAGSourceType, SourceDocument, TechnicalChunker


def document(content: str) -> SourceDocument:
    return SourceDocument(
        source_id="doc-1",
        source_type=RAGSourceType.MARKDOWN,
        path_or_url="docs/example.md",
        title="Example",
        ecosystem="FastAPI",
        version="1",
        content=content,
        checksum=hashlib.sha256(content.encode()).hexdigest(),
        content_type="text/markdown",
    )


def test_chunking_preserves_headings_code_blocks_and_metadata() -> None:
    content = """# Dependencies

FastAPI resolves callables.

## Example

```python
def dependency() -> str:
    return "value"
```

The result is injected into the route.
"""
    chunks = TechnicalChunker(max_tokens=18, overlap_tokens=4).chunk(document(content))

    assert any("# Dependencies" in chunk.text for chunk in chunks)
    code_chunks = [chunk for chunk in chunks if "```python" in chunk.text]
    assert len(code_chunks) == 1
    assert 'return "value"\n```' in code_chunks[0].text
    assert all(chunk.metadata.section for chunk in chunks)
    assert [chunk.metadata.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert set(chunks[0].metadata.model_dump()) == {
        "source_id",
        "source_type",
        "path_or_url",
        "title",
        "section",
        "ecosystem",
        "version",
        "chunk_index",
        "checksum",
        "ingested_at",
        "content_type",
    }


def test_chunking_adds_configurable_overlap_between_chunks() -> None:
    content = """# Topic

alpha beta gamma.

shared overlap phrase.

delta epsilon zeta.

final paragraph here.
"""
    chunks = TechnicalChunker(max_tokens=10, overlap_tokens=4).chunk(document(content))

    assert len(chunks) >= 2
    assert any(
        "shared overlap phrase" in left.text and "shared overlap phrase" in right.text
        for left, right in pairwise(chunks)
    )
