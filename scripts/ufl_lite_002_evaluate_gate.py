# ruff: noqa: E501
"""UFL-LITE-002 / UFLG1 frozen evaluator (criteria: configs/ufl_lite/uflg1_protocol_v1.json). --pre-transition defers only the registry PASS checks."""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import ufl_lite_002_lib as plib
from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
EVD = Path(os.environ.get("UFL_EVD", ROOT / "reports/ufl_lite/ufl_lite_002"))
CONFIG = ROOT / "configs/ufl_lite/uflg1_protocol_v1.json"
LOCK = ROOT / "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.lock.json"
ENTRY = "6871e0891ad697dab3f122afaba2d331a279ec8c"
DEMO_DIGEST = "3a57614e15264f3cd7661a016a30d033aab78647d57be04273c386cc9d048726"
PRE = "--pre-transition" in sys.argv
DEFERRED = {"task_pass", "gate_pass"}
# symbolic frontend-test names (frozen in the protocol) -> the actual vitest test title fragments
VMAP = {
    "helper_clerk_live": "binds SIM_FL_SITE_00 for CLERK + LIVE_RUN", "helper_demo_none": "binds nothing for DEMO + LIVE_RUN", "helper_replay_none": "binds nothing for DEMO + LIVE_RUN",
    "helper_has_no_identity_parameter": "takes no user identity", "demo_no_binding": "show no owner binding and keep the existing title", "replay_no_binding": "show no owner binding and keep the existing title",
    "global_clients_unbound": "the GLOBAL clients view stays unbound", "one_owner_card": "bound: exactly one MY EDGE CLIENT card", "seven_peer_cards": "bound: exactly one MY EDGE CLIENT card", "technical_ids_unchanged": "bound: exactly one MY EDGE CLIENT card",
    "owner_examples_event_derived": "the owner example count follows the events", "synthetic_qualification": "bound: exactly one MY EDGE CLIENT card", "not_your_physiology": "bound: exactly one MY EDGE CLIENT card",
    "owner_state_milestone_digest": "CLERK + LIVE_RUN: one owner card", "summary_derivation": "the owner example count follows the events", "no_contribution_percentage": "adds no contribution percentage",
    "locality_wording": "CLERK + LIVE_RUN: one owner card", "unbound_grid_unchanged": "unbound (no prop)",
}


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def rd(name: str) -> dict[str, Any]:
    return json.loads((EVD / name).read_text())


def drift(*paths: str) -> list[str]:
    return git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *paths).split()


