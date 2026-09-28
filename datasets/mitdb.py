"""MIT-BIH Arrhythmia Database (MITDB) v1.0.0 loader — T006 scope only.

Owns: header/signal/annotation parsing, structural validation, and the locked exact-MLII
channel policy (`MITDB_EXACT_MLII_V1`). Does NOT own patient splitting (T009), AAMI label
mapping (T008), preprocessing/resampling/filtering (T011-T012), or windowing (T013). No
signal is resampled, filtered, or transformed here beyond WFDB's own digital->physical unit
conversion (documented, not silent).

Real acquisition is a separate concern: `scripts/acquire_mitdb.py` downloads and hash-verifies
the dataset into `data/raw/mitdb/1.0.0/`. This module only reads that (or another) local root;
it never downloads anything itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import wfdb

DATASET_ID = "MITDB"
DATASET_VERSION = "1.0.0"
LEAD_POLICY_ID = "MITDB_EXACT_MLII_V1"
REQUIRED_LEAD_NAME = "MLII"
EXPECTED_FS_HZ = 360
EXPECTED_SOURCE_CHANNEL_COUNT = 2

DEFAULT_RAW_ROOT = Path("data/raw/mitdb/1.0.0")


class ExclusionReason:
    NONE = "ELIGIBLE_EXACT_MLII"
    NO_EXACT_MLII = "EXCLUDE_NO_EXACT_MLII"
    AMBIGUOUS_MULTIPLE_MLII = "EXCLUDE_AMBIGUOUS_MULTIPLE_MLII"
    MALFORMED_HEADER = "EXCLUDE_MALFORMED_HEADER"


@dataclass(frozen=True)
class HeaderInfo:
    record_id: str
    fs: float
    sig_len: int
    n_sig: int
    sig_name: tuple[str, ...]
    units: tuple[str, ...]
    duration_seconds: float


@dataclass(frozen=True)
class MliiSelection:
    record_id: str
    all_signal_names: tuple[str, ...]
    mlii_present: bool
    mlii_channel_index: int | None
    eligible: bool
    exclusion_reason: str


def data_not_acquired_error(raw_root: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"MITDB_DATA_NOT_ACQUIRED: no local records found under {raw_root}. "
        "Run scripts/acquire_mitdb.py first; real local data is required, this is never "
        "silently downgraded to a skip."
    )


def list_records(raw_root: Path = DEFAULT_RAW_ROOT) -> list[str]:
    """Return record IDs present in the local RECORDS listing written by acquisition."""
    records_file = raw_root / "RECORDS"
    if not records_file.exists():
        raise data_not_acquired_error(raw_root)
    lines = records_file.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def read_header(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> HeaderInfo:
    header = wfdb.rdheader(str(raw_root / record_id))
    fs = float(header.fs)
    sig_len = int(header.sig_len)
    return HeaderInfo(
        record_id=record_id,
        fs=fs,
        sig_len=sig_len,
        n_sig=int(header.n_sig),
        sig_name=tuple(header.sig_name),
        units=tuple(header.units) if header.units else (),
        duration_seconds=(sig_len / fs) if fs else 0.0,
    )


def select_mlii_channel(sig_name: list[str] | tuple[str, ...]) -> int | None:
    """Return the exact-match index of "MLII" in `sig_name`, or None if absent.

    Raises ValueError if "MLII" appears more than once: an ambiguous header is an audit
    failure/exclusion, never an arbitrary pick. No fuzzy or case-insensitive matching, and no
    index-based fallback of any kind (see contracts/HARDWARE_DATA_CONTRACT_V1.md-style
    exact-match discipline; this is the MITDB channel-policy analogue).
    """
    matches = [index for index, name in enumerate(sig_name) if name == REQUIRED_LEAD_NAME]
    if len(matches) > 1:
        raise ValueError(f"EXCLUDE_AMBIGUOUS_MULTIPLE_MLII: {list(sig_name)}")
    return matches[0] if matches else None


def inspect_record(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> MliiSelection:
    """Apply the locked exact-MLII policy to one record's header. Never raises; unreadable
    or ambiguous headers become an explicit excluded MliiSelection instead."""
    try:
        header = read_header(record_id, raw_root)
    except Exception:
        return MliiSelection(
            record_id=record_id,
            all_signal_names=(),
            mlii_present=False,
            mlii_channel_index=None,
            eligible=False,
            exclusion_reason=ExclusionReason.MALFORMED_HEADER,
        )
    try:
        index = select_mlii_channel(header.sig_name)
    except ValueError:
        return MliiSelection(
            record_id=record_id,
            all_signal_names=header.sig_name,
            mlii_present=True,
            mlii_channel_index=None,
            eligible=False,
            exclusion_reason=ExclusionReason.AMBIGUOUS_MULTIPLE_MLII,
        )
    if index is None:
        return MliiSelection(
            record_id=record_id,
            all_signal_names=header.sig_name,
            mlii_present=False,
            mlii_channel_index=None,
            eligible=False,
            exclusion_reason=ExclusionReason.NO_EXACT_MLII,
        )
    return MliiSelection(
        record_id=record_id,
        all_signal_names=header.sig_name,
        mlii_present=True,
        mlii_channel_index=index,
        eligible=True,
        exclusion_reason=ExclusionReason.NONE,
    )


def load_mlii(
    record_id: str, raw_root: Path = DEFAULT_RAW_ROOT, *, physical: bool = True
) -> np.ndarray:
    """Load only the MLII channel of an eligible record.

    physical=True (default) returns WFDB's calibrated physical-unit conversion from header
    gain/baseline metadata (documented provenance, not a project preprocessing step).
    physical=False returns the untouched digital/raw ADC-style samples. Raises ValueError if
    the record is not eligible under MITDB_EXACT_MLII_V1.
    """
    selection = inspect_record(record_id, raw_root)
    if not selection.eligible or selection.mlii_channel_index is None:
        raise ValueError(
            f"{record_id} is not eligible under {LEAD_POLICY_ID}: {selection.exclusion_reason}"
        )
    record = wfdb.rdrecord(str(raw_root / record_id), physical=physical)
    signal = record.p_signal if physical else record.d_signal
    return signal[:, selection.mlii_channel_index]


def load_annotations(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> wfdb.Annotation:
    """Parse the canonical current `<record>.atr` annotation file. Structural access only --
    no AAMI symbol mapping or label interpretation happens here; that is T008's scope."""
    return wfdb.rdann(str(raw_root / record_id), "atr")


