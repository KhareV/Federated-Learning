"""Offline tests for datasets/nstdb.py against tiny synthetic WFDB fixtures."""

from pathlib import Path

import numpy as np
import pytest
import wfdb

from datasets.nstdb import (
    PURE_NOISE,
    STRESS_ECG,
    classify_record_role,
    data_not_acquired_error,
    list_records,
    load_annotations_if_applicable,
    load_noise_record,
    load_stress_ecg,
    snr_for_record,
    validate_record,
)


def _write_record(
    directory: Path,
    record_id: str,
    *,
    sig_name: list[str],
    fs: int = 360,
    n_samples: int = 1000,
    ann_samples: list[int] | None = None,
) -> None:
    rng = np.random.default_rng(0)
    signal = rng.normal(size=(n_samples, len(sig_name)))
    wfdb.wrsamp(
        record_id,
        fs=fs,
        units=["mV"] * len(sig_name),
        sig_name=sig_name,
        p_signal=signal,
        fmt=["16"] * len(sig_name),
        write_dir=str(directory),
    )
    if ann_samples is not None:
        wfdb.wrann(
            record_id,
            "atr",
            sample=np.array(ann_samples),
            symbol=["N"] * len(ann_samples),
            write_dir=str(directory),
        )


def test_classify_stress_ecg_records() -> None:
    result = classify_record_role("118e24")
    assert result.role == STRESS_ECG
    assert result.clean_source_record == "118"
    assert result.snr_db == 24

    result = classify_record_role("119e_6")
    assert result.role == STRESS_ECG
    assert result.clean_source_record == "119"
    assert result.snr_db == -6


def test_classify_pure_noise_records() -> None:
    assert classify_record_role("bw").role == PURE_NOISE
    assert classify_record_role("bw").noise_type == "baseline_wander"
    assert classify_record_role("em").noise_type == "electrode_motion"
    assert classify_record_role("ma").noise_type == "muscle_artifact"
    assert classify_record_role("bw").snr_db is None


def test_unknown_record_naming_fails_classification_rather_than_guessing() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_NSTDB_RECORD_NAMING"):
        classify_record_role("unknown_record_123")
    with pytest.raises(ValueError, match="UNKNOWN_NSTDB_RECORD_NAMING"):
        classify_record_role("120e00")


def test_snr_for_record() -> None:
    assert snr_for_record("118e24") == 24
    assert snr_for_record("119e00") == 0
    assert snr_for_record("bw") is None


def test_data_not_acquired_error_when_records_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="NSTDB_DATA_NOT_ACQUIRED"):
        list_records(tmp_path)


def test_load_stress_ecg_succeeds_for_stress_record(tmp_path: Path) -> None:
    _write_record(
        tmp_path, "118e24", sig_name=["MLII", "V1"], n_samples=200, ann_samples=[10, 20]
    )
    signal = load_stress_ecg("118e24", tmp_path)
    assert signal.shape == (200, 2)


def test_load_stress_ecg_rejects_pure_noise_record(tmp_path: Path) -> None:
    _write_record(tmp_path, "bw", sig_name=["noise1", "noise2"], n_samples=200)
    with pytest.raises(ValueError, match="not a STRESS_ECG"):
        load_stress_ecg("bw", tmp_path)


def test_load_noise_record_succeeds_for_pure_noise(tmp_path: Path) -> None:
    _write_record(tmp_path, "em", sig_name=["noise1", "noise2"], n_samples=150)
    signal = load_noise_record("em", tmp_path)
    assert signal.shape == (150, 2)


def test_load_noise_record_rejects_stress_ecg_record(tmp_path: Path) -> None:
    _write_record(tmp_path, "119e12", sig_name=["MLII", "V1"], n_samples=150, ann_samples=[1])
    with pytest.raises(ValueError, match="not a PURE_NOISE"):
        load_noise_record("119e12", tmp_path)


def test_annotations_present_for_stress_ecg(tmp_path: Path) -> None:
    _write_record(
        tmp_path, "118e00", sig_name=["MLII", "V1"], n_samples=200, ann_samples=[5, 15]
    )
    annotation = load_annotations_if_applicable("118e00", tmp_path)
    assert annotation is not None
    assert list(annotation.sample) == [5, 15]


def test_annotations_absent_by_design_for_pure_noise_not_an_error(tmp_path: Path) -> None:
    _write_record(tmp_path, "ma", sig_name=["noise1", "noise2"], n_samples=200)
    assert load_annotations_if_applicable("ma", tmp_path) is None


def test_validate_record_stress_ecg_reports_role_and_snr(tmp_path: Path) -> None:
    _write_record(
        tmp_path, "118e18", sig_name=["MLII", "V1"], fs=360, n_samples=1000, ann_samples=[5, 15]
    )
    result = validate_record("118e18", tmp_path)
    assert result["role"] == STRESS_ECG
    assert result["clean_source_record"] == "118"
    assert result["snr_db"] == 18
    assert result["annotation_expected"] is True
    assert result["annotation_parsed"] is True
    assert result["annotation_count"] == 2
    assert result["errors"] == []


def test_validate_record_pure_noise_does_not_flag_missing_annotation_as_error(
    tmp_path: Path,
) -> None:
    _write_record(tmp_path, "bw", sig_name=["noise1", "noise2"], fs=360, n_samples=1000)
    result = validate_record("bw", tmp_path)
    assert result["role"] == PURE_NOISE
    assert result["noise_type"] == "baseline_wander"
    assert result["annotation_expected"] is False
    assert result["annotation_parsed"] is True
    assert result["errors"] == []


def test_validate_record_unknown_naming_reports_classification_error(tmp_path: Path) -> None:
    result = validate_record("totally_unknown", tmp_path)
    assert result["role"] is None
    assert any("classification" in error for error in result["errors"])


def test_data_not_acquired_message_names_the_acquisition_script() -> None:
    error = data_not_acquired_error(Path("data/raw/nstdb/1.0.0"))
    assert "scripts/acquire_nstdb.py" in str(error)
    assert "NSTDB_DATA_NOT_ACQUIRED" in str(error)
