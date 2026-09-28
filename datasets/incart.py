"""St Petersburg INCART 12-lead Arrhythmia Database v1.0.0 loader — T007 scope only.

INCART's project role is LOCKED_EXTERNAL_ECG_EVALUATION, owned exclusively by T020's single
locked external evaluation run. This module never runs inference, computes a performance
metric, or otherwise influences model/preprocessing/threshold/calibration choices -- it only
acquires, structurally validates, and exposes the exact-Lead-II channel and the documented
source patient/Holter identity comment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import wfdb

DATASET_ID = "INCART"
DATASET_VERSION = "1.0.0"
LEAD_POLICY_ID = "INCART_EXACT_II_V1"
REQUIRED_LEAD_NAME = "II"
EXPECTED_FS_HZ = 257
EXPECTED_SOURCE_CHANNEL_COUNT = 12

DEFAULT_RAW_ROOT = Path("data/raw/incartdb/1.0.0")

# wfdb strips the leading '#' from header comment lines, so a comment reads e.g. "patient 1".
_PATIENT_COMMENT_PATTERN = re.compile(r"patient\s+(\d+)", re.IGNORECASE)


class ExclusionReason:
    NONE = "ELIGIBLE_EXACT_II"
    NO_EXACT_II = "EXCLUDE_NO_EXACT_II"
    AMBIGUOUS_MULTIPLE_II = "EXCLUDE_AMBIGUOUS_MULTIPLE_II"
    MALFORMED_HEADER = "EXCLUDE_MALFORMED_HEADER"


@dataclass(frozen=True)
class HeaderInfo:
    record_id: str
    fs: float
    sig_len: int
    n_sig: int
    sig_name: tuple[str, ...]
    comments: tuple[str, ...]
    duration_seconds: float


@dataclass(frozen=True)
class LeadIISelection:
    record_id: str
    all_signal_names: tuple[str, ...]
    ii_present: bool
    ii_channel_index: int | None
    eligible: bool
    exclusion_reason: str


def data_not_acquired_error(raw_root: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"INCART_DATA_NOT_ACQUIRED: no local records found under {raw_root}. "
        "Run scripts/acquire_incart.py first; real local data is required, this is never "
        "silently downgraded to a skip."
    )


def list_records(raw_root: Path = DEFAULT_RAW_ROOT) -> list[str]:
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
        comments=tuple(header.comments) if header.comments else (),
        duration_seconds=(sig_len / fs) if fs else 0.0,
    )


def select_exact_lead_ii(sig_name: list[str] | tuple[str, ...]) -> int | None:
    """Exact-match index of "II" in `sig_name`, or None if absent. Raises if "II" appears
    more than once (ambiguous headers are excluded, never picked arbitrarily). No fuzzy or
    case-insensitive matching, and no index-based fallback."""
    matches = [index for index, name in enumerate(sig_name) if name == REQUIRED_LEAD_NAME]
    if len(matches) > 1:
        raise ValueError(f"EXCLUDE_AMBIGUOUS_MULTIPLE_II: {list(sig_name)}")
    return matches[0] if matches else None


def inspect_record(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> LeadIISelection:
    """Apply the locked exact-II policy to one record's header. Never raises; unreadable or
    ambiguous headers become an explicit excluded LeadIISelection instead."""
    try:
        header = read_header(record_id, raw_root)
    except Exception:
        return LeadIISelection(
            record_id=record_id,
            all_signal_names=(),
            ii_present=False,
            ii_channel_index=None,
            eligible=False,
            exclusion_reason=ExclusionReason.MALFORMED_HEADER,
        )
    try:
        index = select_exact_lead_ii(header.sig_name)
    except ValueError:
        return LeadIISelection(
            record_id=record_id,
            all_signal_names=header.sig_name,
            ii_present=True,
            ii_channel_index=None,
            eligible=False,
            exclusion_reason=ExclusionReason.AMBIGUOUS_MULTIPLE_II,
        )
    if index is None:
        return LeadIISelection(
            record_id=record_id,
            all_signal_names=header.sig_name,
            ii_present=False,
            ii_channel_index=None,
            eligible=False,
            exclusion_reason=ExclusionReason.NO_EXACT_II,
        )
    return LeadIISelection(
        record_id=record_id,
        all_signal_names=header.sig_name,
        ii_present=True,
        ii_channel_index=index,
        eligible=True,
        exclusion_reason=ExclusionReason.NONE,
    )


def load_lead_ii(
    record_id: str, raw_root: Path = DEFAULT_RAW_ROOT, *, physical: bool = True
) -> np.ndarray:
    selection = inspect_record(record_id, raw_root)
    if not selection.eligible or selection.ii_channel_index is None:
        raise ValueError(
            f"{record_id} is not eligible under {LEAD_POLICY_ID}: {selection.exclusion_reason}"
        )
    record = wfdb.rdrecord(str(raw_root / record_id), physical=physical)
    signal = record.p_signal if physical else record.d_signal
    return signal[:, selection.ii_channel_index]


def load_annotations(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> wfdb.Annotation:
    """Parse the canonical `<record>.atr` annotation file. Structural access only -- no AAMI
    symbol mapping or the shared symbol census happens here; that is T008's scope."""
    return wfdb.rdann(str(raw_root / record_id), "atr")


def parse_source_patient_id(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> int | None:
    """Extract the documented "patient N" Holter-grouping identifier from header comments.

    Returns None (never fabricated, never guessed from the record number) if no comment
    matches the documented pattern.
    """
    header = read_header(record_id, raw_root)
    for comment in header.comments:
        match = _PATIENT_COMMENT_PATTERN.search(comment)
        if match:
            return int(match.group(1))
    return None


def validate_record(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> dict[str, Any]:
    """Structural integrity validation only: header/signal/annotation parse, basic
    invariants, and source patient-ID parseability. No AAMI mapping, no preprocessing, no
    external evaluation."""
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
        "source_patient_id": None,
        "source_patient_id_parsed": False,
        "annotation_samples_below_zero": [],
        "annotation_samples_at_or_above_sig_len": [],
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
        patient_id = parse_source_patient_id(record_id, raw_root)
        result["source_patient_id"] = patient_id
        result["source_patient_id_parsed"] = patient_id is not None
        if patient_id is None:
            result["errors"].append("patient_id: no 'patient N' comment found")
    except Exception as error:
        result["errors"].append(f"patient_id: {error}")

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
        # Reported separately (not collapsed into one bounds_ok bit) because a small
        # negative leading sample and a sample past sig_len have very different
        # implications: the former is a verified, benign INCART source characteristic
        # (see reports/t007/incart_validation.json known_source_anomalies), the latter
        # would indicate genuine truncation/corruption. See validate_incart_t007.py for
        # the policy that decides which counts as a hard integrity failure.
        result["annotation_samples_below_zero"] = samples[samples < 0].tolist()
        result["annotation_samples_at_or_above_sig_len"] = samples[
            samples >= header.sig_len
        ].tolist()
        result["annotation_bounds_ok"] = bool(
            len(samples) == 0 or (samples.min() >= 0 and samples.max() < header.sig_len)
        )
        result["annotation_nondecreasing_ok"] = bool(
            len(samples) < 2 or np.all(np.diff(samples) >= 0)
        )
    except Exception as error:
        result["errors"].append(f"annotation: {error}")

    return result
