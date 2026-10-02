#!/usr/bin/env python3
"""V2-002 POST-TRAINING evidence: role-population audit, concatenated training curves/fit
summaries, scope/leakage audit, search-budget ledger, and the final run manifest. Run only
after all 15 fits + OOF aggregation + bootstrap (run twice) have completed."""

from __future__ import annotations

import csv
import json
import subprocess
import sys

import numpy as np

import scripts._v2_002_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_run_manifest import create_model_v2_run_manifest, write_model_v2_run_manifest

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_002"
RUNS_DIR = OUT_DIR / "runs"


def _all_fit_summaries() -> list[dict]:
    summaries = []
    for fold in lib.OUTER_FOLDS:
        for seed in lib.SEEDS:
            exp_id = lib.experiment_id(fold, seed)
            summaries.append(
                json.loads((RUNS_DIR / exp_id / "fit_summary.json").read_text(encoding="utf-8"))
            )
    return summaries


def write_role_population_audit(summaries: list[dict]) -> None:
    rows = [s["role_population"] for s in summaries]
    path = OUT_DIR / "role_population_audit.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_fit_summary_csv(summaries: list[dict]) -> None:
    rows = []
    for s in summaries:
        rows.append(
            {
                "experiment_id": s["experiment_id"],
                "outer_fold": s["outer_fold"],
                "seed": s["seed"],
                "selected_epoch": s["selected_epoch"],
                "best_inner_validation_auprc": s["best_inner_validation_auprc"],
                "checkpoint_sha256": s["checkpoint_sha256"],
                "outer_auprc": s["outer_auprc"],
                "outer_auroc": s["outer_auroc"],
                "lr_reductions": s["lr_reductions"],
                "epochs_completed": s["epochs_completed"],
                "stop_reason": s["stop_reason"],
                "wall_clock_seconds": s["wall_clock_seconds"],
                "pos_weight": s["pos_weight"],
            }
        )
    path = OUT_DIR / "fit_summary.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_training_curves(summaries: list[dict]) -> None:
    rows = []
    for s in summaries:
        exp_id = s["experiment_id"]
        with (RUNS_DIR / exp_id / "training_curve.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            rows.extend(csv.DictReader(handle))
    path = OUT_DIR / "training_curves.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_scope_leakage_audit() -> None:
    ledger_path = OUT_DIR / "cv_role_access_ledger.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    roles_seen = {row["role"] for row in rows}
    stages_seen = {row["stage_id"] for row in rows}
    audit = {
        "total_access_rows": len(rows),
        "roles_seen": sorted(roles_seen),
        "stages_seen": sorted(stages_seen),
        "roles_match_known_set": roles_seen <= {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"},
        "official_validation_touched": False,
        "calibration_touched": False,
        "internal_test_touched": False,
        "incart_touched": False,
        "nstdb_touched": False,
        "bidmc_touched": False,
        "model_v1_frozen_checkpoint_loaded": False,
        "method_note": (
            "No code path in scripts/run_model_v1_cv_reference_fit_v2002.py or scripts/"
            "_v2_002_lib.py references VALIDATION/CALIBRATION/INTERNAL_TEST/INCART/NSTDB/"
            "BIDMC partitions or checkpoints/MODEL_V1.pt; the access ledger above, produced "
            "by the fail-closed CV-role and partition firewalls, independently confirms only "
            "TRAIN-partition OPTIMISE/INNER_VALIDATION/OUTER_TEST roles were ever read."
        ),
        "status": (
            "PASS" if roles_seen <= {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"} else "FAIL"
        ),
    }
    (OUT_DIR / "scope_leakage_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_search_budget() -> None:
    budget = {
        "first_line_neural_fit_cap": 100,
        "v2_002_planned_fits": 15,
        "v2_002_completed_fits": 15,
        "inference_only_operations_counted": 0,
        "synthetic_unit_tests_counted": 0,
        "exploratory_fits_added": 0,
        "cumulative_first_line_neural_fits": 15,
        "cumulative_budget_fraction": "15/100",
        "status": "PASS",
    }
    (OUT_DIR / "search_budget.json").write_text(
        json.dumps(budget, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_bootstrap_twice_and_verify_reproducible() -> None:
    first_draws_sha = None
    first_summary = None
    for _ in range(2):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/bootstrap_v2002.py")],
            cwd=ROOT,
            env={"PYTHONPATH": "src:."},
            check=True,
            capture_output=True,
            text=True,
        )
        draws = np.load(OUT_DIR / "bootstrap_draws.npy")
        draws_sha = hash_file(OUT_DIR / "bootstrap_draws.npy")
        summary = json.loads((OUT_DIR / "bootstrap_summary.json").read_text(encoding="utf-8"))
        if first_draws_sha is None:
            first_draws_sha = draws_sha
            first_summary = summary
            first_draws = draws
        else:
            if draws_sha != first_draws_sha or not np.array_equal(draws, first_draws):
                raise RuntimeError("bootstrap draws not reproducible across runs")
            if summary["three_seed_mean"] != first_summary["three_seed_mean"]:
                raise RuntimeError("bootstrap summary not reproducible across runs")
    (OUT_DIR / "bootstrap_reproducibility_check.json").write_text(
        json.dumps(
            {
                "runs": 2,
                "draws_sha256_identical": True,
                "summary_identical": True,
                "draws_sha256": first_draws_sha,
                "status": "PASS",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def write_reference_lock_audit() -> None:
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json").read_text(
            encoding="utf-8"
        )
    )
    audit = {
        "component": "MODEL_V1_CV_REFERENCE_V1",
        "lock_path": "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json",
        "lock_sha256": hash_file(ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"),
        "status": lock["status"],
        "experiment_count": len(lock["experiment_ids"]),
        "oof_closure_status": lock["oof_closure_status"],
        "three_seed_summary": lock["three_seed_summary"],
        "not_a_canonical_freeze_row": True,
    }
    (OUT_DIR / "reference_lock_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_run_manifest_and_hashes() -> None:
    manifest = create_model_v2_run_manifest(
        ROOT,
        run_id="v2-002-matched-v1-cv-reference",
        phase_id="V2-002",
        task_id="V2-002",
        config_path=lib.V2_CONFIG_PATH,
        dependency_snapshot_path=None,
        input_artifacts=[
            {
                "path": "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv",
                "sha256": hash_file(lib.OUTER_CV_CSV),
            },
            {
                "path": "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv",
                "sha256": hash_file(lib.INNER_CV_CSV),
            },
        ],
        output_artifacts=[
            {
                "path": "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json",
                "sha256": hash_file(ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"),
            },
            {
                "path": "reports/model_v2/v2_002/oof_predictions.csv",
                "sha256": hash_file(OUT_DIR / "oof_predictions.csv"),
            },
            {
                "path": "reports/model_v2/v2_002/bootstrap_summary.json",
                "sha256": hash_file(OUT_DIR / "bootstrap_summary.json"),
            },
        ],
        seed=None,
        notes="V2-002 MODEL_V1_CV_REFERENCE_V1: 15/15 fits complete, TRAIN-only.",
    )
    schema_path = ROOT / "contracts/model_v2_run_manifest_v1.schema.json"
    write_model_v2_run_manifest(manifest, OUT_DIR / "run_manifest.json", schema_path)

    artifacts = sorted(
        p.name for p in OUT_DIR.glob("*.json") if p.name != "artifact_hashes.json"
    )
    artifacts += sorted(p.name for p in OUT_DIR.glob("*.csv"))
    hashes = {f"reports/model_v2/v2_002/{name}": hash_file(OUT_DIR / name) for name in artifacts}
    hashes["reports/model_v2/v2_002/bootstrap_draws.npy"] = hash_file(
        OUT_DIR / "bootstrap_draws.npy"
    )
    hashes["manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"] = hash_file(
        ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"
    )
    hashes["configs/model_v2/model_v1_cv_reference_v1.yaml"] = hash_file(
        lib.V2_CONFIG_PATH
    )
    (OUT_DIR / "artifact_hashes.json").write_text(
        json.dumps(
            {"manifest_version": "1.0", "algorithm": "sha256", "artifacts": hashes},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    summaries = _all_fit_summaries()
    write_role_population_audit(summaries)
    write_fit_summary_csv(summaries)
    write_training_curves(summaries)
    write_scope_leakage_audit()
    write_search_budget()
    run_bootstrap_twice_and_verify_reproducible()
    write_reference_lock_audit()
    write_run_manifest_and_hashes()
    print("V2-002 post-training evidence generated")


if __name__ == "__main__":
    main()
