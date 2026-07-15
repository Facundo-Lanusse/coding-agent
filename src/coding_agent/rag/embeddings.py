"""Embedding provider interface, OpenAI adapter, and deterministic fake."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol, cast

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_./-]+")


class EmbeddingError(Exception):
    code = "embedding_error"


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


class EmbeddingsResource(Protocol):
    def create(self, **kwargs: object) -> object: ...


class OpenAIEmbeddingClient(Protocol):
    @property
    def embeddings(self) -> EmbeddingsResource: ...


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        api_key: str | None = None,
        client: OpenAIEmbeddingClient | None = None,
    ) -> None:
        if not model.strip() or dimension < 1:
            raise EmbeddingError("Embedding model and positive dimension are required.")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise EmbeddingError("The OpenAI SDK is required for real embeddings.") from exc
            sdk_client = OpenAI(api_key=api_key) if api_key is not None else OpenAI()
            client = cast(OpenAIEmbeddingClient, sdk_client)
        self._client = client
        self._model = model
        self._dimension = dimension

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("Embedding inputs must be non-empty text.")
        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=list(texts),
                dimensions=self._dimension,
                encoding_format="float",
            )
        except Exception as exc:
            raise EmbeddingError(
                f"OpenAI embeddings request failed ({type(exc).__name__})."
            ) from exc
        data = getattr(response, "data", None)
        if not isinstance(data, Sequence) or isinstance(data, str | bytes):
            raise EmbeddingError("OpenAI embeddings response has invalid data.")
        ordered = sorted(data, key=lambda item: int(getattr(item, "index", -1)))
        vectors = tuple(_embedding(item, self._dimension) for item in ordered)
        if len(vectors) != len(texts):
            raise EmbeddingError("OpenAI embeddings response count mismatch.")
        return vectors

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self.embed_documents((text,))[0]


class DeterministicFakeEmbeddings:
    def __init__(self, *, dimension: int = 64, model: str = "deterministic-fake-v1") -> None:
        if dimension < 2:
            raise ValueError("Fake embedding dimension must be at least 2.")
        self._dimension = dimension
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._embed(text) for text in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(text)

    def _embed(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise EmbeddingError("Embedding input must be non-empty text.")
        vector = [0.0] * self._dimension
        for token in _TOKEN_PATTERN.findall(text.casefold()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return tuple(value / norm for value in vector)


def _embedding(item: object, dimension: int) -> tuple[float, ...]:
    raw = getattr(item, "embedding", None)
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise EmbeddingError("OpenAI embedding item has no numeric vector.")
    vector = tuple(float(value) for value in raw)
    if len(vector) != dimension:
        raise EmbeddingError("OpenAI embedding dimension mismatch.")
    return vector
