# ruff: noqa: E501
"""CAP-007 mutation / negative controls. Each mutation (one or more edits) is applied in place, the named
tests must FAIL (first failures recorded - a collection error does not count), and the original bytes are
restored and verified (also via git). None is an equivalent mutant. ``--check`` only verifies the anchors
and that every mutated source still parses. Writes reports/capstone/cap_007/mutation_controls.json."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVC_T = "tests/test_capstone_federation_service.py"
MULTI_T = "tests/test_capstone_federation_multiround.py"
API_T = "tests/test_capstone_federation_api.py"
REG_T = "tests/test_capstone_candidate_registry.py"
GOV_T = "tests/test_capstone_candidate_governance.py"
REPLAY_T = "tests/test_capstone_federation_replay.py"
SEC_T = "tests/test_capstone_secagg_integration.py"
ISO_T = "tests/test_capstone_federation_isolation.py"
BIND = "product/federation/execution_binding.py"
SVC = "product/federation/service.py"
STORE = "capstone_persistence/federation_store.py"
GOV = "product/models/governance.py"
SEC = "product/federation/secagg_shadow.py"
SESSION = "product/session.py"
LINEAGE_T = f"{SVC_T}::test_round_two_cannot_start_from_fl_init_and_model_v2_final_is_never_a_base"
SHAPE_T = f"{SVC_T}::test_canonical_fedavg_run_shape"
MUTATIONS = (
    ("ROUND_2_STARTS_FROM_FL_INIT", [(BIND, "    expected = frozen_fl_init_sha() if round_id == 1 else committed.get(round_id - 1)\n",
                                     "    expected = frozen_fl_init_sha()\n")], [LINEAGE_T]),
    ("THREE_CANDIDATES_PER_RUN", [(BIND, "        if not final_round and new is RoundState.CANDIDATE_CREATED:\n", "        if False:\n"),
                                  (SVC, "        if not final:\n            self._round_event(ctx, tracker, round_id, RoundState.COMPLETED, len(coordinator.accepted))\n",
                                   "        if False:\n            self._round_event(ctx, tracker, round_id, RoundState.COMPLETED, len(coordinator.accepted))\n")],
     [SHAPE_T, f"{MULTI_T}::test_each_round_starts_from_the_previous_committed_state_and_the_candidate_is_the_round_3_state"]),
    ("MODEL_V2_FINAL_ACCEPTED_AS_BASE", [(BIND, "    if base_model_id != RUN_BASE_MODEL_ID:\n", "    if False:\n")], [LINEAGE_T]),
    ("UPDATE_OMITTED_FROM_ROUND", [(SVC, "        for cid, adapter in adapters.items():\n            count = adapter._buffer.eligible_count()\n",
                                   "        for cid, adapter in list(adapters.items())[:-1]:\n            count = adapter._buffer.eligible_count()\n")], [SHAPE_T]),
    ("LABEL_ADDED_TO_SUBMITTED_ENVELOPE", [(SVC, "            envelopes[cid], published[cid] = envelope, envelope[\"update_sha256\"]\n",
                                           "            envelope[\"labels\"] = [0, 1]\n            envelopes[cid], published[cid] = envelope, envelope[\"update_sha256\"]\n")], [SHAPE_T]),
    ("PRODUCTION_DEPLOYED_TRUE", [(STORE, "\"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)\"", "\"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)\"")],
     [f"{REG_T}::test_first_candidate_is_0001_with_fl_init_parent_and_sandbox_unreachable_defaults"]),
    ("CANDIDATE_IN_DEFAULT_RUNTIME_BINDING", [(SESSION, "def default_runtime_identity() -> RuntimeIdentity:\n",
                                              "CANDIDATE_REF = \"CAPSTONE_FL_CANDIDATE_0001\"\n\n\ndef default_runtime_identity() -> RuntimeIdentity:\n")],
     [f"{ISO_T}::test_the_released_default_runtime_is_unchanged_and_names_no_candidate"]),
    ("ACCEPT_DESPITE_FAILED_CHECK", [(GOV, "        passed = len(checks) == len(CHECK_IDS) and all(c[\"passed\"] for c in checks) and (\n            tuple(c[\"check_id\"] for c in checks) == CHECK_IDS)\n",
                                    "        passed = True\n")], [f"{GOV_T}::test_a_failed_check_rejects_the_candidate_and_it_never_reaches_the_sandbox"]),
    ("SECAGG_TOLERANCE_WIDENED", [(SEC, "EXPECTED = {\"clients\": 8, \"max_weight\": 256.0,", "EXPECTED = {\"clients\": 8, \"max_weight\": 512.0,")],
     [f"{SEC_T}::test_the_frozen_tolerances_and_expectations_are_untouched"]),
    ("REPLAY_TRAINS", [(SVC, "        coro = self._live(ctx, None) if live else self._replay(ctx)\n", "        coro = self._live(ctx, None)\n")],
     [f"{REPLAY_T}::test_replay_reproduces_the_source_stream_with_zero_training_and_zero_new_candidates"]),
    ("CROSS_USER_ACCESS_ALLOWED", [(SVC, "        if row[\"user_id\"] != user_id:\n            raise ProductError(ProductErrorCode.FORBIDDEN, \"not the owner of this federation run\")\n",
                                   "        if False:\n            raise ProductError(ProductErrorCode.FORBIDDEN, \"not the owner of this federation run\")\n")],
     [f"{API_T}::test_run_ownership_for_get_list_rounds_and_start"]),
    ("SECOND_SIMULTANEOUS_LIVE_RUN", [(SVC, "        if self._active is not None or others:\n", "        if False:\n")],
     [f"{API_T}::test_start_returns_promptly_and_a_second_live_run_is_refused_while_one_is_active"]),
)


def apply(text: str, old: str, new: str) -> str:
    assert old in text
    return text.replace(old, new, 1)


def main() -> int:
    if "--check" in sys.argv:
        bad, syntax = [], []
        for name, edits, _t in MUTATIONS:
            for rel, old, new in edits:
                text = (ROOT / rel).read_text()
                if old not in text:
                    bad.append(f"{name}:{rel}")
                    continue
                try:
                    ast.parse(apply(text, old, new))
                except SyntaxError:
                    syntax.append(name)
        print(json.dumps({"mutations": len(MUTATIONS), "missing_anchor": bad, "syntax_errors": syntax}))
        return 1 if bad or syntax else 0
    results = []
    for name, edits, tests in MUTATIONS:
        originals = {rel: (ROOT / rel).read_bytes() for rel, _o, _n in edits}
        try:
            for rel, old, new in edits:
                path = ROOT / rel
                path.write_text(apply(path.read_text(), old, new))
            run = subprocess.run([sys.executable, "-m", "pytest", *tests, "-x", "-q", "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning"],
                                 cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src:."})
            failed = run.returncode != 0
            first = [ln for ln in run.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))][:1]
        finally:
            for rel, data in originals.items():
                (ROOT / rel).write_bytes(data)
        clean = subprocess.run(["git", "status", "--short", "--", *originals], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        results.append({"mutation": name, "files": sorted(originals), "tests_run": tests, "suite_failed_as_designed": failed,
                        "first_failing_test": first[0] if first else None,
                        "caught_by_a_test_not_a_collection_error": bool(first) and first[0].startswith("FAILED"),
                        "files_restored_byte_identical": all((ROOT / rel).read_bytes() == data for rel, data in originals.items()),
                        "git_status_of_files_after_restore": clean})
        print(name, failed, first[:1], flush=True)
    payload = {"controls": results, "all_caught": all(r["suite_failed_as_designed"] and r["caught_by_a_test_not_a_collection_error"] for r in results),
               "all_restored": all(r["files_restored_byte_identical"] for r in results)}
    (ROOT / "reports/capstone/cap_007/mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
