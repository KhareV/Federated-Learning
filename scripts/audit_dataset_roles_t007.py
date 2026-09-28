#!/usr/bin/env python3
"""Audit the locked dataset-role registry and emit machine-readable evidence.

Confirms INCART/NSTDB/BIDMC role restrictions are declared correctly and that no dataset
loader imports training/evaluation/model code (a structural guard against premature use).
Offline; requires no acquired dataset.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLES_PATH = ROOT / "manifests/datasets/dataset_roles_v1.yaml"
REPORT_DIR = ROOT / "reports/t007"

FORBIDDEN_IMPORT_PREFIXES = ("models", "training", "evaluation", "federated", "deployment")
DATASET_LOADER_MODULES = ("mitdb.py", "incart.py", "nstdb.py", "bidmc.py", "physionet.py")


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


def main() -> None:
    roles = yaml.safe_load(ROLES_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    expected_datasets = {"MITDB", "INCART", "NSTDB", "BIDMC"}
    if set(roles) != expected_datasets:
        errors.append(f"dataset role registry must declare exactly {expected_datasets}")

    incart = roles.get("INCART", {})
    if not (
        incart.get("external_evaluation_only") is True
        and incart.get("allowed_for_training") is False
        and incart.get("allowed_for_model_selection") is False
        and incart.get("allowed_for_calibration") is False
    ):
        errors.append("INCART role restrictions are not fully locked")

    nstdb = roles.get("NSTDB", {})
    if not (
        nstdb.get("robustness_only") is True and nstdb.get("allowed_for_training") is False
    ):
        errors.append("NSTDB role restrictions are not fully locked")

    bidmc = roles.get("BIDMC", {})
    if not (
        bidmc.get("multimodal_engineering_only") is True
        and bidmc.get("allowed_for_arrhythmia_training") is False
    ):
        errors.append("BIDMC role restrictions are not fully locked")

    mitdb = roles.get("MITDB", {})
    core_training = [name for name, role in roles.items() if role.get("allowed_for_training")]
    if core_training != ["MITDB"] or not mitdb.get("allowed_for_training"):
        errors.append("MITDB must remain the only dataset marked allowed_for_training")

    loader_import_findings: dict[str, list[str]] = {}
    for module_name in DATASET_LOADER_MODULES:
        path = ROOT / "datasets" / module_name
        if not path.exists():
            errors.append(f"expected dataset loader module missing: {module_name}")
            continue
        hits = _forbidden_imports(path)
        if hits:
            errors.append(f"{module_name} imports role-violating modules: {hits}")
        loader_import_findings[module_name] = hits

    status = "PASS" if not errors else "FAIL"
    report: dict[str, Any] = {
        "roles": roles,
        "loader_import_findings": loader_import_findings,
        "errors": errors,
        "status": status,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORT_DIR / "dataset_role_audit.json"
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)

    print(f"Dataset role audit: {status}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
