"""Integration checks for the committed MITDB_SPLIT_V1 draft artifacts against the real,
already-generated T006 eligibility manifest -- offline, reads generated files only."""

import csv
import json
from itertools import combinations
from pathlib import Path

import yaml

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "manifests/splits"
PARTITIONS = ("TRAIN", "VALIDATION", "CALIBRATION", "INTERNAL_TEST")


def _split_rows() -> list[dict[str, str]]:
    return read_csv(SPLIT_DIR / "MITDB_SPLIT_V1.csv")


def _groups_rows() -> list[dict[str, str]]:
    return read_csv(SPLIT_DIR / "mitdb_groups.csv")


def _strata_rows() -> list[dict[str, str]]:
    return read_csv(SPLIT_DIR / "mitdb_patient_strata.csv")


def test_eligibility_closure_matches_frozen_t006_manifest() -> None:
    eligible_records_path = ROOT / "manifests/datasets/mitdb_mlii_records.csv"
    eligible_ids = {row["record_id"] for row in read_csv(eligible_records_path)}
    split_ids = {row["record_id"] for row in _split_rows()}
    assert split_ids == eligible_ids
    assert "102" not in split_ids
    assert "104" not in split_ids


def test_201_and_202_are_grouped_before_allocation() -> None:
    rows = {row["record_id"]: row for row in _split_rows()}
    assert rows["201"]["participant_group_id"] == "MITDB_P201_202"
    assert rows["202"]["participant_group_id"] == "MITDB_P201_202"
    assert rows["201"]["partition"] == rows["202"]["partition"]
    assert rows["201"]["group_record_count"] == "2"
    assert rows["202"]["group_record_count"] == "2"


def test_excluded_records_present_in_groups_csv_but_absent_from_split() -> None:
    groups = {row["record_id"]: row for row in _groups_rows()}
    assert groups["102"]["core_channel_eligible"] == "FALSE"
    assert groups["104"]["core_channel_eligible"] == "FALSE"
    split_ids = {row["record_id"] for row in _split_rows()}
    assert "102" not in split_ids
    assert "104" not in split_ids


def test_record_count_and_patient_group_count_are_distinct() -> None:
    split_rows = _split_rows()
    assert len(split_rows) == 46
    unique_groups = {row["participant_group_id"] for row in split_rows}
    assert len(unique_groups) == 45
    assert len(split_rows) != len(unique_groups)


def test_complete_group_assignment_no_missing_duplicate_or_multi_partition() -> None:
    split_rows = _split_rows()
    group_to_partitions: dict[str, set[str]] = {}
    for row in split_rows:
        group_to_partitions.setdefault(row["participant_group_id"], set()).add(row["partition"])
    strata_group_ids = {row["participant_group_id"] for row in _strata_rows()}
    assert set(group_to_partitions) == strata_group_ids
    assert all(len(partitions) == 1 for partitions in group_to_partitions.values())


def test_zero_patient_overlap_across_all_six_partition_pairs() -> None:
    split_rows = _split_rows()
    groups_by_partition: dict[str, set[str]] = {partition: set() for partition in PARTITIONS}
    for row in split_rows:
        groups_by_partition[row["partition"]].add(row["participant_group_id"])
    pairs = list(combinations(PARTITIONS, 2))
    assert len(pairs) == 6
    for left, right in pairs:
        assert groups_by_partition[left] & groups_by_partition[right] == set()


def test_partition_patient_quotas_sum_to_eligible_patient_group_count() -> None:
    report = json.loads((ROOT / "reports/t009/split_generation.json").read_text(encoding="utf-8"))
    quotas = report["partition_patient_quotas"]
    assert sum(quotas.values()) == report["eligible_patient_group_count"] == 45
    split_rows = _split_rows()
    actual_counts: dict[str, set[str]] = {partition: set() for partition in PARTITIONS}
    for row in split_rows:
        actual_counts[row["partition"]].add(row["participant_group_id"])
    for partition in PARTITIONS:
        assert len(actual_counts[partition]) == quotas[partition]


def test_stratification_variable_is_has_svf_event_and_matches_strata_file() -> None:
    strata = {row["participant_group_id"]: row["has_svf_event"] for row in _strata_rows()}
    for row in _split_rows():
        assert row["has_svf_event"] == strata[row["participant_group_id"]]


def test_partition_roles_manifest_declares_locked_usage_rules() -> None:
    roles = yaml.safe_load((SPLIT_DIR / "partition_roles_v1.yaml").read_text(encoding="utf-8"))
    assert roles["partitions"]["INTERNAL_TEST"]["forbidden"] == [
        "all tuning", "all fitting", "threshold choice", "architecture choice",
    ]
    assert "calibration fitting" in roles["partitions"]["VALIDATION"]["forbidden"]
    assert "model training" in roles["partitions"]["CALIBRATION"]["forbidden"]
    assert roles["partitions"]["TRAIN"]["forbidden"] == []


def test_split_yaml_records_frozen_map_and_lead_policy_ids() -> None:
    split_yaml = yaml.safe_load((SPLIT_DIR / "MITDB_SPLIT_V1.yaml").read_text(encoding="utf-8"))
    assert split_yaml["label_map_id"] == "AAMI_SVF_MAP_V1"
    assert split_yaml["lead_policy_id"] == "MITDB_EXACT_MLII_V1"
    assert split_yaml["split_status"] == "DRAFT_VALIDATED"
    assert split_yaml["freeze_status"] == "NOT_FROZEN"
    assert split_yaml["target_proportions"] == {
        "TRAIN": 0.60, "VALIDATION": 0.15, "CALIBRATION": 0.10, "INTERNAL_TEST": 0.15,
    }


def test_class_coverage_reports_patient_level_not_window_level() -> None:
    with (ROOT / "reports/t009/class_coverage.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["partition"] for row in rows} == set(PARTITIONS)
    assert sum(int(row["patient_count"]) for row in rows) == 45
    for row in rows:
        assert int(row["has_svf_patient_count"]) + int(row["no_svf_patient_count"]) == int(
            row["patient_count"]
        )
    assert "window" not in (ROOT / "reports/t009/class_coverage.csv").read_text().casefold()


def test_split_generation_report_distinguishes_records_and_patients() -> None:
    report = json.loads((ROOT / "reports/t009/split_generation.json").read_text(encoding="utf-8"))
    assert report["eligible_record_count"] == 46
    assert report["eligible_patient_group_count"] == 45
    assert report["partition_record_counts"]["VALIDATION"] == 8
    assert report["partition_patient_counts"]["VALIDATION"] == 7
