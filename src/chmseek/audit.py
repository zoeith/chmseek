from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import tomllib


def run_audit(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    lockfiles = [root / "requirements.lock", root / "requirements-dev.lock"]
    lockfile_status = {path.name: path.exists() for path in lockfiles}
    pins = check_dependency_pins(root / "pyproject.toml")
    source_findings = scan_source(root / "src")
    dependency_audit = run_dependency_audit(root)
    ok = all(lockfile_status.values()) and pins["ok"] and not source_findings["findings"]
    if dependency_audit["status"] == "failed":
        ok = False
    return {
        "ok": ok,
        "lockfiles": lockfile_status,
        "dependency_pins": pins,
        "source_scan": source_findings,
        "dependency_audit": dependency_audit,
    }


def check_dependency_pins(pyproject: Path) -> dict[str, Any]:
    if not pyproject.exists():
        return {"ok": False, "missing": str(pyproject), "unpinned": []}
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    dependencies = list(project.get("dependencies", []))
    optional = project.get("optional-dependencies", {})
    for group in optional.values():
        dependencies.extend(group)
    unpinned = [dep for dep in dependencies if "==" not in dep]
    return {"ok": not unpinned, "unpinned": unpinned, "checked": dependencies}


def scan_source(src_dir: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if not src_dir.exists():
        return {"ok": False, "findings": [{"path": str(src_dir), "pattern": "missing"}]}
    patterns = [
        "shell" + "=True",
        "eval" + "(",
        "exec" + "(",
        "pickle" + ".load",
        "extractall" + "(",
    ]
    for path in sorted(src_dir.rglob("*.py")):
        if path.name == "audit.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in patterns:
                if pattern in line:
                    findings.append({"path": str(path), "line": lineno, "pattern": pattern})
    return {"ok": not findings, "findings": findings}


def run_dependency_audit(root: Path) -> dict[str, Any]:
    executable = shutil.which("pip-audit")
    if executable is None:
        return {
            "status": "skipped",
            "message": "pip-audit is not installed.",
            "hints": ["Install development dependencies or use the Conda environment."],
        }
    requirements = root / "requirements.lock"
    if not requirements.exists():
        return {
            "status": "skipped",
            "message": "requirements.lock is missing.",
        }
    try:
        completed = subprocess.run(
            [
                executable,
                "--progress-spinner",
                "off",
                "--format",
                "json",
                "-r",
                str(requirements),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "message": "pip-audit timed out."}
    except OSError as exc:
        return {"status": "failed", "message": f"pip-audit could not run: {exc}"}
    if completed.returncode == 0:
        return {"status": "passed", "output": completed.stdout[:4000]}
    return {
        "status": "failed",
        "returncode": completed.returncode,
        "output": (completed.stdout + completed.stderr)[:4000],
    }


def human_audit_report(payload: dict[str, Any]) -> str:
    lines = ["chmseek audit"]
    lines.append(f"overall: {'ok' if payload['ok'] else 'needs attention'}")
    lines.append("lockfiles:")
    for name, exists in payload["lockfiles"].items():
        lines.append(f"  {name}: {'present' if exists else 'missing'}")
    pins = payload["dependency_pins"]
    lines.append(f"dependency pins: {'ok' if pins['ok'] else 'unpinned dependencies found'}")
    for dep in pins.get("unpinned", []):
        lines.append(f"  unpinned: {dep}")
    scan = payload["source_scan"]
    lines.append(f"source scan: {'ok' if scan['ok'] else 'findings'}")
    for finding in scan.get("findings", []):
        lines.append(f"  {finding['path']}:{finding.get('line', '?')} {finding['pattern']}")
    dep_audit = payload["dependency_audit"]
    lines.append(f"pip-audit: {dep_audit['status']}")
    if dep_audit.get("message"):
        lines.append(f"  {dep_audit['message']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import json

    json.dump(run_audit(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
