"""V2-FL-EVAL-001 evaluation machinery (scientific method; hash-pinned before data exposure).

Pure evaluation of frozen FL checkpoints: raw logit -> sigmoid (no calibration), threshold 0.5 with
`>=`, patient-cluster bootstrap with preserved multiplicity (existing frozen implementation), paired
deltas on shared draws, deterministic prediction tables, and stage-specific one-shot access guards.
Nothing here trains, aggregates, selects, calibrates or tunes anything.
"""

from __future__ import annotations

import copy
import csv
import gzip
import io
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from sklearn.metrics import average_precision_score, roc_auc_score

from evaluation.bootstrap import (
    bootstrap_replicates,
    generate_patient_draws,
    percentile_summary,
)
from evaluation.metrics import METRIC_NAMES, pooled_binary_metrics
from federated.model_adapter import fresh_model_v1
from federated.model_v2_fl import fresh_model_v2
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

PROTOCOL_ID = "V2_FL_EVAL_PROTOCOL_V1"
FAMILY_ID = "V2_FL_TEST_FAMILY_V1"
STAGE_ID = "V2-FL-EVAL-001"
THRESHOLD_ID = "FL_EVAL_RAW_THRESHOLD_0P5_V1"
THRESHOLD = 0.5
BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 20260927
FAMILY_RELATIVE = "configs/model_v2/fl_test_family_v1.yaml"
GUARDS = {"INTERNAL_TEST": "artifacts/V2_FL_INTERNAL_TEST_ACCESS_V1.json",
          "INCART": "artifacts/V2_FL_INCART_ACCESS_V1.json"}
PREDICTION_FIELDS = ["example_id", "participant_group_id", "record_id", "label", "raw_logit",
                     "raw_sigmoid_probability", "prediction_at_0_5", "checkpoint_id"]
REPLICATE_METRICS = METRIC_NAMES


class FamilyEvalError(RuntimeError):
    """Roster, guard, population or integrity failure."""


# ---------------------------------------------------------------------------------------------
# One-shot stage guards
# ---------------------------------------------------------------------------------------------
def guard_state(root: Path, dataset: str) -> str:
    path = root / GUARDS[dataset]
    if not path.exists():
        return "NOT_STARTED"
    return str(json.loads(path.read_text())["status"])


def begin_guard(root: Path, dataset: str, payload: dict[str, Any]) -> dict[str, Any]:
    path = root / GUARDS[dataset]
    state = guard_state(root, dataset)
    if state == "COMPLETED":
        raise FamilyEvalError(f"{dataset}_FAMILY_INFERENCE_ALREADY_CONSUMED")
    if state != "NOT_STARTED":
        raise FamilyEvalError(f"{dataset}_FAMILY_INFERENCE_RUN_INTERRUPTED")
    guard = {"evaluation_id": STAGE_ID, "dataset": dataset, "status": "RUN_STARTED", **payload}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(guard, indent=2, sort_keys=True) + "\n")
    return guard


def complete_guard(root: Path, dataset: str, payload: dict[str, Any]) -> dict[str, Any]:
    path = root / GUARDS[dataset]
    guard = json.loads(path.read_text())
    if guard["status"] != "RUN_STARTED":
        raise FamilyEvalError(f"{dataset}_GUARD_NOT_RUN_STARTED")
    guard.update(payload)
    guard["status"] = "COMPLETED"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(guard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return guard


# ---------------------------------------------------------------------------------------------
# Roster / models
# ---------------------------------------------------------------------------------------------
def load_roster(root: Path) -> list[dict[str, Any]]:
    family = yaml.safe_load((root / FAMILY_RELATIVE).read_text())
    models = family["models"]
    ids = [m["id"] for m in models]
    if len(models) != 20 or len(set(ids)) != 20 or family["model_count"] != 20:
        raise FamilyEvalError("FAMILY_ROSTER_NOT_EXACTLY_20_UNIQUE_MODELS")
    for model in models:
        text = model["checkpoint"]
        if "round50" in text or "mu_0p001" in text or "MU_0p001" in text or "MU_0p01_" in text:
            raise FamilyEvalError(f"EXCLUDED_CHECKPOINT_IN_ROSTER:{text}")
        if text.endswith("MODEL_V2_FINAL.pt") or text.endswith("MODEL_V1.pt"):
            raise FamilyEvalError(f"EXCLUDED_CENTRALIZED_CHECKPOINT_IN_ROSTER:{text}")
        if model["generation"] == "V2" and model["algorithm"] == "FedProx" and model["mu"] != 0.1:
            raise FamilyEvalError("V2_FEDPROX_MU_MUST_BE_0P1")
        if hash_file(root / text) != model["checkpoint_sha256"]:
            raise FamilyEvalError(f"CHECKPOINT_HASH_MISMATCH:{model['id']}")
    return models


def build_model(architecture: str) -> torch.nn.Module:
    if architecture == "MODEL_V1_ARCHITECTURE_V1":
        return fresh_model_v1()
    if architecture == "MODEL_V2_TCN_MEAN":
        return fresh_model_v2()
    raise FamilyEvalError(f"UNKNOWN_ARCHITECTURE:{architecture}")


def load_model(root: Path, entry: dict[str, Any]) -> torch.nn.Module:
    model = build_model(entry["architecture"])
    payload = torch.load(root / entry["checkpoint"], map_location="cpu", weights_only=False)
    model.load_state_dict(payload["state_dict"], strict=True)
    return model.eval()


def normalize_inputs(waveforms: np.ndarray) -> np.ndarray:
    """PER_WINDOW_ZSCORE_V1 on the filtered amplitude-preserving window -> float32 [N,1,2500]."""
    normalized = np.stack([normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON)
                           for row in np.asarray(waveforms, dtype=np.float64)])
    if normalized.shape[1:] != (2500,) or not np.isfinite(normalized).all():
        raise FamilyEvalError("INVALID_NORMALIZED_INPUT")
    return normalized.astype(np.float32)[:, None, :]


