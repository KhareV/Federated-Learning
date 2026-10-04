"""V2-FL-004 method tests: SECAGG_CONFIG_V2 fidelity to the historical T028 parameters, preflight
facts, historical-artifact immutability and the pre-result method lock. Immutable facts only."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "reports/model_v2/v2_fl_004/preflight"
V2 = yaml.safe_load((ROOT / "configs/model_v2/secagg_v2.yaml").read_text())
V1 = yaml.safe_load((ROOT / "configs/secagg_v1.yaml").read_text())


def test_parameters_exactly_historical() -> None:
    for key in ("num_shares", "reconstruction_threshold", "max_weight", "clipping_range",
                "quantization_range", "modulus_range", "timeout"):
        assert V2[key] == V1[key], key
    assert V2["correctness"]["maximum_absolute_parameter_difference"] == 1e-4
    assert V2["correctness"]["relative_l2_difference"] == 1e-4
    assert V2["runtime"]["measured_trials_per_path"] == 10
    assert V2["flower_version"] == "1.39.0"


def test_forbidden_partitions_and_hygiene_declared() -> None:
    for name in ("VALIDATION", "CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"):
        assert V2["access"][name] == "FORBIDDEN"
    assert not any(V2["evidence_hygiene"].values())
    assert "differential privacy" in V2["unsupported_claims"]


def test_preflight_facts() -> None:
    rec = json.loads((PRE / "round1_reconstruction.json").read_text())
    assert rec["status"] == "PASS" and rec["exact_match"] and rec["weights_exact"]
    clip = json.loads((PRE / "clipping_preflight.json").read_text())
    assert clip["coordinates_outside_range"] == 0 and clip["nonfinite_count"] == 0
    assert clip["coordinates_at_or_beyond_boundary"] == 0
    transport = json.loads((PRE / "state_transport_audit.json").read_text())
    assert transport["total_entries"] == 92 and transport["matches_expected"]


def test_historical_secagg_v1_artifacts_unchanged() -> None:
    lock = json.loads((ROOT / "artifacts/SECAGG_METHOD_V2.lock.json").read_text())
    for relative in ("privacy/secagg_app.py", "privacy/server_visibility.py",
                     "privacy/accounting.py", "scripts/run_secagg_t028.py",
                     "configs/secagg_v1.yaml", "artifacts/SECAGG_METHOD_V1.lock.json",
                     "artifacts/SECAGG_CONFIG_V1.lock.json"):
        assert hash_file(ROOT / relative) == lock["bound_artifacts"][relative], relative


def test_method_lock_is_pre_result_and_excludes_lifecycle_test() -> None:
    lock = json.loads((ROOT / "artifacts/SECAGG_METHOD_V2.lock.json").read_text())
    assert lock["frozen_before_any_canonical_secagg_outcome"] is True
    assert lock["lifecycle_test_bound"] is False
    assert not any("current_lifecycle" in p for p in lock["bound_artifacts"])
    assert lock["gate"]["blocks_tasks"] == ["V2-FL-005"]
    assert lock["parameters"]["timeout"] is None
