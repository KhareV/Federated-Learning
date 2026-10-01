#!/usr/bin/env python3
"""Build the WEARABLE_SIM_REPLAY_V1 secondary engineering fixture (T034, Section 12).

SIMULATION_ENGINEERING_ONLY: exercises the multimodal/context/error software plumbing (a
CONTEXT_UNAVAILABLE window and an UNUSABLE-quality window) using the existing WEARABLE_SIM_V1
generator. This is never real wearable validation, never G16/G21 evidence. Only
`ObservedRecord`-shaped fields are read -- `SimulationTruth`/`get_truth()` is never imported
here (see tests/test_simulation_truth_isolation_t034.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from nhm.hashing import hash_file
from preprocessing.windowing import normalize_window_zscore
from simulation.types import SegmentSpec, SimulationScenario
from simulation.wearable import generate_participant, generate_session, iter_observed_records

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/e2e"
NPZ_PATH = FIXTURE_DIR / "WEARABLE_SIM_REPLAY_V1.npz"
MANIFEST_PATH = FIXTURE_DIR / "WEARABLE_SIM_REPLAY_V1.manifest.json"

WINDOW_SAMPLES = 2500
WINDOW_CADENCE_US = 10_000_000  # one full non-overlapping 10s window per segment

SCENARIO = SimulationScenario(
    scenario_id="T034_WEARABLE_SIM_REPLAY_V1",
    segments=(
        SegmentSpec(name="normal", kind="NORMAL", sample_count=WINDOW_SAMPLES),
        SegmentSpec(
            name="context_unavailable", kind="CONTEXT_UNAVAILABLE", sample_count=WINDOW_SAMPLES
        ),
        SegmentSpec(name="unusable_ecg", kind="UNUSABLE_ECG", sample_count=WINDOW_SAMPLES),
    ),
)


def main() -> None:
    participant = generate_participant(index=0, seed=20340101)
    session = generate_session(
        participant,
        SCENARIO,
        session_id="T034-SIM-SOURCE-SESSION",
        session_seed=20340101,
        profile="REST_SEATED",
    )

    records = list(iter_observed_records(session))
    assert len(records) == WINDOW_SAMPLES * len(SCENARIO.segments)

    windows = []
    samples_matrix = np.zeros((len(SCENARIO.segments), WINDOW_SAMPLES), dtype=np.float32)
    for window_index, segment in enumerate(SCENARIO.segments):
        start = window_index * WINDOW_SAMPLES
        chunk = records[start : start + WINDOW_SAMPLES]
        raw = np.array(
            [0.0 if record.ecg_raw is None else float(record.ecg_raw) for record in chunk],
            dtype=np.float64,
        )
        normalized = normalize_window_zscore(raw)
        samples_matrix[window_index] = normalized.astype(np.float32)

        last = chunk[-1]
        windows.append(
            {
                "sequence_index": window_index,
                "segment_kind": segment.kind,
                "prediction_timestamp_us": (window_index + 1) * WINDOW_CADENCE_US,
                "ecg_quality": last.ecg_quality,
                "ppg_quality": last.ppg_quality,
                "pr_ppg_bpm": last.pr_ppg_bpm,
                "spo2_pct": last.spo2_pct,
                "spo2_valid": last.spo2_valid,
            }
        )

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(NPZ_PATH, samples=samples_matrix)

    manifest = {
        "fixture_id": "WEARABLE_SIM_REPLAY_V1",
        "claim_boundary": (
            "SIMULATION_ENGINEERING_ONLY -- not real wearable validation, "
            "not G16/G21 evidence"
        ),
        "source": "simulation.wearable (WEARABLE_SIM_V1 generator)",
        "simulation_seed": session.simulation_seed,
        "session_id": session.session_id,
        "participant_id": participant.participant_id,
        "window_count": len(SCENARIO.segments),
        "window_samples": WINDOW_SAMPLES,
        "cadence_us": WINDOW_CADENCE_US,
        "windows": windows,
        "sample_shape": list(samples_matrix.shape),
        "sample_dtype": "float32",
        "npz_sha256": hash_file(NPZ_PATH),
        "labels_included": False,
        "simulation_truth_used": False,
        "status": "PASS",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(NPZ_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
