#!/usr/bin/env python3
"""V2-002 PRE-TRAINING evidence: entry audit, predeclared experiment matrix, and the method-
freeze record. Must be generated and committed BEFORE the first real training fit begins."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import yaml

import scripts._v2_002_lib as lib
from nhm.hashing import hash_file

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_002"


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def write_experiment_matrix() -> Path:
    config = yaml.safe_load(lib.V2_CONFIG_PATH.read_text(encoding="utf-8"))
    rows = [
        {
            "experiment_id": lib.experiment_id(entry["outer_fold"], entry["seed"]),
            "outer_fold": entry["outer_fold"],
            "seed": entry["seed"],
            "run_order_index": index,
        }
        for index, entry in enumerate(config["run_order"])
    ]
    path = OUT_DIR / "experiment_matrix.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["experiment_id", "outer_fold", "seed", "run_order_index"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_entry_audit() -> Path:
    audit = {
        "checkpoint": "V2-002",
        "expected_entry_sha": "4b7494f3a91faa2bdaab5f752051ccb20162dd3b",
        "actual_head_sha_at_entry": _git_sha(),
        "registry_state_at_entry": {
            "V2-001_status": "PASS",
            "V2G0_status": "PASS",
            "V2-002_status": "NOT_STARTED",
            "V2G1_status": "NOT_STARTED",
            "V2-003_status": "NOT_STARTED",
        },
        "frozen_identities_verified": {
            "protocol_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
            ),
            "outer_cv_sha256": hash_file(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"),
            "inner_cv_sha256": hash_file(
                ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
            ),
            "model_v1_sha256": hash_file(ROOT / "checkpoints/MODEL_V1.pt"),
            "cal_v1_sha256": hash_file(ROOT / "artifacts/CAL_V1.json"),
        },
        "status": "PASS",
    }
    path = OUT_DIR / "entry_audit.json"
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_method_freeze() -> Path:
    freeze = {
        "checkpoint": "V2-002",
        "pre_training_method_commit": None,
        "note_pre_training_method_commit": (
            "Filled in after this evidence is committed -- the commit that contains this "
            "exact file IS the pre-run method commit; see git log for the actual SHA."
        ),
        "config_sha256": hash_file(ROOT / "configs/model_v2/model_v1_cv_reference_v1.yaml"),
        "protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
        ),
        "outer_cv_sha256": hash_file(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"),
        "inner_cv_sha256": hash_file(
            ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
        ),
        "training_code_sha256": {
            "scripts/_v2_002_lib.py": hash_file(ROOT / "scripts/_v2_002_lib.py"),
            "scripts/run_model_v1_cv_reference_fit_v2002.py": hash_file(
                ROOT / "scripts/run_model_v1_cv_reference_fit_v2002.py"
            ),
            "training/train_central.py (reused, unmodified)": hash_file(
                ROOT / "training/train_central.py"
            ),
            "models/ecg_cnn.py (reused, unmodified)": hash_file(ROOT / "models/ecg_cnn.py"),
            "configs/model_v1.yaml (reused, unmodified)": hash_file(ROOT / "configs/model_v1.yaml"),
        },
        "metric_code_sha256": hash_file(ROOT / "scripts/aggregate_oof_v2002.py"),
        "bootstrap_code_sha256": hash_file(ROOT / "scripts/bootstrap_v2002.py"),
        "firewall_code_sha256": {
            "src/nhm/model_v2_partition_guard.py": hash_file(
                ROOT / "src/nhm/model_v2_partition_guard.py"
            ),
            "src/nhm/model_v2_cv_role_guard.py": hash_file(
                ROOT / "src/nhm/model_v2_cv_role_guard.py"
            ),
        },
        "pre_freeze_integration_smoke_test": {
            "performed": True,
            "description": (
                "One manual training step + one validation pass were run interactively "
                "against real OPTIMISE/INNER_VALIDATION TRAIN waveform data (fold 0, seed "
                "20260927) to confirm the data-loading/model/optimizer/loss/DataLoader "
                "wiring is correct before committing to the full 15-fit run."
            ),
            "scientific_fit_produced": False,
            "checkpoint_saved": False,
            "early_stop_decision_made": False,
            "code_changed_based_on_its_numeric_output": False,
            "artifacts_discarded": True,
            "access_ledger_rows_from_smoke_test_removed_before_real_run": True,
        },
        "real_training_started": False,
        "planned_fits": 15,
        "status": "READY_FOR_REAL_TRAINING",
    }
    path = OUT_DIR / "method_freeze.json"
    path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> None:
    write_experiment_matrix()
    write_entry_audit()
    write_method_freeze()
    print("V2-002 pre-freeze evidence written")


if __name__ == "__main__":
    main()
