#!/usr/bin/env python3
"""V2-FL-005 PRE-TRAINING method freeze: writes the frozen cohort manifest, the
V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1 lock (binding cohort, label contract, source contract, router,
protocol, SecAgg compatibility binding, replay digest rule) and method_freeze.json BEFORE any
canonical local training. Metadata only. The mutable strict lifecycle test is NOT bound."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

from nhm.hashing import hash_bytes, hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_005"
COHORT = ROOT / "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json"
METHOD_FILES = [
    "configs/model_v2/v2_fl_wearable_system_protocol_v1.yaml",
    "configs/model_v2/wearable_sim_fl_secagg_compat_v1.yaml",
    "docs/MODEL_V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.md",
    "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json",
    "reports/model_v2/v2_fl_005/cohort_preflight.json",
    "reports/model_v2/v2_fl_005/lifecycle_registry_preflight.json",
    "simulation/fl_cohort_v1.py", "simulation/fl_cohort_truth_v1.py",
    "federated/virtual_client_source_v1.py", "federated/wearable_sim_local_labels.py",
    "federated/wearable_fl_system_v1.py", "federated/wearable_fl_runner_v1.py",
    "federated/wearable_fl_secagg_shadow_v1.py", "scripts/run_v2_fl_005_system_demo.py",
    "scripts/run_v2_fl_005_chunked_regression.py", "scripts/finalize_v2_fl_005_evidence.py",
    "tests/test_v2_fl_005_method.py",
    # unchanged upstream used as-is
    "simulation/stream_runtime_v2013.py", "simulation/profile_v2013.py", "simulation/types.py",
    "simulation/wearable.py", "preprocessing/ecg.py", "preprocessing/gaps.py",
    "preprocessing/resample.py", "preprocessing/filters.py", "preprocessing/quality.py",
    "preprocessing/sync.py", "federated/model_v2_fl.py", "federated/local_training.py",
    "federated/aggregation.py", "federated/model_adapter.py", "models/model_v2_architectures.py",
    "privacy/secagg_app.py", "privacy/server_visibility.py", "privacy/accounting.py",
    "configs/model_v2/secagg_v2.yaml", "artifacts/SECAGG_METHOD_V2.lock.json",
    "configs/model_v2/fl_iid_model_v2_v1.yaml",
]


def main() -> None:
    candidate = OUT / "cohort_manifest_candidate.json"
    shutil.copyfile(candidate, COHORT)
    manifest = json.loads(COHORT.read_text())
    cohort_sha = hash_bytes(json.dumps(manifest, sort_keys=True).encode())
    protocol = yaml.safe_load(
        (ROOT / "configs/model_v2/v2_fl_wearable_system_protocol_v1.yaml").read_text())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    bound = {p: hash_file(ROOT / p) for p in METHOD_FILES}
    lock = {
        "lock_id": "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1", "status": "FROZEN",
        "owner_task": "V2-FL-005", "gate": {"gate_id": "V2FLG4", "blocks_tasks": ["V2-014"],
                                            **protocol["v2flg4"]},
        "cohort_id": manifest["cohort_id"], "cohort_manifest_sha256": cohort_sha,
        "dataset_sha256": {c["client_id"]: c["dataset_sha256"] for c in manifest["clients"]},
        "bound_artifacts": bound, "experiment_id": protocol["experiment_id"],
        "replay_id": protocol["replay_id"], "secagg_compat_max_weight": 256.0,
        "lifecycle_test_bound": False, "frozen_before_any_canonical_local_training": True,
        "scientific_model_fits_added": 0, "scientific_checkpoints_added": 0,
        "protected_partitions_accessed": [],
        "change_control": "Any change after canonical execution begins requires an additive "
        "successor; no max_weight change after this freeze."}
    (ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "method_freeze.json").write_text(json.dumps({
        "owner_task": "V2-FL-005", "gate": "V2FLG4", "entry_head": head,
        "cohort_manifest_sha256": cohort_sha, "method_file_sha256": bound,
        "lock_sha256": hash_file(ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json"),
        "canonical_local_training_exists_at_method_freeze": False, "status": "PASS"},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1 frozen at", head, cohort_sha)


if __name__ == "__main__":
    main()
