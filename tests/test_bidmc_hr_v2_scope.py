from __future__ import annotations

import ast
from pathlib import Path

import yaml

from evaluation.bidmc_context_v2 import INHERITED_FIELDS

ROOT = Path(__file__).resolve().parents[1]


def test_evaluator_has_no_model_or_aami_path() -> None:
    source = (ROOT / "evaluation/bidmc_context_v2.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any("model" in name or "training" in name for name in imports)
    assert not any("aami" in name for name in imports)


def test_reference_is_not_an_estimator_argument() -> None:
    source = (ROOT / "evaluation/bidmc_context_v2.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "estimate_hr"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) == 1
    assert {keyword.arg for keyword in call.keywords} == {"timestamp_us", "candidate_id"}


def test_protocol_forbids_time_shift_tuning_and_perturbations() -> None:
    config = yaml.safe_load((ROOT / "configs/bidmc_context_v2.yaml").read_text())
    assert config["alignment"]["time_shift_optimization"] is False
    assert config["reference"]["detector_access"] is False
    assert config["scope"]["tuning"] is False
    assert config["scope"]["controlled_perturbations"] is False
    assert config["scope"]["model_v1_inference"] is False


def test_only_ecg_hr_dependent_fields_are_new() -> None:
    expected = {
        "record_id",
        "timestamp_us",
        "ppg_quality",
        "ppg_context_available",
        "pr_ppg_bpm",
        "provided_pulse_bpm",
        "pulse_reference_valid",
        "provided_hr_bpm",
        "hr_reference_valid",
        "spo2_pct",
        "spo2_valid",
        "spo2_provenance",
        "short_gap_present",
        "long_gap_present",
    }
    assert set(INHERITED_FIELDS) == expected


def test_policy_and_estimator_are_hash_bound_before_results() -> None:
    config = yaml.safe_load((ROOT / "configs/bidmc_context_v2.yaml").read_text())
    assert config["policy_binding"]["alert_policy_id"] == "ALERT_POLICY_V1"
    assert len(config["policy_binding"]["alert_policy_lock_sha256"]) == 64
    assert config["changed_component"]["replacement"] == "ECG_HR_CONTEXT_V2"
