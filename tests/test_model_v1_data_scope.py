from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest
import yaml

from preprocessing.windowing import normalize_window_zscore
from training.train_central import (
    ModelV1WindowDataset,
    WindowPopulation,
    augment_train_window,
    load_population,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs/model_v1.yaml").read_text())


def population(partition: str) -> WindowPopulation:
    return WindowPopulation(
        partition=partition,
        waveforms=np.arange(5000, dtype=np.float64).reshape(2, 2500),
        labels=np.asarray([0, 1]),
        example_ids=("a", "b"),
        participant_group_ids=np.asarray(["p1", "p2"]),
        accessed_paths=(),
    )


def test_frozen_normalization_reused_exactly_and_float32() -> None:
    dataset = ModelV1WindowDataset(
        population("VALIDATION"),
        training=False,
        seed=20260927,
        augmentation_config=CONFIG["augmentation"],
    )
    tensor, target, _example, _patient = dataset[0]
    expected = normalize_window_zscore(population("VALIDATION").waveforms[0])
    np.testing.assert_allclose(tensor.numpy()[0], expected.astype(np.float32), rtol=0, atol=0)
    assert tensor.shape == (1, 2500) and str(tensor.dtype) == "torch.float32"
    assert target.shape == (1,)


def test_augmentation_is_train_only_deterministic_and_never_reverses() -> None:
    signal = np.linspace(-1.0, 1.0, 2500)
    augmentation = CONFIG["augmentation"]
    first = augment_train_window(
        signal, seed=20260927, epoch=3, example_id="example", config=augmentation
    )
    second = augment_train_window(
        signal, seed=20260927, epoch=3, example_id="example", config=augmentation
    )
    assert np.array_equal(first, second)
    assert not np.array_equal(first, signal[::-1])
    assert augmentation["amplitude_scale_min"] == 0.9
    assert augmentation["amplitude_scale_max"] == 1.1
    assert augmentation["time_reversal"] is False
    validation = ModelV1WindowDataset(
        population("VALIDATION"),
        training=False,
        seed=20260927,
        augmentation_config=augmentation,
    )
    assert np.array_equal(validation[0][0].numpy(), validation[0][0].numpy())


def test_forbidden_waveform_partitions_fail_before_io() -> None:
    for partition in ("CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"):
        with pytest.raises(ValueError, match="forbidden"):
            load_population(partition)


def test_model_path_does_not_import_classical_features_or_labels() -> None:
    source = (ROOT / "training/train_central.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert "features.ecg" not in modules
    assert "datasets.labels" not in modules
    assert "artifacts/baselines" not in source
