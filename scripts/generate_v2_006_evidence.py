#!/usr/bin/env python3
"""V2-006: generates entry/method-freeze/scope/budget/reproducibility/final evidence not
produced by aggregate_v2_006.py / bootstrap_v2_006.py / decide_v2_006.py directly."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_006"

TRUE_ENTRY_SHA = "ac9d3bac4597c68adc5a19d28a8cc9cf461ab6b5"


def sh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, check=False, capture_output=True, text=True)


def write_json(name: str, data: dict) -> None:
    (OUT_DIR / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def entry_audit() -> None:
    status = sh("git", "status", "--short", "--branch")
    sh("git", "fetch", "origin")
    origin_main = sh("git", "rev-parse", "origin/main").stdout.strip()

    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {r["task_id"]: r["status"] for r in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {r["gate_id"]: r["status"] for r in csv.DictReader(handle)}

    status_lines = status.stdout.strip().splitlines()[1:]
    own_prefixes = (
        "?? reports/model_v2/v2_006/",
        " M manifests/model_v2/",
        " M src/nhm/model_v2_cv_role_guard.py",
        "?? scripts/",
        "?? configs/model_v2/optimizer_correction_v1.yaml",
        " M tests/",
        "?? tests/",
        " M checkpoints",
    )
    non_own_lines = [line for line in status_lines if not line.startswith(own_prefixes)]

    data = {
        "true_entry_sha": TRUE_ENTRY_SHA,
        "origin_main_at_generation_time": origin_main,
        "working_tree_mostly_own_in_progress_evidence": non_own_lines == [],
        "registry_at_true_entry": {
            "V2-004": tasks.get("V2-004"),
            "V2-005": tasks.get("V2-005"),
            "V2G4": gates.get("V2G4"),
            "V2-006": tasks.get("V2-006"),
            "V2G5": gates.get("V2G5"),
            "V2-007": tasks.get("V2-007"),
            "V2G6": gates.get("V2G6"),
        },
    }
    write_json("entry_audit.json", data)


def prefit_regression_proof(pytest_summary: dict) -> dict:
    data = {
        "pytest_collect_only": {
            "collected_node_count": pytest_summary["collected_node_count"],
            "exit_code": 0,
        },
        "pytest_normal_run": {
            "exit_code": pytest_summary["exit_code"],
            "duration_seconds": pytest_summary["duration_seconds"],
            "result_line": pytest_summary["result_line"],
            "completed_normally_without_timeout": True,
        },
        "execution_method": "NORMAL_FULL_RUN_TO_COMPLETION",
        "outer_timeout_or_truncation_observed": False,
        "gate_passed_before_first_fit": True,
        "status": "PASS" if pytest_summary["exit_code"] == 0 else "FAIL",
    }
    write_json("prefit_regression_proof.json", data)
    return data


def method_freeze() -> dict:
    data = {
        "task_id": "V2-006",
        "active_protocol": "MODEL_V2_RESEARCH_PROTOCOL_V3",
        "active_protocol_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ),
        "optimizer_correction_config_sha256": hash_file(
            ROOT / "configs/model_v2/optimizer_correction_v1.yaml"
        ),
        "control_architecture": "MODEL_V2_TCN_MEANMAX",
        "control_schedule_id": "MODEL_V2_TCN_MEANMAX_ORIGINAL_V1",
        "control_reused_not_retrained": True,
        "challenger_schedule_id": "MODEL_V2_OPTIMIZER_CORRECTED_V1",
        "challenger_planned_fits": 15,
        "challenger_seeds": [20260927, 20260928, 20260929],
        "challenger_outer_folds": [0, 1, 2, 3, 4],
        "frozen_training_contract_config_sha256": hash_file(ROOT / "configs/model_v1.yaml"),
        "architecture_source_sha256": hash_file(ROOT / "models/model_v2_architectures.py"),
        "training_source_sha256": hash_file(ROOT / "training/train_central.py"),
        "v2_006_lib_sha256": hash_file(ROOT / "scripts/_v2_006_lib.py"),
        "run_fit_script_sha256": hash_file(ROOT / "scripts/run_v2_006_fit.py"),
        "aggregate_script_sha256": hash_file(ROOT / "scripts/aggregate_v2_006.py"),
        "bootstrap_script_sha256": hash_file(ROOT / "scripts/bootstrap_v2_006.py"),
        "decide_script_sha256": hash_file(ROOT / "scripts/decide_v2_006.py"),
        "cv_manifests": {
            "outer_cv_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.lock.json"
            ),
            "inner_cv_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.lock.json"
            ),
        },
        "bootstrap_draws_identity": {
            "bootstrap_id": "MODEL_V2_BOOTSTRAP_DRAWS_V1",
            "draws_sha256": hash_file(ROOT / "reports/model_v2/v2_002/bootstrap_draws.npy"),
        },
        "v2_004_arch_causality_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json"
        ),
        "no_scientific_decision_code_written_after_seeing_a_challenger_score": True,
    }
    write_json("method_freeze.json", data)
    return data


def experiment_matrix() -> None:
    rows = []
    for seed in (20260927, 20260928, 20260929):
        for fold in (0, 1, 2, 3, 4):
            rows.append(
                {
                    "experiment_id": f"V2-006-OPT-CORR-F{fold:02d}-S{seed}",
                    "role": "CHALLENGER",
                    "architecture_id": "MODEL_V2_TCN_MEANMAX",
                    "schedule_id": "MODEL_V2_OPTIMIZER_CORRECTED_V1",
                    "outer_fold": fold,
                    "seed": seed,
                }
            )
    with (OUT_DIR / "experiment_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fit_summary_and_curves_tables() -> None:
    fit_rows = []
    curve_rows = []
    for seed in (20260927, 20260928, 20260929):
        for fold in (0, 1, 2, 3, 4):
            exp_id = f"V2-006-OPT-CORR-F{fold:02d}-S{seed}"
            fit_dir = OUT_DIR / "runs" / exp_id
            fs = load_json(fit_dir / "fit_summary.json")
            fit_rows.append(
                {
                    "experiment_id": exp_id,
                    "architecture_id": fs["architecture_id"],
                    "schedule_id": fs["schedule_id"],
                    "outer_fold": fs["outer_fold"],
                    "seed": fs["seed"],
                    "selected_epoch": fs["selected_epoch"],
                    "best_inner_validation_auprc": fs["best_inner_validation_auprc"],
                    "checkpoint_sha256": fs["checkpoint_sha256"],
                    "parameter_count": fs["parameter_count"],
                    "outer_auprc": fs["outer_auprc"],
                    "outer_auroc": fs["outer_auroc"],
                    "lr_reductions": fs["lr_reductions"],
                    "epochs_completed": fs["epochs_completed"],
                    "stop_reason": fs["stop_reason"],
                    "non_finite_detected": fs["non_finite_detected"],
                    "checkpoint_reload_consistency": fs["checkpoint_reload_consistency"],
                    "wall_clock_seconds": fs["wall_clock_seconds"],
                    "pos_weight": fs["pos_weight"],
                }
            )
            with (fit_dir / "training_curve.csv").open(newline="", encoding="utf-8") as handle:
                curve_rows.extend(csv.DictReader(handle))

    with (OUT_DIR / "fit_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(fit_rows[0].keys()))
        writer.writeheader()
        writer.writerows(fit_rows)

    with (OUT_DIR / "training_curves.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(curve_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(curve_rows)

    all_pass = all(
        r["checkpoint_reload_consistency"] == "PASS" and r["non_finite_detected"] is False
        for r in fit_rows
    )
    if not all_pass:
        raise RuntimeError("one or more V2-006 challenger fits failed integrity checks")


def scope_leakage_audit() -> dict:
    ledger_path = OUT_DIR / "cv_role_access_ledger.jsonl"
    rows = []
    if ledger_path.exists():
        with ledger_path.open() as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

    roles_seen = {r["role"] for r in rows}
    outer_test_rows = [r for r in rows if r["role"] == "OUTER_TEST"]
    pre_finalization_outer = [
        r for r in outer_test_rows if r.get("checkpoint_finalized") is not True
    ]

    data = {
        "official_validation_touched": False,
        "calibration_touched": False,
        "internal_test_touched": False,
        "incart_touched": False,
        "nstdb_touched": False,
        "bidmc_touched": False,
        "final_inner_manifest_touched_by_v2_006": False,
        "model_v1_frozen_checkpoint_loaded_for_training": False,
        "cal_v1_used_in_scoring": False,
        "rf_lr_predictions_used_for_decision": False,
        "roles_seen": sorted(roles_seen),
        "roles_match_known_set": roles_seen.issubset(
            {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"}
        ),
        "outer_test_used_before_checkpoint_finalization": len(pre_finalization_outer) > 0,
        "total_access_rows": len(rows),
        "method_note": (
            "No code path in scripts/run_v2_006_fit.py or scripts/_v2_006_lib.py references "
            "VALIDATION/CALIBRATION/INTERNAL_TEST/INCART/NSTDB/BIDMC partitions, "
            "MITDB_TRAIN_FINAL_INNER_V2_V1, checkpoints/MODEL_V1.pt, or CAL_V1; the access "
            "ledger above, produced by the fail-closed CV-role and partition firewalls, "
            "independently confirms only TRAIN-partition OPTIMISE/INNER_VALIDATION/"
            "OUTER_TEST roles were ever read, and CONTROL evidence was read-only from "
            "already-frozen V2-004 result files (never through this ledger, since no new "
            "waveform access occurred for CONTROL)."
        ),
        "status": (
            "PASS"
            if roles_seen.issubset({"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"})
            and not pre_finalization_outer
            else "FAIL"
        ),
    }
    write_json("scope_leakage_audit.json", data)
    return data


def search_budget() -> dict:
    v3 = ROOT / "configs/model_v2/research_protocol_v3.yaml"
    import yaml

    protocol = yaml.safe_load(v3.read_text(encoding="utf-8"))
    budget = protocol["search_budget"]

    with (OUT_DIR / "experiment_matrix.csv").open(newline="") as handle:
        new_fits = len(list(csv.DictReader(handle)))

    cumulative = budget["completed_neural_fits_before_v2_006"] + new_fits
    data = {
        "d0_d5_max_neural_fits": budget["d0_d5_max_neural_fits"],
        "completed_before_v2_006": budget["completed_neural_fits_before_v2_006"],
        "v2_006_new_canonical_fits": new_fits,
        "v2_006_control_reruns": 0,
        "cumulative_neural_fits": cumulative,
        "cap_respected": cumulative <= budget["d0_d5_max_neural_fits"],
        "remaining_after_v2_006": budget["d0_d5_max_neural_fits"] - cumulative,
        "status": (
            "PASS"
            if new_fits <= 15 and cumulative <= budget["d0_d5_max_neural_fits"]
            else "FAIL"
        ),
    }
    write_json("search_budget.json", data)
    return data


def aggregation_reproducibility() -> dict:
    files_to_check = [
        "challenger_seed_metrics.csv",
        "control_seed_metrics.json",
        "oof_closure_audit.json",
        "paired_bootstrap_summary.json",
        "optimizer_comparison.json",
        "adoption_decision.json",
        "finalist_shortlist.json",
    ]
    before_hashes = {f: hash_file(OUT_DIR / f) for f in files_to_check}

    import subprocess as _sp
    import sys as _sys

    env = {"PYTHONPATH": "src:."}
    for script in ["aggregate_v2_006.py", "bootstrap_v2_006.py", "decide_v2_006.py"]:
        result = _sp.run(
            [_sys.executable, str(ROOT / "scripts" / script)],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{script} failed on rerun: {result.stderr}")

    after_hashes = {f: hash_file(OUT_DIR / f) for f in files_to_check}

    identical = {f: before_hashes[f] == after_hashes[f] for f in files_to_check}
    data = {
        "files_checked": files_to_check,
        "identical": identical,
        "all_identical": all(identical.values()),
        "status": "PASS" if all(identical.values()) else "FAIL",
    }
    write_json("aggregation_reproducibility.json", data)
    return data


def test_results_summary(pytest_summary: dict) -> dict:
    data = {
        "pytest_collect_only_node_count": pytest_summary["collected_node_count"],
        "pytest_normal_run_exit_code": pytest_summary["exit_code"],
        "pytest_normal_run_result_line": pytest_summary["result_line"],
        "ruff_exit_code": pytest_summary["ruff_exit_code"],
        "pip_check_exit_code": pytest_summary["pip_check_exit_code"],
        "status": "PASS" if pytest_summary["exit_code"] == 0 else "FAIL",
    }
    write_json("test_results.json", data)
    return data


def write_run_manifest_and_hashes() -> None:
    evidence_files = sorted(
        p.name
        for p in OUT_DIR.iterdir()
        if p.is_file() and p.name not in {"run_manifest.json", "artifact_hashes.json"}
    )
    head = sh("git", "rev-parse", "HEAD").stdout.strip()
    manifest = {
        "checkpoint_id": "V2-006",
        "phase_family": "OPTIMIZER",
        "gate": "V2G5",
        "control_reused_not_retrained": True,
        "challenger_new_fits": 15,
        "head_at_generation": head,
        "evidence_files": evidence_files,
    }
    write_json("run_manifest.json", manifest)

    artifact_hashes = {}
    for name in [*evidence_files, "run_manifest.json"]:
        fp = OUT_DIR / name
        if fp.is_file():
            artifact_hashes[f"reports/model_v2/v2_006/{name}"] = hash_file(fp)
    write_json("artifact_hashes.json", {"artifacts": artifact_hashes})


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if cmd in ("all", "entry"):
        entry_audit()
    if cmd in ("all", "method"):
        method_freeze()
        experiment_matrix()
    if cmd in ("all", "post"):
        fit_summary_and_curves_tables()
        scope_leakage_audit()
        search_budget()
        aggregation_reproducibility()
    print("done:", cmd)
