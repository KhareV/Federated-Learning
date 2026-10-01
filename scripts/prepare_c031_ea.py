#!/usr/bin/env python3
"""Prepare and hash-lock C031-EA before controlled noise inference."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    t019 = read_csv(ROOT / "reports/t019/nstdb_predictions.csv")
    unique: dict[str, dict[str, str]] = {}
    for row in t019:
        unique.setdefault(row["pair_id"], row)
    base = [
        {
            "base_window_id": pair_id,
            "base_record_id": row["base_record_id"],
            "source_right_edge_index": row["source_right_edge_index"],
            "label": row["label"],
            "label_source": "clean MIT-BIH annotation semantics; verified against T019 pair",
        }
        for pair_id, row in sorted(unique.items())
    ]
    if len(base) != 720 or sum(int(row["label"]) for row in base) != 469:
        raise RuntimeError("NOISE_TYPE_BASE_WINDOW_CONFLICT")
    manifest = ROOT / "reports/t031/c031_noise_base_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(base[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(base)
    config = {
        "id": "NOISE_TYPE_ERROR_ANALYSIS_V1",
        "claim_boundary": "CONTROLLED_SOURCE_WINDOW_NOISE_TYPE_ANALYSIS",
        "base_records": ["118", "119"],
        "base_manifest_sha256": hash_file(manifest),
        "base_windows": 720,
        "positive": 469,
        "negative": 251,
        "noise_sources": {
            "BASELINE_WANDER": "bw",
            "ELECTRODE_MOTION": "em",
            "MUSCLE_ARTIFACT": "ma",
        },
        "snr_db": [24, 18, 12, 6, 0, -6],
        "noise_preprocessing": "T026 frozen PREPROC_V1_MITDB_360_TO_250_CAUSAL_PATH",
        "segment_namespace": "C031_NOISE_TYPE_V1",
        "same_segment_across_snr": True,
        "snr_formula": "signal_rms/(noise_rms*10**(snr_db/20))",
        "post_mix": "frozen per-window MODEL_V1 z-score",
        "MODEL_V1_sha256": hash_file(ROOT / "checkpoints/MODEL_V1.pt"),
        "CAL_V1_sha256": hash_file(ROOT / "artifacts/CAL_V1.json"),
        "PREPROC_V1_sha256": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
        "patient_ranking": "PATIENT_ERROR_RANKING_V2: patient Brier; lower better",
        "historical_patient_F1": "PATIENT_POSITIVE_F1_DIAGNOSTIC_V1_WITH_CAVEAT",
        "pure_noise_labels": "NONE; labels originate only from clean MIT-BIH windows",
        "quality_claim": False,
        "tuning": False,
    }
    config_path = ROOT / "configs/c031_error_analysis_v1.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    bound = [
        "configs/c031_error_analysis_v1.yaml",
        "reports/t031/c031_noise_base_manifest.csv",
        "evaluation/c031_error_analysis.py",
        "checkpoints/MODEL_V1.pt",
        "artifacts/CAL_V1.json",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "reports/noise_robustness.json",
        "reports/error_analysis_v1.json",
        "federated/feature_noise.py",
        "data/raw/nstdb/1.0.0/bw.dat",
        "data/raw/nstdb/1.0.0/em.dat",
        "data/raw/nstdb/1.0.0/ma.dat",
    ]
    write_json(
        ROOT / "artifacts/C031_ERROR_ANALYSIS_V1.lock.json",
        {
            "lock_id": "C031_ERROR_ANALYSIS_V1",
            "status": "PRE_RESULT_LOCKED",
            "analysis_id": "NOISE_TYPE_ERROR_ANALYSIS_V1",
            "bound_artifacts": {path: hash_file(ROOT / path) for path in bound},
        },
    )


if __name__ == "__main__":
    main()
