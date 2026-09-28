"""T010 canonical leakage-audit test suite.

Covers both (a) real-manifest invariants recomputed directly against the committed
MITDB_SPLIT_V1 artifacts, and (b) synthetic adversarial cases that exercise
evaluation.leakage_audit's functions directly -- never by only re-reading a previously
generated JSON report. tests/test_mitdb_grouping.py, tests/test_mitdb_split_v1.py, and
tests/test_split_determinism.py (T009) remain unchanged and continue to pass; this file adds
an independent adversarial layer on top.
"""

from __future__ import annotations

import json
import shutil
from itertools import combinations
from pathlib import Path

import pytest

from evaluation.leakage_audit import (
    PARTITIONS,
    ExternalDataRoleViolation,
    FitScopeViolation,
    PartitionRoleViolation,
    SplitEligibilityMismatch,
    SplitGroupingMismatch,
    SplitHashMismatch,
    SplitPatientOverlap,
    SplitUpstreamMismatch,
    WindowAuditRow,
    assert_incart_operation_allowed,
    assert_partition_use_allowed,
    audit_eligible_record_closure,
    audit_fit_scope,
    audit_group_assignment_completeness,
    audit_group_disjointness,
    audit_group_invariant,
    audit_partition_vocabulary,
    audit_window_manifest,
    verify_frozen_split,
)
from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "manifests/splits"

LOCK_WORKSPACE_FILES = [
    "manifests/splits/MITDB_SPLIT_V1.csv",
    "manifests/splits/MITDB_SPLIT_V1.yaml",
    "manifests/splits/mitdb_groups.csv",
    "manifests/splits/mitdb_patient_strata.csv",
    "manifests/splits/partition_roles_v1.yaml",
    "manifests/splits/MITDB_SPLIT_V1.lock.json",
    "manifests/labels/AAMI_SVF_MAP_V1.yaml",
    "manifests/datasets/mitdb_mlii_records.csv",
]


def _split_rows() -> list[dict[str, str]]:
    return read_csv(SPLIT_DIR / "MITDB_SPLIT_V1.csv")


def _make_workspace(tmp_path: Path) -> Path:
    for relative in LOCK_WORKSPACE_FILES:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return tmp_path


def _forge_lock_hash(tmp_path: Path, field: str, relative_path: str) -> None:
    """Simulate a dishonest lock: recompute the (now-tampered) file's hash and overwrite the
    lock's recorded value with it, so the hash check alone no longer catches the tampering --
    used to prove the deeper semantic checks are independent defense, not decoration."""
    from nhm.hashing import hash_file

    lock_path = tmp_path / "manifests/splits/MITDB_SPLIT_V1.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock[field] = hash_file(tmp_path / relative_path)
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------------------
# Real-manifest invariants (recomputed against the committed split, not trusted from T009)
# ---------------------------------------------------------------------------------------


def test_real_split_eligible_record_closure() -> None:
    split_rows = _split_rows()
    eligible_records_path = ROOT / "manifests/datasets/mitdb_mlii_records.csv"
    eligible_ids = {row["record_id"] for row in read_csv(eligible_records_path)}
    result = audit_eligible_record_closure(split_rows, eligible_ids)
    assert result["status"] == "PASS"
    assert "102" not in {row["record_id"] for row in split_rows}
    assert "104" not in {row["record_id"] for row in split_rows}


def test_real_split_group_assignment_completeness() -> None:
    split_rows = _split_rows()
    strata_rows = read_csv(SPLIT_DIR / "mitdb_patient_strata.csv")
    result = audit_group_assignment_completeness(
        split_rows, {row["participant_group_id"] for row in strata_rows}
    )
    assert result == {
        "status": "PASS", "errors": [], "unassigned_count": 0, "multiply_assigned_count": 0,
    }


