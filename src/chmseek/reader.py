from __future__ import annotations

from typing import Any

from .errors import ChmseekError
from .indexer import IndexHandle
from .storage import (
    attach_images_to_payloads,
    connect,
    get_chunk,
    get_chunks_for_page,
    get_image_refs_for_page_ids,
    get_neighbor_chunks,
    get_page,
)
from .utils import source_uri


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
            attach_images_to_payloads(conn, chunks)
            _add_asset_uris(chunks, handle.chm_path)
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
            "page": _page_with_images(conn, page, handle.chm_path),
            "chunks": _chunks_with_images(conn, page_id, handle.chm_path),
        }
    finally:
        conn.close()


def _chunks_with_images(conn, page_id: str, chm_path) -> list[dict[str, Any]]:
    chunks = get_chunks_for_page(conn, page_id)
    attach_images_to_payloads(conn, chunks)
    _add_asset_uris(chunks, chm_path)
    return chunks


def _page_with_images(conn, page: dict[str, Any], chm_path) -> dict[str, Any]:
    images = get_image_refs_for_page_ids(conn, [page["page_id"]]).get(page["page_id"], [])
    for image in images:
        image["asset_uri"] = source_uri(chm_path, image["source_path"])
    page = dict(page)
    page["images"] = images
    return page


def _add_asset_uris(chunks: list[dict[str, Any]], chm_path) -> None:
    for chunk in chunks:
        for image in chunk.get("images", []):
            image["asset_uri"] = source_uri(chm_path, image["source_path"])
