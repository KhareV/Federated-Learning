#!/usr/bin/env python3
"""V2-009 Section 42: all further calculation from the frozen CALIBRATION logits table only
-- no waveform reread. Fits T (twice, requiring strict reproducibility), computes raw/
calibrated NLL/Brier/reliability/ECE, selects the pooled-F1 operating threshold (twice,
requiring the same result), and freezes the canonical artifacts/CAL_V2.json.
"""

from __future__ import annotations

import csv
import json
import platform

import numpy as np
import torch
import yaml

import scripts._cal_v2_lib as lib
from nhm.hashing import hash_file

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_009"
CONFIG_PATH = ROOT / "configs/model_v2/calibration_v2.yaml"
ARTIFACT_PATH = ROOT / "artifacts/CAL_V2.json"


def _read(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _frozen_eligible_calibration_rows() -> list[dict]:
    """Manifest-metadata-only (not waveform cache) reference set for closure checking --
    deliberately avoids any second waveform read of the already-consumed one-shot partition."""
    with (ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        r for r in rows if r["partition"] == "CALIBRATION" and r["core_eligible"].upper() == "TRUE"
    ]


def prediction_closure_audit(rows: list[dict]) -> dict:
    population_rows = _frozen_eligible_calibration_rows()
    frozen_ids = {r["example_id"] for r in population_rows}
    table_ids = {r["example_id"] for r in rows}
    duplicates = len(rows) - len(table_ids)
    missing = len(frozen_ids - table_ids)
    extra = len(table_ids - frozen_ids)
    label_mismatch = []
    group_mismatch = []
    pop_by_id = {r["example_id"]: r for r in population_rows}
    for row in rows:
        pop = pop_by_id.get(row["example_id"])
        if pop is None:
            continue
        if str(pop["label"]) != str(row["label"]):
            label_mismatch.append(row["example_id"])
        if pop["participant_group_id"] != row["participant_group_id"]:
            group_mismatch.append(row["example_id"])
    logits = np.array([float(r["raw_logit"]) for r in rows])
    probs = np.array([float(r["raw_probability"]) for r in rows])
    data = {
        "frozen_example_count": len(frozen_ids),
        "table_example_count": len(table_ids),
        "duplicates": duplicates,
        "missing": missing,
        "extra": extra,
        "label_mismatches": label_mismatch,
        "group_mismatches": group_mismatch,
        "both_classes_present": len({r["label"] for r in rows}) == 2,
        "all_logits_finite": bool(np.all(np.isfinite(logits))),
        "all_probabilities_finite": bool(np.all(np.isfinite(probs))),
        "probabilities_in_range": bool(np.all((probs >= 0) & (probs <= 1))),
        "status": "PASS" if (
            duplicates == 0 and missing == 0 and extra == 0 and not label_mismatch
            and not group_mismatch and len({r["label"] for r in rows}) == 2
            and bool(np.all(np.isfinite(logits))) and bool(np.all(np.isfinite(probs)))
            and bool(np.all((probs >= 0) & (probs <= 1)))
        ) else "FAIL",
    }
    (OUT_DIR / "prediction_closure_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def ece(bins: list[dict]) -> float:
    total = sum(b["count"] for b in bins)
    return float(
        sum(
            (b["count"] / total) * abs(b["mean_probability"] - b["observed_positive_fraction"])
            for b in bins
            if b["count"]
        )
    )


def main() -> None:
    rows = _read(OUT_DIR / "calibration_predictions.csv")
    closure = prediction_closure_audit(rows)
    if closure["status"] != "PASS":
        raise RuntimeError("CALIBRATION prediction closure FAILED -- stopping before fit")

    logits = np.array([float(r["raw_logit"]) for r in rows])
    labels = np.array([int(r["label"]) for r in rows])
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    temperature_1 = lib.fit_temperature(logits, labels, config)
    temperature_2 = lib.fit_temperature(logits, labels, config)
    temperature_diff = abs(temperature_1["temperature"] - temperature_2["temperature"])
    if temperature_diff > 1e-12:
        raise RuntimeError("CALIBRATION_TEMPERATURE_NONDETERMINISM")
    temperature = float(temperature_1["temperature"])

    (OUT_DIR / "temperature_fit.json").write_text(
        json.dumps(
            {
                "parameterization": "theta=log(T); T=exp(theta)",
                "objective": "MEAN_BINARY_NLL",
                "optimizer": "scipy.optimize.minimize_scalar",
                "method": "bounded",
                "bounds": config["temperature"]["theta_bounds"],
                "xatol": config["temperature"]["xatol"],
                "maxiter": config["temperature"]["maxiter"],
                "temperature": temperature,
                "theta": temperature_1["theta"],
                "optimizer_success": temperature_1["optimizer_success"],
                "boundary_hit": temperature_1["boundary_hit"],
                "raw_nll": temperature_1["raw_nll"],
                "calibrated_nll": temperature_1["calibrated_nll"],
                "repeat_temperature": temperature_2["temperature"],
                "absolute_difference": temperature_diff,
                "status": "PASS",
            },
            indent=2, sort_keys=True,
        ) + "\n", encoding="utf-8",
    )

    raw_probability = lib.raw_probability_from_logit(logits)
    calibrated_probability = lib.source_domain_calibrated_probability(
        logits, {"temperature": temperature}
    )

    threshold_1 = lib.select_f1_threshold(calibrated_probability, labels)
    threshold_2 = lib.select_f1_threshold(calibrated_probability, labels)
    if threshold_1 != threshold_2:
        raise RuntimeError("CALIBRATION_THRESHOLD_NONDETERMINISM")
    threshold = float(threshold_1["selected_threshold"])
    threshold_1_adjusted = {
        **threshold_1, "tie_policy": "HIGHEST_THRESHOLD_AMONG_MAX_F1_V2",
    }
    (OUT_DIR / "threshold_search.json").write_text(
        json.dumps(threshold_1_adjusted, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    raw_brier = lib.brier_score(raw_probability, labels)
    calibrated_brier = lib.brier_score(calibrated_probability, labels)
    raw_bins = lib.reliability_bins(raw_probability, labels)
    calibrated_bins = lib.reliability_bins(calibrated_probability, labels)
    raw_ece = ece(raw_bins)
    calibrated_ece = ece(calibrated_bins)

    reliability = {
        "calibration_id": "CAL_V2",
        "domain": "MIT-BIH-v1.0.0",
        "method": "EQUAL_WIDTH_10_BINS_V1",
        "bin_edges": [i / 10.0 for i in range(11)],
        "raw": raw_bins,
        "temperature_scaled": calibrated_bins,
        "raw_ece": raw_ece,
        "calibrated_ece": calibrated_ece,
        "claim_boundary": (
            "Research-only MIT-BIH source-domain calibration under small-patient-sample "
            "uncertainty."
        ),
    }
    (OUT_DIR / "reliability.json").write_text(
        json.dumps(reliability, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    svg = lib.reliability_svg(raw_bins, calibrated_bins)
    (OUT_DIR / "reliability_diagram.svg").write_text(svg, encoding="utf-8")

    calibration_metrics = {
        "raw_nll": temperature_1["raw_nll"], "calibrated_nll": temperature_1["calibrated_nll"],
        "raw_brier": raw_brier, "calibrated_brier": calibrated_brier,
        "raw_ece": raw_ece, "calibrated_ece": calibrated_ece,
        "status": "PASS",
    }
    (OUT_DIR / "calibration_metrics.json").write_text(
        json.dumps(calibration_metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    groups = sorted({r["participant_group_id"] for r in rows})
    records = sorted({r["record_id"] for r in rows})

    checkpoint_sha = hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt")
    manifest_sha = hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json")
    frozen_config_sha = hash_file(ROOT / "configs/model_v2_final_frozen.yaml")
    protocol_v3_sha = hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json")
    split_sha = hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv")
    preproc_sha = hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json")
    window_manifest_sha = hash_file(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv")
    aami_map_sha = hash_file(ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml")

    upstream = {
        "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json": protocol_v3_sha,
        "checkpoints/MODEL_V2_FINAL.pt": checkpoint_sha,
        "checkpoints/MODEL_V2_FINAL.manifest.json": manifest_sha,
        "configs/model_v2_final_frozen.yaml": frozen_config_sha,
        "manifests/splits/MITDB_SPLIT_V1.csv": split_sha,
        "manifests/preprocessing/PREPROC_V1.lock.json": preproc_sha,
        "manifests/windows/MITDB_WINDOWS_V1.csv": window_manifest_sha,
        "manifests/labels/AAMI_SVF_MAP_V1.yaml": aami_map_sha,
    }

    artifact = {
        "calibration_id": "CAL_V2",
        "status": "FROZEN",
        "owner_task": "V2-009",
        "model_id": "MODEL_V2_FINAL",
        "model_checkpoint_sha256": checkpoint_sha,
        "model_manifest_sha256": manifest_sha,
        "model_frozen_config_sha256": frozen_config_sha,
        "protocol_v3_lock_sha256": protocol_v3_sha,
        "target_id": "AAMI_SVF_WINDOW_V1",
        "map_id": "AAMI_SVF_MAP_V1",
        "split_sha256": split_sha,
        "preproc_sha256": preproc_sha,
        "window_manifest_sha256": window_manifest_sha,
        "fit_partition": "CALIBRATION",
        "calibration_domain": "MIT-BIH-v1.0.0",
        "calibration_patient_count": len(groups),
        "calibration_record_count": len(records),
        "calibration_window_count": int(labels.size),
        "positive_window_count": int(np.sum(labels == 1)),
        "negative_window_count": int(np.sum(labels == 0)),
        "temperature": temperature,
        "temperature_parameterization": "theta=log(T); T=exp(theta)",
        "temperature_fit_objective": "MEAN_BINARY_NLL",
        "temperature_optimizer": config["temperature"],
        "raw_nll": temperature_1["raw_nll"],
        "calibrated_nll": temperature_1["calibrated_nll"],
        "raw_brier": raw_brier,
        "calibrated_brier": calibrated_brier,
        "raw_ece": raw_ece,
        "calibrated_ece": calibrated_ece,
        "reliability_method": "EQUAL_WIDTH_10_BINS_V1",
        "reliability_report_path": "reports/model_v2/v2_009/reliability.json",
        "threshold": threshold,
        "threshold_metric": "POOLED_CALIBRATION_WINDOW_F1",
        "threshold_comparator": ">=",
        "threshold_tie_policy": "HIGHEST_THRESHOLD_AMONG_MAX_F1_V2",
        "threshold_confusion_counts": {
            k: threshold_1[k] for k in ("tp", "fp", "tn", "fn")
        },
        "threshold_calibration_f1": float(threshold_1["selected_f1"]),
        "probability_semantics": {
            "raw_probability": "sigmoid(MODEL_V2_FINAL raw logit)",
            "source_domain_calibrated_probability": (
                "sigmoid(MODEL_V2_FINAL raw logit / CAL_V2.temperature)"
            ),
        },
        "small_patient_sample_uncertainty": (
            "MIT-BIH source-domain calibration under small-patient-sample uncertainty; "
            "window count is not patient n."
        ),
        "internal_test_accessed": False,
        "external_data_accessed": False,
        "operational_lineage": "MODEL_V1",
        "runtime_acceptance": "NOT_EVALUATED",
        "upstream_sha256": upstream,
        "method_config_path": "configs/model_v2/calibration_v2.yaml",
        "method_config_sha256": hash_file(CONFIG_PATH),
        "reference_runtime": {
            "python": platform.python_version(), "torch": str(torch.__version__),
        },
        "change_control": (
            "This artifact is never mutated in place. A corrected calibration requires a "
            "new, additive CAL_V2_V2 successor with this artifact preserved byte-identical "
            "as its predecessor."
        ),
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    reproducibility = {
        "temperature_run_1": temperature, "temperature_run_2": temperature_2["temperature"],
        "temperature_absolute_difference": temperature_diff,
        "threshold_run_1": threshold_1["selected_threshold"],
        "threshold_run_2": threshold_2["selected_threshold"],
        "threshold_identical": threshold_1 == threshold_2,
        "status": "PASS" if (temperature_diff <= 1e-12 and threshold_1 == threshold_2) else "FAIL",
    }
    (OUT_DIR / "reproducibility.json").write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "temperature": temperature, "threshold": threshold,
        "raw_brier": raw_brier, "calibrated_brier": calibrated_brier,
        "raw_ece": raw_ece, "calibrated_ece": calibrated_ece,
    }, indent=2))


if __name__ == "__main__":
    main()
