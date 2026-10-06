# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-002 / FERG1 frozen fail-closed evaluator (criteria: configs/final_eval_repair/fer_002_protocol_v1.json). --pre-transition defers only the registry PASS checks.
Real-browser results (landing audit, product audit, route crawl, truth matrix, owner-binding regression, clean-clone proof B) are RE-DERIVED here from the sanitized observations; recorded verdicts are never trusted."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import final_eval_repair_002_browser_analysis as ba
from scripts import final_eval_repair_002_entry_evidence as ee
from scripts import final_eval_repair_002_lib as l2
from scripts import final_eval_repair_002_provenance as prov
from scripts import final_eval_repair_crawl_analysis as ca
from scripts import final_eval_repair_lib as lib
from scripts import final_eval_repair_presentation as pres
from scripts import ufl_lite_003_lib as ual
from scripts import ufl_lite_lib as ulib

ROOT = lib.ROOT
EVD = Path(os.environ.get("FER2_EVD", ROOT / "reports/final_eval_repair/fer_002"))
CONFIG = ROOT / "configs/final_eval_repair/fer_002_protocol_v1.json"
SURFACE = ROOT / "configs/final_eval_repair/fer_002_authorised_surface_v1.json"
LOCK = ROOT / "artifacts/final_eval_repair/FINAL_EVAL_REPAIR_002_PROTOCOL_V1.lock.json"
ENTRY = l2.ENTRY
PRE = "--pre-transition" in sys.argv
DEFERRED = {"task_pass", "gate_pass"}
FINDINGS = {"f2_01": "f201_neuralgraph_closed", "f2_02": "f202_skip_link", "f2_03": "f203_touch_targets", "loader": "loader_disposition", "candidates": "candidate_observation_disposition"}
NG = "frontend/src/lib/components/landing/NeuralGraph.svelte"


def rd(name: str) -> dict[str, Any]:
    return json.loads((EVD / name).read_text())


def git(*a: str) -> str:
    return lib.git(*a)


def drift(*paths: str) -> list[str]:
    return git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *paths).split()


def entry_blob_sha(rel: str) -> str:
    return hashlib.sha256(subprocess.run(["git", "show", f"{ENTRY}:{rel}"], cwd=ROOT, capture_output=True).stdout).hexdigest()


def delta_outside_authorised(rev: str) -> list[str]:
    s = json.loads(SURFACE.read_text())
    entry_files = set(git("ls-tree", "-r", "--name-only", ENTRY).split())
    bad = []
    for p in git("diff", "--name-only", ENTRY, rev).split():
        if p.startswith(("manifests/final_eval_repair/", "configs/final_eval_repair/", "artifacts/final_eval_repair/", "reports/final_eval_repair/fer_002/", "scripts/final_eval_repair_", "tests/test_final_eval_repair_")):
            if p in entry_files and not (p.startswith("configs/final_eval_repair/") or p.startswith("manifests/final_eval_repair/") or p.startswith("artifacts/final_eval_repair/")) and p.startswith(("scripts/final_eval_repair_", "tests/test_final_eval_repair_")) and p not in s["authorised_modifications"]:
                bad.append(p)
            continue
        if p in entry_files:
            if p not in s["authorised_modifications"]:
                bad.append(p)
        elif p not in s["authorised_new_files"]:
            bad.append(p)
    return bad


def sample() -> dict[str, str]:
    return rd("route_crawl_final.json")["sample"]


def crawl() -> dict[str, Any]:
    d = rd("route_crawl_final.json")
    return ca.analyze_crawl(d["observations"], pres.policy(), d["sample"])


def landing(base: Path | None = None) -> dict[str, bool]:
    return ba.analyze_landing(json.loads(((base or EVD) / "landing_browser_audit.json").read_text())["observations"])


def product(base: Path | None = None) -> dict[str, bool]:
    return ba.analyze_product(json.loads(((base or EVD) / "product_browser_audit.json").read_text())["observations"])


