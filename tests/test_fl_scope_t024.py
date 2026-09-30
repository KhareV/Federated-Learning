from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_federated_scope_and_no_future_work() -> None:
    production = [
        ROOT / "federated/aggregation.py",
        ROOT / "federated/model_adapter.py",
        ROOT / "federated/client_app.py",
        ROOT / "federated/server_app.py",
    ]
    forbidden_import_roots = {"datasets", "evaluation", "fusion", "privacy", "simulation"}
    text = "\n".join(path.read_text(encoding="utf-8") for path in production)
    assert "CLIENTS_IID_V1" not in text
    assert "FedProx" not in text
    assert "SecAgg" not in text
    assert "differential privacy" not in text.lower()
    for path in production:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            else:
                continue
            assert not roots & forbidden_import_roots


def test_t024_scope_audit_records_no_real_client_manifest_at_t024() -> None:
    import json

    audit = json.loads((ROOT / "reports/t024/protocol_audit.json").read_text())
    assert audit["real_MITDB_client_construction"] is False
    assert (ROOT / "manifests/clients/CLIENTS_IID_V1.csv").exists()
    assert not (ROOT / "configs/fedavg_v1.yaml").exists()
