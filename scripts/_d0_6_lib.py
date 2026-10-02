"""C-V2-D0.6 shared library: gated reads of already-frozen development evidence only, through
src.nhm.model_v2_d0_6_guard's per-path allowlist. No raw waveform, no new model inference, no
forbidden-partition access. Distinguishes TRAIN_OOF_DECISION_ELIGIBLE sources (Section 4A) from
HISTORICAL_VALIDATION_CONTEXT_ONLY sources (Section 4B).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from evaluation.error_analysis import class_composition
from nhm.hashing import hash_file
from nhm.model_v2_d0_6_guard import check_d0_6_read_allowed, record_d0_6_access

ROOT = Path(__file__).resolve().parents[1]

TRAIN_OOF = "TRAIN_OOF_DECISION_ELIGIBLE"
VALIDATION_CONTEXT = "HISTORICAL_VALIDATION_CONTEXT_ONLY"
METADATA = "METADATA_SCALAR"

SEEDS: tuple[int, ...] = (20260927, 20260928, 20260929)

HR_FEATURE_INDEX = 20  # detected_hr_mean_bpm, BASELINE_FEATURES_V1 schema order


def _gated_path(relative: str) -> Path:
    check_d0_6_read_allowed(relative)
    return ROOT / relative


def gated_read_csv(relative: str, *, stratum: str, purpose: str) -> list[dict]:
    path = _gated_path(relative)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    record_d0_6_access(
        ROOT, relative_path=relative, stratum=stratum, purpose=purpose, rows_read=len(rows)
    )
    return rows


def gated_read_json(relative: str, *, stratum: str, purpose: str) -> dict:
    path = _gated_path(relative)
    data = json.loads(path.read_text(encoding="utf-8"))
    record_d0_6_access(ROOT, relative_path=relative, stratum=stratum, purpose=purpose)
    return data


def gated_read_yaml(relative: str, *, stratum: str, purpose: str) -> dict:
    path = _gated_path(relative)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    record_d0_6_access(ROOT, relative_path=relative, stratum=stratum, purpose=purpose)
    return data


def gated_load_npy(relative: str, *, stratum: str, purpose: str) -> np.ndarray:
    path = _gated_path(relative)
    array = np.load(path, allow_pickle=False)
    record_d0_6_access(
        ROOT, relative_path=relative, stratum=stratum, purpose=purpose, rows_read=array.shape[0]
    )
    return array


def gated_hash_file(relative: str, *, stratum: str, purpose: str) -> str:
    path = _gated_path(relative)
    digest = hash_file(path)
    record_d0_6_access(ROOT, relative_path=relative, stratum=stratum, purpose=purpose)
    return digest


# ---------------------------------------------------------------------------------------
# TRAIN-OOF decision-eligible sources
# ---------------------------------------------------------------------------------------


def load_model_v1_train_oof() -> dict[int, list[dict]]:
    """reports/model_v2/v2_002/oof_predictions.csv, split by seed."""
    rows = gated_read_csv(
        "reports/model_v2/v2_002/oof_predictions.csv",
        stratum=TRAIN_OOF,
        purpose="MODEL_V1_CV_REFERENCE_V1 TRAIN-OOF predictions, per seed",
    )
    by_seed: dict[int, list[dict]] = {seed: [] for seed in SEEDS}
    for row in rows:
        by_seed[int(row["seed"])].append(row)
    return by_seed


def load_rf_all_train_oof() -> list[dict]:
    """reports/model_v2/v2_003/oof_predictions.csv, filtered to feature_variant=ALL,
    model_family=RF (the historical-comparison classical reference, Section 10)."""
    rows = gated_read_csv(
        "reports/model_v2/v2_003/oof_predictions.csv",
        stratum=TRAIN_OOF,
        purpose="V2-003 RF-ALL TRAIN-OOF predictions",
    )
    return [r for r in rows if r["feature_variant"] == "ALL" and r["model_family"] == "RF"]


def load_v2_003_rf_variant_metrics() -> dict:
    """reports/model_v2/v2_003/oof_metrics.json -- the already-frozen pooled OOF AUPRC/AUROC
    for every (feature_variant, model_family), used as H-RHYTHM/H-MORPH supporting evidence.
    Never recomputed."""
    return gated_read_json(
        "reports/model_v2/v2_003/oof_metrics.json",
        stratum=TRAIN_OOF,
        purpose="V2-003 per-variant RF/LOGISTIC pooled OOF AUPRC (H-RHYTHM/H-MORPH evidence)",
    )


def load_v2_003_grouped_permutation_summary() -> dict:
    """reports/model_v2/v2_003/grouped_permutation_summary.json -- the already-frozen grouped
    permutation importance (STAT/RR/QRS mean delta AUPRC), used as H-RHYTHM/H-MORPH supporting
    evidence. Diagnostic/secondary in V2-003 and remains so here. Never recomputed."""
    return gated_read_json(
        "reports/model_v2/v2_003/grouped_permutation_summary.json",
        stratum=TRAIN_OOF,
        purpose="V2-003 grouped permutation importance (H-RHYTHM/H-MORPH evidence)",
    )


def load_window_manifest(partition: str) -> list[dict]:
    """manifests/windows/MITDB_WINDOWS_V1.csv, filtered to one partition AND core_eligible=TRUE
    (matching the exact eligible population used by every OOF/feature-cache artifact; TRAIN has
    60 non-eligible rows excluded, VALIDATION has none). Metadata only (s/v/f beat counts,
    labels, groups) -- never raw waveform."""
    stratum = TRAIN_OOF if partition == "TRAIN" else VALIDATION_CONTEXT
    rows = gated_read_csv(
        "manifests/windows/MITDB_WINDOWS_V1.csv",
        stratum=stratum,
        purpose=f"frozen window/label/group/s-v-f-count metadata for partition={partition}",
    )
    return [
        r
        for r in rows
        if r["partition"] == partition and r["core_eligible"].upper() == "TRUE"
    ]


def composition_for_row(row: dict) -> str:
    """Reuses evaluation.error_analysis.class_composition exactly -- never redefined."""
    return class_composition(
        int(row["mapped_s_count"]), int(row["mapped_v_count"]), int(row["mapped_f_count"])
    )


# ---------------------------------------------------------------------------------------
# HR-equivalent feature (BASELINE_FEATURES_V1 detected_hr_mean_bpm, already-computed by T014)
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HrFeatureSource:
    by_example_id: dict[str, float]


def load_hr_feature(partition: str) -> HrFeatureSource:
    stratum = TRAIN_OOF if partition == "TRAIN" else VALIDATION_CONTEXT
    manifest_rows = gated_read_csv(
        "manifests/features/MITDB_BASELINE_FEATURES_V1.csv",
        stratum=stratum,
        purpose=f"BASELINE_FEATURES_V1 row index lookup for partition={partition}",
    )
    partition_rows = [r for r in manifest_rows if r["partition"] == partition]
    cache_relative = (
        "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
        f"BASELINE_FEATURES_V1/{partition}_features.npy"
    )
    cache = gated_load_npy(
        cache_relative,
        stratum=stratum,
        purpose=f"detected_hr_mean_bpm (index {HR_FEATURE_INDEX}) for partition={partition}",
    )
    by_example_id: dict[str, float] = {}
    for row in partition_rows:
        index = int(row["feature_row_index"])
        value = float(cache[index, HR_FEATURE_INDEX])
        if np.isfinite(value):
            by_example_id[row["example_id"]] = value
    return HrFeatureSource(by_example_id)


# ---------------------------------------------------------------------------------------
# Historical VALIDATION-context scalar metrics (pooled only -- no per-window predictions exist
# as a frozen artifact; this is explicitly recorded as a gap, never regenerated by new
# inference)
# ---------------------------------------------------------------------------------------


def load_model_v1_historical_validation_scalars() -> dict[int, dict]:
    scalars: dict[int, dict] = {}
    for seed in SEEDS:
        data = gated_read_json(
            f"reports/t015/seeds/{seed}.json",
            stratum=VALIDATION_CONTEXT,
            purpose="historical frozen T015 best-epoch VALIDATION scalar descriptive metrics",
        )
        scalars[seed] = data["best_validation_metrics"]
    return scalars


def load_classical_historical_validation_scalars() -> dict[str, dict]:
    report = gated_read_json(
        "reports/baselines/baseline_report.json",
        stratum=VALIDATION_CONTEXT,
        purpose="historical frozen T014 VALIDATION scalar descriptive metrics (RF, LOGISTIC)",
    )
    return {
        "RF": report["random_forest"]["VALIDATION_metrics"],
        "LOGISTIC": report["logistic"]["VALIDATION_metrics"],
    }


def load_cal_v1_threshold() -> dict:
    data = gated_read_json(
        "artifacts/CAL_V1.json", stratum=METADATA, purpose="frozen CAL_V1 threshold/comparator"
    )
    return {
        "threshold": data["threshold"],
        "comparator": data["threshold_comparator"],
        "temperature": data["temperature"],
    }


def load_t014_rf_threshold() -> dict:
    config = gated_read_yaml(
        "configs/baseline_v1.yaml",
        stratum=METADATA,
        purpose="frozen T014 RF/LR fixed decision threshold",
    )
    return {
        "threshold": config["reporting"]["decision_threshold"],
        "policy": config["reporting"]["threshold_policy"],
    }


__all__ = [
    "HR_FEATURE_INDEX",
    "METADATA",
    "ROOT",
    "SEEDS",
    "TRAIN_OOF",
    "VALIDATION_CONTEXT",
    "HrFeatureSource",
    "composition_for_row",
    "gated_hash_file",
    "gated_load_npy",
    "gated_read_csv",
    "gated_read_json",
    "gated_read_yaml",
    "load_cal_v1_threshold",
    "load_classical_historical_validation_scalars",
    "load_hr_feature",
    "load_model_v1_historical_validation_scalars",
    "load_model_v1_train_oof",
    "load_rf_all_train_oof",
    "load_t014_rf_threshold",
    "load_v2_003_grouped_permutation_summary",
    "load_v2_003_rf_variant_metrics",
    "load_window_manifest",
]