def infer_logits(model: torch.nn.Module, inputs: np.ndarray, batch_size: int = 256) -> np.ndarray:
    before = copy.deepcopy(model.state_dict())
    model.eval()
    output: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(inputs), batch_size):
            batch = torch.from_numpy(np.ascontiguousarray(inputs[start:start + batch_size]))
            output.append(model(batch).cpu().numpy().reshape(-1))
    if any(not torch.equal(before[k], model.state_dict()[k]) for k in before):
        raise FamilyEvalError("MODEL_STATE_MUTATED_DURING_EVALUATION")
    logits = np.concatenate(output).astype(np.float64)
    if not np.isfinite(logits).all():
        raise FamilyEvalError("NONFINITE_LOGITS")
    return logits


def raw_probability(logits: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(logits, dtype=np.float64)))


def sigmoid_float32_consistent(logits: np.ndarray) -> np.ndarray:
    return torch.sigmoid(torch.from_numpy(np.asarray(logits, dtype=np.float64))).numpy()


# ---------------------------------------------------------------------------------------------
# Prediction tables (deterministic gzip CSV)
# ---------------------------------------------------------------------------------------------
def write_prediction_table(path: Path, entry: dict[str, Any], rows: list[dict[str, str]],
                           labels: np.ndarray, logits: np.ndarray) -> str:
    probabilities = sigmoid_float32_consistent(logits)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=PREDICTION_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row, label, logit, prob in zip(rows, labels, logits, probabilities, strict=True):
        writer.writerow({
            "example_id": row["example_id"], "participant_group_id": row["participant_group_id"],
            "record_id": row["record_id"], "label": int(label),
            "raw_logit": format(float(logit), ".17g"),
            "raw_sigmoid_probability": format(float(prob), ".17g"),
            "prediction_at_0_5": int(prob >= THRESHOLD), "checkpoint_id": entry["id"]})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                                               mtime=0) as handle:
        handle.write(buffer.getvalue().encode("utf-8"))
    return hash_file(path)


def read_prediction_table(path: Path) -> dict[str, np.ndarray]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        "example_id": np.asarray([r["example_id"] for r in rows], dtype=str),
        "participant_group_id": np.asarray([r["participant_group_id"] for r in rows], dtype=str),
        "record_id": np.asarray([r["record_id"] for r in rows], dtype=str),
        "label": np.asarray([int(r["label"]) for r in rows], dtype=np.int64),
        "raw_logit": np.asarray([float(r["raw_logit"]) for r in rows], dtype=np.float64),
        "probability": np.asarray([float(r["raw_sigmoid_probability"]) for r in rows],
                                  dtype=np.float64),
        "prediction": np.asarray([int(r["prediction_at_0_5"]) for r in rows], dtype=np.int64)}


def validate_prediction_table(table: dict[str, np.ndarray], expected_ids: list[str]) -> None:
    ids = table["example_id"].tolist()
    if len(ids) != len(set(ids)):
        raise FamilyEvalError("DUPLICATE_EXAMPLE_IDS")
    if ids != list(expected_ids):
        raise FamilyEvalError("EXAMPLE_ID_SET_OR_ORDER_MISMATCH")
    if not np.array_equal(table["prediction"],
                          (table["probability"] >= THRESHOLD).astype(np.int64)):
        raise FamilyEvalError("THRESHOLD_SEMANTICS_VIOLATION")


