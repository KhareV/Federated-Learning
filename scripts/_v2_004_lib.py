"""Shared, reusable primitives for V2-004 (architecture causality experiment). Mirrors
scripts._v2_002_lib's structure and semantics exactly (role loading, firewall wiring,
optimizer/scheduler construction, training contract), but is parameterized over THREE
pre-registered architectures instead of being hardwired to MODEL_V1, and writes to its own
V2-004 CV-role access ledger (never V2-002's). Reuses training.train_central's primitives
(dataset class, augmentation, validation/metric computation, determinism routine) exactly,
and models.model_v2_architectures' pre-registered, already-tested architecture classes exactly
-- no architecture is redefined here.
"""

from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from torch import nn
from torch.utils.data import DataLoader

from models.model_v2_architectures import (
    ModelV2CapCtrl,
    ModelV2TcnMean,
    ModelV2TcnMeanMax,
    analytic_tcn_receptive_field_samples,
    count_trainable_parameters,
)
from nhm.hashing import hash_file
from nhm.model_v2_cv_role_guard import check_cv_role_allowed, record_v2_004_cv_role_access
from nhm.model_v2_partition_guard import check_partition_allowed
from training.train_central import (
    ModelV1WindowDataset,
    WindowPopulation,
    _checkpoint_payload,
    _make_loaders,
    _validate,
    augment_train_window,  # noqa: F401 -- re-exported for callers that want it directly
    derive_pos_weight,
    set_determinism,
)

ROOT = Path(__file__).resolve().parents[1]
OUTER_CV_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"
INNER_CV_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
SPLIT_CSV = ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"
WINDOW_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
CACHE_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv"
CONFIG_PATH = ROOT / "configs/model_v1.yaml"
V2_CONFIG_PATH = ROOT / "configs/model_v2/architecture_causality_v1.yaml"
TASK_ID = "V2-004"

D1_SEED = 20260927
D2_SEEDS = (20260928, 20260929)
ALL_SEEDS = (D1_SEED, *D2_SEEDS)
OUTER_FOLDS = (0, 1, 2, 3, 4)

ARCHITECTURE_IDS: tuple[str, ...] = (
    "MODEL_V2_CAPCTRL",
    "MODEL_V2_TCN_MEAN",
    "MODEL_V2_TCN_MEANMAX",
)
ARCHITECTURE_FACTORIES = {
    "MODEL_V2_CAPCTRL": ModelV2CapCtrl,
    "MODEL_V2_TCN_MEAN": ModelV2TcnMean,
    "MODEL_V2_TCN_MEANMAX": ModelV2TcnMeanMax,
}
ARCHITECTURE_SHORT_NAMES = {
    "MODEL_V2_CAPCTRL": "CAPCTRL",
    "MODEL_V2_TCN_MEAN": "TCNMEAN",
    "MODEL_V2_TCN_MEANMAX": "MEANMAX",
}
EXPECTED_PARAMETER_COUNTS = {
    "MODEL_V2_CAPCTRL": 51969,
    "MODEL_V2_TCN_MEAN": 57553,
    "MODEL_V2_TCN_MEANMAX": 57577,
}
PARAMETER_COUNT_HARD_CAP = 120000
EXPECTED_TCN_RECEPTIVE_FIELD_SAMPLES = 3063


def build_architecture(architecture_id: str) -> nn.Module:
    """Fresh instantiation only -- never loads MODEL_V1 or another candidate's weights."""
    factory = ARCHITECTURE_FACTORIES[architecture_id]
    return factory()


def experiment_id(stage: str, architecture_id: str, outer_fold: int, seed: int) -> str:
    short = ARCHITECTURE_SHORT_NAMES[architecture_id]
    return f"V2-004-{stage}-{short}-F{outer_fold:02d}-S{seed}"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_role_assignments() -> dict[int, dict[str, list[str]]]:
    """fold -> {role: [participant_group_id, ...]}, reused unchanged from the frozen V2-001
    inner-CV manifest (identical source V2-002 reads; never regenerated)."""
    assignments: dict[int, dict[str, list[str]]] = {f: {} for f in OUTER_FOLDS}
    for row in _read_csv(INNER_CV_CSV):
        fold = int(row["outer_fold"])
        role = row["role"]
        assignments[fold].setdefault(role, []).append(row["participant_group_id"])
    return assignments