def owner_groups(base: Path | None = None) -> dict[str, dict[str, bool]]:
    o = json.loads(((base or EVD) / "connected_owner_binding_regression.json").read_text())["observations"]
    b = ulib.load_baseline(ROOT)
    f, auth, models, rp = ual.step(o, "live-completed"), ual.step(o, "live-authoritative"), ual.step(o, "models-after-live"), ual.step(o, "replay")
    g = {"identity": ual.analyze_identity(ual.step(o, "signin")), "live": ual.analyze_live(f, auth, ual.step(o, "clients-rest"), b), "candidate": {k: v for k, v in ual.analyze_candidate(models, auth).items() if k != "one_candidate"}, "refresh": ual.analyze_refresh(ual.step(o, "refresh-mid-run")),
         "websocket": ual.analyze_ws(o["websockets"]), "rounds_page": ual.analyze_rounds_page(ual.step(o, "rounds-page")), "global": ual.analyze_global(ual.step(o, "global-clients-view")), "replay": ual.analyze_replay(rp, auth, ual.step(o, "models-after-replay"), models)}
    cands = models.get("candidates") or []
    g["candidate"]["all_candidates_canonical"] = bool(cands) and all(x["state_digest"] == ual.CANDIDATE for x in cands)
    return g


def _ui_chain() -> bool:
    from scripts.final_eval_repair_002_protected_audit import _ui_ok

    return _ui_ok(6)


def _prior() -> bool:
    from scripts.final_eval_repair_002_protected_audit import _prior_ok

    return _prior_ok() and not git("diff", "--name-only", ENTRY, "--", "reports/final_eval_repair/fer_001").strip()


def _locks() -> bool:
    from scripts.cap_011_protected_audit import all_locks
    from scripts.verify_clerk_connected import verify

    return all(v["verified"] for v in all_locks().values()) and verify()["status"] == "PASS"


def _amendments_pure() -> bool:
    for p in git("diff", "--name-only", "--diff-filter=A", ENTRY).split():
        if "amendment" in p and p.endswith(".json"):
            a = json.loads((ROOT / p).read_text())
            if a["scope"] != "SUCCESSOR_COMPATIBILITY_ONLY" or a["result_evidence_committed_with_amendment"] is not False or not all({"old_sha256", "new_sha256"} <= set(v) for v in a["files"].values()) or re.search(r"PASS|passed|digest", json.dumps(a["change"])):
                return False
    return True


def _f201() -> bool:
    t = (ROOT / NG).read_text()
    plain = prov.pres.strip_comments(t)
    return (not re.search(r"99\.8|LIVE EDGE|real-time|Normal \d+ BPM|Hours Unmonitored|reports/\S+\.json|Edge Peak Detector|128-D Edge", plain)
            and all(x in plain for x in ("ILLUSTRATIVE SIGNAL-FLOW GRAPH", "not live telemetry", "Conceptual snapshot view", "ILLUSTRATIVE VALUE (NOT LIVE)", "No measured percentage is claimed")) and not re.search(r"currentValue: '(?!Illustrative)", plain))


def _inventory() -> bool:
    e, f = rd("landing_claim_inventory_entry.json"), rd("landing_claim_inventory_final.json")
    now = ee.inventory(ROOT)
    bad = {"UNSUPPORTED_QUANTITATIVE_ASSERTION", "MISLEADING_LIVE_STATE_ASSERTION", "STALE_PRODUCT_ASSERTION"}
    ok_graph = set(e["landing_import_graph"]) <= set(f["landing_import_graph"]) and f["landing_import_graph"] == now["landing_import_graph"]
    unresolved = [r for r in now["rows"] if r["classification"] in bad and not any(re.search(x["text_pattern"], r["text"], re.I) and x["surface"] == r["file"] for x in prov.contract(ROOT)["claims"])]
    return ok_graph and e["landing_file_count"] >= 40 and e["by_classification"].get("UNSUPPORTED_QUANTITATIVE_ASSERTION", 0) > 0 and not unresolved and f["by_classification"] == now["by_classification"]


