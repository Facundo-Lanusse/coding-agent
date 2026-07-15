"""Safe local and allowlisted official-URL source loaders."""

from __future__ import annotations

import hashlib
import re
import urllib.request
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from coding_agent.rag.chunking import normalize_text
from coding_agent.rag.models import RAGSourceType, SourceDocument

_DEFAULT_EXTENSIONS = frozenset({".md", ".markdown", ".txt", ".py", ".toml", ".yaml", ".yml"})
_SECRET_NAMES = frozenset({".env", "secrets"})


class SourceLoadError(Exception):
    code = "rag_source_load_error"


class SourceManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_type: RAGSourceType
    path_or_url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    ecosystem: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    retrieved_at: str = Field(min_length=1)


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sources: tuple[SourceManifestEntry, ...]


class LocalSourceLoader:
    def __init__(
        self,
        *,
        allowed_extensions: frozenset[str] = _DEFAULT_EXTENSIONS,
        max_bytes: int = 1_000_000,
        ecosystem: str = "Python/FastAPI",
        version: str = "workspace",
    ) -> None:
        self._extensions = frozenset(item.casefold() for item in allowed_extensions)
        self._max_bytes = max_bytes
        self._ecosystem = ecosystem
        self._version = version

    def load_directory(self, root: str | Path) -> tuple[SourceDocument, ...]:
        canonical_root = Path(root).resolve()
        if not canonical_root.is_dir():
            raise SourceLoadError(f"RAG source directory not found: {canonical_root}.")
        manifest_path = canonical_root / "manifest.yaml"
        if manifest_path.is_file():
            return self._load_manifest(canonical_root, manifest_path)
        documents: list[SourceDocument] = []
        for path in sorted(canonical_root.rglob("*")):
            if path.is_file() and path.suffix.casefold() in self._extensions:
                documents.append(self.load_file(path, root=canonical_root))
        return tuple(documents)

    def load_file(
        self,
        path: str | Path,
        *,
        root: str | Path,
        manifest: SourceManifestEntry | None = None,
    ) -> SourceDocument:
        canonical_root = Path(root).resolve()
        candidate = Path(path).resolve()
        try:
            relative = candidate.relative_to(canonical_root)
        except ValueError as exc:
            raise SourceLoadError("Local RAG source escapes its configured root.") from exc
        if any(part.casefold() in _SECRET_NAMES for part in relative.parts):
            raise SourceLoadError("Sensitive paths cannot be loaded as RAG sources.")
        if candidate.suffix.casefold() not in self._extensions:
            raise SourceLoadError(f"Unsupported RAG source extension: {candidate.suffix}.")
        try:
            size = candidate.stat().st_size
            if size > self._max_bytes:
                raise SourceLoadError(f"RAG source exceeds {self._max_bytes} bytes.")
            content = normalize_text(candidate.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exc:
            raise SourceLoadError("RAG source is not valid UTF-8 text.") from exc
        if not content:
            raise SourceLoadError("RAG source is empty after normalization.")
        checksum = hashlib.sha256(content.encode()).hexdigest()
        if manifest is not None:
            return SourceDocument(
                source_id=manifest.source_id,
                source_type=manifest.source_type,
                path_or_url=manifest.path_or_url,
                title=manifest.title,
                ecosystem=manifest.ecosystem,
                version=manifest.version,
                content=content,
                checksum=checksum,
                content_type=manifest.content_type,
            )
        source_type = _local_source_type(candidate)
        return SourceDocument(
            source_id=hashlib.sha256(relative.as_posix().encode()).hexdigest()[:24],
            source_type=source_type,
            path_or_url=relative.as_posix(),
            title=_title(content, candidate.stem),
            ecosystem=self._ecosystem,
            version=self._version,
            content=content,
            checksum=checksum,
            content_type=_content_type(candidate),
        )

    def _load_manifest(self, root: Path, manifest_path: Path) -> tuple[SourceDocument, ...]:
        try:
            raw: object = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = SourceManifest.model_validate(raw)
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise SourceLoadError("Invalid RAG source manifest.") from exc
        return tuple(
            self.load_file(root / entry.path, root=root, manifest=entry)
            for entry in manifest.sources
        )


class URLFetcher(Protocol):
    def fetch(self, url: str, *, max_bytes: int) -> tuple[str, str, str]:
        """Return response content, content type, and final URL."""


class UrllibURLFetcher:
    def fetch(self, url: str, *, max_bytes: int) -> tuple[str, str, str]:
        request = urllib.request.Request(url, headers={"User-Agent": "coding-agent-rag/1"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read(max_bytes + 1)
                content_type = response.headers.get_content_type()
                final_url = response.geturl()
        except OSError as exc:
            raise SourceLoadError("Official URL could not be fetched.") from exc
        if len(raw) > max_bytes:
            raise SourceLoadError("Official URL response exceeds configured size.")
        return raw.decode("utf-8"), content_type, final_url


class OfficialURLLoader:
    def __init__(
        self,
        *,
        allowed_domains: Iterable[str],
        fetcher: URLFetcher | None = None,
        max_bytes: int = 1_000_000,
    ) -> None:
        self._domains = tuple(domain.casefold().strip(".") for domain in allowed_domains)
        self._fetcher = fetcher or UrllibURLFetcher()
        self._max_bytes = max_bytes

    def load(
        self,
        url: str,
        *,
        source_id: str,
        title: str,
        ecosystem: str,
        version: str,
    ) -> SourceDocument:
        if not _allowed_url(url, self._domains):
            raise SourceLoadError("URL is not HTTPS on an allowlisted official domain.")
        raw, content_type, final_url = self._fetcher.fetch(url, max_bytes=self._max_bytes)
        if not _allowed_url(final_url, self._domains):
            raise SourceLoadError("Official URL redirected outside the domain allowlist.")
        content = normalize_text(_html_to_text(raw) if "html" in content_type else raw)
        if not content:
            raise SourceLoadError("Official URL is empty after normalization.")
        return SourceDocument(
            source_id=source_id,
            source_type=RAGSourceType.OFFICIAL_URL,
            path_or_url=final_url,
            title=title,
            ecosystem=ecosystem,
            version=version,
            content=content,
            checksum=hashlib.sha256(content.encode()).hexdigest(),
            content_type=content_type,
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if re.fullmatch(r"h[1-6]", tag):
            self.parts.append(f"\n{'#' * int(tag[1])} ")
        elif tag in {"p", "pre", "code", "li", "br"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return "".join(parser.parts)


def _allowed_url(url: str, domains: tuple[str, ...]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and any(
        host == domain or host.endswith(f".{domain}") for domain in domains
    )


def _local_source_type(path: Path) -> RAGSourceType:
    if path.name.casefold().startswith("readme"):
        return RAGSourceType.README
    if path.suffix.casefold() in {".md", ".markdown"}:
        return RAGSourceType.MARKDOWN
    if path.suffix.casefold() == ".txt":
        return RAGSourceType.TEXT
    return RAGSourceType.CODE


def _content_type(path: Path) -> str:
    return {
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
        ".py": "text/x-python",
        ".toml": "application/toml",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
    }[path.suffix.casefold()]


def _title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback
