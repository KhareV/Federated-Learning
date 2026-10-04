#!/usr/bin/env python3
"""V2-FL-004 PRE-RESULT method freeze: writes artifacts/SECAGG_METHOD_V2.lock.json (also binding
SECAGG_CONFIG_V2) and reports/model_v2/v2_fl_004/method_freeze.json BEFORE any canonical SecAgg+
outcome. Metadata only: hashes of method files and the V2FLG3 gate definition. The mutable strict
lifecycle test is deliberately NOT bound (MODEL_V2_LIFECYCLE_TEST_POLICY_V1)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_004"
SELF = "scripts/freeze_v2_fl_004_method.py"
METHOD_FILES = [
    "configs/model_v2/secagg_v2.yaml", "docs/MODEL_V2_SECAGG_THREAT_MODEL_V1.md",
    "scripts/run_secagg_v2_fl_004.py", "privacy/model_v2_secagg_fixture.py",
    "tests/test_v2_fl_004_method.py",
    "reports/model_v2/v2_fl_004/flower_secagg_api_audit.json",
    "reports/model_v2/v2_fl_004/preflight/round1_reconstruction.json",
    "reports/model_v2/v2_fl_004/preflight/clipping_preflight.json",
    "reports/model_v2/v2_fl_004/preflight/state_transport_audit.json",
    # historical generic harness, reused byte-identically
    "privacy/secagg_app.py", "privacy/server_visibility.py", "privacy/accounting.py",
    "scripts/run_secagg_t028.py", "configs/secagg_v1.yaml",
    "artifacts/SECAGG_METHOD_V1.lock.json", "artifacts/SECAGG_CONFIG_V1.lock.json",
    "reports/t028/overhead_summary.json", "reports/t028/flower_secagg_api_audit.json",
    # source-round definition
    "manifests/clients/CLIENTS_IID_V1.csv", "configs/model_v2/fl_iid_model_v2_v1.yaml",
    "federated/aggregation.py", "federated/model_adapter.py", "federated/model_v2_fl.py",
    "federated/fedavg_runner.py", "federated/client_manifest.py",
    "models/model_v2_architectures.py",
    "reports/model_v2/v2_fl_001/fl_iid_model_v2_result.json",
]
GATE = {
    "gate_id": "V2FLG3", "blocks_tasks": ["V2-FL-005"], "performance_independent": True,
    "pass_criteria": [
        "lifecycle entry audit PASS", "Flower 1.39.0 SecAggPlusWorkflow/secaggplus_mod available",
        "V2-FL-001 round-1 plain reconstruction reproduces frozen sha exactly",
        "92 state entries; 47+30 floating enter SecAgg; 15 integer counters server-side",
        "0 coordinates outside +-8 and 0 nonfinite", "known-vector within tolerance",
        "MODEL_V2-shaped protected aggregate within max abs 1e-4 and relative L2 1e-4",
        "plain negative control exposes 8 clear updates; protected exposes 0, aggregate available",
        "data-locality audit PASS at message boundary", "10/10 protected trials complete",
        "runtime and byte reports complete", "V1->V2 scaling uses historical T028 values only",
        "TRAIN-only access; no secret material persisted", "protected artifacts unchanged",
        "historical SecAgg V1 artifacts unchanged", "full regression PASS", "clean repository"],
    "fail_rule": "any failure stays recorded; evidence-assembly defects require an additive "
    "reconstruction-only successor, never a self-exemption",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    bound = {p: hash_file(ROOT / p) for p in METHOD_FILES}
    lock = {
        "lock_id": "SECAGG_METHOD_V2", "config_id": "SECAGG_CONFIG_V2", "status": "FROZEN",
        "owner_task": "V2-FL-004", "gate": GATE, "predecessor": "SECAGG_METHOD_V1",
        "bound_artifacts": bound, "flower_version": "1.39.0",
        "parameters": {"num_shares": 5, "reconstruction_threshold": 4, "max_weight": 4096.0,
                       "clipping_range": 8.0, "quantization_range": 2 ** 22,
                       "modulus_range": 2 ** 32, "timeout": None, "dropout": 0},
        "tolerances": {"maximum_absolute_parameter_difference": 1e-4,
                       "relative_l2_difference": 1e-4},
        "trials": {"warmup_per_path": 1, "measured_per_path": 10},
        "byte_accounting": "FLOWER_APPLICATION_PAYLOAD_BYTES_V1",
        "lifecycle_test_bound": False, "frozen_before_any_canonical_secagg_outcome": True,
        "scientific_model_fits_added": 0, "protected_partitions_accessed": [],
        "change_control": "Any change after canonical execution begins requires an additive "
        "successor; method files are immutable."}
    (ROOT / "artifacts/SECAGG_METHOD_V2.lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "method_freeze.json").write_text(json.dumps({
        "owner_task": "V2-FL-004", "gate": "V2FLG3", "entry_head": head,
        "method_file_sha256": bound,
        "lock_sha256": hash_file(ROOT / "artifacts/SECAGG_METHOD_V2.lock.json"),
        "canonical_secagg_outcomes_exist_at_method_freeze": False, "status": "PASS"},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SECAGG_METHOD_V2 frozen at", head)


if __name__ == "__main__":
    main()
