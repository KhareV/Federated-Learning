#!/usr/bin/env python3
"""V2-FL-EVAL-001 V2FLEG0 criteria / run manifest / artifact hashes (post-exposure, metadata and
frozen-statistics only). `--stage1` writes the criteria with the regression criterion PENDING so the
chunked regression can run against complete evidence; the plain invocation writes the final criteria
(PASS only if every performance-independent criterion holds) and the run manifest; `--hashes-only`
writes artifact_hashes.json last. Performance magnitude is never a criterion."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from evaluation.model_v2_fl_eval import FAMILY_RELATIVE
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_eval_001"
RUN_LOGS = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv", "pytest_chunk_results.csv"}


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _defined(model: dict) -> bool:
    point = model["point"]
    return all(point[k] is not None for k in (
        "AUPRC", "AUROC", "pooled_F1", "precision", "sensitivity", "specificity",
        "patient_macro_F1", "accuracy", "BCE"))


def main() -> None:
    if "--hashes-only" in sys.argv:
        files = sorted(p for p in OUT.rglob("*") if p.is_file())
        _write("artifact_hashes.json", {"artifacts": {
            str(p.relative_to(ROOT)): hash_file(p) for p in files
            if p.name not in RUN_LOGS and p.name != "artifact_hashes.json"}})
        print("hashes written")
        return
    roster = yaml.safe_load((ROOT / FAMILY_RELATIVE).read_text())["models"]
    internal, incart = _load("internal_test_statistics.json"), _load("incart_statistics.json")
    population, guards = _load("population_report.json"), _load("one_shot_guard_audit.json")
    firewall = _load("firewall_audit.json")
    immutable = _load("method_immutability_post_exposure.json")
    protected = _load("protected_artifact_audit.json")
    reproductions = [_load(f"verification/reproduction_{n}.json") for n in ("run_1", "run_2")]
    manifest = _load("inference_manifest.json")
    protocol = yaml.safe_load((ROOT / "configs/model_v2/fl_eval_protocol_v1.yaml").read_text())
    ids = {m["id"] for m in roster}
    criteria = {
        "frozen_method_family_only": len(roster) == 20 and set(internal["models"]) == ids,
        "20_of_20_internal_test_complete": len(manifest["internal_test"]) == 20 and all(
            b["rows"] == 2157 for b in manifest["internal_test"]),
        "20_of_20_incart_complete": len(manifest["incart"]) == 20 and all(
            b["rows"] == 26864 for b in manifest["incart"]),
        "no_excluded_checkpoint_evaluated": guards["excluded_checkpoints_evaluated"] is False
        and guards["evaluated_ids_equal_roster"],
        "internal_example_sets_exact": population["INTERNAL_TEST"][
            "all_20_models_identical_ordered_example_ids_equal_frozen_expectation"],
        "incart_example_sets_exact": population["INCART"][
            "all_20_models_identical_ordered_example_ids_equal_frozen_expectation"],
        "all_checkpoint_hashes_verified": protected["roster_checkpoint_drift"] == [],
        "one_shot_guards_completed": all(s == "COMPLETED" for s in guards["states"].values()),
        "second_inference_blocked": guards["second_attempt_blocked_deterministically"],
        "all_point_metrics_complete": all(_defined(m) for d in (internal, incart)
                                          for m in d["models"].values()),
        "all_patient_metrics_complete": all(
            len(m["patients"]) == d["clusters"] for d in (internal, incart)
            for m in d["models"].values()),
        "bootstrap_B_2000_multiplicity_preserved": all(
            d["bootstrap"]["B"] == 2000 and d["bootstrap"]["multiplicity_preserved"]
            and d["bootstrap"]["slots_per_replicate"] == d["clusters"]
            for d in (internal, incart)),
        "primary_v2_iid_fedavg_reported": "V2_FEDAVG_IID" in internal["models"],
        "primary_architecture_delta_reported":
        "V2_FEDAVG_IID_minus_V1_FEDAVG_IID" in internal["comparisons"],
        "condition_wise_architecture_effects_reported": sum(
            1 for c in internal["comparisons"].values() if c["family"] == "architecture_effect")
        == 10,
        "v2_fedprox_vs_fedavg_effects_reported": sum(
            1 for c in internal["comparisons"].values() if c["family"] == "fedprox_effect") == 5,
        "no_calibration": not (firewall["CAL_V1_used"] or firewall["CAL_V2_used"])
        and protocol["input_contract"]["calibration"] == "NONE",
        "no_tuning_no_promotion": firewall["threshold_tuned"] is False
        and protocol["claim_boundary"][0] == "no_model_promotion",
        "later_verification_prediction_only": all(
            r["status"] == "PASS" and not r["checkpoints_loaded"] and not r["source_data_opened"]
            for r in reproductions),
        "method_immutable_after_exposure": immutable["status"] == "PASS",
        "protected_artifacts_unchanged": protected["status"] == "PASS",
        "firewall": firewall["status"] == "PASS"}
    if "--stage1" in sys.argv:
        criteria["regression"] = "PENDING_STAGE1"
        _write("v2fleg0_criteria.json", {
            "criteria": criteria, "status": "STAGE1_PENDING_REGRESSION",
            "performance_magnitude_is_a_criterion": False})
        print(json.dumps({"stage1_failed": [k for k, v in criteria.items() if v is not True]}))
        return
    regression = _load("post_exposure_regression/pre_export_regression.json")
    checks = {
        "ruff": subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts",
                                "simulation", "deployment", "fusion", "api", "datasets",
                                "features", "models", "training", "evaluation", "preprocessing",
                                "federated"], cwd=ROOT).returncode,
        "pip_check": subprocess.run([sys.executable, "-m", "pip", "check"], cwd=ROOT).returncode}
    reg_ok = regression["status"] == "PASS" and all(v == 0 for v in checks.values())
    _write("regression_audit.json", {"chunked_python_regression": regression, "exit_codes": checks,
                                     "ci": "never queried or triggered",
                                     "status": "PASS" if reg_ok else "FAIL"})
    criteria["regression"] = reg_ok
    ok = all(v is True for v in criteria.values())
    _write("v2fleg0_criteria.json", {"criteria": criteria, "status": "PASS" if ok else "FAIL",
                                     "performance_magnitude_is_a_criterion": False})
    _write("run_manifest.json", {
        "checkpoint_id": "V2-FL-EVAL-001", "gate": "V2FLEG0", "models": 20,
        "datasets": ["INTERNAL_TEST (FL-lineage held-out)",
                     "INCART (post-freeze external second-look)"],
        "scientific_model_fits_added": 0, "federated_client_updates_added": 0,
        "model_promotion": False, "calibration_used": False, "ci_queried": False,
        "ci_triggered": False, "V2_FL_004_started": False, "status": "PASS" if ok else "FAIL"})
    print(json.dumps({"V2FLEG0": "PASS" if ok else "FAIL",
                      "failed": [k for k, v in criteria.items() if v is not True]}))


if __name__ == "__main__":
    main()
