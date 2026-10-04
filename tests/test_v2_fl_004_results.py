"""V2-FL-004 post-result tests: canonical SecAgg+ evidence, narrow claims, firewall, immutability,
and the registry transition. Immutable facts only (no future-task NOT_STARTED assertions)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_004"


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text())


@pytest.mark.parametrize("name", [
    "known_vector_correctness.json", "aggregate_correctness.json", "server_visibility_audit.json",
    "client_data_locality_audit.json", "overhead_summary.json", "reproducibility.json",
    "v1_v2_scaling_comparison.json", "privacy_claim_audit.json", "firewall_audit.json",
    "secret_material_audit.json", "method_immutability_post_exposure.json",
    "protected_artifact_audit.json"])
def test_evidence_pass(name: str) -> None:
    assert _j(name)["status"] == "PASS"


def test_correctness_within_predeclared_tolerance() -> None:
    model = _j("aggregate_correctness.json")["MODEL_V2_shaped"]
    assert model["maximum_absolute_difference"] <= 1e-4 and model["relative_L2_difference"] <= 1e-4
    assert model["plain_reference_reproduces_authoritative_sha"] is True
    assert model["clipped_value_count"] == 0 and model["nonfinite_tensor_count"] == 0


def test_visibility_negative_control_and_protected_path() -> None:
    vis = _j("server_visibility_audit.json")
    assert vis["plain_clear_update_count"] == 8 and vis["plain_detector_positive"]
    assert vis["protected_clear_update_count"] == 0 and vis["protected_aggregate_available"]
    assert vis["protected_interface"]["masked_vectors_visible"] == 8


def test_ten_of_ten_protected_completions_and_byte_rule() -> None:
    over = _j("overhead_summary.json")
    assert over["completion"] == {"attempted": 10, "completed": 10, "failed": 0, "rate": 1.0}
    assert over["application_payload_bytes"]["accounting_id"] == (
        "FLOWER_APPLICATION_PAYLOAD_BYTES_V1")
    assert over["application_payload_bytes"]["exact_network_bytes"] is False
    assert over["deployment_latency_claim"] is False
    rows = list(csv.DictReader((OUT / "overhead_trials.csv").open()))
    assert len(rows) == 20


def test_firewall_train_only_no_secrets() -> None:
    assert _j("firewall_audit.json")["partitions_accessed"] == ["TRAIN"]
    secret = _j("secret_material_audit.json")
    assert secret["hits"] == [] and not secret["private_keys_persisted"]


def test_v2flg3_and_registry_transition() -> None:
    criteria = _j("v2flg3_criteria.json")
    flags = criteria["criteria"]
    if flags["regression"] == "PENDING_STAGE1":  # transient while the regression runs
        assert all(v is True for k, v in flags.items() if k != "regression")
    else:
        assert criteria["status"] == "PASS" and all(v is True for v in flags.values())
    assert criteria["performance_magnitude_is_a_criterion"] is False

    def rows(name: str, key: str) -> dict:
        with (ROOT / f"manifests/model_v2/{name}_registry_v1.csv").open(newline="") as handle:
            return {r[key]: r["status"] for r in csv.DictReader(handle)}

    assert rows("task", "task_id")["V2-FL-004"] == "PASS"
    assert rows("gate", "gate_id")["V2FLG3"] == "PASS"
    components = rows("component", "component_id")
    assert components["SECAGG_CONFIG_V2"] == "FROZEN_RESEARCH_PRIVACY_PROTOCOL"
    assert components["SECAGG_METHOD_V2"] == "FROZEN_PRE_RESULT_METHOD"


def test_historical_secagg_v1_untouched() -> None:
    lock = json.loads((ROOT / "artifacts/SECAGG_METHOD_V2.lock.json").read_text())
    for path, digest in lock["bound_artifacts"].items():
        if path.startswith(("privacy/", "configs/secagg", "artifacts/SECAGG_", "reports/t028")):
            assert hash_file(ROOT / path) == digest
