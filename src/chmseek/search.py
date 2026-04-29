from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .embeddings import EmbeddingConfig, make_embedding_backend
from .errors import ChmseekError
from .indexer import IndexHandle
from .storage import SearchRow, connect, counts, get_help_file, keyword_search, load_embedding_rows
from .utils import preview_text, source_uri


def run_search(
    handle: IndexHandle,
    query: str,
    *,
    mode: str = "hybrid",
    top_k: int = 8,
    allow_model_download: bool = False,
    allow_remote_model_code: bool = False,
    offline: bool = False,
    model_revision: str | None = None,
) -> dict[str, Any]:
    if mode not in {"hybrid", "semantic", "keyword"}:
        raise ChmseekError("INVALID_SEARCH_MODE", f"Unsupported search mode: {mode}")
    conn = connect(handle.db_path)
    try:
        help_file = get_help_file(conn)
        if help_file is None:
            raise ChmseekError("INDEX_CORRUPT", "Index is missing help file metadata.")
        count_info = counts(conn)
        keyword_rows: list[SearchRow] = []
        semantic_rows: list[SearchRow] = []
        if mode in {"hybrid", "keyword"}:
            keyword_rows = keyword_search(conn, query, max(top_k * 5, 20))
        if mode in {"hybrid", "semantic"}:
            config = EmbeddingConfig(
                model_name=help_file["embedding_model"],
                dimension=int(help_file["embedding_dimension"]),
                allow_model_download=allow_model_download,
                allow_remote_model_code=allow_remote_model_code,
                offline=offline,
                model_revision=(
                    model_revision or handle.manifest.get("embedding", {}).get("revision")
                ),
            )
            semantic_rows = semantic_search(conn, query, config, max(top_k * 5, 20))
        results = rank_results(mode, keyword_rows, semantic_rows)[:top_k]
        return {
            "ok": True,
            "query": query,
            "mode": mode,
            "help_file": {
                "path": str(handle.chm_path),
                "title": help_file.get("title"),
                "fingerprint": f"sha256:{help_file['sha256']}",
            },
            "index": {
                "status": "ready",
                "was_built": handle.was_built,
                "chunks": count_info["chunks"],
                "pages": count_info["pages"],
                "model": help_file["embedding_model"],
                "embedding_dimension": help_file["embedding_dimension"],
                "path": str(handle.index_dir),
            },
            "results": [
                _result_payload(rank, row, handle.chm_path, query)
                for rank, row in enumerate(results, start=1)
            ],
        }
    finally:
        conn.close()


def semantic_search(
    conn,
    query: str,
    config: EmbeddingConfig,
    limit: int,
) -> list[SearchRow]:
    rows, matrix = load_embedding_rows(conn, config.dimension)
    if matrix.shape[0] == 0:
        return []
    backend = make_embedding_backend(config)
    query_vector = backend.embed_query(query).astype(np.float32)
    scores = matrix @ query_vector
    ranked_indices = np.argsort(-scores)[:limit]
    results: list[SearchRow] = []
    for index in ranked_indices:
        row = rows[int(index)]
        row.score = float(scores[int(index)])
        results.append(row)
    return results


def rank_results(
    mode: str,
    keyword_rows: list[SearchRow],
    semantic_rows: list[SearchRow],
) -> list[SearchRow]:
    if mode == "keyword":
        for row in keyword_rows:
            row.semantic_score = None  # type: ignore[attr-defined]
            row.keyword_score = row.score  # type: ignore[attr-defined]
        return keyword_rows
    if mode == "semantic":
        for row in semantic_rows:
            row.semantic_score = row.score  # type: ignore[attr-defined]
            row.keyword_score = None  # type: ignore[attr-defined]
        return semantic_rows

    by_id: dict[str, SearchRow] = {}
    scores: dict[str, float] = {}
    semantic_scores: dict[str, float] = {}
    keyword_scores: dict[str, float] = {}
    for rank, row in enumerate(keyword_rows, start=1):
        by_id[row.chunk_id] = row
        scores[row.chunk_id] = scores.get(row.chunk_id, 0.0) + 1.0 / (60.0 + rank)
        keyword_scores[row.chunk_id] = row.score
    for rank, row in enumerate(semantic_rows, start=1):
        by_id[row.chunk_id] = row
        scores[row.chunk_id] = scores.get(row.chunk_id, 0.0) + 1.0 / (60.0 + rank)
        semantic_scores[row.chunk_id] = row.score
    ranked = sorted(by_id.values(), key=lambda row: (-scores[row.chunk_id], row.chunk_id))
    for row in ranked:
        row.score = scores[row.chunk_id]
        row.semantic_score = semantic_scores.get(row.chunk_id)  # type: ignore[attr-defined]
        row.keyword_score = keyword_scores.get(row.chunk_id)  # type: ignore[attr-defined]
    return ranked


def _result_payload(rank: int, row: SearchRow, chm_path: Path, query: str) -> dict[str, Any]:
    semantic_score = getattr(row, "semantic_score", row.score)
    keyword_score = getattr(row, "keyword_score", row.score)
    return {
        "rank": rank,
        "score": round(float(row.score), 6),
        "semantic_score": None if semantic_score is None else round(float(semantic_score), 6),
        "keyword_score": None if keyword_score is None else round(float(keyword_score), 6),
        "chunk_id": row.chunk_id,
        "page_id": row.page_id,
        "title": row.title,
        "section_path": row.section_path,
        "source_path": row.source_path,
        "source_uri": source_uri(chm_path, row.source_path, row.anchor),
        "snippet": make_snippet(row.text, query),
        "text_preview": preview_text(row.text),
        "neighbor_command": (
            f"chmseek read {chm_path} --chunk-id {row.chunk_id} --neighbors 2 --json"
        ),
    }


def make_snippet(text: str, query: str, limit: int = 220) -> str:
    lower = text.lower()
    words = [word.lower() for word in query.split() if len(word) > 2]
    positions = [lower.find(word) for word in words if lower.find(word) >= 0]
    if not positions:
        return preview_text(text, limit)
    start = max(0, min(positions) - 70)
    return preview_text(text[start : start + limit], limit)
