# Codex Prompt: Build `chmseek`

You are building a new open-source Python CLI project called `chmseek`.

## Mission

Build a secure, Windows-first, local-first command-line tool that lets agents read, inspect, keyword-search, and semantic-search Windows `.chm` help files.

The intended use case is old software, SDKs, APIs, GUI applications, simulation packages, engineering tools, lab instruments, or enterprise applications whose documentation exists mainly as Windows compiled HTML Help files rather than modern web docs or agent-friendly API references.

A `.chm` help file is not just API reference. It may contain conceptual explanations, workflows, tutorials, examples, GUI operation instructions, troubleshooting guides, reference tables, API/class/function docs, installation notes, and licensing notes. `chmseek` should help agents read the whole help corpus, not only exact API entries.

Use ZotSeek only as conceptual inspiration:
- local/private indexing
- first-use auto-indexing
- semantic search
- hybrid semantic + keyword search
- chunk/passage-level results
- stable JSON output for tools/agents
- crash-resilient indexing
- search results that can be expanded by reading neighboring chunks

Do not depend on Zotero or ZotSeek internals.

## Scope

- Windows-first.
- CLI only.
- No MCP.
- No server.
- No daemon.
- Cross-platform support is a later bonus.
- First target platform: Windows 10/11.
- One-time embedding model download is acceptable.
- After the model is downloaded, normal indexing/search operation should be local/offline.
- The project must be testable without proprietary CHM files.

## Security posture

Treat every `.chm` file as untrusted input.

Never:
- open a CHM for display
- execute anything inside the CHM
- execute scripts, ActiveX, binaries, shortcuts, installers, or embedded executable content
- launch extracted HTML in a browser
- fetch remote links/resources during indexing
- load remote images/scripts/CSS/frames
- use `shell=True`
- use `eval`, `exec`, unsafe pickle loading, or unsafe archive extraction
- write outside the managed cache/index directory

Only extract and parse text-like documentation content.

All subprocess calls must:
- use argument lists, never shell strings
- use `shell=False`
- enforce timeouts
- capture stdout/stderr
- report actionable errors

All extracted paths must be normalized and checked to ensure they remain inside the expected extraction directory.

## Primary extraction behavior

On Windows, use Microsoft HTML Help's decompile mechanism:

```powershell
hh.exe -decompile OUT_DIR FILE.chm
```

Implement this as the primary extractor.

## Extraction architecture

Create an extractor interface.

Implement:

### `WindowsHhExtractor`

Primary extractor.

- Available only on Windows.
- Uses `hh.exe -decompile OUT_DIR FILE.chm`.
- Uses `subprocess.run([...], shell=False, timeout=...)`.
- Captures stdout/stderr.
- Validates extracted paths.
- After extraction, scans the extracted tree and only processes allowlisted file types.

### `ExtractedDirExtractor`

Required for tests and development.

- Allows indexing an already-extracted help directory.
- Enables full indexing/search/read testing without real CHM files.
- Used by `--from-extracted-dir`.

### `SevenZipExtractor`

Optional fallback only.

- Available only if `7z` is on PATH.
- Uses `subprocess.run([...], shell=False, timeout=...)`.
- Treat as best-effort.
- Must pass the same post-extraction safety checks.

Do not make `pychm` a required dependency. If considered later, it must be optional and separately justified because licensing/maintenance posture may not fit this project.

## Embedding model

Use Nomic Embed by default.

Default model:

```text
nomic-ai/nomic-embed-text-v1.5
```

Reasons:
- The help corpus may include long conceptual/tutorial material.
- Nomic v1.5 supports long-context text embedding and Matryoshka-style dimension reduction.
- Default embedding dimension should be 768.
- Allow optional dimensions 512 and 256 later, but the MVP should use 768 unless explicitly configured.

Important task-prefix policy:

All indexed documentation chunks must be embedded as:

```text
search_document: <chunk text>
```

All user search queries must be embedded as:

```text
search_query: <query text>
```

This prefixing must happen inside the embedding backend, not in callers.

Example:

```python
embed_documents(["chunk text"])
# internally embeds ["search_document: chunk text"]

embed_query("how do I configure a project?")
# internally embeds "search_query: how do I configure a project?"
```

Do not accidentally use the same prefix for documents and queries.

### Model download policy

One-time model download is allowed only when the user passes:

```bash
--allow-model-download
```

If `--offline` is set and the model is not cached, fail with a clear error.

If the model is not cached and `--allow-model-download` was not passed, fail with a clear instruction explaining how to allow the download.

The embedding backend must store in the manifest:
- model name
- model revision, if available
- embedding dimension
- prefix policy
- normalization policy
- whether local files only were used
- whether remote/model code was required

