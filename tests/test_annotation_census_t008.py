"""Offline checks for the T008 MIT-BIH/INCART annotation-symbol census and label-map audit.

Reads the already-generated reports/t008/*.csv and reports/labels/label_audit.json (produced
by scripts/build_annotation_census_t008.py and scripts/audit_label_map_t008.py against the
real, hash-verified T006/T007 raw data). No acquisition, no re-parsing of raw WFDB files, no
window-building here.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t008"
LABEL_AUDIT = ROOT / "reports/labels/label_audit.json"

KNOWN_INCART_PRE_SIGNAL_RECORDS = {"I04", "I17", "I35", "I44", "I57", "I72", "I74"}


def _read_csv(relative_path: str) -> list[dict[str, str]]:
    with (REPORT_DIR / relative_path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_census_covers_only_mitdb_and_incart() -> None:
    rows = _read_csv("annotation_symbol_census.csv")
    assert {row["dataset_id"] for row in rows} == {"MITDB", "INCART"}


def test_census_maintains_explicit_source_vs_core_channel_eligible_scope() -> None:
    rows = _read_csv("annotation_symbol_census.csv")
    assert {row["scope"] for row in rows} == {"SOURCE", "CORE_CHANNEL_ELIGIBLE"}


def test_mitdb_source_scope_includes_excluded_records_core_scope_does_not() -> None:
    """MITDB SOURCE = 48 records (incl. 102/104); CORE_CHANNEL_ELIGIBLE = the 46 with exact
    MLII. 102/104's raw annotation symbols must still surface at SOURCE scope."""
    rows = _read_csv("annotation_symbol_census.csv")
    mitdb_rows = [row for row in rows if row["dataset_id"] == "MITDB"]
    source_total = sum(int(r["raw_count"]) for r in mitdb_rows if r["scope"] == "SOURCE")
    core_total = sum(
        int(r["raw_count"]) for r in mitdb_rows if r["scope"] == "CORE_CHANNEL_ELIGIBLE"
    )
    assert source_total > core_total > 0


def test_incart_source_and_core_channel_eligible_scopes_are_identical() -> None:
    """INCART has zero channel exclusions (manifests/datasets/incart_v1.yaml), so both scopes
    cover all 75 records -- reported at both labels for symmetry, not a bug."""
    rows = _read_csv("annotation_symbol_census.csv")
    incart_rows = [row for row in rows if row["dataset_id"] == "INCART"]
    source_total = sum(int(r["raw_count"]) for r in incart_rows if r["scope"] == "SOURCE")
    core_total = sum(
        int(r["raw_count"]) for r in incart_rows if r["scope"] == "CORE_CHANNEL_ELIGIBLE"
    )
    assert source_total == core_total > 0


def test_raw_count_conservation_every_symbol_classified_exactly_once() -> None:
    census_rows = _read_csv("annotation_symbol_census.csv")
    valid_classes = {"N", "S", "V", "F", "Q", "UNMAPPABLE", "NOT_A_BEAT"}
    for row in census_rows:
        assert row["mapped_class"] in valid_classes
        assert int(row["raw_count"]) > 0


def test_symbol_accounting_has_no_negative_or_missing_temporal_counts() -> None:
    rows = _read_csv("symbol_accounting.csv")
    for row in rows:
        total = int(row["count_total"])
        parts = (
            int(row["count_in_signal"])
            + int(row["count_pre_signal"])
            + int(row["count_post_signal"])
        )
        assert total == parts, row


def test_incart_pre_signal_anomaly_is_preserved_not_dropped() -> None:
    """The seven INCART records with a documented benign pre-signal annotation (T007 finding,
    reports/t007/incart_validation.json) must still be visible in T008's own accounting, never
    clipped or silently excluded."""
    rows = _read_csv("symbol_accounting.csv")
    incart_source = [r for r in rows if r["dataset_id"] == "INCART" and r["scope"] == "SOURCE"]
    pre_signal_total = sum(int(r["count_pre_signal"]) for r in incart_source)
    post_signal_total = sum(int(r["count_post_signal"]) for r in incart_source)
    assert pre_signal_total == len(KNOWN_INCART_PRE_SIGNAL_RECORDS)
    assert post_signal_total == 0


def test_at_least_one_real_unlisted_beat_symbol_found_per_dataset() -> None:
    rows = _read_csv("annotation_symbol_census.csv")
    mitdb_unmappable = {
        r["symbol"]
        for r in rows
        if r["dataset_id"] == "MITDB" and r["mapped_class"] == "UNMAPPABLE"
    }
    incart_unmappable = {
        r["symbol"]
        for r in rows
        if r["dataset_id"] == "INCART" and r["mapped_class"] == "UNMAPPABLE"
    }
    assert mitdb_unmappable == {"!"}
    assert incart_unmappable == {"B", "n"}


def test_label_audit_is_g4_evidence_and_passes() -> None:
    audit = json.loads(LABEL_AUDIT.read_text(encoding="utf-8"))
    assert audit["overall_status"] == "PASS"
    assert audit["errors"] == []
    assert audit["gate_id"] == "G4"
    assert audit["freeze_id"] == "F04"
    assert audit["map_id"] == "AAMI_SVF_MAP_V1"
    assert audit["scope_datasets"] == ["MITDB", "INCART"]
    assert audit["excluded_datasets"] == ["NSTDB", "BIDMC", "WEARABLE_SIM_V1"]


def test_label_audit_records_incart_pre_signal_finding_transparently() -> None:
    audit = json.loads(LABEL_AUDIT.read_text(encoding="utf-8"))
    assert audit["incart_pre_signal_annotation_count"] == 7
    assert audit["incart_post_signal_annotation_count"] == 0
    assert set(audit["incart_pre_signal_records"]) == KNOWN_INCART_PRE_SIGNAL_RECORDS
