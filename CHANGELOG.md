# Changelog

## 0.1.0 - 2026-04-29

Initial MVP release candidate.

- Added Windows-first CHM indexing with `hh.exe` extraction.
- Added extracted-directory indexing for tests and fixture demos.
- Added safe HTML/text parsing with active content removed.
- Added SQLite schema with FTS5 keyword search.
- Added deterministic fake embeddings for CI and fixture tests.
- Added gated sentence-transformers embedding backend for Nomic Embed Text v1.5.
- Added hybrid semantic+keyword search, read-with-neighbors, TOC, grep, info, diagnose, and audit commands.
- Added stable JSON output and structured JSON errors.
- Added release docs, security policy, Conda environment, pinned lockfiles, and CI workflow.
