from __future__ import annotations

import ast
from pathlib import Path

import pytest

from evaluation.ecg_hr_v2 import records_for_partition, validate_config

ROOT = Path(__file__).resolve().parents[1]


def test_only_train_validation_partitions_are_accepted() -> None:
    for forbidden in ("CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"):
        with pytest.raises(ValueError, match="SCOPE_VIOLATION"):
            records_for_partition(forbidden)


def test_production_candidate_code_has_no_reference_or_simulation_truth() -> None:
    source = (ROOT / "preprocessing/ecg_hr_context.py").read_text(encoding="utf-8")
    assert "reference_hr" not in source
    assert "SimulationTruth" not in source
    tree = ast.parse(source)
    imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(name.startswith(("datasets.bidmc", "models", "training")) for name in imports)


def test_t021_and_f06_files_are_not_implementation_targets() -> None:
    source = (ROOT / "evaluation/ecg_hr_v2.py").read_text(encoding="utf-8")
    for forbidden in (
        "reports/t021",
        "reports/bidmc_multimodal_engineering",
        "configs/bidmc_context_v1.yaml",
        "data/raw/bidmc",
    ):
        assert forbidden not in source


def test_frozen_method_config_has_required_scope_and_anti_circularity() -> None:
    config = validate_config()
    assert config["selection"]["primary_metric"] == "patient_macro_MAE"
    assert config["selection"]["engineering_quality_floor"] == {
        "pooled_coverage_min": 0.95,
        "patient_macro_MAE_bpm_max": 10.0,
        "pooled_median_absolute_error_bpm_max": 5.0,
        "pooled_p95_absolute_error_bpm_max": 20.0,
    }
    assert config["scope"]["alert_policy_id"] is None
    assert config["scope"]["hr_disagreement_tolerance_bpm"] is None
    assert config["scope"]["bidmc_context_v2_created"] is False
