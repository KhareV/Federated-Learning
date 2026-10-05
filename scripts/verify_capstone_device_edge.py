"""CAP-002 canonical device/edge replay runner (run once per fresh process).

``replay N`` replays the five frozen monitoring scenarios through VirtualEdgeNode ->
SimulatedWearableSource -> existing WearableStreamRuntime and writes
reports/capstone/cap_002/canonical_replay_run_N.json. Wall-clock runtime is printed, never stored.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from product.devices.replay import run_replay
from product.devices.scenarios import MONITORING_SCENARIO_IDS, load_scenarios

OUT = Path(__file__).resolve().parents[1] / "reports/capstone/cap_002"


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] != "replay":
        raise SystemExit("usage: verify_capstone_device_edge.py replay <run-number>")
    run_number = int(sys.argv[2])
    scenarios = load_scenarios()
    results = {}
    for scenario_id in MONITORING_SCENARIO_IDS:
        started = time.monotonic()
        results[scenario_id] = run_replay(scenarios[scenario_id])
        print(f"{scenario_id} {results[scenario_id]['semantic_digest']} "
              f"({time.monotonic() - started:.1f}s wall, not recorded)")
    payload = {"run": run_number, "replay_id": "CAPSTONE_DEVICE_REPLAY_V1",
               "scenarios": results,
               "digests": {k: v["semantic_digest"] for k, v in results.items()}}
    (OUT / f"canonical_replay_run_{run_number}.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
