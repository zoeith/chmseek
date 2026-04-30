from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cli(args: list[str], cli_env: dict[str, str]):
    return subprocess.run(
        [sys.executable, "-m", "chmseek", *args],
        check=False,
        capture_output=True,
        text=True,
        env=cli_env,
        timeout=30,
    )


def test_cli_index_search_read_toc_info(
    tmp_path: Path, fixture_chm: Path, extracted_help: Path, cli_env: dict[str, str]
) -> None:
    index_dir = tmp_path / "index"
    index = run_cli(
        [
            "index",
            str(fixture_chm),
            "--from-extracted-dir",
            str(extracted_help),
            "--index-dir",
            str(index_dir),
            "--model",
            "fake",
            "--embedding-dim",
            "128",
            "--force",
            "--json",
        ],
        cli_env,
    )
    assert index.returncode == 0, index.stderr + index.stdout
    assert json.loads(index.stdout)["ok"] is True

    search = run_cli(
        [
            "search",
            str(fixture_chm),
            "CreateSession",
            "--index-dir",
            str(index_dir),
            "--json",
        ],
        cli_env,
    )
    assert search.returncode == 0, search.stderr + search.stdout
    search_payload = json.loads(search.stdout)
    assert search_payload["results"]
    chunk_id = search_payload["results"][0]["chunk_id"]

    read = run_cli(
        [
            "read",
            str(fixture_chm),
            "--chunk-id",
            chunk_id,
            "--neighbors",
            "1",
            "--index-dir",
            str(index_dir),
            "--json",
        ],
        cli_env,
    )
    assert read.returncode == 0, read.stderr + read.stdout
    assert json.loads(read.stdout)["chunks"]

    toc = run_cli(
        ["toc", str(fixture_chm), "--index-dir", str(index_dir), "--json"],
        cli_env,
    )
    assert toc.returncode == 0, toc.stderr + toc.stdout
    assert json.loads(toc.stdout)["toc"]

    info = run_cli(
        ["info", str(fixture_chm), "--index-dir", str(index_dir), "--json"],
        cli_env,
    )
    assert info.returncode == 0, info.stderr + info.stdout
    assert json.loads(info.stdout)["index"]["indexed"] is True


def test_cli_json_error_for_missing_file(tmp_path: Path, cli_env: dict[str, str]) -> None:
    missing = tmp_path / "missing.chm"
    result = run_cli(["index", str(missing), "--json"], cli_env)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "FILE_NOT_FOUND"


def test_diagnose_and_audit_commands(cli_env: dict[str, str]) -> None:
    diagnose = run_cli(["diagnose", "--json"], cli_env)
    assert diagnose.returncode == 0, diagnose.stderr + diagnose.stdout
    assert json.loads(diagnose.stdout)["sqlite"]["fts5_available"] is True

    audit = run_cli(["audit", "--json"], cli_env)
    assert audit.returncode == 0
    payload = json.loads(audit.stdout)
    assert "source_scan" in payload
    assert "lockfiles" in payload
    assert payload["dependency_audit"]["status"] == "skipped"


def test_models_prepare_with_fake_backend(cli_env: dict[str, str]) -> None:
    result = run_cli(
        [
            "models",
            "prepare",
            "--model",
            "fake",
            "--embedding-dim",
            "32",
            "--json",
        ],
        cli_env,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["model"] == "fake"
    assert payload["resolved_device"] == "cpu"
