"""C-V2-D0.6 hard data firewall: a per-path allowlist (not a partition-role system, since D0.6
reads already-frozen development EVIDENCE, never raw waveform or a live partition). Every file
this checkpoint's code opens must be checked here first and is rejected if it is not on the
explicit allowlist, or if its path matches a forbidden raw-waveform/forbidden-partition pattern.
Fail-closed: unknown paths are denied, never silently allowed.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Exact relative paths (from repo root) this checkpoint is permitted to read. Additive to, never
# a replacement for, the raw-waveform/forbidden-partition denylist below.
ALLOWED_PATHS: frozenset[str] = frozenset(
    {
        # TRAIN-OOF decision-eligible sources (Section 4A)
        "reports/model_v2/v2_002/oof_predictions.csv",
        "reports/model_v2/v2_003/oof_predictions.csv",
        "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json",
        "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json",
        # frozen TRAIN/VALIDATION window+label+group metadata (not waveform)
        "manifests/windows/MITDB_WINDOWS_V1.csv",
        # frozen BASELINE_FEATURES_V1 derived-feature caches (not raw waveform) for the HR
        # feature only -- TRAIN and VALIDATION, both already-computed by T014
        "manifests/features/MITDB_BASELINE_FEATURES_V1.csv",
        "manifests/features/BASELINE_FEATURES_V1.schema.json",
        (
            "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
            "BASELINE_FEATURES_V1/TRAIN_features.npy"
        ),
        (
            "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
            "BASELINE_FEATURES_V1/VALIDATION_features.npy"
        ),
        # frozen scalar/config metadata (Section 2C)
        "artifacts/CAL_V1.json",
        "configs/baseline_v1.yaml",
        "reports/baselines/baseline_report.json",
        "reports/t015/seeds/20260927.json",
        "reports/t015/seeds/20260928.json",
        "reports/t015/seeds/20260929.json",
        # the frozen class-composition definition being reused, read for hash/provenance only
        "evaluation/error_analysis.py",
    }
)

# Any path containing one of these substrings is denied even if it were (by mistake) added to
# ALLOWED_PATHS above -- a second, independent layer against raw-waveform/forbidden-partition
# access.
FORBIDDEN_PATH_SUBSTRINGS: tuple[str, ...] = (
    "MITDB_WINDOWS_V1.cache.csv",  # raw waveform cache manifest
    "/CALIBRATION/",
    "calibration_predictions.csv",
    "internal_test_predictions.csv",
    "external_incart_predictions.csv",
    "nstdb_predictions.csv",
    "/INTERNAL_TEST/",
    "/INCART/",
    "/NSTDB/",
    "/BIDMC/",
    "wearable",
)

LEDGER_RELATIVE_PATH = "reports/model_v2/c_v2_d0_6/scope_access_ledger.jsonl"


class D06AccessViolation(PermissionError):
    """A D0.6 code path attempted to read something outside the explicit allowlist, or
    matching a forbidden raw-waveform/forbidden-partition pattern."""


def check_d0_6_read_allowed(relative_path: str) -> None:
    normalized = relative_path.replace("\\", "/")
    for forbidden in FORBIDDEN_PATH_SUBSTRINGS:
        if forbidden in normalized:
            raise D06AccessViolation(f"D0_6_FIREWALL_FORBIDDEN_PATTERN: {relative_path!r}")
    if normalized not in ALLOWED_PATHS:
        raise D06AccessViolation(f"D0_6_FIREWALL_NOT_ALLOWLISTED: {relative_path!r}")


def record_d0_6_access(
    root: Path,
    *,
    relative_path: str,
    stratum: str,
    purpose: str,
    rows_read: int | None = None,
) -> None:
    """Append one row to the D0.6 scope-access ledger. Call only AFTER
    check_d0_6_read_allowed has not raised, and after the read has actually happened."""
    ledger_path = root / LEDGER_RELATIVE_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "relative_path": relative_path,
        "stratum": stratum,
        "purpose": purpose,
        "rows_read": rows_read,
    }
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def known_allowed_paths() -> Collection[str]:
    return ALLOWED_PATHS
