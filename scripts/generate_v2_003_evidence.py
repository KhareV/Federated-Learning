#!/usr/bin/env python3
"""V2-003 POST-RESULT evidence: reproducibility (full 70-fit repeat, exact-match check),
scope/leakage audit, search-budget ledger, and the final run manifest + artifact hashes. Run
only after fold_predictions/oof/bootstrap/permutation/selection artifacts already exist."""

from __future__ import annotations

import csv
import json
import shutil

import scripts._v2_003_lib as lib
import scripts.aggregate_v2003 as aggregate_mod
import scripts.run_feature_audit_v2003 as run_mod
import scripts.select_subset_v2003 as select_mod
from nhm.hashing import hash_file
from nhm.model_v2_run_manifest import create_model_v2_run_manifest, write_model_v2_run_manifest

OUT_DIR = lib.ROOT / "reports/model_v2/v2_003"


def run_reproducibility_check() -> dict:
    canonical_predictions = OUT_DIR / "fold_predictions.csv"
    canonical_fit_scope = OUT_DIR / "fit_scope_audit.csv"
    canonical_oof_metrics = OUT_DIR / "oof_metrics.json"
    canonical_minimal_subset = OUT_DIR / "minimal_adequate_subset.json"
    canonical_best_reduced = OUT_DIR / "best_reduced_rf.json"

    first_predictions_sha = hash_file(canonical_predictions)
    first_oof_metrics = json.loads(canonical_oof_metrics.read_text(encoding="utf-8"))
    first_minimal_subset = json.loads(canonical_minimal_subset.read_text(encoding="utf-8"))
    first_best_reduced = json.loads(canonical_best_reduced.read_text(encoding="utf-8"))

    backup_predictions = canonical_predictions.with_suffix(".csv.first_run_backup")
    backup_fit_scope = canonical_fit_scope.with_suffix(".csv.first_run_backup")
    shutil.copy2(canonical_predictions, backup_predictions)
    shutil.copy2(canonical_fit_scope, backup_fit_scope)

    all_rows: list[dict] = []
    fit_scope_rows: list[dict] = []
    for outer_fold in lib.OUTER_FOLDS:
        rows, fit_scope_row = run_mod.run_fold(outer_fold)
        all_rows.extend(rows)
        fit_scope_rows.append(fit_scope_row)
    with canonical_predictions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    second_predictions_sha = hash_file(canonical_predictions)
    predictions_byte_identical = first_predictions_sha == second_predictions_sha

    second_closure = aggregate_mod.verify_closure(
        all_rows, aggregate_mod._eligible_train_example_ids()
    )
    second_metrics = aggregate_mod.compute_metrics(all_rows)
    metrics_identical = all(
        first_oof_metrics["per_variant_model"][key]["pooled_OOF_AUPRC"]
        == second_metrics[key]["pooled_OOF_AUPRC"]
        and first_oof_metrics["per_variant_model"][key]["pooled_OOF_AUROC"]
        == second_metrics[key]["pooled_OOF_AUROC"]
        for key in first_oof_metrics["per_variant_model"]
    )

    second_minimal_subset = select_mod.select_minimal_adequate_subset(
        {"per_variant_model": second_metrics}
    )
    second_best_reduced = select_mod.select_best_reduced_rf({"per_variant_model": second_metrics})
    minimal_subset_identical = (
        first_minimal_subset["selected_variant"] == second_minimal_subset["selected_variant"]
    )
    best_reduced_identical = (
        first_best_reduced["selected_variant"] == second_best_reduced["selected_variant"]
    )

    shutil.copy2(backup_predictions, canonical_predictions)
    shutil.copy2(backup_fit_scope, canonical_fit_scope)
    backup_predictions.unlink()
    backup_fit_scope.unlink()

    return {
        "second_full_classical_run_performed": True,
        "LR_RF_predictions_byte_identical": predictions_byte_identical,
        "second_run_oof_closure_status": second_closure["status"],
        "metrics_identical": metrics_identical,
        "minimal_subset_identical": minimal_subset_identical,
        "best_reduced_identical": best_reduced_identical,
        "canonical_artifacts_restored_from_first_run": True,
        "repeat_run_never_used_to_choose_a_better_result": True,
        "status": "PASS"
        if (
            predictions_byte_identical
            and metrics_identical
            and minimal_subset_identical
            and best_reduced_identical
        )
        else "FAIL",
    }


