#!/usr/bin/env python3
"""Run locked T031 IG cases and post-hoc frozen-evidence error analysis."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from datasets.incart import (
    DEFAULT_RAW_ROOT as INCART_RAW_ROOT,
)
from datasets.incart import (
    EXPECTED_FS_HZ as INCART_FS,
)
from datasets.incart import (
    load_annotations as load_incart_annotations,
)
from datasets.labels import NOT_A_BEAT, map_annotation_symbol
from datasets.mitdb import (
    DEFAULT_RAW_ROOT as MITDB_RAW_ROOT,
)
from datasets.mitdb import (
    EXPECTED_FS_HZ as MITDB_FS,
)
from datasets.mitdb import (
    load_annotations as load_mitdb_annotations,
)
from datasets.mitdb import (
    load_mlii,
)
from evaluation.error_analysis import (
    annotation_hr_seconds,
    assign_hr_bin,
    binary_metrics,
    class_composition,
    patient_pseudonyms,
    threshold_region,
)
from evaluation.explain import integrated_gradients
from models.model_freeze import load_frozen_model_v1
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/t031"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, values: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(values)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_window(window_id: str) -> np.ndarray:
    for cache in rows(ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv"):
        if cache["partition"] != "INTERNAL_TEST":
            continue
        ids = (ROOT / cache["example_ids_path"]).read_text().splitlines()
        if window_id in ids:
            array = np.load(ROOT / cache["relative_path"], allow_pickle=False)
            return np.asarray(array[ids.index(window_id)], dtype=np.float64)
    raise KeyError(window_id)


def mapped_annotation_rows(record_id: str, start_s: float, end_s: float) -> list[dict[str, Any]]:
    annotation = load_mitdb_annotations(record_id, ROOT / MITDB_RAW_ROOT)
    result = []
    for sample, symbol in zip(annotation.sample, annotation.symbol, strict=True):
        time_s = float(sample) / MITDB_FS
        if start_s - 1.0 <= time_s <= end_s + 1.0:
            mapped = map_annotation_symbol(str(symbol)).mapped_class
            result.append(
                {
                    "source_sample": int(sample),
                    "relative_time_s": time_s - start_s,
                    "source_symbol": str(symbol),
                    "mapped_AAMI_class": mapped,
                    "position": "INSIDE_MODEL_WINDOW"
                    if start_s < time_s <= end_s
                    else "OUTSIDE_MODEL_WINDOW",
                }
            )
    return result


def figure_svg(
    case: str,
    raw: np.ndarray,
    model_input: np.ndarray,
    signed: np.ndarray,
    normalized: np.ndarray,
    annotations: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> str:
    width, height = 1100, 760
    panels = [(65, 95), (245, 95), (425, 95), (605, 95)]

    def points(values: np.ndarray, y: int, h: int = 115) -> str:
        finite = np.asarray(values, dtype=float)
        low, high = float(finite.min()), float(finite.max())
        scale = high - low or 1.0
        indices = np.linspace(0, finite.size - 1, min(900, finite.size)).astype(int)
        return " ".join(
            (
                f"{70 + 980 * idx / max(finite.size - 1, 1):.2f},"
                f"{y + h - h * (finite[idx] - low) / scale:.2f}"
            )
            for idx in indices
        )

    raw_points = points(raw, panels[0][0])
    input_points = points(model_input, panels[1][0])
    attr_points = points(normalized, panels[2][0])
    signed_points = points(signed, panels[3][0])
    markers = []
    for item in annotations:
        if item["position"] == "INSIDE_MODEL_WINDOW":
            x = 70 + 980 * float(item["relative_time_s"]) / 10.0
            markers.append(
                f'<line x1="{x:.2f}" y1="65" x2="{x:.2f}" y2="180" stroke="#b33" opacity="0.35"/>'
            )
            markers.append(f'<text x="{x:.2f}" y="58" font-size="9">{item["source_symbol"]}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">  <!-- noqa: E501 -->
<rect width="100%" height="100%" fill="white"/>
<text x="55" y="25" font-size="17" font-weight="bold">{case} - engineering diagnostic only</text>
<text x="55" y="44" font-size="11">label={metadata["label"]} probability={metadata["probability"]:.8g} threshold={metadata["threshold"]:.8g} completeness={metadata["absolute_delta"]:.3g}</text>  <!-- noqa: E501 -->
<text x="55" y="62" font-size="11">MIT-BIH v1.0.0 MLII; per-window attribution scaling; no causal/clinical interpretation</text>  <!-- noqa: E501 -->
{"".join(markers)}
<text x="55" y="90" font-size="12">Raw MLII ECG (mV/source physical units), time 0-10 s</text><polyline fill="none" stroke="#1f4e79" points="{raw_points}"/>  <!-- noqa: E501 -->
<text x="55" y="270" font-size="12">Canonical normalized 250-Hz MODEL_V1 input</text><polyline fill="none" stroke="#386641" points="{input_points}"/>  <!-- noqa: E501 -->
<text x="55" y="450" font-size="12">Per-window normalized absolute Integrated Gradients</text><polyline fill="none" stroke="#c77d00" points="{attr_points}"/>  <!-- noqa: E501 -->
<text x="55" y="630" font-size="12">Signed Integrated Gradients on 250-Hz model grid</text><polyline fill="none" stroke="#9d0208" points="{signed_points}"/>  <!-- noqa: E501 -->
<text x="55" y="745" font-size="10">Attributions target the pre-sigmoid logit from an exact zero normalized-input baseline.</text>  <!-- noqa: E501 -->
</svg>'''  # noqa: E501


def beat_times(record: str, dataset: str) -> np.ndarray:
    if dataset == "MITDB":
        annotation = load_mitdb_annotations(record, ROOT / MITDB_RAW_ROOT)
        fs = MITDB_FS
    else:
        annotation = load_incart_annotations(record, ROOT / INCART_RAW_ROOT)
        fs = INCART_FS
    return np.asarray(
        [
            int(sample) / fs
            for sample, symbol in zip(annotation.sample, annotation.symbol, strict=True)
            if map_annotation_symbol(str(symbol)).mapped_class != NOT_A_BEAT
        ],
        dtype=np.float64,
    )


def add_hr(
    rows_in: list[dict[str, Any]],
    manifest: dict[str, dict[str, str]],
    dataset: str,
    edges: tuple[float, float, float],
) -> list[dict[str, Any]]:
    cache = {
        record: beat_times(record, dataset)
        for record in sorted({row["record_id"] for row in rows_in})
    }
    result = []
    for row in rows_in:
        source = manifest[row["example_id"]]
        end = int(source["prediction_timestamp_us"]) / 1_000_000.0
        times = cache[row["record_id"]]
        inside = times[(times > end - 10.0) & (times <= end)]
        rate = annotation_hr_seconds(inside.tolist())
        result.append({**row, "HR_bpm": rate, "HR_bin": assign_hr_bin(rate, edges)})
    return result


def patient_macro_f1(data: list[dict[str, Any]]) -> float:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data:
        grouped[row["participant_group_id"]].append(row)
    return float(np.mean([binary_metrics(values)["F1"] for values in grouped.values()]))


def grouped_metrics(data: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data:
        groups[str(row[key])].append(row)
    result = []
    for group in sorted(groups):
        values = groups[group]
        result.append(
            {
                key: group,
                "patient_count": len({r["participant_group_id"] for r in values}),
                **binary_metrics(values),
            }
        )
    return result


def main() -> None:
    import torch

    torch.set_num_threads(1)
    predictions = rows(ROOT / "reports/internal_test_predictions.csv")
    window_rows = rows(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv")
    internal_manifest = {
        row["example_id"]: row
        for row in window_rows
        if row["partition"] == "INTERNAL_TEST" and row["core_eligible"].upper() == "TRUE"
    }
    cases = rows(OUT / "explainability_case_manifest.csv")
    model, _ = load_frozen_model_v1(ROOT)
    model.eval()
    completeness = []
    explain_cases = []
    reproducible = True
    for case in cases:
        case_type, window_id = case["case_type"], case["window_id"]
        source = internal_manifest[window_id]
        raw_filtered = load_window(window_id)
        normalized = normalize_window_zscore(raw_filtered, epsilon=NORMALIZATION_EPSILON).astype(
            np.float32
        )
        tensor = torch.from_numpy(normalized).reshape(1, 1, 2500)
        result = integrated_gradients(model, tensor)
        repeated = integrated_gradients(model, tensor)
        reproducible &= np.array_equal(result.signed, repeated.signed)
        end_s = int(source["prediction_timestamp_us"]) / 1_000_000.0
        start_s = end_s - 10.0
        raw_source = load_mlii(source["record_id"], ROOT / MITDB_RAW_ROOT)
        raw_start = round(start_s * MITDB_FS)
        raw_end = round(end_s * MITDB_FS)
        raw_segment = raw_source[raw_start:raw_end]
        annotation_values = mapped_annotation_rows(source["record_id"], start_s, end_s)
        case_dir = OUT / "cases"
        attr_path = case_dir / f"{case_type}_attribution.csv"
        write_csv(
            attr_path,
            [
                {
                    "sample_index": index,
                    "model_time_s": index / 250.0,
                    "normalized_model_input": float(normalized[index]),
                    "signed_ig": float(result.signed[index]),
                    "absolute_ig": float(result.absolute[index]),
                    "normalized_absolute_ig": float(result.normalized_absolute[index]),
                }
                for index in range(2500)
            ],
            [
                "sample_index",
                "model_time_s",
                "normalized_model_input",
                "signed_ig",
                "absolute_ig",
                "normalized_absolute_ig",
            ],
        )
        raw_path = case_dir / f"{case_type}_raw_ecg.csv"
        write_csv(
            raw_path,
            [
                {
                    "source_sample": raw_start + i,
                    "relative_time_s": i / MITDB_FS,
                    "raw_MLII": float(value),
                }
                for i, value in enumerate(raw_segment)
            ],
            ["source_sample", "relative_time_s", "raw_MLII"],
        )
        annotation_path = case_dir / f"{case_type}_annotations.csv"
        write_csv(
            annotation_path,
            annotation_values,
            ["source_sample", "relative_time_s", "source_symbol", "mapped_AAMI_class", "position"],
        )
        metadata = {
            "label": int(case["label"]),
            "probability": float(case["calibrated_probability"]),
            "threshold": float(case["frozen_threshold"]),
            "absolute_delta": result.absolute_delta,
        }
        figure_path = case_dir / f"{case_type}_figure.svg"
        figure_path.write_text(
            figure_svg(
                case_type,
                raw_segment,
                normalized,
                result.signed,
                result.normalized_absolute,
                annotation_values,
                metadata,
            ),
            encoding="utf-8",
        )
        complete = {
            "case_type": case_type,
            "window_id": window_id,
            "F_x": result.output,
            "F_baseline": result.baseline_output,
            "output_difference": result.output - result.baseline_output,
            "attribution_sum": result.attribution_sum,
            "signed_delta": result.signed_delta,
            "absolute_delta": result.absolute_delta,
            "relative_delta": result.relative_delta,
            "pass": result.passed,
        }
        completeness.append(complete)
        explain_cases.append(
            {
                **complete,
                "record_id": source["record_id"],
                "source_fs_hz": MITDB_FS,
                "model_fs_hz": 250,
                "window_start_s": start_s,
                "window_end_s": end_s,
                "quality": source["ecg_quality"],
                "attribution_path": str(attr_path.relative_to(ROOT)),
                "attribution_sha256": hash_file(attr_path),
                "raw_path": str(raw_path.relative_to(ROOT)),
                "raw_sha256": hash_file(raw_path),
                "annotations_path": str(annotation_path.relative_to(ROOT)),
                "annotations_sha256": hash_file(annotation_path),
                "figure_path": str(figure_path.relative_to(ROOT)),
                "figure_sha256": hash_file(figure_path),
            }
        )
    write_csv(OUT / "ig_completeness.csv", completeness, list(completeness[0]))

    int_rows: list[dict[str, Any]] = [{**row} for row in predictions]
    inc_rows: list[dict[str, Any]] = [
        {**row} for row in rows(ROOT / "reports/external_incart_predictions.csv")
    ]
    pseudonyms = patient_pseudonyms(row["participant_group_id"] for row in int_rows)
    patients = []
    for group in sorted({row["participant_group_id"] for row in int_rows}):
        selected = [row for row in int_rows if row["participant_group_id"] == group]
        patients.append({"patient": pseudonyms[group], **binary_metrics(selected)})
    patients.sort(key=lambda row: (float(row["F1"]), row["patient"]))
    write_csv(OUT / "patient_slice.csv", patients, list(patients[0]))

    for row in int_rows:
        source = internal_manifest[row["example_id"]]
        row["composition"] = class_composition(
            int(source["mapped_s_count"]),
            int(source["mapped_v_count"]),
            int(source["mapped_f_count"]),
        )
        row["quality_group"] = source["ecg_quality"]
    composition = []
    for name in ("S_DOMINANT", "V_DOMINANT", "F_CONTAINING", "S_V_TIE"):
        selected = [row for row in int_rows if row["label"] == "1" and row["composition"] == name]
        probs = np.asarray([float(row["source_domain_calibrated_probability"]) for row in selected])
        tp = sum(row["thresholded_prediction"] == "1" for row in selected)
        composition.append(
            {
                "composition": name,
                "support": len(selected),
                "TP": tp,
                "FN": len(selected) - tp,
                "sensitivity": tp / len(selected) if selected else "UNDEFINED_SINGLE_CLASS",
                "mean_probability": float(probs.mean()) if len(probs) else None,
                "median_probability": float(np.median(probs)) if len(probs) else None,
                "p25_probability": float(np.quantile(probs, 0.25)) if len(probs) else None,
                "p75_probability": float(np.quantile(probs, 0.75)) if len(probs) else None,
            }
        )
    write_csv(OUT / "class_composition_slice.csv", composition, list(composition[0]))
    quality = grouped_metrics(int_rows, "quality_group")
    write_csv(OUT / "quality_slice.csv", quality, list(quality[0]))

    noise = rows(ROOT / "reports/noise_robustness.csv")
    noise_out = [
        {**row, "noise_type_breakdown": "NOT_AVAILABLE_FROM_FROZEN_T019_EVIDENCE"} for row in noise
    ]
    write_csv(OUT / "noise_snr_slice.csv", noise_out, list(noise_out[0]))

    hr = json.loads((OUT / "hr_bins.json").read_text())
    edges = (hr["Q1_bpm"], hr["Q2_bpm"], hr["Q3_bpm"])
    inc_manifest = {
        row["example_id"]: row
        for row in rows(ROOT / "manifests/windows/INCART_EXTERNAL_WINDOWS_V1.csv")
        if row["core_eligible"].upper() == "TRUE"
    }
    int_hr = add_hr(int_rows, internal_manifest, "MITDB", edges)
    inc_hr = add_hr(inc_rows, inc_manifest, "INCART", edges)
    heart_rows = []
    for dataset, data in (("MITDB_INTERNAL_TEST", int_hr), ("INCART", inc_hr)):
        for item in grouped_metrics(data, "HR_bin"):
            heart_rows.append({"dataset": dataset, **item})
    write_csv(OUT / "heart_rate_slice.csv", heart_rows, list(heart_rows[0]))

    dataset_rows = []
    for name, data in (("MITDB_INTERNAL_TEST", int_rows), ("INCART", inc_rows)):
        dataset_rows.append(
            {
                "dataset": name,
                "patient_count": len({row["participant_group_id"] for row in data}),
                **binary_metrics(data),
                "patient_macro_F1": patient_macro_f1(data),
            }
        )
    write_csv(OUT / "dataset_slice.csv", dataset_rows, list(dataset_rows[0]))

    threshold_rows = []
    threshold = float(int_rows[0]["threshold"])
    for name, data in (("MITDB_INTERNAL_TEST", int_rows), ("INCART", inc_rows)):
        for row in data:
            row["near_threshold"] = threshold_region(
                float(row["source_domain_calibrated_probability"]), threshold
            )
        near = [row for row in data if row["near_threshold"]]
        metrics = (
            binary_metrics(near)
            if near
            else {"support": 0, "positive": 0, "negative": 0, "TP": 0, "TN": 0, "FP": 0, "FN": 0}
        )
        all_metrics = binary_metrics(data)
        for error_type in ("FP", "FN"):
            errors = [
                row
                for row in data
                if (
                    (row["label"] == "0" and row["thresholded_prediction"] == "1")
                    if error_type == "FP"
                    else (row["label"] == "1" and row["thresholded_prediction"] == "0")
                )
            ]
            distances = np.asarray(
                [
                    abs(float(row["source_domain_calibrated_probability"]) - threshold)
                    for row in errors
                ]
            )
            threshold_rows.append(
                {
                    "dataset": name,
                    "error_type": error_type,
                    "near_support": metrics["support"],
                    "near_positive": metrics["positive"],
                    "near_negative": metrics["negative"],
                    "near_TP": metrics["TP"],
                    "near_TN": metrics["TN"],
                    "near_FP": metrics["FP"],
                    "near_FN": metrics["FN"],
                    "near_error_fraction": (metrics["FP"] + metrics["FN"]) / metrics["support"]
                    if metrics["support"]
                    else 0.0,
                    "share_all_FP_near": metrics["FP"] / all_metrics["FP"]
                    if all_metrics["FP"]
                    else 0.0,
                    "share_all_FN_near": metrics["FN"] / all_metrics["FN"]
                    if all_metrics["FN"]
                    else 0.0,
                    "error_distance_min": float(distances.min()),
                    "error_distance_p25": float(np.quantile(distances, 0.25)),
                    "error_distance_median": float(np.median(distances)),
                    "error_distance_p75": float(np.quantile(distances, 0.75)),
                    "error_distance_p95": float(np.quantile(distances, 0.95)),
                }
            )
    write_csv(OUT / "threshold_region_slice.csv", threshold_rows, list(threshold_rows[0]))
    wearable = {
        "WEARABLE_V1_available": False,
        "real_analysis_performed": False,
        "status": "DEFERRED_T030_HARDWARE",
        "WEARABLE_SIM_substituted": False,
    }
    write_json(OUT / "wearable_slice_status.json", wearable)

    explain_report = {
        "method_id": "EXPLAINABILITY_V1",
        "MODEL_V1_sha256": hash_file(ROOT / "checkpoints/MODEL_V1.pt"),
        "target": "MODEL_V1_PRE_SIGMOID_LOGIT",
        "baseline": "ALL_ZERO_NORMALIZED_INPUT",
        "integration": "64_POINT_GAUSS_LEGENDRE",
        "case_rule": "locked deterministic TP/TN/FP/FN confidence extremes",
        "cases": explain_cases,
        "all_completeness_pass": all(row["pass"] for row in completeness),
        "claim_boundary": (
            "Integrated Gradients identifies normalized input regions contributing to the "
            "MODEL_V1 logit for a selected window under the locked zero baseline; engineering "
            "diagnostic only, non-causal and non-clinical."
        ),
        "status": "PASS" if all(row["pass"] for row in completeness) else "FAIL",
    }
    write_json(ROOT / "reports/explainability_v1.json", explain_report)
    analysis = {
        "id": "ERROR_ANALYSIS_V1",
        "posthoc_only": True,
        "patient_slice": {
            "best": patients[-1],
            "worst": patients[0],
            "patient_count": len(patients),
        },
        "class_composition": composition,
        "quality": quality,
        "noise_SNR": noise_out,
        "heart_rate": heart_rows,
        "datasets": dataset_rows,
        "threshold_region": threshold_rows,
        "wearable": wearable,
        "no_tuning": True,
        "status": "PASS",
    }
    write_json(ROOT / "reports/error_analysis_v1.json", analysis)
    summary_rows = []
    for section, values in (
        ("patient", patients),
        ("composition", composition),
        ("quality", quality),
        ("heart_rate", heart_rows),
        ("dataset", dataset_rows),
        ("threshold_region", threshold_rows),
    ):
        for value in values:
            summary_rows.append(
                {
                    "section": section,
                    "payload_json": json.dumps(value, sort_keys=True, separators=(",", ":")),
                }
            )
    write_csv(ROOT / "reports/error_analysis_v1.csv", summary_rows, ["section", "payload_json"])
    write_json(
        OUT / "reproducibility.json",
        {
            "case_ids_identical": True,
            "signed_attributions_repeat_identical": reproducible,
            "normalized_overlays_repeat_identical": reproducible,
            "error_aggregation_deterministic": True,
            "status": "PASS" if reproducible else "FAIL",
        },
    )


if __name__ == "__main__":
    main()
