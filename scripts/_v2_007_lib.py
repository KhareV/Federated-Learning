"""Shared, reusable primitives for V2-007 (official validation). Reuses
scripts._v2_004_lib's architecture/config/optimizer primitives and training.train_central's
dataset/augmentation/determinism primitives exactly -- nothing scientific is reinvented here.
Adds V2-007-specific role loading: no fold dimension (one fixed FINAL TRAIN-only split, not
per-outer-fold), a TRAIN-source diagnostic loader (all 27 TRAIN groups, no gradient), and a
NEW official-VALIDATION loader gated by both the partition firewall (nhm.model_v2_partition_guard)
and an extended CV-role firewall (nhm.model_v2_cv_role_guard) requiring checkpoint_finalized=True.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from torch import nn

import scripts._v2_004_lib as v2004
from models.ecg_cnn import build_model_v1
from nhm.hashing import hash_file
from nhm.model_v2_cv_role_guard import check_cv_role_allowed, record_v2_007_cv_role_access
from nhm.model_v2_partition_guard import check_partition_allowed
from training.train_central import (
    ModelV1WindowDataset,
    WindowPopulation,
    _checkpoint_payload,
    _make_loaders,
    _validate,
    derive_pos_weight,
    set_determinism,
)

ROOT = Path(__file__).resolve().parents[1]
FINAL_INNER_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.csv"
SPLIT_CSV = v2004.SPLIT_CSV
WINDOW_MANIFEST = v2004.WINDOW_MANIFEST
CACHE_MANIFEST = v2004.CACHE_MANIFEST
CONFIG_PATH = v2004.CONFIG_PATH
V2_CONFIG_PATH = ROOT / "configs/model_v2/official_validation_v1.yaml"
TASK_ID = "V2-007"

SEEDS: tuple[int, ...] = (20260927, 20260928, 20260929)
RELEASE_SEED = 20260927

FINALISTS: tuple[dict[str, str], ...] = (
    {"finalist": "A", "architecture_id": "MODEL_V2_TCN_MEAN",
     "schedule_id": "CONFIG_V2_TCN_MEAN_ORIGINAL_V1"},
    {"finalist": "B", "architecture_id": "MODEL_V2_TCN_MEANMAX",
     "schedule_id": "CONFIG_V2_TCN_MEANMAX_ORIGINAL_V1"},
)
ARCHITECTURE_SHORT_NAMES: dict[str, str] = {
    "MODEL_V2_TCN_MEAN": "TCNMEAN",
    "MODEL_V2_TCN_MEANMAX": "TCNMEANMAX",
}
EXPECTED_PARAMETER_COUNTS: dict[str, int] = {
    "MODEL_V2_TCN_MEAN": 57553,
    "MODEL_V2_TCN_MEANMAX": 57577,
}

build_architecture = v2004.build_architecture
load_frozen_model_v1_config = v2004.load_frozen_model_v1_config
build_optimizer_and_scheduler = v2004.build_optimizer_and_scheduler
DataLoader = v2004.DataLoader

# V2-007 has no fold dimension; the shared check_cv_role_allowed signature still requires a
# requested/experiment outer-fold pair, so a fixed synthetic value is passed on both sides
# (0 == 0) -- this never collides with any real outer-fold value used by V2-004/V2-006.
NO_FOLD = 0


def experiment_id(architecture_id: str, seed: int) -> str:
    short = ARCHITECTURE_SHORT_NAMES[architecture_id]
    return f"V2-007-{short}-S{seed}"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_final_inner_roles() -> tuple[list[str], list[str]]:
    """Returns (optimise_groups, final_inner_validation_groups), both sorted."""
    optimise, final_inner = [], []
    for row in _read_csv(FINAL_INNER_CSV):
        (optimise if row["role"] == "OPTIMISE" else final_inner).append(
            row["participant_group_id"]
        )
    return sorted(optimise), sorted(final_inner)


def all_train_groups() -> list[str]:
    optimise, final_inner = load_final_inner_roles()
    return sorted(optimise + final_inner)


def verify_final_inner_closure(optimise: list[str], final_inner: list[str]) -> None:
    opt, fin = set(optimise), set(final_inner)
    if opt & fin:
        raise RuntimeError("OPTIMISE/FINAL_INNER_VALIDATION are not disjoint")
    train_groups = {
        row["participant_group_id"] for row in _read_csv(SPLIT_CSV) if row["partition"] == "TRAIN"
    }
    union = opt | fin
    if union != train_groups:
        raise RuntimeError(
            f"FINAL TRAIN-only role union != all 27 TRAIN groups: "
            f"missing={train_groups - union}, extra={union - train_groups}"
        )
    if len(fin) != 5:
        raise RuntimeError(f"expected exactly 5 FINAL_INNER_VALIDATION groups, got {len(fin)}")


def train_record_ids_for_groups(participant_group_ids: set[str]) -> set[str]:
    return v2004.train_record_ids_for_groups(participant_group_ids)


def _load_waveform_population(
    *, partition: str, groups: set[str], dataset_partition_label: str
) -> tuple[WindowPopulation, dict[str, dict[str, str]]]:
    if partition == "TRAIN":
        record_ids = train_record_ids_for_groups(groups)
    else:
        record_ids = {
            row["record_id"]
            for row in _read_csv(SPLIT_CSV)
            if row["partition"] == partition and row["participant_group_id"] in groups
        }
    selected = {
        row["example_id"]: row
        for row in _read_csv(WINDOW_MANIFEST)
        if row["partition"] == partition
        and row["core_eligible"].upper() == "TRUE"
        and row["participant_group_id"] in groups
    }
    cache_rows = sorted(
        (
            row
            for row in _read_csv(CACHE_MANIFEST)
            if row["partition"] == partition and row["record_id"] in record_ids
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
    return population, example_meta


def load_role_population(
    *,
    role: str,
    stage_id: str,
    architecture_id: str,
    schedule_id: str,
    seed: int,
    participant_group_ids: list[str],
    checkpoint_finalized: bool = False,
    access_purpose: str,
    dataset_partition_label: str,
) -> tuple[WindowPopulation, dict[str, dict[str, str]]]:
    """Fail-closed TRAIN-partition waveform load for OPTIMISE / FINAL_INNER_VALIDATION (no
    fold dimension -- one fixed final-inner split, not per-outer-fold)."""
    check_cv_role_allowed(
        role, stage_id, requested_outer_fold=NO_FOLD, experiment_outer_fold=NO_FOLD,
        checkpoint_finalized=checkpoint_finalized,
    )
    check_partition_allowed("TRAIN", TASK_ID, {"TRAIN"})
    groups = set(participant_group_ids)
    population, example_meta = _load_waveform_population(
        partition="TRAIN", groups=groups, dataset_partition_label=dataset_partition_label
    )
    record_v2_007_cv_role_access(
        ROOT, task_id=TASK_ID, stage_id=stage_id, architecture_id=architecture_id,
        schedule_id=schedule_id, seed=seed, role=role, access_purpose=access_purpose,
        participant_group_ids=groups, example_id_count=len(population.example_ids),
        checkpoint_finalized=checkpoint_finalized,
    )
    return population, example_meta


def load_official_validation_population(
    *,
    architecture_id: str,
    schedule_id: str,
    seed: int,
    participant_group_ids: list[str],
    checkpoint_finalized: bool,
    access_purpose: str,
) -> tuple[WindowPopulation, dict[str, dict[str, str]]]:
    """Fail-closed official-VALIDATION-partition waveform load. Requires
    checkpoint_finalized=True (enforced by the CV-role firewall's OFFICIAL_VALIDATION rule) --
    callers must have already fixed/frozen the checkpoint being scored before calling this."""
    check_cv_role_allowed(
        "OFFICIAL_VALIDATION", "V2-007_OFFICIAL_VALIDATION",
        requested_outer_fold=NO_FOLD, experiment_outer_fold=NO_FOLD,
        checkpoint_finalized=checkpoint_finalized,
    )
    check_partition_allowed("VALIDATION", "V2-007_OFFICIAL_VALIDATION", {"VALIDATION"})
    groups = set(participant_group_ids)
    population, example_meta = _load_waveform_population(
        partition="VALIDATION", groups=groups, dataset_partition_label="VALIDATION"
    )
    record_v2_007_cv_role_access(
        ROOT, task_id=TASK_ID, stage_id="V2-007_OFFICIAL_VALIDATION",
        architecture_id=architecture_id, schedule_id=schedule_id, seed=seed,
        role="OFFICIAL_VALIDATION", access_purpose=access_purpose,
        participant_group_ids=groups, example_id_count=len(population.example_ids),
        checkpoint_finalized=checkpoint_finalized,
    )
    return population, example_meta


def official_validation_groups() -> list[str]:
    return sorted(
        {
            row["participant_group_id"]
            for row in _read_csv(SPLIT_CSV)
            if row["partition"] == "VALIDATION"
        }
    )


def eval_loader(population: WindowPopulation, *, seed: int, config: dict[str, Any]) -> DataLoader:
    dataset = ModelV1WindowDataset(
        population, training=False, seed=seed, augmentation_config=config["augmentation"]
    )
    return DataLoader(
        dataset, batch_size=config["training"]["batch_size"], shuffle=False, drop_last=False,
        num_workers=0,
    )


def score_checkpoint(
    model: nn.Module, population: WindowPopulation, *, seed: int, config: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    """model.eval() + torch.inference_mode() scoring only -- no gradient, no augmentation, no
    BatchNorm update, no dropout, no calibration, no threshold. Returns
    (raw_logits, raw_probabilities, example_ids, participant_group_ids) in loader-emission
    order (population is already example_id-sorted in its own fixed load order)."""
    model.eval()
    loader = eval_loader(population, seed=seed, config=config)
    logits: list[np.ndarray] = []
    ex_ids: list[str] = []
    groups: list[str] = []
    with torch.inference_mode():
        for inputs, _targets, example_ids, group_ids in loader:
            out = model(inputs)
            logits.append(out.cpu().numpy().reshape(-1))
            ex_ids.extend(example_ids)
            groups.extend(group_ids)
    raw_logits = np.concatenate(logits)
    if not np.all(np.isfinite(raw_logits)):
        raise RuntimeError("nonfinite scoring logits")
    raw_probabilities = 1.0 / (1.0 + np.exp(-raw_logits))
    return raw_logits, raw_probabilities, ex_ids, groups


def load_v1_checkpoint(seed: int) -> nn.Module:
    path = ROOT / f"checkpoints/candidates/MODEL_V1/MODEL_V1_seed_{seed}_best.pt"
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = build_model_v1().eval()
    model.load_state_dict(payload["state_dict"])
    return model


def load_v2_checkpoint(architecture_id: str, checkpoint_path: Path) -> nn.Module:
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = build_architecture(architecture_id).eval()
    model.load_state_dict(payload["state_dict"])
    return model


__all__ = [
    "ARCHITECTURE_SHORT_NAMES",
    "CACHE_MANIFEST",
    "CONFIG_PATH",
    "EXPECTED_PARAMETER_COUNTS",
    "FINALISTS",
    "FINAL_INNER_CSV",
    "NO_FOLD",
    "RELEASE_SEED",
    "ROOT",
    "SEEDS",
    "SPLIT_CSV",
    "TASK_ID",
    "V2_CONFIG_PATH",
    "WINDOW_MANIFEST",
    "DataLoader",
    "ModelV1WindowDataset",
    "WindowPopulation",
    "_checkpoint_payload",
    "_make_loaders",
    "_validate",
    "all_train_groups",
    "build_architecture",
    "build_optimizer_and_scheduler",
    "derive_pos_weight",
    "eval_loader",
    "experiment_id",
    "load_final_inner_roles",
    "load_frozen_model_v1_config",
    "load_official_validation_population",
    "load_role_population",
    "load_v1_checkpoint",
    "load_v2_checkpoint",
    "official_validation_groups",
    "score_checkpoint",
    "set_determinism",
    "train_record_ids_for_groups",
    "verify_final_inner_closure",
    "yaml",
]
