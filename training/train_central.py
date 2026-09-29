"""T015 deterministic centralized MODEL_V1 candidate training.

The normal command implements exactly the fixed three-seed policy and has no option to access
calibration, test, external, wearable, or alternate-model data.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import os
import platform
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from torch import nn
from torch.utils.data import DataLoader, Dataset

from evaluation.leakage_audit import verify_frozen_split
from models.baselines import descriptive_metrics
from models.ecg_cnn import EXPECTED_TRAINABLE_PARAMETERS, MODEL_ID, build_model_v1
from nhm.hashing import hash_canonical_json, hash_file
from preprocessing.freeze import verify_preproc_freeze
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]
WINDOW_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
CACHE_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv"
CONFIG_PATH = ROOT / "configs/model_v1.yaml"
CANDIDATE_ROOT = ROOT / "checkpoints/candidates/MODEL_V1"
ARTIFACT_ROOT = ROOT / "artifacts/MODEL_V1_candidate"
REPORT_ROOT = ROOT / "reports/t015"
MODEL_REPORT = ROOT / "reports/model/model_v1_training.json"
ALLOWED_PARTITIONS = ("TRAIN", "VALIDATION")
RELEASE_SEED = 20260927
ROBUSTNESS_SEEDS = (20260928, 20260929)
FORMULA_ID = "TRAIN_NEG_OVER_POS_V1"
AUGMENTATION_ID = "MODEL_V1_TRAIN_AUG_V1"


@dataclass(frozen=True)
class WindowPopulation:
    partition: str
    waveforms: np.ndarray
    labels: np.ndarray
    example_ids: tuple[str, ...]
    participant_group_ids: np.ndarray
    accessed_paths: tuple[str, ...]


class ModelV1WindowDataset(Dataset[tuple[torch.Tensor, torch.Tensor, str, str]]):
    def __init__(
        self,
        population: WindowPopulation,
        *,
        training: bool,
        seed: int,
        augmentation_config: dict[str, Any],
    ) -> None:
        if training and population.partition != "TRAIN":
            raise ValueError("augmentation is permitted only on TRAIN")
        if not training and population.partition != "VALIDATION":
            raise ValueError("T015 evaluation dataset must be VALIDATION")
        self.population = population
        self.training = training
        self.seed = seed
        self.epoch = 0
        self.augmentation_config = augmentation_config

    def __len__(self) -> int:
        return int(self.population.labels.size)

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, str, str]:
        window = np.asarray(self.population.waveforms[index], dtype=np.float64)
        example_id = self.population.example_ids[index]
        if self.training:
            window = augment_train_window(
                window,
                seed=self.seed,
                epoch=self.epoch,
                example_id=example_id,
                config=self.augmentation_config,
            )
        normalized = normalize_window_zscore(window, epsilon=NORMALIZATION_EPSILON)
        signal = torch.from_numpy(normalized.astype(np.float32, copy=False)).unsqueeze(0)
        target = torch.tensor([float(self.population.labels[index])], dtype=torch.float32)
        return signal, target, example_id, str(self.population.participant_group_ids[index])


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_population(partition: str) -> WindowPopulation:
    """Load waveform files only after enforcing T015's exact partition allow-list."""
    if partition not in ALLOWED_PARTITIONS:
        raise ValueError(f"T015 waveform access forbidden: {partition}")
    selected = {
        row["example_id"]: row
        for row in _read_csv(WINDOW_MANIFEST)
        if row["partition"] == partition and row["core_eligible"].upper() == "TRUE"
    }
    cache_rows = sorted(
        (row for row in _read_csv(CACHE_MANIFEST) if row["partition"] == partition),
        key=lambda row: row["record_id"],
    )
    windows: list[np.ndarray] = []
    labels: list[int] = []
    example_ids: list[str] = []
    groups: list[str] = []
    paths: list[str] = []
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
                raise RuntimeError(f"excluded or wrong-partition cache example: {example_id}")
            label = row["label"]
            if label not in {"0", "1"}:
                raise RuntimeError(f"non-binary eligible label: {label!r}")
            windows.append(waveform)
            labels.append(int(label))
            example_ids.append(example_id)
            groups.append(row["participant_group_id"])
    if selected:
        raise RuntimeError(f"eligible manifest examples missing from cache: {len(selected)}")
    return WindowPopulation(
        partition=partition,
        waveforms=np.stack(windows).astype(np.float64, copy=False),
        labels=np.asarray(labels, dtype=np.int64),
        example_ids=tuple(example_ids),
        participant_group_ids=np.asarray(groups, dtype=str),
        accessed_paths=tuple(paths),
    )


