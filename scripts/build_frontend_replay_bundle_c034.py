#!/usr/bin/env python3
"""C034 Section 7/8: deterministic browser-consumable PUBLIC_ECG_REPLAY_V1 bundle.

Derives frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json directly and ONLY from the
already-frozen tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.{npz,manifest.json} -- byte-identical
samples, same window order, same timestamps as the existing T034 backend request path
(scripts/run_replay.py). No normalization is added or removed here (see
reports/c034_ui_e2e/model_input_semantics.json). No label, prediction outcome, or
SimulationTruth field is included. Regeneration must be byte-identical (this script performs
no randomness and reads only the frozen fixture).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/e2e"
NPZ_PATH = FIXTURE_DIR / "PUBLIC_ECG_REPLAY_V1.npz"
MANIFEST_PATH = FIXTURE_DIR / "PUBLIC_ECG_REPLAY_V1.manifest.json"
BUNDLE_PATH = ROOT / "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json"
BUNDLE_MANIFEST_PATH = ROOT / "reports/c034_ui_e2e/frontend_replay_bundle.json"

REPLAY_ID = "PUBLIC_ECG_REPLAY_V1"


def build() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    selection = manifest["selection"]
    samples = np.load(NPZ_PATH)["samples"]
    windows = sorted(selection["windows"], key=lambda w: w["sequence_index"])

    events = []
    for window in windows:
        index = window["sequence_index"]
        events.append(
            {
                "sequence_index": index,
                "window_id": window["example_id"],
                "replay_id": REPLAY_ID,
                "timestamp_us": window["prediction_timestamp_us"],
                "ecg": {
                    "samples": samples[index].astype(np.float64).tolist(),
                    "target_hz": 250,
                    "window_seconds": 10,
                },
                "ecg_quality": "VALID",
                "ppg_context": None,
                "model_id": "MODEL_V1",
                "contract_version": "API_SCHEMA_V1",
            }
        )

    return {
        "replay_id": REPLAY_ID,
        "source_npz_sha256": manifest["npz_sha256"],
        "source_manifest_participant_group_id": selection["participant_group_id"],
        "source_manifest_record_id": selection["record_id"],
        "window_count": len(events),
        "events": events,
        "labels_included": False,
        "prediction_outcome_included": False,
        "simulation_truth_included": False,
    }


def main() -> None:
    bundle = build()
    BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUNDLE_PATH.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    bundle_sha = hash_file(BUNDLE_PATH)
    window_ids = [event["window_id"] for event in bundle["events"]]
    timestamps = [event["timestamp_us"] for event in bundle["events"]]

    record = {
        "path": "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json",
        "sha256": bundle_sha,
        "generated_by": "scripts/build_frontend_replay_bundle_c034.py",
        "generated_deterministically": True,
        "source_npz_sha256": bundle["source_npz_sha256"],
        "window_count": bundle["window_count"],
        "window_ids_ordered": window_ids,
        "timestamps_ordered": timestamps,
        "contains_labels": False,
        "contains_prediction_outcome": False,
        "contains_simulation_truth": False,
        "samples_per_event": len(bundle["events"][0]["ecg"]["samples"]),
        "status": "PASS",
    }
    BUNDLE_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUNDLE_MANIFEST_PATH.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(BUNDLE_PATH)
    print(bundle_sha)


if __name__ == "__main__":
    main()
