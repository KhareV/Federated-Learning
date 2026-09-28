#!/usr/bin/env python3
"""Generate non-secret T001 host evidence and the non-circular artifact hash manifest."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

from nhm.hashing import hash_file
from nhm.reproducibility import capture_execution_identity, runtime_version_line

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t001"


def command_version(*args: str) -> str | None:
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    python_path = REPORT_DIR / "python_version.txt"
    python_path.write_text(runtime_version_line() + "\n", encoding="utf-8")

    identity = capture_execution_identity(
        ROOT,
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=REPORT_DIR / "dependencies.txt",
    )
    environment = {
        **identity,
        "architecture": platform.machine(),
        "git_version": command_version("git", "--version"),
        "runtime_requirement": "Python 3.11.x",
        "runtime_compliance": platform.python_version_tuple()[:2] == ("3", "11"),
        "runtime_note": (
            None
            if platform.python_version_tuple()[:2] == ("3", "11")
            else "VERIFICATION_REQUIRED: Python 3.11 unavailable; local T001 used closest Python."
        ),
    }
    (REPORT_DIR / "environment.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    artifacts = [
        ROOT / "configs/base.yaml",
        ROOT / "contracts/run_manifest_v1.schema.json",
        ROOT / "tests/fixtures/mongodb_observed_v0.json",
        ROOT / "docs/SOURCE_AUTHORITY.md",
        REPORT_DIR / "smoke_report.json",
        REPORT_DIR / "run_manifest.json",
        REPORT_DIR / "dependencies.txt",
        REPORT_DIR / "python_version.txt",
        REPORT_DIR / "environment.json",
    ]
    closure = REPORT_DIR / "closure_verification.json"
    if closure.exists():
        artifacts.append(closure)
    missing = [str(path) for path in artifacts if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing evidence: {missing}")
    payload = {
        "manifest_version": "1.0",
        "algorithm": "sha256",
        "rule": "exact file bytes; this manifest excludes itself to avoid a circular digest",
        "artifacts": {
            str(path.relative_to(ROOT)): hash_file(path) for path in sorted(artifacts)
        },
    }
    (REPORT_DIR / "artifact_hashes.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("T001 evidence: generated")


if __name__ == "__main__":
    main()