### `trust_remote_code` policy

Do not silently execute remote model code.

Implementation should prefer a dependency/model-loading path that does not require `trust_remote_code=True`.

If the currently selected Nomic loading path requires `trust_remote_code=True`, then:
- it must be gated behind an explicit flag, e.g. `--allow-remote-model-code`
- it must require a pinned model revision
- the README must explain the security tradeoff
- tests must cover that the default path refuses to run unpinned remote model code
- the manifest must record that remote model code was allowed

For the MVP, if avoiding `trust_remote_code` proves difficult, implement a clean abstraction and fail safely with an actionable message rather than adding a risky default.

## CLI commands

Use stdlib `argparse` for the MVP unless there is a strong reason to add a CLI dependency.

### `chmseek index PATH_TO_FILE.chm`

Build or rebuild an index.

Options:
- `--force`
- `--index-dir PATH`
- `--model MODEL_NAME`
- `--embedding-dim INT`, default 768
- `--allow-model-download`
- `--allow-remote-model-code`
- `--offline`
- `--from-extracted-dir PATH`

Behavior:
- Compute file fingerprint.
- Check whether index exists.
- Rebuild if stale.
- Extract CHM, unless `--from-extracted-dir` is provided.
- Parse TOC/index if available.
- Parse HTML-like content.
- Chunk text.
- Build SQLite database.
- Build SQLite FTS5 keyword index.
- Generate local embeddings.
- Store manifest.

### `chmseek search PATH_TO_FILE.chm QUERY`

Search conceptually or by exact terms.

Options:
- `--mode hybrid|semantic|keyword`, default `hybrid`
- `--top-k INT`, default 8
- `--json`
- `--offline`
- `--allow-model-download`
- `--allow-remote-model-code`

Behavior:
- On first use, check whether an index exists.
- If missing or stale, build it automatically.
- If indexing requires model download and download is not allowed, fail clearly.
- Return ranked chunk-level results.
- Default hybrid search must work well for both:
  - conceptual queries like `how do I configure a project before running analysis?`
  - exact terms like `CreateSession`, `HRESULT`, `SetParameter`, menu commands, or error codes.

### `chmseek read PATH_TO_FILE.chm`

Read page/chunk context.

Options:
- `--page-id ID`
- `--chunk-id ID`
- `--neighbors INT`, default 0
- `--json`

Behavior:
- Return exact chunk or page text.
- If `--neighbors 2`, include two chunks before and two chunks after the target.
- This is critical for agents because search results should be expandable without dumping the entire help file.

### `chmseek toc PATH_TO_FILE.chm`

Show table of contents.

Options:
- `--json`
- `--max-depth INT`

Behavior:
- Let agents browse conceptual/tutorial sections.
- If no TOC exists, synthesize a shallow outline from parsed page titles and headings.

### `chmseek grep PATH_TO_FILE.chm QUERY`

Keyword-only search.

Options:
- `--top-k INT`, default 20
- `--json`

Behavior:
- Use SQLite FTS5.
- Good for symbols, function names, menu names, error codes, class names, and exact phrases.

### `chmseek info PATH_TO_FILE.chm`

Show index metadata.

Options:
- `--json`

Include:
- indexed/not indexed
- stale/not stale
- page count
- chunk count
- embedding model
- embedding dimension
- schema version
- chunker version
- original file SHA-256
- index path
- extraction method used
- model cache status
- remote model code status

### `chmseek diagnose`

Show environment diagnostics.

Include:
- OS
- Python version
- SQLite version
- SQLite FTS5 availability
- cache directory
- whether `hh.exe` is available
- whether `7z` is available
- whether embedding model is cached
- whether embedding backend loads
- whether dependency audit tooling is installed

### `chmseek audit`

Run project security checks.

Behavior:
- Run dependency vulnerability audit if available.
- Check lockfile presence.
- Check that dependencies are pinned.
- Check for risky source patterns:
  - `shell=True`
  - `eval(`
  - `exec(`
  - `pickle.load`
  - unsafe archive extraction
  - arbitrary writes outside cache/index directory
- Print human-readable output by default.
- Support `--json`.

## Dependency policy

Use as few dependencies as practical.

Runtime dependencies should be limited and well-established.

Allowed default runtime dependencies:
- Python standard library
- `beautifulsoup4`
- `lxml`
- `numpy`
- `pydantic`
- `sentence-transformers`

Optional:
- `rich`, only if it clearly improves human CLI output

Development/audit dependencies:
- `pytest`
- `pip-audit`
- optionally `bandit`
- optionally `ruff`

