"""Focused T028 Flower SecAgg+ correctness and scope tests."""

from __future__ import annotations

from pathlib import Path

import flwr
import numpy as np
import pytest
import yaml
from flwr.client.mod import secaggplus_mod
from flwr.server.workflow import SecAggPlusWorkflow

from privacy.accounting import ACCOUNTING_ID
from privacy.secagg_app import ClientPayload, run_flower_secaggplus, run_plain_reference
from privacy.server_visibility import ServerVisibilityProbe, require_visibility_contract

ROOT = Path(__file__).resolve().parents[1]


def fixture() -> tuple[list[ClientPayload], list[np.ndarray]]:
    payloads = [
        ClientPayload(
            f"SITE_{index:02d}",
            index + 1,
            (np.asarray([index / 10, -index / 20], dtype=np.float32),),
            index + 2,
        )
        for index in range(8)
    ]
    return payloads, [np.zeros(2, dtype=np.float32)]


def test_version_and_real_flower_apis() -> None:
    assert flwr.__version__ == "1.39.0"
    assert SecAggPlusWorkflow.__module__.startswith("flwr.")
    assert secaggplus_mod.__module__.startswith("flwr.")


def test_config_is_predeclared_and_iid_fedavg() -> None:
    config = yaml.safe_load((ROOT / "configs/secagg_v1.yaml").read_text())
    assert config["clients"] == 8
    assert config["base_condition"] == "FL_IID_V1"
    assert config["algorithm"] == "FEDAVG"
    assert config["num_shares"] == 5
    assert config["reconstruction_threshold"] == 4
    assert config["max_weight"] == 4096.0
    assert config["runtime"]["measured_trials"] == 10


def test_plain_visibility_negative_control_and_tamper() -> None:
    payloads, initial = fixture()
    _, plain, accounting = run_plain_reference(payloads, initial)
    protected = ServerVisibilityProbe("protected-fixture")
    protected.observe_aggregate()
    require_visibility_contract(plain, protected)
    assert plain.clear_individual_update_count == 8
    assert accounting["accounting_id"] == ACCOUNTING_ID
    neutral = ServerVisibilityProbe("neutralized")
    with pytest.raises(RuntimeError, match="VISIBILITY_PROBE_NOT_SENSITIVE"):
        require_visibility_contract(neutral, protected)
    protected.observe_plain_update(1, has_arrays=True, has_weight=True)
    with pytest.raises(RuntimeError, match="PROTECTED_CLEAR_UPDATE_EXPOSED"):
        require_visibility_contract(plain, protected)


def test_real_secaggplus_known_vector() -> None:
    payloads, initial = fixture()
    plain, plain_probe, _ = run_plain_reference(payloads, initial)
    protected, protected_probe, _, stages = run_flower_secaggplus(payloads, initial)
    require_visibility_contract(plain_probe, protected_probe)
    delta = np.asarray(protected[0]) - np.asarray(plain[0])
    assert float(np.max(np.abs(delta))) <= 1e-4
    assert stages == 4
    assert protected_probe.masked_vector_count == 8


def test_required_scope_and_claim_language() -> None:
    threat = (ROOT / "docs/privacy_threat_model.md").read_text()
    config = (ROOT / "configs/secagg_v1.yaml").read_text()
    assert "differential privacy" in threat
    assert "real-hospital privacy" in threat
    assert "FEDAVG" in config
    assert "FedProx" not in config
    source = (ROOT / "privacy/secagg_app.py").read_text()
    assert "secaggplus_mod" in source
    assert "SecAggPlusWorkflow" in source
    assert "custom additive" not in source


def test_protected_requires_eight_clients() -> None:
    payloads, initial = fixture()
    with pytest.raises(ValueError, match="exactly eight"):
        run_flower_secaggplus(payloads[:-1], initial)
