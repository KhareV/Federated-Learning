#!/usr/bin/env python3
"""Audit that the T009 split builder is independent of any model/result-driven input.

Structural guard (v2.2 Section 11 / T009 execution instructions Section 40): the split
builder must not import model, training, evaluation, calibration, or federated code, and must
not read from any report directory that could carry model or evaluation results. Offline;
static source analysis only.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t009"

AUDITED_MODULES = ("datasets/grouping.py", "scripts/build_mitdb_split_t009.py")
FORBIDDEN_IMPORT_PREFIXES = ("models", "training", "evaluation", "calibration", "federated")
FORBIDDEN_PATH_SUBSTRINGS = (
    "reports/models/",
    "reports/evaluation/",
    "reports/t020/",
    "reports/calibration/",
    "reports/federated/",
    "reports/baselines/",
)


def _forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORT_PREFIXES:
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in FORBIDDEN_IMPORT_PREFIXES:
                hits.append(module)
    return hits


def _forbidden_paths(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [substring for substring in FORBIDDEN_PATH_SUBSTRINGS if substring in text]


def main() -> None:
    errors: list[str] = []
    findings: dict[str, dict[str, list[str]]] = {}

    for relative in AUDITED_MODULES:
        path = ROOT / relative
        if not path.exists():
            errors.append(f"expected split-builder module missing: {relative}")
            continue
        import_hits = _forbidden_imports(path)
        path_hits = _forbidden_paths(path)
        findings[relative] = {"forbidden_imports": import_hits, "forbidden_path_strings": path_hits}
        if import_hits:
            errors.append(f"{relative} imports result-driven modules: {import_hits}")
        if path_hits:
            errors.append(f"{relative} references result-driven report paths: {path_hits}")

    status = "PASS" if not errors else "FAIL"
    report: dict[str, Any] = {
        "audited_modules": list(AUDITED_MODULES),
        "forbidden_import_prefixes": list(FORBIDDEN_IMPORT_PREFIXES),
        "forbidden_path_substrings": list(FORBIDDEN_PATH_SUBSTRINGS),
        "findings": findings,
        "errors": errors,
        "status": status,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORT_DIR / "split_independence_audit.json"
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)

    print(f"T009 split independence audit: {status}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
