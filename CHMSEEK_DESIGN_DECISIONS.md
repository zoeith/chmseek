# `chmseek` Design Decisions

This file records the initial design decisions for `chmseek`, a Windows-first CLI for indexing, reading, and searching `.chm` help files with both keyword and semantic retrieval.

## 1. Product framing

`chmseek` exists because many old software systems, SDKs, APIs, simulation tools, lab instruments, engineering tools, and enterprise applications still ship documentation as Windows compiled HTML Help files (`.chm`).

These files are often broader than API references. They may include:

- conceptual explanations
- workflows
- tutorials
- GUI instructions
- examples
- troubleshooting guides
- reference tables
- API/class/function docs
- installation and licensing notes

Therefore the tool must support both:

1. exact lookup of API symbols, error codes, menu commands, and class/function names
2. conceptual search and reading of tutorial/workflow/explanatory material

The core agent workflow should be:

```text
toc -> search -> read result with neighbors -> grep exact term -> read page/chunk
```

## 2. Name

The project name is:

```text
chmseek
```

The name is intentionally specific to `.chm` help files. A later generalized project could use a broader name such as `docseek`, but the MVP should stay focused.

## 3. Scope

The MVP is:

- Windows-first
- CLI-only
- local-first
- testable without proprietary CHM files

Explicit non-goals:

- no GUI
- no MCP server
- no daemon
- no chat interface
- no web app
- no attempt to render CHM content
- no dependency on Zotero or ZotSeek internals

Cross-platform support is a bonus, not an MVP requirement.

## 4. Extraction decision

Primary extraction should use Windows HTML Help:

```powershell
hh.exe -decompile OUT_DIR FILE.chm
```

This is the Windows-first path and should be implemented as `WindowsHhExtractor`.

A test/dev extractor, `ExtractedDirExtractor`, is required so the entire indexing/search/read pipeline can be tested with fixture directories.

An optional `SevenZipExtractor` can be added as a fallback if `7z` is present, but it is not the main path.

## 5. Security model

Treat CHM files as untrusted input.

The tool should extract and parse text, not execute or render help content.

Never:

- open a CHM for display
- execute anything from the CHM
- execute scripts, ActiveX, binaries, shortcuts, or installers
- launch extracted HTML in a browser
- fetch external resources while indexing
- follow network links
- load remote images, scripts, CSS, or frames
- use `shell=True`
- use `eval` or `exec`
- load pickle data derived from CHM content
- write outside the managed cache/index directory

Only process allowlisted text-like file types:

- `.htm`
- `.html`
- `.xhtml`
- `.txt`, if safe

Ignore executable or active content, including:

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

Remove unsafe HTML tags:

- `script`
- `style`
- `object`
- `embed`
- `iframe`
- `frame`

All subprocess calls must use argument lists, `shell=False`, timeouts, and captured output.

All extracted paths must be normalized and verified to remain inside the extraction directory.

## 6. Embedding model decision

Default embedding model:

```text
nomic-ai/nomic-embed-text-v1.5
```

Reasons:

- It is a stronger retrieval-oriented embedding model than a very small MiniLM-style default.
- It supports long help-document chunks.
- It supports variable embedding dimensions through Matryoshka-style truncation.
- It is suitable for conceptual/tutorial search in addition to short API references.

Default embedding dimension:

```text
768
```

Optional future dimensions:

```text
512
256
```

The MVP should use 768 unless explicitly configured otherwise.

## 7. Nomic prefix policy

Nomic retrieval embeddings require task prefixes.

All indexed documentation chunks must be embedded as:

```text
search_document: <chunk text>
```

All user queries must be embedded as:

```text
search_query: <query text>
```

This must be enforced inside the embedding backend. Callers should never be responsible for prefixing.

The manifest must record the prefix policy because changing it invalidates the semantic index.

## 8. Model download and remote-code policy

One-time model download is acceptable, but only when explicitly allowed:

```bash
--allow-model-download
```

If `--offline` is set and the model is not cached, the tool should fail clearly.

If the model is not cached and `--allow-model-download` was not passed, the tool should fail with a clear instruction.

Remote model code must not be executed silently.

The implementation should prefer a model loading path that does not require `trust_remote_code=True`.

If `trust_remote_code=True` is required for the selected Nomic loading path:

- require explicit `--allow-remote-model-code`
- require a pinned model revision
- document the security tradeoff
- record the decision in the manifest
- test that the default path refuses unpinned remote model code

## 9. Indexing behavior

Indexing should happen automatically on first use.

If the user runs:

```bash
chmseek search VendorSDK.chm "CreateSession" --json
```

and no index exists, `chmseek` should attempt to build one.

The index is stale if any of the following changed:

- CHM file hash
- schema version
- embedding model
- embedding dimension
- embedding prefix policy
- chunker version

The user can force rebuilding with:

```bash
chmseek index VendorSDK.chm --force
```

## 10. Cache layout

Use the Windows cache path by default:

```text
%LOCALAPPDATA%\chmseek\indexes\<fingerprint>\
```

Support override:

```bash
--index-dir PATH
```

Each index directory should contain:

```text
manifest.json
index.sqlite
extracted/
logs/
```

