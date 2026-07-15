from pathlib import Path

import pytest

from coding_agent.rag import LocalSourceLoader, OfficialURLLoader, RAGSourceType, SourceLoadError

ROOT = Path(__file__).resolve().parents[2]


class FakeFetcher:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch(self, url: str, *, max_bytes: int) -> tuple[str, str, str]:
        self.urls.append(url)
        assert max_bytes > 0
        return (
            "<h1>Dependencies</h1><p>Use Depends with a callable.</p>",
            "text/html",
            url,
        )


class RedirectFetcher:
    def fetch(self, url: str, *, max_bytes: int) -> tuple[str, str, str]:
        del url, max_bytes
        return "untrusted", "text/plain", "https://example.com/redirected"


def test_local_loader_reads_markdown_text_and_allowed_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nFastAPI example.", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("pytest fixtures", encoding="utf-8")
    (tmp_path / "app.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")

    documents = LocalSourceLoader().load_directory(tmp_path)

    assert {item.source_type for item in documents} == {
        RAGSourceType.README,
        RAGSourceType.TEXT,
        RAGSourceType.CODE,
    }
    assert all(len(item.checksum) == 64 for item in documents)


def test_local_loader_blocks_symlink_that_escapes_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside", encoding="utf-8")
    link = root / "linked.md"
    link.symlink_to(outside)

    with pytest.raises(SourceLoadError, match="escapes"):
        LocalSourceLoader().load_file(link, root=root)


def test_official_url_loader_enforces_https_domain_allowlist() -> None:
    fetcher = FakeFetcher()
    loader = OfficialURLLoader(
        allowed_domains=("fastapi.tiangolo.com",),
        fetcher=fetcher,
    )

    document = loader.load(
        "https://fastapi.tiangolo.com/tutorial/dependencies/",
        source_id="fastapi-dependencies",
        title="Dependencies",
        ecosystem="FastAPI",
        version="latest",
    )

    assert document.source_type is RAGSourceType.OFFICIAL_URL
    assert "# Dependencies" in document.content
    assert fetcher.urls == ["https://fastapi.tiangolo.com/tutorial/dependencies/"]
    with pytest.raises(SourceLoadError, match="allowlisted"):
        loader.load(
            "https://example.com/untrusted",
            source_id="bad",
            title="Bad",
            ecosystem="Python",
            version="unknown",
        )


def test_versioned_rag_sources_manifest_loads_complete_metadata() -> None:
    documents = LocalSourceLoader().load_directory(ROOT / "rag_sources")

    assert len(documents) == 3
    assert {item.ecosystem for item in documents} == {"FastAPI", "Pydantic", "pytest"}
    assert all(item.source_type is RAGSourceType.OFFICIAL_URL for item in documents)
    assert all(item.path_or_url.startswith("https://") for item in documents)
    assert all("2026-07-14" in item.version for item in documents)


def test_official_url_loader_revalidates_redirect_destination() -> None:
    loader = OfficialURLLoader(
        allowed_domains=("fastapi.tiangolo.com",),
        fetcher=RedirectFetcher(),
    )

    with pytest.raises(SourceLoadError, match="redirected"):
        loader.load(
            "https://fastapi.tiangolo.com/tutorial/",
            source_id="redirect",
            title="Redirect",
            ecosystem="FastAPI",
            version="latest",
        )
