from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .audit import human_audit_report, run_audit
from .diagnostics import diagnose
from .embeddings import (
    DEFAULT_EMBEDDING_DIM,
    EmbeddingConfig,
    default_model_name,
    is_model_cached,
    make_embedding_backend,
    normalize_embedding_config,
)
from .errors import ChmseekError
from .indexer import IndexOptions, ensure_index, index_status
from .reader import read_content
from .search import run_search
from .storage import connect, counts, get_help_file, get_toc_entries, keyword_search
from .utils import json_dumps, preview_text


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = dispatch(args)
        if getattr(args, "json", False):
            print(json_dumps(payload))
        else:
            print(humanize(args, payload))
        return 0 if payload.get("ok", True) else 1
    except ChmseekError as exc:
        if getattr(args, "json", False):
            print(json_dumps(exc.to_payload()))
        else:
            print(f"error[{exc.code}]: {exc.message}", file=sys.stderr)
            for hint in exc.hints:
                print(f"hint: {hint}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chmseek",
        description="Search and read Windows CHM help files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="Build or rebuild an index.")
    add_path_argument(index)
    add_index_options(index)
    add_json_option(index)

    search = sub.add_parser("search", help="Search indexed CHM help.")
    add_path_argument(search)
    search.add_argument("query")
    search.add_argument("--mode", choices=["hybrid", "semantic", "keyword"], default="hybrid")
    search.add_argument("--top-k", type=int, default=8)
    add_runtime_options(search)
    add_json_option(search)

    grep = sub.add_parser("grep", help="Keyword-only search.")
    add_path_argument(grep)
    grep.add_argument("query")
    grep.add_argument("--top-k", type=int, default=20)
    add_runtime_options(grep)
    add_json_option(grep)

    read = sub.add_parser("read", help="Read a page or chunk with optional neighbors.")
    add_path_argument(read)
    target = read.add_mutually_exclusive_group(required=True)
    target.add_argument("--page-id")
    target.add_argument("--chunk-id")
    read.add_argument("--neighbors", type=int, default=0)
    add_runtime_options(read)
    add_json_option(read)

    toc = sub.add_parser("toc", help="Show table of contents.")
    add_path_argument(toc)
    toc.add_argument("--max-depth", type=int)
    add_runtime_options(toc)
    add_json_option(toc)

    info = sub.add_parser("info", help="Show index metadata.")
    add_path_argument(info)
    add_runtime_options(info, include_model=True)
    add_json_option(info)

    diag = sub.add_parser("diagnose", help="Show environment diagnostics.")
    diag.add_argument("--model", default=default_model_name())
    add_json_option(diag)

    models = sub.add_parser("models", help="Manage embedding models.")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    prepare = models_sub.add_parser(
        "prepare",
        help="Download/cache the configured embedding model.",
    )
    prepare.add_argument("--model", default=default_model_name(), help="Embedding model name.")
    prepare.add_argument("--embedding-dim", type=int, default=DEFAULT_EMBEDDING_DIM)
    prepare.add_argument(
        "--allow-model-download",
        action="store_true",
        help="Allow one-time embedding model download if not cached.",
    )
    prepare.add_argument(
        "--allow-remote-model-code",
        action="store_true",
        help="Allow remote model code, only with --model-revision.",
    )
    prepare.add_argument("--model-revision", help="Pinned model revision for remote model code.")
    prepare.add_argument("--offline", action="store_true", help="Do not download embedding models.")
    add_device_option(prepare)
    add_json_option(prepare)

    audit = sub.add_parser("audit", help="Run release/security checks.")
    add_json_option(audit)

    return parser


def add_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", type=Path, help="Path to the original .chm file.")


def add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output.")


def add_index_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--force", action="store_true", help="Rebuild even if the index is fresh.")
    add_runtime_options(parser, include_model=True)


def add_runtime_options(parser: argparse.ArgumentParser, *, include_model: bool = False) -> None:
    parser.add_argument("--index-dir", type=Path, help="Use an explicit managed index directory.")
    parser.add_argument("--offline", action="store_true", help="Do not download embedding models.")
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help="Allow one-time embedding model download if not cached.",
    )
    parser.add_argument(
        "--allow-remote-model-code",
        action="store_true",
        help="Allow remote model code, only with --model-revision.",
    )
    parser.add_argument("--model-revision", help="Pinned model revision for remote model code.")
    add_device_option(parser)
    parser.add_argument(
        "--from-extracted-dir",
        type=Path,
        help="Index from an already-extracted help directory for tests/development.",
    )
    if include_model:
        parser.add_argument("--model", default=default_model_name(), help="Embedding model name.")
        parser.add_argument("--embedding-dim", type=int, default=DEFAULT_EMBEDDING_DIM)
    else:
        parser.add_argument("--model", help=argparse.SUPPRESS)
        parser.add_argument("--embedding-dim", type=int, help=argparse.SUPPRESS)


