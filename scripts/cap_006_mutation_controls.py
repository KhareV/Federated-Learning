# ruff: noqa: E501
"""CAP-006 mutation / negative controls. Each mutation is applied in place, the named test files must FAIL
(first failures recorded - collection errors do not count), and the original bytes are restored and verified
(also via git). None is an equivalent mutant. ``--check`` only verifies the anchors and that every mutated
source still parses. Writes reports/capstone/cap_006/mutation_controls.json."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUF_T = "tests/test_capstone_local_training_buffer.py"
CLI_T = "tests/test_capstone_fl_client_adapter.py"
BRG_T = "tests/test_capstone_local_update_bridge.py"
REP_T = "tests/test_capstone_local_training_repro.py"
BUF = "product/edge/local_training_buffer.py"
CLI = "product/federation/client.py"
BRG = "product/federation/update_bridge.py"
MUTATIONS = (
    ("MODEL_PREDICTION_LABEL_ACCEPTED", BUF, "            if source in forbidden:\n", "            if False:\n", [BUF_T]),
    ("SIMULATION_TRUTH_ADDED_TO_UPDATE_ENVELOPE", CLI,
     "            if scan_forbidden(envelope):\n",
     "            envelope[\"simulation_truth\"] = {\"event_schedule\": [1]}\n            if scan_forbidden(envelope):\n", [CLI_T, BRG_T]),
    ("LABEL_ADDED_TO_UPDATE_SUBMISSION", BRG,
     "                        \"update_digest\": \"update_sha256\", \"examples_seen\": \"examples_seen\"}\n",
     "                        \"update_digest\": \"update_sha256\", \"examples_seen\": \"examples_seen\", \"labels\": \"examples_seen\"}\n", [BRG_T]),
    ("RAW_ECG_ARRAY_ADDED_TO_SERVER_ENVELOPE", CLI,
     "            if scan_forbidden(envelope):\n",
     "            envelope[\"payload\"][\"preview\"] = np.array(inputs[:4], copy=True)\n            if scan_forbidden(envelope):\n", [CLI_T, BRG_T]),
    ("CROSS_CLIENT_MODEL_INPUT_LOOKUP_ALLOWED", BUF,
     "        if requester_client_id != self._client_id:\n            raise BufferError(\"CROSS_CLIENT_INPUT_ACCESS\")\n        if ref not in self._private:\n",
     "        if False:\n            raise BufferError(\"CROSS_CLIENT_INPUT_ACCESS\")\n        if ref not in self._private:\n", [BUF_T]),
    ("MODEL_V2_FINAL_ACCEPTED_AS_FL_BASE", CLI,
     "ALLOWED_BASE_MODEL_IDS = (\"FL_INIT_V2\",)", "ALLOWED_BASE_MODEL_IDS = (\"FL_INIT_V2\", \"MODEL_V2_FINAL\")", [CLI_T]),
    ("WRONG_BASE_STATE_DIGEST_ACCEPTED", CLI, "        if base_state_digest != self._base_sha:\n", "        if False:\n", [CLI_T]),
    ("UPDATE_DIGEST_MISMATCH_ACCEPTED", CLI,
     "            if delta_sha(envelope[\"payload\"][\"delta\"]) != envelope[\"update_sha256\"]:\n", "            if False:\n", [CLI_T]),
    ("FEDPROX_MU_CHANGED_FROM_FROZEN_VALUE", CLI,
     "    return float(json.loads(MU_LOCK.read_text())[\"selected_mu\"])", "    return float(json.loads(MU_LOCK.read_text())[\"selected_mu\"]) * 10", [CLI_T]),
    ("AGGREGATE_WEIGHTED_DELTAS_INVOKED_DURING_LOCAL_TRAINING", CLI,
     "        self._result, self._envelope, self._round = result, envelope, round_id\n",
     "        __import__(\"federated.aggregation\", fromlist=[\"x\"]).aggregate_weighted_deltas([result.update])\n        self._result, self._envelope, self._round = result, envelope, round_id\n", [CLI_T, REP_T, BRG_T]),
)


def main() -> int:
    if "--check" in sys.argv:
        bad, syntax = [], []
        for name, rel, old, new, _t in MUTATIONS:
            text = (ROOT / rel).read_text()
            if old not in text:
                bad.append(name)
            else:
                try:
                    ast.parse(text.replace(old, new, 1))
                except SyntaxError:
                    syntax.append(name)
        print(json.dumps({"mutations": len(MUTATIONS), "missing_anchor": bad, "syntax_errors": syntax}))
        return 1 if bad or syntax else 0
    results = []
    for name, rel, old, new, tests in MUTATIONS:
        path = ROOT / rel
        original = path.read_bytes()
        text = original.decode()
        assert old in text, name
        try:
            path.write_text(text.replace(old, new, 1))
            run = subprocess.run([sys.executable, "-m", "pytest", *tests, "-x", "-q", "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning"],
                                 cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src:."})
            failed = run.returncode != 0
            first = [ln for ln in run.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))][:1]
        finally:
            path.write_bytes(original)
        clean = subprocess.run(["git", "status", "--short", "--", rel], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        results.append({"mutation": name, "file": rel, "tests_run": tests, "suite_failed_as_designed": failed,
                        "first_failing_test": first[0] if first else None,
                        "caught_by_a_test_not_a_collection_error": bool(first) and first[0].startswith("FAILED"),
                        "file_restored_byte_identical": path.read_bytes() == original, "git_status_of_file_after_restore": clean})
        print(name, failed, first[:1], flush=True)
    payload = {"controls": results, "all_caught": all(r["suite_failed_as_designed"] and r["caught_by_a_test_not_a_collection_error"] for r in results),
               "all_restored": all(r["file_restored_byte_identical"] for r in results)}
    (ROOT / "reports/capstone/cap_006/mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
