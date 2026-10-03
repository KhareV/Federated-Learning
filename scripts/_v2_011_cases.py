"""V2-011 explainability-case library: deterministic case selection from the frozen V2-010
INTERNAL_TEST prediction table, the case-manifest writer, the guarded four-window loader, raw
ECG/annotation context extraction, Integrated Gradients case execution, and deterministic SVG
figures. All scientific rules are frozen at METHOD_COMMIT; nothing here selects, tunes or
re-scores INTERNAL_TEST.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from datasets.labels import map_annotation_symbol
from datasets.mitdb import DEFAULT_RAW_ROOT, EXPECTED_FS_HZ, load_annotations, load_mlii
from evaluation.explain_v2 import (
    explain_window,
    model_state_unchanged,
    snapshot_model_state,
)
from models.model_v2_final_freeze import load_model_v2_final
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_011"
CASES_DIR = OUT / "cases"
CONFIG_PATH = ROOT / "configs/model_v2/explainability_v2.yaml"
PREDICTIONS_PATH = ROOT / "reports/model_v2/v2_010/internal_v2_predictions.csv"
CASE_MANIFEST_PATH = OUT / "explainability_case_manifest.csv"
CASE_TYPES = ("TP", "TN", "FP", "FN")
PROB_COL = "source_domain_calibrated_probability"

MANIFEST_FIELDS = [
    "case_type", "example_id", "participant_group_id", "record_id", "prediction_timestamp_us",
    "label", "calibrated_probability", "cal_v2_threshold", "thresholded_prediction",
    "model_v2_final_sha256", "cal_v2_sha256", "source_prediction_table_sha256",
    "selection_rule", "tie_rule",
]


class V2011Error(RuntimeError):
    """Raised for any V2-011 scope, closure or integrity failure."""


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_config(root: Path = ROOT) -> dict[str, Any]:
    return yaml.safe_load((root / "configs/model_v2/explainability_v2.yaml").read_text())


# ---------------------------------------------------------------------------
# Deterministic case selection (frozen V2-010 table only; never reruns the model)
# ---------------------------------------------------------------------------


def confusion_category(label: int, prediction: int) -> str:
    return ("T" if label == prediction else "F") + ("P" if prediction else "N")


def select_cases(rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, str]], dict[str, int]]:
    grouped: dict[str, list[dict[str, str]]] = {key: [] for key in CASE_TYPES}
    for row in rows:
        grouped[confusion_category(int(row["label"]), int(row["thresholded_prediction"]))].append(
            row
        )
    counts = {key: len(values) for key, values in grouped.items()}
    empty = [key for key, count in counts.items() if count == 0]
    if empty:
        raise V2011Error(f"V2_011_EMPTY_CASE_CATEGORY:{empty}")

    def probability(row: dict[str, str]) -> float:
        return float(row[PROB_COL])

    selected = {
        "TP": min(grouped["TP"], key=lambda r: (-probability(r), r["example_id"])),
        "TN": min(grouped["TN"], key=lambda r: (probability(r), r["example_id"])),
        "FP": min(grouped["FP"], key=lambda r: (-probability(r), r["example_id"])),
        "FN": min(grouped["FN"], key=lambda r: (probability(r), r["example_id"])),
    }
    return selected, counts


SELECTION_RULES = {
    "TP": "highest_source_domain_calibrated_probability",
    "TN": "lowest_source_domain_calibrated_probability",
    "FP": "highest_source_domain_calibrated_probability",
    "FN": "lowest_source_domain_calibrated_probability",
}
TIE_RULE = "lexicographically_smallest_example_id"


def build_case_manifest_rows(root: Path = ROOT) -> tuple[list[dict[str, Any]], dict[str, int]]:
    predictions = root / "reports/model_v2/v2_010/internal_v2_predictions.csv"
    rows = read_csv(predictions)
    selected, counts = select_cases(rows)
    cal = json.loads((root / "artifacts/CAL_V2.json").read_text())
    model_sha = hash_file(root / "checkpoints/MODEL_V2_FINAL.pt")
    cal_sha = hash_file(root / "artifacts/CAL_V2.json")
    table_sha = hash_file(predictions)
    manifest = []
    for case_type in CASE_TYPES:
        row = selected[case_type]
        manifest.append(
            {
                "case_type": case_type,
                "example_id": row["example_id"],
                "participant_group_id": row["participant_group_id"],
                "record_id": row["record_id"],
                "prediction_timestamp_us": row["prediction_timestamp_us"],
                "label": row["label"],
                "calibrated_probability": row[PROB_COL],
                "cal_v2_threshold": format(float(cal["threshold"]), ".17g"),
                "thresholded_prediction": row["thresholded_prediction"],
                "model_v2_final_sha256": model_sha,
                "cal_v2_sha256": cal_sha,
                "source_prediction_table_sha256": table_sha,
                "selection_rule": SELECTION_RULES[case_type],
                "tie_rule": TIE_RULE,
            }
        )
    return manifest, counts


# ---------------------------------------------------------------------------
# Guarded four-window access
# ---------------------------------------------------------------------------


def frozen_case_ids(root: Path = ROOT) -> dict[str, str]:
    manifest = read_csv(root / CASE_MANIFEST_PATH.relative_to(ROOT))
    return {r["case_type"]: r["example_id"] for r in manifest}


def assert_case_allowed(example_id: str, allowed: set[str]) -> None:
    if example_id not in allowed:
        raise V2011Error(f"V2_011_NON_FROZEN_CASE_ACCESS_FORBIDDEN:{example_id}")


def load_case_window(
    root: Path, example_id: str, record_id: str, allowed: set[str]
) -> tuple[np.ndarray, list[str]]:
    """Return the single frozen INTERNAL_TEST filtered window and the cache paths opened."""
    assert_case_allowed(example_id, allowed)
    caches = [
        row
        for row in read_csv(root / "manifests/windows/MITDB_WINDOWS_V1.cache.csv")
        if row["partition"] == "INTERNAL_TEST" and row["record_id"] == record_id
    ]
    if len(caches) != 1:
        raise V2011Error("V2_011_CASE_CACHE_RECORD_CLOSURE_FAILURE")
    cache = caches[0]
    waveform_path = root / cache["relative_path"]
    id_path = root / cache["example_ids_path"]
    waveform_ok = hash_file(waveform_path) == cache["sha256"]
    ids_ok = hash_file(id_path) == cache["example_ids_sha256"]
    if not (waveform_ok and ids_ok):
        raise V2011Error("V2_011_CASE_CACHE_HASH_MISMATCH")
    ids = id_path.read_text(encoding="utf-8").splitlines()
    if example_id not in ids:
        raise V2011Error("V2_011_CASE_NOT_IN_RECORD_CACHE")
    array = np.load(waveform_path, allow_pickle=False)
    window = np.asarray(array[ids.index(example_id)], dtype=np.float64)
    del array
    return window, [cache["relative_path"], cache["example_ids_path"]]


def mapped_annotation_rows(
    root: Path, record_id: str, start_s: float, end_s: float
) -> list[dict[str, Any]]:
    annotation = load_annotations(record_id, root / DEFAULT_RAW_ROOT)
    result = []
    for sample, symbol in zip(annotation.sample, annotation.symbol, strict=True):
        time_s = float(sample) / EXPECTED_FS_HZ
        if start_s - 1.0 <= time_s <= end_s + 1.0:
            inside = start_s < time_s <= end_s
            result.append(
                {
                    "source_sample": int(sample),
                    "relative_time_s": time_s - start_s,
                    "source_symbol": str(symbol),
                    "mapped_AAMI_class": map_annotation_symbol(str(symbol)).mapped_class,
                    "position": "INSIDE_MODEL_WINDOW" if inside else "OUTSIDE_MODEL_WINDOW",
                }
            )
    return result


def raw_ecg_segment(root: Path, record_id: str, start_s: float, end_s: float):
    raw = load_mlii(record_id, root / DEFAULT_RAW_ROOT)
    start, end = round(start_s * EXPECTED_FS_HZ), round(end_s * EXPECTED_FS_HZ)
    return start, np.asarray(raw[start:end], dtype=np.float64)


# ---------------------------------------------------------------------------
# Deterministic SVG
# ---------------------------------------------------------------------------


def figure_svg(
    case_type: str,
    raw: np.ndarray,
    model_input: np.ndarray,
    signed: np.ndarray,
    normalized: np.ndarray,
    annotations: list[dict[str, Any]],
    meta: dict[str, Any],
) -> str:
    width, height = 1100, 840

    def points(values: np.ndarray, y: int, h: int = 115) -> str:
        finite = np.asarray(values, dtype=float)
        low, high = float(finite.min()), float(finite.max())
        scale = high - low or 1.0
        indices = np.linspace(0, finite.size - 1, min(900, finite.size)).astype(int)
        return " ".join(
            f"{70 + 980 * idx / max(finite.size - 1, 1):.2f},"
            f"{y + h - h * (finite[idx] - low) / scale:.2f}"
            for idx in indices
        )

    markers = []
    for item in annotations:
        if item["position"] == "INSIDE_MODEL_WINDOW":
            x = 70 + 980 * float(item["relative_time_s"]) / 10.0
            markers.append(
                f'<line x1="{x:.2f}" y1="105" x2="{x:.2f}" y2="760" stroke="#b33" '
                f'opacity="0.30"/>'
            )
            markers.append(
                f'<text x="{x:.2f}" y="98" font-size="9">{item["source_symbol"]}'
                f"/{item['mapped_AAMI_class']}</text>"
            )
    panels = [
        (125, "Raw MLII ECG (source physical units), exact 10-s window", raw, "#1f4e79"),
        (305, "PREPROC_V1 normalized 250-Hz MODEL_V2_FINAL input", model_input, "#386641"),
        (485, "Absolute IG overlay (normalized by this window's maximum only)", normalized,
         "#c77d00"),
        (665, "Signed Integrated Gradients (pre-sigmoid logit, zero baseline)", signed, "#9d0208"),
    ]
    body = []
    for y, title, series, color in panels:
        body.append(f'<text x="55" y="{y - 8}" font-size="12">{title}</text>')
        body.append(f'<polyline fill="none" stroke="{color}" points="{points(series, y)}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        '<rect width="100%" height="100%" fill="white"/>\n'
        f'<text x="55" y="25" font-size="17" font-weight="bold">{case_type} - '
        "engineering model-contribution diagnostic</text>\n"
        f'<text x="55" y="44" font-size="11">case={case_type} target_label={meta["label"]} '
        f'calibrated_probability={meta["probability"]:.8g} '
        f'CAL_V2_threshold={meta["threshold"]:.10g} prediction={meta["prediction"]} '
        f'IG_completeness_abs_delta={meta["absolute_delta"]:.3g}</text>\n'
        f'<text x="55" y="62" font-size="11">MODEL_V2_FINAL sha256={meta["model_sha"][:16]} '
        f'(MODEL_V2_TCN_MEAN, seed 20260927); CAL_V2 used for status labels only</text>\n'
        '<text x="55" y="80" font-size="11">Not a causal physiological explanation and not a '
        "clinical explanation; per-window attribution scaling; annotations are display "
        "context only</text>\n"
        + "\n".join(markers)
        + "\n"
        + "\n".join(body)
        + '\n<text x="55" y="815" font-size="10">Attributions target the raw pre-sigmoid '
        "logit from an exact zero normalized-input baseline (64-point Gauss-Legendre)."
        "</text>\n</svg>\n"
    )


# ---------------------------------------------------------------------------
# One IG case
# ---------------------------------------------------------------------------


def run_case(
    root: Path, model: torch.nn.Module, case: dict[str, str], allowed: set[str], config: dict
) -> dict[str, Any]:
    case_type = case["case_type"]
    example_id, record_id = case["example_id"], case["record_id"]
    window, cache_paths = load_case_window(root, example_id, record_id, allowed)
    normalized = normalize_window_zscore(window, epsilon=NORMALIZATION_EPSILON).astype(np.float32)
    tensor = torch.from_numpy(normalized).reshape(1, 1, 2500)
    first = explain_window(model, tensor)
    second = explain_window(model, tensor)
    tol = float(config["repeat_run_tolerance_abs"])
    repro = {
        "raw_logit_identical": first.output == second.output,
        "baseline_logit_identical": first.baseline_output == second.baseline_output,
        "signed_max_abs_difference": float(np.max(np.abs(first.signed - second.signed))),
        "sum_attribution_difference": abs(first.attribution_sum - second.attribution_sum),
        "completeness_identical": first.passed == second.passed
        and first.absolute_delta == second.absolute_delta,
        "max_abs_attribution_index_identical": first.max_abs_attribution_index
        == second.max_abs_attribution_index,
    }
    repro["within_tolerance"] = bool(
        repro["signed_max_abs_difference"] <= tol
        and repro["sum_attribution_difference"] <= tol
        and repro["raw_logit_identical"]
        and repro["baseline_logit_identical"]
        and repro["completeness_identical"]
        and repro["max_abs_attribution_index_identical"]
    )
    end_s = int(case["prediction_timestamp_us"]) / 1_000_000.0
    start_s = end_s - 10.0
    raw_start, raw_segment = raw_ecg_segment(root, record_id, start_s, end_s)
    annotations = mapped_annotation_rows(root, record_id, start_s, end_s)

    attr_rows = [
        {
            "sample_index": i,
            "model_time_s": i / 250.0,
            "normalized_model_input": float(normalized[i]),
            "signed_ig": float(first.signed[i]),
            "absolute_ig": float(first.absolute[i]),
            "normalized_absolute_ig": float(first.normalized_absolute[i]),
        }
        for i in range(2500)
    ]
    attr_path = CASES_DIR / f"{case_type}_attribution.csv"
    write_csv(attr_path, attr_rows, list(attr_rows[0]))
    raw_path = CASES_DIR / f"{case_type}_raw_ecg.csv"
    write_csv(
        raw_path,
        [
            {"source_sample": raw_start + i, "relative_time_s": i / EXPECTED_FS_HZ,
             "raw_MLII": float(v)}
            for i, v in enumerate(raw_segment)
        ],
        ["source_sample", "relative_time_s", "raw_MLII"],
    )
    ann_path = CASES_DIR / f"{case_type}_annotations.csv"
    write_csv(
        ann_path, annotations,
        ["source_sample", "relative_time_s", "source_symbol", "mapped_AAMI_class", "position"],
    )
    meta = {
        "label": int(case["label"]),
        "probability": float(case["calibrated_probability"]),
        "threshold": float(case["cal_v2_threshold"]),
        "prediction": int(case["thresholded_prediction"]),
        "absolute_delta": first.absolute_delta,
        "model_sha": case["model_v2_final_sha256"],
    }
    fig_path = CASES_DIR / f"{case_type}_figure.svg"
    fig_path.write_text(
        figure_svg(case_type, raw_segment, normalized, first.signed, first.normalized_absolute,
                   annotations, meta),
        encoding="utf-8",
    )
    stored = next(
        r for r in read_csv(PREDICTIONS_PATH) if r["example_id"] == example_id
    )
    logit_diff = abs(first.output - float(stored["raw_logit"]))
    return {
        "case_type": case_type,
        "example_id": example_id,
        "record_id": record_id,
        "F_x": first.output,
        "F_baseline": first.baseline_output,
        "output_difference": first.output_difference,
        "attribution_sum": first.attribution_sum,
        "signed_delta": first.signed_delta,
        "absolute_delta": first.absolute_delta,
        "relative_delta": first.relative_delta,
        "pass": first.passed,
        "max_abs_attribution_index": first.max_abs_attribution_index,
        "logit_vs_v2_010_stored_abs_diff": logit_diff,
        "logit_consistent_with_v2_010": bool(
            logit_diff <= float(config["logit_consistency_tolerance_abs"])
        ),
        "reproducibility": repro,
        "cache_paths_opened": cache_paths,
        "window_start_s": start_s,
        "window_end_s": end_s,
        "attribution_sha256": hash_file(attr_path),
        "raw_sha256": hash_file(raw_path),
        "annotations_sha256": hash_file(ann_path),
        "figure_sha256": hash_file(fig_path),
    }


def run_all_cases(root: Path = ROOT) -> dict[str, Any]:
    torch.set_num_threads(1)
    config = load_config(root)
    cases = read_csv(root / CASE_MANIFEST_PATH.relative_to(ROOT))
    allowed = {c["example_id"] for c in cases}
    if len(cases) != 4 or [c["case_type"] for c in cases] != list(CASE_TYPES):
        raise V2011Error("V2_011_CASE_MANIFEST_SHAPE_INVALID")
    model, _ = load_model_v2_final(root)
    model.eval()
    before = snapshot_model_state(model)
    checkpoint_before = hash_file(root / "checkpoints/MODEL_V2_FINAL.pt")
    results = [run_case(root, model, case, allowed, config) for case in cases]
    mutated = not model_state_unchanged(model, before) or (
        hash_file(root / "checkpoints/MODEL_V2_FINAL.pt") != checkpoint_before
    )
    return {"cases": results, "model_mutated": mutated}


# ---------------------------------------------------------------------------
# Method-file registry and guard preconditions (single source of truth)
# ---------------------------------------------------------------------------

METHOD_PATHS = [
    "configs/model_v2/explainability_v2.yaml",
    "configs/model_v2/error_analysis_v2.yaml",
    "reports/model_v2/v2_011/explainability_case_manifest.csv",
    "reports/model_v2/v2_011/case_selection_audit.json",
    "reports/model_v2/v2_011/noise_type_protocol_audit.json",
    "evaluation/explain_v2.py",
    "src/nhm/model_v2_explainability_guard.py",
    "scripts/_v2_011_cases.py",
    "scripts/_v2_011_analysis.py",
    "scripts/freeze_v2_011_method.py",
    "scripts/run_v2_011_cases.py",
    "scripts/run_v2_011_error_analysis.py",
    "scripts/run_v2_011_noise_type.py",
    "scripts/build_explainability_v2.py",
    "models/explainability_v2_verify.py",
    "evaluation/explain.py",
    "evaluation/error_analysis.py",
    "evaluation/c031_error_analysis.py",
    "evaluation/metrics.py",
    "federated/feature_noise.py",
]

COMMON_PRECONDITIONS = {
    "model_v2_final_checkpoint_sha256": "checkpoints/MODEL_V2_FINAL.pt",
    "cal_v2_sha256": "artifacts/CAL_V2.json",
    "protocol_v3_lock_sha256": "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
    "preproc_v1_lock_sha256": "manifests/preprocessing/PREPROC_V1.lock.json",
    "explainability_config_sha256": "configs/model_v2/explainability_v2.yaml",
    "error_analysis_config_sha256": "configs/model_v2/error_analysis_v2.yaml",
    "explain_v2_code_sha256": "evaluation/explain_v2.py",
    "cases_lib_sha256": "scripts/_v2_011_cases.py",
    "analysis_lib_sha256": "scripts/_v2_011_analysis.py",
}
GUARD_PRECONDITIONS = {
    "CASE_ACCESS": {
        "case_manifest_sha256": "reports/model_v2/v2_011/explainability_case_manifest.csv",
        "v2_010_internal_predictions_sha256": "reports/model_v2/v2_010/internal_v2_predictions.csv",
    },
    "NOISE_TYPE": {
        "noise_protocol_audit_sha256": "reports/model_v2/v2_011/noise_type_protocol_audit.json",
        "c031_lock_sha256": "artifacts/C031_ERROR_ANALYSIS_V1.lock.json",
        "c031_base_manifest_sha256": "reports/t031/c031_noise_base_manifest.csv",
    },
}


def observed_preconditions(root: Path, guard: str) -> dict[str, str]:
    paths = {**COMMON_PRECONDITIONS, **GUARD_PRECONDITIONS[guard]}
    return {key: hash_file(root / rel) for key, rel in paths.items()}
