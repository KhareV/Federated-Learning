"""Offline tests for datasets/mitdb.py against tiny synthetic WFDB fixtures.

No network access and no real MIT-BIH data are required: each test writes a minimal valid
WFDB record (via wfdb's own writer) into a pytest tmp_path directory, matching the exact
on-disk format the loader parses, without downloading anything.
"""

from pathlib import Path

import numpy as np
import pytest
import wfdb

from datasets.mitdb import (
    EXPECTED_FS_HZ,
    EXPECTED_SOURCE_CHANNEL_COUNT,
    data_not_acquired_error,
    list_records,
    load_annotations,
    load_mlii,
    read_header,
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
    ann_symbols: list[str] | None = None,
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
            symbol=ann_symbols or ["N"] * len(ann_samples),
            write_dir=str(directory),
        )


def test_data_not_acquired_error_when_records_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="MITDB_DATA_NOT_ACQUIRED"):
        list_records(tmp_path)


def test_list_records_reads_local_records_file(tmp_path: Path) -> None:
    (tmp_path / "RECORDS").write_text("100\n101\n102\n", encoding="utf-8")
    assert list_records(tmp_path) == ["100", "101", "102"]


def test_read_header_reports_expected_invariants(tmp_path: Path) -> None:
    _write_record(tmp_path, "T100", sig_name=["MLII", "V1"], fs=360, n_samples=500)
    header = read_header("T100", tmp_path)
    assert header.record_id == "T100"
    assert header.fs == EXPECTED_FS_HZ
    assert header.n_sig == EXPECTED_SOURCE_CHANNEL_COUNT
    assert header.sig_name == ("MLII", "V1")
    assert header.sig_len == 500
    assert header.duration_seconds == pytest.approx(500 / 360)


def test_load_mlii_returns_only_the_mlii_channel(tmp_path: Path) -> None:
    _write_record(tmp_path, "T101", sig_name=["V5", "MLII"], n_samples=200)
    mlii = load_mlii("T101", tmp_path)
    assert mlii.shape == (200,)


def test_load_mlii_raises_for_ineligible_record(tmp_path: Path) -> None:
    _write_record(tmp_path, "T102", sig_name=["V5", "V1"], n_samples=200)
    with pytest.raises(ValueError, match="not eligible"):
        load_mlii("T102", tmp_path)


def test_load_annotations_parses_structural_fields(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "T103",
        sig_name=["MLII", "V1"],
        n_samples=200,
        ann_samples=[10, 50, 90],
        ann_symbols=["N", "N", "V"],
    )
    annotation = load_annotations("T103", tmp_path)
    assert list(annotation.sample) == [10, 50, 90]
    assert list(annotation.symbol) == ["N", "N", "V"]


def test_validate_record_passes_for_well_formed_record(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "T104",
        sig_name=["MLII", "V1"],
        fs=360,
        n_samples=1000,
        ann_samples=[5, 15, 25],
    )
    result = validate_record("T104", tmp_path)
    assert result["header_parsed"] is True
    assert result["signal_parsed"] is True
    assert result["annotation_parsed"] is True
    assert result["fs_ok"] is True
    assert result["channel_count_ok"] is True
    assert result["signal_length_positive"] is True
    assert result["signal_finite"] is True
    assert result["annotation_count"] == 3
    assert result["annotation_bounds_ok"] is True
    assert result["annotation_nondecreasing_ok"] is True
    assert result["errors"] == []


def test_validate_record_flags_wrong_sampling_rate(tmp_path: Path) -> None:
    _write_record(tmp_path, "T105", sig_name=["MLII", "V1"], fs=250, n_samples=500)
    result = validate_record("T105", tmp_path)
    assert result["header_parsed"] is True
    assert result["fs_ok"] is False


def test_validate_record_flags_wrong_channel_count(tmp_path: Path) -> None:
    _write_record(tmp_path, "T106", sig_name=["MLII"], fs=360, n_samples=500)
    result = validate_record("T106", tmp_path)
    assert result["channel_count_ok"] is False


def test_validate_record_reports_missing_record_without_raising(tmp_path: Path) -> None:
    result = validate_record("DOES_NOT_EXIST", tmp_path)
    assert result["header_parsed"] is False
    assert result["errors"]


def test_data_not_acquired_message_names_the_acquisition_script() -> None:
    error = data_not_acquired_error(Path("data/raw/mitdb/1.0.0"))
    assert "scripts/acquire_mitdb.py" in str(error)
    assert "MITDB_DATA_NOT_ACQUIRED" in str(error)
