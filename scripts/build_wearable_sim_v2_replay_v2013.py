#!/usr/bin/env python3
"""V2-013: (1) mechanically audit WEARABLE_SIM_V1 maturity AT ENTRY (git HEAD state, before the
V2-013 extension), (2) materialize the deterministic V2 integration profile/session manifest, and
(3) run the canonical-stream -> streaming-preprocessing -> window/quality/context chain to build the
WEARABLE_SIM_V2_REPLAY_V1 request bundle (frontend/static/replay) + manifest. Runs the simulator
and the preprocessing chain only: no model, no API, no dataset, no scientific metric. Deterministic
and frozen BEFORE any replay result exists."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import simulation.profile_v2013 as prof
from nhm.hashing import hash_file
from simulation.stream_runtime_v2013 import CHUNK_RECORDS, run_stream

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_013"
BUNDLE = ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json"
MANIFEST = ROOT / "tests/fixtures/e2e/WEARABLE_SIM_V2_REPLAY_V1.manifest.json"
REPLAY_ID = "WEARABLE_SIM_V2_REPLAY_V1"
ENTRY = "40e127308b50bb4d5943826639d467203b9b4b29"
BUNDLE_KEYS = ("sequence_index", "window_id", "replay_id", "contract_version", "timestamp_us",
               "ecg", "ecg_quality", "ppg_context", "model_id")


def _git_files(pattern: str) -> list[str]:
    out = subprocess.run(["git", "grep", "-l", pattern, ENTRY, "--", "*.py"], cwd=ROOT,
                         capture_output=True, text=True, check=False).stdout.split()
    return sorted(line.split(":", 1)[1] for line in out)


def maturity_audit() -> dict:
    modes = {}
    config_modes = ["SYNTHETIC_PHYSIOLOGY", "MITDB_REPLAY", "BIDMC_REPLAY", "FAULT_INJECTION",
                    "LONGITUDINAL_COHORT", "LIVE_SPEED_REPLAY", "ACCELERATED_REPLAY"]
    non_test = lambda files: [f for f in files if not f.startswith("tests/")]  # noqa: E731
    for mode in config_modes:
        files = _git_files(mode)
        modes[mode] = {"python_files_naming_it_at_entry": files,
                       "non_test_implementation_files": non_test(files)}
    classification = {
        "SYNTHETIC_PHYSIOLOGY": "PARTIAL",
        "MITDB_REPLAY": "CONTRACT_ONLY",
        "BIDMC_REPLAY": "CONTRACT_ONLY",
        "FAULT_INJECTION": "PARTIAL",
        "LONGITUDINAL_COHORT": "MISSING",
        "LIVE_SPEED_REPLAY": "CONTRACT_ONLY",
        "ACCELERATED_REPLAY": "CONTRACT_ONLY",
    }
    reasons = {
        "SYNTHETIC_PHYSIOLOGY": "simulation/wearable.py generates SPARSE smoke samples (2 per "
        "segment, integer ecg_raw ~2200, no waveform morphology, no streaming rate); T004/T005 "
        "explicitly deferred full morphology synthesis",
        "MITDB_REPLAY": "named only in the contract/deferral scripts/tests; the T034 public "
        "replay is a frozen NPZ outside the simulator, not a simulator mode",
        "BIDMC_REPLAY": "contract/deferral/test names only; BIDMC context code lives in "
        "evaluation/bidmc_context*.py outside the simulator",
        "FAULT_INJECTION": "simulation/quality_perturbations.py (T023) perturbs BIDMC/ECG arrays "
        "for the quality-aware experiment; not wired into the simulator sample stream",
        "LONGITUDINAL_COHORT": "no implementation; simulation.profiles.IMPLEMENTED_PROFILES == "
        "(WEARABLE_SIM_SMOKE,)",
        "LIVE_SPEED_REPLAY": "contract name only (the T034 frontend 'speed=1' pacing is a UI "
        "presentation option, not a simulator replay mode)",
        "ACCELERATED_REPLAY": "contract name only",
    }
    data = {
        "audited_commit": ENTRY,
        "inspected": ["contracts/WEARABLE_SIM_V1.md", "configs/simulation/WEARABLE_SIM_V1.yaml",
                      "simulation/", "tests/fixtures/session_v1*", "reports/t004/",
                      "reports/t005/", "scripts/build_wearable_sim_replay_t034.py",
                      "simulation/quality_perturbations.py", "scripts/run_replay.py"],
        "implemented_profiles_at_entry": ["WEARABLE_SIM_SMOKE"],
        "config_status_at_entry": "CONTRACT_ONLY",
        "modes": {m: {"classification": classification[m], "reason": reasons[m], **modes[m]}
                  for m in config_modes},
        "implemented": [], "partial": ["SYNTHETIC_PHYSIOLOGY", "FAULT_INJECTION"],
        "contract_only": ["MITDB_REPLAY", "BIDMC_REPLAY", "LIVE_SPEED_REPLAY",
                          "ACCELERATED_REPLAY"],
        "missing": ["LONGITUDINAL_COHORT"], "obsolete": [],
        "existing_t034_wearable_sim_replay": "WEARABLE_SIM_REPLAY_V1 = 3 segment-flat windows "
        "(NORMAL / CONTEXT_UNAVAILABLE / UNUSABLE) built from the smoke kernel; kept untouched",
        "no_duplication_of_existing_functionality": True,
        "known_quality_v1_observation": "QUALITY_V1 flatline test needs numerical flatness "
        "(std/rms<=1e-12); a SOURCE-level flat segment decays through the causal band-pass and "
        "is not flagged, so the V2-013 UNUSABLE scenarios use sensor dropout / gaps / ADC-rail "
        "clipping instead; recommended for V2-SIM-001, frozen QUALITY_V1 NOT changed",
        "status": "PASS",
    }
    (OUT / "simulator_maturity_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def build() -> dict:
    profile = prof.FULL_PROFILE
    events = run_stream(prof.iter_observed_records(profile), session_id=profile.session_id,
                        model_id="MODEL_V2_FINAL", replay_id=REPLAY_ID)
    bundle_events = [{k: e[k] for k in BUNDLE_KEYS} for e in events]
    bundle = {"replay_id": REPLAY_ID, "window_count": len(bundle_events), "events": bundle_events,
              "provenance": prof.provenance(profile), "labels_included": False,
              "prediction_outcome_included": False, "simulation_truth_included": False,
              "source_participant_is_human": False}
    BUNDLE.write_text(json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n",
                      encoding="utf-8")
    kinds = {}
    for e in events:
        kinds[e["ecg_quality"]] = kinds.get(e["ecg_quality"], 0) + 1
    sha = hashlib.sha256(json.dumps(bundle_events, sort_keys=True).encode()).hexdigest()
    manifest = {
        "fixture_id": REPLAY_ID,
        "purpose": "deterministic ENGINEERING-ONLY simulated-wearable software replay for "
        "API_RUNTIME_V2 dashboard E2E; NOT clinical, NOT real-wearable evidence",
        "bundle_path": "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json",
        "bundle_sha256": hash_file(BUNDLE), "events_semantic_sha256": sha,
        "window_count": len(events), "ecg_quality_counts": kinds,
        "request_model_id": "MODEL_V2_FINAL",
        "chain": "WEARABLE_SIM_V1 ObservedRecord stream (360 Hz) -> GAP_POLICY_V1 -> stateful "
        "360->250 Hz resampler -> causal ECG band-pass -> 10 s windows @ 5 s cadence -> "
        "QUALITY_V1 -> causal context alignment",
        "first_right_edge_us": 15_000_000, "cadence_us": 5_000_000,
        "chunk_records": CHUNK_RECORDS,
        "provenance": prof.provenance(profile),
        "protected_partitions_accessed": False, "scientific_metrics": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scenario = {
        "profile_id": profile.profile_id, "session_id": profile.session_id,
        "duration_s": profile.duration_s, "seed": profile.seed,
        "source_rate_hz": prof.SOURCE_RATE_HZ, "adc_rail_counts": prof.ADC_RAIL_COUNTS,
        "sim_ecg_counts_per_mv": prof.SIM_ECG_COUNTS_PER_MV,
        "faults": [vars(f) for f in profile.faults],
        "context_schedule": [vars(c) for c in profile.context],
        "scenarios_exercised": ["clean monitoring", "valid ECG + valid context",
                                "valid ECG + missing PPG", "valid ECG + invalid SpO2",
                                "ECG/PPG rate disagreement", "DEGRADED ECG (short gap)",
                                "UNUSABLE ECG (long gap / sensor dropout / clipping)",
                                "long-gap segment reset", "transport dropped chunk"],
        "state_machine_scenarios_via_separate_fixtures": [
            "two consecutive above-threshold windows", "episode opening", "two below",
            "episode closure", "cooldown", "post-cooldown recovery", "SYSTEM_ERROR path"],
        "episode_scores_forced_by_simulator": False,
        "provenance": prof.provenance(profile),
    }
    (OUT / "simulation_profile.json").write_text(
        json.dumps(scenario, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "simulation_session_manifest.json").write_text(json.dumps({
        **manifest, "diagnostics_per_window": [
            {"sequence_index": e["sequence_index"], "timestamp_us": e["timestamp_us"],
             "ecg_quality": e["ecg_quality"], **e["diagnostics"]} for e in events]},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    maturity_audit()
    print(json.dumps(build(), indent=1, sort_keys=True)[:600])
