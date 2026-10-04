#!/usr/bin/env python3
"""V2-FL-EVAL-001 PRE-ACCESS method freeze: writes the V2_FL_EVAL_PROTOCOL_V1 and
V2_FL_TEST_FAMILY_V1 component locks and method_freeze.json (hashes of every
scientific-method file and of the 20 checkpoints). Metadata only: no held-out data is read and
no FL model is run."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from evaluation.model_v2_fl_eval import load_roster
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_eval_001"
METHOD_FILES = [
    "configs/model_v2/fl_eval_protocol_v1.yaml", "configs/model_v2/fl_test_family_v1.yaml",
    "evaluation/model_v2_fl_eval.py", "evaluation/bootstrap.py", "evaluation/metrics.py",
    "evaluation/internal_test.py", "evaluation/external_incart.py",
    "scripts/run_v2_fl_eval_001.py", "scripts/compute_v2_fl_eval_stats.py",
    "scripts/verify_v2_fl_eval_stats.py", "scripts/freeze_v2_fl_eval_001_method.py",
    "scripts/v2_fl_eval_pre_access_audit.py", "scripts/build_v2_fl_test_family.py",
    "tests/test_v2_fl_eval_method.py",
    "federated/model_adapter.py", "federated/model_v2_fl.py", "models/model_v2_architectures.py",
    "models/ecg_cnn.py", "preprocessing/windowing.py",
    "reports/t018/bootstrap_draws.npz", "reports/t020/bootstrap_draws.npz",
    "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json",
    "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V2.lock.json", "artifacts/FEDPROX_MU_V2.lock.json",
    "artifacts/FEDPROX_MU_V1.lock.json",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    roster = load_roster(ROOT)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    family_lock = {
        "lock_id": "V2_FL_TEST_FAMILY_V1", "status": "FROZEN", "owner_task": "V2-FL-EVAL-001",
        "model_count": 20, "family_config_sha256": hash_file(
            ROOT / "configs/model_v2/fl_test_family_v1.yaml"),
        "checkpoints": {m["id"]: {"path": m["checkpoint"], "sha256": m["checkpoint_sha256"]}
                        for m in roster},
        "excluded_from_inference": yaml.safe_load((ROOT / "configs/model_v2/"
                                                   "fl_test_family_v1.yaml").read_text())[
            "excluded"],
        "frozen_before_any_held_out_inference": True,
        "change_control": "No model may be added or substituted after freeze."}
    protocol_lock = {
        "lock_id": "V2_FL_EVAL_PROTOCOL_V1", "status": "FROZEN", "owner_task": "V2-FL-EVAL-001",
        "gate": "V2FLEG0", "family_lock": "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json",
        "bound_artifacts": {p: hash_file(ROOT / p) for p in METHOD_FILES
                            if p != "scripts/freeze_v2_fl_eval_001_method.py"},
        "bootstrap": {"B": 2000, "seed": 20260927, "method": "PATIENT_CLUSTER_PERCENTILE_95_V1"},
        "threshold_id": "FL_EVAL_RAW_THRESHOLD_0P5_V1", "calibration": "NONE",
        "scientific_model_fits_added": 0, "federated_client_updates_added": 0,
        "frozen_before_any_held_out_inference": True,
        "change_control": "Any change after exposure requires an additive successor; scientific "
        "method files are immutable after the one-shot run starts."}
    (ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json").write_text(
        json.dumps(family_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "manifests/model_v2/V2_FL_EVAL_PROTOCOL_V1.lock.json").write_text(
        json.dumps(protocol_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "method_freeze.json").write_text(json.dumps({
        "owner_task": "V2-FL-EVAL-001", "gate": "V2FLEG0", "entry_head": head,
        "method_file_sha256": {p: hash_file(ROOT / p) for p in METHOD_FILES},
        "checkpoint_sha256": {m["id"]: m["checkpoint_sha256"] for m in roster},
        "protocol_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/V2_FL_EVAL_PROTOCOL_V1.lock.json"),
        "family_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json"),
        "held_out_inference_exists_at_method_freeze": False, "status": "PASS"},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("V2-FL-EVAL-001 method frozen at", head)


if __name__ == "__main__":
    main()
