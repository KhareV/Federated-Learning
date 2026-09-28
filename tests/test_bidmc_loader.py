"""Offline tests for datasets/bidmc.py against tiny synthetic WFDB fixtures."""

from pathlib import Path

import numpy as np
import pytest
import wfdb

from datasets.bidmc import (
    EXPECTED_NUMERICS_FS_HZ,
    EXPECTED_WAVEFORM_FS_HZ,
    data_not_acquired_error,
    find_signal,
    list_records,
    load_lead_ii,
    load_numerics,
    load_pleth,
    read_numeric_header,
    read_waveform_header,
    validate_record,
)


def _write_waveform(
    directory: Path, record_id: str, *, sig_name_with_commas: list[str], n_samples: int = 500
) -> None:
    rng = np.random.default_rng(0)
    signal = rng.normal(size=(n_samples, len(sig_name_with_commas)))
    wfdb.wrsamp(
        record_id,
        fs=EXPECTED_WAVEFORM_FS_HZ,
        units=["mV"] * len(sig_name_with_commas),
        sig_name=sig_name_with_commas,
        p_signal=signal,
        fmt=["16"] * len(sig_name_with_commas),
        write_dir=str(directory),
    )


def _write_numerics(
    directory: Path,
    numeric_record_id: str,
    *,
    sig_name_with_commas: list[str],
    n_samples: int = 100,
    with_nan: bool = False,
) -> None:
    rng = np.random.default_rng(0)
    signal = rng.uniform(60, 100, size=(n_samples, len(sig_name_with_commas)))
    if with_nan:
        signal[0, 0] = np.nan
        signal[1, 0] = np.nan
    wfdb.wrsamp(
        numeric_record_id,
        fs=EXPECTED_NUMERICS_FS_HZ,
        units=["bpm"] * len(sig_name_with_commas),
        sig_name=sig_name_with_commas,
        p_signal=signal,
        fmt=["16"] * len(sig_name_with_commas),
        write_dir=str(directory),
    )


def test_data_not_acquired_error_when_records_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="BIDMC_DATA_NOT_ACQUIRED"):
        list_records(tmp_path)


def test_find_signal_exact_match_only() -> None:
    names = ("RESP", "PLETH", "II")
    assert find_signal(names, "PLETH") == 1
    assert find_signal(names, "pleth") is None
    assert find_signal(names, "PLETH ") is None
    assert find_signal(names, "V") is None


def test_find_signal_raises_on_ambiguous_duplicate() -> None:
    with pytest.raises(ValueError, match="AMBIGUOUS_SIGNAL_NAME"):
        find_signal(("II", "II"), "II")


def test_trailing_comma_source_quirk_is_stripped_from_clean_name(tmp_path: Path) -> None:
    """The verified BIDMC v1.0.0 source format writes signal descriptions with a trailing
    comma (e.g. raw "PLETH,"); HeaderInfo.sig_name must expose the clean name while
    raw_sig_name preserves the untouched original for audit."""
    _write_waveform(tmp_path, "bidmc01", sig_name_with_commas=["RESP,", "PLETH,", "II,"])
    header = read_waveform_header("bidmc01", tmp_path)
    assert header.sig_name == ("RESP", "PLETH", "II")
    assert header.raw_sig_name == ("RESP,", "PLETH,", "II,")


def test_channel_order_is_not_assumed_pleth_can_be_last(tmp_path: Path) -> None:
    _write_waveform(tmp_path, "bidmc02", sig_name_with_commas=["RESP,", "II,", "V,", "PLETH,"])
    header = read_waveform_header("bidmc02", tmp_path)
    assert find_signal(header.sig_name, "PLETH") == 3


def test_load_pleth_and_load_lead_ii(tmp_path: Path) -> None:
    _write_waveform(tmp_path, "bidmc03", sig_name_with_commas=["RESP,", "PLETH,", "II,"])
    ppg = load_pleth("bidmc03", tmp_path)
    ecg = load_lead_ii("bidmc03", tmp_path)
    assert ppg.shape == (500,)
    assert ecg.shape == (500,)


def test_load_pleth_raises_when_unavailable(tmp_path: Path) -> None:
    _write_waveform(tmp_path, "bidmc04", sig_name_with_commas=["RESP,", "V,"])
    with pytest.raises(ValueError, match="PPG_UNAVAILABLE"):
        load_pleth("bidmc04", tmp_path)


def test_load_lead_ii_raises_when_unavailable_no_substitution(tmp_path: Path) -> None:
    _write_waveform(tmp_path, "bidmc05", sig_name_with_commas=["RESP,", "PLETH,", "V,"])
    with pytest.raises(ValueError, match="ECG_II_UNAVAILABLE"):
        load_lead_ii("bidmc05", tmp_path)


def test_hr_and_pulse_are_structurally_and_semantically_distinct(tmp_path: Path) -> None:
    _write_numerics(
        tmp_path, "bidmc06n", sig_name_with_commas=["HR,", "PULSE,", "RESP,", "SpO2,"]
    )
    header = read_numeric_header("bidmc06", tmp_path)
    hr_index = find_signal(header.sig_name, "HR")
    pulse_index = find_signal(header.sig_name, "PULSE")
    assert hr_index != pulse_index
    numerics = load_numerics("bidmc06", tmp_path)
    assert set(numerics) == {"HR", "PULSE", "SpO2"}
    assert numerics["HR"] is not None
    assert numerics["PULSE"] is not None
    assert not np.array_equal(numerics["HR"], numerics["PULSE"])


def test_missing_numeric_context_is_none_not_fabricated(tmp_path: Path) -> None:
    _write_numerics(tmp_path, "bidmc07n", sig_name_with_commas=["HR,", "RESP,"])
    numerics = load_numerics("bidmc07", tmp_path)
    assert numerics["HR"] is not None
    assert numerics["PULSE"] is None
    assert numerics["SpO2"] is None


def test_missing_samples_within_a_present_channel_are_preserved_as_nan(tmp_path: Path) -> None:
    _write_numerics(
        tmp_path,
        "bidmc08n",
        sig_name_with_commas=["HR,", "PULSE,", "RESP,", "SpO2,"],
        with_nan=True,
    )
    numerics = load_numerics("bidmc08", tmp_path)
    assert np.isnan(numerics["HR"][0])
    assert np.isnan(numerics["HR"][1])
    assert not np.isnan(numerics["HR"][2])


def test_validate_record_reports_no_arrhythmia_labels(tmp_path: Path) -> None:
    _write_waveform(tmp_path, "bidmc09", sig_name_with_commas=["RESP,", "PLETH,", "II,"])
    _write_numerics(tmp_path, "bidmc09n", sig_name_with_commas=["HR,", "PULSE,", "SpO2,"])
    result = validate_record("bidmc09", tmp_path)
    assert "aami_class" not in result
    assert "target" not in result
    assert "label" not in result
    assert result["waveform_fs_ok"] is True
    assert result["numeric_fs_ok"] is True
    assert result["pleth_available"] is True
    assert result["ii_available"] is True
    assert result["hr_available"] is True
    assert result["spo2_available"] is True


def test_data_not_acquired_message_names_the_acquisition_script() -> None:
    error = data_not_acquired_error(Path("data/raw/bidmc/1.0.0"))
    assert "scripts/acquire_bidmc.py" in str(error)
    assert "BIDMC_DATA_NOT_ACQUIRED" in str(error)