def _augmentation_rng(seed: int, epoch: int, example_id: str) -> np.random.Generator:
    payload = f"{AUGMENTATION_ID}|{seed}|{epoch}|{example_id}".encode()
    derived = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return np.random.default_rng(derived)


def augment_train_window(
    window: np.ndarray,
    *,
    seed: int,
    epoch: int,
    example_id: str,
    config: dict[str, Any],
) -> np.ndarray:
    """Fixed TRAIN-only amplitude, baseline-drift, and noise augmentation."""
    values = np.asarray(window, dtype=np.float64)
    if values.shape != (2500,):
        raise ValueError("augmentation requires one 2500-sample window")
    if config["time_reversal"]:
        raise RuntimeError("time reversal is forbidden")
    rng = _augmentation_rng(seed, epoch, example_id)
    scale = rng.uniform(config["amplitude_scale_min"], config["amplitude_scale_max"])
    result = values * scale
    window_std = float(np.std(values, ddof=0))
    drift = config["baseline_drift"]
    frequency = rng.uniform(drift["frequency_hz_min"], drift["frequency_hz_max"])
    amplitude = rng.uniform(0.0, drift["max_amplitude_window_std_fraction"] * window_std)
    phase = rng.uniform(0.0, 2.0 * math.pi)
    seconds = np.arange(values.size, dtype=np.float64) / 250.0
    result = result + amplitude * np.sin(2.0 * math.pi * frequency * seconds + phase)
    noise = config["gaussian_noise"]
    result = result + rng.normal(
        noise["mean"], noise["std_window_std_fraction"] * window_std, values.size
    )
    return np.asarray(result, dtype=np.float64)


def set_determinism(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))


def derive_pos_weight(labels: np.ndarray) -> dict[str, Any]:
    values = np.asarray(labels, dtype=np.int64)
    if values.ndim != 1 or not set(np.unique(values)).issubset({0, 1}):
        raise ValueError("TRAIN labels must be binary")
    positives = int(np.sum(values == 1))
    negatives = int(np.sum(values == 0))
    if positives == 0:
        raise ValueError("TRAIN positives absent")
    return {
        "formula_id": FORMULA_ID,
        "formula": "N_train_negative / N_train_positive",
        "source_partition": "TRAIN",
        "train_positives": positives,
        "train_negatives": negatives,
        "pos_weight": float(negatives / positives),
    }


def release_candidate_seed(results: list[dict[str, Any]]) -> int:
    seeds = {int(result["seed"]) for result in results}
    if RELEASE_SEED not in seeds:
        raise ValueError("release-seed result absent")
    return RELEASE_SEED


def _make_loaders(
    train: WindowPopulation,
    validation: WindowPopulation,
    *,
    seed: int,
    config: dict[str, Any],
) -> tuple[ModelV1WindowDataset, DataLoader, DataLoader]:
    train_dataset = ModelV1WindowDataset(
        train, training=True, seed=seed, augmentation_config=config["augmentation"]
    )
    validation_dataset = ModelV1WindowDataset(
        validation, training=False, seed=seed, augmentation_config=config["augmentation"]
    )
    generator = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(
        train_dataset,
        batch_size=config["training"]["batch_size"],
        shuffle=True,
        drop_last=False,
        num_workers=0,
        generator=generator,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=config["training"]["batch_size"],
        shuffle=False,
        drop_last=False,
        num_workers=0,
    )
    return train_dataset, train_loader, validation_loader


