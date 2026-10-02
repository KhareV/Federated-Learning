"""V2-003 shared library: TRAIN-only BASELINE_FEATURES_V1 loading (feature-cache strategy 1 --
the frozen T014 TRAIN/VALIDATION-separated .npy cache is read directly, VALIDATION_features.npy
is never opened), the V2-003 feature-access firewall wiring, variant column masks, and model
factories reused unmodified from models.baselines.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

import scripts._v2_002_lib as v2002_lib
from models.baselines import create_logistic_regression, create_random_forest
from nhm.hashing import hash_file
from nhm.model_v2_cv_role_guard import check_cv_role_allowed, record_feature_access
from nhm.model_v2_partition_guard import check_partition_allowed

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "V2-003"

FEATURE_MANIFEST = ROOT / "manifests/features/MITDB_BASELINE_FEATURES_V1.csv"
TRAIN_FEATURE_CACHE = (
    ROOT
    / "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/"
    "AAMI_SVF_WINDOW_V1/BASELINE_FEATURES_V1/TRAIN_features.npy"
)
FEATURE_SCHEMA_PATH = ROOT / "manifests/features/BASELINE_FEATURES_V1.schema.json"
BASELINE_V1_LOCK = ROOT / "manifests/baselines/BASELINE_V1.lock.json"
V2_003_CONFIG_PATH = ROOT / "configs/model_v2/classical_feature_audit_v1.yaml"
V2_002_DIR = ROOT / "reports/model_v2/v2_002"
MODEL_V1_THREE_SEED_MEAN_AUPRC = 0.4138882608052527
BOOTSTRAP_B = 2000

OUTER_FOLDS = v2002_lib.OUTER_FOLDS
role_groups_for_fold = v2002_lib.role_groups_for_fold
verify_role_closure = v2002_lib.verify_role_closure

VARIANT_IDS: tuple[str, ...] = ("STAT", "RR", "QRS", "RR_QRS", "STAT_RR", "STAT_QRS", "ALL")
MODEL_FAMILIES: tuple[str, ...] = ("LOGISTIC", "RF")

STAT_INDICES = tuple(range(0, 13))
RR_INDICES = tuple(range(13, 22))
QRS_INDICES = tuple(range(22, 29))

VARIANT_INDICES: dict[str, tuple[int, ...]] = {
    "STAT": STAT_INDICES,
    "RR": RR_INDICES,
    "QRS": QRS_INDICES,
    "RR_QRS": RR_INDICES + QRS_INDICES,
    "STAT_RR": STAT_INDICES + RR_INDICES,
    "STAT_QRS": STAT_INDICES + QRS_INDICES,
    "ALL": STAT_INDICES + RR_INDICES + QRS_INDICES,
}
assert [len(VARIANT_INDICES[v]) for v in VARIANT_IDS] == [13, 9, 7, 16, 22, 20, 29]


def experiment_id(variant: str, model_family: str, outer_fold: int) -> str:
    return f"V2-003-{variant}-{model_family}-F{outer_fold:02d}"


def load_config() -> dict:
    return yaml.safe_load(V2_003_CONFIG_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class FeaturePopulation:
    features: np.ndarray
    labels: np.ndarray
    example_ids: tuple[str, ...]
    participant_group_ids: np.ndarray
    record_ids: tuple[str, ...]


_FEATURE_CACHE_SINGLETON: np.ndarray | None = None
_MANIFEST_ROWS_SINGLETON: list[dict[str, str]] | None = None


def _load_train_feature_cache() -> tuple[np.ndarray, list[dict[str, str]]]:
    """Strategy 1 of Section 5: read the partition-separated TRAIN-only feature cache. Never
    opens VALIDATION_features.npy. Verifies the manifest's recorded hash for TRAIN rows against
    the actual cache file before trusting any row index into it."""
    global _FEATURE_CACHE_SINGLETON, _MANIFEST_ROWS_SINGLETON
    if _FEATURE_CACHE_SINGLETON is not None and _MANIFEST_ROWS_SINGLETON is not None:
        return _FEATURE_CACHE_SINGLETON, _MANIFEST_ROWS_SINGLETON
    with FEATURE_MANIFEST.open(newline="", encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))
    train_rows = [row for row in all_rows if row["partition"] == "TRAIN"]
    if not train_rows:
        raise RuntimeError("no TRAIN rows found in BASELINE_FEATURES_V1 manifest")
    expected_sha = {row["feature_cache_sha256"] for row in train_rows}
    if len(expected_sha) != 1:
        raise RuntimeError("TRAIN feature rows reference more than one cache file hash")
    actual_sha = hash_file(TRAIN_FEATURE_CACHE)
    if actual_sha != next(iter(expected_sha)):
        raise RuntimeError(
            f"TRAIN_features.npy hash mismatch: manifest={next(iter(expected_sha))} "
            f"actual={actual_sha}"
        )
    cache = np.load(TRAIN_FEATURE_CACHE, allow_pickle=False)
    if cache.shape != (len(train_rows), 29):
        raise RuntimeError(f"unexpected TRAIN feature cache shape {cache.shape}")
    _FEATURE_CACHE_SINGLETON = cache
    _MANIFEST_ROWS_SINGLETON = train_rows
    return cache, train_rows


def load_role_population(
    *,
    role: str,
    stage_id: str,
    requested_outer_fold: int,
    experiment_outer_fold: int,
    participant_group_ids: set[str],
    access_purpose: str,
    fit_scope_finalized: bool = False,
) -> FeaturePopulation:
    """The single gated feature-loading entry point for V2-003. Checks the CV-role firewall
    first (role permitted for this stage, correct fold, OUTER_TEST only after
    fit_scope_finalized), then the V2-001 partition firewall (TRAIN only), THEN reads the
    TRAIN-only feature cache filtered to the given patient groups. Records one ledger row."""
    check_cv_role_allowed(
        role,
        stage_id,
        requested_outer_fold=requested_outer_fold,
        experiment_outer_fold=experiment_outer_fold,
        checkpoint_finalized=fit_scope_finalized,
    )
    check_partition_allowed("TRAIN", TASK_ID, {"TRAIN"})

    cache, train_rows = _load_train_feature_cache()
    selected = [
        row for row in train_rows if row["participant_group_id"] in participant_group_ids
    ]
    if not selected:
        groups_repr = sorted(participant_group_ids)
        raise RuntimeError(f"no TRAIN feature rows found for groups {groups_repr}")
    selected.sort(key=lambda row: row["example_id"])
    row_indices = [int(row["feature_row_index"]) for row in selected]
    features = cache[row_indices, :].astype(np.float64, copy=True)
    labels = np.asarray([int(row["label"]) for row in selected], dtype=np.int64)
    example_ids = tuple(row["example_id"] for row in selected)
    groups = np.asarray([row["participant_group_id"] for row in selected], dtype=str)
    record_ids = tuple(row["record_id"] for row in selected)

    record_feature_access(
        ROOT,
        task_id=TASK_ID,
        experiment_id=f"F{experiment_outer_fold:02d}",
        outer_fold=experiment_outer_fold,
        role=role,
        stage_id=stage_id,
        participant_group_ids=participant_group_ids,
        example_id_count=len(selected),
        access_purpose=access_purpose,
    )
    return FeaturePopulation(features, labels, example_ids, groups, record_ids)


def fit_fold_local_transform(train_features: np.ndarray) -> tuple[SimpleImputer, StandardScaler]:
    """Fit a fresh imputer (median, keep_empty_features) and a fresh StandardScaler on the
    given (already column-subset) OPTIMISE feature matrix only. Reuses the exact sklearn
    classes/constructor arguments from models.baselines.FeatureTransformer.fit (which cannot
    be reused directly here since it is hardwired to the full 29-feature schema)."""
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    imputed = imputer.fit_transform(train_features)
    scaler = StandardScaler(with_mean=True, with_std=True)
    scaler.fit(imputed)
    return imputer, scaler


def load_model_v1_replicate_means() -> list[float | None]:
    """Reuse (never recompute) V2-002's own per-seed bootstrap replicates (reports/model_v2/
    v2_002/bootstrap_seed_metrics.csv): the MODEL_V1_CV_REFERENCE_V1 three-seed-mean AUPRC
    series on each SAME patient draw, for pairing against a V2-003 classical replicate."""
    path = V2_002_DIR / "bootstrap_seed_metrics.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_replicate: dict[int, list[float | None]] = {i: [] for i in range(BOOTSTRAP_B)}
    for row in rows:
        replicate = int(row["replicate"])
        value = None if row["AUPRC"] == "" else float(row["AUPRC"])
        by_replicate[replicate].append(value)
    means: list[float | None] = []
    for replicate in range(BOOTSTRAP_B):
        values = by_replicate[replicate]
        if len(values) != 3 or any(v is None for v in values):
            means.append(None)
        else:
            means.append(float(np.mean(values)))
    return means


def ci_from_values(values: list[float | None]) -> dict:
    valid = [v for v in values if v is not None]
    invalid = len(values) - len(valid)
    if not valid:
        return {"ci_lower_2_5": None, "ci_upper_97_5": None, "valid_B": 0, "invalid_B": invalid}
    lower, upper = np.percentile(np.asarray(valid), [2.5, 97.5])
    return {
        "ci_lower_2_5": float(lower),
        "ci_upper_97_5": float(upper),
        "valid_B": len(valid),
        "invalid_B": invalid,
    }


__all__ = [
    "BASELINE_V1_LOCK",
    "BOOTSTRAP_B",
    "FEATURE_MANIFEST",
    "FEATURE_SCHEMA_PATH",
    "MODEL_FAMILIES",
    "MODEL_V1_THREE_SEED_MEAN_AUPRC",
    "OUTER_FOLDS",
    "QRS_INDICES",
    "ROOT",
    "RR_INDICES",
    "STAT_INDICES",
    "TASK_ID",
    "TRAIN_FEATURE_CACHE",
    "V2_002_DIR",
    "V2_003_CONFIG_PATH",
    "VARIANT_IDS",
    "VARIANT_INDICES",
    "FeaturePopulation",
    "ci_from_values",
    "create_logistic_regression",
    "create_random_forest",
    "experiment_id",
    "fit_fold_local_transform",
    "load_config",
    "load_model_v1_replicate_means",
    "load_role_population",
    "role_groups_for_fold",
    "verify_role_closure",
]
