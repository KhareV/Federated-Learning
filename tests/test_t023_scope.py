from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_no_aami_labels_training_or_learned_fusion() -> None:
    source = (ROOT / "evaluation/quality_aware_alerts.py").read_text()
    tree = ast.parse(source)
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]
    assert not any("training" in name or "label" in name for name in imports)
    config = yaml.safe_load((ROOT / "configs/quality_aware_experiment_v1.yaml").read_text())
    assert config["scope"]["aami_labels"] is False
    assert config["scope"]["learned_fusion"] is False
    assert config["scope"]["wearable_v1_access"] is False
    assert config["scope"]["hardware_required"] is False


def test_method_lock_binds_all_frozen_inputs() -> None:
    lock = json.loads((ROOT / "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json").read_text())
    assert lock["status"] == "FROZEN_EXPERIMENT_METHOD"
    for identity in (
        "MODEL_V1",
        "CAL_V1",
        "QUALITY_V1",
        "ECG_HR_CONTEXT_V2",
        "BIDMC_CONTEXT_V2",
        "ALERT_POLICY_V1",
    ):
        assert identity in lock["hashes"]


def test_production_path_does_not_import_simulation_truth() -> None:
    for relative in (
        "evaluation/quality_aware_alerts.py",
        "fusion/state_machine.py",
        "fusion/episode_manager.py",
    ):
        tree = ast.parse((ROOT / relative).read_text())
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert "SimulationTruth" not in imports


def test_policy_sensitivity_predeclares_context_invariance() -> None:
    audit = json.loads((ROOT / "reports/t023/policy_sensitivity_audit.json").read_text())
    assert audit["PPG_quality"]["episode_count"] is False
    assert audit["SpO2_validity"]["episode_count"] is False
    assert audit["ECG_PPG_disagreement"]["episode_count"] is False
    assert audit["PRIMARY_EPISODE_CONTEXT_INVARIANCE_EXPECTED"] is True
