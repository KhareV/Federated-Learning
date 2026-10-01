#!/usr/bin/env python3
"""Deterministic PUBLIC_ECG_REPLAY_V1 window selection (T034, Section 8).

Structural selection ONLY: no label, model-probability, prediction-correctness, beat-class, or
signal-quality-outcome field is used to choose which windows are selected. The rule is fixed
BEFORE any replay request is sent, from the frozen TRAIN partition of
manifests/windows/MITDB_WINDOWS_V1.csv:

1. Group TRAIN windows by participant_group_id; take the lexicographically smallest group that
   contains a run of 12 windows (within one record_id) whose prediction_timestamp_us values are
   exactly 5,000,000 microseconds apart.
2. Within that group, take the earliest such run (by timestamp).

No VALIDATION/CALIBRATION/INTERNAL_TEST/INCART/NSTDB/BIDMC/WEARABLE_V1 row is read.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
REPLAY_LENGTH = 12
CADENCE_US = 5_000_000


def _read_train_rows() -> list[dict[str, str]]:
    with WINDOWS_MANIFEST.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row["partition"] == "TRAIN"]


def _find_first_run(record_rows: list[dict[str, str]]) -> list[dict[str, str]] | None:
    """record_rows must already be sorted by prediction_timestamp_us ascending."""
    n = len(record_rows)
    for start in range(0, n - REPLAY_LENGTH + 1):
        window = record_rows[start : start + REPLAY_LENGTH]
        if all(
            int(window[i + 1]["prediction_timestamp_us"])
            - int(window[i]["prediction_timestamp_us"])
            == CADENCE_US
            for i in range(REPLAY_LENGTH - 1)
        ):
            return window
    return None


def select() -> dict[str, Any]:
    rows = _read_train_rows()
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_group[row["participant_group_id"]].append(row)

    for group_id in sorted(by_group):
        by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in by_group[group_id]:
            by_record[row["record_id"]].append(row)

        best_run: list[dict[str, str]] | None = None
        best_record_id: str | None = None
        for record_id in sorted(by_record):
            record_rows = sorted(
                by_record[record_id], key=lambda r: int(r["prediction_timestamp_us"])
            )
            run = _find_first_run(record_rows)
            if run is not None and (
                best_run is None
                or int(run[0]["prediction_timestamp_us"])
                < int(best_run[0]["prediction_timestamp_us"])
            ):
                best_run = run
                best_record_id = record_id

        if best_run is not None:
            return {
                "replay_id": "PUBLIC_ECG_REPLAY_V1",
                "dataset_id": "MITDB",
                "partition": "TRAIN",
                "participant_group_id": group_id,
                "record_id": best_record_id,
                "window_count": REPLAY_LENGTH,
                "cadence_us": CADENCE_US,
                "window_seconds": 10,
                "selection_rule": (
                    "Lexicographically smallest TRAIN participant_group_id containing a run "
                    "of 12 windows (within one record_id) with prediction_timestamp_us exactly "
                    "5,000,000us apart; earliest such run by timestamp within that group. No "
                    "label, probability, prediction-correctness, beat-class, or signal-quality "
                    "field was used to select."
                ),
                "windows": [
                    {
                        "sequence_index": index,
                        "example_id": row["example_id"],
                        "prediction_timestamp_us": int(row["prediction_timestamp_us"]),
                        "signal_start_timestamp_us": int(row["signal_start_timestamp_us"]),
                        "signal_end_exclusive_timestamp_us": int(
                            row["signal_end_exclusive_timestamp_us"]
                        ),
                    }
                    for index, row in enumerate(best_run)
                ],
                "manifest_sha256": hash_file(WINDOWS_MANIFEST),
                "status": "PASS",
            }

    raise RuntimeError("PUBLIC_ECG_REPLAY_V1_SELECTION_FAILED: no eligible TRAIN run found")


def validate_selection(selection: dict[str, Any]) -> None:
    """Structural ordering/cadence/uniqueness check (Section 46). Raises RuntimeError on any
    violation -- reversed windows, a duplicated timestamp, a missing window, or a broken
    cadence must all fail here, not silently pass through to replay."""
    windows = sorted(selection["windows"], key=lambda w: w["sequence_index"])
    if len(windows) != REPLAY_LENGTH:
        raise RuntimeError(f"PUBLIC_ECG_REPLAY_V1_WINDOW_COUNT_MISMATCH:{len(windows)}")

    sequence_indices = [w["sequence_index"] for w in windows]
    if sequence_indices != list(range(REPLAY_LENGTH)):
        raise RuntimeError("PUBLIC_ECG_REPLAY_V1_SEQUENCE_INDEX_GAP_OR_DUPLICATE")

    example_ids = [w["example_id"] for w in windows]
    if len(set(example_ids)) != len(example_ids):
        raise RuntimeError("PUBLIC_ECG_REPLAY_V1_DUPLICATE_WINDOW_ID")

    timestamps = [w["prediction_timestamp_us"] for w in windows]
    if timestamps != sorted(timestamps):
        raise RuntimeError("PUBLIC_ECG_REPLAY_V1_TIMESTAMPS_NOT_MONOTONIC")
    if len(set(timestamps)) != len(timestamps):
        raise RuntimeError("PUBLIC_ECG_REPLAY_V1_DUPLICATE_TIMESTAMP")
    for earlier, later in pairwise(timestamps):
        if later - earlier != CADENCE_US:
            raise RuntimeError(f"PUBLIC_ECG_REPLAY_V1_CADENCE_VIOLATION:{earlier}->{later}")


def main() -> None:
    destination = ROOT / "reports/t034/replay_selection.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = select()
    validate_selection(result)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
