#!/usr/bin/env python3
"""C-V2-PRE004-CONTROL evidence generator (part 1): d0_6_final_method_inventory.json -- hashes
the CURRENT committed state of every scientifically relevant D0.6 file (code, config, tests)
and every frozen input artifact the D0.6 computation depends on. Does not scientifically
modify anything; read-only hashing."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/c_v2_pre004_control"

D0_6_CODE_FILES = [
    "configs/model_v2/d0_6_diagnostic_reconstruction_v1.yaml",
    "src/nhm/model_v2_d0_6_guard.py",
    "scripts/_d0_6_lib.py",
    "scripts/_d0_6_diagnostics.py",
    "scripts/generate_d0_6_prefreeze_evidence.py",
    "scripts/run_d0_6_diagnostics.py",
    "tests/test_c_v2_d0_6_config.py",
    "tests/test_c_v2_d0_6_results.py",
]

D0_6_INPUT_ARTIFACTS = [
    "reports/model_v2/v2_002/oof_predictions.csv",
    "reports/model_v2/v2_003/oof_predictions.csv",
    "reports/model_v2/v2_003/oof_metrics.json",
    "reports/model_v2/v2_003/grouped_permutation_summary.json",
    "manifests/windows/MITDB_WINDOWS_V1.csv",
    "manifests/features/MITDB_BASELINE_FEATURES_V1.csv",
    "manifests/features/BASELINE_FEATURES_V1.schema.json",
    (
        "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
        "BASELINE_FEATURES_V1/TRAIN_features.npy"
    ),
    (
        "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
        "BASELINE_FEATURES_V1/VALIDATION_features.npy"
    ),
    "artifacts/CAL_V1.json",
    "configs/baseline_v1.yaml",
    "reports/t015/seeds/20260927.json",
    "reports/t015/seeds/20260928.json",
    "reports/t015/seeds/20260929.json",
    "reports/baselines/baseline_report.json",
    "evaluation/error_analysis.py",
]

D0_6_ORIGINAL_RESULT_FILES = [
    "reports/model_v2/c_v2_d0_6/patient_composition_train_oof.csv",
    "reports/model_v2/c_v2_d0_6/patient_composition_validation.csv",
    "reports/model_v2/c_v2_d0_6/class_composition_train_oof.csv",
    "reports/model_v2/c_v2_d0_6/class_composition_validation.csv",
    "reports/model_v2/c_v2_d0_6/score_distributions.csv",
    "reports/model_v2/c_v2_d0_6/diagnostic_thresholds.json",
    "reports/model_v2/c_v2_d0_6/threshold_region_errors.csv",
    "reports/model_v2/c_v2_d0_6/patient_loo_auprc.csv",
    "reports/model_v2/c_v2_d0_6/patient_brier.csv",
    "reports/model_v2/c_v2_d0_6/train_oof_hypothesis_audit.json",
    "reports/model_v2/c_v2_d0_6/historical_validation_context.json",
]


def main() -> None:
    inventory = {
        "d0_6_code_sha256": {path: hash_file(ROOT / path) for path in D0_6_CODE_FILES},
        "d0_6_input_artifact_sha256": {
            path: hash_file(ROOT / path) for path in D0_6_INPUT_ARTIFACTS
        },
        "d0_6_original_result_sha256": {
            path: hash_file(ROOT / path) for path in D0_6_ORIGINAL_RESULT_FILES
        },
        "note": (
            "This inventory hashes the CURRENT committed state as of this checkpoint's entry "
            "(69d7d90). scripts/run_d0_6_diagnostics.py is included here for the first time "
            "as an explicitly frozen-and-attested file (see "
            "d0_6_git_chronology_audit.json for the historical gap this remediates)."
        ),
        "status": "PASS",
    }
    (OUT_DIR / "d0_6_final_method_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("d0_6_final_method_inventory.json written")


if __name__ == "__main__":
    main()
