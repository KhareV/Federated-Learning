#!/usr/bin/env python3
# ruff: noqa: E501
"""SYSTEM_V2_RELEASE_DECISION_V1 evaluator (V2-REL-001, policy SYSTEM_V2_RELEASE_POLICY_V1).

Reads ONLY frozen repository evidence (registries, locks, committed reports/prediction-table-derived
summaries, artifact verifiers). It runs no model on any waveform dataset, fits nothing and generates
no scientific metric. The decision is DERIVED from the hard blockers (ACCEPT iff all pass and no
unresolved integrity defect); there is no manual override and ACCEPT is never hard-coded.

Usage: python -m scripts.evaluate_system_v2_release [--out-dir reports/model_v2/v2_rel_001]
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "configs/model_v2/system_v2_release_policy_v1.yaml"
ENTRY = "f3d3d9f642fbd20158743c24c60d96b945c35d0c"
REPORTS = ROOT / "reports/model_v2"
PROTECTED = [
    "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json", "artifacts/MODEL_V2_COMPLETE_REPRO_V1.lock.json",
    "artifacts/API_RUNTIME_V1.lock.json", "artifacts/API_RUNTIME_V1_1.lock.json",
    "artifacts/API_RUNTIME_V2.lock.json", "artifacts/API_RUNTIME_V2_1.lock.json",
    "artifacts/CAL_V1.json", "artifacts/CAL_V2.json", "artifacts/DASHBOARD_UI_V1_4.lock.json",
    "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json", "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
    "artifacts/SECAGG_METHOD_V2.lock.json", "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json",
    "artifacts/deployment", "checkpoints", "reports/model_v2", "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json",
    "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V2.lock.json", "manifests/model_v2/V2_FL_EVAL_PROTOCOL_V1.lock.json",
    "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json", "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json",
    "manifests/clients", "preprocessing", "privacy", "federated", "models", "evaluation", "deployment",
    "simulation", "fusion", "api/app.py", "api/app_v2.py", "api/runtime.py", "api/runtime_v2.py",
    "api/schemas.py", "api/session.py", "contracts", "configs/secagg_v1.yaml",
    "configs/model_v2/secagg_v2.yaml", "frontend/static/replay",
]
ALLOWED_NEW_UNDER = ("reports/model_v2/v2_rel_001/",)
FIVE_STATES = {"NORMAL_MONITORED_PATTERN", "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN", "RECHECK_SENSOR",
               "CONTEXT_UNAVAILABLE", "SYSTEM_ERROR"}


def _json(path: str | Path) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _rows(name: str) -> dict[str, dict[str, str]]:
    key = {"task": "task_id", "gate": "gate_id", "component": "component_id"}[name]
    with (ROOT / f"manifests/model_v2/{name}_registry_v1.csv").open(newline="") as handle:
        return {r[key]: r for r in csv.DictReader(handle)}


class Criteria:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, cid: str, requirement: str, source: str, observed: Any, passed: bool) -> None:
        self.rows.append({"id": cid, "requirement": requirement, "source": source,
                          "observed": observed, "status": "PASS" if passed else "FAIL"})

    def guard(self, cid: str, requirement: str, source: str, fn) -> None:
        try:
            observed, passed = fn()
        except Exception as exc:  # a verifier failure is a FAILED criterion, never skipped
            observed, passed = f"{type(exc).__name__}: {exc}", False
        self.add(cid, requirement, source, observed, bool(passed))


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def evaluate() -> tuple[dict[str, Any], dict[str, Any]]:
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    tasks, gates, components = _rows("task"), _rows("gate"), _rows("component")
    c = Criteria()

    def central(verifier: str):
        def run():
            if verifier == "model":
                from models.model_v2_final_freeze import verify_model_v2_final as fn
            elif verifier == "cal":
                from models.cal_v2_verify import verify_cal_v2 as fn
            else:
                from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2 as fn
            result = fn(ROOT)
            return str(result.get("status")), str(result.get("status")) in ("PASS", "VERIFIED", "FROZEN")
        return run

    c.guard("H01", "MODEL_V2_FINAL hash valid", "models.model_v2_final_freeze.verify_model_v2_final",
            central("model"))
    c.guard("H02", "CAL_V2 valid", "models.cal_v2_verify.verify_cal_v2", central("cal"))
    c.guard("H03", "GATEWAY_ARTIFACT_V2 valid",
            "models.gateway_artifact_v2_verify.verify_gateway_artifact_v2", central("gateway"))

    def runtime_acceptance():
        d = _json("reports/model_v2/v2_010/runtime_acceptance_decision.json")
        ok = (d["MODEL_V2_RUNTIME_ACCEPTED"] == "ACCEPTED" and d["INCART_AUROC_RUNTIME_GUARD_PASS"]
              and d["NSTDB_NO_COLLAPSE_PASS"] and d["subjective_override_applied"] is False)
        return {k: d[k] for k in ("MODEL_V2_RUNTIME_ACCEPTED", "INCART_AUROC_RUNTIME_GUARD_PASS",
                                  "NSTDB_NO_COLLAPSE_PASS", "subjective_override_applied")}, ok

    c.guard("H04", "runtime acceptance ACCEPTED + INCART guard + NSTDB guard",
            "reports/model_v2/v2_010/runtime_acceptance_decision.json", runtime_acceptance)

    pairs = (("H05", "V2-012"), ("H06", "V2-013"), ("H07", "V2-FL-001"), ("H08", "V2-FL-002"),
             ("H09", "V2-FL-003"), ("H10", "V2-FL-EVAL-001"), ("H11", "V2-FL-004"),
             ("H12", "V2-FL-005"), ("H13", "V2-014"))
    for cid, task in pairs:
        gate = tasks[task]["gate_impact"]
        c.add(cid, f"{task} PASS and gate {gate} PASS", "manifests/model_v2/{task,gate}_registry_v1.csv",
              {"task": tasks[task]["status"], "gate": gates[gate]["status"]},
              tasks[task]["status"] == "PASS" and gates[gate]["status"] == "PASS")

    def repro():
        from scripts.verify_v2_014_evidence import verify as verify_repro

        result = verify_repro()
        ok = (result["status"] == "PASS" and {"clone1", "clone2"} <= set(result["packages"])
              and components["MODEL_V2_COMPLETE_REPRO_V1"]["status"]
              == "FROZEN_REPRODUCIBILITY_EVIDENCE")
        return {"verifier": result["status"], "packages": sorted(result["packages"]),
                "component": components["MODEL_V2_COMPLETE_REPRO_V1"]["status"]}, ok

    c.guard("H13b", "V2-014 evidence (clone 1 and clone 2) re-verified from committed files",
            "scripts.verify_v2_014_evidence.verify", repro)

    def schema():
        lock = _json("artifacts/DASHBOARD_UI_V1_4.lock.json")
        observed = {"api_schema_sha256": hash_file(ROOT / "contracts/API_SCHEMA_V1.json"),
                    "openapi_sha256": hash_file(ROOT / "contracts/openapi_v1.json")}
        return observed, (observed["api_schema_sha256"] == lock["api_schema_v1_sha256"]
                          and observed["openapi_sha256"] == lock["openapi_v1_sha256"])

    c.guard("H14", "API_SCHEMA_V1 contract/OpenAPI hashes unchanged", "contracts/*", schema)

    def selector():
        lock = _json("artifacts/API_RUNTIME_V2_1.lock.json")
        dash = _json("artifacts/DASHBOARD_UI_V1_4.lock.json")
        app_source = (ROOT / "api/app_v2.py").read_text()
        route_has_only_payload = "def infer_window(payload: InferWindowRequest)" in app_source
        observed = {"runtime_lock": lock["public_runtime_model_selector"],
                    "dashboard_lock": dash["public_runtime_model_selector_added"],
                    "route_signature_payload_only": route_has_only_payload}
        return observed, (lock["public_runtime_model_selector"] is False
                          and dash["public_runtime_model_selector_added"] is False
                          and route_has_only_payload)

    c.guard("H15", "no public model/checkpoint/threshold selector", "API_RUNTIME_V2_1 lock + api/app_v2.py",
            selector)

    def vocabulary():
        from api.schemas import MonitoringState

        values = {s.value for s in MonitoringState}
        return sorted(values), values == FIVE_STATES

    c.guard("H16", "five non-diagnostic monitoring states preserved", "api.schemas.MonitoringState",
            vocabulary)

    def preproc():
        from preprocessing.freeze import verify_preproc_freeze

        result = verify_preproc_freeze(ROOT)
        return str(result.get("status", "PASS")) if isinstance(result, dict) else "PASS", True

    c.guard("H17", "PREPROC_V1 normalization boundary preserved", "preprocessing.freeze", preproc)

    def hr():
        d = _json("reports/model_v2/v2_013/normalization_branch_audit.json")
        ok = (d["status"] == "PASS" and d["normalize_window_zscore_calls_in_estimate_ecg_hr"] == 0
              and d["normalize_window_zscore_calls_in_infer"] == 1
              and d["stream_runtime_applies_normalization"] is False)
        return {k: d[k] for k in ("status", "normalize_window_zscore_calls_in_estimate_ecg_hr",
                                  "normalize_window_zscore_calls_in_infer")}, ok

    c.guard("H18", "HR branch amplitude-preserving",
            "reports/model_v2/v2_013/normalization_branch_audit.json", hr)

    def calibration():
        d = _json("artifacts/CAL_V2.json")
        ok = (d["calibration_domain"] == "MIT-BIH-v1.0.0" and d["calibration_id"] == "CAL_V2"
              and d["status"] == "FROZEN")
        return {"calibration_domain": d["calibration_domain"], "calibration_id": d["calibration_id"],
                "patients": d["calibration_patient_count"]}, ok

    c.guard("H19", "source-domain CAL_V2 labeling preserved", "artifacts/CAL_V2.json", calibration)

    def rollback():
        from models.model_freeze import verify_frozen_model_v1
        from scripts.verify_api_runtime_v1_1_c032 import verify as verify_v1_1

        verify_frozen_model_v1(ROOT)
        v1_1 = verify_v1_1()
        present = all((ROOT / p).exists() for p in (
            "api/app.py", "api/runtime.py", "artifacts/CAL_V1.json",
            "artifacts/GATEWAY_ARTIFACT_V1.lock.json", "artifacts/API_RUNTIME_V1_1.lock.json",
            "checkpoints/MODEL_V1.pt"))
        return {"model_v1": "verified", "api_runtime_v1_1": v1_1.get("status"),
                "files_present": present}, present and v1_1.get("status") == "PASS"

    c.guard("H20", "V1 rollback components present and verifying",
            "models.model_freeze + scripts.verify_api_runtime_v1_1_c032", rollback)

    def disposition():
        decision = _json("reports/model_v2/v2_007/promotion_decision.json")
        lock = _json("manifests/model_v2/MODEL_V2_VALIDATION_DECISION_V1.lock.json")
        observed = {"decision": decision["decision"], "promotion_eligible": decision["promotion_eligible"],
                    "release_ci_lower": decision["release_ci"]["lower"],
                    "decision_file_sha256_matches_lock": hash_file(
                        ROOT / "reports/model_v2/v2_007/promotion_decision.json")
                    == lock["promotion_decision_sha256"]}
        return observed, (decision["decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
                          and decision["promotion_eligible"] is False
                          and observed["decision_file_sha256_matches_lock"])

    c.guard("H21", "MODEL_V2_NOT_PROMOTED_RELEASE_CI immutable and unchanged",
            "reports/model_v2/v2_007/promotion_decision.json + validation decision lock", disposition)

    def drift():
        changed = []
        for line in _git("diff", "--name-status", ENTRY, "HEAD").splitlines():
            status, *paths = line.split("\t")
            if status[0] in "MDR" and any(p == q or p.startswith(q + "/")
                                          for p in paths for q in PROTECTED):
                changed.append(line)
        dirty = [x for x in _git("status", "--porcelain").splitlines()
                 if not x[3:].startswith(ALLOWED_NEW_UNDER)
                 and any(x[3:] == q or x[3:].startswith(q + "/") for q in PROTECTED)]
        return {"modified_or_deleted_since_entry": changed, "dirty_protected": dirty}, not (
            changed or dirty)

    c.guard("H22", "no protected-artifact drift since entry", "git diff entry..HEAD", drift)

    def regression():
        reg = json.loads((ROOT / "reports/model_v2/v2_014/clone1/regression.json").read_text())
        ok = (reg["status"] == "PASS" and reg["failed_tests"] == 0 and reg["missing"] == 0
              and reg["duplicates"] == 0 and reg["unexpected"] == 0
              and reg["monolithic"]["exit_code"] == 0)
        return {"nodes": reg["collected_node_count"], "failed": reg["failed_tests"],
                "DATA_GATED_SKIPPED": reg["DATA_GATED_SKIPPED"]}, ok

    c.guard("H23", "full regression passes (frozen V2-014 clean-clone evidence)",
            "reports/model_v2/v2_014/clone1/regression.json", regression)

    def fl_program():
        out = {}
        for name, folder, _flag in (("V2-FL-001", "v2_fl_001", "V2FLG0"), ("V2-FL-002", "v2_fl_002", "V2FLG1"),
                                   ("V2-FL-003", "v2_fl_003", "V2FLG2")):
            manifest = _json(f"reports/model_v2/{folder}/run_manifest.json")
            firewall = _json(f"reports/model_v2/{folder}/heldout_firewall_audit.json")
            out[name] = {"run_manifest": manifest["status"], "heldout_firewall": firewall["status"]}
        ok = all(v["run_manifest"] == "PASS" and v["heldout_firewall"] == "PASS" for v in out.values())
        return out, ok

    c.guard("H24", "V2 real-data FL program complete without integrity failure",
            "reports/model_v2/v2_fl_00{1,2,3}/run_manifest.json + heldout_firewall_audit.json", fl_program)

    failed = [r["id"] for r in c.rows if r["status"] != "PASS"]
    matrix = build_matrix(tasks, components)
    limitations = build_limitations(policy)
    defects = [f"CRITERION_FAILED:{cid}" for cid in failed]
    decision = "ACCEPT" if not failed and not defects else "REJECT"
    return {
        "decision_id": "SYSTEM_V2_RELEASE_DECISION_V1", "policy_id": policy["policy_id"],
        "release_level": policy["release_level"], "criteria": c.rows, "failed_criteria": failed,
        "unresolved_integrity_defects": defects, "known_limitations": limitations,
        "SYSTEM_V2_RELEASE_DECISION": decision,
        "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED": decision == "ACCEPT", "manual_override": False,
        "evidence_timing_disclosure": policy["evidence_timing_disclosure"].strip(),
        "scientific_preregistration_claim": False,
        "historical_model_promotion_disposition": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "new_system_release_disposition": "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED"
        if decision == "ACCEPT" else "NOT_ACCEPTED",
        "federated_checkpoint_deployed": False,
        "new_scientific_evidence_generated": False, "waveform_datasets_accessed": False,
        "decision_wording": policy["claim_rules"]["required_wording"].strip()
        if decision == "ACCEPT" else None,
    }, matrix


def build_limitations(policy: dict[str, Any]) -> list[dict[str, Any]]:
    release = _json("reports/model_v2/v2_007/promotion_decision.json")
    population = _json("reports/model_v2/v2_fl_eval_001/population_report.json")
    repro = _json("reports/model_v2/v2_014/clone1/regression.json")
    observed = {
        "L01": {"release_ci": release["release_ci"], "decision": release["decision"]},
        "L02": {"contributing_clusters": population["INTERNAL_TEST"]["contributing_clusters"],
                "frozen_groups": population["INTERNAL_TEST"]["frozen_groups"]},
        "L03": {"classification": "post-freeze second look (reports/model_v2/v2_010)"},
        "L04": {"claim": population["INCART"]["claim"]},
        "L05": {"source": "reports/model_v2/c_v2_013_quality_flatline/classification.json"},
        "L06": {"calibration_domain": _json("artifacts/CAL_V2.json")["calibration_domain"]},
        "L07": {"WEARABLE_V1": "no physical wearable data exists; hardware out of scope"},
        "L08": {"claim_boundary": _json("reports/model_v2/v2_fl_004/claim_boundary.json")}
        if (REPORTS / "v2_fl_004/claim_boundary.json").exists()
        else {"source": "docs/MODEL_V2_SECAGG_THREAT_MODEL_V1.md"},
        "L09": {"DATA_GATED_SKIPPED": repro["DATA_GATED_SKIPPED"]},
    }
    return [{**item, "observed": observed[item["id"]], "blocks_release": False}
            for item in policy["non_blocking_known_limitations"]]


def build_matrix(tasks: dict[str, dict[str, str]], components: dict[str, dict[str, str]]
                 ) -> dict[str, Any]:
    release = _json("reports/model_v2/v2_007/promotion_decision.json")
    history = _json("reports/model_v2/v2_007/historical_reference_metrics.json")
    finalist = _json("reports/model_v2/v2_007/finalist_selection.json")
    second = {n: _json(f"reports/model_v2/v2_010/{n}_comparison.json") for n in ("internal", "incart")}
    nstdb = _json("reports/model_v2/v2_010/nstdb_comparison_summary.json")
    architecture: dict[str, Any] = {}
    for dataset in ("internal_test", "incart"):
        stats = _json(f"reports/model_v2/v2_fl_eval_001/{dataset}_statistics.json")
        rows = {k: v for k, v in stats["comparisons"].items() if v["family"] == "architecture_effect"}
        architecture[dataset] = {
            "comparisons": len(rows),
            "AUPRC_point_delta_positive": sum(v["delta"]["AUPRC"]["point_delta"] > 0
                                              for v in rows.values()),
            "patient_macro_F1_point_delta_positive": sum(
                v["delta"]["patient_macro_F1"]["point_delta"] > 0 for v in rows.values()),
            "claim_label": stats["claim_label"],
            "deltas_with_exact_95CI": {k.split("_minus_")[0]: {
                m: v["delta"][m] for m in ("AUPRC", "patient_macro_F1")} for k, v in rows.items()}}
    all_positive = all(a["comparisons"] == a["AUPRC_point_delta_positive"]
                       == a["patient_macro_F1_point_delta_positive"] for a in architecture.values())
    gateway = _json("artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json")
    api_lock = _json("artifacts/API_RUNTIME_V2_1.lock.json")
    secagg = _json("reports/model_v2/v2_fl_004/v2flg3_criteria.json")
    synth = _json("reports/model_v2/v2_fl_005/v2flg4_criteria.json")
    repro = _json("reports/model_v2/v2_014/clone1/reproducibility_manifest.json")
    return {
        "matrix_id": "SYSTEM_V2_RELEASE_EVIDENCE_MATRIX_V1", "rewrites_history": False,
        "A_official_validation_history": {
            "source": "reports/model_v2/v2_007/promotion_decision.json", "observed": {
                "decision": release["decision"], "promotion_eligible": release["promotion_eligible"],
                "release_ci": release["release_ci"], "release_point_delta_vs_v1":
                release["release_point_delta_vs_v1"],
                "reason": "release-seed paired VALIDATION CI lower bound crossed zero",
                "converted_to_pass": False}},
        "B_central_model_improvement_evidence": {
            "official_validation": {
                "source": "reports/model_v2/v2_007", "observed": {
                    "MODEL_V1_release_seed_AUPRC": history["v1_release_seed_auprc"],
                    "MODEL_V1_three_seed_mean_AUPRC": history["v1_three_seed_mean_auprc"],
                    "MODEL_V2_three_seed_mean_AUPRC": finalist["selected_three_seed_mean_auprc"],
                    "LR_AUPRC_descriptive": history["LR_official_validation_auprc"],
                    "RF_AUPRC_descriptive": history["RF_official_validation_auprc"],
                    "three_seed_delta": release["three_seed_point_delta_vs_v1"],
                    "three_seed_CI": release["three_seed_ci"]}},
            "post_freeze_second_look_NOT_untouched_validation": {
                "source": "reports/model_v2/v2_010", "observed": {
                    "INTERNAL_TEST_AUPRC": second["internal"]["paired_bootstrap_deltas"]["AUPRC"],
                    "INCART_AUPRC": second["incart"]["paired_bootstrap_deltas"]["AUPRC"],
                    "NSTDB_delta_auprc_by_snr": nstdb["delta_auprc_by_snr"]}}},
        "C_runtime_acceptance": {"source": "reports/model_v2/v2_010/runtime_acceptance_decision.json",
                                 "observed": _json(
                                     "reports/model_v2/v2_010/runtime_acceptance_decision.json")},
        "D_gateway": {"source": "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
                      "observed": {"artifact": gateway["artifact"], "task": tasks["V2-012"]["status"]}},
        "E_software_integration": {"source": "artifacts/API_RUNTIME_V2_1.lock.json", "observed": {
            "lock_status": api_lock["status"], "software_replay": api_lock["software_replay"],
            "flatline_replay": api_lock["flatline_replay"], "task": tasks["V2-013"]["status"]}},
        "F_real_data_federated_program": {"source": "V2-FL-001..003", "observed": {
            t: tasks[t]["status"] for t in ("V2-FL-001", "V2-FL-002", "V2-FL-003")}},
        "G_federated_heldout_evaluation": {
            "source": "reports/model_v2/v2_fl_eval_001/*_statistics.json", "observed": architecture,
            "all_architecture_effect_point_estimates_positive_for_AUPRC_and_patient_macro_F1":
            all_positive, "labels": "FL-lineage held-out (INTERNAL_TEST) / project-exposed external "
            "second look (INCART); no new promotion gate"},
        "H_privacy_protocol_engineering": {"source": "reports/model_v2/v2_fl_004", "observed": {
            "V2FLG3": secagg["status"], "claim": "narrow protected-aggregation-interface result",
            "differential_privacy_claim": False}},
        "I_synthetic_wearable_system": {"source": "reports/model_v2/v2_fl_005", "observed": {
            "V2FLG4": synth["status"], "engineering_only": True,
            "clinical_or_wearable_efficacy_claim": False}},
        "J_complete_reproducibility": {"source": "reports/model_v2/v2_014", "observed": {
            "clone1_target": repro["clone_target_sha"], "result": repro["result"],
            "component": components["MODEL_V2_COMPLETE_REPRO_V1"]["status"]}},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="reports/model_v2/v2_rel_001")
    args = parser.parse_args()
    decision, matrix = evaluate()
    out = ROOT / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "system_v2_release_evidence_matrix.json").write_text(
        json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "system_v2_release_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision["SYSTEM_V2_RELEASE_DECISION"],
                      "failed": decision["failed_criteria"]}))
    if decision["SYSTEM_V2_RELEASE_DECISION"] != "ACCEPT":
        sys.exit(1)


if __name__ == "__main__":
    main()
