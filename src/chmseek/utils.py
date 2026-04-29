from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .constants import APP_NAME
from .errors import ChmseekError


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        Path(tmp_name).replace(path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def ensure_within(path: Path, root: Path, *, code: str = "PATH_OUTSIDE_INDEX") -> Path:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if not is_relative_to(resolved_path, resolved_root):
        raise ChmseekError(
            code,
            f"Refusing path outside managed directory: {path}",
            [f"Managed directory: {resolved_root}"],
        )
    return resolved_path


def safe_relative_posix(path: Path, root: Path) -> str:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if not is_relative_to(resolved_path, resolved_root):
        raise ChmseekError(
            "UNSAFE_EXTRACTED_PATH",
            f"Extracted path escapes the extraction directory: {path}",
            ["CHM files are untrusted; remove path traversal or unsafe symlinks."],
        )
    return resolved_path.relative_to(resolved_root).as_posix()


def cache_root() -> Path:
    if platform.system() == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / APP_NAME
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".cache" / APP_NAME


def default_index_dir(fingerprint: str) -> Path:
    return cache_root() / "indexes" / fingerprint


def validate_chm_path(path: Path) -> None:
    if not path.exists():
        from .errors import file_not_found

        raise file_not_found(path)
    if path.suffix.lower() != ".chm":
        raise ChmseekError(
            "NOT_CHM_FILE",
            f"Expected a .chm file path, got: {path}",
            ["Pass the original .chm file even when using --from-extracted-dir."],
        )


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    collapsed: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                collapsed.append("")
            blank = True
            continue
        collapsed.append(line)
        blank = False
    return "\n".join(collapsed).strip()


def word_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_][A-Za-z0-9_.:-]*", text)


def preview_text(text: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."


def source_uri(chm_path: Path, source_path: str, anchor: str | None = None) -> str:
    suffix = f"#{anchor}" if anchor else ""
    return f"chm://{chm_path.name}/{source_path}{suffix}"
