#!/usr/bin/env python3
"""Select and freeze FEDPROX_MU_V2 from the three LABEL candidates (deterministic, run twice, no
human override). Writes the candidate table, the selection evidence, the LABEL alias (the selected
candidate IS the canonical LABEL FedProx result; no duplicate weights) and the lock. Must be
COMMITTED before any transfer-condition run (scripts.run_v2_fl_003 enforces this)."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import yaml

from federated.model_v2_fedprox import CANDIDATES, MACRO_ID, WORST_ID, select_mu
from federated.model_v2_fedprox_runner import CONFIG_RELATIVE, mu_token
from nhm.hashing import hash_bytes, hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_003"
SEL = OUT / "selection"


def csv_bytes(rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def load_rows() -> list[dict]:
    rows = []
    for mu in CANDIDATES:
        result = json.loads((OUT / f"candidates/mu_{mu_token(mu)}/result.json").read_text())
        summary = result["validation_patient_summary"]
        if summary["finite_AUPRC_patients"] != 7 or result["status"] != "COMPLETE":
            raise RuntimeError(f"FEDPROX_CANDIDATE_INVALID:{mu}")
        rows.append({
            "mu": mu, "round0_global_AUPRC": result["round_0_validation"]["AUPRC"],
            "best_round": result["best_round"],
            "best_global_validation_AUPRC": result["best_validation"]["AUPRC"],
            "round50_global_AUPRC": result["round_50_validation_AUPRC"],
            MACRO_ID: summary[MACRO_ID], WORST_ID: summary[WORST_ID],
            "logical_payload_bytes": result["communication"]["total_logical_payload_bytes"],
            "finite": result["stability"]["nonfinite_tensor_count"] == 0,
            "candidate_status": result["status"]})
    return rows


def main() -> None:
    config = yaml.safe_load((ROOT / CONFIG_RELATIVE).read_text())
    baseline = config["label_fedavg_baseline"]
    first = select_mu(load_rows(), baseline[WORST_ID])
    second = select_mu(load_rows(), baseline[WORST_ID])
    if first != second:
        sys.exit("V2_FL_003_SELECTION_NOT_DETERMINISTIC")
    SEL.mkdir(parents=True, exist_ok=True)
    table_bytes = csv_bytes(first["evaluated_candidates"])
    (SEL / "mu_candidates.csv").write_bytes(table_bytes)
    selected = first["selected_mu"]
    first.update({
        "selection_semantics_id": "FEDPROX_SELECTION_SEMANTICS_V1 (MODEL_V2 binding, ids _V2)",
        "tuning_condition": "label", "tuning_manifest": "NONIID_LABEL_V1",
        "baseline_label_fedavg": {MACRO_ID: baseline[MACRO_ID], WORST_ID: baseline[WORST_ID]},
        "human_override": False, "selection_runs": 2, "runs_identical": True,
        "mu_zero_in_candidate_set": False, "candidate_table_sha256": hash_bytes(table_bytes)})
    selection_bytes = (json.dumps(first, indent=2, sort_keys=True) + "\n").encode()
    (SEL / "selection.json").write_bytes(selection_bytes)
    (SEL / "selection_repeat.json").write_text(json.dumps(
        {"run_2_equals_run_1": True, "selected_mu": second["selected_mu"]}, indent=2) + "\n")
    stem = f"mu_{mu_token(selected)}"
    result_path = f"reports/model_v2/v2_fl_003/candidates/{stem}/result.json"
    result = json.loads((ROOT / result_path).read_text())
    alias = {"alias_of": result_path, "role": "CANONICAL_LABEL_FEDPROX_COMPARISON_RESULT",
             "retrained": False, "selected_mu": selected,
             "best_checkpoint": result["best_checkpoint"],
             "best_checkpoint_sha256": result["best_checkpoint_sha256"],
             "round_50_checkpoint": result["round_50_checkpoint"],
             "round_50_checkpoint_sha256": result["round_50_checkpoint_sha256"]}
    (SEL / "label_alias.json").write_text(json.dumps(alias, indent=2, sort_keys=True) + "\n")
    candidates = {}
    for mu in CANDIDATES:
        r = json.loads((OUT / f"candidates/mu_{mu_token(mu)}/result.json").read_text())
        candidates[str(mu)] = {"best_checkpoint_sha256": r["best_checkpoint_sha256"],
                               "round_50_checkpoint_sha256": r["round_50_checkpoint_sha256"]}
    lock = {
        "lock_id": "FEDPROX_MU_V2", "status": "FROZEN_ENGINEERING_METHOD",
        "selected_mu": selected, "candidate_set": list(CANDIDATES),
        "candidate_checkpoint_sha256": candidates,
        "candidate_table_sha256": hash_bytes(table_bytes),
        "selection_evidence_sha256": hash_bytes(selection_bytes),
        "LABEL_manifest_sha256": config["conditions"]["label"]["sha256"],
        "FL_INIT_V2_round_0_state_sha256": config["initialization"]["round_0_state_sha256"],
        "model_architecture": "MODEL_V2_TCN_MEAN", "parameter_count": 57553,
        "fedprox_implementation_sha256": {
            "federated/model_v2_fedprox.py": hash_file(ROOT / "federated/model_v2_fedprox.py"),
            "federated/model_v2_fedprox_runner.py": hash_file(
                ROOT / "federated/model_v2_fedprox_runner.py")},
        "selection_semantics_sha256": hash_file(
            ROOT / "configs/fedprox_selection_semantics_v1.yaml"),
        "baseline_label_fedavg": {MACRO_ID: baseline[MACRO_ID], WORST_ID: baseline[WORST_ID],
                                  "best_validation_AUPRC": baseline["best_validation_AUPRC"]},
        "selected_before_cross_condition_runs": True,
        "selection_provenance": "V2_FL_003_LABEL_ONLY_PREDECLARED_SELECTION",
        "human_override": False, "label_alias": "reports/model_v2/v2_fl_003/selection/"
        "label_alias.json", "supersedes_or_reuses_FEDPROX_MU_V1": False}
    (ROOT / "artifacts/FEDPROX_MU_V2.lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected_mu": selected, "ranking": first["ranking"]}))


if __name__ == "__main__":
    main()
