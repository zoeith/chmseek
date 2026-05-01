# Changelog

## 0.1.2 - 2026-04-30

Patch release.

- Bumped `transformers` to `5.7.0`.
- Replaced DirectML device selection with Intel XPU support.
- Updated automatic embedding device priority to CUDA, XPU, MPS, then CPU.
- Documented XPU speed guidance and kept `einops` out of direct dependencies.

## 0.1.1 - 2026-04-29

Bugfix and usability release.

- Added `CHMSEEK_SKIP_PIP_AUDIT=1` for fast deterministic CLI tests.
- Improved Windows `hh.exe` extraction by using short paths when available.
- Pinned the default Nomic model revision to `e9b6763023c676ca8431644204f50c2b100d9aab`.
- Added `chmseek models prepare` for explicit model cache warmup.
- Added embedding device selection for `auto`, `cpu`, `cuda`, `mps`, and optional `directml`.
- Added progress display for document embedding while keeping query embedding quiet.
- Added safe local image-reference metadata in search/read JSON output.
- Improved Unicode readability in JSON output.
- Documented speed options, DirectML behavior, pinned model policy, and long-indexing expectations.

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
