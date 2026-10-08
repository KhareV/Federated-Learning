# ruff: noqa: E501
"""Run the 10-round experiment.   python -m scripts.run_fl10 --mode A|B --out DIR [--run-id ID]
Mode A: canonical eight-client synthetic cohort (reference; must reproduce R0-R3 exactly).
Mode B: ONE live monitoring session (real released inference) -> SITE_00's verified buffer (reused for all ten rounds) + seven synthetic peers; trainer inputs are traced to the monitored windows.
No fresh-holdout prediction is computed here."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from federated.wearable_fl_runner_v1 import build_cohort
from final_showcase import link_trace
from final_showcase import live_link as ll
from fl10 import runner
from fl10.trace import Fl10TrainerTap
from simulation.fl_cohort_v1 import cohort_profiles

ROOT = Path(__file__).resolve().parents[1]


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def protocol_sha() -> str:
    return hashlib.sha256((ROOT / "configs/fl10/protocol_v1.json").read_bytes()).hexdigest()


def manifest_for(datasets) -> dict:
    return {d.client_id: {"participant_id": d.participant_id, "session_id": d.session_id, "dataset_sha": d.dataset_sha256} for d in datasets}


def mode_a(out: Path, run_id: str) -> dict:
    _, datasets, manifest = build_cohort()
    return runner.run_training(mode="A", run_id=run_id, out_dir=out, datasets=datasets, manifest=manifest, git_commit=git_head(), protocol_sha256=protocol_sha())


def mode_b(out: Path, run_id: str, inference_url: str) -> dict:
    from product.inference.client import CapstoneInferenceClient

    profile = cohort_profiles()[0]
    _, datasets, _ = build_cohort()
    canonical_site00 = datasets[0]
    monitored = asyncio.run(ll.monitor_site00(lambda: CapstoneInferenceClient(inference_url), session_id=f"LIVELINK-{run_id}"))
    live = ll.dataset_from_windows(monitored["windows"], profile)
    parity = ll.parity(monitored, live, profile, canonical_site00.dataset_sha256)
    datasets = [live, *datasets[1:]]
    expected = link_trace.expected_trace(live)
    tap = Fl10TrainerTap()
    with tap:
        report = runner.run_training(mode="B", run_id=run_id, out_dir=out, datasets=datasets, manifest=manifest_for(datasets), require_prefix_parity=False, git_commit=git_head(), protocol_sha256=protocol_sha())
    from product.edge.local_training_buffer import LocalTrainingBufferV1

    buffer = LocalTrainingBufferV1(live.client_id, live.participant_id)
    buffer.ingest_dataset(live)
    trace = link_trace.verify_trace(expected, link_trace.buffer_trace(buffer), tap.calls, client_id=live.client_id, rounds=10)
    link = {"label": "LIVE-MONITORED SIMULATED ECG — NOT A REAL PHYSIOLOGICAL PATIENT", "monitoring": {k: v for k, v in monitored.items() if k != "windows"}, "parity": parity, "trace": {**trace, "window_identities": expected["windows"][:3],
            "window_identity_count": len(expected["windows"])}, "monitoring_sessions_executed": 1, "buffer_reused_for_rounds": 10, "site00_source": "LIVE_MONITORED_WINDOWS",
            "prefix_equals_frozen_reference": report["prefix_equals_frozen_reference"], "states_equal_mode_a": None}
    (out / "monitoring_link.json").write_text(json.dumps(link, indent=1, sort_keys=True, default=str) + "\n")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("A", "B"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run-id")
    a = ap.parse_args()
    out = Path(a.out)
    run_id = a.run_id or f"FL10_MODE_{a.mode}_RUN_01"
    if (out / "run_report.json").exists():
        raise SystemExit("REFUSING_TO_OVERWRITE_EXISTING_RUN")
    if a.mode == "A":
        report = mode_a(out, run_id)
    else:
        from scripts.run_capstone_monitoring_e2e import launch_released_inference

        with launch_released_inference() as (base, _info):
            report = mode_b(out, run_id, base)
    print(json.dumps({"status": report["status"], "rounds": report["rounds_committed"], "accepted_updates": report["accepted_updates_total"], "exposures": report["example_exposures_total"],
                      "candidate": report["candidate"]["state_sha256"], "prefix": report["prefix_equals_frozen_reference"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
