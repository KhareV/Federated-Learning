# ruff: noqa: E501
"""CLERK-LIVE-001 / CLERKG0 frozen evaluator: the code that decides the connected-auth gate. It exists and is frozen in the connected
TARGET commit BEFORE the canonical real-Clerk E2E. It reads only committed-format evidence, the repository and git; criteria live in
configs/clerk_connected/clerk_live_001_protocol_v1.json.
  --pre-decision   defer only the result-transition checks (task/gate registry PASS, decision)
  --write-decision (with --pre-decision) write connected_decision.json iff every non-deferred criterion passes
  (no flag)        strict final evaluation of all criteria; writes clerk_g0_criteria.json"""

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

from scripts import clerk_connected_lib as lib

ROOT = Path(__file__).resolve().parents[1]
EVD = Path(os.environ.get("CLERK_EVD", ROOT / "reports/clerk_connected/clerk_live_001"))
CONFIG = ROOT / "configs/clerk_connected/clerk_live_001_protocol_v1.json"
ENTRY = "be2e4473223876699e74b64adc72672453ebc34b"
PRE = "--pre-decision" in sys.argv
WRITE_DECISION = "--write-decision" in sys.argv
DEFERRED = {"task_pass", "gate_pass", "decision_accept"}
SECRET = os.environ.get("CLERK_SECRET_KEY", "")
STEPS = ("signin", "identity", "monitoring", "history", "federation", "models", "research-ml", "research-fl", "system-page", "refresh", "logout")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def drift(*paths: str) -> list[str]:
    return git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *paths).split()


def added() -> list[str]:
    return git("diff", "--name-only", "--diff-filter=A", ENTRY).split() + git("ls-files", "--others", "--exclude-standard").split()


def rd(name: str, base: Path | None = None) -> dict[str, Any]:
    return json.loads(((base or EVD) / name).read_text(encoding="utf-8"))