def test_real_split_zero_pairwise_patient_overlap() -> None:
    split_rows = _split_rows()
    result = audit_group_disjointness(split_rows, "participant_group_id", "partition")
    assert result["status"] == "PASS"
    assert result["pairwise_overlaps"] == []
    assert len(list(combinations(result["partitions"], 2))) == 6


def test_real_split_201_202_invariant() -> None:
    result = audit_group_invariant(_split_rows(), ["201", "202"])
    assert result["status"] == "PASS"
    assert result["group_id"] == "MITDB_P201_202"
    assert result["record_count_found"] == 2


def test_real_split_partition_vocabulary_is_canonical() -> None:
    result = audit_partition_vocabulary(_split_rows())
    assert result == {"status": "PASS", "invalid_partitions": []}


def test_verify_frozen_split_passes_against_committed_lock() -> None:
    result = verify_frozen_split(ROOT)
    assert result["status"] == "PASS"
    assert result["split_id"] == "MITDB_SPLIT_V1"


# ---------------------------------------------------------------------------------------
# Synthetic adversarial population/eligibility/disjointness cases
# ---------------------------------------------------------------------------------------


def test_eligibility_rejects_missing_record() -> None:
    rows = [{"record_id": "100"}]
    result = audit_eligible_record_closure(rows, ["100", "101"])
    assert result["status"] == "FAIL"
    assert result["missing"] == ["101"]


def test_eligibility_rejects_extra_record() -> None:
    rows = [{"record_id": "100"}, {"record_id": "102"}]
    result = audit_eligible_record_closure(rows, ["100"])
    assert result["status"] == "FAIL"
    assert result["extra"] == ["102"]


def test_disjointness_rejects_patient_in_two_partitions() -> None:
    rows = [
        {"participant_group_id": "A", "partition": "TRAIN"},
        {"participant_group_id": "A", "partition": "INTERNAL_TEST"},
    ]
    result = audit_group_disjointness(rows, "participant_group_id", "partition")
    assert result["status"] == "FAIL"
    assert result["pairwise_overlaps"] == [("INTERNAL_TEST", "TRAIN", ["A"])]


def test_completeness_rejects_unassigned_and_multiply_assigned_groups() -> None:
    rows = [
        {"participant_group_id": "A", "partition": "TRAIN"},
        {"participant_group_id": "A", "partition": "VALIDATION"},
    ]
    result = audit_group_assignment_completeness(rows, {"A", "B"})
    assert result["status"] == "FAIL"
    assert result["unassigned_count"] == 1
    assert result["multiply_assigned_count"] == 1


def test_partition_vocabulary_rejects_unexpected_values() -> None:
    for invalid in ("DEV", "TEST", "HOLDOUT", "UNKNOWN"):
        result = audit_partition_vocabulary([{"partition": invalid}])
        assert result["status"] == "FAIL"
        assert result["invalid_partitions"] == [invalid]


def test_group_invariant_rejects_separated_201_202() -> None:
    rows = [
        {"record_id": "201", "participant_group_id": "G1", "partition": "TRAIN"},
        {"record_id": "202", "participant_group_id": "G2", "partition": "VALIDATION"},
    ]
    result = audit_group_invariant(rows, ["201", "202"])
    assert result["status"] == "FAIL"
    assert result["same_group"] is False
    assert result["same_partition"] is False


# ---------------------------------------------------------------------------------------
# Partition-role / fit-scope / INCART external-guard contracts (Sections 13-16)
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "partition,operation",
    [
        ("TRAIN", "FIT_MODEL_WEIGHTS"),
        ("VALIDATION", "EARLY_STOPPING"),
        ("CALIBRATION", "TEMPERATURE_SCALING"),
        ("INTERNAL_TEST", "FINAL_LOCKED_INTERNAL_EVALUATION"),
    ],
)
def test_partition_role_allows_canonical_operations(partition: str, operation: str) -> None:
    assert_partition_use_allowed(partition, operation)  # must not raise


