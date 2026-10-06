# ruff: noqa: E501
"""CAP-010 mutation / negative controls. Each (non-equivalent) mutation is applied in place, the named tests must FAIL (first
failing test recorded; a collection/syntax error does not count), then the original bytes are restored and verified (also via
git). Mutations never start a real stack: the selected tests are unit tests with real tiny services only.
``--check`` verifies anchors only. Writes reports/capstone/cap_010/mutation_controls.json."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("CAP010_OUT", ROOT / "reports/capstone/cap_010"))
L, W = "scripts/run_capstone_faculty_demo.py", "scripts/capstone_demo_workspace.py"
RB, DRV, RUN = "docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md", "scripts/cap_010_cdp_driver.mjs", "scripts/run_capstone_full_demo_e2e.py"
ORC, WT, FD = "tests/test_capstone_demo_orchestrator.py", "tests/test_capstone_demo_workspace.py", "tests/test_capstone_full_demo.py"
RUNBOOK_TESTS = [f"{FD}::test_runbook_claim_audit_finds_no_overclaim", f"{FD}::test_runbook_has_required_statements_and_both_paths"]
MUTATIONS = (
    ("LAUNCHER_USES_ROLLBACK_V1", [(L, '"--profile", "default",', '"--profile", "rollback-v1",')], [f"{ORC}::test_the_faculty_stack_is_exactly_three_services_with_the_default_runtime_only"]),
    ("START_WITHOUT_DEMO_ACK", [(L, "    if not args.acknowledge_demo_auth:\n", "    if False:\n")], [f"{ORC}::test_missing_acknowledgement_refuses_even_in_preflight_only_mode"]),
    ("READY_BEFORE_SERVICE_READINESS", [(L, "                ok, _detail = spec.ready()\n", '                ok, _detail = True, ""\n')], [f"{ORC}::test_ready_only_after_every_service_answers_and_shutdown_is_reverse_ordered"]),
    ("RESET_WITHOUT_SENTINEL", [(W, "        read_sentinel(resolved)  # raises without a valid sentinel\n", "        pass\n")], [f"{WT}::test_unsafe_reset_targets_are_rejected_and_nothing_is_deleted[RANDOM_NO_SENTINEL]"]),
    ("REPO_ROOT_ACCEPTED_AS_RESET_TARGET", [(W, "    if resolved == ROOT or resolved in ROOT.parents or ROOT in resolved.parents:\n", "    if False:\n")],
     [f"{WT}::test_unsafe_reset_targets_are_rejected_and_nothing_is_deleted[ROOT]", f"{WT}::test_unsafe_reset_targets_are_rejected_and_nothing_is_deleted[ROOT_PARENT]"]),
    ("PREWARM_CREATES_FEDERATION_RUN", [(L, '    clients = httpx.get(f"{base}/federation/clients", timeout=300).json()\n', '    clients = httpx.get(f"{base}/federation/clients", timeout=300).json()\n    httpx.post(f"{base}/federation/runs", json={})\n')],
     [f"{ORC}::test_prewarm_is_a_read_only_preparation_with_an_audited_zero_side_effect_report"]),
    ("PREWARM_STARTS_A_RUN", [(L, '    clients = httpx.get(f"{base}/federation/clients", timeout=300).json()\n', '    clients = httpx.get(f"{base}/federation/clients", timeout=300).json()\n    httpx.post(f"{base}/federation/runs/X/start")\n')],
     [f"{ORC}::test_prewarm_is_a_read_only_preparation_with_an_audited_zero_side_effect_report", f"{ORC}::test_the_launcher_never_issues_a_write_request_and_has_no_package_manager_calls"]),
    ("RUNBOOK_SAYS_PHYSICAL_HARDWARE_CONNECTED", [(RB, "The device is simulated. It enters", "The physical wearable is connected. It enters")], RUNBOOK_TESTS),
    ("RUNBOOK_SAYS_EIGHT_HOSPITALS", [(RB, "These eight clients are synthetic research partitions running logically on one laptop.", "These eight clients are hospitals running at eight sites.")], RUNBOOK_TESTS),
    ("RUNBOOK_SAYS_SECAGG_PROVIDES_DP", [(RB, "it is not differential privacy and gives no anonymity guarantee", "it provides differential privacy and anonymity")], RUNBOOK_TESTS),
    ("RUNBOOK_SAYS_CANDIDATE_DEPLOYED", [(RB, "It is never automatically deployed, and MODEL_V2_FINAL is still the released default.", "It is deployed automatically, and MODEL_V2_FINAL is still the released default.")], RUNBOOK_TESTS),
    ("RUNBOOK_SAYS_USER_SESSION_TRAINS_PERSONAL_MODEL", [(RB, "There is no personal model and no continuous learning.", "The user session trains a personal model.")], RUNBOOK_TESTS),
    ("RUNBOOK_DESCRIBES_REPLAY_AS_TRAINING", [(RB, "the UI says NO TRAINING IS EXECUTING and it creates no candidate, no governance decision and no training", "the UI says training in progress and it creates candidates")], RUNBOOK_TESTS),
    ("CANDIDATE_BECOMES_MONITORING_DEFAULT", [(L, '"model_id": "MODEL_V2_FINAL", "persistence_mode"', '"model_id": "CAPSTONE_FL_CANDIDATE_0001", "persistence_mode"')], [f"{ORC}::test_product_readiness_probe_demands_the_exact_identity"]),
    ("HERO_PATH_USES_FAKE_BACKEND", [(DRV, "void cdp.send(allowed ? 'Fetch.continueRequest'", "void cdp.send(allowed ? 'Fetch.fulfillRequest'")], [f"{FD}::test_hero_path_uses_the_real_stack_without_mocks"]),
    ("MODEL_OUTCOME_HARDCODED_INTO_EXPECTATION", [(RUN, '"inference_ran": r["inference_results"] > 0}', '"inference_ran": r["inference_results"] > 0, "positive_state_required": "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN" in r["monitoring_states_observed"]}')], [f"{FD}::test_no_outcome_tuning_or_hardcoded_model_output"]),
)


def apply(text: str, old: str, new: str) -> str:
    assert old in text, old[:70]
    return text.replace(old, new, 1)


def main() -> int:
    if "--check" in sys.argv:
        bad, syntax = [], []
        for name, edits, _t in MUTATIONS:
            for rel, old, new in edits:
                text = (ROOT / rel).read_text()
                if old not in text:
                    bad.append(f"{name}:{rel}")
                elif rel.endswith(".py"):
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
                (ROOT / rel).write_text(apply((ROOT / rel).read_text(), old, new))
            run = subprocess.run([sys.executable, "-m", "pytest", *tests, "-x", "-q", "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning"], cwd=ROOT,
                                 capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src:."}, timeout=900)
            first = [ln for ln in run.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))][:1]
            caught = run.returncode != 0 and bool(first) and first[0].startswith("FAILED")
        finally:
            for rel, data in originals.items():
                (ROOT / rel).write_bytes(data)
        clean = subprocess.run(["git", "status", "--short", "--", *originals], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        results.append({"mutation": name, "files": sorted(originals), "tests_run": tests, "caught_by_a_failing_test": caught, "first_failing_test": first[0] if first else None,
                        "files_restored_byte_identical": all((ROOT / rel).read_bytes() == data for rel, data in originals.items()), "git_status_after_restore": clean})
        print(name, caught, first[:1], flush=True)
    payload = {"controls": results, "all_caught": all(r["caught_by_a_failing_test"] for r in results), "all_restored": all(r["files_restored_byte_identical"] for r in results)}
    (OUT / "mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
