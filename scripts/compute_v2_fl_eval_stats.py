#!/usr/bin/env python3
"""V2-FL-EVAL-001 statistics from the FROZEN prediction tables ONLY (no checkpoint is loaded,
no waveform or source dataset is opened). Computes point/patient metrics, patient-cluster
bootstrap CIs, paired deltas on shared draws and the shift/effect tables. Usage:
    python -m scripts.compute_v2_fl_eval_stats <out_dir>"""

from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml

from evaluation.model_v2_fl_eval import (
    BOOTSTRAP_B,
    BOOTSTRAP_SEED,
    FAMILY_RELATIVE,
    REPLICATE_METRICS,
    ci_summary,
    comparison_pairs,
    paired_delta,
    patient_metrics,
    point_metrics,
    read_prediction_table,
    replicate_matrix,
    shared_draws,
    validate_prediction_table,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "reports/model_v2/v2_fl_eval_001/predictions"
DATASETS = ("INTERNAL_TEST", "INCART")
LABELS = {"INTERNAL_TEST": "FL-LINEAGE HELD-OUT (not project-globally unseen)",
          "INCART": "POST-FREEZE EXTERNAL FL SECOND-LOOK -- NOT PROJECT-BLIND"}


def _worker(args: tuple[str, str, np.ndarray]) -> tuple[str, np.ndarray]:
    model_id, path, draws = args
    return model_id, replicate_matrix(read_prediction_table(Path(path)), draws)


def evaluate_dataset(dataset: str, roster: list[dict]) -> dict:
    tables = {m["id"]: read_prediction_table(PRED / dataset / f"{m['id']}.csv.gz")
              for m in roster}
    reference = tables[roster[0]["id"]]
    for table in tables.values():
        validate_prediction_table(table, reference["example_id"].tolist())
        if not np.array_equal(table["label"], reference["label"]) or not np.array_equal(
                table["participant_group_id"], reference["participant_group_id"]):
            raise RuntimeError("PREDICTION_TABLES_NOT_ALIGNED")
    patients, draws = shared_draws(reference["participant_group_id"])
    points = {k: point_metrics(t) for k, t in tables.items()}
    with ProcessPoolExecutor(max_workers=8) as pool:
        jobs = [(k, str(PRED / dataset / f"{k}.csv.gz"), draws) for k in tables]
        matrices = dict(pool.map(_worker, jobs))
    models = {}
    for entry in roster:
        key = entry["id"]
        models[key] = {
            "checkpoint_sha256": entry["checkpoint_sha256"], "algorithm": entry["algorithm"],
            "generation": entry["generation"], "condition": entry["condition"],
            "mu": entry["mu"], "development_round": entry["development_round"],
            "development_validation_AUPRC": entry["development_validation_AUPRC"],
            "development_validation_patient_macro_F1": entry[
                "development_validation_patient_macro_F1"],
            "point": points[key], "bootstrap_95": ci_summary(points[key], matrices[key]),
            "patients": patient_metrics(tables[key])}
    comparisons = {}
    for name, a, b, family in comparison_pairs(list(tables)):
        comparisons[name] = {"A": a, "B": b, "family": family,
                             "delta": paired_delta(points[a], matrices[a], points[b], matrices[b])}
    return {
        "dataset": dataset, "claim_label": LABELS[dataset], "windows": int(
            reference["label"].size), "clusters": int(patients.size),
        "bootstrap": {
            "B": BOOTSTRAP_B, "seed": BOOTSTRAP_SEED, "rng": "numpy PCG64",
            "slots_per_replicate": int(draws.shape[1]), "multiplicity_preserved": True,
            "rejection_or_redraw": False,
            "draws_sha256": hashlib.sha256(draws.tobytes()).hexdigest(),
            "replicate_metrics": list(REPLICATE_METRICS), "p_values": "NOT_COMPUTED",
            "multiplicity_adjustment": "NONE (nominal 95% intervals)"},
        "models": models, "comparisons": comparisons}


def shift_tables(internal: dict, incart: dict) -> dict:
    rows = {}
    for key, m in internal["models"].items():
        if m["generation"] != "V2":
            continue
        i, x = m["point"], incart["models"][key]["point"]
        rows[key] = {
            "development_to_internal": {
                "AUPRC": [m["development_validation_AUPRC"], i["AUPRC"],
                          i["AUPRC"] - m["development_validation_AUPRC"]],
                "patient_macro_F1": [m["development_validation_patient_macro_F1"],
                                     i["patient_macro_F1"], i["patient_macro_F1"]
                                     - m["development_validation_patient_macro_F1"]]},
            "internal_to_incart": {
                "AUPRC": [i["AUPRC"], x["AUPRC"], x["AUPRC"] - i["AUPRC"]],
                "patient_macro_F1": [i["patient_macro_F1"], x["patient_macro_F1"],
                                     x["patient_macro_F1"] - i["patient_macro_F1"]]}}
    return {"labels": {"development_to_internal": "shift descriptor, no causal inference",
                       "internal_to_incart": "cross-dataset shift, not calibration drift or "
                       "clinical performance"}, "models": rows}


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    roster = yaml.safe_load((ROOT / FAMILY_RELATIVE).read_text())["models"]
    results = {d: evaluate_dataset(d, roster) for d in DATASETS}
    for dataset, data in results.items():
        (out / f"{dataset.lower()}_statistics.json").write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "shift_tables.json").write_text(json.dumps(
        shift_tables(results["INTERNAL_TEST"], results["INCART"]), indent=2,
        sort_keys=True) + "\n", encoding="utf-8")
    (out / "stats_inputs.json").write_text(json.dumps({
        "tables": {f"{d}/{m['id']}": hash_file(PRED / d / f"{m['id']}.csv.gz")
                   for d in DATASETS for m in roster},
        "checkpoints_loaded": False, "source_waveforms_opened": False}, indent=2,
        sort_keys=True) + "\n", encoding="utf-8")
    print("statistics written to", out)


if __name__ == "__main__":
    main()
