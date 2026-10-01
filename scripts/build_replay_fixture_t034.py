#!/usr/bin/env python3
"""Build the tracked PUBLIC_ECG_REPLAY_V1 fixture from the frozen selection
(reports/t034/replay_selection.json).

Extracts only the 12 selected windows' model-ready PREPROC_V1 samples (never the full MITDB
record, never a label) from the existing TRAIN windows cache
(manifests/windows/MITDB_WINDOWS_V1.cache.csv) into a small, tracked, self-contained fixture.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
CACHE_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv"
SELECTION_PATH = ROOT / "reports/t034/replay_selection.json"
FIXTURE_DIR = ROOT / "tests/fixtures/e2e"
NPZ_PATH = FIXTURE_DIR / "PUBLIC_ECG_REPLAY_V1.npz"
MANIFEST_PATH = FIXTURE_DIR / "PUBLIC_ECG_REPLAY_V1.manifest.json"


def _cache_row(record_id: str) -> dict[str, str]:
    with CACHE_MANIFEST.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["partition"] == "TRAIN" and row["record_id"] == record_id:
                return row
    raise KeyError(f"No TRAIN cache row for record_id={record_id}")


def main() -> None:
    selection: dict[str, Any] = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    cache_row = _cache_row(selection["record_id"])

    ids = (ROOT / cache_row["example_ids_path"]).read_text(encoding="utf-8").splitlines()
    array = np.load(ROOT / cache_row["relative_path"], allow_pickle=False)

    windows = sorted(selection["windows"], key=lambda w: w["sequence_index"])
    samples = np.zeros((len(windows), array.shape[1]), dtype=np.float32)
    for window in windows:
        samples[window["sequence_index"]] = array[ids.index(window["example_id"])].astype(
            np.float32
        )

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(NPZ_PATH, samples=samples)

    manifest = {
        "fixture_id": "PUBLIC_ECG_REPLAY_V1",
        "selection": selection,
        "sample_shape": list(samples.shape),
        "sample_dtype": "float32",
        "npz_sha256": hash_file(NPZ_PATH),
        "source_cache_npy_sha256": cache_row["sha256"],
        "source_cache_relative_path": cache_row["relative_path"],
        "labels_included": False,
        "status": "PASS",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(NPZ_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
