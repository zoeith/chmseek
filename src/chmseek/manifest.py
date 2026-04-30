from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import CHUNKER_VERSION, DOCUMENT_PREFIX, QUERY_PREFIX, SCHEMA_VERSION
from .embeddings import EmbeddingConfig
from .utils import read_json

MANIFEST_NAME = "manifest.json"


def manifest_path(index_dir: Path) -> Path:
    return index_dir / MANIFEST_NAME


def load_manifest(index_dir: Path) -> dict[str, Any] | None:
    return read_json(manifest_path(index_dir))


def is_manifest_stale(
    manifest: dict[str, Any] | None,
    *,
    sha256: str,
    embedding_config: EmbeddingConfig,
) -> tuple[bool, list[str]]:
    if manifest is None:
        return True, ["missing"]
    reasons: list[str] = []
    file_info = manifest.get("file", {})
    embedding = manifest.get("embedding", {})
    if manifest.get("schema_version") != SCHEMA_VERSION:
        reasons.append("schema_version")
    if file_info.get("sha256") != sha256:
        reasons.append("sha256")
    if embedding.get("model") != embedding_config.model_name:
        reasons.append("embedding_model")
    if int(embedding.get("dimension", 0)) != embedding_config.dimension:
        reasons.append("embedding_dimension")
    if embedding.get("revision") != embedding_config.model_revision:
        reasons.append("embedding_revision")
    if embedding.get("requested_device", "auto") != embedding_config.device:
        reasons.append("embedding_device")
    if embedding.get("document_prefix") != DOCUMENT_PREFIX:
        reasons.append("embedding_document_prefix")
    if embedding.get("query_prefix") != QUERY_PREFIX:
        reasons.append("embedding_query_prefix")
    if manifest.get("chunker_version") != CHUNKER_VERSION:
        reasons.append("chunker_version")
    return bool(reasons), reasons
