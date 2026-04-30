from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from chmseek.embeddings import (
    EmbeddingConfig,
    FakeEmbeddingBackend,
    SentenceTransformersEmbeddingBackend,
    make_embedding_backend,
)
from chmseek.errors import ChmseekError
from chmseek.extractors import copy_safe_text_tree, windows_short_path
from chmseek.indexer import IndexOptions, ensure_index
from chmseek.parser import parse_help_tree
from chmseek.reader import read_content
from chmseek.storage import connect, get_toc_entries, keyword_search
from chmseek.utils import json_dumps


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
    conn = connect(handle.db_path)
    try:
        chunk_id = keyword_search(conn, "CreateSession", 1)[0].chunk_id
    finally:
        conn.close()
    payload = read_content(handle, chunk_id=chunk_id, neighbors=1)
    assert payload["ok"] is True
    assert len(payload["chunks"]) == 3
    assert payload["chunks"][1]["chunk_id"] == chunk_id
    assert payload["chunks"][1]["images"][0]["source_path"] == "images/session-flow.png"


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
                model_name="example/private-model",
                allow_model_download=True,
                allow_remote_model_code=True,
            )
        )
    assert exc.value.code == "REMOTE_MODEL_CODE_UNPINNED"


def test_windows_short_path_uses_fallback_on_non_windows(tmp_path: Path) -> None:
    path = tmp_path / "path with spaces"
    assert windows_short_path(path) == str(path)


def test_windows_short_path_uses_short_name_when_available(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "path with spaces"
    monkeypatch.setattr("chmseek.extractors.platform.system", lambda: "Windows")
    monkeypatch.setattr("chmseek.extractors._get_windows_short_path", lambda value: "C:\\SHORT")
    assert windows_short_path(path) == "C:\\SHORT"


def test_unicode_json_is_readable() -> None:
    payload = json_dumps({"text": "Project » Settings"})
    assert "Project » Settings" in payload
    assert "\\u00bb" not in payload


def test_literal_unicode_escape_is_normalized(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    pages = parse_help_tree(handle.index_dir / "extracted")
    all_text = "\n".join(page.text for page in pages)
    assert "Project » Settings" in all_text


def test_document_embeddings_show_progress_but_queries_do_not() -> None:
    class DummyModel:
        def __init__(self) -> None:
            self.progress_values: list[bool] = []

        def encode(self, texts, **kwargs):
            self.progress_values.append(kwargs["show_progress_bar"])
            return np.ones((len(texts), 4), dtype=np.float32)

    backend = object.__new__(SentenceTransformersEmbeddingBackend)
    backend.dimension = 4
    backend._model = DummyModel()
    backend.document_prefix = "search_document: "
    backend.query_prefix = "search_query: "

    backend.embed_documents(["chunk"])
    backend.embed_query("query")

    assert backend._model.progress_values == [True, False]
