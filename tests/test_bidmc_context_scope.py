from __future__ import annotations

import ast
import json
from pathlib import Path

from evaluation.bidmc_context import validate_config

ROOT = Path(__file__).resolve().parents[1]


def test_context_scope_has_no_model_labels_training_or_fusion() -> None:
    source = (ROOT / "evaluation/bidmc_context.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(name.startswith(("models", "training", "fusion")) for name in imports)
    forbidden_calls = {"resample", "resample_poly", "filtfilt", "sosfiltfilt"}
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (called & forbidden_calls)
    config = validate_config()
    assert config["scope"]["aami_svf_labels"] is False
    assert config["scope"]["model_v1_inference"] is False
    assert config["scope"]["learned_fusion"] is False


def test_bidmc19_spo2_source_anomaly_is_frozen() -> None:
    validation = json.loads((ROOT / "reports/t007/bidmc_validation.json").read_text())
    assert validation["spo2_availability"]["records_missing_spo2"] == ["bidmc19"]


def test_f06_does_not_contain_context_resamplers() -> None:
    lock = (ROOT / "manifests/preprocessing/PREPROC_V1.lock.json").read_text()
    assert "BIDMC_PPG_125_TO_100_V1" not in lock
    assert "BIDMC_ECG_HR_125_TO_250_V1" not in lock
