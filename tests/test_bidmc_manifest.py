"""Offline checks against the committed BIDMC manifest artifacts."""

from pathlib import Path

import yaml

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests/datasets/bidmc_v1.yaml"
CHANNEL_MANIFEST = ROOT / "manifests/datasets/bidmc_channel_availability.csv"
FILES_MANIFEST = ROOT / "manifests/datasets/bidmc_v1_files.csv"


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_identity_and_role_are_locked() -> None:
    manifest = _manifest()
    assert manifest["dataset_id"] == "BIDMC"
    assert manifest["version"] == "1.0.0"
    assert manifest["provider"] == "PhysioNet"
    assert manifest["doi"] == "10.13026/C2208R"
    assert manifest["role"] == "MULTIMODAL_ENGINEERING_CONTEXT"
    assert manifest["raw_data_committed"] is False
    assert set(manifest["excluded_by_design"]) >= {".breath", "bidmc_csv/*", "bidmc_data.mat"}


def test_waveform_and_numeric_rates_are_locked() -> None:
    manifest = _manifest()
    assert manifest["waveform_sampling_rate_hz"] == 125
    assert manifest["numerics_sampling_rate_hz"] == 1


def test_channel_availability_manifest_covers_all_records() -> None:
    rows = read_csv(CHANNEL_MANIFEST)
    assert len(rows) == 53
    assert {row["record_id"] for row in rows} == {f"bidmc{n:02d}" for n in range(1, 54)}


def test_files_manifest_covers_exactly_waveform_and_numerics_no_breath_or_csv() -> None:
    rows = read_csv(FILES_MANIFEST)
    assert len(rows) == 53 * 4
    assert all(row["verified"] == "True" for row in rows)
    for row in rows:
        assert not row["relative_path"].endswith(".breath")
        assert "bidmc_csv" not in row["relative_path"]
        assert not row["relative_path"].endswith(".mat")


def test_manifest_never_claims_arrhythmia_labels() -> None:
    manifest = _manifest()
    text = yaml.safe_dump(manifest).casefold()
    for forbidden in ("aami", "arrhythmia_label", "svf_window"):
        assert forbidden not in text


def test_known_source_anomalies_are_documented_not_hidden() -> None:
    """T007 discovered a real malformed-gain header defect in bidmc19's SpO2 channel; this
    must remain visible in evidence, not silently swallowed."""
    import json

    validation = json.loads((ROOT / "reports/t007/bidmc_validation.json").read_text())
    assert "known_source_anomalies" in validation