def validate_record(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> dict[str, Any]:
    """Structural integrity validation only: header/signal/annotation parse and basic
    invariants. No AAMI mapping, no preprocessing, no clinical/physiological filtering."""
    result: dict[str, Any] = {
        "record_id": record_id,
        "header_parsed": False,
        "signal_parsed": False,
        "annotation_parsed": False,
        "fs_ok": False,
        "channel_count_ok": False,
        "signal_length_positive": False,
        "signal_finite": False,
        "annotation_count": 0,
        "annotation_bounds_ok": False,
        "annotation_nondecreasing_ok": False,
        "errors": [],
    }

    try:
        header = read_header(record_id, raw_root)
        result["header_parsed"] = True
        result["fs_ok"] = header.fs == EXPECTED_FS_HZ
        result["channel_count_ok"] = header.n_sig == EXPECTED_SOURCE_CHANNEL_COUNT
        result["signal_length_positive"] = header.sig_len > 0
    except Exception as error:
        result["errors"].append(f"header: {error}")
        return result

    try:
        record = wfdb.rdrecord(str(raw_root / record_id), physical=True)
        result["signal_parsed"] = True
        result["signal_finite"] = bool(np.isfinite(record.p_signal).all())
    except Exception as error:
        result["errors"].append(f"signal: {error}")

    try:
        annotation = load_annotations(record_id, raw_root)
        result["annotation_parsed"] = True
        samples = np.asarray(annotation.sample)
        result["annotation_count"] = len(samples)
        result["annotation_bounds_ok"] = bool(
            len(samples) == 0 or (samples.min() >= 0 and samples.max() < header.sig_len)
        )
        result["annotation_nondecreasing_ok"] = bool(
            len(samples) < 2 or np.all(np.diff(samples) >= 0)
        )
    except Exception as error:
        result["errors"].append(f"annotation: {error}")

    return result
