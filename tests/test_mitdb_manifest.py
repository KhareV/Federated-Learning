"""Offline checks against the committed MIT-BIH manifest artifacts.

No network access: these tests only read files already committed to the repository by
scripts/validate_mitdb_t006.py (run once against the real acquired dataset).
"""

import csv
from pathlib import Path

import yaml

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests/datasets/mitdb_v1.yaml"
FILES_MANIFEST = ROOT / "manifests/datasets/mitdb_v1_files.csv"
ELIGIBLE_MANIFEST = ROOT / "manifests/datasets/mitdb_mlii_records.csv"
EXCLUSION_MANIFEST = ROOT / "manifests/datasets/mitdb_mlii_exclusions.csv"


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_identity_and_policy_are_locked() -> None:
    manifest = _manifest()
    assert manifest["dataset_id"] == "MITDB"
    assert manifest["version"] == "1.0.0"
    assert manifest["provider"] == "PhysioNet"
    assert manifest["doi"] == "10.13026/C2F305"
    assert manifest["lead_policy_id"] == "MITDB_EXACT_MLII_V1"
    assert manifest["lead_name_required"] == "MLII"
    assert manifest["sampling_rate_hz"] == 360
    assert manifest["source_channel_count"] == 2
    assert manifest["raw_data_committed"] is False


def test_manifest_distinguishes_documented_source_from_observed_validation() -> None:
    manifest = _manifest()
    assert "documented_source" in manifest
    assert "observed_local_validation" in manifest
    assert manifest["documented_source"]["record_count"] == 48
    assert manifest["documented_source"]["subject_count"] == 47
    assert manifest["observed_local_validation"]["records_in_RECORDS"] == 48


def test_manifest_does_not_claim_patient_split_or_labels() -> None:
    manifest = _manifest()
    text = yaml.safe_dump(manifest).casefold()
    for forbidden in ("split", "train", "calibration", "aami_svf_map", "aami_svf_window"):
        assert forbidden not in text


def test_manifest_eligible_and_excluded_counts_are_consistent() -> None:
    manifest = _manifest()
    eligible_rows = read_csv(ELIGIBLE_MANIFEST)
    exclusion_rows = read_csv(EXCLUSION_MANIFEST)
    assert manifest["eligible_record_count"] == len(eligible_rows)
    assert manifest["excluded_record_count"] == len(exclusion_rows)
    assert len(eligible_rows) + len(exclusion_rows) == 48


def test_files_manifest_reports_all_hashes_verified() -> None:
    rows = read_csv(FILES_MANIFEST)
    assert len(rows) == 48 * 3
    assert all(row["verified"] == "True" for row in rows)
    assert all(row["official_sha256"] == row["local_sha256"] for row in rows)


def test_eligible_manifest_has_no_split_or_label_fields() -> None:
    with ELIGIBLE_MANIFEST.open(newline="", encoding="utf-8") as handle:
        fieldnames = set(csv.DictReader(handle).fieldnames or [])
    forbidden_fields = {"split", "partition", "aami_class", "target", "label"}
    assert not (forbidden_fields & fieldnames)


def test_exclusion_manifest_reasons_are_header_derived_not_performance_based() -> None:
    rows = read_csv(EXCLUSION_MANIFEST)
    allowed_reasons = {
        "EXCLUDE_NO_EXACT_MLII",
        "EXCLUDE_AMBIGUOUS_MULTIPLE_MLII",
        "EXCLUDE_MALFORMED_HEADER",
    }
    for row in rows:
        assert row["reason"] in allowed_reasons
        assert row["source_policy"] == "MITDB_EXACT_MLII_V1"


def test_record_102_and_104_are_excluded_by_header_not_hardcoded_list() -> None:
    """Cross-check only: the documented no-MLII records must appear in the exclusion list,
    but the exclusion mechanism itself (datasets.mitdb.select_mlii_channel) never hard-codes
    these IDs -- see test_mitdb_lead_policy.py::test_no_index_based_fallback_in_source and the
    absence of any literal record-ID list in datasets/mitdb.py."""
    rows = {row["record_id"]: row for row in read_csv(EXCLUSION_MANIFEST)}
    for record_id in ("102", "104"):
        assert record_id in rows
        assert "MLII" not in rows[record_id]["signal_names"].split(";")

    source = (ROOT / "datasets/mitdb.py").read_text(encoding="utf-8")
    assert '"102"' not in source
    assert '"104"' not in source
