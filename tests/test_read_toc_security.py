from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from chmseek.embeddings import EmbeddingConfig, FakeEmbeddingBackend, make_embedding_backend
from chmseek.errors import ChmseekError
from chmseek.extractors import copy_safe_text_tree
from chmseek.indexer import IndexOptions, ensure_index
from chmseek.parser import parse_help_tree
from chmseek.reader import read_content
from chmseek.storage import connect, get_toc_entries, keyword_search


def build_fixture_index(tmp_path: Path, fixture_chm: Path, extracted_help: Path):
    return ensure_index(
        fixture_chm,
        IndexOptions(
            index_dir=tmp_path / "index",
            model_name="fake",
            embedding_dim=96,
            from_extracted_dir=extracted_help,
            force=True,
        ),
    )


def test_read_chunk_with_neighbors(tmp_path: Path, fixture_chm: Path, extracted_help: Path) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    payload = read_content(handle, chunk_id="ch_000003", neighbors=1)
    assert payload["ok"] is True
    assert len(payload["chunks"]) == 3
    assert payload["chunks"][1]["chunk_id"] == "ch_000003"


def test_synthetic_toc_when_hhc_absent(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    copied = tmp_path / "help_without_toc"
    shutil.copytree(extracted_help, copied)
    (copied / "toc.hhc").unlink()
    handle = ensure_index(
        fixture_chm,
        IndexOptions(
            index_dir=tmp_path / "index",
            model_name="fake",
            embedding_dim=96,
            from_extracted_dir=copied,
            force=True,
        ),
    )
    conn = connect(handle.db_path)
    try:
        entries = get_toc_entries(conn)
    finally:
        conn.close()
    assert any(entry["title"] == "Analysis Workflow Tutorial" for entry in entries)


def test_script_object_iframe_content_is_ignored(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    pages = parse_help_tree(handle.index_dir / "extracted")
    all_text = "\n".join(page.text for page in pages)
    assert "window.location" not in all_text
    assert "unsafe ActiveX content" not in all_text
    conn = connect(handle.db_path)
    try:
        assert keyword_search(conn, "ActiveX", 5) == []
    finally:
        conn.close()


def test_unsafe_symlink_escape_is_rejected(tmp_path: Path) -> None:
    if sys.platform.startswith("win"):
        pytest.skip("Symlink permissions vary on Windows.")
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.html"
    outside.write_text("<html><body>outside</body></html>", encoding="utf-8")
    (source / "escape.html").symlink_to(outside)
    with pytest.raises(ChmseekError) as exc:
        copy_safe_text_tree(source, tmp_path / "out")
    assert exc.value.code == "UNSAFE_EXTRACTED_PATH"


def test_embedding_backend_applies_required_prefixes() -> None:
    backend = FakeEmbeddingBackend(32)
    backend.embed_documents(["chunk text"])
    backend.embed_query("query text")
    assert backend.last_document_inputs == ["search_document: chunk text"]
    assert backend.last_query_input == "search_query: query text"


def test_remote_model_code_requires_pinned_revision() -> None:
    with pytest.raises(ChmseekError) as exc:
        make_embedding_backend(
            EmbeddingConfig(
                model_name="nomic-ai/nomic-embed-text-v1.5",
                allow_model_download=True,
                allow_remote_model_code=True,
            )
        )
    assert exc.value.code == "REMOTE_MODEL_CODE_UNPINNED"
