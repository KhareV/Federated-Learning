"""V2-011 error-analysis library: prediction-table-only slices (patient/Brier, class
composition, quality, TRAIN-defined HR bins, dataset, threshold region, NSTDB SNR) and the
controlled C031-derived V2 noise-type matrix. Reuses the frozen V1 ERROR_ANALYSIS_V1 /
C031 helpers unchanged; every slice boundary comes from configs/model_v2/error_analysis_v2.yaml.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from datasets.incart import DEFAULT_RAW_ROOT as INCART_RAW_ROOT
from datasets.incart import EXPECTED_FS_HZ as INCART_FS
from datasets.incart import load_annotations as load_incart_annotations
from datasets.labels import NOT_A_BEAT, map_annotation_symbol
from datasets.mitdb import DEFAULT_RAW_ROOT as MITDB_RAW_ROOT
from datasets.mitdb import EXPECTED_FS_HZ as MITDB_FS
from datasets.mitdb import load_annotations as load_mitdb_annotations
from evaluation.c031_error_analysis import (
    NOISE_TYPES,
    SNR_LEVELS,
    noise_offset,
    reconstruct_base_windows,
)
from evaluation.calibration import apply_operating_threshold, source_domain_calibrated_probability
from evaluation.error_analysis import (
    annotation_hr_seconds,
    assign_hr_bin,
    binary_metrics,
    class_composition,
    patient_pseudonyms,
    threshold_region,
)
from evaluation.explain_v2 import model_state_unchanged, snapshot_model_state
from evaluation.metrics import patient_macro_f1, pooled_binary_metrics
from federated.feature_noise import build_noise_bank, mix_noise
from models.cal_v2_verify import load_cal_v2
from models.model_v2_final_freeze import load_model_v2_final
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore
from scripts._v2_011_cases import read_csv

ROOT = Path(__file__).resolve().parents[1]
PROB = "source_domain_calibrated_probability"


def load_error_config(root: Path = ROOT) -> dict[str, Any]:
    return yaml.safe_load((root / "configs/model_v2/error_analysis_v2.yaml").read_text())


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def v2_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base = binary_metrics(rows)
    labels = np.asarray([int(r["label"]) for r in rows], dtype=np.float64)
    probs = np.asarray([float(r[PROB]) for r in rows], dtype=np.float64)
    tp, fp = base["TP"], base["FP"]
    base["precision"] = tp / (tp + fp) if tp + fp else "UNDEFINED_NO_PREDICTED_POSITIVE"
    base["Brier"] = float(np.mean((probs - labels) ** 2)) if labels.size else None
    return base


def patient_macro(rows: list[dict[str, Any]]) -> float:
    return patient_macro_f1(
        np.asarray([r["participant_group_id"] for r in rows], dtype=str),
        np.asarray([int(r["label"]) for r in rows], dtype=np.int64),
        np.asarray([int(r["thresholded_prediction"]) for r in rows], dtype=np.int64),
    )


# ---------------------------------------------------------------------------
# Patient / cluster slice (ranking metric is Brier)
# ---------------------------------------------------------------------------


def patient_slice(rows: list[dict[str, str]], prefix: str) -> list[dict[str, Any]]:
    pseudonyms = patient_pseudonyms((r["participant_group_id"] for r in rows), prefix=prefix)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[pseudonyms[row["participant_group_id"]]].append(row)
    table = []
    for patient in sorted(groups):
        selected = groups[patient]
        m = v2_metrics(selected)
        positive, negative = m["positive"], m["negative"]
        f1_defined = positive > 0
        table.append(
            {
                "patient": patient,
                "window_count": m["support"],
                "positive": positive,
                "negative": negative,
                "prevalence": m["positive_prevalence"],
                "brier_score": m["Brier"],
                "TP": m["TP"], "FP": m["FP"], "TN": m["TN"], "FN": m["FN"],
                "F1": m["F1"] if f1_defined else "NOT_INTERPRETABLE_FOR_OVERALL_PATIENT_RANKING",
                "F1_status": "DEFINED_POSITIVE_CLASS_DIAGNOSTIC" if f1_defined
                else "SINGLE_CLASS_NO_POSITIVE_WINDOWS",
                "precision": m["precision"],
                "sensitivity": m["sensitivity"],
                "specificity": m["specificity"],
            }
        )
    ordered = sorted(table, key=lambda r: (float(r["brier_score"]), r["patient"]))
    for i, row in enumerate(ordered):
        row["brier_rank"] = i + 1
        row["ranking_status"] = (
            "BEST_BY_BRIER" if i == 0 else "WORST_BY_BRIER" if i == len(ordered) - 1
            else "UNRANKED_EXTREME"
        )
    return ordered


# ---------------------------------------------------------------------------
# Window metadata joins
# ---------------------------------------------------------------------------


def manifest_index(root: Path, dataset: str) -> dict[str, dict[str, str]]:
    path = load_error_config(root)["window_manifests"][dataset]
    return {
        r["example_id"]: r
        for r in read_csv(root / path)
        if r["core_eligible"].upper() == "TRUE"
    }


def class_composition_slice(
    dataset: str, rows: list[dict[str, str]], manifest: dict[str, dict[str, str]], floor: int
) -> list[dict[str, Any]]:
    out = []
    labelled = [
        (
            class_composition(
                int(manifest[r["example_id"]]["mapped_s_count"]),
                int(manifest[r["example_id"]]["mapped_v_count"]),
                int(manifest[r["example_id"]]["mapped_f_count"]),
            ),
            r,
        )
        for r in rows
        if r["label"] == "1"
    ]
    for name in ("S_DOMINANT", "V_DOMINANT", "F_CONTAINING", "S_V_TIE"):
        selected = [r for comp, r in labelled if comp == name]
        probs = np.asarray([float(r[PROB]) for r in selected])
        tp = sum(r["thresholded_prediction"] == "1" for r in selected)
        out.append(
            {
                "dataset": dataset,
                "composition": name,
                "support": len(selected),
                "TP": tp,
                "FN": len(selected) - tp,
                "sensitivity": tp / len(selected) if selected else "UNDEFINED_NO_SUPPORT",
                "mean_probability": float(probs.mean()) if len(probs) else None,
                "median_probability": float(np.median(probs)) if len(probs) else None,
                "p25_probability": float(np.quantile(probs, 0.25)) if len(probs) else None,
                "p75_probability": float(np.quantile(probs, 0.75)) if len(probs) else None,
                "exploratory_small_support": len(selected) < floor,
            }
        )
    return out


def grouped(dataset: str, rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    out = []
    for group in sorted(groups):
        values = groups[group]
        out.append(
            {
                "dataset": dataset,
                key: group,
                "patient_count": len({r["participant_group_id"] for r in values}),
                **v2_metrics(values),
            }
        )
    return out


def quality_slice(
    dataset: str, rows: list[dict[str, str]], manifest: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    tagged = [{**r, "quality_group": manifest[r["example_id"]]["ecg_quality"]} for r in rows]
    return grouped(dataset, tagged, "quality_group")


def beat_times(record: str, dataset: str, root: Path) -> np.ndarray:
    if dataset == "INTERNAL_TEST":
        annotation, fs = load_mitdb_annotations(record, root / MITDB_RAW_ROOT), MITDB_FS
    else:
        annotation, fs = load_incart_annotations(record, root / INCART_RAW_ROOT), INCART_FS
    return np.asarray(
        [
            int(s) / fs
            for s, sym in zip(annotation.sample, annotation.symbol, strict=True)
            if map_annotation_symbol(str(sym)).mapped_class != NOT_A_BEAT
        ],
        dtype=np.float64,
    )


def add_hr(
    root: Path, dataset: str, rows: list[dict[str, str]], edges: tuple[float, float, float]
) -> list[dict[str, Any]]:
    cache = {r: beat_times(r, dataset, root) for r in sorted({r["record_id"] for r in rows})}
    out = []
    for row in rows:
        end = int(row["prediction_timestamp_us"]) / 1_000_000.0
        times = cache[row["record_id"]]
        rate = annotation_hr_seconds(times[(times > end - 10.0) & (times <= end)].tolist())
        out.append({**row, "HR_bpm": rate, "HR_bin": assign_hr_bin(rate, edges)})
    return out


def hr_edges(config: dict[str, Any]) -> tuple[float, float, float]:
    h = config["heart_rate_slice"]
    return (float(h["Q1_bpm"]), float(h["Q2_bpm"]), float(h["Q3_bpm"]))


def dataset_slice(name: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    m = v2_metrics(rows)
    prevalence = m["positive_prevalence"]
    auprc = m["AUPRC"]
    return {
        "dataset": name,
        "patient_count": len({r["participant_group_id"] for r in rows}),
        "window_count": m["support"],
        "positive": m["positive"],
        "negative": m["negative"],
        "prevalence": prevalence,
        "AUPRC": auprc,
        "AUPRC_lift_over_prevalence": auprc / prevalence,
        "AUROC": m["AUROC"],
        "pooled_F1": m["F1"],
        "patient_macro_F1": patient_macro(rows),
        "Brier": m["Brier"],
        "precision": m["precision"],
        "sensitivity": m["sensitivity"],
        "specificity": m["specificity"],
        "TP": m["TP"], "FP": m["FP"], "TN": m["TN"], "FN": m["FN"],
        "prevalence_note": "different prevalence: raw AUPRC magnitudes are not directly "
        "exchangeable across datasets; INCART remains un-recalibrated",
    }


def threshold_region_slice(
    name: str, rows: list[dict[str, str]], threshold: float, margin: float
) -> dict[str, Any]:
    def kind(r: dict[str, str]) -> str:
        return "FP" if (r["label"] == "0" and r["thresholded_prediction"] == "1") else (
            "FN" if (r["label"] == "1" and r["thresholded_prediction"] == "0") else "OK"
        )

    if margin != 0.05:
        raise ValueError("THRESHOLD_REGION margin is frozen at 0.05")
    tagged = [(kind(r), threshold_region(float(r[PROB]), threshold, margin)) for r in rows]
    fp = sum(k == "FP" for k, _ in tagged)
    fn = sum(k == "FN" for k, _ in tagged)
    fp_in = sum(k == "FP" and near for k, near in tagged)
    fn_in = sum(k == "FN" and near for k, near in tagged)
    return {
        "dataset": name,
        "threshold": threshold,
        "band_lower": max(0.0, threshold - margin),
        "band_upper": min(1.0, threshold + margin),
        "window_count": len(rows),
        "windows_in_band": sum(near for _, near in tagged),
        "FP": fp,
        "FN": fn,
        "FP_within_band": fp_in,
        "FN_within_band": fn_in,
        "share_FP_within_band": fp_in / fp if fp else 0.0,
        "share_FN_within_band": fn_in / fn if fn else 0.0,
    }


def nstdb_snr_slice(root: Path) -> list[dict[str, Any]]:
    rows = read_csv(root / load_error_config(root)["sources"]["NSTDB_COMPARISON"])
    return [
        {
            **row,
            "scope": "OFFICIAL_NSTDB_118e_119e_ELECTRODE_MOTION_STRESS_PROVIDER_GENERATED",
            "noise_type_coverage": "ELECTRODE_MOTION_ONLY_NOT_ALL_THREE_ARTIFACT_TYPES",
        }
        for row in rows
    ]


def compute_error_tables(root: Path = ROOT) -> dict[str, Any]:
    config = load_error_config(root)
    threshold = float(config["cal_v2_threshold"])
    margin = float(config["threshold_region"]["margin"])
    floor = int(config["class_composition"]["exploratory_support_below"])
    edges = hr_edges(config)
    internal = read_csv(root / config["sources"]["INTERNAL_TEST"])
    incart = read_csv(root / config["sources"]["INCART"])
    manifests = {"INTERNAL_TEST": manifest_index(root, "INTERNAL_TEST"),
                 "INCART": manifest_index(root, "INCART")}
    data = {"INTERNAL_TEST": internal, "INCART": incart}
    prefix = config["patient_slice"]["pseudonym_prefix"]
    tables: dict[str, Any] = {
        "patient_internal": patient_slice(internal, prefix["INTERNAL_TEST"]),
        "patient_incart": patient_slice(incart, prefix["INCART"]),
        "class_composition": [],
        "quality": [],
        "heart_rate": [],
        "dataset": [],
        "threshold_region": [],
    }
    for name, rows in data.items():
        tables["class_composition"] += class_composition_slice(name, rows, manifests[name], floor)
        tables["quality"] += quality_slice(name, rows, manifests[name])
        tables["heart_rate"] += grouped(name, add_hr(root, name, rows, edges), "HR_bin")
        tables["dataset"].append(dataset_slice(name, rows))
        tables["threshold_region"].append(threshold_region_slice(name, rows, threshold, margin))
    tables["nstdb_snr"] = nstdb_snr_slice(root)
    return tables


# ---------------------------------------------------------------------------
# Controlled C031-derived noise-type matrix (V2)
# ---------------------------------------------------------------------------


def verify_noise_protocol(root: Path = ROOT) -> dict[str, Any]:
    """Mechanically verify the frozen C031 protocol before any V2 noise output. No waveform
    access (only file hashes and CSV/YAML metadata)."""
    import json

    config = load_error_config(root)["noise_type"]
    lock = json.loads((root / config["c031_lock"]).read_text())
    c031 = yaml.safe_load((root / config["c031_config"]).read_text())
    checks: dict[str, bool] = {}
    checks["c031_lock_sha"] = hash_file(root / config["c031_lock"]) == config["c031_lock_sha256"]
    checks["c031_config_sha"] = (
        hash_file(root / config["c031_config"]) == config["c031_config_sha256"]
    )
    checks["c031_code_sha"] = hash_file(root / config["c031_code"]) == config["c031_code_sha256"]
    checks["mixing_code_sha"] = (
        hash_file(root / config["mixing_code"]) == config["mixing_code_sha256"]
    )
    checks["lock_bound_artifacts_all_match"] = all(
        hash_file(root / path) == digest for path, digest in lock["bound_artifacts"].items()
    )
    checks["base_manifest_sha"] = (
        hash_file(root / config["base_manifest"]) == config["base_manifest_sha256"]
        == c031["base_manifest_sha256"]
    )
    base = read_csv(root / config["base_manifest"])
    positive = sum(int(r["label"]) for r in base)
    checks["base_windows_720"] = len(base) == config["base_windows"] == 720
    checks["positive_469"] = positive == config["positive"] == 469
    checks["negative_251"] = len(base) - positive == config["negative"] == 251
    checks["base_records"] = sorted({r["base_record_id"] for r in base}) == ["118", "119"]
    t019 = {r["pair_id"]: r for r in read_csv(root / "reports/t019/nstdb_predictions.csv")}
    checks["base_pairs_match_t019"] = set(t019) == {r["base_window_id"] for r in base} and all(
        t019[r["base_window_id"]]["label"] == r["label"] for r in base
    )
    checks["noise_sources"] = config["noise_sources"] == c031["noise_sources"]
    checks["snr_list"] = config["snr_db"] == c031["snr_db"] == list(SNR_LEVELS)
    checks["noise_types_map"] = NOISE_TYPES == {
        "BASELINE_WANDER": "bw", "ELECTRODE_MOTION": "em", "MUSCLE_ARTIFACT": "ma"}
    checks["analysis_cells_18"] = (
        len(NOISE_TYPES) * len(SNR_LEVELS) == config["analysis_cells"] == 18
    )
    checks["segment_namespace"] = config["segment_namespace"] == c031["segment_namespace"]
    dat_hashes = {
        s: hash_file(root / f"data/raw/nstdb/1.0.0/{s}.dat") for s in ("bw", "em", "ma")
    }
    checks["noise_source_hashes"] = dat_hashes == config["noise_source_dat_sha256"]
    checks["pure_noise_labels_none"] = str(c031["pure_noise_labels"]).startswith("NONE")
    v1 = read_csv(root / config["v1_comparator"])
    checks["v1_comparator_sha"] = (
        hash_file(root / config["v1_comparator"]) == config["v1_comparator_sha256"]
    )
    checks["v1_comparator_18_cells"] = len(v1) == 18
    checks["v1_predictions_sha"] = (
        hash_file(root / config["v1_predictions"]) == config["v1_predictions_sha256"]
    )
    return {
        "protocol_id": config["protocol_id"],
        "checks": checks,
        "noise_source_dat_sha256": dat_hashes,
        "source_windows": len(base),
        "positive": positive,
        "negative": len(base) - positive,
        "noise_types": sorted(NOISE_TYPES),
        "snr_levels": list(SNR_LEVELS),
        "analysis_cells": 18,
        "pure_noise_labels_fabricated": False,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


NOISE_PRED_FIELDS = [
    "base_window_id", "base_record_id", "source_right_edge_index", "label", "noise_type",
    "noise_source", "noise_offset", "snr_db", "achieved_snr_db", "raw_logit",
    "calibrated_probability", "thresholded_prediction", "clean_calibrated_probability",
    "clean_thresholded_prediction",
]


def run_noise_matrix_v2(
    root: Path = ROOT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    torch.set_num_threads(1)
    base = read_csv(root / load_error_config(root)["noise_type"]["base_manifest"])
    clean, labels = reconstruct_base_windows(root, base)
    bank, bank_audit = build_noise_bank(root)
    model, _ = load_model_v2_final(root)
    cal = load_cal_v2(root)
    model.eval()
    before = snapshot_model_state(model)

    def infer(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        normalized = np.stack(
            [normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON) for row in values]
        ).astype(np.float32)
        outputs = []
        with torch.inference_mode():
            for start in range(0, len(normalized), 128):
                batch = torch.from_numpy(normalized[start : start + 128, None, :])
                outputs.append(model(batch).numpy()[:, 0])
        logits = np.concatenate(outputs).astype(np.float64)
        probabilities = source_domain_calibrated_probability(logits, cal)
        return logits, probabilities, apply_operating_threshold(probabilities, cal)

    _, clean_prob, clean_pred = infer(clean)
    rows: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    for noise_type, source in NOISE_TYPES.items():
        offsets = [
            noise_offset(str(r["base_window_id"]), noise_type, bank[source].size) for r in base
        ]
        segments = np.stack([bank[source][o : o + 2500] for o in offsets])
        for snr in SNR_LEVELS:
            noisy, achieved = [], []
            for window, segment in zip(clean, segments, strict=True):
                mixed, got = mix_noise(window, segment, float(snr))
                noisy.append(mixed)
                achieved.append(got)
            if max(abs(v - snr) for v in achieved) > 0.05:
                raise RuntimeError("V2_011_SNR_FIXTURE_FAILURE")
            logits, probs, preds = infer(np.stack(noisy))
            for i, b in enumerate(base):
                rows.append(
                    {
                        "base_window_id": b["base_window_id"],
                        "base_record_id": b["base_record_id"],
                        "source_right_edge_index": b["source_right_edge_index"],
                        "label": int(labels[i]),
                        "noise_type": noise_type,
                        "noise_source": source,
                        "noise_offset": offsets[i],
                        "snr_db": snr,
                        "achieved_snr_db": achieved[i],
                        "raw_logit": float(logits[i]),
                        "calibrated_probability": float(probs[i]),
                        "thresholded_prediction": int(preds[i]),
                        "clean_calibrated_probability": float(clean_prob[i]),
                        "clean_thresholded_prediction": int(clean_pred[i]),
                    }
                )
            fixtures.append(
                {"noise_type": noise_type, "source": source, "snr_db": snr,
                 "base_window_id": base[0]["base_window_id"], "offset": offsets[0],
                 "achieved_snr_db": achieved[0], "absolute_error_db": abs(achieved[0] - snr),
                 "status": "PASS", "source_audit": bank_audit[source]}
            )
    mutated = not model_state_unchanged(model, before)
    return rows, fixtures, mutated


def read_noise_predictions(path: Path) -> list[dict[str, Any]]:
    out = []
    for r in read_csv(path):
        out.append(
            {
                **r,
                "label": int(r["label"]),
                "snr_db": int(r["snr_db"]),
                "calibrated_probability": float(r["calibrated_probability"]),
                "thresholded_prediction": int(r["thresholded_prediction"]),
                "clean_calibrated_probability": float(r["clean_calibrated_probability"]),
                "clean_thresholded_prediction": int(r["clean_thresholded_prediction"]),
            }
        )
    return out


def _cell_metrics(rows: list[dict[str, Any]], *, allow_undefined: bool) -> dict[str, Any]:
    labels = np.asarray([r["label"] for r in rows], dtype=np.int64)
    probs = np.asarray([r["calibrated_probability"] for r in rows], dtype=np.float64)
    preds = np.asarray([r["thresholded_prediction"] for r in rows], dtype=np.int64)
    clean_p = np.asarray([r["clean_calibrated_probability"] for r in rows], dtype=np.float64)
    clean_pred = np.asarray([r["clean_thresholded_prediction"] for r in rows], dtype=np.int64)
    patients = np.asarray([r["base_record_id"] for r in rows], dtype=str)
    m = pooled_binary_metrics(labels, probs, preds, patients, allow_undefined=allow_undefined)
    c = pooled_binary_metrics(
        labels, clean_p, clean_pred, patients, allow_undefined=allow_undefined
    )
    defined = m["AUPRC"] is not None and c["AUPRC"] is not None
    delta = (m["AUPRC"] - c["AUPRC"]) if defined else None
    counts = m["confusion_matrix"]
    return {
        "source_records": len(set(patients.tolist())),
        "windows": int(labels.size),
        "positive": int(labels.sum()),
        "negative": int(labels.size - labels.sum()),
        "AUPRC": m["AUPRC"],
        "delta_AUPRC_vs_clean": delta,
        "AUROC": m["AUROC"],
        "F1": m["pooled_F1"],
        "precision": m["precision"],
        "sensitivity": m["sensitivity"],
        "specificity": m["specificity"],
        "TP": counts["tp"], "FP": counts["fp"], "TN": counts["tn"], "FN": counts["fn"],
        "mean_calibrated_probability": float(np.mean(probs)),
        "decision_changes_vs_clean": int(np.sum(preds != clean_pred)),
    }


def aggregate_noise(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for noise_type, source in NOISE_TYPES.items():
        for snr in SNR_LEVELS:
            cell = [r for r in rows if r["noise_type"] == noise_type and r["snr_db"] == snr]
            out.append({"scope": "POOLED_BOTH_SOURCE_RECORDS", "noise_type": noise_type,
                        "noise_source": source, "snr_db": snr,
                        **_cell_metrics(cell, allow_undefined=False)})
            for record in ("118", "119"):
                part = [r for r in cell if r["base_record_id"] == record]
                out.append({"scope": f"SOURCE_RECORD_{record}", "noise_type": noise_type,
                            "noise_source": source, "snr_db": snr,
                            **_cell_metrics(part, allow_undefined=True)})
    return out


def compare_noise_to_v1(metrics: list[dict[str, Any]], root: Path = ROOT) -> list[dict[str, Any]]:
    v1 = {(r["noise_type"], int(r["snr_db"])): r for r in read_csv(
        root / load_error_config(root)["noise_type"]["v1_comparator"])}
    out = []
    for row in metrics:
        if row["scope"] != "POOLED_BOTH_SOURCE_RECORDS":
            continue
        old = v1[(row["noise_type"], int(row["snr_db"]))]
        entry = {"noise_type": row["noise_type"], "noise_source": row["noise_source"],
                 "snr_db": row["snr_db"], "windows": row["windows"], "positive": row["positive"],
                 "negative": row["negative"]}
        for name, v1_name in (("AUPRC", "AUPRC"), ("AUROC", "AUROC"), ("F1", "F1"),
                              ("precision", "precision"), ("sensitivity", "sensitivity"),
                              ("specificity", "specificity")):
            entry[f"v1_{name}"] = float(old[v1_name])
            entry[f"v2_{name}"] = row[name]
            entry[f"delta_{name}_V2_minus_V1"] = row[name] - float(old[v1_name])
        entry["descriptive_only"] = True
        out.append(entry)
    return out


__all__ = ["compute_error_tables", "run_noise_matrix_v2", "verify_noise_protocol"]
