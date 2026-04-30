from __future__ import annotations

from pathlib import Path

from chmseek import search as search_module
from chmseek.constants import DEFAULT_MODEL, DEFAULT_MODEL_REVISION
from chmseek.embeddings import EmbeddingConfig, make_embedding_backend, normalize_embedding_config
from chmseek.indexer import IndexOptions, ensure_index, index_status
from chmseek.search import run_search
from chmseek.storage import connect, counts, get_toc_entries, keyword_search


def build_fixture_index(tmp_path: Path, fixture_chm: Path, extracted_help: Path):
    return ensure_index(
        fixture_chm,
        IndexOptions(
            index_dir=tmp_path / "index",
            model_name="fake",
            embedding_dim=128,
            from_extracted_dir=extracted_help,
            force=True,
        ),
    )


def test_index_from_extracted_dir(tmp_path: Path, fixture_chm: Path, extracted_help: Path) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    assert handle.was_built is True
    assert (handle.index_dir / "manifest.json").exists()
    assert (handle.index_dir / "index.sqlite").exists()
    conn = connect(handle.db_path)
    try:
        count_info = counts(conn)
    finally:
        conn.close()
    assert count_info["pages"] == 6
    assert count_info["chunks"] >= 6
    assert count_info["images"] == 1


def test_keyword_search_finds_exact_symbol(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    conn = connect(handle.db_path)
    try:
        rows = keyword_search(conn, "CreateSession", 5)
    finally:
        conn.close()
    assert rows
    assert rows[0].title == "Session API"
    assert "CreateSession" in rows[0].text


def test_hybrid_search_finds_conceptual_workflow(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    payload = run_search(
        handle,
        "how do I set up a project before running the analysis?",
        mode="hybrid",
        top_k=3,
    )
    assert payload["ok"] is True
    titles = [result["title"] for result in payload["results"]]
    assert "Analysis Workflow Tutorial" in titles or "Project Concepts" in titles


def test_search_json_schema_is_stable(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    payload = run_search(handle, "HRESULT", mode="hybrid", top_k=2)
    assert set(payload) >= {"ok", "query", "mode", "help_file", "index", "results"}
    result = payload["results"][0]
    assert set(result) >= {
        "rank",
        "score",
        "semantic_score",
        "keyword_score",
        "chunk_id",
        "page_id",
        "title",
        "section_path",
        "source_path",
        "source_uri",
        "snippet",
        "text_preview",
        "images",
        "neighbor_command",
    }


def test_search_results_include_image_metadata(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    payload = run_search(handle, "CreateSession", mode="hybrid", top_k=1)
    image = payload["results"][0]["images"][0]
    assert image["source_path"] == "images/session-flow.png"
    assert image["alt"] == "Session lifecycle diagram"
    assert image["asset_uri"].endswith("/images/session-flow.png")


def test_toc_parsing_works_with_hhc(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    conn = connect(handle.db_path)
    try:
        entries = get_toc_entries(conn)
    finally:
        conn.close()
    assert any(entry["title"] == "Workflow Tutorial" and entry["depth"] == 1 for entry in entries)
    assert any(entry["title"] == "Session API" and entry["page_id"] for entry in entries)


def test_stale_detection_for_embedding_changes(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    status = index_status(
        fixture_chm,
        IndexOptions(index_dir=handle.index_dir, model_name="fake", embedding_dim=64),
    )
    assert status["stale"] is True
    assert "embedding_dimension" in status["stale_reasons"]
    status = index_status(
        fixture_chm,
        IndexOptions(index_dir=handle.index_dir, model_name="other-model", embedding_dim=128),
    )
    assert "embedding_model" in status["stale_reasons"]
    status = index_status(
        fixture_chm,
        IndexOptions(
            index_dir=handle.index_dir,
            model_name="fake",
            embedding_dim=128,
            device="cpu",
        ),
    )
    assert "embedding_device" in status["stale_reasons"]


def test_default_nomic_config_uses_pinned_revision() -> None:
    config = normalize_embedding_config(EmbeddingConfig(model_name=DEFAULT_MODEL))
    assert config.model_revision == DEFAULT_MODEL_REVISION


def test_search_reuses_manifest_embedding_policy(
    monkeypatch, tmp_path: Path, fixture_chm: Path, extracted_help: Path
) -> None:
    handle = build_fixture_index(tmp_path, fixture_chm, extracted_help)
    handle.manifest["embedding"]["revision"] = "manifest-revision"
    handle.manifest["embedding"]["remote_model_code_allowed"] = True
    handle.manifest["embedding"]["requested_device"] = "cpu"
    captured: dict[str, EmbeddingConfig] = {}

    def fake_backend(config: EmbeddingConfig):
        captured["config"] = config
        return make_embedding_backend(EmbeddingConfig(model_name="fake", dimension=128))

    monkeypatch.setattr(search_module, "make_embedding_backend", fake_backend)
    run_search(handle, "CreateSession", mode="semantic", top_k=1)

    config = captured["config"]
    assert config.model_revision == "manifest-revision"
    assert config.allow_remote_model_code is True
    assert config.device == "cpu"
