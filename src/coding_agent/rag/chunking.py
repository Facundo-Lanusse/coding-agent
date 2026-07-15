"""Normalization and heading/code-aware chunking with configurable overlap."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from coding_agent.rag.models import ChunkMetadata, DocumentChunk, SourceDocument

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
_MULTIPLE_BLANKS = re.compile(r"\n{3,}")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return _MULTIPLE_BLANKS.sub("\n\n", "\n".join(lines)).strip()


def approximate_token_count(value: str) -> int:
    return len(_TOKEN_PATTERN.findall(value))


@dataclass(frozen=True, slots=True)
class _Block:
    text: str
    section: str
    tokens: int


class TechnicalChunker:
    def __init__(self, *, max_tokens: int, overlap_tokens: int) -> None:
        if max_tokens < 1 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("Chunk size must be positive and overlap smaller than size.")
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens

    def chunk(self, document: SourceDocument) -> tuple[DocumentChunk, ...]:
        blocks = _parse_blocks(document.content, document.title)
        if not blocks:
            return ()
        groups: list[list[_Block]] = []
        current: list[_Block] = []
        current_tokens = 0
        for block in blocks:
            if current and current_tokens + block.tokens > self._max_tokens:
                groups.append(current)
                current = _overlap(current, self._overlap_tokens)
                current_tokens = sum(item.tokens for item in current)
            current.append(block)
            current_tokens += block.tokens
        if current:
            groups.append(current)

        chunks: list[DocumentChunk] = []
        for index, group in enumerate(groups):
            text = normalize_text("\n\n".join(block.text for block in group))
            section = next(
                (block.section for block in reversed(group) if block.section),
                document.title,
            )
            chunk_id = hashlib.sha256(
                f"{document.source_id}:{document.checksum}:{index}:{text}".encode()
            ).hexdigest()
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    text=text,
                    token_count=approximate_token_count(text),
                    metadata=ChunkMetadata(
                        source_id=document.source_id,
                        source_type=document.source_type,
                        path_or_url=document.path_or_url,
                        title=document.title,
                        section=section,
                        ecosystem=document.ecosystem,
                        version=document.version,
                        chunk_index=index,
                        checksum=document.checksum,
                        ingested_at=document.ingested_at,
                        content_type=document.content_type,
                    ),
                )
            )
        return tuple(chunks)


def _parse_blocks(content: str, default_section: str) -> list[_Block]:
    lines = normalize_text(content).splitlines()
    blocks: list[_Block] = []
    paragraph: list[str] = []
    section_stack: list[str] = [default_section]
    in_code = False
    code: list[str] = []

    def section() -> str:
        return " > ".join(section_stack)

    def flush_paragraph() -> None:
        if paragraph:
            text = "\n".join(paragraph).strip()
            blocks.append(_Block(text, section(), approximate_token_count(text)))
            paragraph.clear()

    for line in lines:
        if line.lstrip().startswith("```"):
            if not in_code:
                flush_paragraph()
                in_code = True
                code = [line]
            else:
                code.append(line)
                text = "\n".join(code)
                blocks.append(_Block(text, section(), approximate_token_count(text)))
                in_code = False
                code = []
            continue
        if in_code:
            code.append(line)
            continue
        heading = _HEADING_PATTERN.match(line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            section_stack = section_stack[:level]
            if len(section_stack) < level:
                section_stack.extend([title] * (level - len(section_stack)))
            else:
                section_stack[-1] = title
            blocks.append(_Block(line, section(), approximate_token_count(line)))
        elif not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line)
    flush_paragraph()
    if code:
        text = "\n".join(code)
        blocks.append(_Block(text, section(), approximate_token_count(text)))
    return blocks


def _overlap(blocks: list[_Block], limit: int) -> list[_Block]:
    selected: list[_Block] = []
    tokens = 0
    for block in reversed(blocks):
        if block.tokens > limit:
            break
        if tokens and tokens + block.tokens > limit:
            break
        selected.append(block)
        tokens += block.tokens
        if tokens >= limit:
            break
    selected.reverse()
    return selected
