from __future__ import annotations

import ast
from pathlib import Path

from evaluation.noise import curve_svg

ROOT = Path(__file__).resolve().parents[1]


def test_production_path_has_no_training_or_tuning() -> None:
    source = (ROOT / "evaluation/noise.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "train" not in attributes
    assert "backward" not in attributes
    assert "step" not in attributes
    assert "fit_temperature" not in names
    assert "select_f1_threshold" not in names
    assert "load_internal_population" not in names
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any("incart" in module.casefold() for module in imported_modules)


def test_curve_reports_delta_against_24_not_clean() -> None:
    pooled = []
    by_record = []
    for snr, value in zip((24, 18, 12, 6, 0, -6), (0.9, 0.8, 0.7, 0.6, 0.5, 0.4), strict=True):
        pooled.append({"snr_db": snr, "AUPRC": value})
        by_record.extend(
            [
                {"base_record_id": "118", "snr_db": snr, "AUPRC": value},
                {"base_record_id": "119", "snr_db": snr, "AUPRC": value / 2},
            ]
        )
    svg = curve_svg(pooled, by_record)
    assert "highest-SNR reference is not clean" in svg
    assert "smooth" not in svg.casefold()


def test_pure_noise_policy_is_frozen_in_config() -> None:
    config = (ROOT / "configs/noise_robustness_v1.yaml").read_text(encoding="utf-8")
    assert "predictive_labels: FORBIDDEN" in config
    assert "classification_metrics: FORBIDDEN" in config
    assert "reference_semantics: HIGHEST_SNR_OFFICIAL_NSTDB_STRESS_CONDITION_NOT_CLEAN" in config


def test_quality_and_primary_population_are_separate_in_config() -> None:
    config = (ROOT / "configs/noise_robustness_v1.yaml").read_text(encoding="utf-8")
    assert "OFFLINE_MODEL_STRESS_ONLY" in config
    assert "runtime_quality_gate_applied_to_primary_curve: false" in config
