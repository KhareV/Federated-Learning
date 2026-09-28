"""MIT-BIH Noise Stress Test Database (NSTDB) v1.0.0 loader — T007 scope only.

Represents two distinct source-defined record roles rather than flattening them:
`STRESS_ECG` (118e*/119e*: clean MIT-BIH ECG with injected electrode-motion noise at a
documented SNR) and `PURE_NOISE` (bw/em/ma: standalone noise recordings). NSTDB's project
role is NOISE_ROBUSTNESS, owned by T019; this module never runs a robustness experiment,
computes accuracy, or performs AAMI mapping (T008's scope).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import wfdb

DATASET_ID = "NSTDB"
DATASET_VERSION = "1.0.0"
EXPECTED_STRESS_FS_HZ = 360
EXPECTED_STRESS_CHANNEL_COUNT = 2

STRESS_ECG = "STRESS_ECG"
PURE_NOISE = "PURE_NOISE"

STRESS_SOURCES = ("118", "119")
NOISE_TYPE_BY_RECORD = {
    "bw": "baseline_wander",
    "em": "electrode_motion",
    "ma": "muscle_artifact",
}
# Source-defined SNR identities (v2.2/PhysioNet documentation), never derived by estimation.
SNR_DB_BY_SUFFIX = {
    "e24": 24,
    "e18": 18,
    "e12": 12,
    "e06": 6,
    "e00": 0,
    "e_6": -6,
}

DEFAULT_RAW_ROOT = Path("data/raw/nstdb/1.0.0")


@dataclass(frozen=True)
class RecordClassification:
    record_id: str
    role: str
    clean_source_record: str | None
    snr_db: int | None
    noise_type: str | None


@dataclass(frozen=True)
class HeaderInfo:
    record_id: str
    fs: float
    sig_len: int
    n_sig: int
    sig_name: tuple[str, ...]
    duration_seconds: float


def data_not_acquired_error(raw_root: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"NSTDB_DATA_NOT_ACQUIRED: no local records found under {raw_root}. "
        "Run scripts/acquire_nstdb.py first; real local data is required, this is never "
        "silently downgraded to a skip."
    )


def list_records(raw_root: Path = DEFAULT_RAW_ROOT) -> list[str]:
    records_file = raw_root / "RECORDS"
    if not records_file.exists():
        raise data_not_acquired_error(raw_root)
    lines = records_file.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def classify_record_role(record_id: str) -> RecordClassification:
    """Classify a record from its source-defined naming convention only.

    Unknown naming raises rather than silently guessing a role.
    """
    if record_id in NOISE_TYPE_BY_RECORD:
        return RecordClassification(
            record_id=record_id,
            role=PURE_NOISE,
            clean_source_record=None,
            snr_db=None,
            noise_type=NOISE_TYPE_BY_RECORD[record_id],
        )
    for source in STRESS_SOURCES:
        if record_id.startswith(source + "e"):
            suffix = record_id[len(source) :]
            if suffix in SNR_DB_BY_SUFFIX:
                return RecordClassification(
                    record_id=record_id,
                    role=STRESS_ECG,
                    clean_source_record=source,
                    snr_db=SNR_DB_BY_SUFFIX[suffix],
                    noise_type=None,
                )
    raise ValueError(
        f"UNKNOWN_NSTDB_RECORD_NAMING: {record_id!r} does not match a known "
        "NSTDB stress-ECG or pure-noise naming convention"
    )


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
        duration_seconds=(sig_len / fs) if fs else 0.0,
    )


def load_stress_ecg(
    record_id: str, raw_root: Path = DEFAULT_RAW_ROOT, *, physical: bool = True
) -> np.ndarray:
    classification = classify_record_role(record_id)
    if classification.role != STRESS_ECG:
        raise ValueError(f"{record_id} is not a {STRESS_ECG} record (role={classification.role})")
    record = wfdb.rdrecord(str(raw_root / record_id), physical=physical)
    return record.p_signal if physical else record.d_signal


def load_noise_record(
    record_id: str, raw_root: Path = DEFAULT_RAW_ROOT, *, physical: bool = True
) -> np.ndarray:
    classification = classify_record_role(record_id)
    if classification.role != PURE_NOISE:
        raise ValueError(f"{record_id} is not a {PURE_NOISE} record (role={classification.role})")
    record = wfdb.rdrecord(str(raw_root / record_id), physical=physical)
    return record.p_signal if physical else record.d_signal


def load_annotations_if_applicable(
    record_id: str, raw_root: Path = DEFAULT_RAW_ROOT
) -> wfdb.Annotation | None:
    """Return the `.atr` annotation for STRESS_ECG records; None for PURE_NOISE records,
    which have no beat annotation by source design (not a parse failure)."""
    classification = classify_record_role(record_id)
    if classification.role == PURE_NOISE:
        return None
    return wfdb.rdann(str(raw_root / record_id), "atr")


def snr_for_record(record_id: str) -> int | None:
    return classify_record_role(record_id).snr_db


def validate_record(record_id: str, raw_root: Path = DEFAULT_RAW_ROOT) -> dict[str, Any]:
    """Role-aware structural validation. No robustness experiment, no AAMI mapping."""
    result: dict[str, Any] = {
        "record_id": record_id,
        "role": None,
        "clean_source_record": None,
        "snr_db": None,
        "noise_type": None,
        "header_parsed": False,
        "signal_parsed": False,
        "annotation_parsed": False,
        "annotation_expected": False,
        "fs": None,
        "n_sig": None,
        "signal_length_positive": False,
        "signal_finite": False,
        "annotation_count": 0,
        "annotation_bounds_ok": False,
        "annotation_nondecreasing_ok": False,
        "errors": [],
    }

    try:
        classification = classify_record_role(record_id)
        result["role"] = classification.role
        result["clean_source_record"] = classification.clean_source_record
        result["snr_db"] = classification.snr_db
        result["noise_type"] = classification.noise_type
        result["annotation_expected"] = classification.role == STRESS_ECG
    except ValueError as error:
        result["errors"].append(f"classification: {error}")
        return result

    try:
        header = read_header(record_id, raw_root)
        result["header_parsed"] = True
        result["fs"] = header.fs
        result["n_sig"] = header.n_sig
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

    if result["annotation_expected"]:
        try:
            annotation = load_annotations_if_applicable(record_id, raw_root)
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
    else:
        # PURE_NOISE records have no annotation by source design; this is the expected,
        # correct state, not an error -- mark the annotation-related checks trivially true.
        result["annotation_parsed"] = True
        result["annotation_bounds_ok"] = True
        result["annotation_nondecreasing_ok"] = True

    return result
