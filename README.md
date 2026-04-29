# chmseek

`chmseek` is a secure, local-first command-line tool for indexing, reading, and searching
Windows compiled HTML Help (`.chm`) files.

It is built for old SDKs, lab instruments, engineering tools, simulation packages, GUI
applications, and enterprise systems where the real documentation still lives in CHM files.
The intended agent workflow is:

```text
toc -> search -> read result with neighbors -> grep exact term -> read page/chunk
```

## Status

This is an MVP release candidate. It includes:

- Windows-first CHM extraction through `hh.exe -decompile`.
- Test/development indexing from an already-extracted help directory.
- Optional `7z` fallback when available.
- Safe HTML/text parsing with active content ignored.
- SQLite storage with FTS5 keyword search.
- Local embedding search with Nomic Embed Text v1.5 by default.
- Hybrid search using reciprocal rank fusion.
- Stable JSON output for tools and agents.
- Fixture-based tests that do not require proprietary CHM files.

## Install For Development

Conda is the recommended development environment:

```bash
conda env create -f environment.yml
conda activate chmseek-dev
python -m pip install -e .
pytest
```

You can also install from the pinned lockfile:

```bash
python -m pip install -r requirements-dev.lock
python -m pip install -e .
pytest
```

## Quick Start

```bash
chmseek diagnose

chmseek index VendorSDK.chm --allow-model-download

chmseek search VendorSDK.chm "How do I configure the software before running analysis?" --json

chmseek search VendorSDK.chm "CreateSession" --mode hybrid --json

chmseek grep VendorSDK.chm "HRESULT" --json

chmseek toc VendorSDK.chm --json

chmseek read VendorSDK.chm --chunk-id ch_000153 --neighbors 2 --json

chmseek info VendorSDK.chm --json

chmseek audit
```

## Fixture Demo Without A Real CHM

The test fixture uses `--from-extracted-dir` and the deterministic fake embedding backend:

```bash
chmseek index tests/fixtures/fake.chm \
  --from-extracted-dir tests/fixtures/extracted_help \
  --index-dir .chmseek-test-cache/fixture \
  --model fake \
  --embedding-dim 128 \
  --force \
  --json

chmseek search tests/fixtures/fake.chm "CreateSession" \
  --index-dir .chmseek-test-cache/fixture \
  --json
```

## Security Model

CHM files are treated as untrusted input. `chmseek` extracts and parses documentation text; it
does not render help content, open CHM files for display, execute scripts, launch browsers, fetch
remote resources, or follow network links.

The indexer only processes allowlisted text-like file types:

- `.htm`
- `.html`
- `.xhtml`
- `.txt`
- `.hhc` and `.hhk` for TOC/index metadata

Active or executable content is ignored, including scripts, ActiveX/object/embed/iframe/frame
content, shortcuts, binaries, installers, CSS, and images. Subprocess calls use argument lists,
captured output, timeouts, and no shell execution.

## Extraction

On Windows, the primary extractor uses Microsoft HTML Help:

```powershell
hh.exe -decompile OUT_DIR FILE.chm
```

For tests and CI, `--from-extracted-dir` indexes a directory that already contains extracted help
files. If `7z` is available, it can be used as a best-effort fallback.

## Embeddings And Offline Mode

The default model is:

```text
nomic-ai/nomic-embed-text-v1.5
```

The default embedding dimension is `768`.

Model download is explicit. If the model is not cached, indexing/search fails unless you pass:

```bash
--allow-model-download
```

With `--offline`, the model must already be cached locally. Query/document prefixes are applied
inside the embedding backend:

- documents: `search_document: <chunk text>`
- queries: `search_query: <query text>`

Remote model code is never allowed silently. If a selected model requires remote code, you must
pass `--allow-remote-model-code` and a pinned `--model-revision`.

## Cache Layout

By default, indexes are stored under:

```text
%LOCALAPPDATA%\chmseek\indexes\<sha256>
```

On non-Windows systems, the fallback is:

```text
~/.cache/chmseek/indexes/<sha256>
```

Use `--index-dir PATH` to choose an explicit managed index directory.

Each index contains:

```text
manifest.json
index.sqlite
extracted/
logs/
```

## Commands

- `chmseek index PATH.chm`: build or rebuild an index.
- `chmseek search PATH.chm QUERY`: hybrid, semantic, or keyword search.
- `chmseek grep PATH.chm QUERY`: keyword-only search.
- `chmseek read PATH.chm --chunk-id ID --neighbors N`: read result context.
- `chmseek toc PATH.chm`: browse parsed or synthetic TOC entries.
- `chmseek info PATH.chm`: inspect index metadata and staleness.
- `chmseek diagnose`: inspect OS, SQLite, extractor, model, and audit readiness.
- `chmseek audit`: run dependency/release/security checks.

For a short copy-paste guide that can be added to other projects for agent use, see
`AGENT_CHMSEEK_USAGE.md`.

All commands that support `--json` return stable JSON. Errors use:

```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "...",
    "hints": ["..."]
  }
}
```

## Release Checks

```bash
pytest
chmseek diagnose --json
chmseek audit --json
python -m build --no-isolation
```

## Limitations

- The MVP is CLI-only; it does not include a GUI, server, daemon, chat interface, or MCP server.
- It does not render CHM HTML visually.
- Semantic search uses brute-force NumPy similarity over SQLite-stored embeddings.
- Cross-platform use is best-effort; Windows remains the primary extraction target.
