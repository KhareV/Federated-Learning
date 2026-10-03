"""Shared, reusable primitives for V2-006 (optimizer correction / finalist shortlist).

Mirrors scripts._v2_004_lib's structure and semantics exactly (role loading, firewall
wiring, optimizer/scheduler construction, training contract), but is fixed to the single
winning architecture (MODEL_V2_TCN_MEANMAX) and parameterized over SCHEDULE identity instead
of architecture identity, writing to its own V2-006 CV-role access ledger (never V2-004's).
Reuses training.train_central's primitives (dataset class, augmentation, validation/metric
computation, determinism routine) exactly, scripts._v2_004_lib's outer/inner CV manifests,
architecture factory, and frozen CONTROL config loader exactly, and
models.model_v2_architectures' pre-registered MODEL_V2_TCN_MEANMAX class exactly -- no
architecture or CV manifest is redefined here.
"""

from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

import scripts._v2_004_lib as v2004
from nhm.hashing import hash_file
from nhm.model_v2_cv_role_guard import check_cv_role_allowed, record_v2_006_cv_role_access
from nhm.model_v2_partition_guard import check_partition_allowed
from training.train_central import WindowPopulation

ROOT = Path(__file__).resolve().parents[1]
OUTER_CV_CSV = v2004.OUTER_CV_CSV
INNER_CV_CSV = v2004.INNER_CV_CSV
SPLIT_CSV = v2004.SPLIT_CSV
WINDOW_MANIFEST = v2004.WINDOW_MANIFEST
CACHE_MANIFEST = v2004.CACHE_MANIFEST
CONFIG_PATH = v2004.CONFIG_PATH
V2_006_CONFIG_PATH = ROOT / "configs/model_v2/optimizer_correction_v1.yaml"
TASK_ID = "V2-006"

ARCHITECTURE_ID = "MODEL_V2_TCN_MEANMAX"
EXPECTED_PARAMETER_COUNT = 57577

ALL_SEEDS = (20260927, 20260928, 20260929)
OUTER_FOLDS = (0, 1, 2, 3, 4)

CONTROL_SCHEDULE_ID = "MODEL_V2_TCN_MEANMAX_ORIGINAL_V1"
CHALLENGER_SCHEDULE_ID = "MODEL_V2_OPTIMIZER_CORRECTED_V1"

# Only permitted changes relative to CONTROL (Section 8 of the V2-006 spec).
CHALLENGER_SCHEDULER_OVERRIDES = {"patience": 3, "factor": 0.3}
CHALLENGER_EARLY_STOP_PATIENCE = 8


def build_architecture() -> nn.Module:
    return v2004.build_architecture(ARCHITECTURE_ID)


def experiment_id(outer_fold: int, seed: int) -> str:
    return f"V2-006-OPT-CORR-F{outer_fold:02d}-S{seed}"


def load_frozen_model_v1_config() -> tuple[dict[str, Any], str]:
    """The exact same CONTROL training contract V2-004 reused (configs/model_v1.yaml) --
    identical call to scripts._v2_004_lib.load_frozen_model_v1_config."""
    return v2004.load_frozen_model_v1_config()


def build_challenger_config(control_config: dict[str, Any]) -> dict[str, Any]:
    """Deep-copies the CONTROL config and overrides ONLY scheduler patience/factor and
    training.early_stopping_patience -- every other field (optimizer LR/weight-decay/betas/
    eps, batch_size, max_epochs, augmentation, loss, determinism) is inherited unchanged."""
    challenger = copy.deepcopy(control_config)
    challenger["scheduler"]["patience"] = CHALLENGER_SCHEDULER_OVERRIDES["patience"]
    challenger["scheduler"]["factor"] = CHALLENGER_SCHEDULER_OVERRIDES["factor"]
    challenger["training"]["early_stopping_patience"] = CHALLENGER_EARLY_STOP_PATIENCE
    return challenger


