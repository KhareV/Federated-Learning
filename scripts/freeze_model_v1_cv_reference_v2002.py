#!/usr/bin/env python3
"""Create the MODEL_V1_CV_REFERENCE_V1 component lock (V2-002). Additive V2 component lock,
NOT a canonical Fxx freeze registry row. Run only after all 15 fits, OOF aggregation, and
bootstrap evidence exist."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_002"
DESTINATION = ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"


def main() -> None:
    oof_metrics = json.loads((OUT_DIR / "oof_metrics.json").read_text(encoding="utf-8"))
    bootstrap_summary = json.loads(
        (OUT_DIR / "bootstrap_summary.json").read_text(encoding="utf-8")
    )
    closure = json.loads((OUT_DIR / "oof_closure_audit.json").read_text(encoding="utf-8"))

    experiment_hashes = {}
    for fold in range(5):
        for seed in (20260927, 20260928, 20260929):
            exp_id = f"V2-002-F{fold:02d}-S{seed}"
            fit_summary_path = OUT_DIR / "runs" / exp_id / "fit_summary.json"
            fit_summary = json.loads(fit_summary_path.read_text(encoding="utf-8"))
            experiment_hashes[exp_id] = {
                "checkpoint_sha256": fit_summary["checkpoint_sha256"],
                "outer_predictions_sha256": hash_file(
                    OUT_DIR / "runs" / exp_id / "outer_predictions.csv"
                ),
                "selected_epoch": fit_summary["selected_epoch"],
                "outer_auprc": fit_summary["outer_auprc"],
                "outer_auroc": fit_summary["outer_auroc"],
            }

    lock = {
        "component_id": "MODEL_V1_CV_REFERENCE_V1",
        "status": "FROZEN_CV_REFERENCE",
        "owner_task": "V2-002",
        "not_calibrated": True,
        "not_a_release_model": True,
        "train_only_development_reference": True,
        "no_held_out_official_partition_accessed": True,
        "research_protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
        ),
        "model_v1_architecture_config_sha256": hash_file(ROOT / "configs/model_v1.yaml"),
        "f05_split_sha256": hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json"),
        "f06_preproc_sha256": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
        "window_manifest_sha256": hash_file(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"),
        "outer_cv_manifest_sha256": hash_file(
            ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"
        ),
        "inner_cv_manifest_sha256": hash_file(
            ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
        ),
        "v2_002_config_sha256": hash_file(
            ROOT / "configs/model_v2/model_v1_cv_reference_v1.yaml"
        ),
        "training_code_sha256": hash_file(
            ROOT / "scripts/run_model_v1_cv_reference_fit_v2002.py"
        ),
        "training_lib_sha256": hash_file(ROOT / "scripts/_v2_002_lib.py"),
        "metric_code_sha256": hash_file(ROOT / "scripts/aggregate_oof_v2002.py"),
        "bootstrap_code_sha256": hash_file(ROOT / "scripts/bootstrap_v2002.py"),
        "seeds": [20260927, 20260928, 20260929],
        "outer_folds": [0, 1, 2, 3, 4],
        "experiment_ids": sorted(experiment_hashes),
        "experiment_hashes": experiment_hashes,
        "oof_predictions_sha256": hash_file(OUT_DIR / "oof_predictions.csv"),
        "oof_metrics_sha256": hash_file(OUT_DIR / "oof_metrics.json"),
        "oof_closure_status": closure["status"],
        "bootstrap_draws_sha256": hash_file(OUT_DIR / "bootstrap_draws.npy"),
        "bootstrap_summary_sha256": hash_file(OUT_DIR / "bootstrap_summary.json"),
        "three_seed_summary": oof_metrics["three_seed_summary"],
        "bootstrap_three_seed_mean": bootstrap_summary["three_seed_mean"],
        "change_control": (
            "This lock is never mutated in place. A corrected reference requires a new, "
            "additive MODEL_V1_CV_REFERENCE_V2 successor with this lock preserved "
            "byte-identical as its predecessor."
        ),
    }

    DESTINATION.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(DESTINATION))


if __name__ == "__main__":
    main()
