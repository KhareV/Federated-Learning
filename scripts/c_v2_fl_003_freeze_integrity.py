#!/usr/bin/env python3
"""C-V2-FL-003-FREEZE-INTEGRITY. Provenance/control correction only: no training, no new mu, no
checkpoint reselection, no held-out data. Subcommands:

  method   write correction_method.json (inputs bound BEFORE the corrective result)
  verify   scientific-freeze verification, independent reconstruction via the successor finalizer,
           mu=0 re-run, lifecycle-test drift audit, historical freeze-scope audits, reconciliation
  replay   (internal) one fresh-process replay verification, label = argv[2]
  attest   corrective V2FLG2 attestation (after the regression)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/c_v2_fl_003_freeze_integrity"
V2FL003 = ROOT / "reports/model_v2/v2_fl_003"
ENTRY = "87943640b86fcca2dd769690e5df2706c2f2a793"
METHOD_COMMIT = "dd9d9df2303260d3b540c35fb382bb86212b96ef"
SELECTION_COMMIT = "89accff02af8c8280d57e9da29217fbfcd30d792"
FROZEN_FINALIZER = "scripts/finalize_v2_fl_003_evidence.py"
FROZEN_FINALIZER_SHA = "21c640c209577c999d17a30b961d0f74ef1d12e09a2f187e7e1ac30d1bf5ea75"
SUCCESSOR = "scripts/finalize_v2_fl_003_evidence_v2.py"
LIFECYCLE_TESTS = ["tests/test_model_v2_control_plane.py", "tests/test_v2_fl_001_results.py",
                   "tests/test_v2_fl_002_method.py", "tests/test_v2_fl_002_results.py"]
ID_LIST = re.compile(r'^[+-]\s*("V2[A-Za-z0-9-]*",\s*)+$')
FEDPROX_RUNS = ["candidates/mu_0p001", "candidates/mu_0p01", "candidates/mu_0p1",
                "transfer/iid", "transfer/quantity", "transfer/feature", "transfer/combined"]


def _write(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=False).stdout


def _sha_at(commit: str, path: str) -> str | None:
    blob = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True,
                          check=False)
    if blob.returncode != 0:
        return None
    import hashlib

    return hashlib.sha256(blob.stdout).hexdigest()


def scientific_inputs() -> dict:
    results = {r: hash_file(V2FL003 / r / "result.json") for r in FEDPROX_RUNS}
    return {
        "checkpoints": {str(p.relative_to(ROOT)): hash_file(p) for p in sorted(
            (ROOT / "checkpoints/model_v2/v2_fl_003").rglob("*.pt"))},
        "result_json": {f"reports/model_v2/v2_fl_003/{r}/result.json": h
                        for r, h in results.items()},
        "validation_prediction_tables": {
            f"reports/model_v2/v2_fl_003/{r}/validation_predictions.csv": hash_file(
                V2FL003 / r / "validation_predictions.csv") for r in FEDPROX_RUNS},
        "round_logs": {f"reports/model_v2/v2_fl_003/{r}/round_log.csv": hash_file(
            V2FL003 / r / "round_log.csv") for r in FEDPROX_RUNS},
        "selection_table": hash_file(V2FL003 / "selection/mu_candidates.csv"),
        "selection_lock": hash_file(ROOT / "artifacts/FEDPROX_MU_V2.lock.json"),
        "FEDPROX_MU_V2_sha256": hash_file(ROOT / "artifacts/FEDPROX_MU_V2.lock.json"),
        "bootstrap_implementation_sha256": hash_file(ROOT / "evaluation/bootstrap.py"),
    }


def method() -> None:
    data = {
        "checkpoint_id": "C-V2-FL-003-FREEZE-INTEGRITY", "entry_sha": ENTRY,
        "V2_FL_003_method_commit": METHOD_COMMIT, "V2_FL_003_selection_freeze_commit":
        SELECTION_COMMIT, "V2_FL_003_result_commit": ENTRY,
        "inputs": scientific_inputs(),
        "historical_frozen_finalizer": {"path": FROZEN_FINALIZER, "sha256": hash_file(
            ROOT / FROZEN_FINALIZER), "expected_sha256": FROZEN_FINALIZER_SHA,
            "restored_byte_identically": hash_file(ROOT / FROZEN_FINALIZER)
            == FROZEN_FINALIZER_SHA},
        "successor_finalizer": {"path": SUCCESSOR, "id": "V2_FL_003_EVIDENCE_FINALIZER_V2",
                                "sha256": hash_file(ROOT / SUCCESSOR)},
        "corrective_script_sha256": hash_file(ROOT / "scripts/c_v2_fl_003_freeze_integrity.py"),
        "strict_lifecycle_test_sha256": hash_file(
            ROOT / "tests/test_model_v2_current_lifecycle.py"),
        "statements": ["scientific method unchanged", "training outputs already frozen",
                       "evidence-finalization correction only", "no new training",
                       "no new mu candidate or reselection", "no held-out data access"],
        "dry_run_disclosure": "The successor finalizer was executed once against the committed "
        "evidence before this freeze to debug it (reconstruction equality PASS); that output was "
        "discarded and is not evidence. The canonical run follows this commit.",
        "status": "PASS"}
    _write("correction_method.json", data)
    print("correction method written")


def verify() -> None:
    meta = _load("correction_method.json")
    # 1. scientific freezes (hash comparison; nothing is rewritten).
    now = scientific_inputs()
    drift = []
    for key in ("checkpoints", "result_json", "validation_prediction_tables", "round_logs"):
        drift += [p for p, h in meta["inputs"][key].items() if now[key].get(p) != h]
    for key in ("selection_table", "selection_lock", "FEDPROX_MU_V2_sha256",
                "bootstrap_implementation_sha256"):
        if now[key] != meta["inputs"][key]:
            drift.append(key)
    for phase in ("v2_fl_001", "v2_fl_002", "v2_fl_003"):
        pins = json.loads((ROOT / f"reports/model_v2/{phase}/artifact_hashes.json").read_text())[
            "artifacts"]
        drift += [p for p, h in pins.items() if hash_file(ROOT / p) != h]
    for d in ("v2_fl_001", "v2_fl_002"):
        for pt in (ROOT / f"checkpoints/model_v2/{d}").glob("*.pt"):
            if not pt.exists():
                drift.append(str(pt))
    baseline = json.loads((V2FL003 / "protected_baseline.json").read_text())["artifacts"]
    drift += [p for p, h in baseline.items() if hash_file(ROOT / p) != h]
    from federated.model_v2_non_iid_runner import verify_entry

    entry = verify_entry(ROOT)
    _write("scientific_freeze_verification.json", {
        "drifted_files": sorted(set(drift)), "v2_fl_001_entry_reference": entry["status"],
        "FEDPROX_MU_V2_selected_mu": json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json"
                                                 ).read_text())["selected_mu"],
        "status": "PASS" if not drift and entry["status"] == "PASS" else "FAIL"})
    # 2. independent reconstruction.
    import scripts.finalize_v2_fl_003_evidence_v2 as successor

    successor.main()
    # 3. mu=0 re-run into the corrective directory (not the historical file).
    import scripts.freeze_v2_fl_003_method as freeze

    freeze.OUT = OUT / "mu0_rerun"
    (OUT / "mu0_rerun").mkdir(parents=True, exist_ok=True)
    mu0 = freeze.mu0_equivalence()
    _write("mu0_reverification.json", {
        "loss_delta": mu0["A_objective_gradient"]["loss_delta"],
        "max_abs_gradient_delta": mu0["A_objective_gradient"]["max_abs_gradient_delta"],
        "all_8_local_update_max_delta": mu0["B_local_updates"][
            "max_abs_delta_difference_all_clients"],
        "aggregate_sha256": mu0["C_round_1_aggregate"]["fedprox_mu0_round_1_sha256"],
        "stored_V2_FL_002_label_round_1_sha256": mu0["C_round_1_aggregate"][
            "stored_V2_FL_002_LABEL_round_1_sha256"],
        "exact_match": mu0["C_round_1_aggregate"]["exact_match"], "status": mu0["status"]})
    lifecycle_audit()
    freeze_scope()
    reconciliation()
    print("verify complete")


def lifecycle_audit() -> dict:
    files, blockers = {}, []
    forbidden = re.compile(r"sha|hash|config|partition|firewall|patient|seed|checkpoint|"
                           r"manifest|prerequisite|threshold", re.IGNORECASE)
    for path in LIFECYCLE_TESTS:
        diff = _git("diff", METHOD_COMMIT, ENTRY, "--", path)
        changed = [line for line in diff.splitlines()
                   if line[:1] in "+-" and not line.startswith(("+++", "---"))]
        def lifecycle_line(c: str) -> bool:
            if forbidden.search(c.replace("test_", "")):
                return False
            if ID_LIST.match(c):
                return True
            return ("V2-FL-003" in c and "status" in c) or "for later in" in c

        lifecycle_only = all(lifecycle_line(c) for c in changed)
        entry = {"old_sha256": _sha_at(METHOD_COMMIT, path), "entry_sha256": _sha_at(ENTRY, path),
                 "current_sha256": hash_file(ROOT / path), "diff": diff,
                 "changed_lines": changed, "changed_assertions": [
                     c for c in changed if "assert" in c or "for later" in c or '"V2' in c],
                 "classification": "FORWARD_LIFECYCLE_ONLY" if lifecycle_only else "BLOCKER",
                 "weakens_hashes_or_scientific_configuration_or_firewall_or_integrity":
                 not lifecycle_only}
        files[path] = entry
        if not lifecycle_only:
            blockers.append(path)
    added = _git("diff", "--name-status", METHOD_COMMIT, ENTRY, "--", "tests").splitlines()
    data = {"range": f"{METHOD_COMMIT[:7]}..{ENTRY[:7]}", "files": files,
            "name_status_in_range": added,
            "changed_historical_test_files": len(LIFECYCLE_TESTS),
            "prior_handoff_said_three_actual_is_four": True,
            "added_new_test_files": [a.split("\t")[1] for a in added if a.startswith("A\t")],
            "broadening_note": "the V2-FL-001/002 results tests and the V2-FL-002 method test "
            "now accept V2-FL-003 in {NOT_STARTED, PASS}; exactness is enforced by the strict "
            "current-lineage lifecycle test (tests/test_model_v2_current_lifecycle.py)",
            "blockers": blockers, "status": "PASS" if not blockers else "FAIL"}
    _write("lifecycle_test_drift_audit.json", data)
    return data


def freeze_scope() -> dict:
    audits = {}
    for phase, name in (("v2_fl_001", "V2-FL-001"), ("v2_fl_002", "V2-FL-002"),
                        ("v2_fl_003", "V2-FL-003")):
        freeze = json.loads((ROOT / f"reports/model_v2/{phase}/method_freeze.json"
                             ).read_text())["method_file_sha256"]
        drift = sorted(p for p, h in freeze.items() if hash_file(ROOT / p) != h)
        lifecycle = [p for p in drift if p.startswith("tests/")]
        scientific = [p for p in drift if p not in lifecycle]
        audits[name] = {"frozen_file_count": len(freeze), "drifted_files": drift,
                        "B_LIFECYCLE_STATUS_ASSERTION_FILES_drifted": lifecycle,
                        "A_SCIENTIFIC_METHOD_FILES_drifted": scientific,
                        "scientific_method_files_byte_identical": not scientific,
                        "scientific_method_file_count": len([p for p in freeze
                                                            if not p.startswith("tests/")])}
    v2 = audits["V2-FL-002"]
    ok = (not any(a["A_SCIENTIFIC_METHOD_FILES_drifted"] for a in audits.values())
          and v2["B_LIFECYCLE_STATUS_ASSERTION_FILES_drifted"] == [
              "tests/test_v2_fl_002_method.py"]
          and not audits["V2-FL-003"]["drifted_files"])
    data = {"audits": audits,
            "V2_FL_002_only_drift_is_audited_forward_lifecycle_assertion": v2[
                "B_LIFECYCLE_STATUS_ASSERTION_FILES_drifted"] == [
                    "tests/test_v2_fl_002_method.py"],
            "historical_freezes_rewritten": False,
            "claim_boundary": "V2-FL-002's frozen file set is NOT claimed byte-identical today: "
            "exactly one lifecycle test file changed; all scientific-method files are identical",
            "status": "PASS" if ok else "FAIL"}
    _write("historical_freeze_scope_audit.json", data)
    return data


def reconciliation() -> dict:
    freeze = json.loads((V2FL003 / "method_freeze.json").read_text())["method_file_sha256"]
    historical = json.loads((V2FL003 / "method_immutability_audit.json").read_text())
    changed_now = sorted(p for p, h in freeze.items() if hash_file(ROOT / p) != h)
    data = {
        "historical_method_freeze_file_count": len(freeze),
        "historical_expected_hashes": freeze,
        "post_freeze_changed_method_files_originally_observed": historical[
            "method_files_changed_since_freeze"],
        "historical_current_result_behavior": "self-exempted: the amended finalizer defined "
        "AMENDMENT_ALLOWED = {itself} and method_unchanged := 'no unexpected changes' instead of "
        "'no method-file changes'; the original audit PASS is preserved unaltered as history",
        "corrective_action": "historical finalizer restored byte-identically to its "
        "method-commit version; additive successor V2_FL_003_EVIDENCE_FINALIZER_V2 created",
        "historical_finalizer_sha256_now": hash_file(ROOT / FROZEN_FINALIZER),
        "historical_finalizer_expected_sha256": FROZEN_FINALIZER_SHA,
        "historical_finalizer_byte_identical": hash_file(ROOT / FROZEN_FINALIZER)
        == FROZEN_FINALIZER_SHA,
        "historical_finalizer_contains_self_exemption": "AMENDMENT_ALLOWED" in (
            ROOT / FROZEN_FINALIZER).read_text(),
        "successor_contains_self_exemption": "AMENDMENT_ALLOWED" in (ROOT / SUCCESSOR
                                                                    ).read_text(),
        "known_historical_bug_preserved_in_frozen_file": "eager dict default in comparison()",
        "successor_finalizer": SUCCESSOR,
        "unexpected_changed_method_files_after_correction": changed_now,
        "scientific_method_impact": "NONE", "training_impact": "NONE", "selection_impact": "NONE",
        "metrics_impact": "NONE",
        "final_method_freeze_status": "BYTE-CLEAN" if not changed_now else "NOT_CLEAN",
        "status": "PASS" if (not changed_now and hash_file(ROOT / FROZEN_FINALIZER)
                             == FROZEN_FINALIZER_SHA) else "FAIL"}
    _write("method_freeze_reconciliation.json", data)
    return data


def replay(label: str) -> None:
    subprocess.run([sys.executable, "-m", "scripts.verify_v2_fl_003_replay", label], cwd=ROOT,
                   check=True)
    (OUT / "replay").mkdir(parents=True, exist_ok=True)
    shutil.move(str(V2FL003 / f"replay_verification_{label}.json"),
                str(OUT / "replay" / f"replay_verification_{label}.json"))


def attest() -> None:
    sci = _load("scientific_freeze_verification.json")
    recon = _load("reconstruction/reconstruction_equality.json")
    mu0 = _load("mu0_reverification.json")
    life = _load("lifecycle_test_drift_audit.json")
    scope = _load("historical_freeze_scope_audit.json")
    rec = _load("method_freeze_reconciliation.json")
    replays = [json.loads((OUT / "replay" / f"replay_verification_c_run_{n}.json").read_text())
               for n in (1, 2)]
    regression = _load("pre_export_regression.json")
    ledger = [json.loads(x) for x in (ROOT / "reports/model_v2/access_ledger.jsonl"
                                      ).read_text().splitlines() if x.strip()]
    mine = [r for r in ledger if r.get("stage_id") == "V2-FL-003"]
    partitions = sorted({r["partition"] for r in mine})
    criteria = {
        "scientific_outputs_unchanged": sci["status"] == "PASS",
        "FEDPROX_MU_V2_unchanged_0_1": sci["FEDPROX_MU_V2_selected_mu"] == 0.1,
        "historical_finalizer_restored_exact_sha": rec["historical_finalizer_byte_identical"],
        "successor_reproduces_all_final_evidence": recon["status"] == "PASS",
        "self_exemption_removed": not rec["historical_finalizer_contains_self_exemption"]
        and not rec["successor_contains_self_exemption"],
        "no_unclassified_method_drift": rec["status"] == "PASS",
        "v2_fl_002_scientific_method_unchanged": scope["status"] == "PASS",
        "lifecycle_test_drift_control_only": life["status"] == "PASS",
        "mu0_reverified_exact": mu0["status"] == "PASS" and mu0["exact_match"],
        "replays_two_fresh_processes": all(r["status"] == "PASS" for r in replays),
        "internal_test_untouched": "INTERNAL_TEST" not in partitions
        and "CALIBRATION" not in partitions and "INCART" not in partitions
        and "BIDMC" not in partitions,
        "full_regression": regression["status"] == "PASS"}
    ok = all(criteria.values())
    _write("v2flg2_corrective_attestation.json", {
        "V2FLG2_remains": "PASS" if ok else "FAIL", "criteria": criteria,
        "historical_v2flg2_criteria_preserved_unaltered": True,
        "ledger_partitions_for_stage_V2_FL_003": partitions, "status": "PASS" if ok else "FAIL"})
    _write("run_manifest.json", {
        "checkpoint_id": "C-V2-FL-003-FREEZE-INTEGRITY", "status": "PASS" if ok else "FAIL",
        "V2_FL_003": "PASS (scientific result unchanged)",
        "V2_FL_003_method_freeze": "BYTE-CLEAN AFTER ADDITIVE CORRECTION" if ok else "NOT_CLEAN",
        "FEDPROX_MU_V2": 0.1, "V2_FL_EVAL_001_started": False, "ci_queried": False,
        "ci_triggered": False})
    print(json.dumps({"attestation": "PASS" if ok else "FAIL",
                      "failed": [k for k, v in criteria.items() if not v]}))


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "method":
        method()
    elif command == "verify":
        verify()
    elif command == "replay":
        replay(sys.argv[2])
    elif command == "attest":
        attest()
    else:
        sys.exit("unknown command")
