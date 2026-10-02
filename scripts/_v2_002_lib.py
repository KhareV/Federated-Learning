"""Shared, reusable primitives for V2-002 (MODEL_V1_CV_REFERENCE_V1). Imported by the
per-fit runner, the OOF/bootstrap aggregators, and the freeze/evidence scripts -- never
duplicated across those entry points. Reuses training.train_central's primitives (dataset
class, augmentation, validation/metric computation, determinism routine, model factory)
exactly, rather than reimplementing T015 semantics.
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

from nhm.hashing import hash_file
from nhm.model_v2_cv_role_guard import check_cv_role_allowed, record_cv_role_access
from training.train_central import (
    ModelV1WindowDataset,
    WindowPopulation,
    _checkpoint_payload,
    _make_loaders,
    _validate,
    augment_train_window,  # noqa: F401 -- re-exported for callers that want it directly
    build_model_v1,
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
V2_CONFIG_PATH = ROOT / "configs/model_v2/model_v1_cv_reference_v1.yaml"
TASK_ID = "V2-002"
SEEDS = (20260927, 20260928, 20260929)
OUTER_FOLDS = (0, 1, 2, 3, 4)


def experiment_id(outer_fold: int, seed: int) -> str:
    return f"V2-002-F{outer_fold:02d}-S{seed}"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_role_assignments() -> dict[int, dict[str, list[str]]]:
    """fold -> {role: [participant_group_id, ...]} derived from the frozen inner-CV manifest
    (which already encodes OUTER_TEST/INNER_VALIDATION/OPTIMISE for every TRAIN patient and
    every fold)."""
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


def load_role_population(
    *,
    role: str,
    stage_id: str,
    requested_outer_fold: int,
    experiment_outer_fold: int,
    seed: int,
    exp_id: str,
    participant_group_ids: list[str],
    checkpoint_finalized: bool = False,
    access_purpose: str,
    dataset_partition_label: str,
) -> tuple[WindowPopulation, dict[str, dict[str, str]]]:
    """Fail-closed waveform load for one CV role. Checks the CV-role firewall, then the
    existing partition firewall (defense in depth), then loads from the frozen T013 TRAIN
    cache (filtered to the given patient groups only), then records the access ledger row.
    `dataset_partition_label` is the WindowPopulation.partition value handed to the reused
    training.train_central.ModelV1WindowDataset/_make_loaders -- it must be "TRAIN" for any
    role fed into training (OPTIMISE) and "VALIDATION" for any role evaluated without
    augmentation (INNER_VALIDATION, OUTER_TEST), matching that class's own assertions; it is
    purely an internal dataset-class discriminator and carries no partition-access meaning of
    its own (the actual partition-access check happens separately, below)."""
    check_cv_role_allowed(
        role,
        stage_id,
        requested_outer_fold=requested_outer_fold,
        experiment_outer_fold=experiment_outer_fold,
        checkpoint_finalized=checkpoint_finalized,
    )
    from nhm.model_v2_partition_guard import check_partition_allowed

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
                continue  # example from this record belongs to a different role's group set
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
    record_cv_role_access(
        ROOT,
        task_id=TASK_ID,
        experiment_id=exp_id,
        outer_fold=requested_outer_fold,
        seed=seed,
        role=role,
        stage_id=stage_id,
        participant_group_ids=groups,
        example_id_count=len(example_ids),
        access_purpose=access_purpose,
    )
    return population, example_meta


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
        row["participant_group_id"]
        for row in _read_csv(SPLIT_CSV)
        if row["partition"] == "TRAIN"
    }
    union = optimise | inner | outer
    if union != train_groups:
        raise RuntimeError(
            f"CV role union does not equal all 27 TRAIN groups: "
            f"missing={train_groups - union}, extra={union - train_groups}"
        )
    if len(inner) != 4:
        raise RuntimeError(f"expected exactly 4 INNER_VALIDATION groups, got {len(inner)}")


def load_frozen_model_v1_config() -> tuple[dict[str, Any], str]:
    config_sha256 = hash_file(CONFIG_PATH)
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return config, config_sha256


def build_optimizer_and_scheduler(
    model: nn.Module, config: dict[str, Any]
) -> tuple[torch.optim.Optimizer, torch.optim.lr_scheduler.ReduceLROnPlateau]:
    """Mirrors training.train_central.train_seed's optimizer/scheduler construction exactly
    (same config keys, same call signature)."""
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
    "CONFIG_PATH",
    "INNER_CV_CSV",
    "OUTER_CV_CSV",
    "OUTER_FOLDS",
    "ROOT",
    "SEEDS",
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
    "build_model_v1",
    "build_optimizer_and_scheduler",
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
