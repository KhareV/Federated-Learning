"""Offline checks against the committed INCART manifest artifacts."""

from pathlib import Path

import yaml

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests/datasets/incart_v1.yaml"
FILES_MANIFEST = ROOT / "manifests/datasets/incart_v1_files.csv"
ELIGIBLE_MANIFEST = ROOT / "manifests/datasets/incart_lead_ii_records.csv"
EXCLUSION_MANIFEST = ROOT / "manifests/datasets/incart_lead_ii_exclusions.csv"
PATIENT_MAP = ROOT / "manifests/datasets/incart_patient_map.csv"


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_identity_and_policy_are_locked() -> None:
    manifest = _manifest()
    assert manifest["dataset_id"] == "INCART"
    assert manifest["version"] == "1.0.0"
    assert manifest["provider"] == "PhysioNet"
    assert manifest["doi"] == "10.13026/C2V88N"
    assert manifest["lead_policy_id"] == "INCART_EXACT_II_V1"
    assert manifest["lead_name_required"] == "II"
    assert manifest["sampling_rate_hz"] == 257
    assert manifest["source_channel_count"] == 12
    assert manifest["raw_data_committed"] is False
    assert manifest["role"] == "LOCKED_EXTERNAL_ECG_EVALUATION"
    assert manifest["owning_task"] == "T020"


def test_manifest_distinguishes_documented_source_from_observed_validation() -> None:
    manifest = _manifest()
    assert manifest["documented_source"]["record_count"] == 75
    assert manifest["documented_source"]["source_patient_count"] == 32
    assert manifest["observed_local_validation"]["records_in_RECORDS"] == 75
    assert manifest["observed_local_validation"]["unique_source_patient_ids_observed"] == 32


def test_manifest_does_not_claim_split_labels_or_external_metrics() -> None:
    manifest = _manifest()
    text = yaml.safe_dump(manifest).casefold()
    for forbidden in (
        "split",
        "train",
        "aami_svf_map",
        "aami_svf_window",
        "auprc",
        "sensitivity",
        "specificity",
    ):
        assert forbidden not in text


def test_eligible_and_excluded_counts_are_consistent() -> None:
    manifest = _manifest()
    eligible_rows = read_csv(ELIGIBLE_MANIFEST)
    exclusion_rows = read_csv(EXCLUSION_MANIFEST)
    assert manifest["eligible_record_count"] == len(eligible_rows)
    assert manifest["excluded_record_count"] == len(exclusion_rows)
    assert len(eligible_rows) + len(exclusion_rows) == 75


def test_files_manifest_reports_all_hashes_verified() -> None:
    rows = read_csv(FILES_MANIFEST)
    assert len(rows) == 75 * 3
    assert all(row["verified"] == "True" for row in rows)
    assert all(row["official_sha256"] == row["local_sha256"] for row in rows)


def test_patient_map_covers_every_record_with_no_fabricated_ids() -> None:
    rows = read_csv(PATIENT_MAP)
    assert len(rows) == 75
    for row in rows:
        assert row["source_patient_id"] != ""
        assert row["source_patient_id"].isdigit()
    unique_ids = {row["source_patient_id"] for row in rows}
    assert len(unique_ids) == 32


def test_eligible_manifest_has_no_split_or_label_fields() -> None:
    import csv

    with ELIGIBLE_MANIFEST.open(newline="", encoding="utf-8") as handle:
        fieldnames = set(csv.DictReader(handle).fieldnames or [])
    forbidden_fields = {"split", "partition", "aami_class", "target", "label"}
    assert not (forbidden_fields & fieldnames)


def test_exclusion_manifest_reasons_are_header_derived_not_performance_based() -> None:
    rows = read_csv(EXCLUSION_MANIFEST)
    allowed_reasons = {
        "EXCLUDE_NO_EXACT_II",
        "EXCLUDE_AMBIGUOUS_MULTIPLE_II",
        "EXCLUDE_MALFORMED_HEADER",
    }
    for row in rows:
        assert row["reason"] in allowed_reasons
        assert row["source_policy"] == "INCART_EXACT_II_V1"
