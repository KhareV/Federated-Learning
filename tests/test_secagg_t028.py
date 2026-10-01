"""Focused T028 Flower SecAgg+ correctness and scope tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import flwr
import numpy as np
import pytest
import yaml
from flwr.client.mod import secaggplus_mod
from flwr.server.workflow import SecAggPlusWorkflow

from federated.model_adapter import fresh_model_v1, model_v1_state_spec
from nhm.hashing import hash_bytes, hash_file
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
            1000 + 50 * index,
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


def test_weight_range_transport_and_clipping_preflight() -> None:
    audit = json.loads((ROOT / "reports/t028/clipping_preflight.json").read_text())
    assert audit["maximum_client_weight"] == 1436
    assert audit["maximum_client_weight"] < audit["max_weight"]
    assert audit["coordinates_at_or_beyond_boundary"] == 0
    specs = model_v1_state_spec(fresh_model_v1())
    assert any(spec.state_role == "non_floating_buffer" for spec in specs)
    assert all(not spec.aggregatable for spec in specs if spec.state_role == "non_floating_buffer")


def test_correctness_tamper_and_frozen_reference_identity() -> None:
    report = json.loads((ROOT / "reports/t028/aggregate_correctness.json").read_text())
    model = report["MODEL_V1_shaped"]
    assert model["plain_aggregate_sha256"] == model["authoritative_T025_round_1_state_sha256"]
    assert model["maximum_absolute_difference"] <= 1e-4
    mutated_difference = model["maximum_absolute_difference"] + 2e-4
    assert mutated_difference > 1e-4


def test_trials_failures_and_byte_accounting_are_retained() -> None:
    with (ROOT / "reports/t028/overhead_trials.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 20
    assert sum(row["path"] == "FLOWER_SECAGGPLUS_V1" for row in rows) == 10
    assert all(row["status"] == "PASS" for row in rows)
    assert all(int(row["total"]) > 0 for row in rows)


def test_no_raw_data_or_secret_material_persisted() -> None:
    locality = json.loads((ROOT / "reports/t028/client_data_locality_audit.json").read_text())
    assert locality["raw_ECG_waveform_in_server_messages"] is False
    assert locality["AAMI_labels_in_server_messages"] is False
    protocol = json.loads((ROOT / "reports/t028/flower_protocol_log.json").read_text())
    assert protocol["private_material_persisted"] is False
    visibility = json.loads((ROOT / "reports/t028/server_visibility_audit.json").read_text())
    assert visibility["protected_clear_update_count"] == 0


def test_f13_lock_detects_config_tamper() -> None:
    lock = json.loads((ROOT / "artifacts/SECAGG_CONFIG_V1.lock.json").read_text())
    config_path = "configs/secagg_v1.yaml"
    expected = lock["bound_artifacts"][config_path]
    actual = hash_file(ROOT / config_path)
    assert actual == expected
    mutated = (ROOT / config_path).read_bytes().replace(b"num_shares: 5", b"num_shares: 7")
    assert hash_bytes(mutated) != expected


def test_narrow_claim_and_scope_artifacts() -> None:
    audit = json.loads((ROOT / "reports/t028/privacy_claim_audit.json").read_text())
    claim = audit["supported_claim"]
    assert "instrumented protected aggregation interface" in claim
    assert "application-level server aggregation point" in claim
    assert "privacy guaranteed" not in claim.lower()
    scope = json.loads((ROOT / "reports/t028/scope_audit.json").read_text())
    assert scope["FedProx"] is False
    assert scope["differential_privacy"] is False
    assert all(
        not accessed
        for partition, accessed in scope["partition_access"].items()
        if partition != "TRAIN"
    )