def build_optimizer_and_scheduler(
    model: nn.Module, config: dict[str, Any]
) -> tuple[torch.optim.Optimizer, torch.optim.lr_scheduler.ReduceLROnPlateau]:
    """Identical construction call to scripts._v2_004_lib.build_optimizer_and_scheduler;
    the challenger-vs-control difference is expressed entirely in the `config` dict passed
    in (built by build_challenger_config), never in this function's code."""
    return v2004.build_optimizer_and_scheduler(model, config)


@dataclass(frozen=True)
class RolePopulations:
    optimise_groups: list[str]
    inner_groups: list[str]
    outer_groups: list[str]


def role_groups_for_fold(fold: int) -> RolePopulations:
    populations = v2004.role_groups_for_fold(fold)
    return RolePopulations(
        optimise_groups=populations.optimise_groups,
        inner_groups=populations.inner_groups,
        outer_groups=populations.outer_groups,
    )


def verify_role_closure(roles: RolePopulations) -> None:
    v2004.verify_role_closure(
        v2004.RolePopulations(
            optimise_groups=roles.optimise_groups,
            inner_groups=roles.inner_groups,
            outer_groups=roles.outer_groups,
        )
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def train_record_ids_for_groups(participant_group_ids: set[str]) -> set[str]:
    return v2004.train_record_ids_for_groups(participant_group_ids)


def derive_pos_weight(labels: np.ndarray) -> dict[str, Any]:
    return v2004.derive_pos_weight(labels)


def set_determinism(seed: int) -> None:
    v2004.set_determinism(seed)


def _make_loaders(optimise_population, inner_population, *, seed: int, config: dict):
    return v2004._make_loaders(optimise_population, inner_population, seed=seed, config=config)


def _validate(model, loader, criterion, labels, groups):
    return v2004._validate(model, loader, criterion, labels, groups)


def _checkpoint_payload(
    model, *, seed: int, epoch: int, validation_auprc: float, config_sha256: str
):
    return v2004._checkpoint_payload(
        model, seed=seed, epoch=epoch, validation_auprc=validation_auprc,
        config_sha256=config_sha256,
    )


def load_role_population(
    *,
    role: str,
    stage_id: str,
    requested_outer_fold: int,
    experiment_outer_fold: int,
    configuration: str,
    seed: int,
    participant_group_ids: list[str],
    checkpoint_finalized: bool = False,
    access_purpose: str,
    dataset_partition_label: str,
) -> tuple[WindowPopulation, dict[str, dict[str, str]]]:
    """Fail-closed waveform load for one CV role, identical in mechanism to V2-004's loader
    but writing to V2-006's own ledger (record_v2_006_cv_role_access) with a `configuration`
    field (the schedule identity) instead of V2-004's `architecture_id`, since V2-006 fixes
    the architecture and varies only the optimizer/scheduler schedule."""
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
    record_v2_006_cv_role_access(
        ROOT,
        task_id=TASK_ID,
        stage_id=stage_id,
        configuration=configuration,
        seed=seed,
        outer_fold=requested_outer_fold,
        role=role,
        access_purpose=access_purpose,
        participant_group_ids=groups,
        example_id_count=len(example_ids),
        checkpoint_finalized=checkpoint_finalized,
    )
    return population, example_meta


__all__ = [
    "ALL_SEEDS",
    "ARCHITECTURE_ID",
    "CACHE_MANIFEST",
    "CHALLENGER_EARLY_STOP_PATIENCE",
    "CHALLENGER_SCHEDULER_OVERRIDES",
    "CHALLENGER_SCHEDULE_ID",
    "CONFIG_PATH",
    "CONTROL_SCHEDULE_ID",
    "EXPECTED_PARAMETER_COUNT",
    "INNER_CV_CSV",
    "OUTER_CV_CSV",
    "OUTER_FOLDS",
    "SPLIT_CSV",
    "TASK_ID",
    "V2_006_CONFIG_PATH",
    "WINDOW_MANIFEST",
    "RolePopulations",
    "build_architecture",
    "build_challenger_config",
    "build_optimizer_and_scheduler",
    "derive_pos_weight",
    "experiment_id",
    "load_frozen_model_v1_config",
    "load_role_population",
    "role_groups_for_fold",
    "set_determinism",
    "train_record_ids_for_groups",
    "verify_role_closure",
]
