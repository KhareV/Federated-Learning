"""BIDMC PPG and Respiration Dataset v1.0.0 loader — T007 scope only.

BIDMC's project role is MULTIMODAL_ENGINEERING_CONTEXT (ECG/PPG synchronization, pulse-rate
context, HR/PR agreement, SpO2 validity/context, quality testing, multimodal replay). It is
never supervised arrhythmia evidence and must never be merged into MODEL_V1 training labels.

Each record has two WFDB families: the waveform record (bidmc##, 125 Hz target: RESP, PLETH,
ECG leads) and the numerics record (bidmc##n, 1 Hz target: HR, PULSE, RESP, SpO2). Channel
order is NOT assumed consistent across records (verified: it varies) and lookups are always
by exact name, never by position.

VERIFIED SOURCE FORMAT QUIRK: every signal description in every official v1.0.0 header (both
waveform and numerics families) carries a literal trailing comma, e.g. the raw header field is
"PLETH," not "PLETH" (confirmed by direct byte inspection of the .hea files, not a WFDB parsing
artifact). This is a fixed, universal, per-record-verified source encoding, not case-insensitive
or approximate matching: `HeaderInfo.sig_name` strips exactly one trailing "," (and any trailing
whitespace) from each raw WFDB signal description before exact-equality lookups are performed
against the documented canonical names (PLETH, II, HR, PULSE, SpO2). The untouched original
strings remain available via `HeaderInfo.raw_sig_name` so nothing is hidden. This does not
substitute one physiological channel for another; it only strips a fixed source-format
character sequence common to every signal in every record, then applies ordinary exact
equality. See reports/t007/bidmc_validation.json for the full per-record audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import wfdb

DATASET_ID = "BIDMC"
DATASET_VERSION = "1.0.0"
EXPECTED_WAVEFORM_FS_HZ = 125
EXPECTED_NUMERICS_FS_HZ = 1

PPG_SIGNAL_NAME = "PLETH"
ECG_SIGNAL_NAME = "II"
HR_SIGNAL_NAME = "HR"
PULSE_SIGNAL_NAME = "PULSE"
SPO2_SIGNAL_NAME = "SpO2"

# The single, narrow, source-verified normalization documented in the module docstring above.
_TRAILING_DESCRIPTION_SUFFIX = ","

DEFAULT_RAW_ROOT = Path("data/raw/bidmc/1.0.0")


def _clean_signal_name(raw_name: str) -> str:
    stripped = raw_name.strip()
    if stripped.endswith(_TRAILING_DESCRIPTION_SUFFIX):
        stripped = stripped[: -len(_TRAILING_DESCRIPTION_SUFFIX)]
    return stripped.strip()


@dataclass(frozen=True)
class HeaderInfo:
    record_id: str
    fs: float
    sig_len: int
    n_sig: int
    sig_name: tuple[str, ...]
    raw_sig_name: tuple[str, ...]
    units: tuple[str, ...]
    duration_seconds: float


def data_not_acquired_error(raw_root: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"BIDMC_DATA_NOT_ACQUIRED: no local records found under {raw_root}. "
        "Run scripts/acquire_bidmc.py first; real local data is required, this is never "
        "silently downgraded to a skip."
    )


def list_records(raw_root: Path = DEFAULT_RAW_ROOT) -> list[str]:
    """Return base waveform record IDs (e.g. 'bidmc01'), derived from the local RECORDS file."""
    records_file = raw_root / "RECORDS"
    if not records_file.exists():
        raise data_not_acquired_error(raw_root)
    lines = records_file.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def _read_header(path: str, record_id: str) -> HeaderInfo:
    header = wfdb.rdheader(path)
    fs = float(header.fs)
    sig_len = int(header.sig_len)
    raw_names = tuple(header.sig_name)
    return HeaderInfo(
        record_id=record_id,
        fs=fs,
        sig_len=sig_len,
        n_sig=int(header.n_sig),
        sig_name=tuple(_clean_signal_name(name) for name in raw_names),
        raw_sig_name=raw_names,
        units=tuple(header.units) if header.units else (),
        duration_seconds=(sig_len / fs) if fs else 0.0,
    )


def read_waveform_header(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> HeaderInfo:
    return _read_header(str(raw_root / record_id), record_id)


def read_numeric_header(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> HeaderInfo:
    numeric_id = f"{record_id}n"
    return _read_header(str(raw_root / numeric_id), numeric_id)


def find_signal(sig_name: tuple[str, ...], name: str) -> int | None:
    """Exact-match index of `name` in `sig_name`, or None if absent. Raises if ambiguous
    (multiple exact matches) rather than picking one arbitrarily. No fuzzy matching."""
    matches = [index for index, candidate in enumerate(sig_name) if candidate == name]
    if len(matches) > 1:
        raise ValueError(f"AMBIGUOUS_SIGNAL_NAME: {name!r} appears at indices {matches}")
    return matches[0] if matches else None


def load_pleth(
    record_id: str, raw_root: Path = DEFAULT_RAW_ROOT, *, physical: bool = True
) -> np.ndarray:
    header = read_waveform_header(record_id, raw_root)
    index = find_signal(header.sig_name, PPG_SIGNAL_NAME)
    if index is None:
        raise ValueError(f"PPG_UNAVAILABLE: {record_id} has no exact {PPG_SIGNAL_NAME} channel")
    record = wfdb.rdrecord(str(raw_root / record_id), physical=physical)
    signal = record.p_signal if physical else record.d_signal
    return signal[:, index]


def load_lead_ii(
    record_id: str, raw_root: Path = DEFAULT_RAW_ROOT, *, physical: bool = True
) -> np.ndarray:
    header = read_waveform_header(record_id, raw_root)
    index = find_signal(header.sig_name, ECG_SIGNAL_NAME)
    if index is None:
        raise ValueError(f"ECG_II_UNAVAILABLE: {record_id} has no exact {ECG_SIGNAL_NAME} channel")
    record = wfdb.rdrecord(str(raw_root / record_id), physical=physical)
    signal = record.p_signal if physical else record.d_signal
    return signal[:, index]


def load_numerics(
    record_id: str, raw_root: Path = DEFAULT_RAW_ROOT, *, physical: bool = True
) -> dict[str, np.ndarray | None]:
    """Return {'HR': array|None, 'PULSE': array|None, 'SpO2': array|None}, exact-name lookup
    only. Missing channels are None, never fabricated. Source values and missingness (e.g.
    invalid/dropout samples within a present channel) are preserved verbatim -- no forward
    fill, interpolation, zero-fill, or physiological clipping happens here."""
    header = read_numeric_header(record_id, raw_root)
    record = wfdb.rdrecord(str(raw_root / f"{record_id}n"), physical=physical)
    signal = record.p_signal if physical else record.d_signal
    result: dict[str, np.ndarray | None] = {}
    for name in (HR_SIGNAL_NAME, PULSE_SIGNAL_NAME, SPO2_SIGNAL_NAME):
        index = find_signal(header.sig_name, name)
        result[name] = signal[:, index] if index is not None else None
    return result


def validate_record(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> dict[str, Any]:
    """Structural validation + exact-channel-availability audit for one record. No arrhythmia
    labels, no engineering experiments -- audits availability only."""
    result: dict[str, Any] = {
        "record_id": record_id,
        "waveform_header_parsed": False,
        "numeric_header_parsed": False,
        "waveform_signal_parsed": False,
        "numeric_signal_parsed": False,
        "waveform_fs": None,
        "numeric_fs": None,
        "waveform_fs_ok": False,
        "numeric_fs_ok": False,
        "waveform_sig_name": None,
        "raw_waveform_sig_name": None,
        "numeric_sig_name": None,
        "raw_numeric_sig_name": None,
        "pleth_available": False,
        "ii_available": False,
        "hr_available": False,
        "pulse_available": False,
        "spo2_available": False,
        "waveform_signal_finite": False,
        "numeric_missing_sample_counts": {},
        "errors": [],
    }

    try:
        waveform_header = read_waveform_header(record_id, raw_root)
        result["waveform_header_parsed"] = True
        result["waveform_fs"] = waveform_header.fs
        result["waveform_fs_ok"] = waveform_header.fs == EXPECTED_WAVEFORM_FS_HZ
        result["waveform_sig_name"] = list(waveform_header.sig_name)
        result["raw_waveform_sig_name"] = list(waveform_header.raw_sig_name)
        result["pleth_available"] = (
            find_signal(waveform_header.sig_name, PPG_SIGNAL_NAME) is not None
        )
        result["ii_available"] = find_signal(waveform_header.sig_name, ECG_SIGNAL_NAME) is not None
    except Exception as error:
        result["errors"].append(f"waveform_header: {error}")

    try:
        numeric_header = read_numeric_header(record_id, raw_root)
        result["numeric_header_parsed"] = True
        result["numeric_fs"] = numeric_header.fs
        result["numeric_fs_ok"] = numeric_header.fs == EXPECTED_NUMERICS_FS_HZ
        result["numeric_sig_name"] = list(numeric_header.sig_name)
        result["raw_numeric_sig_name"] = list(numeric_header.raw_sig_name)
        result["hr_available"] = find_signal(numeric_header.sig_name, HR_SIGNAL_NAME) is not None
        result["pulse_available"] = (
            find_signal(numeric_header.sig_name, PULSE_SIGNAL_NAME) is not None
        )
        result["spo2_available"] = (
            find_signal(numeric_header.sig_name, SPO2_SIGNAL_NAME) is not None
        )
    except Exception as error:
        result["errors"].append(f"numeric_header: {error}")

    if result["waveform_header_parsed"]:
        try:
            waveform_record = wfdb.rdrecord(str(raw_root / record_id), physical=True)
            result["waveform_signal_parsed"] = True
            result["waveform_signal_finite"] = bool(np.isfinite(waveform_record.p_signal).all())
        except Exception as error:
            result["errors"].append(f"waveform_signal: {error}")

    if result["numeric_header_parsed"]:
        try:
            numeric_record = wfdb.rdrecord(str(raw_root / f"{record_id}n"), physical=True)
            result["numeric_signal_parsed"] = True
            missing_counts = {}
            for index, name in enumerate(numeric_header.sig_name):
                column = numeric_record.p_signal[:, index]
                missing_counts[name] = int(np.isnan(column).sum())
            result["numeric_missing_sample_counts"] = missing_counts
        except Exception as error:
            result["errors"].append(f"numeric_signal: {error}")

    return result