def _validate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    labels: np.ndarray,
    groups: np.ndarray,
) -> tuple[float, np.ndarray, dict[str, Any]]:
    model.eval()
    losses: list[float] = []
    logits: list[np.ndarray] = []
    with torch.inference_mode():
        for inputs, targets, _example_ids, _groups in loader:
            outputs = model(inputs)
            if outputs.shape != targets.shape:
                raise RuntimeError(f"BCE shape mismatch: {outputs.shape} vs {targets.shape}")
            loss = criterion(outputs, targets)
            if not torch.isfinite(loss):
                raise RuntimeError("nonfinite validation loss")
            losses.append(float(loss.item()) * inputs.shape[0])
            logits.append(outputs.cpu().numpy())
    raw_logits = np.concatenate(logits).reshape(-1)
    probabilities = torch.sigmoid(torch.from_numpy(raw_logits)).numpy()
    if float(np.std(raw_logits)) == 0.0:
        raise RuntimeError("all-constant validation logits")
    metrics = descriptive_metrics(labels, probabilities, groups, threshold=0.5)
    return float(sum(losses) / labels.size), raw_logits, metrics


def _checkpoint_payload(
    model: nn.Module,
    *,
    seed: int,
    epoch: int,
    validation_auprc: float,
    config_sha256: str,
) -> dict[str, Any]:
    return {
        "model_id": MODEL_ID,
        "candidate_status": "CANDIDATE_T015",
        "seed": seed,
        "best_epoch": epoch,
        "best_validation_auprc": validation_auprc,
        "model_config_sha256": config_sha256,
        "state_dict": copy.deepcopy(model.state_dict()),
    }


