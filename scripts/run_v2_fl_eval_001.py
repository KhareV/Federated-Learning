#!/usr/bin/env python3
"""V2-FL-EVAL-001 ONE-SHOT FAMILY INFERENCE (single orchestration command).

1. INTERNAL_TEST predictions for all 20 frozen checkpoints, then 2. INCART predictions for all 20,
3. both stage guards COMPLETED. Only prediction tables and an integrity manifest are written here:
no performance metric, bootstrap or comparison is computed or exposed before BOTH stages complete.
Refuses unless the pre-access method commit and audit are committed and intact, both guards are
NOT_STARTED and the tree is clean. Any failure after a guard enters RUN_STARTED STOPS the phase (no
reset, no retry). Evaluation only: no training, calibration, tuning or selection."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from evaluation.external_incart import _record_windows, load_patient_map, verify_source_contract
from evaluation.internal_test import load_internal_population
from evaluation.model_v2_fl_eval import (
    FAMILY_RELATIVE,
    GUARDS,
    STAGE_ID,
    begin_guard,
    complete_guard,
    guard_state,
    incart_expectations,
    infer_logits,
    internal_expectations,
    load_model,
    load_roster,
    normalize_inputs,
    read_prediction_table,
    validate_prediction_table,
    verify_population,
    write_prediction_table,
)
from nhm.hashing import hash_file
from nhm.model_v2_partition_guard import _append_ledger, check_partition_allowed

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_eval_001"
PRED = OUT / "predictions"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def preconditions() -> dict:
    if _git("status", "--porcelain"):
        sys.exit("V2_FL_EVAL_PRECONDITION: working tree not clean")
    freeze = json.loads((OUT / "method_freeze.json").read_text())
    drift = [p for p, h in freeze["method_file_sha256"].items() if hash_file(ROOT / p) != h]
    if drift:
        sys.exit(f"V2_FL_EVAL_METHOD_DRIFT_BEFORE_ACCESS:{drift}")
    audit = json.loads((OUT / "pre_access_audit.json").read_text())
    if audit["status"] != "PASS":
        sys.exit("V2_FL_EVAL_PRE_ACCESS_AUDIT_NOT_PASS")
    for path in ("reports/model_v2/v2_fl_eval_001/method_freeze.json",
                 "reports/model_v2/v2_fl_eval_001/pre_access_audit.json"):
        if not _git("log", "--format=%H", "-n", "1", "--", path):
            sys.exit(f"V2_FL_EVAL_NOT_COMMITTED:{path}")
    for dataset in GUARDS:
        if guard_state(ROOT, dataset) != "NOT_STARTED":
            sys.exit(f"V2_FL_EVAL_GUARD_NOT_NOT_STARTED:{dataset}")
    if PRED.exists():
        sys.exit("V2_FL_EVAL_PREDICTIONS_ALREADY_EXIST")
    return {"git_head": _git("rev-parse", "HEAD"),
            "protocol_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/V2_FL_EVAL_PROTOCOL_V1.lock.json"),
            "family_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json"),
            "family_config_sha256": hash_file(ROOT / FAMILY_RELATIVE),
            "pre_access_audit_sha256": hash_file(OUT / "pre_access_audit.json"),
            "method_freeze_sha256": hash_file(OUT / "method_freeze.json")}


def _ledger(partition: str, access: str, rows: int) -> None:
    _append_ledger(ROOT, {"timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                          "stage_id": STAGE_ID, "experiment_id": "family_one_shot",
                          "partition": partition, "access_type": access, "rows": rows,
                          "source_path": "frozen caches / raw source via the frozen loaders"})


def _bind(entry: dict, dataset: str, table_sha: str, rows: int) -> dict:
    return {"checkpoint_id": entry["id"], "algorithm": entry["algorithm"],
            "architecture": entry["architecture"], "condition": entry["condition"],
            "mu": entry["mu"], "checkpoint_sha256": entry["checkpoint_sha256"],
            "preprocessing_id": "PREPROC_V1", "target_id": "AAMI_SVF_WINDOW_V1",
            "split_id": "MITDB_SPLIT_V1" if dataset == "INTERNAL_TEST" else
            "NOT_APPLICABLE_EXTERNAL_FULL_DATASET", "dataset": dataset,
            "table_sha256": table_sha, "rows": rows}


def run_stage(dataset: str, roster: list[dict], rows: list[dict], labels: np.ndarray,
              waveforms: np.ndarray) -> list[dict]:
    inputs = normalize_inputs(waveforms)
    bindings = []
    for entry in roster:
        model = load_model(ROOT, entry)
        logits = infer_logits(model, inputs)
        path = PRED / dataset / f"{entry['id']}.csv.gz"
        sha = write_prediction_table(path, entry, rows, labels, logits)
        bindings.append(_bind(entry, dataset, sha, len(rows)))
        print(f"{dataset} {entry['id']} done", flush=True)
    return bindings


def main() -> None:
    context = preconditions()
    roster = load_roster(ROOT)
    check_partition_allowed("INTERNAL_TEST", STAGE_ID, ("INTERNAL_TEST", "INCART"))
    # ---- Stage 1: INTERNAL_TEST ----------------------------------------------------------------
    begin_guard(ROOT, "INTERNAL_TEST", context)
    expected = internal_expectations(ROOT)
    population = load_internal_population(ROOT)
    _ledger("INTERNAL_TEST", "FL_FAMILY_ONE_SHOT_INFERENCE", len(population.rows))
    ids = [r["example_id"] for r in population.rows]
    groups = [r["participant_group_id"] for r in population.rows]
    verify_population(expected, ids, population.labels, groups)
    internal_rows = [{"example_id": r["example_id"], "participant_group_id":
                      r["participant_group_id"], "record_id": r["record_id"]}
                     for r in population.rows]
    internal_bind = run_stage("INTERNAL_TEST", roster, internal_rows, population.labels,
                              population.waveforms)
    # ---- Stage 2: INCART -----------------------------------------------------------------------
    check_partition_allowed("INCART", STAGE_ID, ("INTERNAL_TEST", "INCART"))
    begin_guard(ROOT, "INCART", context)
    verify_source_contract(ROOT)
    patient_map = load_patient_map(ROOT)
    manifest_rows, waveforms = [], []
    for record_id in sorted(patient_map):
        rows, eligible = _record_windows(record_id, patient_map[record_id], ROOT)
        eligible_rows = [r for r in rows if r["core_eligible"] == "TRUE"]
        if len(eligible_rows) != len(eligible):
            raise RuntimeError("INCART_ELIGIBLE_WAVEFORM_CLOSURE_FAILURE")
        manifest_rows.extend(eligible_rows)
        waveforms.extend(eligible)
    order = sorted(range(len(manifest_rows)), key=lambda i: manifest_rows[i]["example_id"])
    manifest_rows = [manifest_rows[i] for i in order]
    wave_array = np.stack([waveforms[i] for i in order])
    del waveforms
    _ledger("INCART", "FL_FAMILY_ONE_SHOT_INFERENCE", len(manifest_rows))
    incart_expected = incart_expectations(ROOT)
    labels = np.asarray([int(r["label"]) for r in manifest_rows], dtype=np.int64)
    verify_population(incart_expected, [r["example_id"] for r in manifest_rows], labels,
                      [r["participant_group_id"] for r in manifest_rows])
    if (len(manifest_rows), len({r["record_id"] for r in manifest_rows}),
            len({r["participant_group_id"] for r in manifest_rows})) != (26864, 75, 32):
        raise RuntimeError("INCART_POPULATION_COUNTS_DIFFER_FROM_T020")
    incart_rows = [{"example_id": r["example_id"], "participant_group_id":
                    r["participant_group_id"], "record_id": r["record_id"]}
                   for r in manifest_rows]
    incart_bind = run_stage("INCART", roster, incart_rows, labels, wave_array)
    # ---- Integrity (no metrics) + complete both guards ------------------------------------------
    for dataset, expected_ids, bindings in (("INTERNAL_TEST", expected["ids"], internal_bind),
                                            ("INCART", incart_expected["ids"], incart_bind)):
        for binding in bindings:
            table = read_prediction_table(PRED / dataset / f"{binding['checkpoint_id']}.csv.gz")
            validate_prediction_table(table, expected_ids)
    manifest = {"protocol": "V2_FL_EVAL_PROTOCOL_V1", "family": "V2_FL_TEST_FAMILY_V1",
                "internal_test": internal_bind, "incart": incart_bind,
                "family_invocations": {"INTERNAL_TEST": 1, "INCART": 1},
                "checkpoints_evaluated": len(roster), "metrics_computed_in_this_step": False}
    (OUT / "inference_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_sha = hash_file(OUT / "inference_manifest.json")
    complete_guard(ROOT, "INTERNAL_TEST", {"inference_manifest_sha256": manifest_sha,
                                           "models": len(internal_bind),
                                           "rows_per_model": len(expected["ids"])})
    complete_guard(ROOT, "INCART", {"inference_manifest_sha256": manifest_sha,
                                    "models": len(incart_bind),
                                    "rows_per_model": len(incart_expected["ids"])})
    print(json.dumps({"status": "COMPLETED", "models": len(roster)}))


if __name__ == "__main__":
    main()
