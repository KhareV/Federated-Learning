from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_fedprox_scope_and_f12_immutability_contract() -> None:
    config = yaml.safe_load((ROOT / "configs/fedprox_v1.yaml").read_text())
    assert config["mu_candidates"] == [0.001, 0.01, 0.1]
    assert config["candidate_tuning_condition"] == "FL_LABEL_SKEW_V1"
    assert config["shuffle_seed_namespace"] == "FL_IID_V1"
    assert config["secure_aggregation"] is False
    assert config["differential_privacy"] is False
    assert config["access"]["INTERNAL_TEST"] == "FORBIDDEN"
    assert config["access"]["CALIBRATION"] == "FORBIDDEN"


def test_no_frozen_fedavg_source_edited_by_t027_imports() -> None:
    source = (ROOT / "federated/fedprox_runner.py").read_text()
    assert 'load_population("INTERNAL_TEST")' not in source
    assert "CAL_V1" not in source
    assert "SecAgg" not in source
