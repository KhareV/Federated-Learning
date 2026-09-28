"""Offline checks for the G2/G3 gate-evidence index files.

The gate registry's G2/G3 rows declare generic required_artifacts paths
(reports/data/validation_report.json, manifests/datasets/channel_exclusions.csv) inherited
from the v2.2-derived registry. These are thin indexes over the authoritative per-dataset
reports in reports/t006/ and reports/t007/, not a duplicate validation implementation.
"""

import json
from pathlib import Path

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_REPORT = ROOT / "reports/data/validation_report.json"
CHANNEL_EXCLUSIONS = ROOT / "manifests/datasets/channel_exclusions.csv"
ACQUISITION_AUDIT = ROOT / "reports/data/acquisition_audit.json"


def test_validation_report_indexes_all_four_datasets() -> None:
    report = json.loads(VALIDATION_REPORT.read_text(encoding="utf-8"))
    assert set(report["index_of"]) == {"MITDB", "INCART", "NSTDB", "BIDMC"}
    assert set(report["status_by_dataset"]) == {"MITDB", "INCART", "NSTDB", "BIDMC"}
    assert all(status == "PASS" for status in report["status_by_dataset"].values())
    assert report["overall_status"] == "PASS"


def test_validation_report_references_real_reports_not_duplicated_content() -> None:
    report = json.loads(VALIDATION_REPORT.read_text(encoding="utf-8"))
    for relative_path in report["index_of"].values():
        assert (ROOT / relative_path).exists()


def test_channel_exclusions_combines_mitdb_and_incart_with_dataset_id() -> None:
    """MITDB (2-lead subset) has real exclusions (102/104 lack exact MLII); INCART (12-lead,
    always carries exact II) legitimately has zero -- both are correct, not a bug."""
    rows = read_csv(CHANNEL_EXCLUSIONS)
    assert set(rows[0].keys()) >= {"dataset_id", "record_id", "reason", "source_policy"}
    assert {row["dataset_id"] for row in rows} <= {"MITDB", "INCART"}
    mitdb_rows = [row for row in rows if row["dataset_id"] == "MITDB"]
    incart_rows = [row for row in rows if row["dataset_id"] == "INCART"]
    assert {row["record_id"] for row in mitdb_rows} == {"102", "104"}
    assert incart_rows == []
    assert all(row["source_policy"] == "MITDB_EXACT_MLII_V1" for row in mitdb_rows)


def test_acquisition_audit_indexes_all_four_datasets_with_exact_versions_and_licenses() -> None:
    audit = json.loads(ACQUISITION_AUDIT.read_text(encoding="utf-8"))
    assert set(audit["index_of"]) == {"MITDB", "INCART", "NSTDB", "BIDMC"}
    assert audit["overall_status"] == "PASS"
    for dataset_id, summary in audit["summary_by_dataset"].items():
        assert summary["version"] == "1.0.0", dataset_id
        assert summary["license"] == "Open Data Commons Attribution License v1.0", dataset_id
        assert summary["all_files_hash_verified"] is True, dataset_id
        assert summary["doi"].startswith("10.13026/"), dataset_id


def test_acquisition_audit_references_real_reports_not_duplicated_content() -> None:
    audit = json.loads(ACQUISITION_AUDIT.read_text(encoding="utf-8"))
    for relative_path in audit["index_of"].values():
        assert (ROOT / relative_path).exists()
