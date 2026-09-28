from pathlib import Path

import yaml

from nhm.config import load_yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/WEARABLE_SIM_V1.md"
SIM_CONFIG = ROOT / "configs/simulation/WEARABLE_SIM_V1.yaml"


def _text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _normalized_text() -> str:
    """Whitespace-normalized text for phrase checks that may be markdown-wrapped."""
    return " ".join(_text().split())


def test_wearable_sim_v1_is_distinct_from_wearable_v1() -> None:
    text = _text()
    assert "WEARABLE_SIM_V1" in text
    assert "WEARABLE_V1" in text
    assert "does **not** replace, alias, or redefine" in text
    assert "reserved exclusively for future real hardware/domain sessions" in text


def test_simulator_modes_are_documented() -> None:
    text = _text()
    for mode in (
        "SYNTHETIC_PHYSIOLOGY",
        "MITDB_REPLAY",
        "BIDMC_REPLAY",
        "FAULT_INJECTION",
        "LONGITUDINAL_COHORT",
        "LIVE_SPEED_REPLAY",
        "ACCELERATED_REPLAY",
    ):
        assert mode in text


def test_synthetic_provenance_marking_is_required() -> None:
    text = _text()
    assert "dataset_id = WEARABLE_SIM_V1" in text
    assert "SYNTHETIC_*" in text or "SYNTHETIC_" in text
    assert "simulation_version" in text
    assert "simulation_seed" in text
    assert "never" in text.casefold()
    assert "actual human volunteers" in _normalized_text()


def test_claim_boundary_prohibits_clinical_evidence_uses() -> None:
    text = _text().casefold()
    for prohibited in (
        "clinical accuracy",
        "real wearable sensitivity",
        "real wearable specificity",
        "clinical prevalence",
        "medical efficacy",
        "real sensor calibration",
        "real device-domain validation",
    ):
        assert prohibited in text


def test_truth_channel_is_isolated_from_production() -> None:
    text = _text()
    assert "ObservedRecord" in text
    assert "SimulationTruth" in text
    assert "must never read, import, or otherwise depend on `SimulationTruth`" in text


def test_primary_model_evidence_boundary_is_explicit() -> None:
    text = _text()
    assert "MIT-BIH" in text
    assert "INCART" in text
    assert "never replaces that evidence, at any stage" in text


def test_primary_federated_learning_boundary_is_explicit() -> None:
    text = _text()
    assert "eight simulated research sites" in text
    assert "whole real MIT-BIH training patients" in text
    assert "never substituted into that experiment" in text


def test_deterministic_seed_policy_is_required() -> None:
    text = _text()
    assert "deterministic" in text.casefold()
    assert "simulation_seed" in text
    assert "No global untracked random state." in text


def test_virtual_participant_namespace_is_documented() -> None:
    text = _text()
    assert "SIM_P000001" in text
    assert "SIM_P000002" in text


def test_layered_architecture_is_documented() -> None:
    text = _text()
    assert "Layer A" in text
    assert "Layer B" in text
    assert "Layer C" in text


def test_dataset_size_profiles_are_named_without_hardcoded_counts() -> None:
    text = _text()
    for profile in (
        "WEARABLE_SIM_SMOKE",
        "WEARABLE_SIM_DEV",
        "WEARABLE_SIM_FULL",
        "WEARABLE_SIM_STRESS",
    ):
        assert profile in text


def test_simulation_config_skeleton_loads_and_matches_contract() -> None:
    config = load_yaml(SIM_CONFIG)
    assert config["simulation"]["simulation_id"] == "WEARABLE_SIM_V1"
    assert config["simulation"]["distinct_from"] == "WEARABLE_V1"
    assert config["truth_channel_policy"]["production_may_consume_truth_stream"] is False
    assert config["claim_boundary"]["clinical_validation_claim_allowed"] is False
    assert config["claim_boundary"]["synthetic_participants_are_real_humans"] is False
    assert set(config["supported_modes"]) == {
        "SYNTHETIC_PHYSIOLOGY",
        "MITDB_REPLAY",
        "BIDMC_REPLAY",
        "FAULT_INJECTION",
        "LONGITUDINAL_COHORT",
        "LIVE_SPEED_REPLAY",
        "ACCELERATED_REPLAY",
    }


def test_simulation_config_is_valid_yaml_mapping() -> None:
    with SIM_CONFIG.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    assert isinstance(raw, dict)
