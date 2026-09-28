from pathlib import Path

from nhm.coverage import audit_registries, classify_change, expand_refs

ROOT = Path(__file__).resolve().parents[1]


def test_full_registry_audit_passes_with_zero_coverage_gaps() -> None:
    result = audit_registries(ROOT)
    assert result["status"] == "PASS", result["errors"]
    assert result["task_count"] == 36
    assert result["gate_count"] == 23
    assert result["mandatory_requirement_count"] == 80
    assert result["unmapped_requirement_count"] == 0
    assert result["invalid_task_reference_count"] == 0
    assert result["invalid_gate_reference_count"] == 0
    assert result["orphan_task_count"] == 0
    assert result["semantic_task_mapping_error_count"] == 0
    assert result["remaining_derived_task_definition_count"] == 0


def test_blocked_hardware_task_does_not_trip_future_task_guard() -> None:
    """The coverage audit must not treat T004=BLOCKED as preventing T005=PASS merely
    because T004's numeric task ID is earlier (T005 execution instructions Section 37)."""
    from nhm.coverage import read_csv

    result = audit_registries(ROOT)
    assert result["status"] == "PASS", result["errors"]
    tasks = {row["task_id"]: row for row in read_csv(ROOT / "manifests/task_registry_v1.csv")}
    assert tasks["T004"]["status"] == "BLOCKED"
    assert tasks["T005"]["status"] == "PASS"
    assert not any("future tasks falsely advanced" in error for error in result["errors"])


def test_g1_hardware_block_does_not_prevent_g2_g3_dataset_gates_passing() -> None:
    """G1 (hardware/data contract) stays NOT_STARTED while G2/G3 (public-dataset acquisition
    and validation, owned by T006+T007) legitimately close ahead of it -- an explicit
    allowlist (APPROVED_PASSED_GATES), not a numeric ordering assumption."""
    from nhm.coverage import read_csv

    result = audit_registries(ROOT)
    assert result["status"] == "PASS", result["errors"]
    gates = {row["gate_id"]: row for row in read_csv(ROOT / "manifests/gate_registry_v1.csv")}
    assert gates["G1"]["status"] == "NOT_STARTED"
    assert gates["G2"]["status"] == "PASS"
    assert gates["G3"]["status"] == "PASS"
    assert gates["G4"]["status"] == "NOT_STARTED"
    assert not any("future gates falsely advanced" in error for error in result["errors"])


def test_change_control_distinguishes_interface_and_scientific_changes() -> None:
    assert classify_change("Correct an internal parsing bug") == "A"
    assert classify_change("Move an API file path") == "B"
    assert classify_change("Change MIT-BIH lead to arbitrary best-performing lead") == "C"
    assert classify_change("Change the window to 8 seconds") == "C"
    assert classify_change("Replace AAMI_SVF_MAP_V1") == "C"


def test_reference_ranges_expand_without_hiding_unknown_identifiers() -> None:
    assert expand_refs("T002-T004;T010") == ["T002", "T003", "T004", "T010"]
    assert expand_refs("E01-E03") == ["E01", "E02", "E03"]


def test_task_reconciliation_records_every_corrected_task() -> None:
    from nhm.coverage import read_csv

    rows = read_csv(ROOT / "reports/t002/task_registry_reconciliation.csv")
    assert {row["task_id"] for row in rows} == {
        f"T{number:03d}" for number in range(1, 37)
    }
    assert all(row["resolution"] == "REPLACED_WITH_EXECUTION_PLAN_VALUE" for row in rows)
    assert all(row["scientific_impact"].startswith("NONE") for row in rows)
