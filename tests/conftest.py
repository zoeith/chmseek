from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = ROOT / "tests" / "fixtures"

sys.path.insert(0, str(SRC))


@pytest.fixture
def fixture_chm() -> Path:
    return FIXTURES / "fake.chm"


@pytest.fixture
def extracted_help() -> Path:
    return FIXTURES / "extracted_help"


@pytest.fixture
def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["CHMSEEK_EMBEDDING_BACKEND"] = "fake"
    env["CHMSEEK_SKIP_PIP_AUDIT"] = "1"
    return env
