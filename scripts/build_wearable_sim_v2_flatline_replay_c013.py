#!/usr/bin/env python3
"""C-V2-013: build the additive WEARABLE_SIM_V2_REPLAY_V2_FLATLINE bundle (a true contract
flatline: exact-zero source for 40 s from stream start, then signal). The original
WEARABLE_SIM_V2_REPLAY_V1 bundle and all V2-013 evidence are untouched."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import simulation.flatline_scenario_c_v2_013 as scen
from nhm.hashing import hash_file
from simulation.stream_runtime_v2013 import CHUNK_RECORDS, run_stream

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.json"
MANIFEST = ROOT / "tests/fixtures/e2e/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.manifest.json"
REPLAY_ID = "WEARABLE_SIM_V2_REPLAY_V2_FLATLINE"
KEYS = ("sequence_index", "window_id", "replay_id", "contract_version", "timestamp_us", "ecg",
        "ecg_quality", "ppg_context", "model_id")


def main() -> None:
    profile = scen.FULL_FLATLINE_PROFILE
    events = run_stream(scen.iter_flatline_records(profile), session_id=profile.session_id,
                        model_id="MODEL_V2_FINAL", replay_id=REPLAY_ID)
    bundle_events = [{k: e[k] for k in KEYS} for e in events]
    flat = [e for e in events if "FLATLINE" in e["diagnostics"]["quality_reasons"]]
    bundle = {"replay_id": REPLAY_ID, "window_count": len(bundle_events), "events": bundle_events,
              "provenance": scen.provenance(profile), "labels_included": False,
              "prediction_outcome_included": False, "simulation_truth_included": False,
              "source_participant_is_human": False}
    BUNDLE.write_text(json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n",
                      encoding="utf-8")
    counts: dict[str, int] = {}
    for e in events:
        counts[e["ecg_quality"]] = counts.get(e["ecg_quality"], 0) + 1
    MANIFEST.write_text(json.dumps({
        "fixture_id": REPLAY_ID, "supersedes": None,
        "relation": "additive successor scenario to WEARABLE_SIM_V2_REPLAY_V1 (which is preserved)",
        "purpose": "engineering-only software replay containing a true QUALITY_V1 flatline",
        "bundle_path": "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.json",
        "bundle_sha256": hash_file(BUNDLE),
        "events_semantic_sha256": hashlib.sha256(
            json.dumps(bundle_events, sort_keys=True).encode()).hexdigest(),
        "window_count": len(events), "ecg_quality_counts": counts,
        "flatline_reason_window_count": len(flat),
        "flatline_window_ids": [e["window_id"] for e in flat],
        "request_model_id": "MODEL_V2_FINAL", "chunk_records": CHUNK_RECORDS,
        "provenance": scen.provenance(profile), "protected_partitions_accessed": False,
        "scientific_metrics": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(len(events), counts, "flatline windows:", len(flat))


if __name__ == "__main__":
    main()