Do not make audit tools runtime dependencies unless necessary.

Avoid:
- unmaintained packages
- obscure CHM libraries
- packages with unclear license
- packages that execute or render CHM/HTML content
- packages that require network access during indexing
- large dependency trees unless justified

Use pinned dependencies through a lockfile.

## Cache layout

Use this Windows default cache location:

```text
%LOCALAPPDATA%\chmseek\indexes\<fingerprint>\
```

Also support explicit:

```bash
--index-dir PATH
```

Cache contents:

```text
manifest.json
index.sqlite
extracted/
logs/
```

## Fingerprint and staleness

For MVP, use full SHA-256 of the CHM file.

Manifest should include:
- original path
- file size
- mtime
- SHA-256
- schema version
- embedding model
- embedding dimension
- embedding prefix policy
- embedding normalization policy
- chunker version
- extraction method
- indexed timestamp

Rebuild if:
- CHM hash changed
- schema version changed
- embedding model changed
- embedding dimension changed
- embedding prefix policy changed
- chunker version changed
- `--force` was passed

## SQLite schema

Use stdlib `sqlite3`.

Create tables:
- `help_file`
- `pages`
- `chunks`
- `toc_entries`
- `chunks_fts` using SQLite FTS5

Store embeddings as float32 BLOBs in `chunks.embedding`.

Suggested schema:

```sql
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
```

## HTML/content parsing

Process only allowlisted file extensions:
- `.htm`
- `.html`
- `.xhtml`
- `.txt`, if safe

Ignore:
- `.exe`
- `.dll`
- `.ocx`
- `.vbs`
- `.js`
- `.ps1`
- `.bat`
- `.cmd`
- `.scr`
- `.lnk`
- `.msi`
- `.cab`
- images
- CSS
- binaries

Remove:
- `script`
- `style`
- `object`
- `embed`
- `iframe`
- `frame`
- ActiveX-like/object content

Do not fetch network resources.

Preserve:
- headings
- code/preformatted blocks
- tables, converted to readable markdown-like text
- lists
- useful link text, but do not follow links

Extract title from:
1. TOC entry
2. HTML `<title>`
3. first `h1`
4. filename

## TOC/index parsing

Parse `.hhc` and `.hhk` if available.

They are usually HTML-like files.

Extract:
- topic names
- local paths
- hierarchy/depth
- page mapping

If parsing fails, continue without failing indexing.

Build a useful synthetic outline from page titles/headings if TOC is absent.

## Chunking

Because Nomic v1.5 can support longer context, use slightly larger chunks than a small MiniLM-style model:

- target chunk size: 1000-1600 tokens
- max chunk size: 2200 tokens
- overlap: 150-250 tokens

However:
- prefer section-aware chunking
- use h1/h2/h3 boundaries when possible
- do not split code/pre blocks if reasonably avoidable
- create smaller chunks for dense API reference pages
- store section path
- store page title
- store source path
- store anchor when available
- store token counts
- warn if a chunk exceeds configured model context limits

## Embedding backend interface

Implement:

```python
class EmbeddingBackend:
    model_name: str
    dimension: int
    document_prefix: str
    query_prefix: str

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        ...

    def embed_query(self, text: str) -> np.ndarray:
        ...
```

The backend is responsible for:
- applying prefixes
- batching
- normalization
- optional Matryoshka truncation
- converting to float32
- returning deterministic dimensions

Add a deterministic fake embedding backend for tests so CI does not need to download a model.

## Search

### Semantic search

- Embed query with `search_query:`.
- Load chunk embeddings.
- Compute cosine similarity against normalized document vectors.

### Keyword search

- Use SQLite FTS5 BM25.

### Hybrid search

Default mode.

Use Reciprocal Rank Fusion over semantic and keyword rankings.

Hybrid search should support both:
- conceptual help queries
- exact API/symbol queries

## JSON output

All JSON output should be stable and agent-friendly.

### `search --json`

Return:

```json
{
  "ok": true,
  "query": "how do I configure a project?",
  "mode": "hybrid",
  "help_file": {
    "path": "VendorSDK.chm",
    "title": "Vendor SDK Help",
    "fingerprint": "sha256:..."
  },
  "index": {
    "status": "ready",
    "was_built": false,
    "chunks": 1931,
    "pages": 842,
    "model": "nomic-ai/nomic-embed-text-v1.5",
    "embedding_dimension": 768
  },
  "results": [
    {
      "rank": 1,
      "score": 0.8421,
      "semantic_score": 0.7912,
      "keyword_score": 0.36,
      "chunk_id": "ch_000153",
      "page_id": "p_000077",
      "title": "Connecting to the Server",
      "section_path": ["Getting Started", "Connections", "Authentication"],
      "source_path": "html/getting_started/connect.htm",
      "source_uri": "chm://VendorSDK.chm/html/getting_started/connect.htm#authentication",
      "snippet": "Call CreateSession before any API operation...",
      "text_preview": "Call CreateSession before any API operation. The session handle must be...",
      "neighbor_command": "chmseek read VendorSDK.chm --chunk-id ch_000153 --neighbors 2 --json"
    }
  ]
}
```

