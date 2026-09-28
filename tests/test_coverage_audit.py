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


def test_change_control_distinguishes_interface_and_scientific_changes() -> None:
    assert classify_change("Correct an internal parsing bug") == "A"
    assert classify_change("Move an API file path") == "B"
    assert classify_change("Change MIT-BIH lead to arbitrary best-performing lead") == "C"
    assert classify_change("Change the window to 8 seconds") == "C"
    assert classify_change("Replace AAMI_SVF_MAP_V1") == "C"


def test_reference_ranges_expand_without_hiding_unknown_identifiers() -> None:
    assert expand_refs("T002-T004;T010") == ["T002", "T003", "T004", "T010"]
    assert expand_refs("E01-E03") == ["E01", "E02", "E03"]
