import json
from pathlib import Path

from nhm.coverage import CLAIM_BOUNDARY_IDS, read_csv, split_refs

ROOT = Path(__file__).resolve().parents[1]


def test_core_requirements_and_claim_boundaries_are_preserved() -> None:
    rows = read_csv(ROOT / "manifests/requirements_v22.csv")
    identifiers = {row["requirement_id"] for row in rows}
    assert {f"R{number:02d}" for number in range(1, 29)} <= identifiers
    assert identifiers >= CLAIM_BOUNDARY_IDS
    assert len(identifiers) == len(rows)


def test_every_mandatory_requirement_has_concrete_coverage() -> None:
    rows = read_csv(ROOT / "manifests/requirements_v22.csv")
    mandatory = [row for row in rows if row["mandatory"] == "TRUE"]
    required_fields = (
        "source_document",
        "source_version",
        "source_section",
        "source_page_or_locator",
        "implementation_tasks",
        "planned_files_or_modules",
        "validation_method",
        "acceptance_criterion",
        "gate_ids",
        "evidence_artifacts",
        "change_class",
    )
    assert len(rows) == 84
    assert len(mandatory) == 80
    assert all(all(row[field].strip() for field in required_fields) for row in mandatory)
    assert all(split_refs(row["implementation_tasks"]) for row in mandatory)
    assert all(split_refs(row["gate_ids"]) for row in mandatory)


def test_source_versions_and_out_of_scope_rows_are_explicit() -> None:
    rows = read_csv(ROOT / "manifests/requirements_v22.csv")
    assert all(
        row["source_version"] == ("2.2" if "Specification" in row["source_document"] else "1.0")
        for row in rows
    )
    excluded = [row for row in rows if row["status"] == "OUT_OF_SCOPE_BY_SPEC"]
    assert {row["requirement_id"] for row in excluded} == {
        "OOS01",
        "OOS02",
        "OOS03",
        "OOS04",
    }
    assert all(row["mandatory"] == "FALSE" for row in excluded)


def test_core_requirement_owners_match_execution_plan_coverage_matrix() -> None:
    rows = {
        row["requirement_id"]: row
        for row in read_csv(ROOT / "manifests/requirements_v22.csv")
    }
    snapshot = json.loads((ROOT / "manifests/task_packets_v1.json").read_text())
    expected = dict(snapshot["requirement_task_map"])
    expected["R27"] = ";".join(f"T{number:03d}" for number in range(1, 37))
    assert all(
        rows[requirement_id]["implementation_tasks"] == tasks
        for requirement_id, tasks in expected.items()
    )