### JSON error schema

All commands with `--json` should return structured errors:

```json
{
  "ok": false,
  "error": {
    "code": "EXTRACTION_FAILED",
    "message": "...",
    "hints": ["..."]
  }
}
```

Important error cases:
- file does not exist
- file is not `.chm`
- extraction failed
- no parseable help content found
- model not cached and offline mode requested
- model download required but not allowed
- remote model code required but not allowed
- SQLite FTS5 unavailable
- invalid chunk ID
- invalid page ID
- extraction attempted path traversal
- extracted file tried to escape cache directory
- dependency audit failed

## Tests

Use `pytest`.

Because we do not have proprietary target CHM files, tests must work with fixture directories.

Create fixtures:
- `tests/fixtures/extracted_help/index.html`
- `tests/fixtures/extracted_help/getting_started/concepts.html`
- `tests/fixtures/extracted_help/tutorials/workflow.html`
- `tests/fixtures/extracted_help/api/session.html`
- `tests/fixtures/extracted_help/api/errors.html`
- `tests/fixtures/extracted_help/reference/tables.html`
- optional `.hhc` and `.hhk` fixture files

Fixture content should include both:
- conceptual/tutorial text
- exact API symbols like `CreateSession`, `CloseSession`, `HRESULT`, and `SetParameter`

Required tests:
1. Index from extracted dir.
2. Search exact keyword like `CreateSession`.
3. Search conceptual query like `how do I set up a project before running the analysis?`
4. Semantic search smoke test using fake embeddings.
5. Hybrid search returns stable JSON schema.
6. Read chunk with neighbors.
7. TOC parsing works with `.hhc`.
8. Synthetic TOC works when `.hhc` is absent.
9. Stale index detection works.
10. Diagnose command runs.
11. Extraction failure produces actionable JSON error.
12. Unsafe extracted paths are rejected.
13. Script/object/iframe content is ignored.
14. CLI commands run through subprocess or argparse test harness.
15. Audit command returns useful output.
16. Document chunks are prefixed with `search_document:`.
17. Queries are prefixed with `search_query:`.
18. Changing embedding dimension marks the index stale.
19. Changing model name marks the index stale.
20. Remote model code is not allowed unless explicitly enabled.

## README requirements

Include:
- What problem `chmseek` solves.
- Why CHM files are treated as untrusted input.
- Windows-first extraction design.
- How first-use indexing works.
- How one-time embedding model download works.
- Offline mode behavior.
- Example commands for agents.
- Security model.
- Dependency audit instructions.
- Limitations.

Example commands:

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

## Implementation order

1. Project skeleton.
2. CLI parser with stub commands.
3. Cache/fingerprint/manifest logic.
4. Extracted-dir indexing path.
5. Safe file traversal and allowlist filtering.
6. HTML parser.
7. TOC parser.
8. Chunker.
9. SQLite schema and FTS.
10. Fake embedding backend.
11. Semantic search plumbing.
12. Hybrid search.
13. Search/read/toc/info JSON output.
14. Windows `hh.exe` extractor.
15. Optional 7z extractor.
16. Diagnose command.
17. Audit command.
18. Tests.
19. README and architecture docs.

## Acceptance criteria

- `pytest` passes.
- Project can be tested without real CHM files.
- `chmseek index fake.chm --from-extracted-dir tests/fixtures/extracted_help --force` works.
- `chmseek search fake.chm "CreateSession" --json` returns at least one result.
- `chmseek search fake.chm "how do I set up a project before analysis?" --json` returns conceptual/tutorial content.
- `chmseek read fake.chm --chunk-id <id> --neighbors 1 --json` returns neighboring chunks.
- `chmseek toc fake.chm --json` returns either parsed or synthetic TOC.
- `chmseek info fake.chm --json` reports index status.
- `chmseek diagnose` reports Windows extraction readiness.
- `chmseek audit` runs and reports dependency/security status.
- No subprocess call uses `shell=True`.
- Extracted content cannot write or read outside the managed cache/index directory.
- The code is modular enough that a future wrapper could call Python service functions directly, but do not build MCP or server functionality now.