def train_record_ids_for_groups(participant_group_ids: set[str]) -> set[str]:
    return {
        row["record_id"]
        for row in _read_csv(SPLIT_CSV)
        if row["partition"] == "TRAIN" and row["participant_group_id"] in participant_group_ids
    }


@dataclass(frozen=True)
class RolePopulations:
    optimise_groups: list[str]
    inner_groups: list[str]
    outer_groups: list[str]


def role_groups_for_fold(fold: int) -> RolePopulations:
    assignments = load_role_assignments()[fold]
    return RolePopulations(
        optimise_groups=sorted(assignments.get("OPTIMISE", [])),
        inner_groups=sorted(assignments.get("INNER_VALIDATION", [])),
        outer_groups=sorted(assignments.get("OUTER_TEST", [])),
    )


def verify_role_closure(roles: RolePopulations) -> None:
    optimise = set(roles.optimise_groups)
    inner = set(roles.inner_groups)
    outer = set(roles.outer_groups)
    if optimise & inner or optimise & outer or inner & outer:
        raise RuntimeError("CV role sets are not pairwise disjoint")
    train_groups = {
        row["participant_group_id"] for row in _read_csv(SPLIT_CSV) if row["partition"] == "TRAIN"
    }
    union = optimise | inner | outer
    if union != train_groups:
        raise RuntimeError(
            f"CV role union does not equal all 27 TRAIN groups: "
            f"missing={train_groups - union}, extra={union - train_groups}"
        )
    if len(inner) != 4:
        raise RuntimeError(f"expected exactly 4 INNER_VALIDATION groups, got {len(inner)}")


def load_role_population(
    *,
    role: str,
    stage_id: str,
    requested_outer_fold: int,
    experiment_outer_fold: int,
    architecture_id: str,
    seed: int,
    participant_group_ids: list[str],
    checkpoint_finalized: bool = False,
    access_purpose: str,
    dataset_partition_label: str,
) -> tuple[WindowPopulation, dict[str, dict[str, str]]]:
    """Fail-closed waveform load for one CV role, identical in mechanism to V2-002's loader
    but writing to V2-004's own ledger (record_v2_004_cv_role_access) with an architecture_id
    field, since D1/D2 span three architectures rather than one model identity."""
    check_cv_role_allowed(
        role,
        stage_id,
        requested_outer_fold=requested_outer_fold,
        experiment_outer_fold=experiment_outer_fold,
        checkpoint_finalized=checkpoint_finalized,
    )
    check_partition_allowed("TRAIN", TASK_ID, {"TRAIN"})

    groups = set(participant_group_ids)
    record_ids = train_record_ids_for_groups(groups)
    selected = {
        row["example_id"]: row
        for row in _read_csv(WINDOW_MANIFEST)
        if row["partition"] == "TRAIN"
        and row["core_eligible"].upper() == "TRUE"
        and row["participant_group_id"] in groups
    }
    cache_rows = sorted(
        (
            row
            for row in _read_csv(CACHE_MANIFEST)
            if row["partition"] == "TRAIN" and row["record_id"] in record_ids
        ),
        key=lambda row: row["record_id"],
    )
    windows: list[np.ndarray] = []
    labels: list[int] = []
    example_ids: list[str] = []
    out_groups: list[str] = []
    paths: list[str] = []
    example_meta: dict[str, dict[str, str]] = {}
    for cache in cache_rows:
        waveform_path = ROOT / cache["relative_path"]
        id_path = ROOT / cache["example_ids_path"]
        paths.extend([cache["relative_path"], cache["example_ids_path"]])
        if hash_file(waveform_path) != cache["sha256"]:
            raise RuntimeError(f"frozen waveform cache hash mismatch: {waveform_path}")
        if hash_file(id_path) != cache["example_ids_sha256"]:
            raise RuntimeError(f"frozen example-ID cache hash mismatch: {id_path}")
        array = np.load(waveform_path, allow_pickle=False)
        ids = id_path.read_text(encoding="utf-8").splitlines()
        if array.shape != (len(ids), 2500):
            raise RuntimeError(f"cache/ID shape mismatch: {cache['record_id']}")
        for waveform, example_id in zip(array, ids, strict=True):
            row = selected.pop(example_id, None)
            if row is None:
                continue
            label = row["label"]
            if label not in {"0", "1"}:
                raise RuntimeError(f"non-binary eligible label: {label!r}")
            windows.append(waveform)
            labels.append(int(label))
            example_ids.append(example_id)
            out_groups.append(row["participant_group_id"])
            example_meta[example_id] = {
                "record_id": row["record_id"],
                "prediction_timestamp_us": row["prediction_timestamp_us"],
            }
    if selected:
        raise RuntimeError(f"eligible manifest examples missing from cache: {len(selected)}")

    population = WindowPopulation(
        partition=dataset_partition_label,
        waveforms=np.stack(windows).astype(np.float64, copy=False),
        labels=np.asarray(labels, dtype=np.int64),
        example_ids=tuple(example_ids),
        participant_group_ids=np.asarray(out_groups, dtype=str),
        accessed_paths=tuple(paths),
    )
    record_v2_004_cv_role_access(
        ROOT,
        task_id=TASK_ID,
        stage_id=stage_id,
        architecture_id=architecture_id,
        seed=seed,
        outer_fold=requested_outer_fold,
        role=role,
        access_purpose=access_purpose,
        participant_group_ids=groups,
        example_id_count=len(example_ids),
        checkpoint_finalized=checkpoint_finalized,
    )
    return population, example_meta


