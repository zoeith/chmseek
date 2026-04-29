from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .chunker import CHUNKER_VERSION, chunk_pages
from .constants import (
    SCHEMA_VERSION,
)
from .embeddings import EmbeddingConfig, default_model_name, make_embedding_backend
from .errors import ChmseekError
from .extractors import choose_extractor
from .manifest import is_manifest_stale, load_manifest, manifest_path
from .parser import parse_help_tree
from .storage import connect, counts, initialize_schema, insert_index
from .toc import build_toc
from .utils import atomic_write_json, default_index_dir, sha256_file, utc_now_iso, validate_chm_path


@dataclass
class IndexOptions:
    force: bool = False
    index_dir: Path | None = None
    model_name: str | None = None
    embedding_dim: int | None = None
    allow_model_download: bool = False
    allow_remote_model_code: bool = False
    offline: bool = False
    model_revision: str | None = None
    from_extracted_dir: Path | None = None


@dataclass
class IndexHandle:
    chm_path: Path
    index_dir: Path
    db_path: Path
    manifest: dict[str, Any]
    was_built: bool
    stale_reasons: list[str]


def ensure_index(chm_path: Path, options: IndexOptions) -> IndexHandle:
    chm_path = chm_path.expanduser().resolve()
    validate_chm_path(chm_path)
    sha = sha256_file(chm_path)
    index_dir = (
        options.index_dir.expanduser().resolve()
        if options.index_dir
        else default_index_dir(sha)
    )
    manifest = load_manifest(index_dir)
    config = _effective_embedding_config(options, manifest)
    stale, reasons = is_manifest_stale(manifest, sha256=sha, embedding_config=config)
    db_path = index_dir / "index.sqlite"
    if manifest and db_path.exists() and not options.force and not stale:
        return IndexHandle(
            chm_path,
            index_dir,
            db_path,
            manifest,
            was_built=False,
            stale_reasons=[],
        )
    built = build_index(chm_path, index_dir, sha, config, options)
    return IndexHandle(
        chm_path,
        index_dir,
        db_path,
        built,
        was_built=True,
        stale_reasons=(["force"] if options.force else reasons),
    )


def build_index(
    chm_path: Path,
    index_dir: Path,
    sha: str,
    embedding_config: EmbeddingConfig,
    options: IndexOptions,
) -> dict[str, Any]:
    _clear_managed_index_files(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "logs").mkdir(exist_ok=True)

    extractor = choose_extractor(options.from_extracted_dir)
    extraction = extractor.extract(chm_path, index_dir / "extracted")
    pages = parse_help_tree(extraction.root)
    toc_entries = build_toc(extraction.root, pages)
    chunks = chunk_pages(pages)
    if not chunks:
        raise ChmseekError(
            "NO_PARSEABLE_HELP_CONTENT",
            "No chunks were produced from parseable help pages.",
            ["Inspect the extracted help content for readable text."],
        )

    backend = make_embedding_backend(embedding_config)
    embeddings = backend.embed_documents([chunk.text for chunk in chunks])
    db_path = index_dir / "index.sqlite"
    conn = connect(db_path)
    try:
        initialize_schema(conn)
        stat = chm_path.stat()
        help_file = {
            "id": f"sha256:{sha}",
            "original_path": str(chm_path),
            "title": pages[0].title if pages else chm_path.stem,
            "sha256": sha,
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "indexed_at": utc_now_iso(),
            "schema_version": SCHEMA_VERSION,
            "embedding_model": backend.model_name,
            "embedding_dimension": backend.dimension,
            "embedding_document_prefix": backend.document_prefix,
            "embedding_query_prefix": backend.query_prefix,
            "embedding_normalized": 1 if backend.normalized else 0,
            "chunker_version": CHUNKER_VERSION,
            "extraction_method": extraction.method,
        }
        insert_index(
            conn,
            help_file=help_file,
            pages=pages,
            chunks=chunks,
            embeddings=embeddings,
            toc_entries=toc_entries,
        )
        count_info = counts(conn)
    finally:
        conn.close()

    stat = chm_path.stat()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "original_path": str(chm_path),
        "file": {
            "sha256": sha,
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "fingerprint": f"sha256:{sha}",
        },
        "embedding": {
            "model": backend.model_name,
            "revision": backend.model_revision,
            "dimension": backend.dimension,
            "document_prefix": backend.document_prefix,
            "query_prefix": backend.query_prefix,
            "normalized": backend.normalized,
            "used_local_files_only": backend.used_local_files_only,
            "remote_model_code_allowed": backend.remote_model_code_allowed,
        },
        "extraction_method": extraction.method,
        "indexed_at": utc_now_iso(),
        "counts": count_info,
        "index_path": str(index_dir),
    }
    atomic_write_json(manifest_path(index_dir), manifest)
    return manifest


def index_status(chm_path: Path, options: IndexOptions) -> dict[str, Any]:
    chm_path = chm_path.expanduser().resolve()
    validate_chm_path(chm_path)
    sha = sha256_file(chm_path)
    index_dir = (
        options.index_dir.expanduser().resolve()
        if options.index_dir
        else default_index_dir(sha)
    )
    manifest = load_manifest(index_dir)
    config = _effective_embedding_config(options, manifest)
    stale, reasons = is_manifest_stale(manifest, sha256=sha, embedding_config=config)
    return {
        "indexed": manifest is not None and (index_dir / "index.sqlite").exists(),
        "stale": stale if manifest else None,
        "stale_reasons": reasons,
        "index_dir": str(index_dir),
        "manifest": manifest,
        "sha256": sha,
    }


def _effective_embedding_config(
    options: IndexOptions, manifest: dict[str, Any] | None
) -> EmbeddingConfig:
    embedding = manifest.get("embedding", {}) if manifest else {}
    return EmbeddingConfig(
        model_name=options.model_name or embedding.get("model") or default_model_name(),
        dimension=int(options.embedding_dim or embedding.get("dimension") or 768),
        allow_model_download=options.allow_model_download,
        allow_remote_model_code=options.allow_remote_model_code,
        offline=options.offline,
        model_revision=options.model_revision or embedding.get("revision"),
    )


def _clear_managed_index_files(index_dir: Path) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    for name in ("index.sqlite", "manifest.json"):
        target = index_dir / name
        if target.exists():
            target.unlink()
    for name in ("extracted", "logs"):
        target = index_dir / name
        if target.exists():
            if not target.is_dir():
                target.unlink()
            else:
                shutil.rmtree(target)