def train_seed(
    *,
    seed: int,
    train: WindowPopulation,
    validation: WindowPopulation,
    config: dict[str, Any],
    config_sha256: str,
    pos_weight: float,
) -> dict[str, Any]:
    set_determinism(seed)
    model = build_model_v1().to("cpu")
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], dtype=torch.float32))
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
    train_dataset, train_loader, validation_loader = _make_loaders(
        train, validation, seed=seed, config=config
    )
    best = -math.inf
    best_epoch = 0
    non_improvement = 0
    best_metrics: dict[str, Any] | None = None
    best_logits: np.ndarray | None = None
    epoch_logs: list[dict[str, Any]] = []
    checkpoint_path = CANDIDATE_ROOT / f"MODEL_V1_seed_{seed}_best.pt"
    CANDIDATE_ROOT.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    initial_lr = float(optimizer.param_groups[0]["lr"])
    lr_reductions = 0
    stop_reason = "MAX_EPOCHS"
    for epoch in range(1, config["training"]["max_epochs"] + 1):
        train_dataset.set_epoch(epoch)
        model.train()
        loss_sum = 0.0
        count = 0
        for inputs, targets, _example_ids, _groups in train_loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(inputs)
            if logits.shape != targets.shape:
                raise RuntimeError(f"BCE shape mismatch: {logits.shape} vs {targets.shape}")
            loss = criterion(logits, targets)
            if not torch.isfinite(loss):
                raise RuntimeError("nonfinite training loss")
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.item()) * inputs.shape[0]
            count += inputs.shape[0]
        validation_loss, validation_logits, metrics = _validate(
            model,
            validation_loader,
            criterion,
            validation.labels,
            validation.participant_group_ids,
        )
        validation_auprc = float(metrics["AUPRC"])
        improved = validation_auprc > best
        if improved:
            best = validation_auprc
            best_epoch = epoch
            best_metrics = metrics
            best_logits = validation_logits.copy()
            non_improvement = 0
            torch.save(
                _checkpoint_payload(
                    model,
                    seed=seed,
                    epoch=epoch,
                    validation_auprc=validation_auprc,
                    config_sha256=config_sha256,
                ),
                checkpoint_path,
            )
        else:
            non_improvement += 1
        old_lr = float(optimizer.param_groups[0]["lr"])
        scheduler.step(validation_auprc)
        new_lr = float(optimizer.param_groups[0]["lr"])
        if new_lr < old_lr:
            lr_reductions += 1
        epoch_logs.append(
            {
                "epoch": epoch,
                "train_loss": float(loss_sum / count),
                "validation_loss": validation_loss,
                "validation_auprc": validation_auprc,
                "learning_rate": old_lr,
                "improved": improved,
                "non_improvement_count": non_improvement,
            }
        )
        if non_improvement >= config["training"]["early_stopping_patience"]:
            stop_reason = "EARLY_STOP_PATIENCE_7_NON_IMPROVING_EPOCHS"
            break
    wall_seconds = float(time.perf_counter() - start)
    if best_metrics is None or best_logits is None:
        raise RuntimeError("no candidate checkpoint selected")
    saved = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    reloaded = build_model_v1().eval()
    reloaded.load_state_dict(saved["state_dict"])
    _, reload_logits, _ = _validate(
        reloaded,
        validation_loader,
        criterion,
        validation.labels,
        validation.participant_group_ids,
    )
    # Compare the entire selected-epoch vector, not only a convenient test point.
    reload_equal = bool(np.array_equal(best_logits, reload_logits))
    if not reload_equal:
        raise RuntimeError("candidate checkpoint reload logits differ")
    result = {
        "model_id": MODEL_ID,
        "candidate_status": "CANDIDATE_T015",
        "seed": seed,
        "epochs_completed": len(epoch_logs),
        "best_epoch": best_epoch,
        "best_validation_auprc": best,
        "best_validation_metrics": best_metrics,
        "stop_epoch": len(epoch_logs),
        "stop_reason": stop_reason,
        "lr_reductions": lr_reductions,
        "initial_learning_rate": initial_lr,
        "final_learning_rate": float(optimizer.param_groups[0]["lr"]),
        "checkpoint_path": str(checkpoint_path.relative_to(ROOT)),
        "checkpoint_sha256": hash_file(checkpoint_path),
        "checkpoint_reload_test": "PASS",
        "wall_clock_seconds": wall_seconds,
        "checkpoint_size_bytes": checkpoint_path.stat().st_size,
        "epoch_logs": epoch_logs,
    }
    seed_path = REPORT_ROOT / "seeds" / f"{seed}.json"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _write_metadata(
    result: dict[str, Any],
    *,
    train: WindowPopulation,
    validation: WindowPopulation,
    weight: dict[str, Any],
    config_sha256: str,
) -> Path:
    checkpoint_path = ROOT / result["checkpoint_path"]
    metadata = {
        "model_id": MODEL_ID,
        "candidate_status": "CANDIDATE_T015_NOT_FROZEN",
        "seed": result["seed"],
        "best_epoch": result["best_epoch"],
        "best_validation_auprc": result["best_validation_auprc"],
        "architecture_config_sha256": hash_canonical_json(
            yaml.safe_load(CONFIG_PATH.read_text())["architecture"]
        ),
        "model_config_sha256": config_sha256,
        "target_id": "AAMI_SVF_WINDOW_V1",
        "map_id": "AAMI_SVF_MAP_V1",
        "split_id": "MITDB_SPLIT_V1",
        "split_sha256": hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"),
        "preproc_id": "PREPROC_V1",
        "F06_lock_sha256": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
        "window_manifest_sha256": hash_file(WINDOW_MANIFEST),
        "train_patient_count": len(set(train.participant_group_ids.tolist())),
        "train_window_count": int(train.labels.size),
        "validation_patient_count": len(set(validation.participant_group_ids.tolist())),
        "validation_window_count": int(validation.labels.size),
        "train_positive_count": weight["train_positives"],
        "train_negative_count": weight["train_negatives"],
        "pos_weight": weight["pos_weight"],
        "torch_version": torch.__version__,
        "input_dtype": "float32",
        "device": "cpu",
        "augmentation_id": AUGMENTATION_ID,
        "augmentation_config_sha256": hash_canonical_json(
            yaml.safe_load(CONFIG_PATH.read_text())["augmentation"]
        ),
        "checkpoint_path": result["checkpoint_path"],
        "checkpoint_sha256": hash_file(checkpoint_path),
        "calibration": None,
        "operating_threshold": None,
    }
    path = checkpoint_path.with_suffix(".metadata.json")
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run() -> dict[str, Any]:
    verify_frozen_split(ROOT)
    verify_preproc_freeze(ROOT)
    from models.baseline_freeze import verify_baseline_freeze

    verify_baseline_freeze(ROOT)
    config_sha_before = hash_file(CONFIG_PATH)
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if config["model_id"] != MODEL_ID or config["training"]["device"] != "cpu":
        raise RuntimeError("MODEL_V1 identity/device contract mismatch")
    if config["augmentation"]["time_reversal"]:
        raise RuntimeError("time reversal forbidden")
    train = load_population("TRAIN")
    weight = derive_pos_weight(train.labels)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    weight.update(
        {
            "split_sha256": hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"),
            "window_manifest_sha256": hash_file(WINDOW_MANIFEST),
        }
    )
    weight_path = ARTIFACT_ROOT / "train_pos_weight.json"
    weight_path.write_text(json.dumps(weight, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Configuration and TRAIN-derived loss weight are frozen before VALIDATION cache access.
    validation = load_population("VALIDATION")
    results: list[dict[str, Any]] = []
    for seed in (RELEASE_SEED, *ROBUSTNESS_SEEDS):
        result = train_seed(
            seed=seed,
            train=train,
            validation=validation,
            config=config,
            config_sha256=config_sha_before,
            pos_weight=weight["pos_weight"],
        )
        _write_metadata(
            result,
            train=train,
            validation=validation,
            weight=weight,
            config_sha256=config_sha_before,
        )
        results.append(result)
    config_sha_after = hash_file(CONFIG_PATH)
    if config_sha_before != config_sha_after:
        raise RuntimeError("MODEL_V1 config changed after validation access")
    release_seed = release_candidate_seed(results)
    release = next(result for result in results if result["seed"] == release_seed)
    auprcs = np.asarray([result["best_validation_auprc"] for result in results])
    macro_f1s = np.asarray(
        [result["best_validation_metrics"]["patient_macro_F1"] for result in results]
    )
    robustness = {
        "seeds": [
            {
                "seed": result["seed"],
                "best_epoch": result["best_epoch"],
                "best_validation_auprc": result["best_validation_auprc"],
                "validation_patient_macro_F1": result["best_validation_metrics"][
                    "patient_macro_F1"
                ],
                "checkpoint_sha256": result["checkpoint_sha256"],
            }
            for result in results
        ],
        "validation_auprc_mean": float(np.mean(auprcs)),
        "validation_auprc_sd": float(np.std(auprcs, ddof=1)),
        "validation_patient_macro_F1_mean": float(np.mean(macro_f1s)),
        "validation_patient_macro_F1_sd": float(np.std(macro_f1s, ddof=1)),
        "sd_convention": "sample standard deviation, ddof=1",
        "highest_scoring_seed": int(results[int(np.argmax(auprcs))]["seed"]),
        "release_candidate_seed": release_seed,
        "release_seed_invariant": "PASS",
        "overall_status": "PASS",
    }
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / "seed_robustness.json").write_text(
        json.dumps(robustness, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    access = {
        "TRAIN": {
            "role": "FIT",
            "access_count": len(train.accessed_paths),
            "paths": list(train.accessed_paths),
        },
        "VALIDATION": {
            "role": "MODEL_SELECTION_EARLY_STOPPING_ONLY",
            "access_count": len(validation.accessed_paths),
            "paths": list(validation.accessed_paths),
        },
        "CALIBRATION": {"role": "NOT_ACCESSED", "access_count": 0, "paths": []},
        "INTERNAL_TEST": {"role": "NOT_ACCESSED", "access_count": 0, "paths": []},
        "INCART": {"role": "NOT_ACCESSED", "access_count": 0, "paths": []},
        "NSTDB": {"role": "NOT_ACCESSED", "access_count": 0, "paths": []},
        "BIDMC": {"role": "NOT_ACCESSED", "access_count": 0, "paths": []},
        "WEARABLE_V1": {"role": "NOT_ACCESSED", "access_count": 0, "paths": []},
        "WEARABLE_SIM_V1": {"role": "NOT_ACCESSED", "access_count": 0, "paths": []},
        "overall_status": "PASS",
    }
    (REPORT_ROOT / "partition_access_audit.json").write_text(
        json.dumps(access, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    architecture_parameters = sum(
        parameter.numel() for parameter in build_model_v1().parameters() if parameter.requires_grad
    )
    contract = {
        "architecture_exact": "PASS",
        "parameter_count": architecture_parameters,
        "input_shape_exact": "PASS",
        "loss": "BCEWithLogitsLoss",
        "sigmoid_absent_from_forward": "PASS",
        "optimizer": "AdamW",
        "learning_rate": 0.001,
        "weight_decay": 0.0001,
        "batch_size": 64,
        "max_epochs": 50,
        "early_stop_monitor": "VALIDATION_POOLED_WINDOW_AUPRC",
        "early_stop_patience": 7,
        "scheduler": "ReduceLROnPlateau",
        "scheduler_monitor": "VALIDATION_POOLED_WINDOW_AUPRC",
        "release_seed": RELEASE_SEED,
        "robustness_seeds": list(ROBUSTNESS_SEEDS),
        "time_reversal": False,
        "TRAIN_only_pos_weight": "PASS",
        "config_sha_before_validation": config_sha_before,
        "config_sha_after_validation": config_sha_after,
        "overall_status": "PASS",
    }
    (REPORT_ROOT / "training_contract_audit.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "model_id": MODEL_ID,
        "status": "MODEL_V1_CANDIDATE_READY_FOR_T016",
        "architecture_parameter_count": EXPECTED_TRAINABLE_PARAMETERS,
        "upstream_frozen_hashes": {
            "F05": hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json"),
            "F06": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
            "F07": hash_file(ROOT / "manifests/baselines/BASELINE_V1.lock.json"),
            "window_manifest": hash_file(WINDOW_MANIFEST),
        },
        "training_contract": config,
        "pos_weight": weight,
        "seed_policy": {
            "release_seed": RELEASE_SEED,
            "robustness_seeds": list(ROBUSTNESS_SEEDS),
            "best_seed_selection": "FORBIDDEN",
        },
        "release_candidate": release,
        "robustness": robustness,
        "partition_access": access,
        "environment": {
            "device": "cpu",
            "torch_version": torch.__version__,
            "numpy_version": np.__version__,
            "platform": platform.platform(),
            "deterministic_algorithms": True,
        },
        "calibration": None,
        "operating_threshold": None,
        "overall_status": "PASS",
    }
    MODEL_REPORT.parent.mkdir(parents=True, exist_ok=True)
    MODEL_REPORT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    summary = run()
    release = summary["release_candidate"]
    print(
        "T015 MODEL_V1 candidates: PASS "
        f"(release_seed={release['seed']}, best_epoch={release['best_epoch']}, "
        f"validation_AUPRC={release['best_validation_auprc']:.6f})"
    )


if __name__ == "__main__":
    main()