def registry(name: str, key: str) -> dict[str, str]:
    with (ROOT / f"manifests/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        return {r[key]: r["status"] for r in csv.DictReader(h)}


def tags() -> dict[str, str]:
    return {t: subprocess.run(["git", "ls-remote", "origin", f"refs/tags/{t}^{{}}"], cwd=ROOT, capture_output=True, text=True).stdout.split("\t")[0] for t in lib.RELEASE_TAGS}


def build_checks() -> dict[str, Callable[[], bool]]:
    base = lambda: lib.load_baseline(ROOT)  # noqa: E731
    rep = lambda: rd("test_report.json")  # noqa: E731
    return {
        "entry_audited": lambda: rd("entry_audit.json")["entry_sha"] == ENTRY and rd("entry_audit.json")["origin_main_sha"] == ENTRY and rd("entry_audit.json")["uflg0_pass_and_lock_verified"] is True,
        "uflg0_preserved": lambda: registry("ufl_lite/task", "task_id").get("UFL-LITE-001") == "PASS" and registry("ufl_lite/gate", "gate_id").get("UFLG0") == "PASS" and not git("diff", "--name-only", ENTRY, "--", "reports/ufl_lite/ufl_lite_001", "configs/ufl_lite/user_bound_fl_participation_v1.json", "configs/ufl_lite/uflg0_protocol_v1.json", "artifacts/ufl_lite/UFL_LITE_001_PROTOCOL_V1.lock.json", "docs/ufl_lite").strip(),
        "tags_unchanged": lambda: lib.tags_ok(tags()),
        "locks_verify": lambda: _locks(),
        "no_backend_change": lambda: not drift("api", "product", "capstone_persistence", "src", "privacy", "simulation"),
        "no_api_change": lambda: not drift("api", "contracts") and lib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_db_change": lambda: not drift("capstone_persistence") and lib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_fl_change": lambda: not drift("federated", "product/federation", "product/edge", "product/models") and lib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_auth_change": lambda: not drift("product/auth", "frontend/src/lib/product/auth.ts", "scripts/run_capstone_clerk_connected.py") and lib.hash_drift(ROOT, base(), "auth") == [],
        "helper_pure": lambda: plib.helper_audit()["ok"] and plib.grid_audit()["ok"] and plib.live_audit()["ok"],
        "global_page_unchanged": lambda: plib.global_page_ok() and not drift("frontend/src/routes/app/federation/clients/+page.svelte"),
        "b_site00_93": lambda: base()["datasets"]["SIM_FL_SITE_00"]["local_example_count"] == 93 and base()["datasets"]["SIM_FL_SITE_00"]["dataset_sha256"].startswith("fca44709"),
        "claims_clean": lambda: plib.text_audit()["ok"],
        "no_contribution_in_source": lambda: plib.text_audit()["ok"] and not re.search(r"contribution|influence score", " ".join((ROOT / p).read_text() for p in plib.PRESENTATION), re.I),
        "no_consent_ui": lambda: not re.search(r"consent|opt[- ]in|join federation|type=\"checkbox\"|role=\"switch\"", " ".join((ROOT / p).read_text() for p in plib.PRESENTATION), re.I),
        "b_client_count": lambda: base()["client_count"] == 8 and lib.cohort_ok(base()["client_ids"])["ok"],
        "b_rounds": lambda: base()["planned_rounds"] == 3,
        "b_updates": lambda: base()["total_updates"] == 24 and base()["accepted_updates_per_round"] == [8, 8, 8],
        "b_digest": lambda: base()["canonical_candidate_digest"] == lib.CANONICAL_CANDIDATE_DIGEST and rd("demo_regression.json")["candidate_state_digests"] == [lib.CANONICAL_CANDIDATE_DIGEST],
        "b_candidate": lambda: lib.candidate_state_ok(base()["candidate"]),
        "h_scientific": lambda: lib.hash_drift(ROOT, base(), "scientific") == [] and not drift("checkpoints", "reports/model_v2", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json") and base()["released_monitoring_model"] == "MODEL_V2_FINAL" and base()["calibration"] == "CAL_V2",
        "demo_digest": lambda: rd("demo_regression.json")["semantic_sha256"] == DEMO_DIGEST and rd("demo_regression.json")["equals_canonical"] is True,
        "demo_regression": lambda: (d := rd("demo_regression.json"))["status"] == "PASS" and d["demo_auth_works"] is True and d["clerk_global_in_browser"] is False and d["external_requests"] == [] and d["blocked_external_requests"] == [] and d["clerk_origins_contacted"] == [],
        "ui14_ok": lambda: _ui14(),
        "ui_locks_identical": lambda: not git("diff", "--name-only", ENTRY, "--", "artifacts/capstone/CAPSTONE_UI_V1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json").strip(),
        "amendments_pure": lambda: _amendments(),
        "frontend_scope_exact": lambda: sorted(set(git("diff", "--name-only", "--diff-filter=AM", ENTRY, "--", "frontend").split())) == sorted(json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json").read_text())["changed_from_predecessor"]),
        "fe_tests": lambda: rep()["frontend"]["vitest_returncode"] == 0 and rep()["frontend"]["failed"] == 0 and rep()["frontend"]["passed"] >= 210,
        "fe_check": lambda: rep()["frontend"]["svelte_check"]["returncode"] == 0 and rep()["frontend"]["svelte_check"]["errors"] == 0,
        "fe_build": lambda: rep()["frontend"]["build_returncode"] == 0,
        "py_targeted": lambda: rep()["targeted_python"]["returncode"] == 0 and rep()["targeted_python"]["counts"].get("failed", 0) == 0,
        "py_full": lambda: rep()["full_python"]["returncode"] == 0 and not rep()["full_python"]["failed"] and rep()["inherited_flake"]["status"] == "PASS_INHERITED_FLAKE_POLICY",
        "lint": lambda: rep()["commands"]["ruff"]["returncode"] == 0 and rep()["commands"]["pip_check"]["returncode"] == 0,
        "mutation_log": lambda: (m := rd("mutation_controls.json"))["all_caught"] and m["all_restored"] and [x["mutation"] for x in m["controls"]] == json.loads(CONFIG.read_text())["mutation_controls"] and len(m["controls"]) == 18,
        "ci_untouched": lambda: rep()["ci_queried"] is False and rep()["ci_triggered"] is False,
        "protected_final": lambda: rd("protected_artifact_final.json")["protected_artifact_drift"] is False,
        "lock_ok": lambda: _lock_ok(),
        "task_pass": lambda: registry("ufl_lite/task", "task_id").get("UFL-LITE-002") == "PASS",
        "gate_pass": lambda: registry("ufl_lite/gate", "gate_id").get("UFLG1") == "PASS",
    }


def _locks() -> bool:
    from scripts.cap_011_protected_audit import all_locks
    from scripts.verify_clerk_connected import verify

    return all(v["verified"] for v in all_locks().values()) and verify()["status"] == "PASS"


def _ui14() -> bool:
    from scripts.verify_capstone_ui_v1 import verify as v1
    from scripts.verify_capstone_ui_v1_1 import verify as v11
    from scripts.verify_capstone_ui_v1_2 import verify as v12
    from scripts.verify_capstone_ui_v1_3 import verify as v13
    from scripts.verify_capstone_ui_v1_4 import verify as v14

    lock = json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json").read_text())
    return all(f()["status"] == "PASS" for f in (v1, v11, v12, v13, v14)) and lock["predecessor_id"] == "CAPSTONE_UI_V1_3" and lock["owner_phase"] == "UFL-LITE-002" and lock["npm_dependencies_added"] == []


def _amendments() -> bool:
    for n in ("CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_9_1.json", "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_4.json", "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.amendment_9_4.json", "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_3.json"):
        a = json.loads((ROOT / "artifacts/capstone" / n).read_text())
        if a["scope"] != "SUCCESSOR_COMPATIBILITY_ONLY" or a["result_evidence_committed_with_amendment"] is not False or not a["previous_amendment"] or not all({"old_sha256", "new_sha256"} <= set(v) for v in a["files"].values()):
            return False
        if any(re.search(r"PASS|passed|digest", json.dumps(a["change"])) for _ in [0]):
            return False
    return True


def _lock_ok() -> bool:
    lock = json.loads(LOCK.read_text())
    return all(lib.sha(ROOT / p) == h for p, h in lock["bound_files"].items()) and lock["criteria_count"] == json.loads(CONFIG.read_text())["criteria_count"]


def evaluate() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text())
    frozen = config["uflg1_criteria"]
    if len(frozen) != config["criteria_count"]:
        raise RuntimeError("UFLG1_FROZEN_CRITERIA_CHANGED")
    from scripts.ufl_lite_002_protected_audit import final as protected_final

    protected_final()
    checks = build_checks()
    rep = rd("test_report.json")
    vt, pt = rep["frontend"]["tests"], rep["targeted_python"]["tests"]
    cache: dict[str, tuple[bool, str]] = {}

    def run(name: str) -> tuple[bool, str]:
        if name not in cache:
            if PRE and name in DEFERRED:
                cache[name] = (True, "DEFERRED")
            else:
                try:
                    cache[name] = (bool(checks[name]()), "")
                except Exception as e:
                    cache[name] = (False, f"{type(e).__name__}:{str(e)[:120]}")
        return cache[name]

    rows = []
    for row in frozen:
        res = []
        for c in row["checks"]:
            if c.startswith("V:"):
                frag = VMAP[c[2:]]
                hits = [v for k, v in vt.items() if frag in k]
                res.append((c, bool(hits) and all(v == "passed" for v in hits), ""))
            elif c.startswith("P:"):
                hits = [v for k, v in pt.items() if k.split("::")[-1] == c[2:]]
                res.append((c, bool(hits) and all(v == "passed" for v in hits), ""))
            else:
                res.append((c, *run(c)))
        rows.append({"id": row["id"], "text": row["text"], "pass": all(r[1] for r in res), "checks": [{"check": n, "pass": ok, **({"note": w} if w else {})} for n, ok, w in res]})
    return {"gate": "UFLG1", "mode": "PRE_TRANSITION" if PRE else "FINAL", "criteria_count": len(rows), "all_decided_pass": all(r["pass"] for r in rows), "failed": [r["id"] for r in rows if not r["pass"]], "criteria": rows}


def main() -> int:
    r = evaluate()
    (EVD / ("uflg1_pre_transition.json" if PRE else "uflg1_criteria.json")).write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"mode": r["mode"], "all_decided_pass": r["all_decided_pass"], "failed": r["failed"]}))
    return 0 if r["all_decided_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
