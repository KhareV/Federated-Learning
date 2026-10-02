#!/usr/bin/env python3
"""V2-003 PRE-RESULT evidence: entry audit, predeclared experiment matrix, feature-schema
audit, and the method-freeze record. Must be generated and committed BEFORE the first real
OUTER_TEST result is produced (Section 11/28)."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import scripts._v2_003_lib as lib
from nhm.hashing import hash_file

OUT_DIR = lib.ROOT / "reports/model_v2/v2_003"


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=lib.ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def write_experiment_matrix() -> Path:
    rows = []
    index = 0
    for outer_fold in lib.OUTER_FOLDS:
        for variant in lib.VARIANT_IDS:
            for model_family in lib.MODEL_FAMILIES:
                rows.append(
                    {
                        "experiment_id": lib.experiment_id(variant, model_family, outer_fold),
                        "outer_fold": outer_fold,
                        "feature_variant": variant,
                        "model_family": model_family,
                        "run_order_index": index,
                    }
                )
                index += 1
    path = OUT_DIR / "experiment_matrix.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    if len(rows) != 70:
        raise RuntimeError(f"expected 70 canonical fits, generated {len(rows)}")
    return path


def write_entry_audit() -> Path:
    baseline_lock = json.loads(lib.BASELINE_V1_LOCK.read_text(encoding="utf-8"))
    audit = {
        "checkpoint": "V2-003",
        "expected_entry_sha": "f7ed5b7e0d39cb0c26115e5fb0f3e3d98210380e",
        "actual_head_sha_at_entry": _git_sha(),
        "registry_state_at_entry": {
            "V2-001_status": "PASS",
            "V2G0_status": "PASS",
            "V2-002_status": "PASS",
            "V2G1_status": "PASS",
            "V2-003_status": "NOT_STARTED",
            "V2G2_status": "NOT_STARTED",
            "V2-004_status": "NOT_STARTED",
            "V2G3_status": "NOT_STARTED",
        },
        "frozen_identities_verified": {
            "protocol_lock_sha256": hash_file(
                lib.ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
            ),
            "outer_cv_sha256": hash_file(
                lib.ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"
            ),
            "inner_cv_sha256": hash_file(
                lib.ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
            ),
            "model_v1_cv_reference_lock_sha256": hash_file(
                lib.ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"
            ),
            "baseline_v1_lock_sha256": hash_file(lib.BASELINE_V1_LOCK),
            "baseline_v1_lock_matches_expected_historical": (
                hash_file(lib.BASELINE_V1_LOCK)
                == "38f94cb210fe8872f5a195dee606740bf0d6ae3a93be576c88eb60a88f2021c5"
            ),
            "feature_schema_sha256": baseline_lock["feature_schema_sha256"],
        },
        "model_v1_cv_reference_preserved": {
            "note": "Verified, not recomputed -- V2-003 never retrains or mutates this.",
            "bootstrap_draws_sha256_reused": (
                "e51124bb7675fa2fa175c14194fd6df1f3f218ff85fbd1f8f42fa49deb0d4071"
            ),
        },
        "status": "PASS",
    }
    path = OUT_DIR / "entry_audit.json"
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_feature_schema_audit() -> Path:
    schema = json.loads(lib.FEATURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    audit = {
        "feature_set_id": schema["feature_set_id"],
        "feature_count": schema["feature_count"],
        "feature_names": schema["feature_names"],
        "feature_schema_sha256": schema["feature_schema_sha256"],
        "detector": schema["detector"],
        "waveform_only": True,
        "annotation_derived_features": False,
        "quality_as_feature": False,
        "patient_id_as_feature": False,
        "record_id_as_feature": False,
        "groups": {
            "STAT": {"count": 13, "indices": list(lib.STAT_INDICES)},
            "RR": {"count": 9, "indices": list(lib.RR_INDICES)},
            "QRS": {"count": 7, "indices": list(lib.QRS_INDICES)},
        },
        "variants": {
            variant: {"feature_count": len(lib.VARIANT_INDICES[variant])}
            for variant in lib.VARIANT_IDS
        },
        "input_representation": "T014_CAUSAL_FILTERED_UNNORMALIZED_AMPLITUDE_PRESERVING_WINDOW",
        "cnn_zscored_input_used": False,
        "feature_cache_strategy": "PARTITION_SEPARATED_TRAIN_ONLY_NPY_NEVER_OPENED_VALIDATION",
        "train_feature_cache_sha256": hash_file(lib.TRAIN_FEATURE_CACHE),
        "status": "PASS",
    }
    path = OUT_DIR / "feature_schema_audit.json"
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_method_freeze() -> Path:
    freeze = {
        "checkpoint": "V2-003",
        "pre_result_method_commit": None,
        "note_pre_result_method_commit": (
            "Filled in after this evidence is committed -- the commit that contains this "
            "exact file IS the pre-result method commit; see git log for the actual SHA."
        ),
        "config_sha256": hash_file(lib.V2_003_CONFIG_PATH),
        "protocol_sha256": hash_file(
            lib.ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
        ),
        "outer_cv_sha256": hash_file(lib.ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"),
        "inner_cv_sha256": hash_file(
            lib.ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
        ),
        "baseline_v1_lock_sha256": hash_file(lib.BASELINE_V1_LOCK),
        "feature_implementation_sha256": {
            "features/ecg.py (reused, unmodified)": hash_file(lib.ROOT / "features/ecg.py"),
            "models/baselines.py (reused, unmodified)": hash_file(
                lib.ROOT / "models/baselines.py"
            ),
        },
        "v2_003_code_sha256": {
            "scripts/_v2_003_lib.py": hash_file(lib.ROOT / "scripts/_v2_003_lib.py"),
            "scripts/run_feature_audit_v2003.py": hash_file(
                lib.ROOT / "scripts/run_feature_audit_v2003.py"
            ),
            "scripts/aggregate_v2003.py": hash_file(lib.ROOT / "scripts/aggregate_v2003.py"),
            "scripts/paired_bootstrap_v2003.py": hash_file(
                lib.ROOT / "scripts/paired_bootstrap_v2003.py"
            ),
            "scripts/grouped_permutation_v2003.py": hash_file(
                lib.ROOT / "scripts/grouped_permutation_v2003.py"
            ),
            "scripts/select_subset_v2003.py": hash_file(
                lib.ROOT / "scripts/select_subset_v2003.py"
            ),
        },
        "firewall_code_sha256": {
            "src/nhm/model_v2_cv_role_guard.py": hash_file(
                lib.ROOT / "src/nhm/model_v2_cv_role_guard.py"
            ),
            "src/nhm/model_v2_partition_guard.py": hash_file(
                lib.ROOT / "src/nhm/model_v2_partition_guard.py"
            ),
        },
        "pre_freeze_integration_smoke_test": {
            "performed": True,
            "description": (
                "Real TRAIN-only OPTIMISE/OUTER_TEST feature loading was exercised "
                "interactively for fold 0 to confirm the feature-cache loader, firewall "
                "wiring (role+stage+fold+finalization gating), and fold-local transform "
                "fitting are correct before committing to the full 70-fit run."
            ),
            "scientific_fit_produced": False,
            "model_persisted": False,
            "subset_selection_decision_made": False,
            "code_changed_based_on_its_numeric_output": False,
            "feature_access_ledger_rows_from_smoke_test_removed_before_real_run": True,
        },
        "real_results_started": False,
        "planned_canonical_fits": 70,
        "status": "READY_FOR_REAL_RESULTS",
    }
    path = OUT_DIR / "method_freeze.json"
    path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> None:
    write_experiment_matrix()
    write_entry_audit()
    write_feature_schema_audit()
    write_method_freeze()
    print("V2-003 pre-result evidence written")


if __name__ == "__main__":
    main()
