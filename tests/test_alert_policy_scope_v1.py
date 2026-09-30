from __future__ import annotations

import ast
import inspect
from pathlib import Path

import yaml

import fusion.episode_manager as episode_manager
import fusion.state_machine as state_machine
from fusion.episode_manager import load_alert_policy
from fusion.state_machine import FIXTURE_STATE_POLICY_ID, MONITORING_STATES

ROOT = Path(__file__).resolve().parents[1]


def test_t005_mock_policy_remains_distinct() -> None:
    assert FIXTURE_STATE_POLICY_ID == "FIXTURE_STATE_POLICY_V0"
    assert load_alert_policy().policy_id != FIXTURE_STATE_POLICY_ID


def test_monitoring_vocabulary_is_exact_and_warning_is_metadata_only() -> None:
    policy = yaml.safe_load((ROOT / "configs/alert_policy_v1.yaml").read_text())
    assert set(policy["monitoring_state_vocabulary"]) == MONITORING_STATES
    assert "QUALITY_WARNING" not in MONITORING_STATES
    assert policy["rate_consistency"]["top_level_state"] is False


def test_policy_values_and_anti_circularity_are_frozen() -> None:
    config = yaml.safe_load((ROOT / "configs/alert_policy_v1.yaml").read_text())
    assert config["open"]["required_consecutive_valid_above"] == 2
    assert config["close"]["required_consecutive_valid_below"] == 2
    assert config["cooldown_seconds"] == 30
    assert config["threshold"]["comparator"] == ">="
    assert config["rate_consistency"]["tolerance_bpm"] == 20.0
    assert config["rate_consistency"]["continuous_duration_seconds"] == 10.0
    assert config["rate_consistency"]["selected_before_bidmc_v2"] is True
    assert config["rate_consistency"]["selected_from_outcome_data"] is False


def test_production_fusion_has_no_forbidden_imports_or_truth() -> None:
    forbidden_prefixes = ("training", "datasets", "simulation", "models")
    for module in (state_machine, episode_manager):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert "SimulationTruth" not in names
        imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not any(name.startswith(forbidden_prefixes) for name in imports)


def test_no_learned_fusion_or_probability_modification() -> None:
    source = inspect.getsource(episode_manager) + inspect.getsource(state_machine)
    for forbidden in (
        "optimizer",
        "fit(",
        "adjusted_probability",
        "quality_factor",
        "predict_proba",
    ):
        assert forbidden not in source


def test_ecg_hr_v2_binding_is_exact() -> None:
    config = yaml.safe_load((ROOT / "configs/alert_policy_v1.yaml").read_text())
    assert config["ecg_hr_context"] == {
        "id": "ECG_HR_CONTEXT_V2",
        "lock_sha256": "8ea6203c5a32b9cd951e7cb7dfcd133ca0f7c2ef7441d04cda8c15e72faec6ca",
    }
