from __future__ import annotations

from typing import Any

from .errors import ChmseekError
from .indexer import IndexHandle
from .storage import connect, get_chunk, get_chunks_for_page, get_neighbor_chunks, get_page


def read_content(
    handle: IndexHandle,
    *,
    page_id: str | None = None,
    chunk_id: str | None = None,
    neighbors: int = 0,
) -> dict[str, Any]:
    if not page_id and not chunk_id:
        raise ChmseekError(
            "READ_TARGET_REQUIRED",
            "Pass either --page-id or --chunk-id.",
            ["Use search results or toc output to choose an ID."],
        )
    conn = connect(handle.db_path)
    try:
        if chunk_id:
            target = get_chunk(conn, chunk_id)
            if target is None:
                raise ChmseekError(
                    "INVALID_CHUNK_ID",
                    f"No chunk exists with ID {chunk_id}.",
                    ["Use search to find valid chunk IDs."],
                )
            chunks = get_neighbor_chunks(conn, chunk_id, max(0, neighbors))
            return {
                "ok": True,
                "target": {"type": "chunk", "chunk_id": chunk_id, "page_id": target["page_id"]},
                "chunks": chunks,
            }
        assert page_id is not None
        page = get_page(conn, page_id)
        if page is None:
            raise ChmseekError(
                "INVALID_PAGE_ID",
                f"No page exists with ID {page_id}.",
                ["Use toc output to find valid page IDs."],
            )
        return {
            "ok": True,
            "target": {"type": "page", "page_id": page_id},
            "page": page,
            "chunks": get_chunks_for_page(conn, page_id),
        }
    finally:
        conn.close()