def add_device_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda", "mps", "directml"],
        default="auto",
        help="Embedding device for model loading and indexing.",
    )


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "index":
        handle = ensure_index(args.path, options_from_args(args))
        return {
            "ok": True,
            "status": "ready",
            "was_built": handle.was_built,
            "stale_reasons": handle.stale_reasons,
            "index_dir": str(handle.index_dir),
            "manifest": handle.manifest,
        }
    if args.command == "search":
        handle = ensure_index(args.path, options_from_args(args))
        return run_search(
            handle,
            args.query,
            mode=args.mode,
            top_k=args.top_k,
            allow_model_download=args.allow_model_download,
            allow_remote_model_code=args.allow_remote_model_code,
            offline=args.offline,
            model_revision=args.model_revision,
            device=args.device,
        )
    if args.command == "grep":
        handle = ensure_index(args.path, options_from_args(args))
        return run_grep(handle, args.query, args.top_k)
    if args.command == "read":
        handle = ensure_index(args.path, options_from_args(args))
        payload = read_content(
            handle,
            page_id=args.page_id,
            chunk_id=args.chunk_id,
            neighbors=args.neighbors,
        )
        payload["index"] = {"path": str(handle.index_dir), "was_built": handle.was_built}
        return payload
    if args.command == "toc":
        handle = ensure_index(args.path, options_from_args(args))
        return run_toc(handle, args.max_depth)
    if args.command == "info":
        return run_info(args.path, options_from_args(args))
    if args.command == "diagnose":
        return diagnose(model_name=args.model)
    if args.command == "models":
        return run_models_prepare(args)
    if args.command == "audit":
        return run_audit(Path.cwd())
    raise ChmseekError("UNKNOWN_COMMAND", f"Unknown command: {args.command}")


def options_from_args(args: argparse.Namespace) -> IndexOptions:
    return IndexOptions(
        force=getattr(args, "force", False),
        index_dir=getattr(args, "index_dir", None),
        model_name=getattr(args, "model", None),
        embedding_dim=getattr(args, "embedding_dim", None),
        allow_model_download=getattr(args, "allow_model_download", False),
        allow_remote_model_code=getattr(args, "allow_remote_model_code", False),
        offline=getattr(args, "offline", False),
        model_revision=getattr(args, "model_revision", None),
        from_extracted_dir=getattr(args, "from_extracted_dir", None),
        device=getattr(args, "device", "auto"),
    )


def run_models_prepare(args: argparse.Namespace) -> dict[str, Any]:
    if args.models_command != "prepare":
        raise ChmseekError("UNKNOWN_COMMAND", f"Unknown models command: {args.models_command}")
    config = normalize_embedding_config(
        EmbeddingConfig(
            model_name=args.model,
            dimension=args.embedding_dim,
            allow_model_download=args.allow_model_download,
            allow_remote_model_code=args.allow_remote_model_code,
            offline=args.offline,
            model_revision=args.model_revision,
            device=args.device,
        )
    )
    backend = make_embedding_backend(config)
    return {
        "ok": True,
        "model": backend.model_name,
        "revision": backend.model_revision,
        "embedding_dimension": backend.dimension,
        "model_cached": is_model_cached(backend.model_name),
        "remote_model_code_allowed": backend.remote_model_code_allowed,
        "requested_device": backend.requested_device,
        "resolved_device": backend.resolved_device,
    }


