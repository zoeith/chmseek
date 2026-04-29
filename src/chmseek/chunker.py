from __future__ import annotations

from dataclasses import dataclass

from .constants import CHUNKER_VERSION
from .parser import ParsedPage
from .utils import word_tokens


@dataclass
class Chunk:
    chunk_id: str
    page_id: str
    ordinal: int
    title: str
    section_path: list[str]
    anchor: str | None
    text: str
    token_count: int


def chunk_pages(pages: list[ParsedPage]) -> list[Chunk]:
    chunks: list[Chunk] = []
    next_id = 1
    for page in pages:
        page_chunks = chunk_page(page, next_id)
        chunks.extend(page_chunks)
        next_id += len(page_chunks)
    return chunks


def chunk_page(page: ParsedPage, first_chunk_number: int) -> list[Chunk]:
    tokens = word_tokens(page.text)
    api_like = "/api/" in f"/{page.source_path.lower()}" or any(
        symbol in page.text for symbol in ("HRESULT", "CreateSession", "SetParameter")
    )
    target = 900 if api_like else 1400
    max_tokens = 1400 if api_like else 2200
    overlap = 120 if api_like else 200
    section_path = [page.title]
    if page.headings and page.headings[0] != page.title:
        section_path.append(page.headings[0])

    if len(tokens) <= max_tokens:
        return [
            Chunk(
                chunk_id=f"ch_{first_chunk_number:06d}",
                page_id=page.page_id,
                ordinal=0,
                title=page.title,
                section_path=section_path,
                anchor=None,
                text=page.text,
                token_count=len(tokens),
            )
        ]

    text_tokens = page.text.split()
    chunks: list[Chunk] = []
    start = 0
    ordinal = 0
    while start < len(text_tokens):
        end = min(start + target, len(text_tokens))
        if end < len(text_tokens):
            end = min(start + max_tokens, end)
        chunk_text = " ".join(text_tokens[start:end]).strip()
        chunks.append(
            Chunk(
                chunk_id=f"ch_{first_chunk_number + ordinal:06d}",
                page_id=page.page_id,
                ordinal=ordinal,
                title=page.title,
                section_path=section_path,
                anchor=None,
                text=chunk_text,
                token_count=len(word_tokens(chunk_text)),
            )
        )
        if end == len(text_tokens):
            break
        start = max(0, end - overlap)
        ordinal += 1
    return chunks


__all__ = ["CHUNKER_VERSION", "Chunk", "chunk_page", "chunk_pages"]
