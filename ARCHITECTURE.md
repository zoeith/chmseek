# Architecture

`chmseek` is organized as a small importable Python package so a future wrapper can call the
service functions directly without turning the MVP into a server.

## Flow

```text
CLI -> indexer -> extractor -> parser -> toc/chunker -> embeddings -> SQLite
CLI -> search/read/toc/info -> SQLite + embeddings
```

## Modules

- `chmseek.cli`: `argparse` command surface and human/JSON output.
- `chmseek.indexer`: fingerprinting, cache layout, staleness, and index builds.
- `chmseek.extractors`: Windows `hh.exe`, extracted directory, and optional `7z` extraction.
- `chmseek.parser`: safe text extraction from allowlisted HTML/text files.
- `chmseek.toc`: `.hhc`/`.hhk` parsing and synthetic outlines.
- `chmseek.chunker`: section-aware chunk creation.
- `chmseek.embeddings`: fake test embeddings and gated sentence-transformers backend.
- `chmseek.storage`: SQLite schema, FTS5 keyword search, and read helpers.
- `chmseek.search`: semantic, keyword, and hybrid search ranking.
- `chmseek.audit`: release/security checks.
- `chmseek.diagnostics`: environment readiness checks.

## Staleness

An index is stale when any of these change:

- source CHM SHA-256
- schema version
- embedding model
- embedding dimension
- embedding prefix policy
- chunker version

## Search

Keyword search uses SQLite FTS5 BM25. Semantic search loads normalized float32 embeddings from
SQLite and computes cosine similarity in memory with NumPy. Hybrid search combines keyword and
semantic rankings with reciprocal rank fusion.
