# ruff: noqa: E501
"""CAP-004 mutation / negative controls. Each mutation is applied in place, the named targeted tests
must FAIL, and the original bytes are restored and verified (also via git). None is an equivalent
mutant: each changes observable behaviour or a statically checked property.
``--check`` only verifies that every mutation anchor exists (no file is touched, nothing is written).
Writes reports/capstone/cap_004/mutation_controls.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH_T = "tests/test_capstone_auth.py"
PERSIST_T = "tests/test_capstone_persistence.py"
SESSION_T = "tests/test_capstone_session_service.py"
RESTART_T = "tests/test_capstone_restart_recovery.py"
MUTATIONS = (
    ("DEMO_ACTIVATES_WITHOUT_ACK", "product/auth/base.py",
     "        if env.get(ENV_DEMO_ACK) != expected:\n", "        if False:\n", [AUTH_T]),
    ("CLERK_INVALID_TOKEN_ACCEPTED", "product/auth/clerk.py",
     '        if not getattr(state, "is_signed_in", False) or not isinstance(\n'
     '                getattr(state, "payload", None), dict):\n',
     '        if False:\n', [AUTH_T]),
    ("CROSS_USER_SESSION_READ_ACCEPTED", "product/sessions/service.py",
     "        if session.user_id != owner.user_id:\n", "        if False:\n", [SESSION_T]),
    ("DEVICE_SCENARIO_LOST_ON_RESTART", "product/persistence/recovery.py",
     '        scenario_id = row["scenario_id"]\n',
     '        scenario_id = "NORMAL_MONITORING"\n', [RESTART_T]),
    ("RUNTIME_IDENTITY_MUTABLE_IN_SQL", "product/persistence/schema.py",
     """        f"BEFORE UPDATE OF {', '.join(RUNTIME_COLUMNS)} ON monitoring_sessions "\n""",
     '        "BEFORE UPDATE OF created_at_us ON monitoring_sessions "\n', [PERSIST_T]),
    ("RAW_360HZ_TABLE_INTRODUCED", "product/persistence/schema.py",
     "    return statements\n",
     '    statements.append("CREATE TABLE raw_ecg_samples (sample_index INTEGER, ecg_raw INTEGER)")\n'
     "    return statements\n", [PERSIST_T]),
    ("QUALITY_WRITTEN_EVERY_WINDOW", "product/persistence/bridge.py",
     "                if self._last_quality.get(session_id) != state:  # CHANGE-ONLY storage\n",
     "                if True:  # CHANGE-ONLY storage\n", [PERSIST_T]),
    ("RAW_CONTEXT_OVERWRITTEN_BY_NORMALIZED", "product/persistence/bridge.py",
     "latency_ms=payload.latency_ms, raw_context=raw)\n",
     'latency_ms=payload.latency_ms, raw_context=(payload.context.model_dump(mode="json") if payload.context else raw))\n',
     [PERSIST_T]),
    ("STALE_MONITORING_SILENTLY_RESUMED", "product/persistence/store.py",
     '                    (SessionState.FAILED.value, now_us, row["session_id"]))\n',
     '                    (row["state"], now_us, row["session_id"]))\n', [RESTART_T]),
    ("FL_TABLE_RECEIVES_TRUTH_LABELS", "product/persistence/store.py",
     "    def insert_context_snapshot(self, *, session_id: str, sequence_index: int, timestamp_us: int,\n"
     "                                context: Mapping[str, Any]) -> None:\n",
     "    def insert_context_snapshot(self, *, session_id: str, sequence_index: int, timestamp_us: int,\n"
     "                                context: Mapping[str, Any]) -> None:\n"
     "        self._run(\n"
     '            "INSERT OR IGNORE INTO session_summaries (session_id, summary_version, duration_ms,"\n'
     '            " windows_inferred, state_counts_json, quality_counts_json, reconnect_count,"\n'
     '            " disconnect_count, generated_at_us) VALUES (?, \'truth_label\', 0, 0, \'{}\',"\n'
     '            " \'{}\', 0, 0, 0)", (session_id,))\n',
     [PERSIST_T, SESSION_T]),
)


def main() -> int:
    if "--check" in sys.argv:
        bad = [name for name, rel, old, _n, _t in MUTATIONS if old not in (ROOT / rel).read_text()]
        print(json.dumps({"mutations": len(MUTATIONS), "missing_anchor": bad}))
        return 1 if bad else 0
    results = []
    for name, rel, old, new, tests in MUTATIONS:
        path = ROOT / rel
        original = path.read_bytes()
        text = original.decode()
        assert old in text, name
        try:
            path.write_text(text.replace(old, new, 1))
            run = subprocess.run(
                [sys.executable, "-m", "pytest", *tests, "-x", "-q", "-p", "no:cacheprovider",
                 "-W", "ignore::DeprecationWarning"], cwd=ROOT, capture_output=True, text=True,
                env={**os.environ, "PYTHONPATH": "src:."})
            failed = run.returncode != 0
            first = [ln for ln in run.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))][:1]
        finally:
            path.write_bytes(original)
        clean = subprocess.run(["git", "status", "--short", "--", rel], cwd=ROOT, check=True,
                               capture_output=True, text=True).stdout.strip()
        results.append({"mutation": name, "file": rel, "tests_run": tests,
                        "suite_failed_as_designed": failed,
                        "first_failing_test": first[0] if first else None,
                        "file_restored_byte_identical": path.read_bytes() == original,
                        "git_status_of_file_after_restore": clean})
        print(name, failed, first[:1], flush=True)
    payload = {"controls": results,
               "all_caught": all(r["suite_failed_as_designed"] for r in results),
               "all_restored": all(r["file_restored_byte_identical"] for r in results)}
    (ROOT / "reports/capstone/cap_004/mutation_controls.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
