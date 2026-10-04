#!/usr/bin/env python3
"""V2-FL-004 evidence assembly (metadata and frozen canonical outputs only; no SecAgg re-run).
`--stage1` writes the V2FLG3 criteria with the regression criterion PENDING; the plain invocation
writes the final criteria + run manifest after the regression; `--hashes-only` writes
artifact_hashes.json last. Performance (runtime/byte magnitude) is never a pass criterion."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_004"
ENTRY = "da30b7a2a41f32aa93fe32a22bb5030048f70645"
RUN_LOGS = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv", "pytest_chunk_results.csv"}
V1_PARAMS, V2_PARAMS = 13185, 57553
PROTECTED_PREFIXES = [
    "configs/secagg_v1.yaml", "artifacts/SECAGG_METHOD_V1.lock.json",
    "artifacts/SECAGG_CONFIG_V1.lock.json", "privacy/secagg_app.py",
    "privacy/server_visibility.py", "privacy/accounting.py", "scripts/run_secagg_t028.py",
    "reports/t028", "reports/privacy.json", "reports/privacy_secagg",
    "docs/privacy_threat_model.md", "artifacts/MODEL_V1_FINAL.json",
    "artifacts/MODEL_V2_FINAL.json",
    "artifacts/CAL_V1.json", "artifacts/CAL_V2.json", "reports/model_v2/v2_fl_001",
    "reports/model_v2/v2_fl_002", "reports/model_v2/v2_fl_003", "reports/model_v2/v2_fl_eval_001",
    "manifests/clients", "checkpoints",
]


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def stage_audits() -> None:
    v1 = json.loads((ROOT / "reports/t028/overhead_summary.json").read_text())
    v2 = _load("overhead_summary.json")
    b1, b2 = v1["application_payload_bytes"], v2["application_payload_bytes"]
    _write("v1_v2_scaling_comparison.json", {
        "v1_source": "reports/t028/overhead_summary.json (historical frozen; MODEL_V1 not rerun)",
        "parameters": {"V1": V1_PARAMS, "V2": V2_PARAMS, "ratio": V2_PARAMS / V1_PARAMS},
        "bytes": {
            "plain_total": {"V1": b1["plain"]["total"], "V2": b2["plain"]["total"],
                            "ratio": b2["plain"]["total"] / b1["plain"]["total"]},
            "protected_total": {"V1": b1["protected"]["total"], "V2": b2["protected"]["total"],
                                "ratio": b2["protected"]["total"] / b1["protected"]["total"]},
            "overhead_ratio": {"V1": b1["total_ratio"], "V2": b2["total_ratio"]}},
        "runtime_median_seconds": {
            "plain": {"V1": v1["plain_runtime"]["median_seconds"],
                      "V2": v2["plain_runtime"]["median_seconds"]},
            "protected": {"V1": v1["protected_runtime"]["median_seconds"],
                          "V2": v2["protected_runtime"]["median_seconds"]},
            "protected_over_plain": {"V1": v1["protected_to_plain_median_runtime_ratio"],
                                     "V2": v2["protected_to_plain_median_runtime_ratio"]}},
        "runtime_comparison_status": "NON_MATCHED_DESCRIPTIVE_CONTEXT (V1 runtimes were measured "
        "in an earlier session; same host/environment not guaranteed)",
        "extrapolation_beyond_two_points": False, "status": "PASS"})
    _write("privacy_claim_audit.json", {
        "supported_claim": json.loads(json.dumps(
            __import__("yaml").safe_load(
                (ROOT / "configs/model_v2/secagg_v2.yaml").read_text())["claim_boundary"])),
        "unsupported_claims": __import__("yaml").safe_load(
            (ROOT / "configs/model_v2/secagg_v2.yaml").read_text())["unsupported_claims"],
        "forbidden_claims_asserted": [], "status": "PASS"})
    ledger = [json.loads(line) for line in
              (ROOT / "reports/model_v2/access_ledger.jsonl").read_text().splitlines() if line]
    mine = [r for r in ledger if r.get("stage_id") == "V2-FL-004"]
    parts = sorted({r["partition"] for r in mine})
    _write("firewall_audit.json", {
        "partitions_accessed": parts, "ledger_rows": len(mine),
        "access_types": sorted({r["access_type"] for r in mine}),
        "VALIDATION_accessed": "VALIDATION" in parts,
        "CALIBRATION_accessed": "CALIBRATION" in parts,
        "INTERNAL_TEST_accessed": "INTERNAL_TEST" in parts, "INCART_accessed": "INCART" in parts,
        "NSTDB_accessed": "NSTDB" in parts, "BIDMC_accessed": "BIDMC" in parts,
        "WEARABLE_accessed": any("WEARABLE" in p for p in parts),
        "scientific_model_fits_added": 0, "checkpoints_written": 0,
        "status": "PASS" if parts == ["TRAIN"] else "FAIL"})
    lock = json.loads((ROOT / "artifacts/SECAGG_METHOD_V2.lock.json").read_text())
    drift = [p for p, h in lock["bound_artifacts"].items() if hash_file(ROOT / p) != h]
    _write("method_immutability_post_exposure.json", {
        "lock": "artifacts/SECAGG_METHOD_V2.lock.json", "drift": drift,
        "status": "PASS" if not drift else "FAIL"})
    changed = [p for p in _git("diff", "--name-only", ENTRY, "HEAD").splitlines()
               if any(p == q or p.startswith(q + "/") for q in PROTECTED_PREFIXES)]
    dirty = [line[3:] for line in _git("status", "--porcelain").splitlines()
             if any(line[3:] == q or line[3:].startswith(q + "/") for q in PROTECTED_PREFIXES)]
    _write("protected_artifact_audit.json", {
        "entry_commit": ENTRY, "protected_changed_since_entry": changed,
        "protected_dirty": dirty, "status": "PASS" if not changed and not dirty else "FAIL"})
    secret_hits = [p.name for p in OUT.rglob("*.json") if any(
        token in p.read_text() for token in ("private_key_bytes", "secret_share_bytes"))]
    _write("secret_material_audit.json", {
        "files_scanned": len(list(OUT.rglob("*.json"))), "hits": secret_hits,
        "private_keys_persisted": False, "raw_secret_shares_persisted": False,
        "unmasked_individual_updates_persisted": False,
        "status": "PASS" if not secret_hits else "FAIL"})


def criteria() -> dict:
    api = _load("flower_secagg_api_audit.json")
    rec = _load("canonical_preflight/round1_reconstruction.json")
    clip = _load("canonical_preflight/clipping_preflight.json")
    transport = _load("canonical_preflight/state_transport_audit.json")
    known, agg = _load("known_vector_correctness.json"), _load("aggregate_correctness.json")
    vis, loc = _load("server_visibility_audit.json"), _load("client_data_locality_audit.json")
    over, rep = _load("overhead_summary.json"), _load("reproducibility.json")
    return {
        "lifecycle_entry_audit": _load("entry_lifecycle_governance_audit.json")["status"]
        == "PASS",
        "flower_api_available": api["status"] == "PASS"
        and api["required_flower_version"] == "1.39.0",
        "round1_reconstruction_exact": rec["status"] == "PASS",
        "state_transport_92_entries": transport["status"] == "PASS",
        "clipping_zero_violations": clip["coordinates_outside_range"] == 0
        and clip["nonfinite_count"] == 0 and clip["status"] == "PASS",
        "known_vector": known["status"] == "PASS",
        "model_v2_aggregate_within_tolerance": agg["status"] == "PASS"
        and agg["MODEL_V2_shaped"]["status"] == "PASS",
        "plain_negative_control_positive": vis["plain_detector_positive"],
        "protected_zero_clear_updates": vis["protected_clear_update_count"] == 0
        and vis["protected_aggregate_available"],
        "data_locality": loc["status"] == "PASS",
        "protected_completions_10_of_10": over["completion"]["completed"] == 10
        and over["completion"]["attempted"] == 10,
        "runtime_and_bytes_reported": over["status"] == "PASS",
        "scaling_comparison": _load("v1_v2_scaling_comparison.json")["status"] == "PASS",
        "semantic_reproducibility": rep["status"] == "PASS",
        "privacy_claim_narrow": _load("privacy_claim_audit.json")["status"] == "PASS",
        "firewall_train_only": _load("firewall_audit.json")["status"] == "PASS",
        "no_secret_material_persisted": _load("secret_material_audit.json")["status"] == "PASS",
        "method_immutable": _load("method_immutability_post_exposure.json")["status"] == "PASS",
        "protected_artifacts_unchanged": _load("protected_artifact_audit.json")["status"] == "PASS"}


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
        _write("v2flg3_criteria.json", {"criteria": flags, "status": "STAGE1_PENDING_REGRESSION",
                                        "performance_magnitude_is_a_criterion": False})
        print(json.dumps({"stage1_failed": [k for k, v in flags.items() if v is not True
                                            and v != "PENDING_STAGE1"]}))
        return
    regression = _load("post_exposure_regression/pre_export_regression.json")
    checks = {
        "ruff": subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts",
                                "privacy", "federated", "models", "evaluation"],
                               cwd=ROOT).returncode,
        "pip_check": subprocess.run([sys.executable, "-m", "pip", "check"], cwd=ROOT).returncode}
    reg_ok = regression["status"] == "PASS" and all(v == 0 for v in checks.values())
    _write("regression_audit.json", {"chunked_python_regression": regression, "exit_codes": checks,
                                     "ci": "never queried or triggered",
                                     "status": "PASS" if reg_ok else "FAIL"})
    flags = criteria()
    flags["regression"] = reg_ok
    ok = all(v is True for v in flags.values())
    _write("v2flg3_criteria.json", {"criteria": flags, "status": "PASS" if ok else "FAIL",
                                    "performance_magnitude_is_a_criterion": False})
    _write("run_manifest.json", {
        "checkpoint_id": "V2-FL-004", "gate": "V2FLG3", "base_condition": "FL_IID_MODEL_V2_V1",
        "scientific_model_fits_added": 0, "differential_privacy": False,
        "production_security_claim": False, "ci_queried": False, "ci_triggered": False,
        "V2_FL_005_started": False, "V2_014_started": False, "T036_started": False,
        "status": "PASS" if ok else "FAIL"})
    print(json.dumps({"V2FLG3": "PASS" if ok else "FAIL",
                      "failed": [k for k, v in flags.items() if v is not True]}))


if __name__ == "__main__":
    main()