@pytest.mark.parametrize(
    "partition,operation",
    [
        ("VALIDATION", "FIT_MODEL_WEIGHTS"),
        ("CALIBRATION", "FIT_MODEL_WEIGHTS"),
        ("CALIBRATION", "MODEL_SELECTION"),
        ("INTERNAL_TEST", "THRESHOLD_SELECTION"),
        ("VALIDATION", "FINAL_LOCKED_INTERNAL_EVALUATION"),
    ],
)
def test_partition_role_rejects_out_of_role_operations(partition: str, operation: str) -> None:
    with pytest.raises(PartitionRoleViolation):
        assert_partition_use_allowed(partition, operation)


def test_fit_scope_rejects_scaler_fit_on_train_and_validation() -> None:
    with pytest.raises(FitScopeViolation):
        audit_fit_scope("FIT_SCALER", ["TRAIN", "VALIDATION"])


def test_fit_scope_rejects_feature_selector_fit_on_internal_test() -> None:
    with pytest.raises(FitScopeViolation):
        audit_fit_scope("FIT_FEATURE_TRANSFORM", ["INTERNAL_TEST"])


def test_fit_scope_rejects_majority_baseline_from_calibration() -> None:
    with pytest.raises(FitScopeViolation):
        audit_fit_scope("DERIVE_MAJORITY_BASELINE", ["CALIBRATION"])


def test_fit_scope_accepts_correctly_scoped_operations() -> None:
    audit_fit_scope("FIT_SCALER", ["TRAIN"])
    audit_fit_scope("TEMPERATURE_SCALING", ["CALIBRATION"])
    audit_fit_scope("THRESHOLD_SELECTION", ["CALIBRATION"])


def test_fit_scope_rejects_validation_calibration_mixed_fit() -> None:
    with pytest.raises(FitScopeViolation):
        audit_fit_scope("TEMPERATURE_SCALING", ["VALIDATION", "CALIBRATION"])


def test_fit_scope_rejects_internal_test_threshold_tuning() -> None:
    with pytest.raises(FitScopeViolation):
        audit_fit_scope("THRESHOLD_SELECTION", ["INTERNAL_TEST"])


@pytest.mark.parametrize(
    "operation",
    [
        "TRAINING", "MODEL_SELECTION", "THRESHOLD_SELECTION", "TEMPERATURE_SCALING",
        "LEAD_SELECTION", "MAPPING_ADAPTATION", "PREPROCESSING_TUNING",
    ],
)
def test_incart_guard_rejects_every_forbidden_operation(operation: str) -> None:
    with pytest.raises(ExternalDataRoleViolation):
        assert_incart_operation_allowed(operation)


def test_incart_guard_allows_locked_external_evaluation() -> None:
    assert_incart_operation_allowed("LOCKED_EXTERNAL_EVALUATION")  # must not raise


# ---------------------------------------------------------------------------------------
# Federated-client disjointness harness (T025 will apply this unchanged; Section 17)
# ---------------------------------------------------------------------------------------


def test_fl_client_disjointness_harness_rejects_patient_in_two_clients() -> None:
    manifest = [
        {"participant_group_id": "MITDB_P100", "client_id": "client_1"},
        {"participant_group_id": "MITDB_P100", "client_id": "client_2"},
        {"participant_group_id": "MITDB_P101", "client_id": "client_2"},
    ]
    result = audit_group_disjointness(manifest, "participant_group_id", "client_id")
    assert result["status"] == "FAIL"
    assert result["pairwise_overlaps"] == [("client_1", "client_2", ["MITDB_P100"])]


def test_fl_client_disjointness_harness_passes_clean_manifest() -> None:
    manifest = [
        {"participant_group_id": "MITDB_P100", "client_id": "client_1"},
        {"participant_group_id": "MITDB_P101", "client_id": "client_2"},
    ]
    result = audit_group_disjointness(manifest, "participant_group_id", "client_id")
    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------------------
# Window-manifest leakage harness (synthetic provenance metadata; no waveform arrays)
# ---------------------------------------------------------------------------------------