def registry(name: str, key: str) -> dict[str, str]:
    with (ROOT / f"manifests/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        return {r[key]: r["status"] for r in csv.DictReader(h)}


def tag_target() -> str:
    return subprocess.run(["git", "ls-remote", "origin", "refs/tags/capstone-release-v1^{}"], cwd=ROOT, capture_output=True, text=True).stdout.split("\t")[0]


def e2e_core(base: Path) -> dict[str, bool]:
    """The real-Clerk E2E facts, evaluated from one E2E evidence directory (used for the canonical run AND the clean clone)."""
    full, me, signin = rd("connected_full_system_e2e.json", base), rd("real_me_audit.json", base), rd("real_signin_e2e.json", base)
    mon, fed, own = rd("monitoring_websocket_real_clerk.json", base), rd("federation_websocket_real_clerk.json", base), rd("cross_user_ownership.json", base)
    rest, logout, refresh = rd("real_rest_auth_audit.json", base), rd("logout_relogin.json", base), rd("refresh_restore.json", base)
    persist, wp = rd("persistence_restart.json", base), rd("wrong_authorized_party_negative.json", base)
    sec, build, sq = rd("secret_leak_audit.json", base), rd("frontend_bundle_secret_audit.json", base), rd("sqlite_secret_audit.json", base)
    own_chk = lib.ownership_ok(own["b_rest"]["ui_navigation"], own["b_rest"]["probes"], own["b_websockets"])
    fedrun = full["federation_run_rest"]
    storage = [full["user_a_storage_scan"], full["user_b_storage_scan"]]
    return {
        "signin": signin["status"] == "PASS" and signin["real_clerk_test_instance"] is True and signin["mocked_clerk"] is False and signin["clerk_ui_rendered"] and not signin["demo_button_present_in_clerk_mode"],
        "identity": lib.identity_ok(me["system"], me["me"])["ok"] and me["status"] == "PASS" and me["demo_fallback"] is False,
        "rest_bearer": rest["status"] == "PASS" and rest["token_value_recorded"] is False and not rest["demo_acknowledgement_creates_identity"],
        "invalid_rejected": all(rest["unauthenticated_and_invalid"][k] == 401 for k in ("no_token", "garbage_bearer", "jwt_shaped_garbage", "demo_acknowledgement_as_bearer", "demo_identity_header", "protected_sessions_no_token")),
        "monitoring_rest": full["monitoring"]["finalState"] == "COMPLETED" and full["monitoring"]["models"] == ["MODEL_V2_FINAL"] and full["history"]["summaryStatus"] == 200 and full["history"]["timelineStatus"] == 200 and full["history"]["listed"],
        "monitoring_ws": mon["status"] == "PASS" and lib.ws_evidence_ok(mon["websocket"], "sessionIdInPathIsOwned") and mon["session_completed"],
        "monitoring_ws_no_token": mon["websocket"]["urlHasToken"] is False and mon["token_in_url"] is False,
        "federation_rest": fedrun["status"] == 200 and fedrun["run_status"] == "COMPLETED" and fedrun["run_type"] == "LIVE_RUN" and fedrun["algorithm"] == "FEDAVG" and fedrun["secagg_mode"] == "SECAGG_SHADOW" and bool(full["federation"].get("preRunRest")) and all(r["status"] == 200 and r["bearer_present"] is not False for r in full["federation"]["preRunRest"]) and any(r["bearer_present"] is True for r in full["federation"]["preRunRest"]),
        "federation_ws": fed["status"] == "PASS" and lib.ws_evidence_ok(fed["websocket"], "runIdInPathIsOwned") and "COMPLETED" in fed["run_status_text"],
        "federation_ws_no_token": fed["websocket"]["urlHasToken"] is False and fed["token_in_url"] is False,
        "logout": logout["status"] == "PASS" and lib.unauth_ws_rejected(logout["websocket_after_logout"]) and logout["rest_without_token_after_logout"]["status"] == 401 and logout["logout"]["demoFallback"] is False and not logout["logout"]["identityChipVisibleAfter"] and logout["logout"]["appRedirectsToSignIn"],
        "refresh": refresh["status"] == "PASS" and refresh["refresh"]["same_user_id"] and refresh["nhm_persists_token"] is False,
        "no_token_storage": all(not s[k]["jwtLike"] for s in storage for k in ("localStorage", "sessionStorage", "indexedDB")),
        "secrets": sec["status"] == "PASS" and all(v["files_with_exact_secret"] == 0 for v in sec["scopes"].values()) and build["status"] == "PASS" and sq["status"] == "PASS" and sec["secret_value_recorded"] is False,
        "ownership": own["status"] == "PASS" and own_chk["ok"] and own["two_distinct_real_clerk_users"] and own["b_global_read"]["research_ml_status"] == 200 and own["b_own_list"]["contains_a_session"] is False,
        "persistence": persist["status"] == "PASS" and persist["same_owner_after_restart"] and persist["backend_restarted_same_sqlite"],
        "wrong_party": wp["status"] == "PASS" and wp["wildcard_used"] is False and wp["real_clerk_session_established"] and not wp["identity_chip_visible"] and wp["demo_fallback"] is False,
        "journey": all(full[k] for k in ("monitoring", "history", "federation", "models", "research_ml", "research_fl", "system_page")) and not full["console_errors"] and full["research_ml"]["status"] == 200 and full["research_fl"]["status"] == 200 and full["system_page"]["simulatedOnly"],
        "candidate": lib.candidate_ok(full["models"])["ok"],
        "network": bool(full["clerk_owned_hosts"]) and any(h.endswith("clerk.accounts.dev") for h in full["clerk_owned_hosts"]),
        "fed_facts": full["federation"]["maxClientsSubmittedAtOnce"] == 8 and full["federation"]["updatesText"] == "24" and full["federation"]["secaggShadowVerifiedSeen"] and full["federation"]["aggregationPlainSeen"],
    }


def build_checks() -> dict[str, Callable[[], bool]]:
    c: dict[str, Callable[[], bool]] = {}
    core = lambda: e2e_core(EVD)  # noqa: E731
    cfg = lambda: json.loads(CONFIG.read_text())  # noqa: E731
    full = lambda: rd("connected_full_system_e2e.json")  # noqa: E731
    cred = lambda: rd("credential_handling_audit.json")  # noqa: E731
    dev = lambda: rd("test_report.json")  # noqa: E731
    target = lambda: rd("connected_target.json")  # noqa: E731
    clone = lambda: rd("clean_connected_clone.json")  # noqa: E731
    sci = lambda: rd("scientific_noninterference.json")  # noqa: E731
    flni = lambda: rd("fl_noninterference.json")  # noqa: E731
    sec = lambda scope: rd("secret_leak_audit.json")["scopes"][scope]["files_with_exact_secret"] == 0  # noqa: E731
    store = lambda key: all(not s[key]["jwtLike"] for s in (full()["user_a_storage_scan"], full()["user_b_storage_scan"]))  # noqa: E731
    c.update({
        "closed_lineage": lambda: all(v == "PASS" for v in registry("capstone/task", "task_id").values()) and set(registry("capstone/task", "task_id")) == {f"CAP-{i:03d}" for i in range(1, 12)} and all(v == "PASS" for v in registry("capstone/gate", "gate_id").values()) and set(registry("capstone/gate", "gate_id")) == {f"CAPG{i}" for i in range(11)},
        "release_untouched": lambda: not git("diff", "--name-only", ENTRY, "--", "reports/capstone", "artifacts/capstone/CAPSTONE_RELEASE_MANIFEST_V1.json", "artifacts/capstone/CAPSTONE_RELEASE_PROTOCOL_V1.lock.json", "configs/capstone/cap_011_release_policy_v1.json", "configs/capstone/cap_011_release_protocol_v1.json", "docs/capstone/CAPSTONE_RELEASE_GUIDE_V1.md").strip(),
        "tag_unchanged": lambda: lib.tag_ok(tag_target()),
        "no_sci_drift": lambda: not drift("checkpoints", "reports/model_v2", "src", "simulation", "privacy", "contracts", ":(glob)artifacts/*.json"),
        "no_runtime_drift": lambda: not drift("artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/ROLLBACK_RUNTIME_BINDING_V1.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "api", "product", "capstone_persistence", "src"),
        "no_fl_drift": lambda: not drift("federated", "reports/model_v2", "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "artifacts/FEDPROX_MU_V2.lock.json", "product/federation", "product/models"),
        "no_personal_model": lambda: sci()["personal_model"] is False and not [p for p in added() if re.search(r"personal_model|personali[sz]", p, re.I)],
        "fl_isolation": lambda: flni()["status"] == "PASS" and lib.fl_isolation_static(ROOT)["ok"] and flni()["monitoring_session_data_enters_fl"] is False,
        "keys_not_committed": lambda: cred()["status"] == "PASS" and cred()["secret_committed"] is False and (not SECRET or subprocess.run(["git", "grep", "-qF", "--untracked", "-e", SECRET], cwd=ROOT).returncode != 0) and (not SECRET or not git("log", "--all", "--format=%H", f"{ENTRY}..HEAD", "-S" + SECRET).strip()),
        "no_key_rotation": lambda: cred()["key_rotation_performed"] is False and cred()["key_revocation_performed"] is False,
        "key_mapping": lambda: rd("frontend_key_mapping_audit.json")["status"] == "PASS" and lib.frontend_static_audit(ROOT, SECRET)["ok"],
        "backend_secret_var": lambda: rd("backend_clerk_config_audit.json")["status"] == "PASS" and "CLERK_SECRET_KEY" in rd("backend_clerk_config_audit.json")["secret_variable"] and rd("frontend_key_mapping_audit.json")["secret_passed_to_frontend_build"] is False,
        "parties_explicit": lambda: __import__("scripts.run_capstone_clerk_connected", fromlist=["x"]).resolve_config({"NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "pk_test_" + "Zm9vLmNsZXJrLmFjY291bnRzLmRldiQ", "CLERK_SECRET_KEY": "sk_test_" + "A" * 24}, 4173)["authorized_parties"] == ["http://127.0.0.1:4173"] and rd("wrong_authorized_party_negative.json")["real_origin"] == "http://127.0.0.1:4173",
        "no_wildcard_party": lambda: rd("wrong_authorized_party_negative.json")["wildcard_used"] is False and _wildcard_refused(),
        "official_clerkjs": lambda: json.loads((ROOT / "frontend/clerk-sdk/package.json").read_text())["dependencies"]["@clerk/clerk-js"] == "6.37.0" and "import('@clerk/clerk-js')" in (ROOT / "frontend/src/lib/product/auth.ts").read_text() and "ui.browser.js" in (ROOT / "frontend/src/lib/product/auth.ts").read_text(),
        "official_sdk": lambda: lib.backend_static_audit(ROOT)["ok"] and rd("backend_clerk_config_audit.json")["official_backend_sdk"].endswith("authenticate_request_async"),
        "no_custom_crypto": lambda: lib.backend_static_audit(ROOT)["ok"] and rd("backend_clerk_config_audit.json")["custom_jwt_crypto"] is False,
        "real_instance": lambda: core()["signin"] and core()["network"],
        "signin_pass": lambda: core()["signin"],
        "system_clerk": lambda: rd("real_me_audit.json")["system"]["auth_provider"] == "CLERK",
        "demo_false": lambda: rd("real_me_audit.json")["system"]["demo_mode"] is False and rd("real_me_audit.json")["me"]["demo_mode"] is False,
        "me_real": lambda: core()["identity"],
        "no_demo_fallback": lambda: rd("real_signin_e2e.json")["demo_button_present_in_clerk_mode"] is False and rd("logout_relogin.json")["logout"]["demoFallback"] is False and rd("wrong_authorized_party_negative.json")["demo_fallback"] is False and rd("real_me_audit.json")["demo_fallback"] is False,
        "rest_bearer": lambda: core()["rest_bearer"],
        "invalid_rejected": lambda: core()["invalid_rejected"],
        "monitoring_rest": lambda: core()["monitoring_rest"],
        "monitoring_ws_auth": lambda: core()["monitoring_ws"],
        "monitoring_ws_no_token": lambda: core()["monitoring_ws_no_token"],
        "federation_rest": lambda: core()["federation_rest"],
        "federation_ws_auth": lambda: core()["federation_ws"],
        "federation_ws_no_token": lambda: core()["federation_ws_no_token"],
        "logout_ok": lambda: core()["logout"],
        "refresh_ok": lambda: core()["refresh"],
        "no_token_localstorage": lambda: store("localStorage"),
        "no_token_sessionstorage": lambda: store("sessionStorage"),
        "no_token_indexeddb": lambda: store("indexedDB"),
        "secret_absent_frontend_src": lambda: sec("frontend_src") and rd("frontend_bundle_secret_audit.json")["exact_secret_in_frontend_src"] is False,
        "secret_absent_build": lambda: sec("frontend_build") and sec("frontend_build_secret_prefix") and rd("frontend_bundle_secret_audit.json")["status"] == "PASS",
        "secret_absent_logs": lambda: sec("logs") and sec("launcher_logs") and rd("secret_leak_audit.json")["secret_logged"] is False,
        "secret_absent_sqlite": lambda: rd("sqlite_secret_audit.json")["status"] == "PASS" and not rd("sqlite_secret_audit.json")["tables_with_secret_or_token"] and rd("sqlite_secret_audit.json")["password_column_present"] is False,
        "secret_absent_artifacts": lambda: sec("workspace") and sec("raw_driver_output"),
        "secret_absent_evidence": lambda: not SECRET or (not lib.find_secret(EVD, SECRET) and not lib.find_secret(EVD, lib.SECRET_PREFIX)) if SECRET else not lib.find_secret(EVD, lib.SECRET_PREFIX),
        "ownership_rest": lambda: core()["ownership"],
        "ownership_monitoring_ws": lambda: (rd("cross_user_ownership.json")["b_websockets"]["monitoring"]["closeCode"] == 4403 and not rd("cross_user_ownership.json")["b_websockets"]["monitoring"]["frames"] and core()["ownership"]),
        "ownership_federation": lambda: (rd("cross_user_ownership.json")["b_websockets"]["federation"]["closeCode"] == 4403 and any(p["label"].startswith("start A run") and p["status"] == 403 for p in rd("cross_user_ownership.json")["b_rest"]["probes"]) and core()["ownership"]),
        "persistence_ok": lambda: core()["persistence"],
        "identity_stable": lambda: rd("persistence_restart.json")["same_owner_after_restart"] is True and rd("logout_relogin.json")["relogin_identity"]["auth_provider"] == "CLERK",
        "model_unchanged": lambda: sci()["status"] == "PASS" and sci()["connected"]["monitoring_models"] == ["MODEL_V2_FINAL"] and full()["model_id"] == "MODEL_V2_FINAL",
        "cal_unchanged": lambda: all(str(x).startswith("CAL_V2") for x in sci()["connected"]["calibrations"]) and bool(sci()["connected"]["calibrations"]),
        "identity_no_ml_selection": lambda: sci()["identity_selects_model"] is False and sci()["status"] == "PASS",
        "fl_unchanged": lambda: flni()["status"] == "PASS" and flni()["clients"] == 8 and flni()["rounds"] == 3 and flni()["updates_total"] == 24 and core()["fed_facts"],
        "candidate_sandbox": lambda: core()["candidate"] and full()["models"]["candidate"][0]["sandbox_status"] == "IN_SANDBOX",
        "not_deployed": lambda: full()["models"]["candidate"][0]["production_deployed"] is False and full()["models"]["productionDeployed"] == ["FALSE"],
        "demo_works": lambda: rd("demo_mode_regression.json")["demo_auth_works"] is True,
        "demo_no_clerk": lambda: lib.demo_regression_ok(rd("demo_mode_regression.json"))["ok"],
        "demo_zero_clerk_traffic": lambda: rd("demo_mode_regression.json")["clerk_origins_contacted"] == [] and rd("demo_mode_regression.json")["external_requests"] == [],
        "connected_needs_clerk_network": lambda: core()["network"],
        "research_unchanged": lambda: sci()["status"] == "PASS" and flni()["candidate_digest_equals_offline_demo"] is True and full()["research_ml"]["status"] == 200,
        "journey_ok": lambda: core()["journey"],
        "history_ok": lambda: full()["history"]["previews"] >= 1 and full()["history"]["summaryStatus"] == 200,
        "federation_ok": lambda: core()["fed_facts"] and core()["federation_ws"],
        "models_ok": lambda: full()["models"]["candidates"] == 1 and full()["models"]["released_default"] == "MODEL_V2_FINAL",
        "research_ok": lambda: full()["research_ml"]["promotionDistinction"] and full()["research_fl"]["engineeringSeparate"],
        "no_new_science": lambda: not drift("checkpoints", "reports/model_v2", "src", "simulation", "privacy", "contracts", "federated") and not [p for p in added() if re.search(r"\.(pt|npz|npy|ckpt)$", p)],
        "no_heldout": lambda: _no_pattern(r"heldout|held_out|internal_test|incart"),
        "no_retrain": lambda: _no_pattern(r"retrain|recalibrat|\.fit\(|train_local|train_epoch"),
        "no_hardware": lambda: rd("real_me_audit.json")["system"]["physical_hardware_available"] is False and not [p for p in added() if re.search(r"ble_|bluetooth|serial_port|firmware", p, re.I)],
        "clone_ok": lambda: clone()["status"] == "PASS" and clone()["release_target_sha"] == target()["connected_target_sha"] and all(e2e_core(EVD / "clean_connected_clone_e2e").values()) and clone()["pre_install_audit"]["ok"] and clone()["checkout_matches_target"],
        "clone_fresh_browser": lambda: clone()["fresh_browser_profile"] is True and clone()["developer_browser_session_copied"] is False and rd("real_signin_e2e.json", EVD / "clean_connected_clone_e2e")["status"] == "PASS",
        "clone_no_session_copied": lambda: clone()["developer_browser_session_copied"] is False and clone()["developer_clerk_cookie_copied"] is False,
        "clone_no_db_copied": lambda: clone()["developer_db_copied"] is False and not any(v["kind"] == "copied_runtime_state" for v in clone()["pre_install_audit"]["violations"]),
        "clone_no_env_copied": lambda: clone()["developer_env_copied"] is False and not any(v["kind"] == "developer_dotenv" for v in clone()["pre_install_audit"]["violations"]) and clone()["credentials_supplied_externally"] is True,
        "target_clean_pushed": lambda: target()["working_tree_clean"] is True and target()["pushed"] is True and target()["local_head"] == target()["connected_target_sha"] == target()["origin_main"],
        "protected_final": lambda: rd("protected_artifact_final.json")["protected_artifact_drift"] is False,
        "dev_regression": lambda: dev()["full_regression"]["returncode"] == 0 and not dev()["full_regression"]["failed"] and dev()["inherited_flake"]["status"] == "PASS_INHERITED_FLAKE_POLICY" and dev()["targeted"]["returncode"] == 0,
        "dev_frontend_tests": lambda: dev()["commands"]["vitest"]["returncode"] == 0,
        "dev_svelte": lambda: dev()["commands"]["svelte_check"]["returncode"] == 0 and dev()["frontend_summary"]["svelte_check_zero_errors"],
        "dev_build": lambda: dev()["commands"]["build"]["returncode"] == 0,
        "dev_ruff": lambda: dev()["commands"]["ruff"]["returncode"] == 0,
        "dev_pip": lambda: dev()["commands"]["pip_check"]["returncode"] == 0,
        "mutation_log": lambda: (m := rd("mutation_controls.json"))["all_caught"] and m["all_restored"] and [x["mutation"] for x in m["controls"]] == cfg()["mutation_controls"] and len(m["controls"]) == 20,
        "wrong_party_rejected": lambda: core()["wrong_party"],
        "ui_chain_ok": lambda: _ui_chain(),
        "frontend_scope_exact": lambda: sorted(set(git("diff", "--name-only", "--diff-filter=AM", ENTRY, "--", "frontend").split() + [p for p in added() if p.startswith("frontend/")])) == sorted(json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json").read_text())["changed_from_predecessor"]),
        "ci_untouched": lambda: dev()["ci_queried"] is False and dev()["ci_triggered"] is False and not [p for p in git("ls-files", "scripts/clerk_*", "scripts/run_capstone_clerk_*").split() if re.search(r"\"gh\"|'gh'|api\.github|actions/runs", (ROOT / p).read_text()) and "evaluate_gate" not in p],
        "task_pass": lambda: registry("clerk_connected/task", "task_id").get("CLERK-LIVE-001") == "PASS",
        "gate_pass": lambda: registry("clerk_connected/gate", "gate_id").get("CLERKG0") == "PASS",
        "decision_accept": lambda: rd("connected_decision.json")["decision"] == "ACCEPT" and rd("connected_decision.json")["release_id"] == "CAPSTONE_CLERK_CONNECTED_V1" and rd("connected_decision.json")["connected_target_sha"] == target()["connected_target_sha"] and rd("connected_decision.json")["claim"] == cfg()["claim"],
    })
    return c


def _wildcard_refused() -> bool:
    from scripts.run_capstone_clerk_connected import ConnectedConfigError, resolve_config

    try:
        resolve_config({"NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "pk_test_" + "Zm9vLmNsZXJrLmFjY291bnRzLmRldiQ", "CLERK_SECRET_KEY": "sk_test_" + "A" * 24, "NHM_CLERK_AUTHORIZED_PARTIES": "*"}, 4173)
    except ConnectedConfigError:
        return True
    return False


def _no_pattern(pattern: str) -> bool:
    rx = re.compile(pattern, re.I)
    for p in added():
        scoped = p.endswith((".py", ".mjs", ".ts")) and p.startswith(("scripts/clerk_", "scripts/run_capstone_clerk", "tests/test_clerk", "scripts/verify_clerk", "scripts/freeze_capstone_ui_v1_3"))
        if scoped and "evaluate_gate" not in p and "mutation_controls" not in p and rx.search((ROOT / p).read_text(errors="ignore")):
            return False
    return True


def _ui_chain() -> bool:
    from scripts.verify_capstone_ui_v1 import verify as v1
    from scripts.verify_capstone_ui_v1_1 import verify as v11
    from scripts.verify_capstone_ui_v1_2 import verify as v12
    from scripts.verify_capstone_ui_v1_3 import verify as v13

    ok = all(f()["status"] == "PASS" for f in (v1, v11, v12, v13))
    return ok and not git("diff", "--name-only", ENTRY, "--", "artifacts/capstone/CAPSTONE_UI_V1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json").strip()


def evaluate() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    frozen = config["clerkg0_criteria"]
    if len(frozen) != config["criteria_count"] or [r["id"] for r in frozen] != [f"CLERKG0-{i:03d}" for i in range(1, len(frozen) + 1)]:
        raise RuntimeError("CLERKG0_FROZEN_CRITERIA_CHANGED")
    from scripts.clerk_live_001_protected_audit import final as protected_final

    protected_final()
    checks = build_checks()
    cache: dict[str, tuple[bool, str]] = {}

    def run_check(name: str) -> tuple[bool, str]:
        if name not in cache:
            if PRE and name in DEFERRED:
                cache[name] = (True, "DEFERRED_TO_RESULT_TRANSITION")
            else:
                try:
                    cache[name] = (bool(checks[name]()), "")
                except Exception as error:   # a failed check, never a crash
                    cache[name] = (False, f"{type(error).__name__}:{str(error)[:140]}")
        return cache[name]

    rows = []
    for row in frozen:
        res = [(chk, *run_check(chk)) for chk in row["checks"]]
        rows.append({"id": row["id"], "text": row["text"], "pass": all(r[1] for r in res), "checks": [{"check": n, "pass": ok, **({"note": why} if why else {})} for n, ok, why in res]})
    return {"gate": "CLERKG0", "mode": "PRE_DECISION" if PRE else "FINAL", "criteria_count": len(rows), "all_decided_pass": all(r["pass"] for r in rows), "failed": [r["id"] for r in rows if not r["pass"]], "criteria": rows}


def write_decision(config: dict[str, Any]) -> None:
    target = rd("connected_target.json")
    decision = {"decision_id": "CAPSTONE_CLERK_CONNECTED_DECISION_V1", "release_id": "CAPSTONE_CLERK_CONNECTED_V1", "connected_target_sha": target["connected_target_sha"], "decision": "ACCEPT", "claim": config["claim"], "claim_not": config["claim_not"], "limitations": config["limitations"],
                "offline_profile": "DEMO (preserved, unchanged)", "connected_profile": "CLERK (real TEST instance verified)", "released_monitoring_model": "MODEL_V2_FINAL", "candidate_deployed": False, "physical_hardware": False, "capstone_release_v1_untouched": True,
                "note": "Successor to the offline capstone release; does not modify CAPSTONE_RELEASE_V1 or its tag."}
    (EVD / "connected_decision.json").write_text(json.dumps(decision, indent=1, sort_keys=True) + "\n")


def main() -> int:
    result = evaluate()
    (EVD / ("clerk_g0_pre_decision.json" if PRE else "clerk_g0_criteria.json")).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"mode": result["mode"], "all_decided_pass": result["all_decided_pass"], "failed": result["failed"]}))
    if PRE and WRITE_DECISION:
        if result["all_decided_pass"]:
            write_decision(json.loads(CONFIG.read_text()))
            print("connected_decision.json written: ACCEPT")
        else:
            print("NO DECISION WRITTEN")
            return 1
    return 0 if result["all_decided_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
