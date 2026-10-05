"""CAP-002 mutation / negative controls. Each mutation is applied to a CAP-002 module in place, the
targeted suite must FAIL, and the original bytes are restored (and verified) in a finally block.
Writes reports/capstone/cap_002/mutation_controls.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = "product/devices/simulated.py"
SUITE = ["tests/test_capstone_simulated_device.py", "tests/test_capstone_virtual_edge.py",
         "tests/test_capstone_device_replay.py", "-x", "-q", "-p", "no:cacheprovider"]
MUTATIONS = (
    ("ILLEGAL_LIFECYCLE_TRANSITION_ACCEPTED", SIM,
     "        validate_device_transition(self._state, new_state)  # raises, state unchanged\n", ""),
    ("SIMULATION_TRUTH_LEAKAGE", SIM, "import asyncio\n",
     "import asyncio\nfrom simulation.types import SimulationTruth  # MUTATION\n"),
    ("SCENARIO_NONDETERMINISM", SIM, "self._sequence * PRE_STREAM_TICK_US)",
     "self._sequence * PRE_STREAM_TICK_US + time.time_ns() % 7)"),
    ("RECORD_DELIVERED_DURING_OUTAGE", SIM,
     '            yield ("record", record, record.timestamp_us)\n',
     '            yield ("record", record, record.timestamp_us)\n'
     "            if outages and record.sample_index == outages[0][0] - 1:\n"
     "                from dataclasses import replace\n"
     '                yield ("record", replace(record, sample_index=record.sample_index + 1,'
     " timestamp_us=record.timestamp_us + 3000), record.timestamp_us)\n"),
    ("WRONG_OBSERVED_RECORD_TYPE", SIM, "            self._records.append(payload)",
     "            self._records.append(payload.to_canonical_dict())"),
    ("NON_MONOTONIC_RECORD_SEQUENCE", SIM, "            self._records.append(payload)",
     "            self._records.appendleft(payload)"),
)


def main() -> int:
    results = []
    for name, rel, old, new in MUTATIONS:
        path = ROOT / rel
        original = path.read_bytes()
        text = original.decode()
        assert old in text, name
        try:
            path.write_text(text.replace(old, new, 1))
            run = subprocess.run([sys.executable, "-m", "pytest", *SUITE], cwd=ROOT,
                                 capture_output=True, text=True,
                                 env={**os.environ, "PYTHONPATH": "src:."})
            failed = run.returncode != 0
            tail = [line for line in run.stdout.splitlines() if line.startswith("FAILED")][:1]
        finally:
            path.write_bytes(original)
        clean = subprocess.run(["git", "status", "--short", "--", rel], cwd=ROOT, check=True,
                               capture_output=True, text=True).stdout.strip()
        results.append({"mutation": name, "file": rel, "suite_failed_as_designed": failed,
                        "first_failing_test": tail[0] if tail else None,
                        "file_restored_byte_identical": path.read_bytes() == original,
                        "git_status_of_file_after_restore": clean})
    payload = {"controls": results,
               "all_caught": all(r["suite_failed_as_designed"] for r in results),
               "all_restored": all(r["file_restored_byte_identical"] for r in results),
               "in_test_controls": ["checker negative controls (ordering, types, outage delivery)",
                                    "truth scanner planted-leakage cases",
                                    "replay-digest event-order sensitivity"]}
    (ROOT / "reports/capstone/cap_002/mutation_controls.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