# ---------------------------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------------------------
def bce(labels: np.ndarray, probabilities: np.ndarray) -> float:
    p = np.clip(np.asarray(probabilities, dtype=np.float64), 1e-15, 1 - 1e-15)
    y = np.asarray(labels, dtype=np.float64)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def point_metrics(table: dict[str, np.ndarray]) -> dict[str, Any]:
    labels, probs, preds = table["label"], table["probability"], table["prediction"]
    groups = table["participant_group_id"]
    base = pooled_binary_metrics(labels, probs, preds, groups)
    counts = base["confusion_matrix"]
    return {
        "AUPRC": base["AUPRC"], "AUROC": base["AUROC"], "pooled_F1": base["pooled_F1"],
        "precision": base["precision"], "sensitivity": base["sensitivity"],
        "specificity": base["specificity"], "patient_macro_F1": base["patient_macro_F1"],
        "accuracy": float((counts["tp"] + counts["tn"]) / labels.size),
        "BCE": bce(labels, probs), "TP": counts["tp"], "FP": counts["fp"], "TN": counts["tn"],
        "FN": counts["fn"], "windows": int(labels.size), "positives": int(np.sum(labels == 1)),
        "negatives": int(np.sum(labels == 0)),
        "contributing_patients": len(set(groups.tolist()))}


