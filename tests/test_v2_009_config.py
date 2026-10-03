"""V2-009 pre-CALIBRATION test gate (Section 39). Must all pass BEFORE the canonical
CALIBRATION waveform access. Covers: entry/upstream/provenance-disclosure/population-closure
preflight evidence, the one-shot CALIBRATION guard's state machine, the partition firewall
(CALIBRATION allowed, everything else forbidden), and the CAL_V2 verifier's tamper-detection
logic -- exercised against a FABRICATED CAL_V2 artifact layered on top of the real (already-
frozen) MODEL_V2_FINAL package, since no real CAL_V2 exists yet.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

import scripts._cal_v2_lib as cal_lib
from models.cal_v2_verify import CalV2VerifyError, verify_cal_v2
from nhm.hashing import hash_file
from nhm.model_v2_calibration_guard import (
    CalibrationGuardViolation,
    arm_guard,
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
    read_guard_state,
)
from nhm.model_v2_partition_guard import PartitionAccessViolation, check_partition_allowed

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_009"


def _load(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Preflight evidence (Sections 1,3,4,5,7,8,11)
# ---------------------------------------------------------------------------

def test_entry_audit_pass() -> None:
    data = _load("entry_audit.json")
    assert data["status"] == "PASS"
    assert data["head_equals_origin_main"] is True
    assert data["model_v2_final_frozen"] is True
    assert data["cal_v2_absent"] is True


def test_v2_008_provenance_disclosure_honest() -> None:
    data = _load("v2_008_entry_provenance_disclosure.json")
    assert data["status"] == "DISCLOSED"
    fact_a = data["fact_a_outer_timeout_claim"]
    assert fact_a["disclosure_fabrication_declined"] is True
    fact_b = data["fact_b_verifier_chronology"]
    assert fact_b["status"] == "CONFIRMED_AND_CORRECTED"
    assert fact_b["diff_is_purely_additive"] is True
    assert fact_b["classification"] == "ADDITIVE_FAIL_CLOSED_VALIDATION_HARDENING"
    assert fact_b["scientific_impact"] == "NONE"


def test_v2_008_method_diff_pass() -> None:
    data = _load("v2_008_method_diff_audit.json")
    assert data["status"] == "PASS"
    assert data["checkpoint_created_once_not_changed"] is True
    assert data["architecture_unchanged"] is True
    assert data["promotion_status_unchanged"] is True
    assert data["operational_lineage_unchanged"] is True


def test_upstream_identity_pass() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    for check in data["checks"].values():
        assert check["match"] is True


def test_model_v2_final_verification_pass() -> None:
    data = _load("model_v2_final_verification.json")
    assert data["status"] == "PASS"
    assert data["both_pass"] is True
    assert data["checkpoint_sha_matches_expected"] is True


def test_freeze_identity_does_not_touch_canonical_registry() -> None:
    data = _load("freeze_identity_audit.json")
    assert data["status"] == "PASS"
    assert data["canonical_registry_modified"] is False
    assert data["canonical_registry_row_count"] == 15


def test_calibration_population_closure_exact() -> None:
    data = _load("calibration_population_audit.json")
    assert data["status"] == "PASS"
    assert data["split_record_count"] == 4
    assert data["contributing_patient_groups"] == 3
    assert data["eligible_windows"] == 1080
    assert data["positive_windows"] == 367
    assert data["negative_windows"] == 713
    assert data["both_classes_present"] is True
    assert data["matches_historical_expectation"] is True


# ---------------------------------------------------------------------------
# Partition firewall (Section 10)
# ---------------------------------------------------------------------------

def test_calibration_partition_allowed() -> None:
    check_partition_allowed("CALIBRATION", "V2-009_CALIBRATION", {"CALIBRATION"})


@pytest.mark.parametrize(
    "forbidden", ["TRAIN", "VALIDATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"]
)
def test_forbidden_partitions_rejected(forbidden: str) -> None:
    with pytest.raises(PartitionAccessViolation):
        check_partition_allowed(forbidden, "V2-009_CALIBRATION", {"CALIBRATION"})


def test_load_calibration_population_v2_firewall_wired() -> None:
    # Calling with an impossible allowed-set proves the wrapper actually calls the firewall
    # (not just a docstring claim) -- real population loading is exercised only once, in the
    # guarded one-shot session itself.
    import scripts._cal_v2_lib as lib

    original = lib.check_partition_allowed
    try:
        def deny(*_args, **_kwargs):
            raise PartitionAccessViolation("FORCED_FOR_TEST")

        lib.check_partition_allowed = deny
        with pytest.raises(PartitionAccessViolation):
            cal_lib.load_calibration_population_v2(ROOT)
    finally:
        lib.check_partition_allowed = original


# ---------------------------------------------------------------------------
# One-shot CALIBRATION guard (Section 14) -- synthetic, uses a temp root
# ---------------------------------------------------------------------------

def test_guard_arm_then_begin_then_complete() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, preconditions=preconditions)
        state = check_and_begin_session(root, observed_preconditions=preconditions)
        assert state["state"] == "RUNNING"
        completed = complete_session(root, completion_summary={"rows": 1080})
        assert completed["state"] == "COMPLETED"


def test_guard_second_invocation_blocked_after_completion() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, preconditions=preconditions)
        check_and_begin_session(root, observed_preconditions=preconditions)
        complete_session(root, completion_summary={"rows": 1080})
        with pytest.raises(CalibrationGuardViolation, match="ALREADY_CONSUMED"):
            check_and_begin_session(root, observed_preconditions=preconditions)


def test_guard_precondition_mismatch_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        arm_guard(root, preconditions={"a": 1})
        with pytest.raises(CalibrationGuardViolation, match="PRECONDITION_MISMATCH"):
            check_and_begin_session(root, observed_preconditions={"a": 2})


def test_guard_partial_consumption_blocks_further_access() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, preconditions=preconditions)
        check_and_begin_session(root, observed_preconditions=preconditions)
        mark_partially_consumed(root, failure_summary={"error": "crash"})
        state = read_guard_state(root)
        assert state["requires_human_review"] is True
        with pytest.raises(CalibrationGuardViolation, match="PARTIALLY_CONSUMED"):
            check_and_begin_session(root, observed_preconditions=preconditions)


def test_guard_cannot_double_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        arm_guard(root, preconditions={"a": 1})
        with pytest.raises(CalibrationGuardViolation, match="GUARD_ALREADY_EXISTS"):
            arm_guard(root, preconditions={"a": 1})


def test_real_guard_file_armed_before_any_calibration_access() -> None:
    state = read_guard_state(ROOT)
    assert state is not None
    assert state["state"] in {"ARMED", "RUNNING", "COMPLETED"}


# ---------------------------------------------------------------------------
# ECE / reliability helper sanity (Section 23) -- the shared math already has its own
# exhaustive test suite (tests/test_calibration_v1.py); this only checks the CAL_V2-specific
# ECE aggregator, which is new code.
# ---------------------------------------------------------------------------

def test_ece_formula() -> None:
    import scripts.fit_cal_v2 as fit_mod

    bins = [
        {"count": 5, "mean_probability": 0.2, "observed_positive_fraction": 0.4},
        {"count": 0, "mean_probability": None, "observed_positive_fraction": None},
        {"count": 5, "mean_probability": 0.8, "observed_positive_fraction": 0.6},
    ]
    result = fit_mod.ece(bins)
    expected = (5 / 10) * abs(0.2 - 0.4) + (5 / 10) * abs(0.8 - 0.6)
    assert abs(result - expected) < 1e-12


# ---------------------------------------------------------------------------
# CAL_V2 verifier tamper-detection -- fabricated CAL_V2 artifact over the REAL (already
# frozen) MODEL_V2_FINAL package
# ---------------------------------------------------------------------------

def _build_fake_cal_v2_package(tmp_path: Path) -> None:
    real_manifest = json.loads(
        (ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text(encoding="utf-8")
    )
    paths_to_copy = {
        "checkpoints/MODEL_V2_FINAL.pt",
        "checkpoints/MODEL_V2_FINAL.manifest.json",
        "configs/model_v2_final_frozen.yaml",
        "tests/fixtures/model_v2_final_test_vector.npz",
        "manifests/splits/MITDB_SPLIT_V1.csv",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "manifests/windows/MITDB_WINDOWS_V1.csv",
        "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        *real_manifest["upstream_sha256"],
    }
    for rel in paths_to_copy:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)

    checkpoint_sha = hash_file(tmp_path / "checkpoints/MODEL_V2_FINAL.pt")
    manifest_sha = hash_file(tmp_path / "checkpoints/MODEL_V2_FINAL.manifest.json")
    frozen_config_sha = hash_file(tmp_path / "configs/model_v2_final_frozen.yaml")
    protocol_v3_sha = hash_file(
        tmp_path / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
    )
    split_sha = hash_file(tmp_path / "manifests/splits/MITDB_SPLIT_V1.csv")
    preproc_sha = hash_file(tmp_path / "manifests/preprocessing/PREPROC_V1.lock.json")
    window_manifest_sha = hash_file(tmp_path / "manifests/windows/MITDB_WINDOWS_V1.csv")

    artifact = {
        "calibration_id": "CAL_V2",
        "status": "FROZEN",
        "model_id": "MODEL_V2_FINAL",
        "fit_partition": "CALIBRATION",
        "calibration_domain": "MIT-BIH-v1.0.0",
        "calibration_patient_count": 3,
        "calibration_window_count": 1080,
        "temperature": 1.5,
        "threshold": 0.4,
        "model_checkpoint_sha256": checkpoint_sha,
        "model_manifest_sha256": manifest_sha,
        "model_frozen_config_sha256": frozen_config_sha,
        "protocol_v3_lock_sha256": protocol_v3_sha,
        "split_sha256": split_sha,
        "preproc_sha256": preproc_sha,
        "window_manifest_sha256": window_manifest_sha,
        "target_id": "AAMI_SVF_WINDOW_V1",
        "map_id": "AAMI_SVF_MAP_V1",
        "threshold_comparator": ">=",
        "threshold_metric": "POOLED_CALIBRATION_WINDOW_F1",
        "threshold_tie_policy": "HIGHEST_THRESHOLD_AMONG_MAX_F1_V2",
        "internal_test_accessed": False,
        "external_data_accessed": False,
        "operational_lineage": "MODEL_V1",
        "runtime_acceptance": "NOT_EVALUATED",
        "upstream_sha256": {
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json": protocol_v3_sha,
            # AAMI_SVF_MAP_V1.yaml has no dedicated "*_binding" required-field check in
            # verify_cal_v2 (only its map_id STRING is checked there) and is not part of
            # MODEL_V2_FINAL's own upstream bindings, so tampering its file content can only
            # be caught by CAL_V2's own upstream_sha256 loop -- exercising that check
            # specifically rather than an earlier cascading one.
            "manifests/labels/AAMI_SVF_MAP_V1.yaml": hash_file(
                tmp_path / "manifests/labels/AAMI_SVF_MAP_V1.yaml"
            ),
        },
    }
    artifact_path = tmp_path / "artifacts/CAL_V2.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    guard_path = tmp_path / "reports/model_v2/v2_009/calibration_access_guard.json"
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    guard_path.write_text(json.dumps({"state": "COMPLETED"}), encoding="utf-8")


def test_fabricated_cal_v2_package_verifies_cleanly(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    result = verify_cal_v2(tmp_path)
    assert result["status"] == "PASS"


def test_tamper_temperature_nonpositive_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["temperature"] = -1.0
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_temperature_nan_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["temperature"] = float("nan")
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_threshold_out_of_range_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["threshold"] = 1.5
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_fit_partition_changed_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["fit_partition"] = "TRAIN"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_domain_changed_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["calibration_domain"] = "INCART"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_comparator_changed_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["threshold_comparator"] = ">"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_tie_policy_changed_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["threshold_tie_policy"] = "LOWEST_THRESHOLD"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_internal_test_accessed_flag_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["internal_test_accessed"] = True
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_operational_lineage_changed_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    path = tmp_path / "artifacts/CAL_V2.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["operational_lineage"] = "MODEL_V2_FINAL"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_guard_not_completed_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    guard_path = tmp_path / "reports/model_v2/v2_009/calibration_access_guard.json"
    guard_path.write_text(json.dumps({"state": "RUNNING"}), encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_SEMANTIC_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_tamper_upstream_hash_changed_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    map_path = tmp_path / "manifests/labels/AAMI_SVF_MAP_V1.yaml"
    map_path.write_text(map_path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    with pytest.raises(CalV2VerifyError, match="CAL_V2_UPSTREAM_HASH_MISMATCH"):
        verify_cal_v2(tmp_path)


def test_cal_v2_missing_detected(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    (tmp_path / "artifacts/CAL_V2.json").unlink()
    with pytest.raises(CalV2VerifyError, match="CAL_V2_MISSING"):
        verify_cal_v2(tmp_path)


def test_checkpoint_tamper_detected_via_model_v2_final_verification(tmp_path: Path) -> None:
    _build_fake_cal_v2_package(tmp_path)
    checkpoint_path = tmp_path / "checkpoints/MODEL_V2_FINAL.pt"
    data = bytearray(checkpoint_path.read_bytes())
    data[len(data) // 2] ^= 1
    checkpoint_path.write_bytes(bytes(data))
    with pytest.raises(Exception):  # noqa: B017 -- ModelV2FinalFreezeError, re-raised path
        verify_cal_v2(tmp_path)


def test_no_patient_cluster_bootstrap_module_imported_this_phase() -> None:
    # Section 37: V2-009 must not perform the D9/second-look performance bootstrap. This is
    # a structural guard -- the CAL_V2 lib must not import any V2-007-style bootstrap module.
    import scripts._cal_v2_lib as lib

    source = Path(lib.__file__).read_text(encoding="utf-8")
    assert "bootstrap" not in source.lower()


def test_reliability_svg_has_no_volatile_timestamp() -> None:
    bins = [
        {"bin_index": i, "count": 1, "mean_probability": 0.5, "observed_positive_fraction": 0.5}
        for i in range(10)
    ]
    svg_a = cal_lib.reliability_svg(bins, bins)
    svg_b = cal_lib.reliability_svg(bins, bins)
    assert svg_a == svg_b


def test_reliability_bins_both_raw_and_calibrated_share_edges() -> None:
    probs = np.asarray([0.05, 0.35, 0.95])
    labels = np.asarray([0, 1, 1])
    bins = cal_lib.reliability_bins(probs, labels)
    assert len(bins) == 10
    assert bins[9]["upper_inclusive"] is True
