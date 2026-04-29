from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .chunker import Chunk
from .errors import ChmseekError
from .parser import ParsedPage
from .toc import TocEntry


@dataclass
class SearchRow:
    chunk_id: str
    page_id: str
    title: str
    section_path: list[str]
    source_path: str
    anchor: str | None
    text: str
    token_count: int
    score: float


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def check_fts5_available() -> bool:
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE ftstest USING fts5(text)")
        conn.close()
        return True
    except sqlite3.DatabaseError:
        return False


def require_fts5() -> None:
    if not check_fts5_available():
        raise ChmseekError(
            "SQLITE_FTS5_UNAVAILABLE",
            "This Python SQLite build does not support FTS5.",
            ["Install a Python build with SQLite FTS5 enabled."],
        )


def initialize_schema(conn: sqlite3.Connection) -> None:
    require_fts5()
    conn.executescript(
        """
        DROP TABLE IF EXISTS chunks_fts;
        DROP TABLE IF EXISTS toc_entries;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS pages;
        DROP TABLE IF EXISTS help_file;

        CREATE TABLE help_file (
          id TEXT PRIMARY KEY,
          original_path TEXT NOT NULL,
          title TEXT,
          sha256 TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          mtime REAL NOT NULL,
          indexed_at TEXT NOT NULL,
          schema_version INTEGER NOT NULL,
          embedding_model TEXT NOT NULL,
          embedding_dimension INTEGER NOT NULL,
          embedding_document_prefix TEXT NOT NULL,
          embedding_query_prefix TEXT NOT NULL,
          embedding_normalized INTEGER NOT NULL,
          chunker_version TEXT NOT NULL,
          extraction_method TEXT
        );

        CREATE TABLE pages (
          page_id TEXT PRIMARY KEY,
          source_path TEXT NOT NULL,
          title TEXT,
          toc_path TEXT,
          raw_html_path TEXT,
          text TEXT NOT NULL
        );

        CREATE TABLE chunks (
          chunk_id TEXT PRIMARY KEY,
          page_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          title TEXT,
          section_path TEXT,
          anchor TEXT,
          text TEXT NOT NULL,
          token_count INTEGER,
          embedding BLOB,
          FOREIGN KEY(page_id) REFERENCES pages(page_id)
        );

        CREATE TABLE toc_entries (
          toc_id TEXT PRIMARY KEY,
          parent_id TEXT,
          ordinal INTEGER NOT NULL,
          title TEXT NOT NULL,
          page_id TEXT,
          source_path TEXT,
          depth INTEGER
        );

        CREATE VIRTUAL TABLE chunks_fts USING fts5(
          chunk_id UNINDEXED,
          title,
          section_path,
          text,
          tokenize='porter unicode61'
        );
        """
    )


def insert_index(
    conn: sqlite3.Connection,
    *,
    help_file: dict[str, Any],
    pages: list[ParsedPage],
    chunks: list[Chunk],
    embeddings: np.ndarray,
    toc_entries: list[TocEntry],
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO help_file (
              id, original_path, title, sha256, size_bytes, mtime, indexed_at,
              schema_version, embedding_model, embedding_dimension,
              embedding_document_prefix, embedding_query_prefix, embedding_normalized,
              chunker_version, extraction_method
            )
            VALUES (
              :id, :original_path, :title, :sha256, :size_bytes, :mtime, :indexed_at,
              :schema_version, :embedding_model, :embedding_dimension,
              :embedding_document_prefix, :embedding_query_prefix, :embedding_normalized,
              :chunker_version, :extraction_method
            )
            """,
            help_file,
        )
        conn.executemany(
            """
            INSERT INTO pages (page_id, source_path, title, toc_path, raw_html_path, text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (page.page_id, page.source_path, page.title, None, page.raw_html_path, page.text)
                for page in pages
            ],
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            section_path = " > ".join(chunk.section_path)
            blob = np.asarray(embedding, dtype=np.float32).tobytes()
            conn.execute(
                """
                INSERT INTO chunks (
                  chunk_id, page_id, ordinal, title, section_path, anchor, text,
                  token_count, embedding
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.page_id,
                    chunk.ordinal,
                    chunk.title,
                    section_path,
                    chunk.anchor,
                    chunk.text,
                    chunk.token_count,
                    blob,
                ),
            )
            conn.execute(
                """
                INSERT INTO chunks_fts (chunk_id, title, section_path, text)
                VALUES (?, ?, ?, ?)
                """,
                (chunk.chunk_id, chunk.title, section_path, chunk.text),
            )
        conn.executemany(
            """
            INSERT INTO toc_entries (toc_id, parent_id, ordinal, title, page_id, source_path, depth)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    entry.toc_id,
                    entry.parent_id,
                    entry.ordinal,
                    entry.title,
                    entry.page_id,
                    entry.source_path,
                    entry.depth,
                )
                for entry in toc_entries
            ],
        )


