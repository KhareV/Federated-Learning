# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-001 / FERG0 frozen fail-closed evaluator (criteria: configs/final_eval_repair/fer_001_protocol_v1.json). --pre-transition defers only the registry PASS checks.
Real-browser results (crawl, truth matrix, owner-bound regression, clean-clone proof B) are RE-DERIVED here from the sanitized observations; recorded verdicts are never trusted."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import final_eval_repair_crawl_analysis as ca
from scripts import final_eval_repair_lib as lib
from scripts import final_eval_repair_presentation as pres
from scripts import ufl_lite_003_lib as ual
from scripts import ufl_lite_lib as ulib

ROOT = lib.ROOT
EVD = Path(os.environ.get("FER_EVD", ROOT / "reports/final_eval_repair/fer_001"))
CONFIG = ROOT / "configs/final_eval_repair/fer_001_protocol_v1.json"
SURFACE = ROOT / "configs/final_eval_repair/fer_001_authorised_surface_v1.json"
LOCK = ROOT / "artifacts/final_eval_repair/FINAL_EVAL_REPAIR_001_PROTOCOL_V1.lock.json"
ENTRY = lib.ENTRY
PRE = "--pre-transition" in sys.argv
DEFERRED = {"task_pass", "gate_pass"}
FINDINGS = {"f01": "f01_about_closed", "f02": "f02_landing_closed", "f03": "crawl_final_clean", "f04": "runbook_successor_truthful", "f05": "presentation_verifier_passes", "f06": "no_lastoria_reference", "f07": "f07_disposition"}


def rd(name: str) -> dict[str, Any]:
    return json.loads((EVD / name).read_text())


def git(*a: str) -> str:
    return lib.git(*a)


def drift(*paths: str) -> list[str]:
    return git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *paths).split()


def _surface() -> dict[str, Any]:
    return json.loads(SURFACE.read_text())


def delta_outside_authorised(rev: str) -> list[str]:
    s = _surface()
    entry_files = set(git("ls-tree", "-r", "--name-only", ENTRY).split())
    ok_new = set(s["authorised_new_files"])
    ok_mod = set(s["authorised_modifications"])
    bad = []
    for p in git("diff", "--name-only", ENTRY, rev).split():
        if p.startswith(("manifests/final_eval_repair/", "configs/final_eval_repair/", "artifacts/final_eval_repair/", "reports/final_eval_repair/", "scripts/final_eval_repair_", "tests/test_final_eval_repair_")):
            continue
        if p in entry_files:
            if p not in ok_mod:
                bad.append(p)
        elif p not in ok_new:
            bad.append(p)
    return bad


def sample_map() -> dict[str, str]:
    return rd("legacy_route_crawl_final.json")["sample"]


def crawl_analysis() -> dict[str, Any]:
    d = rd("legacy_route_crawl_final.json")
    return ca.analyze_crawl(d["observations"], pres.policy(), d["sample"])


def owner_groups(base: Path | None = None) -> dict[str, dict[str, bool]]:
    o = json.loads(((base or EVD) / "connected_owner_binding_regression.json").read_text())["observations"]
    b = ulib.load_baseline(ROOT)
    f, auth, models, rp = ual.step(o, "live-completed"), ual.step(o, "live-authoritative"), ual.step(o, "models-after-live"), ual.step(o, "replay")
    g = {"identity": ual.analyze_identity(ual.step(o, "signin")), "live": ual.analyze_live(f, auth, ual.step(o, "clients-rest"), b), "candidate": {k: v for k, v in ual.analyze_candidate(models, auth).items() if k != "one_candidate"}, "refresh": ual.analyze_refresh(ual.step(o, "refresh-mid-run")),
         "websocket": ual.analyze_ws(o["websockets"]), "rounds_page": ual.analyze_rounds_page(ual.step(o, "rounds-page")), "global": ual.analyze_global(ual.step(o, "global-clients-view")), "replay": ual.analyze_replay(rp, auth, ual.step(o, "models-after-replay"), models)}
    cands = models.get("candidates") or []
    g["candidate"]["all_candidates_canonical"] = bool(cands) and all(x["state_digest"] == ual.CANDIDATE for x in cands)
    return g


def _locks() -> bool:
    from scripts.cap_011_protected_audit import all_locks
    from scripts.verify_clerk_connected import verify

    return all(v["verified"] for v in all_locks().values()) and verify()["status"] == "PASS"


def _ui_chain() -> bool:
    return not subprocess.run([sys.executable, "-c", "from scripts import final_eval_repair_protected_audit as a; import sys; sys.exit(0 if a._ui_ok(5) else 1)"], cwd=ROOT, env={**os.environ, "PYTHONPATH": "src:."}).returncode


