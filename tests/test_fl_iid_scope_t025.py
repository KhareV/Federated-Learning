from __future__ import annotations

import ast
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t025_production_scope_has_no_forbidden_system_imports() -> None:
    paths = [
        ROOT / "federated/client_manifest.py",
        ROOT / "federated/local_training.py",
        ROOT / "federated/fedavg_runner.py",
        ROOT / "federated/evaluation.py",
    ]
    forbidden = {"fusion", "privacy", "simulation", "deployment", "datasets"}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            else:
                continue
            assert not roots & forbidden


def test_no_non_iid_fedprox_secagg_or_calibration_transfer() -> None:
    text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "federated/client_manifest.py",
            "federated/local_training.py",
            "federated/fedavg_runner.py",
            "federated/evaluation.py",
        )
    )
    assert "evaluation.calibration" not in text
    assert "temperature_scale" not in text
    assert "FedProx" not in text
    assert "SecAgg" not in text
    assert "CLIENTS_LABEL" not in text
    assert "CLIENTS_QUANTITY" not in text
    assert "CLIENTS_FEATURE" not in text


def test_canonical_f12_remains_open_before_non_iid_manifests() -> None:
    with (ROOT / "manifests/freeze_registry_v1.csv").open(newline="") as handle:
        freezes = {row["freeze_id"]: row for row in csv.DictReader(handle)}
    assert freezes["F12"]["version_id"] == "FL_CONFIG_V1"
    assert freezes["F12"]["current_status"] == "NOT_FROZEN"
    assert not (ROOT / "manifests/clients/CLIENTS_LABEL_V1.csv").exists()
    assert not (ROOT / "manifests/clients/CLIENTS_QUANTITY_V1.csv").exists()
    assert not (ROOT / "manifests/clients/CLIENTS_FEATURE_V1.csv").exists()
