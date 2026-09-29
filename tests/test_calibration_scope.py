from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

import numpy as np
import yaml

from evaluation.calibration import fit_from_partitioned_arrays

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs/calibration_v1.yaml").read_text())


def test_non_calibration_rows_cannot_change_temperature_or_threshold() -> None:
    partitions = np.asarray(
        ["TRAIN", "VALIDATION", "CALIBRATION", "CALIBRATION", "INTERNAL_TEST"]
    )
    logits = np.asarray([-100.0, 100.0, -1.0, 1.0, 500.0])
    labels = np.asarray([1, 0, 0, 1, 0])
    first = fit_from_partitioned_arrays(partitions, logits, labels, CONFIG)
    logits[[0, 1, 4]] = [1000.0, -1000.0, -999.0]
    labels[[0, 1, 4]] = [0, 1, 1]
    second = fit_from_partitioned_arrays(partitions, logits, labels, CONFIG)
    assert first == second


def test_access_ledger_contains_only_calibration_paths() -> None:
    audit = json.loads((ROOT / "reports/t017/partition_access_audit.json").read_text())
    assert audit["CALIBRATION"]["waveform_cache_reads"] > 0
    assert all("/CALIBRATION/" in path for path in audit["CALIBRATION"]["paths"])
    for partition in ("TRAIN", "VALIDATION", "INTERNAL_TEST"):
        assert audit[partition]["waveform_cache_reads"] == 0
        assert audit[partition]["paths"] == []
    for dataset in ("INCART", "NSTDB", "BIDMC", "WEARABLE"):
        assert audit[dataset]["reads"] == 0


def test_method_config_was_unchanged_through_fit() -> None:
    audit = json.loads((ROOT / "reports/t017/calibration_audit.json").read_text())
    assert audit["method_config_unchanged"] is True
    assert audit["method_config_sha_before"] == audit["method_config_sha_after"]


def test_prediction_population_exactly_closes_against_eligible_calibration_rows() -> None:
    with (ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv").open(newline="") as handle:
        expected_rows = [
            row
            for row in csv.DictReader(handle)
            if row["partition"] == "CALIBRATION" and row["core_eligible"] == "TRUE"
        ]
    with (ROOT / "reports/calibration/calibration_predictions.csv").open(newline="") as handle:
        actual_rows = list(csv.DictReader(handle))
    assert {row["example_id"] for row in actual_rows} == {
        row["example_id"] for row in expected_rows
    }
    assert {row["participant_group_id"] for row in actual_rows} == {
        row["participant_group_id"] for row in expected_rows
    }
    assert all(row["label"] in {"0", "1"} for row in actual_rows)


def test_calibration_path_has_no_model_training_operations() -> None:
    source = (ROOT / "evaluation/calibration.py").read_text()
    ast.parse(source)
    for forbidden in (
        "optimizer.step",
        ".backward(",
        "model.train(",
        "training.train_central",
        "checkpoints/candidates",
    ):
        assert forbidden not in source