def _ufl_state() -> bool:
    r = lib.registry
    return (all(r("manifests/ufl_lite/task_registry_v1.csv", "task_id").get(f"UFL-LITE-00{i}") == "PASS" for i in (1, 2, 3)) and all(r("manifests/ufl_lite/gate_registry_v1.csv", "gate_id").get(g) == "PASS" for g in ("UFLG0", "UFLG1", "UFLG2")) and all(v["verified"] for v in lib.verify_all_ufl_locks().values()))


def _amendments_pure() -> bool:
    for p in git("diff", "--name-only", "--diff-filter=A", ENTRY).split():
        if "amendment" in p and p.endswith(".json"):
            a = json.loads((ROOT / p).read_text())
            if a["scope"] != "SUCCESSOR_COMPATIBILITY_ONLY" or a["result_evidence_committed_with_amendment"] is not False or not all({"old_sha256", "new_sha256"} <= set(v) for v in a["files"].values()):
                return False
            if re.search(r"PASS|passed|digest", json.dumps(a["change"])):
                return False
    return True


def _target_recorded() -> bool:
    t = rd("repair_target.json")
    sha = t["repair_target_sha"]
    return (bool(re.fullmatch(r"[0-9a-f]{40}", sha)) and sha != ENTRY and t["pushed_to_origin_main_at_record"] is True and t["unauthorised_delta_from_entry"] == [] and t["canonical_evidence_existed_at_target"] is False
            and subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=ROOT).returncode == 0 and all(subprocess.run(["git", "cat-file", "-e", f"{sha}:{p}"], cwd=ROOT).returncode == 0 for p in json.loads(LOCK.read_text())["bound_files"]))


def _secret_clean() -> bool:
    secret = os.environ.get("CLERK_SECRET_KEY", "")
    if not secret:
        return False
    s = rd("secret_audit.json")
    hit = subprocess.run(["git", "grep", "-lF", "--untracked", "-e", secret], cwd=ROOT, capture_output=True, text=True).stdout.split()
    scan = [p for p in EVD.rglob("*") if p.is_file() and secret.encode() in p.read_bytes()]
    return s["clean"] is True and not hit and not scan


def _clone() -> dict[str, Any]:
    return json.loads((EVD / "clean_clone/clean_clone.json").read_text())


def _clone_ok() -> bool:
    c, t = _clone(), rd("repair_target.json")["repair_target_sha"]
    proof_a, proof_b = c["proof_a_clean_clone"], c["proof_b_presentation_in_clone"]
    return (c["status"] == "PASS" and c["target_sha"] == t and proof_a["status"] == "PASS" and proof_a["checkout_sha"] == t and proof_a["tree_clean_after_checkout"] is True and proof_a["fresh_venv_created_by_run"] is True and proof_b["status"] == "PASS"
            and c["tracked_modified_after_execution"] == [] and c["developer_env_or_db_or_cookie_copied"] is False and proof_b["crawl_all_pass"] is True and proof_b["owner_binding_all_pass"] is True and proof_b["secrets_clean"] is True)


def _no_new_phase() -> bool:
    tasks = lib.registry("manifests/capstone/task_registry_v1.csv", "task_id")
    ufl = lib.registry("manifests/ufl_lite/task_registry_v1.csv", "task_id")
    fer = lib.registry("manifests/final_eval_repair/task_registry_v1.csv", "task_id")
    tags = git("tag", "-l").split()
    return "CAP-012" not in tasks and "UFL-LITE-004" not in ufl and "FINAL-EVAL-REPAIR-002" not in fer and not [t for t in tags if re.search(r"final|evaluator|ready|release", t) and t not in ("capstone-release-v1",)]


