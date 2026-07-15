from types import SimpleNamespace

from coding_agent.rag import DeterministicFakeEmbeddings, OpenAIEmbeddingProvider


class FakeEmbeddingsResource:
    def __init__(self) -> None:
        self.payload: dict[str, object] = {}

    def create(self, **kwargs: object) -> object:
        self.payload = kwargs
        return SimpleNamespace(
            data=(
                SimpleNamespace(index=0, embedding=[1.0, 0.0, 0.0]),
                SimpleNamespace(index=1, embedding=[0.0, 1.0, 0.0]),
            )
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = FakeEmbeddingsResource()


def test_fake_embeddings_are_deterministic_without_network() -> None:
    provider = DeterministicFakeEmbeddings(dimension=32)

    first = provider.embed_query("FastAPI dependencies")
    second = provider.embed_query("FastAPI dependencies")

    assert first == second
    assert len(first) == 32


def test_openai_embedding_adapter_uses_injected_sdk_client() -> None:
    client = FakeOpenAIClient()
    provider = OpenAIEmbeddingProvider(
        model="configured-embedding-model",
        dimension=3,
        client=client,
    )

    vectors = provider.embed_documents(("first", "second"))

    assert vectors == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert client.embeddings.payload == {
        "model": "configured-embedding-model",
        "input": ["first", "second"],
        "dimensions": 3,
        "encoding_format": "float",
    }