_SPLIT_LOOKUP = {"100": ("MITDB_P100", "TRAIN"), "106": ("MITDB_P106", "VALIDATION")}
_ELIGIBLE = ["100", "106"]


def test_window_audit_passes_valid_within_partition_overlap() -> None:
    rows = [
        WindowAuditRow("w1", "MITDB_P100", "100", "TRAIN", 0, 3600, "h1"),
        WindowAuditRow("w2", "MITDB_P100", "100", "TRAIN", 1800, 5400, "h2"),
    ]
    result = audit_window_manifest(rows, _SPLIT_LOOKUP, _ELIGIBLE)
    assert result["status"] == "PASS"


def test_window_audit_rejects_same_patient_across_partitions() -> None:
    rows = [
        WindowAuditRow("w1", "MITDB_P100", "100", "TRAIN", 0, 3600, "h1"),
        WindowAuditRow("w2", "MITDB_P100", "100", "VALIDATION", 3600, 7200, "h2"),
    ]
    result = audit_window_manifest(rows, _SPLIT_LOOKUP, _ELIGIBLE)
    assert result["status"] == "FAIL"


def test_window_audit_rejects_duplicate_source_hash_across_partitions() -> None:
    rows = [
        WindowAuditRow("w1", "MITDB_P100", "100", "TRAIN", 0, 3600, "dup"),
        WindowAuditRow("w2", "MITDB_P106", "106", "VALIDATION", 0, 3600, "dup"),
    ]
    result = audit_window_manifest(rows, _SPLIT_LOOKUP, _ELIGIBLE)
    assert result["status"] == "FAIL"


def test_window_audit_rejects_overlapping_interval_across_partitions() -> None:
    lookup = {"201": ("MITDB_P201_202", "VALIDATION"), "202": ("MITDB_P201_202", "VALIDATION")}
    rows = [
        WindowAuditRow("w1", "MITDB_P201_202", "201", "VALIDATION", 0, 3600, "h1"),
        WindowAuditRow("w2", "MITDB_P201_202", "201", "TRAIN", 1800, 5400, "h2"),
    ]
    result = audit_window_manifest(rows, lookup, ["201", "202"])
    assert result["status"] == "FAIL"


def test_window_audit_rejects_wrong_partition_inheritance() -> None:
    rows = [WindowAuditRow("w1", "MITDB_P100", "100", "VALIDATION", 0, 3600, "h1")]
    result = audit_window_manifest(rows, _SPLIT_LOOKUP, _ELIGIBLE)
    assert result["status"] == "FAIL"


def test_window_audit_rejects_excluded_record() -> None:
    rows = [WindowAuditRow("w1", "MITDB_P102", "102", "TRAIN", 0, 3600, "h1")]
    result = audit_window_manifest(rows, _SPLIT_LOOKUP, _ELIGIBLE)
    assert result["status"] == "FAIL"


def test_window_audit_rejects_duplicate_example_ids() -> None:
    rows = [
        WindowAuditRow("dup", "MITDB_P100", "100", "TRAIN", 0, 3600, "h1"),
        WindowAuditRow("dup", "MITDB_P106", "106", "VALIDATION", 0, 3600, "h2"),
    ]
    result = audit_window_manifest(rows, _SPLIT_LOOKUP, _ELIGIBLE)
    assert result["status"] == "FAIL"


def test_synthetic_window_harness_report_confirms_deferred_real_windows() -> None:
    report = json.loads((ROOT / "reports/splits/window_audit.json").read_text(encoding="utf-8"))
    assert report["audit_mode"] == "SYNTHETIC_HARNESS_VALIDATION"
    assert report["real_window_count"] == 0
    assert report["real_window_manifest_available"] is False
    assert report["real_window_audit_deferred_to"] == "T013"
    assert report["overall_status"] == "PASS"


# ---------------------------------------------------------------------------------------
# Frozen-split immutability / tamper matrix (Sections 27-28)
# ---------------------------------------------------------------------------------------