def _candidate_obs() -> bool:
    e = rd("failed_findings_reproduction.json")["findings"]["candidate_observation"]
    card = (ROOT / "frontend/src/lib/components/product/federation/CandidateCard.svelte").read_text()
    phr = subprocess.run(["grep", "-rniE", "duplicate model|same candidate|deployed twice|identical candidate", "frontend/src/routes", "frontend/src/lib"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return e["candidate_identity_and_digest_are_separate_fields"] is True and not e["misleading_phrases_found"] and "candidate.candidate_id" in card and "State digest" in card and not phr


def _fer1_stays_closed() -> bool:
    p = pres.verify_all()
    c = crawl()["checks"]
    return p["ok"] and pres.about_ok()["ok"] and pres.landing_ok()["ok"] and pres.routes_ok()["ok"] and pres.runbook_ok()["ok"] and pres.lastoria_unreferenced()["ok"] and c["legacy_and_compat_land_on_expected_current_route"] and c["zero_stale_feature_status_rendered"] and c["zero_fabricated_or_legacy_content_rendered"]


def _target_recorded() -> bool:
    t = rd("repair_target.json")
    sha = t["repair_target_sha"]
    return (bool(re.fullmatch(r"[0-9a-f]{40}", sha)) and sha != ENTRY and t["pushed_to_origin_main_at_record"] is True and t["unauthorised_delta_from_entry"] == [] and t["canonical_evidence_existed_at_target"] is False
            and subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=ROOT).returncode == 0 and all(subprocess.run(["git", "cat-file", "-e", f"{sha}:{p}"], cwd=ROOT).returncode == 0 for p in json.loads(LOCK.read_text())["bound_files"]))


def _clone_ok() -> bool:
    c = json.loads((EVD / "clean_clone/clean_clone.json").read_text())
    t = rd("repair_target.json")["repair_target_sha"]
    a, b = c["proof_a_clean_clone"], c["proof_b_browser_in_clone"]
    base = EVD / "clean_clone"
    lc, pc = landing(base), product(base)
    cr = ca.analyze_crawl(json.loads((base / "route_crawl_final.json").read_text())["observations"], pres.policy(), json.loads((base / "route_crawl_final.json").read_text())["sample"])
    return (c["status"] == "PASS" and c["target_sha"] == t and a["status"] == "PASS" and a["checkout_sha"] == t and a["tree_clean_after_checkout"] is True and a["fresh_venv_created_by_run"] is True and b["status"] == "PASS" and c["tracked_modified_after_execution"] == [] and c["developer_env_or_db_or_cookie_copied"] is False
            and all(lc.values()) and all(pc.values()) and cr["all_pass"] and all(all(v.values()) for v in owner_groups(base).values()) and json.loads((base / "secret_audit.json").read_text())["clean"] is True)


def _secret_clean() -> bool:
    secret = os.environ.get("CLERK_SECRET_KEY", "")
    return bool(secret) and rd("secret_audit.json")["clean"] is True and not [p for p in EVD.rglob("*") if p.is_file() and secret.encode() in p.read_bytes()] and not subprocess.run(["git", "grep", "-lF", "--untracked", "-e", secret], cwd=ROOT, capture_output=True, text=True).stdout.split()


def _no_new_phase() -> bool:
    tasks, ufl, fer = lib.registry("manifests/capstone/task_registry_v1.csv", "task_id"), lib.registry("manifests/ufl_lite/task_registry_v1.csv", "task_id"), lib.registry("manifests/final_eval_repair/task_registry_v1.csv", "task_id")
    tags = git("tag", "-l").split()
    return "CAP-012" not in tasks and "UFL-LITE-004" not in ufl and "FINAL-EVAL-REPAIR-003" not in fer and not [t for t in tags if re.search(r"final|evaluator|ready|release", t) and t != "capstone-release-v1"]


def _lock_ok() -> bool:
    lock = json.loads(LOCK.read_text())
    return all(lib.sha(ROOT / p) == h for p, h in lock["bound_files"].items()) and lock["criteria_count"] == json.loads(CONFIG.read_text())["criteria_count"]


def build_checks() -> dict[str, Callable[[], bool]]:
    base = lambda: ulib.load_baseline(ROOT)  # noqa: E731
    rep = lambda: rd("test_report.json")  # noqa: E731
    A = lambda: prov.a11y_static_ok()["checks"]  # noqa: E731
    return {
        "entry_audited": lambda: rd("entry_audit.json")["entry_sha"] == ENTRY and rd("entry_audit.json")["origin_main_sha"] == ENTRY and rd("entry_audit.json")["tags_ok"] is True and rd("entry_audit.json")["fer1_and_ufl_state_and_locks_ok"] is True and rd("entry_audit.json")["ui_v1_through_v1_5_verified"] is True and rd("failed_findings_reproduction.json")["all_reproduced"] is True,
        "tags_unchanged": lambda: lib.tags_ok(), "prior_phases_preserved": lambda: _prior(), "capstone_locks_verify": lambda: _locks(),
        "ui_predecessor_locks_identical": lambda: not git("diff", "--name-only", ENTRY, "--", *[f"artifacts/capstone/CAPSTONE_UI_V1{s}.lock.json" for s in ("", "_1", "_2", "_3", "_4", "_5")]).strip(),
        "ui_v16_verifies": lambda: _ui_chain(),
        "no_new_dependency": lambda: not git("diff", "--name-only", ENTRY, "--", "frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json", "requirements-dev.lock", "requirements-capstone-auth.lock").strip() and json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json").read_text())["npm_dependencies_added"] == [],
        "amendments_pure": lambda: _amendments_pure(),
        "f201_neuralgraph_closed": lambda: _f201(), "landing_inventory_complete": lambda: _inventory(),
        "no_unsourced_quantitative_claims": lambda: not [h for h in prov.scan_tree()["uncovered"] if h["claim_type"] in {"QUANTITATIVE", "PERCENTAGE", "SCORE", "PHYSIOLOGICAL_VALUE", "FILE_REFERENCE"}] and prov.scan_tree()["ok"],
        "no_misleading_live_claims": lambda: not [h for h in prov.scan_tree()["uncovered"] if h["claim_type"] in {"LIVE_STATE", "EDGE_INFERENCE", "HARDWARE_DATA", "STATUS_LABEL"}] and prov.scan_tree()["ok"],
        "provenance_contract_valid": lambda: prov.provenance_ok()["ok"], "new_guards_pass": lambda: prov.verify_all()["ok"], "fer1_presentation_verifier_passes": lambda: pres.verify_all()["ok"],
        "f202_skip_link": lambda: A()["landing_skip_link_first"] and A()["skip_target_focusable_main"] and A()["skip_link_hidden_until_focus"] and all(v for k, v in landing().items() if k.startswith("skip_link")),
        "f202_nav_labelled": lambda: A()["landing_nav_labelled"] and landing()["nav_labelled"] and product()["labelled_navs"],
        "f202_reduced_motion": lambda: all(A()[k] for k in ("neural_graph_reduced_motion", "multimodal_reduced_motion", "watch_reduced_motion", "globe_reduced_motion", "landing_css_reduced_motion")) and all(v for k, v in landing().items() if k.startswith("reduced_motion")) and product()["reduced_motion_no_raf_loops"],
        "f203_touch_targets": lambda: landing()["touch_targets_390_none_under_24"] and product()["touch_targets_390_none_under_24"],
        "loader_disposition": lambda: A()["boot_loader_has_heading"] and product()["one_h1_each"], "candidate_observation_disposition": lambda: _candidate_obs(),
        "landing_browser_audit_clean": lambda: all(landing().values()) and rd("landing_browser_audit.json")["label"] == "CANONICAL",
        "route_crawl_final_clean": lambda: crawl()["all_pass"] and rd("route_crawl_final.json")["label"] == "CANONICAL" and rd("route_crawl_final.json")["real_clerk_test_instance"] is True and all(product().values()),
        "truth_matrix_final": lambda: ca.truth_matrix(rd("route_crawl_final.json")["observations"], sample())["consistent"], "fer1_findings_stay_closed": lambda: _fer1_stays_closed(),
        "route_policy_unchanged": lambda: all(lib.sha(ROOT / p) == entry_blob_sha(p) for p in ("configs/final_eval_repair/legacy_route_policy_v1.json", "frontend/src/lib/product/route-policy.ts", "frontend/src/routes/+layout.ts")),
        "landing_network_clean": lambda: landing()["zero_failed_assets"] and crawl()["checks"]["landing_zero_failed_or_404_requests"],
        "no_backend_drift": lambda: not drift("product", "src", "privacy", "simulation", "federated", "checkpoints") and ulib.hash_drift(ROOT, base(), "reused_unchanged") == [], "no_api_drift": lambda: not drift("api", "contracts") and ulib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_db_drift": lambda: not drift("capstone_persistence") and ulib.hash_drift(ROOT, base(), "reused_unchanged") == [], "no_fl_drift": lambda: not drift("federated", "product/federation", "product/edge", "product/models") and ulib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_auth_drift": lambda: not drift("product/auth", "frontend/src/lib/product/auth.ts", "scripts/run_capstone_clerk_connected.py") and ulib.hash_drift(ROOT, base(), "auth") == [],
        "no_scientific_drift": lambda: ulib.hash_drift(ROOT, base(), "scientific") == [] and not drift("checkpoints", "reports/model_v2", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json") and base()["released_monitoring_model"] == "MODEL_V2_FINAL" and base()["calibration"] == "CAL_V2",
        "candidate_digest_unchanged": lambda: base()["canonical_candidate_digest"] == ulib.CANONICAL_CANDIDATE_DIGEST == pres.truth()["canonical_candidate_digest"] and ulib.candidate_state_ok(base()["candidate"]) and all(owner_groups()["candidate"].values()),
        "owner_binding_connected_regression": lambda: all(all(v.values()) for v in owner_groups().values()) and rd("connected_owner_binding_regression.json")["label"] == "CANONICAL" and rd("connected_owner_binding_regression.json")["real_clerk_test_instance"] is True,
        "demo_replay_global_unbound": lambda: pres.unbound_ok()["ok"] and all(owner_groups()["replay"].values()) and all(owner_groups()["global"].values()),
        "offline_demo_digest": lambda: (d := rd("demo_regression.json"))["semantic_sha256"] == pres.truth()["offline_demo_semantic_digest"] and d["equals_canonical"] is True and d["status"] == "PASS" and d["demo_auth_works"] is True and d["clerk_global_in_browser"] is False and d["external_requests"] == [] and d["blocked_external_requests"] == [] and d["clerk_origins_contacted"] == [],
        "fe_tests": lambda: rep()["frontend"]["vitest_returncode"] == 0 and rep()["frontend"]["failed"] == 0 and rep()["frontend"]["passed"] >= 218, "fe_check_build": lambda: rep()["frontend"]["svelte_check"]["returncode"] == 0 and rep()["frontend"]["svelte_check"]["errors"] == 0 and rep()["frontend"]["build_returncode"] == 0,
        "py_targeted": lambda: rep()["targeted_python"]["returncode"] == 0 and rep()["targeted_python"]["counts"].get("failed", 0) == 0, "py_full": lambda: rep()["full_python"]["returncode"] == 0 and not rep()["full_python"]["failed"] and rep()["inherited_flake"]["status"] == "PASS_INHERITED_FLAKE_POLICY",
        "lint": lambda: rep()["commands"]["ruff"]["returncode"] == 0 and rep()["commands"]["pip_check"]["returncode"] == 0, "ci_untouched": lambda: rep()["ci_queried"] is False and rep()["ci_triggered"] is False,
        "mutation_log": lambda: (m := rd("mutation_controls.json"))["all_caught"] and m["all_restored"] and [x["mutation"] for x in m["controls"]] == json.loads(CONFIG.read_text())["mutation_controls"] and len(m["controls"]) == 38,
        "clean_clone": lambda: _clone_ok(), "repair_target_recorded": lambda: _target_recorded(), "protected_final": lambda: rd("protected_artifact_final.json")["protected_artifact_drift"] is False, "lock_ok": lambda: _lock_ok(),
        "task_pass": lambda: lib.registry("manifests/final_eval_repair/task_registry_v1.csv", "task_id").get("FINAL-EVAL-REPAIR-002") == "PASS", "gate_pass": lambda: lib.registry("manifests/final_eval_repair/gate_registry_v1.csv", "gate_id").get("FERG1") == "PASS",
        "no_new_phase": lambda: _no_new_phase(),
    }


def evaluate() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text())
    frozen = config["ferg1_criteria"]
    if len(frozen) != config["criteria_count"]:
        raise RuntimeError("FERG1_FROZEN_CRITERIA_CHANGED")
    from scripts.final_eval_repair_002_protected_audit import final as protected_final

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
    failed = [r["id"] for r in rows if not r["pass"]]
    inv = ee.inventory(ROOT)
    try:
        target = rd("repair_target.json")["repair_target_sha"]
    except Exception:
        target = None
    return {"gate": "FERG1", "mode": "PRE_TRANSITION" if PRE else "FINAL", "criteria_count": len(rows), "passed_count": len(rows) - len(failed), "failed_count": len(failed), "failed": failed, "repair_target_sha": target, **{f"{k}_status": v for k, v in status.items()},
            "landing_file_count": inv["landing_file_count"], "landing_high_risk_strings": inv["high_risk_strings"], "landing_claims_by_classification": inv["by_classification"], "protected_drift": not cache.get("protected_final", (False, ""))[0], "all_decided_pass": not failed, "final_decision": "FERG1_PASS" if not failed else "FERG1_FAIL", "criteria": rows}


def main() -> int:
    r = evaluate()
    (EVD / ("ferg1_pre_transition.json" if PRE else "ferg1_criteria.json")).write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: r[k] for k in ("mode", "all_decided_pass", "failed", "passed_count", "criteria_count")}))
    return 0 if r["all_decided_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