def run_grep(handle, query: str, top_k: int) -> dict[str, Any]:
    conn = connect(handle.db_path)
    try:
        help_file = get_help_file(conn)
        count_info = counts(conn)
        rows = keyword_search(conn, query, top_k)
        return {
            "ok": True,
            "query": query,
            "mode": "keyword",
            "help_file": {
                "path": str(handle.chm_path),
                "title": help_file.get("title") if help_file else None,
                "fingerprint": f"sha256:{help_file['sha256']}" if help_file else None,
            },
            "index": {
                "status": "ready",
                "was_built": handle.was_built,
                "chunks": count_info["chunks"],
                "pages": count_info["pages"],
            },
            "results": [
                {
                    "rank": rank,
                    "score": round(row.score, 6),
                    "chunk_id": row.chunk_id,
                    "page_id": row.page_id,
                    "title": row.title,
                    "section_path": row.section_path,
                    "source_path": row.source_path,
                    "snippet": preview_text(row.text),
                }
                for rank, row in enumerate(rows, start=1)
            ],
        }
    finally:
        conn.close()


def run_toc(handle, max_depth: int | None) -> dict[str, Any]:
    conn = connect(handle.db_path)
    try:
        entries = get_toc_entries(conn, max_depth)
        return {
            "ok": True,
            "help_file": {"path": str(handle.chm_path)},
            "index": {"path": str(handle.index_dir), "was_built": handle.was_built},
            "toc": entries,
        }
    finally:
        conn.close()


def run_info(path: Path, options: IndexOptions) -> dict[str, Any]:
    status = index_status(path, options)
    manifest = status.get("manifest")
    embedding = (manifest or {}).get("embedding", {})
    embedding_model = embedding.get("model")
    return {
        "ok": True,
        "help_file": {
            "path": str(path),
            "fingerprint": f"sha256:{status['sha256']}",
        },
        "index": {
            "indexed": status["indexed"],
            "stale": status["stale"],
            "stale_reasons": status["stale_reasons"],
            "path": status["index_dir"],
            "page_count": (manifest or {}).get("counts", {}).get("pages"),
            "chunk_count": (manifest or {}).get("counts", {}).get("chunks"),
            "schema_version": (manifest or {}).get("schema_version"),
            "chunker_version": (manifest or {}).get("chunker_version"),
            "embedding_model": embedding_model,
            "embedding_dimension": embedding.get("dimension"),
            "embedding_revision": embedding.get("revision"),
            "model_cache_status": (
                "cached" if embedding_model and is_model_cached(embedding_model) else "not_cached"
            ),
            "requested_device": embedding.get("requested_device"),
            "resolved_device": embedding.get("resolved_device"),
            "extraction_method": (manifest or {}).get("extraction_method"),
            "remote_model_code_allowed": embedding.get("remote_model_code_allowed"),
        },
    }


def humanize(args: argparse.Namespace, payload: dict[str, Any]) -> str:
    if args.command == "audit":
        return human_audit_report(payload)
    if args.command == "models":
        return (
            f"model ready: {payload['model']} revision={payload['revision']} "
            f"device={payload['resolved_device']}"
        )
    if args.command == "diagnose":
        return "\n".join(
            [
                "chmseek diagnose",
                f"os: {payload['os']['system']} {payload['os']['release']}",
                f"python: {payload['python']['version']}",
                (
                    f"sqlite: {payload['sqlite']['version']} "
                    f"fts5={payload['sqlite']['fts5_available']}"
                ),
                f"cache: {payload['paths']['cache_dir']}",
                f"hh.exe: {payload['extractors']['hh_exe'] or 'not found'}",
                f"7z: {payload['extractors']['seven_zip'] or 'not found'}",
                (
                    f"embedding model: {payload['embedding']['model']} "
                    f"cached={payload['embedding']['model_cached']}"
                ),
            ]
        )
    if args.command in {"search", "grep"}:
        lines = [f"{payload['mode']} results for {payload['query']!r}"]
        for result in payload["results"]:
            lines.append(
                f"{result['rank']:>2}. {result['chunk_id']} {result['title']} "
                f"score={result['score']} {result['snippet']}"
            )
        return "\n".join(lines)
    if args.command == "toc":
        return "\n".join(
            f"{'  ' * entry['depth']}- {entry['title']} ({entry.get('page_id') or 'no page'})"
            for entry in payload["toc"]
        )
    if args.command == "read":
        return "\n\n".join(chunk["text"] for chunk in payload["chunks"])
    if args.command == "info":
        index = payload["index"]
        return "\n".join(
            [
                f"indexed: {index['indexed']}",
                f"stale: {index['stale']}",
                f"index path: {index['path']}",
                f"pages: {index['page_count']}",
                f"chunks: {index['chunk_count']}",
            ]
        )
    if args.command == "index":
        return f"index ready: {payload['index_dir']} built={payload['was_built']}"
    return json_dumps(payload)