def patient_metrics(table: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    labels, probs, preds = table["label"], table["probability"], table["prediction"]
    groups = table["participant_group_id"]
    rows = []
    for group in sorted(set(groups.tolist())):
        mask = groups == group
        y, p, q = labels[mask], probs[mask], preds[mask]
        pos, neg = int(np.sum(y == 1)), int(np.sum(y == 0))
        tp, fp, fn = int(np.sum((q == 1) & (y == 1))), int(np.sum((q == 1) & (y == 0))), int(
            np.sum((q == 0) & (y == 1)))
        denominator = 2 * tp + fp + fn
        rows.append({
            "participant_group_id": group, "windows": int(mask.sum()), "positives": pos,
            "negatives": neg,
            "AUPRC": float(average_precision_score(y, p)) if pos > 0 else None,
            "AUROC": float(roc_auc_score(y, p)) if pos > 0 and neg > 0 else None,
            "F1_at_0_5": (2 * tp / denominator) if denominator > 0 else None})
    return rows


# ---------------------------------------------------------------------------------------------
# Bootstrap (frozen implementation; shared draws; multiplicity preserved)
# ---------------------------------------------------------------------------------------------
def shared_draws(groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return generate_patient_draws(np.asarray(groups, dtype=str), BOOTSTRAP_B, BOOTSTRAP_SEED)


def replicate_matrix(table: dict[str, np.ndarray], draws: np.ndarray) -> np.ndarray:
    """[B, len(REPLICATE_METRICS)] with NaN for undefined replicate metrics."""
    _, rows = bootstrap_replicates(
        table["participant_group_id"], table["label"], table["probability"], table["prediction"],
        replicates=BOOTSTRAP_B, seed=BOOTSTRAP_SEED, draws=draws)
    return np.asarray([[np.nan if r[name] is None else float(r[name])
                        for name in REPLICATE_METRICS] for r in rows], dtype=np.float64)


def ci_summary(point: dict[str, Any], matrix: np.ndarray) -> dict[str, dict[str, Any]]:
    rows = [{name: (None if np.isnan(matrix[i, j]) else float(matrix[i, j]))
             for j, name in enumerate(REPLICATE_METRICS)} for i in range(matrix.shape[0])]
    return percentile_summary(point, rows)


def paired_delta(point_a: dict[str, Any], matrix_a: np.ndarray, point_b: dict[str, Any],
                 matrix_b: np.ndarray) -> dict[str, dict[str, Any]]:
    """A - B on the SAME draws; invalid when either replicate metric is undefined."""
    out = {}
    for j, name in enumerate(REPLICATE_METRICS):
        delta = matrix_a[:, j] - matrix_b[:, j]
        finite = delta[np.isfinite(delta)]
        out[name] = {
            "point_delta": float(point_a[name] - point_b[name]),
            "ci_lower_95": float(np.quantile(finite, 0.025, method="linear")),
            "ci_upper_95": float(np.quantile(finite, 0.975, method="linear")),
            "valid_replicates": int(finite.size),
            "invalid_replicates": int(delta.size - finite.size)}
    return out


def comparison_pairs(ids: list[str]) -> list[tuple[str, str, str, str]]:
    """(name, A, B, family): predeclared contrasts, A minus B."""
    conditions = ["IID", "LABEL", "QUANTITY", "FEATURE", "COMBINED"]
    pairs: list[tuple[str, str, str, str]] = []
    for algorithm in ("FEDAVG", "FEDPROX"):
        for c in conditions:
            pairs.append((f"V2_{algorithm}_{c}_minus_V1_{algorithm}_{c}",
                          f"V2_{algorithm}_{c}", f"V1_{algorithm}_{c}", "architecture_effect"))
    for c in conditions:
        pairs.append((f"V2_FEDPROX_{c}_minus_V2_FEDAVG_{c}", f"V2_FEDPROX_{c}",
                      f"V2_FEDAVG_{c}", "fedprox_effect"))
    for algorithm in ("FEDAVG", "FEDPROX"):
        for c in conditions[1:]:
            pairs.append((f"V2_{algorithm}_{c}_minus_V2_{algorithm}_IID", f"V2_{algorithm}_{c}",
                          f"V2_{algorithm}_IID", "condition_vs_iid"))
    missing = {x for pair in pairs for x in pair[1:3]} - set(ids)
    if missing:
        raise FamilyEvalError(f"COMPARISON_REFERENCES_UNKNOWN_MODELS:{sorted(missing)}")
    return pairs


def finite(value: Any) -> bool:
    return value is not None and math.isfinite(float(value))


# ---------------------------------------------------------------------------------------------
# Frozen-population expectations (metadata + committed historical identity tables only; no
# waveform is read and no model output of this family exists here)
# ---------------------------------------------------------------------------------------------
def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def internal_expectations(root: Path) -> dict[str, Any]:
    manifest = [r for r in _csv_rows(root / "manifests/windows/MITDB_WINDOWS_V1.csv")
                if r["partition"] == "INTERNAL_TEST"]
    eligible = sorted((r for r in manifest if r["core_eligible"].upper() == "TRUE"),
                      key=lambda r: r["example_id"])
    split = [r for r in _csv_rows(root / "manifests/splits/MITDB_SPLIT_V1.csv")
             if r["partition"] == "INTERNAL_TEST"]
    frozen_groups = sorted({r["participant_group_id"] for r in split})
    contributing = sorted({r["participant_group_id"] for r in eligible})
    historical = _csv_rows(root / "reports/internal_test_predictions.csv")
    return {
        "candidate_windows": len(manifest), "eligible_windows": len(eligible),
        "positive": sum(int(r["label"]) for r in eligible),
        "negative": sum(1 - int(r["label"]) for r in eligible),
        "frozen_groups": frozen_groups, "contributing_groups": contributing,
        "zero_eligible_groups": sorted(set(frozen_groups) - set(contributing)),
        "ids": [r["example_id"] for r in eligible],
        "labels": [int(r["label"]) for r in eligible],
        "groups": [r["participant_group_id"] for r in eligible],
        "historical_ids_match": sorted(r["example_id"] for r in historical) == [
            r["example_id"] for r in eligible]}


def incart_expectations(root: Path) -> dict[str, Any]:
    rows = sorted(_csv_rows(root / "reports/external_incart_predictions.csv"),
                  key=lambda r: r["example_id"])
    patient_map = _csv_rows(root / "manifests/datasets/incart_patient_map.csv")
    return {
        "eligible_windows": len(rows), "records": len({r["record_id"] for r in rows}),
        "clusters": len({r["participant_group_id"] for r in rows}),
        "positive": sum(int(r["label"]) for r in rows),
        "ids": [r["example_id"] for r in rows], "labels": [int(r["label"]) for r in rows],
        "groups": [r["participant_group_id"] for r in rows],
        "records_list": [r["record_id"] for r in rows], "patient_map_rows": len(patient_map)}


def verify_population(expected: dict[str, Any], ids: list[str], labels: np.ndarray,
                      groups: list[str]) -> None:
    if list(ids) != list(expected["ids"]):
        raise FamilyEvalError("POPULATION_EXAMPLE_IDS_DIFFER_FROM_FROZEN")
    if [int(x) for x in labels] != list(expected["labels"]):
        raise FamilyEvalError("POPULATION_LABELS_DIFFER_FROM_FROZEN")
    if list(groups) != list(expected["groups"]):
        raise FamilyEvalError("POPULATION_GROUP_MAPPING_DIFFERS_FROM_FROZEN")
