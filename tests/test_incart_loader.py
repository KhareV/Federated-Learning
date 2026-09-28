"""Offline tests for datasets/incart.py against tiny synthetic WFDB fixtures."""

from pathlib import Path

import numpy as np
import pytest
import wfdb

from datasets.incart import (
    EXPECTED_FS_HZ,
    EXPECTED_SOURCE_CHANNEL_COUNT,
    data_not_acquired_error,
    list_records,
    load_annotations,
    load_lead_ii,
    parse_source_patient_id,
    read_header,
    validate_record,
)


def _write_record(
    directory: Path,
    record_id: str,
    *,
    sig_name: list[str],
    fs: int = 257,
    n_samples: int = 1000,
    comments: list[str] | None = None,
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
        comments=comments,
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


def test_data_not_acquired_error_when_records_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="INCART_DATA_NOT_ACQUIRED"):
        list_records(tmp_path)


def test_list_records_reads_local_records_file(tmp_path: Path) -> None:
    (tmp_path / "RECORDS").write_text("I01\nI02\nI03\n", encoding="utf-8")
    assert list_records(tmp_path) == ["I01", "I02", "I03"]


def test_read_header_reports_expected_invariants(tmp_path: Path) -> None:
    twelve_leads = ["I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    _write_record(tmp_path, "T01", sig_name=twelve_leads, fs=257, n_samples=500)
    header = read_header("T01", tmp_path)
    assert header.fs == EXPECTED_FS_HZ
    assert header.n_sig == EXPECTED_SOURCE_CHANNEL_COUNT
    assert header.sig_name[1] == "II"


def test_load_lead_ii_returns_only_ii_channel(tmp_path: Path) -> None:
    _write_record(tmp_path, "T02", sig_name=["I", "II", "III"], n_samples=200)
    ii = load_lead_ii("T02", tmp_path)
    assert ii.shape == (200,)


def test_load_lead_ii_raises_for_ineligible_record(tmp_path: Path) -> None:
    _write_record(tmp_path, "T03", sig_name=["I", "III"], n_samples=200)
    with pytest.raises(ValueError, match="not eligible"):
        load_lead_ii("T03", tmp_path)


def test_load_annotations_parses_structural_fields(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "T04",
        sig_name=["I", "II"],
        n_samples=200,
        ann_samples=[10, 50, 90],
    )
    annotation = load_annotations("T04", tmp_path)
    assert list(annotation.sample) == [10, 50, 90]


def test_parse_source_patient_id_valid_comment(tmp_path: Path) -> None:
    _write_record(
        tmp_path, "T05", sig_name=["I", "II"], n_samples=100, comments=["patient 7", "PVCs"]
    )
    assert parse_source_patient_id("T05", tmp_path) == 7


def test_parse_source_patient_id_missing_comment_returns_none_not_fabricated(
    tmp_path: Path,
) -> None:
    _write_record(tmp_path, "T06", sig_name=["I", "II"], n_samples=100, comments=["PVCs, noise"])
    assert parse_source_patient_id("T06", tmp_path) is None


def test_parse_source_patient_id_never_derived_from_record_number(tmp_path: Path) -> None:
    """A record named 'I42' with no patient comment must not silently yield patient 42."""
    _write_record(tmp_path, "I42", sig_name=["I", "II"], n_samples=100, comments=[])
    assert parse_source_patient_id("I42", tmp_path) is None


def test_validate_record_passes_for_well_formed_record(tmp_path: Path) -> None:
    twelve_leads = ["I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    _write_record(
        tmp_path,
        "T07",
        sig_name=twelve_leads,
        fs=257,
        n_samples=1000,
        comments=["patient 3"],
        ann_samples=[5, 15, 25],
    )
    result = validate_record("T07", tmp_path)
    assert result["header_parsed"] is True
    assert result["fs_ok"] is True
    assert result["channel_count_ok"] is True
    assert result["source_patient_id"] == 3
    assert result["source_patient_id_parsed"] is True
    assert result["annotation_count"] == 3
    assert result["signal_finite"] is True
    assert result["annotation_samples_below_zero"] == []
    assert result["annotation_samples_at_or_above_sig_len"] == []


def test_validate_record_reports_negative_leading_annotation_without_hiding_it(
    tmp_path: Path, monkeypatch
) -> None:
    """Mirrors the real INCART finding: a benign small negative leading annotation must be
    structurally reported, not silently dropped or folded into a single opaque bounds bit.

    wfdb's own writer refuses to persist a negative sample (stricter than its reader, which
    accepts one -- exactly the asymmetry the real official .atr files exploit), so this test
    mocks the annotation object directly rather than round-tripping through wfdb.wrann.
    """
    from types import SimpleNamespace

    _write_record(
        tmp_path, "T09", sig_name=["I", "II"], fs=257, n_samples=1000, comments=["patient 9"]
    )
    fake_annotation = SimpleNamespace(sample=np.array([-11, 5, 15]))
    monkeypatch.setattr(
        "datasets.incart.load_annotations", lambda record_id, raw_root: fake_annotation
    )
    result = validate_record("T09", tmp_path)
    assert result["annotation_samples_below_zero"] == [-11]
    assert result["annotation_samples_at_or_above_sig_len"] == []
    assert result["annotation_bounds_ok"] is False


def test_validate_record_reports_upper_bound_violation_separately(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "T10",
        sig_name=["I", "II"],
        fs=257,
        n_samples=100,
        comments=["patient 10"],
        ann_samples=[5, 15, 500],
    )
    result = validate_record("T10", tmp_path)
    assert result["annotation_samples_below_zero"] == []
    assert result["annotation_samples_at_or_above_sig_len"] == [500]
    assert result["annotation_bounds_ok"] is False


def test_validate_record_flags_missing_patient_id(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "T08",
        sig_name=["I", "II"],
        fs=257,
        n_samples=500,
        comments=["no id here"],
        ann_samples=[1],
    )
    result = validate_record("T08", tmp_path)
    assert result["source_patient_id"] is None
    assert result["source_patient_id_parsed"] is False
    assert any("patient_id" in error for error in result["errors"])


def test_data_not_acquired_message_names_the_acquisition_script() -> None:
    error = data_not_acquired_error(Path("data/raw/incartdb/1.0.0"))
    assert "scripts/acquire_incart.py" in str(error)
    assert "INCART_DATA_NOT_ACQUIRED" in str(error)