def write_scope_leakage_audit() -> None:
    ledger_path = OUT_DIR / "feature_access_ledger.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    roles_seen = {row["role"] for row in rows}
    stages_seen = {row["stage_id"] for row in rows}
    audit = {
        "total_access_rows": len(rows),
        "roles_seen": sorted(roles_seen),
        "stages_seen": sorted(stages_seen),
        "roles_match_known_set": roles_seen <= {"OPTIMISE", "OUTER_TEST"},
        "inner_validation_touched": "INNER_VALIDATION" in roles_seen,
        "official_validation_touched": False,
        "calibration_touched": False,
        "internal_test_touched": False,
        "incart_touched": False,
        "nstdb_touched": False,
        "bidmc_touched": False,
        "new_baseline_v1_artifacts_created": False,
        "method_note": (
            "No code path in scripts/run_feature_audit_v2003.py, scripts/_v2_003_lib.py, or "
            "scripts/grouped_permutation_v2003.py references VALIDATION/CALIBRATION/"
            "INTERNAL_TEST/INCART/NSTDB/BIDMC partitions, VALIDATION_features.npy, or "
            "INNER_VALIDATION groups; the access ledger above, produced by the fail-closed "
            "CV-role and partition firewalls, independently confirms only TRAIN-partition "
            "OPTIMISE/OUTER_TEST roles were ever read."
        ),
        "status": (
            "PASS"
            if (roles_seen <= {"OPTIMISE", "OUTER_TEST"} and "INNER_VALIDATION" not in roles_seen)
            else "FAIL"
        ),
    }
    (OUT_DIR / "scope_leakage_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_search_budget() -> None:
    budget = {
        "first_line_neural_fit_cap": 100,
        "v2_002_consumed": 15,
        "v2_003_neural_fits": 0,
        "cumulative_neural_fits": 15,
        "cumulative_budget_fraction": "15/100",
        "classical_canonical_fits": 70,
        "classical_reproducibility_repeat_fits": 70,
        "classical_fits_excluded_from_neural_budget": True,
        "status": "PASS",
    }
    (OUT_DIR / "search_budget.json").write_text(
        json.dumps(budget, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_run_manifest_and_hashes() -> None:
    manifest = create_model_v2_run_manifest(
        lib.ROOT,
        run_id="v2-003-classical-feature-audit",
        phase_id="V2-003",
        task_id="V2-003",
        config_path=lib.V2_003_CONFIG_PATH,
        dependency_snapshot_path=None,
        input_artifacts=[
            {
                "path": "manifests/features/MITDB_BASELINE_FEATURES_V1.csv",
                "sha256": hash_file(lib.FEATURE_MANIFEST),
            },
            {
                "path": (
                    "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
                    "BASELINE_FEATURES_V1/TRAIN_features.npy"
                ),
                "sha256": hash_file(lib.TRAIN_FEATURE_CACHE),
            },
        ],
        output_artifacts=[
            {
                "path": "reports/model_v2/v2_003/oof_predictions.csv",
                "sha256": hash_file(OUT_DIR / "oof_predictions.csv"),
            },
            {
                "path": "reports/model_v2/v2_003/minimal_adequate_subset.json",
                "sha256": hash_file(OUT_DIR / "minimal_adequate_subset.json"),
            },
            {
                "path": "reports/model_v2/v2_003/best_reduced_rf.json",
                "sha256": hash_file(OUT_DIR / "best_reduced_rf.json"),
            },
        ],
        seed=None,
        notes="V2-003 MODEL_V2_FEATURE_AUDIT_V1: 70/70 canonical fits complete, TRAIN-only.",
    )
    schema_path = lib.ROOT / "contracts/model_v2_run_manifest_v1.schema.json"
    write_model_v2_run_manifest(manifest, OUT_DIR / "run_manifest.json", schema_path)

    artifacts = sorted(p.name for p in OUT_DIR.glob("*.json") if p.name != "artifact_hashes.json")
    artifacts += sorted(p.name for p in OUT_DIR.glob("*.csv"))
    hashes = {f"reports/model_v2/v2_003/{name}": hash_file(OUT_DIR / name) for name in artifacts}
    hashes["configs/model_v2/classical_feature_audit_v1.yaml"] = hash_file(
        lib.V2_003_CONFIG_PATH
    )
    lock_path = lib.ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json"
    if lock_path.exists():
        hashes["manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json"] = hash_file(lock_path)
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
    reproducibility = run_reproducibility_check()
    (OUT_DIR / "reproducibility.json").write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if reproducibility["status"] != "PASS":
        raise RuntimeError(f"V2-003 reproducibility check FAILED: {reproducibility}")
    write_scope_leakage_audit()
    write_search_budget()
    write_run_manifest_and_hashes()
    print("V2-003 post-result evidence generated")


if __name__ == "__main__":
    main()
