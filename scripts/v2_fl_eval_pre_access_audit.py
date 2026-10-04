#!/usr/bin/env python3
"""V2-FL-EVAL-001 PRE-ACCESS AUDIT (run after the method commit, before any held-out inference).
Proves the frozen family/locks/resources are exact and the access guards are still NOT_STARTED.
Metadata and committed artifacts only; no checkpoint is run and no held-out waveform is opened."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from evaluation.bootstrap import generate_patient_draws
from evaluation.model_v2_fl_eval import (
    GUARDS,
    guard_state,
    incart_expectations,
    internal_expectations,
    load_roster,
)
from nhm.hashing import hash_file
from preprocessing.freeze import verify_preproc_freeze

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_eval_001"


def _draws_match(npz: str, groups: list[str]) -> dict:
    stored = np.load(ROOT / npz, allow_pickle=False)
    _, regenerated = generate_patient_draws(np.asarray(groups, dtype=str), 2000, 20260927)
    pins = json.loads((ROOT / npz.rsplit("/", 1)[0] / "artifact_hashes.json").read_text())
    pinned = pins.get("artifacts", pins)
    key = next((k for k in pinned if k.endswith("bootstrap_draws.npz")), None)
    return {"path": npz, "regenerated_equals_stored": bool(
        np.array_equal(stored["draws_int64"], regenerated)),
        "clusters": len(set(groups)), "slots_per_replicate": int(regenerated.shape[1]),
        "stored_hash_matches_pin": key is not None and hash_file(ROOT / npz) == pinned[key]}


def main() -> None:
    freeze = json.loads((OUT / "method_freeze.json").read_text())
    drift = [p for p, h in freeze["method_file_sha256"].items() if hash_file(ROOT / p) != h]
    roster = load_roster(ROOT)
    internal = internal_expectations(ROOT)
    incart = incart_expectations(ROOT)
    c_att = json.loads((ROOT / "reports/model_v2/c_v2_fl_003_freeze_integrity/"
                        "v2flg2_corrective_attestation.json").read_text())
    mu = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
    pins = {}
    for phase in ("v2_fl_001", "v2_fl_002", "v2_fl_003"):
        hashes = json.loads((ROOT / f"reports/model_v2/{phase}/artifact_hashes.json"
                             ).read_text())["artifacts"]
        pins[phase] = sorted(p for p, h in hashes.items() if hash_file(ROOT / p) != h)
    regression = json.loads((OUT / "pre_export_regression.json").read_text())
    ledger = [json.loads(x) for x in (ROOT / "reports/model_v2/access_ledger.jsonl"
                                      ).read_text().splitlines() if x.strip()]
    prior = [r for r in ledger if r.get("stage_id") == "V2-FL-EVAL-001"
             and r["partition"] in ("INTERNAL_TEST", "INCART")]
    protocol_lock = json.loads((ROOT / "manifests/model_v2/V2_FL_EVAL_PROTOCOL_V1.lock.json"
                                ).read_text())
    family_lock = json.loads((ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json"
                              ).read_text())
    preproc = verify_preproc_freeze(ROOT)
    checks = {
        "all_20_checkpoint_hashes_exact": len(roster) == 20 and all(
            family_lock["checkpoints"][m["id"]]["sha256"] == m["checkpoint_sha256"]
            for m in roster),
        "protocol_and_family_locks_bound": all(
            hash_file(ROOT / p) == h for p, h in protocol_lock["bound_artifacts"].items()),
        "FEDPROX_MU_V2_is_0_1": mu["selected_mu"] == 0.1,
        "v2_fl_001_002_003_artifact_pins_exact": all(not d for d in pins.values()),
        "C_V2_FL_003_corrective_attestation_PASS": c_att["status"] == "PASS",
        "PREPROC_V1_exact": preproc["status"] == "PASS",
        "historical_v2_fl_003_finalizer_byte_clean": hash_file(
            ROOT / "scripts/finalize_v2_fl_003_evidence.py") == (
            "21c640c209577c999d17a30b961d0f74ef1d12e09a2f187e7e1ac30d1bf5ea75"),
        "internal_population_expectations": (
            internal["candidate_windows"], internal["eligible_windows"], internal["positive"],
            internal["negative"], len(internal["frozen_groups"]),
            len(internal["contributing_groups"]), internal["zero_eligible_groups"],
            internal["historical_ids_match"]) == (
            2520, 2157, 1156, 1001, 7, 6, ["MITDB_P107"], True),
        "incart_population_expectations": (
            incart["records"], incart["clusters"], incart["eligible_windows"]) == (75, 32, 26864),
        "t018_bootstrap_resource_exact": _draws_match(
            "reports/t018/bootstrap_draws.npz", internal["groups"]),
        "t020_bootstrap_resource_exact": _draws_match(
            "reports/t020/bootstrap_draws.npz", incart["groups"]),
        "method_files_unchanged_from_method_commit": not drift,
        "regression_PASS": regression["status"] == "PASS",
        "access_guards_NOT_STARTED": {d: guard_state(ROOT, d) for d in GUARDS},
        "no_prior_family_ledger_rows_on_held_out_partitions": not prior,
        "no_prediction_outputs_exist": not (OUT / "predictions").exists(),
        "historical_guards_untouched": {
            "internal": json.loads((ROOT / "artifacts/internal_test_access_v1.json"
                                    ).read_text())["status"],
            "incart": json.loads((ROOT / "artifacts/external_incart_access_v1.json"
                                  ).read_text())["status"]}}

    def ok(value: object) -> bool:
        if isinstance(value, dict):
            if "regenerated_equals_stored" in value:
                return bool(value["regenerated_equals_stored"] and value[
                    "stored_hash_matches_pin"])
            if set(value) == set(GUARDS):
                return all(v == "NOT_STARTED" for v in value.values())
            return all(v == "COMPLETED" for v in value.values())
        return value is True

    status = "PASS" if all(ok(v) for v in checks.values()) else "FAIL"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    (OUT / "pre_access_audit.json").write_text(json.dumps({
        "audit": "V2_FL_EVAL_PRE_ACCESS_AUDIT", "head_at_audit": head,
        "method_commit": freeze["entry_head"], "checks": checks,
        "drifted_method_files": drift,
        "failed_checks": [k for k, v in checks.items() if not ok(v)], "status": status},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status}))


if __name__ == "__main__":
    main()
