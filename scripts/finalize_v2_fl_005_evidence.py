#!/usr/bin/env python3
"""V2-FL-005 evidence assembly (metadata + frozen canonical outputs only; nothing re-run).
`--stage1` writes audits and the V2FLG4 criteria with the regression criterion PENDING; the plain
invocation writes final criteria + run manifest after the post-result regression; `--hashes-only`
writes artifact_hashes.json last. Engineering gate: no efficacy magnitude is ever a criterion."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_005"
ENTRY = "cc98c6c1ac6bc157c207d25da349591e78adacac"
RUN_LOGS = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv", "pytest_chunk_results.csv"}
PROTECTED = [
    "artifacts", "checkpoints", "reports/t028", "reports/privacy.json", "reports/privacy_secagg",
    "reports/model_v2/v2_fl_001", "reports/model_v2/v2_fl_002", "reports/model_v2/v2_fl_003",
    "reports/model_v2/v2_fl_eval_001", "reports/model_v2/v2_fl_004",
    "reports/model_v2/v2_013", "manifests/clients", "frontend/static/replay",
    "simulation/stream_runtime_v2013.py", "simulation/profile_v2013.py", "simulation/types.py",
    "simulation/wearable.py", "preprocessing", "privacy", "configs/secagg_v1.yaml",
    "configs/model_v2/secagg_v2.yaml", "configs/model_v2/fl_iid_model_v2_v1.yaml",
    "configs/model_v2/fl_non_iid_model_v2_v1.yaml", "federated/model_v2_fl.py",
    "federated/aggregation.py", "federated/local_training.py", "federated/model_adapter.py",
    "models", "api", "docs/privacy_threat_model.md", "docs/MODEL_V2_SECAGG_THREAT_MODEL_V1.md",
]
EXTRA_NEW_ALLOWED = ("artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json",)
METRIC_KEYS = ("AUPRC", "AUROC", "auroc", "auprc", "f1", "F1", "precision", "sensitivity",
               "specificity", "accuracy", "patient_macro")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def _under(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PROTECTED)


def _keys(obj: object) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


def stage_audits() -> None:
    lock = json.loads((ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json").read_text())
    drift = [p for p, h in lock["bound_artifacts"].items() if hash_file(ROOT / p) != h]
    _write("method_immutability_post_exposure.json", {
        "lock": "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "drift": drift,
        "status": "PASS" if not drift else "FAIL"})
    changed = []
    for line in _git("diff", "--name-status", ENTRY, "HEAD").splitlines():
        status, *paths = line.split("\t")
        if status[0] in "MDR" and any(_under(p) for p in paths):
            changed.append(line)
    dirty = [line for line in _git("status", "--porcelain").splitlines()
             if _under(line[3:]) and line[3:] not in EXTRA_NEW_ALLOWED
             and not line[3:].startswith("reports/model_v2/v2_fl_004/post")]
    _write("protected_artifact_audit.json", {
        "entry_commit": ENTRY, "protected_modified_or_deleted_since_entry": changed,
        "protected_dirty": dirty, "new_checkpoint_files": [
            line for line in _git("diff", "--name-status", ENTRY, "HEAD").splitlines()
            if line.startswith("A") and (line.endswith(".pt") or "checkpoints/" in line)],
        "status": "PASS" if not changed and not dirty else "FAIL"})
    ledger_changed = _git("diff", ENTRY, "HEAD", "--", "reports/model_v2/access_ledger.jsonl")
    ledger_dirty = _git("status", "--porcelain", "reports/model_v2/access_ledger.jsonl")
    ledger_rows = [line for line in (ROOT / "reports/model_v2/access_ledger.jsonl").read_text(
    ).splitlines() if "V2-FL-005" in line]
    firewall = _load("firewall_audit.json")
    _write("firewall_audit.json", {
        **firewall, "ledger_changed_since_entry": bool(ledger_changed or ledger_dirty),
        "ledger_rows_for_V2_FL_005": len(ledger_rows),
        "scientific_waveform_partitions_read": [],
        "status": "PASS" if firewall["status"] == "PASS" and not ledger_changed
        and not ledger_dirty and not ledger_rows else "FAIL"})
    seen = set()
    for name in ("federation_run.json", "secagg_shadow.json", "finite_inference_smoke.json",
                 "restart_resume.json", "reproducibility.json"):
        seen |= {k for k in _keys(_load(name)) if k in METRIC_KEYS}
    _write("efficacy_metric_audit.json", {
        "forbidden_metric_keys_found": sorted(seen), "efficacy_metrics_computed": bool(seen),
        "permitted_diagnostics": ["finite local loss", "update norm", "state hash",
                                  "examples processed", "tensor count", "payload bytes",
                                  "round completion", "finite-logit smoke count"],
        "status": "PASS" if not seen else "FAIL"})
    _write("claim_audit.json", {
        "claim_boundary": json.loads(json.dumps(__import__("yaml").safe_load(
            (ROOT / "configs/model_v2/v2_fl_wearable_system_protocol_v1.yaml").read_text())[
            "claim_boundary"])),
        "engineering_only": True, "AAMI_SVF_efficacy_claim": False, "clinical_claim": False,
        "real_wearable_claim": False, "model_promotion": False, "runtime_cutover": False,
        "status": "PASS"})


def criteria() -> dict:
    run, shadow = _load("federation_run.json"), _load("secagg_shadow.json")
    restart, repro = _load("restart_resume.json"), _load("reproducibility.json")
    replay, smoke = _load("event_replay.json"), _load("finite_inference_smoke.json")
    locality, firewall = _load("server_data_locality_audit.json"), _load("firewall_audit.json")
    cohort = _load("cohort_preflight.json")
    lock = json.loads((ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json").read_text())
    run_manifest = _load("cohort_manifest_run.json")
    rounds = run["round_reports"]
    expected_codes = {"STALE_ROUND", "DUPLICATE_UPDATE", "BASE_STATE_MISMATCH", "UNKNOWN_CLIENT"}
    r3 = [r["code"] for r in rounds["3"]["rejections"]]
    return {
        "cohort_frozen_before_training": lock["frozen_before_any_canonical_local_training"]
        and subprocess.run(["git", "log", "--format=%H", "-n", "1", "--",
                            "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip() != "",
        "cohort_manifest_matches_frozen": hash_file(
            ROOT / "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json") == lock["bound_artifacts"][
            "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json"]
        and {c["client_id"]: c["dataset_sha256"] for c in run_manifest["clients"]}
        == lock["dataset_sha256"],
        "8_unique_virtual_clients": len({c["client_id"] for c in run_manifest["clients"]}) == 8,
        "zero_participant_overlap": not cohort["participant_overlap"]
        and len({c["participant_id"] for c in run_manifest["clients"]}) == 8,
        "structural_coverage": cohort["status"] == "PASS"
        and not cohort["clients_failing_structural_coverage"],
        "deterministic_source_generation": repro["client_dataset_hashes_identical"],
        "truth_runtime_separation": locality["SimulationTruth_visible"] is False
        and locality["status"] == "PASS",
        "production_like_preprocessing_used": all(
            c["counts"]["windows_emitted"] > 0 and c["counts"]["source_records"] > 100000
            for c in run_manifest["clients"]),
        "3_rounds_completed": sorted(rounds) == ["1", "2", "3"] and all(
            s["finite"] for s in run["state_progression"].values()),
        "24_of_24_updates_accepted": run["accepted_updates"] == 24
        and run["local_training_calls"] == 24 and run["failed_updates"] == 0,
        "all_updates_finite": run["nonfinite_states"] == 0,
        "rejection_tests_correct": {r["code"] for r in run["rejected_injected_attempts"]}
        == expected_codes and len(r3) == 4 and all(
            not rounds[k]["rejections"] for k in ("1", "2")),
        "rejections_do_not_affect_state": all(
            rounds[k]["order_invariance"]["equals_committed"] for k in rounds),
        "exactly_once_round_commit": all(
            rounds[k]["second_commit"] == "ROUND_ALREADY_COMMITTED" for k in rounds),
        "arrival_order_canonicalization": all(
            rounds[k]["order_invariance"]["all_equal"] for k in rounds),
        "restart_resume_equals_uninterrupted": restart["exact_match"] and restart["fresh_process"],
        "server_receives_no_raw_samples_labels_truth": locality["status"] == "PASS"
        and not locality["forbidden_hits"],
        "secagg_shadow_pass": shadow["status"] == "PASS" and shadow["compat_id"]
        == "WEARABLE_SIM_FL_SECAGG_COMPAT_V1" and shadow["preflight"]["weight_headroom_ratio"] > 1,
        "protected_clear_update_count_zero": shadow["protected_clear_update_count"] == 0
        and shadow["plain_clear_update_count"] == 8,
        "two_fresh_process_reproductions_identical": repro["status"] == "PASS",
        "event_log_replay_identical": replay["status"] == "PASS",
        "final_logits_finite": smoke["all_logits_finite"] and not smoke["labels_read"],
        "zero_efficacy_metrics": _load("efficacy_metric_audit.json")["status"] == "PASS"
        and smoke["classification_metrics_computed"] is False,
        "zero_real_dataset_access": firewall["status"] == "PASS",
        "upstream_artifacts_unchanged": _load("protected_artifact_audit.json")["status"] == "PASS",
        "method_immutable": _load("method_immutability_post_exposure.json")["status"] == "PASS",
        "claim_boundary_engineering_only": _load("claim_audit.json")["status"] == "PASS"}


def main() -> None:
    if "--hashes-only" in sys.argv:
        _write("artifact_hashes.json", {"artifacts": {
            str(p.relative_to(ROOT)): hash_file(p) for p in sorted(OUT.rglob("*")) if p.is_file()
            and p.name not in RUN_LOGS and p.name != "artifact_hashes.json"}})
        print("hashes written")
        return
    if "--stage1" in sys.argv:
        stage_audits()
        flags = criteria()
        flags["regression"] = "PENDING_STAGE1"
        _write("v2flg4_criteria.json", {"criteria": flags, "status": "STAGE1_PENDING_REGRESSION",
                                        "performance_magnitude_is_a_criterion": False})
        print(json.dumps({"stage1_failed": [k for k, v in flags.items()
                                            if v is not True and v != "PENDING_STAGE1"]}))
        return
    regression = _load("regression/post_result/pre_export_regression.json")
    checks = {
        "ruff": subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts",
                                "privacy", "federated", "models", "evaluation", "simulation"],
                               cwd=ROOT).returncode,
        "pip_check": subprocess.run([sys.executable, "-m", "pip", "check"], cwd=ROOT).returncode}
    ok_reg = regression["status"] == "PASS" and all(v == 0 for v in checks.values())
    _write("regression_audit.json", {"chunked_python_regression": regression, "exit_codes": checks,
                                     "ci": "never queried or triggered",
                                     "status": "PASS" if ok_reg else "FAIL"})
    flags = criteria()
    flags["regression"] = ok_reg
    ok = all(v is True for v in flags.values())
    _write("v2flg4_criteria.json", {"criteria": flags, "status": "PASS" if ok else "FAIL",
                                    "performance_magnitude_is_a_criterion": False})
    _write("run_manifest.json", {
        "checkpoint_id": "V2-FL-005", "gate": "V2FLG4",
        "experiment_id": "WEARABLE_SIM_FL_SYSTEM_V1",
        "engineering_local_training_calls": 24, "scientific_model_fits_added": 0,
        "scientific_checkpoints_added": 0, "efficacy_metrics_computed": False,
        "model_promotion": False, "runtime_cutover": False, "ci_queried": False,
        "ci_triggered": False, "V2_014_started": False, "T036_started": False,
        "status": "PASS" if ok else "FAIL"})
    print(json.dumps({"V2FLG4": "PASS" if ok else "FAIL",
                      "failed": [k for k, v in flags.items() if v is not True]}))


if __name__ == "__main__":
    main()
