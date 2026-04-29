from __future__ import annotations

import platform
import shutil
import sqlite3
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from .embeddings import default_model_name, is_model_cached
from .storage import check_fts5_available
from .utils import cache_root


def diagnose(*, model_name: str | None = None) -> dict[str, Any]:
    model = model_name or default_model_name()
    return {
        "ok": True,
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
        },
        "sqlite": {
            "version": sqlite3.sqlite_version,
            "fts5_available": check_fts5_available(),
        },
        "paths": {
            "cache_dir": str(cache_root()),
            "cwd": str(Path.cwd()),
        },
        "extractors": {
            "hh_exe": shutil.which("hh.exe"),
            "seven_zip": shutil.which("7z"),
        },
        "embedding": {
            "model": model,
            "model_cached": is_model_cached(model),
            "backend": "fake" if model == "fake" else "sentence-transformers",
            "backend_importable": model == "fake" or find_spec("sentence_transformers") is not None,
        },
        "audit": {
            "pip_audit": shutil.which("pip-audit"),
            "ruff": shutil.which("ruff"),
        },
    }
