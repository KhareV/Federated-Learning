"""Offline checks against the committed NSTDB manifest artifacts."""

from pathlib import Path

import yaml

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests/datasets/nstdb_v1.yaml"
RECORDS_MANIFEST = ROOT / "manifests/datasets/nstdb_records.csv"
FILES_MANIFEST = ROOT / "manifests/datasets/nstdb_v1_files.csv"


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_identity_and_role_are_locked() -> None:
    manifest = _manifest()
    assert manifest["dataset_id"] == "NSTDB"
    assert manifest["version"] == "1.0.0"
    assert manifest["provider"] == "PhysioNet"
    assert manifest["doi"] == "10.13026/C2HS3T"
    assert manifest["role"] == "NOISE_ROBUSTNESS"
    assert manifest["owning_task"] == "T019"
    assert manifest["raw_data_committed"] is False


def test_records_manifest_distinguishes_stress_and_noise_roles() -> None:
    rows = read_csv(RECORDS_MANIFEST)
    assert len(rows) == 15
    stress_rows = [row for row in rows if row["role"] == "STRESS_ECG"]
    noise_rows = [row for row in rows if row["role"] == "PURE_NOISE"]
    assert len(stress_rows) == 12
    assert len(noise_rows) == 3
    assert {row["record_id"] for row in noise_rows} == {"bw", "em", "ma"}


def test_snr_identities_match_source_definitions() -> None:
    rows = {row["record_id"]: row for row in read_csv(RECORDS_MANIFEST)}
    expected_snr = {
        "118e24": "24",
        "118e18": "18",
        "118e12": "12",
        "118e06": "6",
        "118e00": "0",
        "118e_6": "-6",
        "119e24": "24",
        "119e_6": "-6",
    }
    for record_id, snr in expected_snr.items():
        assert rows[record_id]["snr_db"] == snr
        assert rows[record_id]["clean_source_record"] in ("118", "119")


def test_noise_types_match_source_definitions() -> None:
    rows = {row["record_id"]: row for row in read_csv(RECORDS_MANIFEST)}
    assert rows["bw"]["noise_type"] == "baseline_wander"
    assert rows["em"]["noise_type"] == "electrode_motion"
    assert rows["ma"]["noise_type"] == "muscle_artifact"


def test_pure_noise_records_have_no_annotation_by_design() -> None:
    rows = {row["record_id"]: row for row in read_csv(RECORDS_MANIFEST)}
    for record_id in ("bw", "em", "ma"):
        assert rows[record_id]["annotation_present"] == "False"


def test_stress_records_have_annotations() -> None:
    rows = read_csv(RECORDS_MANIFEST)
    for row in rows:
        if row["role"] == "STRESS_ECG":
            assert row["annotation_present"] == "True"


def test_files_manifest_reports_all_hashes_verified() -> None:
    rows = read_csv(FILES_MANIFEST)
    assert len(rows) == 42  # 12 stress * 3 files + 3 noise * 2 files
    assert all(row["verified"] == "True" for row in rows)


def test_manifest_does_not_claim_robustness_experiment_results() -> None:
    manifest = _manifest()
    text = yaml.safe_dump(manifest).casefold()
    for forbidden in ("auprc", "sensitivity", "specificity", "accuracy"):
        assert forbidden not in text