def build_checks() -> dict[str, Callable[[], bool]]:
    base = lambda: ulib.load_baseline(ROOT)  # noqa: E731
    rep = lambda: rd("test_report.json")  # noqa: E731
    R = lambda: pres.routes_ok()["checks"]  # noqa: E731
    return {
        "entry_audited": lambda: rd("entry_audit.json")["entry_sha"] == ENTRY and rd("entry_audit.json")["origin_main_sha"] == ENTRY and rd("entry_audit.json")["tags_ok"] is True and rd("entry_audit.json")["ufl_tasks_gates_and_locks_ok"] is True and rd("entry_audit.json")["ui_v1_through_v1_4_verified"] is True and rd("failed_findings_reproduction.json")["all_reproduced"] is True,
        "tags_unchanged": lambda: lib.tags_ok(), "ufl_state_preserved": lambda: _ufl_state(), "capstone_locks_verify": lambda: _locks(),
        "ui_predecessor_locks_identical": lambda: not git("diff", "--name-only", ENTRY, "--", *[f"artifacts/capstone/CAPSTONE_UI_V1{s}.lock.json" for s in ("", "_1", "_2", "_3", "_4")]).strip(),
        "ui_v15_verifies": lambda: _ui_chain(),
        "no_new_dependency": lambda: not git("diff", "--name-only", ENTRY, "--", "frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json", "requirements-dev.lock", "requirements-capstone-auth.lock").strip() and json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json").read_text())["npm_dependencies_added"] == [],
        "amendments_pure": lambda: _amendments_pure(),
        "f01_about_closed": lambda: pres.about_ok()["ok"], "f02_landing_closed": lambda: pres.landing_ok()["ok"], "landing_claim_sweep": lambda: pres.landing_claims_ok(), "landing_no_owner_binding_overreach": lambda: pres.landing_ok()["owner_binding_overreach"] == [],
        "routes_all_classified": lambda: R()["routes_all_classified"], "redirect_policy_safe": lambda: R()["redirect_policy_safe"], "current_routes_not_retired": lambda: R()["current_routes_not_retired"], "known_bad_routes_redirect": lambda: R()["known_bad_routes_redirect"], "monitoring_decision_documented": lambda: R()["monitoring_decision_documented"],
        "crawl_final_clean": lambda: crawl_analysis()["all_pass"] and rd("legacy_route_crawl_final.json")["label"] == "CANONICAL" and rd("legacy_route_crawl_final.json")["real_clerk_test_instance"] is True,
        "runbook_successor_truthful": lambda: pres.runbook_ok()["ok"], "runbook_historical_preserved": lambda: lib.sha(ROOT / "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1.md") == __import__("hashlib").sha256(subprocess.run(["git", "show", f"{ENTRY}:docs/capstone/CLERK_CONNECTED_RUNBOOK_V1.md"], cwd=ROOT, capture_output=True).stdout).hexdigest(),
        "truth_contract_matches_backend": lambda: pres.truth_contract_ok()["ok"] and pres.pages_ok()["ok"], "presentation_verifier_passes": lambda: pres.verify_all()["ok"], "no_stale_feature_status": lambda: pres.stale_feature_status()["ok"] and pres.claims_ok()["ok"],
        "truth_matrix_final": lambda: ca.truth_matrix(rd("legacy_route_crawl_final.json")["observations"], sample_map())["consistent"],
        "no_lastoria_reference": lambda: pres.lastoria_unreferenced()["ok"] and not pres.landing_ok()["font_refs"],
        "landing_network_clean": lambda: crawl_analysis()["checks"]["landing_zero_failed_or_404_requests"] and rd("font_404_final.json")["missing_asset_requested"] is False and rd("font_404_final.json")["landing_requests_failed"] == [],
        "f07_disposition": lambda: (d := rd("deep_link_investigation.json"))["disposition"].startswith("KNOWN STATIC-HOST FALLBACK SEMANTIC") and crawl_analysis()["checks"]["deep_links_reload_clean"] and bool(d["root_cause"]) and bool(d["why_safe"]),
        "no_backend_drift": lambda: not drift("product", "src", "privacy", "simulation", "federated", "checkpoints") and ulib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_api_drift": lambda: not drift("api", "contracts") and ulib.hash_drift(ROOT, base(), "reused_unchanged") == [], "no_db_drift": lambda: not drift("capstone_persistence") and ulib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_fl_drift": lambda: not drift("federated", "product/federation", "product/edge", "product/models") and ulib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_auth_drift": lambda: not drift("product/auth", "frontend/src/lib/product/auth.ts", "scripts/run_capstone_clerk_connected.py") and ulib.hash_drift(ROOT, base(), "auth") == [],
        "no_scientific_drift": lambda: ulib.hash_drift(ROOT, base(), "scientific") == [] and not drift("checkpoints", "reports/model_v2", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json") and base()["released_monitoring_model"] == "MODEL_V2_FINAL" and base()["calibration"] == "CAL_V2",
        "candidate_digest_unchanged": lambda: base()["canonical_candidate_digest"] == ulib.CANONICAL_CANDIDATE_DIGEST == pres.truth()["canonical_candidate_digest"] and ulib.candidate_state_ok(base()["candidate"]) and all(owner_groups()["candidate"].values()),
        "owner_binding_connected_regression": lambda: all(all(v.values()) for g, v in owner_groups().items()) and rd("connected_owner_binding_regression.json")["label"] == "CANONICAL" and rd("connected_owner_binding_regression.json")["real_clerk_test_instance"] is True,
        "demo_replay_global_unbound": lambda: pres.unbound_ok()["ok"] and all(owner_groups()["replay"].values()) and all(owner_groups()["global"].values()),
        "offline_demo_digest": lambda: (d := rd("demo_regression.json"))["semantic_sha256"] == pres.truth()["offline_demo_semantic_digest"] and d["equals_canonical"] is True and d["status"] == "PASS" and d["demo_auth_works"] is True and d["clerk_global_in_browser"] is False and d["external_requests"] == [] and d["blocked_external_requests"] == [] and d["clerk_origins_contacted"] == [],
        "fe_tests": lambda: rep()["frontend"]["vitest_returncode"] == 0 and rep()["frontend"]["failed"] == 0 and rep()["frontend"]["passed"] >= 214, "fe_check_build": lambda: rep()["frontend"]["svelte_check"]["returncode"] == 0 and rep()["frontend"]["svelte_check"]["errors"] == 0 and rep()["frontend"]["build_returncode"] == 0,
        "py_targeted": lambda: rep()["targeted_python"]["returncode"] == 0 and rep()["targeted_python"]["counts"].get("failed", 0) == 0, "py_full": lambda: rep()["full_python"]["returncode"] == 0 and not rep()["full_python"]["failed"] and rep()["inherited_flake"]["status"] == "PASS_INHERITED_FLAKE_POLICY",
        "lint": lambda: rep()["commands"]["ruff"]["returncode"] == 0 and rep()["commands"]["pip_check"]["returncode"] == 0, "ci_untouched": lambda: rep()["ci_queried"] is False and rep()["ci_triggered"] is False,
        "mutation_log": lambda: (m := rd("mutation_controls.json"))["all_caught"] and m["all_restored"] and [x["mutation"] for x in m["controls"]] == json.loads(CONFIG.read_text())["mutation_controls"] and len(m["controls"]) == 35,
        "clean_clone": lambda: _clone_ok(), "repair_target_recorded": lambda: _target_recorded(), "protected_final": lambda: rd("protected_artifact_final.json")["protected_artifact_drift"] is False, "lock_ok": lambda: _lock_ok(),
        "task_pass": lambda: lib.registry("manifests/final_eval_repair/task_registry_v1.csv", "task_id").get("FINAL-EVAL-REPAIR-001") == "PASS", "gate_pass": lambda: lib.registry("manifests/final_eval_repair/gate_registry_v1.csv", "gate_id").get("FERG0") == "PASS",
        "no_new_phase": lambda: _no_new_phase(),
    }


def _lock_ok() -> bool:
    lock = json.loads(LOCK.read_text())
    return all(lib.sha(ROOT / p) == h for p, h in lock["bound_files"].items()) and lock["criteria_count"] == json.loads(CONFIG.read_text())["criteria_count"]


def evaluate() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text())
    frozen = config["ferg0_criteria"]
    if len(frozen) != config["criteria_count"]:
        raise RuntimeError("FERG0_FROZEN_CRITERIA_CHANGED")
    from scripts.final_eval_repair_protected_audit import final as protected_final

    protected_final()
    checks = build_checks()
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
        res = [(c, *run(c)) for c in row["checks"]]
        rows.append({"id": row["id"], "text": row["text"], "pass": all(r[1] for r in res), "checks": [{"check": n, "pass": ok, **({"note": w} if w else {})} for n, ok, w in res]})
    status = {k: ("CLOSED" if cache.get(v, (False, ""))[0] else "OPEN") for k, v in FINDINGS.items()}
    pol = pres.policy()
    counts = {"legacy_route_count": pol["legacy_redirect_count"] + pol["retained_legacy_tool_count"], "legacy_redirect_count": pol["legacy_redirect_count"], "retained_legacy_tool_count": pol["retained_legacy_tool_count"], "unclassified_route_count": pres.routes_ok()["counts"]["unclassified"]}
    try:
        target = rd("repair_target.json")["repair_target_sha"]
    except Exception:
        target = None
    failed = [r["id"] for r in rows if not r["pass"]]
    return {"gate": "FERG0", "mode": "PRE_TRANSITION" if PRE else "FINAL", "criteria_count": len(rows), "passed_count": len(rows) - len(failed), "failed_count": len(failed), "failed": failed, "repair_target_sha": target, **{f"{k}_status": v for k, v in status.items()},
            **counts, "protected_drift": not cache.get("protected_final", (False, ""))[0], "all_decided_pass": not failed, "final_decision": "FERG0_PASS" if not failed else "FERG0_FAIL", "criteria": rows}


def main() -> int:
    r = evaluate()
    (EVD / ("ferg0_pre_transition.json" if PRE else "ferg0_criteria.json")).write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: r[k] for k in ("mode", "all_decided_pass", "failed", "passed_count", "criteria_count")}))
    return 0 if r["all_decided_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