def test_verify_frozen_split_passes_on_unmodified_copy(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    assert verify_frozen_split(workspace)["status"] == "PASS"


def test_tamper_partition_mutation_detected_by_hash(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    text = split_path.read_text(encoding="utf-8")
    mutated = text.replace(",TRAIN,", ",VALIDATION,", 1)
    assert mutated != text
    split_path.write_text(mutated, encoding="utf-8")
    with pytest.raises(SplitHashMismatch):
        verify_frozen_split(workspace)


def test_tamper_patient_moved_into_two_partitions_detected_when_hash_forged(
    tmp_path: Path,
) -> None:
    """"Moved into two partitions" means duplicated: the same participant_group_id appears
    under a second, different partition value while the original row is left in place --
    an overlap, which audit_group_disjointness (used inside verify_frozen_split) must catch
    even when the lock's hash has been forged to match the tampered bytes."""
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    lines = split_path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = lines[0].rstrip("\n").split(",")
    partition_index = header.index("partition")
    duplicate_line = None
    for line in lines[1:]:
        fields = line.rstrip("\n").split(",")
        if fields[0] == "100":
            alternate = "TRAIN" if fields[partition_index] == "INTERNAL_TEST" else "INTERNAL_TEST"
            fields[partition_index] = alternate
            duplicate_line = ",".join(fields) + "\n"
            break
    assert duplicate_line is not None
    split_path.write_text("".join([*lines, duplicate_line]), encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    expected_exceptions = (
        SplitPatientOverlap, SplitGroupingMismatch, SplitUpstreamMismatch, SplitEligibilityMismatch,
    )
    with pytest.raises(expected_exceptions):
        verify_frozen_split(workspace)


def test_tamper_record_202_moved_away_from_201_detected_when_hash_forged(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    lines = split_path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = lines[0].rstrip("\n").split(",")
    group_index = header.index("participant_group_id")
    for index in range(1, len(lines)):
        fields = lines[index].rstrip("\n").split(",")
        if fields[0] == "202":
            fields[group_index] = "MITDB_P202"
            lines[index] = ",".join(fields) + "\n"
            break
    split_path.write_text("".join(lines), encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises((SplitGroupingMismatch, SplitEligibilityMismatch, SplitUpstreamMismatch)):
        verify_frozen_split(workspace)


def test_tamper_excluded_record_102_inserted_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    lines = split_path.read_text(encoding="utf-8").splitlines(keepends=True)
    injected = lines[1].replace("100,MITDB_P100", "102,MITDB_P102")
    split_path.write_text("".join([lines[0], injected, *lines[1:]]), encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises((SplitEligibilityMismatch, SplitUpstreamMismatch)):
        verify_frozen_split(workspace)


def test_tamper_eligible_record_deleted_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    lines = split_path.read_text(encoding="utf-8").splitlines(keepends=True)
    remaining = [lines[0], *[line for line in lines[1:] if not line.startswith("100,")]]
    split_path.write_text("".join(remaining), encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises((SplitEligibilityMismatch, SplitUpstreamMismatch)):
        verify_frozen_split(workspace)


def test_tamper_duplicate_row_added_detected(tmp_path: Path) -> None:
    """A duplicate row for the same record under a *different* partition is a patient/record
    overlap; caught even with a forged hash."""
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    lines = split_path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = lines[0].rstrip("\n").split(",")
    partition_index = header.index("partition")
    original = lines[1].rstrip("\n").split(",")
    duplicate_fields = list(original)
    duplicate_fields[partition_index] = (
        "VALIDATION" if original[partition_index] != "VALIDATION" else "CALIBRATION"
    )
    duplicate_line = ",".join(duplicate_fields) + "\n"
    mutated_text = "".join([lines[0], lines[1], duplicate_line, *lines[2:]])
    split_path.write_text(mutated_text, encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises((SplitPatientOverlap, SplitEligibilityMismatch, SplitUpstreamMismatch)):
        verify_frozen_split(workspace)


def test_tamper_invalid_partition_name_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    text = split_path.read_text(encoding="utf-8")
    for canonical in PARTITIONS:
        if f",{canonical}," in text:
            text = text.replace(f",{canonical},", ",HOLDOUT,", 1)
            break
    split_path.write_text(text, encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises((SplitGroupingMismatch, SplitUpstreamMismatch)):
        verify_frozen_split(workspace)


def test_tamper_wrong_split_id_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    text = split_path.read_text(encoding="utf-8").replace("MITDB_SPLIT_V1", "MITDB_SPLIT_V2")
    split_path.write_text(text, encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises((SplitUpstreamMismatch, SplitHashMismatch)):
        verify_frozen_split(workspace)


def test_tamper_wrong_split_seed_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    text = split_path.read_text(encoding="utf-8").replace("20260927", "1")
    split_path.write_text(text, encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises(SplitUpstreamMismatch):
        verify_frozen_split(workspace)


def test_tamper_wrong_label_map_id_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    text = split_path.read_text(encoding="utf-8").replace("AAMI_SVF_MAP_V1", "AAMI_SVF_MAP_V2")
    split_path.write_text(text, encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises(SplitUpstreamMismatch):
        verify_frozen_split(workspace)


def test_tamper_wrong_lead_policy_id_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    text = split_path.read_text(encoding="utf-8").replace(
        "MITDB_EXACT_MLII_V1", "MITDB_EXACT_MLII_V2"
    )
    split_path.write_text(text, encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises(SplitUpstreamMismatch):
        verify_frozen_split(workspace)


def test_tamper_has_svf_event_altered_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    lines = split_path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = lines[0].rstrip("\n").split(",")
    svf_index = header.index("has_svf_event")
    for index in range(1, len(lines)):
        fields = lines[index].rstrip("\n").split(",")
        if fields[0] == "100" and fields[svf_index] == "TRUE":
            fields[svf_index] = "FALSE"
            lines[index] = ",".join(fields) + "\n"
            break
    split_path.write_text("".join(lines), encoding="utf-8")
    _forge_lock_hash(tmp_path, "split_sha256", "manifests/splits/MITDB_SPLIT_V1.csv")
    with pytest.raises(SplitGroupingMismatch):
        verify_frozen_split(workspace)


def test_tamper_split_hash_changed_without_forging_lock_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    split_path = workspace / "manifests/splits/MITDB_SPLIT_V1.csv"
    split_path.write_text(split_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SplitHashMismatch):
        verify_frozen_split(workspace)


def test_tamper_upstream_map_hash_changed_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    map_path = workspace / "manifests/labels/AAMI_SVF_MAP_V1.yaml"
    map_path.write_text(map_path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    with pytest.raises(SplitHashMismatch):
        verify_frozen_split(workspace)


def test_tamper_eligible_manifest_hash_changed_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    eligible_path = workspace / "manifests/datasets/mitdb_mlii_records.csv"
    eligible_path.write_text(eligible_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SplitHashMismatch):
        verify_frozen_split(workspace)


def test_tamper_missing_lock_file_detected(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    (workspace / "manifests/splits/MITDB_SPLIT_V1.lock.json").unlink()
    with pytest.raises(SplitHashMismatch):
        verify_frozen_split(workspace)


def test_original_committed_split_hash_unchanged_by_this_entire_test_module() -> None:
    """Defense in depth: prove the real repository split file was never touched by any test
    in this module (all tampering happens in tmp_path copies)."""
    from nhm.hashing import hash_file

    lock = json.loads((SPLIT_DIR / "MITDB_SPLIT_V1.lock.json").read_text(encoding="utf-8"))
    assert hash_file(SPLIT_DIR / "MITDB_SPLIT_V1.csv") == lock["split_sha256"]