def get_help_file(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM help_file LIMIT 1").fetchone()
    return dict(row) if row else None


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    toc = conn.execute("SELECT COUNT(*) FROM toc_entries").fetchone()[0]
    return {"pages": pages, "chunks": chunks, "toc_entries": toc}


def keyword_search(conn: sqlite3.Connection, query: str, limit: int) -> list[SearchRow]:
    fts_query = build_fts_query(query)
    if not fts_query:
        return []
    try:
        rows = conn.execute(
            """
            SELECT
              c.chunk_id, c.page_id, c.title, c.section_path, c.anchor, c.text, c.token_count,
              p.source_path,
              bm25(chunks_fts) AS bm25_score
            FROM chunks_fts
            JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            JOIN pages p ON p.page_id = c.page_id
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_score
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.DatabaseError:
        like = f"%{query}%"
        rows = conn.execute(
            """
            SELECT
              c.chunk_id, c.page_id, c.title, c.section_path, c.anchor, c.text, c.token_count,
              p.source_path,
              0.0 AS bm25_score
            FROM chunks c
            JOIN pages p ON p.page_id = c.page_id
            WHERE c.text LIKE ? OR c.title LIKE ?
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
    results: list[SearchRow] = []
    for row in rows:
        bm25 = float(row["bm25_score"])
        score = 1.0 / (1.0 + abs(bm25))
        results.append(_row_to_search_row(row, score))
    return results


def load_embedding_rows(
    conn: sqlite3.Connection, dimension: int
) -> tuple[list[SearchRow], np.ndarray]:
    rows = conn.execute(
        """
        SELECT
          c.chunk_id, c.page_id, c.title, c.section_path, c.anchor, c.text, c.token_count,
          c.embedding, p.source_path
        FROM chunks c
        JOIN pages p ON p.page_id = c.page_id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.chunk_id
        """
    ).fetchall()
    search_rows: list[SearchRow] = []
    vectors: list[np.ndarray] = []
    for row in rows:
        vector = np.frombuffer(row["embedding"], dtype=np.float32)
        if vector.shape[0] != dimension:
            continue
        vectors.append(vector)
        search_rows.append(_row_to_search_row(row, 0.0))
    if not vectors:
        return [], np.zeros((0, dimension), dtype=np.float32)
    return search_rows, np.vstack(vectors).astype(np.float32)


def get_chunk(conn: sqlite3.Connection, chunk_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT c.*, p.source_path
        FROM chunks c
        JOIN pages p ON p.page_id = c.page_id
        WHERE c.chunk_id = ?
        """,
        (chunk_id,),
    ).fetchone()
    return _dict_with_section_path(row) if row else None


def get_page(conn: sqlite3.Connection, page_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM pages WHERE page_id = ?", (page_id,)).fetchone()
    return dict(row) if row else None


def get_chunks_for_page(conn: sqlite3.Connection, page_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.*, p.source_path
        FROM chunks c
        JOIN pages p ON p.page_id = c.page_id
        WHERE c.page_id = ?
        ORDER BY c.ordinal
        """,
        (page_id,),
    ).fetchall()
    return [_dict_with_section_path(row) for row in rows]


def get_neighbor_chunks(
    conn: sqlite3.Connection, chunk_id: str, neighbors: int
) -> list[dict[str, Any]]:
    target = get_chunk(conn, chunk_id)
    if target is None:
        raise ChmseekError(
            "INVALID_CHUNK_ID",
            f"No chunk exists with ID {chunk_id}.",
            ["Use search or toc to find valid chunk IDs."],
        )
    number = int(chunk_id.removeprefix("ch_"))
    rows = conn.execute(
        """
        SELECT c.*, p.source_path
        FROM chunks c
        JOIN pages p ON p.page_id = c.page_id
        WHERE CAST(substr(c.chunk_id, 4) AS INTEGER) BETWEEN ? AND ?
        ORDER BY c.chunk_id
        """,
        (number - neighbors, number + neighbors),
    ).fetchall()
    return [_dict_with_section_path(row) for row in rows]


def get_toc_entries(conn: sqlite3.Connection, max_depth: int | None = None) -> list[dict[str, Any]]:
    if max_depth is None:
        rows = conn.execute("SELECT * FROM toc_entries ORDER BY ordinal").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM toc_entries WHERE depth <= ? ORDER BY ordinal", (max_depth,)
        ).fetchall()
    return [dict(row) for row in rows]


def build_fts_query(query: str) -> str:
    import re

    tokens = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_.:-]*", query)
    clean_tokens = [token.replace('"', '""') for token in tokens]
    if not clean_tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in clean_tokens[:12])


def _row_to_search_row(row: sqlite3.Row, score: float) -> SearchRow:
    return SearchRow(
        chunk_id=row["chunk_id"],
        page_id=row["page_id"],
        title=row["title"] or "",
        section_path=_split_section_path(row["section_path"]),
        source_path=row["source_path"],
        anchor=row["anchor"],
        text=row["text"],
        token_count=int(row["token_count"] or 0),
        score=score,
    )


def _dict_with_section_path(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["section_path"] = _split_section_path(payload.get("section_path"))
    payload.pop("embedding", None)
    return payload


def _split_section_path(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(">") if part.strip()]