## 11. Storage decision

Use SQLite.

Reasons:

- built into Python
- reliable
- easy to inspect
- supports FTS5 keyword search
- sufficient for small/medium help files
- no separate vector database dependency needed for MVP

Use SQLite FTS5 for keyword search.

Store embeddings as float32 BLOBs in the `chunks` table.

For MVP semantic search, load embeddings into memory and do brute-force cosine similarity with NumPy. This avoids adding FAISS, hnswlib, sqlite-vec, or another vector database dependency too early.

## 12. Search design

Support three modes:

```text
keyword
semantic
hybrid
```

Default:

```text
hybrid
```

Keyword search uses SQLite FTS5 BM25.

Semantic search uses Nomic query embeddings and cosine similarity against normalized document embeddings.

Hybrid search uses Reciprocal Rank Fusion over keyword and semantic rankings.

This is important because `.chm` help files contain both:

- exact symbols like `CreateSession`, `HRESULT`, `SetParameter`
- conceptual content like “how do I configure a project before running analysis?”

## 13. TOC and read are first-class features

`toc` is first-class because agents need to browse help structure, not only retrieve snippets.

`read` is first-class because agents need to expand around search hits.

Required commands:

```bash
chmseek toc VendorSDK.chm --json
chmseek read VendorSDK.chm --chunk-id ch_000153 --neighbors 2 --json
```

If no `.hhc` table of contents is available, synthesize one from page titles and headings.

## 14. Chunking decision

Because the default Nomic model can support longer context than a tiny embedding model, use larger but still manageable chunks:

```text
target chunk size: 1000-1600 tokens
max chunk size: 2200 tokens
overlap: 150-250 tokens
```

Chunking should be section-aware.

Prefer h1/h2/h3 boundaries.

Avoid splitting code/pre blocks when reasonably possible.

Create smaller chunks for dense API reference pages.

Store:

- chunk ID
- page ID
- ordinal
- title
- section path
- source path
- anchor
- text
- token count
- embedding

## 15. CLI design

Use stdlib `argparse` for MVP unless a dependency is clearly justified.

Required commands:

```bash
chmseek index
chmseek search
chmseek read
chmseek toc
chmseek grep
chmseek info
chmseek diagnose
chmseek audit
```

The JSON output should be stable and agent-oriented.

All JSON errors should use:

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

## 16. Dependency posture

Runtime dependencies should be few, well-known, and auditable.

Allowed default runtime dependencies:

- Python standard library
- `beautifulsoup4`
- `lxml`
- `numpy`
- `pydantic`
- `sentence-transformers`

Optional runtime dependency:

- `rich`, only if worthwhile for human-readable output

Development/audit dependencies:

- `pytest`
- `pip-audit`
- optionally `bandit`
- optionally `ruff`

Avoid obscure or unmaintained CHM libraries.

Do not make `pychm` a required dependency.

Use pinned dependencies and a lockfile.

## 17. Audit command

Add:

```bash
chmseek audit
```

It should:

- run dependency vulnerability audit if available
- check lockfile presence
- check dependencies are pinned
- scan source for risky patterns:
  - `shell=True`
  - `eval(`
  - `exec(`
  - `pickle.load`
  - unsafe archive extraction
  - writes outside cache/index directory

Support:

```bash
chmseek audit --json
```

## 18. Testing strategy

The project must be testable without proprietary CHM files.

Use fixture directories that simulate extracted CHM contents.

Required fixtures:

```text
tests/fixtures/extracted_help/index.html
tests/fixtures/extracted_help/getting_started/concepts.html
tests/fixtures/extracted_help/tutorials/workflow.html
tests/fixtures/extracted_help/api/session.html
tests/fixtures/extracted_help/api/errors.html
tests/fixtures/extracted_help/reference/tables.html
```

Optional:

```text
tests/fixtures/extracted_help/toc.hhc
tests/fixtures/extracted_help/index.hhk
```

Fixture content should include both conceptual material and exact symbols such as:

```text
CreateSession
CloseSession
HRESULT
SetParameter
```

Use a fake deterministic embedding backend in tests so CI does not need to download the Nomic model.

## 19. Acceptance criteria

The MVP is successful when:

- `pytest` passes
- indexing works from an extracted fixture directory
- exact symbol search works
- conceptual search works
- hybrid search returns stable JSON
- TOC browsing works
- synthetic TOC works if no `.hhc` exists
- reading chunks with neighbors works
- stale index detection works
- `diagnose` works
- `audit` works
- no subprocess uses `shell=True`
- CHM-derived files cannot escape the managed cache/index directory
- model download is explicit
- remote model code is not silently executed
- the implementation is modular enough for a future wrapper, but no MCP/server is built in MVP

## 20. References

- Microsoft HTML Help decompile behavior: https://learn.microsoft.com/en-us/previous-versions/windows/desktop/htmlhelp/decompiling-a-help-file
- Nomic Embed Text v1.5 model card: https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
- Nomic embedding documentation: https://docs.nomic.ai/reference/api/embed-text-v-1-embedding-text-post
- pip-audit project: https://pypi.org/project/pip-audit/