def load_frozen_model_v1_config() -> tuple[dict[str, Any], str]:
    """The exact T015/V2-002 training contract (configs/model_v1.yaml) -- architecture is the
    only intended experimental variable, so the training contract itself is reused unchanged,
    never the later-corrected V2-006 optimizer schedule."""
    config_sha256 = hash_file(CONFIG_PATH)
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return config, config_sha256


def build_optimizer_and_scheduler(
    model: nn.Module, config: dict[str, Any]
) -> tuple[torch.optim.Optimizer, torch.optim.lr_scheduler.ReduceLROnPlateau]:
    """Mirrors training.train_central.train_seed's optimizer/scheduler construction exactly
    (same config keys, same call signature) -- identical to scripts._v2_002_lib's version."""
    optimizer_config = config["optimizer"]
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=optimizer_config["learning_rate"],
        betas=tuple(optimizer_config["betas"]),
        eps=optimizer_config["epsilon"],
        weight_decay=optimizer_config["weight_decay"],
        amsgrad=optimizer_config["amsgrad"],
        maximize=optimizer_config["maximize"],
        foreach=optimizer_config["foreach"],
        capturable=optimizer_config["capturable"],
        differentiable=optimizer_config["differentiable"],
        fused=optimizer_config["fused"],
    )
    scheduler_config = config["scheduler"]
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="max",
        factor=scheduler_config["factor"],
        patience=scheduler_config["patience"],
        threshold=scheduler_config["threshold"],
        threshold_mode=scheduler_config["threshold_mode"],
        cooldown=scheduler_config["cooldown"],
        min_lr=scheduler_config["min_lr"],
        eps=scheduler_config["epsilon"],
    )
    return optimizer, scheduler


__all__ = [
    "ALL_SEEDS",
    "ARCHITECTURE_FACTORIES",
    "ARCHITECTURE_IDS",
    "ARCHITECTURE_SHORT_NAMES",
    "CONFIG_PATH",
    "D1_SEED",
    "D2_SEEDS",
    "EXPECTED_PARAMETER_COUNTS",
    "EXPECTED_TCN_RECEPTIVE_FIELD_SAMPLES",
    "INNER_CV_CSV",
    "OUTER_CV_CSV",
    "OUTER_FOLDS",
    "PARAMETER_COUNT_HARD_CAP",
    "ROOT",
    "SPLIT_CSV",
    "TASK_ID",
    "V2_CONFIG_PATH",
    "DataLoader",
    "ModelV1WindowDataset",
    "RolePopulations",
    "WindowPopulation",
    "_checkpoint_payload",
    "_make_loaders",
    "_validate",
    "analytic_tcn_receptive_field_samples",
    "build_architecture",
    "build_optimizer_and_scheduler",
    "count_trainable_parameters",
    "derive_pos_weight",
    "experiment_id",
    "load_frozen_model_v1_config",
    "load_role_population",
    "math",
    "role_groups_for_fold",
    "set_determinism",
    "time",
    "verify_role_closure",
]
