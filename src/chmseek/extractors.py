from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .constants import ALLOWED_EXTRACTED_EXTENSIONS
from .errors import ChmseekError
from .utils import ensure_within, safe_relative_posix


@dataclass(frozen=True)
class ExtractionResult:
    root: Path
    method: str
    files: list[Path]


class Extractor:
    method = "base"

    def extract(self, source: Path, output_dir: Path) -> ExtractionResult:
        raise NotImplementedError


class ExtractedDirExtractor(Extractor):
    method = "extracted-dir"

    def __init__(self, extracted_dir: Path) -> None:
        self.extracted_dir = extracted_dir

    def extract(self, source: Path, output_dir: Path) -> ExtractionResult:
        if not self.extracted_dir.exists() or not self.extracted_dir.is_dir():
            raise ChmseekError(
                "EXTRACTED_DIR_NOT_FOUND",
                f"Extracted help directory does not exist: {self.extracted_dir}",
                ["Pass a directory containing already-decompiled CHM help files."],
            )
        _prepare_output_dir(output_dir)
        copied = copy_safe_text_tree(self.extracted_dir, output_dir)
        if not copied:
            raise ChmseekError(
                "NO_PARSEABLE_HELP_CONTENT",
                "The extracted directory did not contain parseable help content.",
                ["Expected .htm, .html, .xhtml, .txt, .hhc, or .hhk files."],
            )
        return ExtractionResult(output_dir, self.method, copied)


class WindowsHhExtractor(Extractor):
    method = "windows-hh"

    def __init__(self, timeout_seconds: int = 120) -> None:
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def available() -> bool:
        return platform.system() == "Windows" and shutil.which("hh.exe") is not None

    def extract(self, source: Path, output_dir: Path) -> ExtractionResult:
        if platform.system() != "Windows":
            raise ChmseekError(
                "EXTRACTOR_UNAVAILABLE",
                "Windows HTML Help extraction is only available on Windows.",
                ["Use --from-extracted-dir for tests or run on Windows with hh.exe available."],
            )
        hh = shutil.which("hh.exe")
        if hh is None:
            raise ChmseekError(
                "HH_EXE_NOT_FOUND",
                "Could not find hh.exe on PATH.",
                ["Install/use Windows HTML Help, or pass --from-extracted-dir."],
            )
        _prepare_output_dir(output_dir)
        try:
            completed = subprocess.run(
                [hh, "-decompile", str(output_dir), str(source)],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ChmseekError(
                "EXTRACTION_TIMEOUT",
                f"Timed out while decompiling {source}.",
                ["Try again with a smaller CHM or inspect the file manually in a sandbox."],
            ) from exc
        if completed.returncode != 0:
            raise ChmseekError(
                "EXTRACTION_FAILED",
                f"hh.exe failed while decompiling {source}.",
                [completed.stderr.strip() or completed.stdout.strip() or "No extractor output."],
            )
        files = validate_extracted_tree(output_dir)
        return ExtractionResult(output_dir, self.method, files)


class SevenZipExtractor(Extractor):
    method = "sevenzip"

    def __init__(self, timeout_seconds: int = 120) -> None:
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def available() -> bool:
        return shutil.which("7z") is not None

    def extract(self, source: Path, output_dir: Path) -> ExtractionResult:
        seven_zip = shutil.which("7z")
        if seven_zip is None:
            raise ChmseekError(
                "SEVENZIP_NOT_FOUND",
                "Could not find 7z on PATH.",
                ["Use Windows hh.exe or pass --from-extracted-dir."],
            )
        _prepare_output_dir(output_dir)
        try:
            completed = subprocess.run(
                [seven_zip, "x", f"-o{output_dir}", str(source)],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ChmseekError(
                "EXTRACTION_TIMEOUT",
                f"Timed out while extracting {source} with 7z.",
                ["Use --from-extracted-dir or inspect the CHM in a sandbox."],
            ) from exc
        if completed.returncode != 0:
            raise ChmseekError(
                "EXTRACTION_FAILED",
                f"7z failed while extracting {source}.",
                [completed.stderr.strip() or completed.stdout.strip() or "No extractor output."],
            )
        files = validate_extracted_tree(output_dir)
        return ExtractionResult(output_dir, self.method, files)


def choose_extractor(from_extracted_dir: Path | None = None) -> Extractor:
    if from_extracted_dir is not None:
        return ExtractedDirExtractor(from_extracted_dir)
    if WindowsHhExtractor.available():
        return WindowsHhExtractor()
    if SevenZipExtractor.available():
        return SevenZipExtractor()
    raise ChmseekError(
        "EXTRACTOR_UNAVAILABLE",
        "No CHM extractor is available.",
        [
            "On Windows, ensure hh.exe is available.",
            "For tests or pre-extracted help files, pass --from-extracted-dir.",
        ],
    )


def validate_extracted_tree(root: Path) -> list[Path]:
    root = root.resolve()
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        resolved = path.resolve()
        if not resolved.exists():
            continue
        if not _is_within(resolved, root):
            raise ChmseekError(
                "UNSAFE_EXTRACTED_PATH",
                f"Extracted path escapes the extraction directory: {path}",
                ["CHM files are untrusted; unsafe symlinks and path traversal are rejected."],
            )
        if not resolved.is_file():
            continue
        if resolved.suffix.lower() in ALLOWED_EXTRACTED_EXTENSIONS:
            files.append(resolved)
    return files


def copy_safe_text_tree(source_root: Path, output_root: Path) -> list[Path]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    copied: list[Path] = []
    for source_path in sorted(source_root.rglob("*")):
        resolved_source = source_path.resolve()
        if not resolved_source.exists():
            continue
        if not _is_within(resolved_source, source_root):
            raise ChmseekError(
                "UNSAFE_EXTRACTED_PATH",
                f"Extracted path escapes the source directory: {source_path}",
                ["Remove unsafe symlinks before indexing."],
            )
        if not resolved_source.is_file():
            continue
        if resolved_source.suffix.lower() not in ALLOWED_EXTRACTED_EXTENSIONS:
            continue
        rel = safe_relative_posix(resolved_source, source_root)
        dest = output_root / rel
        ensure_within(dest, output_root, code="EXTRACTED_FILE_ESCAPE")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved_source, dest)
        copied.append(dest.resolve())
    return copied


def _prepare_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ChmseekError(
                "INDEX_PATH_CONFLICT",
                f"Extraction output path exists and is not a directory: {output_dir}",
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
