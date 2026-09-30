from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_t026 import verify

ROOT = Path(__file__).resolve().parents[1]


def test_all_four_results_verify() -> None:
    result = verify(ROOT)
    assert result["status"] == "PASS"
    assert result["client_updates"] == 1600


def test_matched_budget_and_clean_validation() -> None:
    audit = json.loads((ROOT / "reports/t026/matched_budget_audit.json").read_text())
    for condition in audit["conditions"].values():
        assert condition["patient_pool_identical"] is True
        assert condition["total_examples_identical"] is True
        assert condition["rounds"] == 50
        assert condition["clients_per_round"] == 8
        assert condition["validation"] == "VALIDATION_CLEAN"
        assert condition["only_intended_heterogeneity_changed"] is True


def test_scope_and_fedprox_deferred() -> None:
    audit = json.loads((ROOT / "reports/t026/scope_audit.json").read_text())
    assert audit["TRAIN_access"] is True
    assert audit["VALIDATION_access"] is True
    assert audit["NSTDB_pure_noise_access"] is True
    for key in (
        "NSTDB_labels_access",
        "CALIBRATION_access",
        "INTERNAL_TEST_access",
        "INCART_access",
        "BIDMC_access",
        "WEARABLE_V1_access",
        "CAL_V1_applied",
        "FedProx",
        "SecAgg_plus",
        "differential_privacy",
        "hardware",
    ):
        assert audit[key] is False


def test_fedprox_metric_semantics_remains_explicitly_unresolved() -> None:
    audit = json.loads((ROOT / "reports/t026/fedprox_metric_semantics_audit.json").read_text())
    assert audit["status_for_T027"] == "REQUIRES_PRE_T027_INTERPRETATION"
    assert audit["pseudo_client_validation_groups_invented"] is False
    assert audit["TRAIN_diagnostics_mislabeled_validation"] is False
