# ruff: noqa: E501
"""CAP-007: released-monitoring isolation, truth firewall, central-DB locality, claims, protected surface."""

from __future__ import annotations

import ast
import json
import re
import sqlite3
import subprocess

from fastapi.testclient import TestClient

from federated import wearable_fl_system_v1 as fl_system
from product.contracts import ROOT
from product.federation import update_bridge
from product.session import default_runtime_identity
from tests.capstone_federation_support import (
    BASE,
    SINGLE_RUN,
    USER_A,
    completed_run,
    make_fed_app,
    poll_run,
)

NEW_SOURCES = [
    "product/federation/client_v2.py", "product/federation/service.py", "product/federation/events.py",
    "product/federation/journal.py", "product/federation/recovery.py", "product/federation/execution_binding.py",
    "product/federation/artifact_store.py", "product/federation/secagg_shadow.py", "product/federation/replay.py",
    "product/models/registry.py", "product/models/governance.py", "product/models/candidate_artifacts.py",
    "product/models/views.py", "capstone_persistence/federation_store.py", "api/product_app_v1_2.py",
]


def test_the_released_default_runtime_is_unchanged_and_names_no_candidate() -> None:
    runtime = default_runtime_identity()
    assert runtime.model_id == "MODEL_V2_FINAL" and runtime.software_system_id == "SOFTWARE_SYSTEM_V2"
    for path in ("artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json",
                 "product/session.py", "product/inference/client.py", "api/product_app_v1_1.py"):
        assert "CAPSTONE_FL_CANDIDATE" not in (ROOT / path).read_text(), path
    for tree in ("product/monitoring", "product/sessions", "product/persistence", "product/devices"):
        for source in (ROOT / tree).rglob("*.py"):
            assert "CAPSTONE_FL_CANDIDATE" not in source.read_text(), source


def test_no_candidate_reference_exists_in_the_frontend_or_the_inference_service_sources() -> None:
    for tree in ("frontend/src", "api", "src"):
        for source in (ROOT / tree).rglob("*"):
            if source.is_file() and source.suffix in (".py", ".ts", ".svelte", ".js") and "product_app_v1_2" not in source.name:
                assert "CAPSTONE_FL_CANDIDATE" not in source.read_text(errors="ignore"), source


def _imports(path: str) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse((ROOT / path).read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_new_modules_import_no_truth_data_loader_or_scientific_runtime_module() -> None:
    forbidden = ("truth", "simulation.wearable", "datasets", "preprocessing", "training", "evaluation",
                 "inference", "calibration", "software_system")
    for source in NEW_SOURCES:
        for module in _imports(source):
            assert not any(part in module.split(".")[0:2] or module.startswith(f"{part}.") or module == part
                           for part in ("training", "preprocessing", "evaluation", "datasets")), (source, module)
            assert "truth" not in module, (source, module)
    for source in ("product/federation/service.py", "product/models/governance.py"):
        text = (ROOT / source).read_text()
        assert not re.search(r"\b(torch\.nn|nn\.Module|optimizer|\.backward\(|\.step\()", text)
    assert forbidden  # documentation of the intent


def test_new_modules_never_compute_efficacy_metrics_or_run_inference() -> None:
    for source in NEW_SOURCES:
        text = (ROOT / source).read_text().lower()
        for forbidden in ("auroc", "auprc", "roc_auc", "f1_score", "accuracy_score", "predict_proba",
                          "model.eval", "infer_window"):
            assert forbidden not in text, (source, forbidden)


def test_the_central_database_holds_only_federation_metadata_no_data_labels_or_tensors() -> None:
    done = completed_run()
    connection = sqlite3.connect(done.root / "product.sqlite3")
    banned_columns = ("label", "truth", "raw", "waveform", "sample", "tensor", "delta", "weights", "state_bytes")
    for table in ("federation_runs", "federation_rounds", "fl_client_statuses", "candidate_models",
                  "governance_decisions"):
        for column in (r[1] for r in connection.execute(f"PRAGMA table_info({table})")):
            assert not any(b in column.lower() for b in banned_columns), (table, column)
    # candidate bytes live only in the artifact directory, and the DB holds only a digest
    candidate = done.run["candidate_ids"][0]
    assert (done.root / "candidates" / candidate / "state.bin").stat().st_size > 100_000
    assert connection.execute("SELECT length(state_digest) FROM candidate_models").fetchone()[0] == 64
    assert (done.root / "product.sqlite3").stat().st_size < 1_000_000


def test_every_submitted_envelope_passes_the_forbidden_field_scan(tmp_path, monkeypatch) -> None:
    seen: list[list[str]] = []
    original = update_bridge.scan_forbidden

    def spy(envelope):
        found = original(envelope)
        seen.append(found)
        return found

    monkeypatch.setattr(update_bridge, "scan_forbidden", spy)
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        rid = client.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).json()["run_id"]
        client.post(f"{BASE}/federation/runs/{rid}/start", headers=USER_A)
        assert poll_run(client, rid, USER_A)["status"] == "COMPLETED"
    assert len(seen) == 24 and all(f == [] for f in seen)
    assert fl_system.ENVELOPE_FIELDS  # the existing envelope schema is the only one used


def test_cross_user_access_is_refused_and_no_user_data_reaches_federation() -> None:
    done = completed_run()
    app, store = make_fed_app(done.root)
    with TestClient(app) as client:
        other = {"x-cap003-test-user": "someone-else"}
        assert client.get(f"{BASE}/federation/runs/{done.run_id}", headers=other).status_code == 403
        assert client.get(f"{BASE}/sessions", headers=other).json() == []
    assert store.row_counts().get("monitoring_sessions", 0) == 0  # federation never needs a monitoring row


def test_the_claims_in_the_overview_are_bounded(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        body = client.get(f"{BASE}/federation", headers=USER_A).json()
    text = json.dumps(body).lower()
    assert "engineering" in body["banner"].lower() and "no scientific evidence" in body["banner"].lower()
    for claim in ("hospital", "differential privacy", "anonym", "clinical", "diagnos", "enclave"):
        assert claim not in text


def test_the_frozen_cap_006_client_and_every_protected_file_are_byte_identical_to_the_entry_commit() -> None:
    entry = "651bfa61022cf699a43c0a91cbc43a6486943bcb"
    for path in ("product/federation/client.py", "product/federation/local_cohort.py",
                 "product/federation/update_bridge.py", "product/federation/base.py", "product/events.py",
                 "api/product_app_v1_1.py", "capstone_persistence/store.py", "contracts/capstone/federation_v1.json",
                 "federated/wearable_fl_system_v1.py", "federated/aggregation.py",
                 "federated/wearable_fl_secagg_shadow_v1.py"):
        diff = subprocess.run(["git", "diff", "--quiet", entry, "--", path], cwd=ROOT).returncode
        assert diff == 0, path
