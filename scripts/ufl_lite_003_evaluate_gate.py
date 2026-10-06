# ruff: noqa: E501
"""UFL-LITE-003 / UFLG2 frozen fail-closed evaluator (criteria: configs/ufl_lite/uflg2_protocol_v1.json). --pre-transition defers only the registry PASS checks.
Real-Clerk observation checks (G:group.check) are RE-DERIVED here from the sanitized observations; recorded verdicts are never trusted."""

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

from scripts import ufl_lite_003_lib as an
from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
EVD = Path(os.environ.get("UFL_EVD", ROOT / "reports/ufl_lite/ufl_lite_003"))
CONFIG = ROOT / "configs/ufl_lite/uflg2_protocol_v1.json"
LOCK = ROOT / "artifacts/ufl_lite/UFL_LITE_003_PROTOCOL_V1.lock.json"
ENTRY = "9324ef40ecb8fdecfc4880aa827bc68b45e4f9a0"
DEMO_DIGEST = "3a57614e15264f3cd7661a016a30d033aab78647d57be04273c386cc9d048726"
PRE = "--pre-transition" in sys.argv
DEFERRED = {"task_pass", "gate_pass"}
ADDITIVE = ("manifests/ufl_lite/", "configs/ufl_lite/", "docs/ufl_lite/", "artifacts/ufl_lite/", "reports/ufl_lite/", "scripts/ufl_lite_003_", "tests/test_ufl_lite_003_")
MODIFIABLE = ("manifests/ufl_lite/task_registry_v1.csv", "manifests/ufl_lite/gate_registry_v1.csv")


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def rd(name: str) -> dict[str, Any]:
    return json.loads((EVD / name).read_text())


def drift(*paths: str) -> list[str]:
    return git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *paths).split()


def registry(name: str, key: str) -> dict[str, str]:
    with (ROOT / f"manifests/ufl_lite/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        return {r[key]: r["status"] for r in csv.DictReader(h)}


def tags() -> dict[str, str]:
    return {t: subprocess.run(["git", "ls-remote", "origin", f"refs/tags/{t}^{{}}"], cwd=ROOT, capture_output=True, text=True).stdout.split("\t")[0] for t in lib.RELEASE_TAGS}


def delta_outside_additive(rev: str) -> list[str]:
    changed = git("diff", "--name-only", ENTRY, rev).split()
    entry_files = set(git("ls-tree", "-r", "--name-only", ENTRY).split())
    return [p for p in changed if not p.startswith(ADDITIVE) or (p in entry_files and p not in MODIFIABLE)]


def observations(name: str = "owner_e2e_observations.json", base: Path | None = None) -> dict[str, dict[str, bool]]:
    o = json.loads(((base or EVD) / name).read_text())
    return an.analyze_all(o["A"], o["B"], o["A_return"], lib.load_baseline(ROOT))


def _g(path: str, base: Path | None = None) -> bool:
    group, check = path.split(".")
    return bool(observations(base=base)[group][check])


def build_checks() -> dict[str, Callable[[], bool]]:
    base = lambda: lib.load_baseline(ROOT)  # noqa: E731
    rep = lambda: rd("test_report.json")  # noqa: E731
    return {
        "entry_audited": lambda: rd("entry_audit.json")["entry_sha"] == ENTRY and rd("entry_audit.json")["origin_main_sha"] == ENTRY and rd("entry_audit.json")["uflg0_pass_and_lock_verified"] is True and rd("entry_audit.json")["uflg1_pass_and_lock_verified"] is True,
        "prior_phases_preserved": lambda: registry("task", "task_id").get("UFL-LITE-001") == "PASS" and registry("task", "task_id").get("UFL-LITE-002") == "PASS" and registry("gate", "gate_id").get("UFLG0") == "PASS" and registry("gate", "gate_id").get("UFLG1") == "PASS"
        and not git("diff", "--name-only", ENTRY, "--", "reports/ufl_lite/ufl_lite_001", "reports/ufl_lite/ufl_lite_002", "configs/ufl_lite/user_bound_fl_participation_v1.json", "configs/ufl_lite/uflg0_protocol_v1.json", "configs/ufl_lite/uflg1_protocol_v1.json", "artifacts/ufl_lite/UFL_LITE_001_PROTOCOL_V1.lock.json", "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.lock.json", "docs/ufl_lite").strip(),
        "tags_unchanged": lambda: lib.tags_ok(tags()),
        "locks_verify": lambda: _locks(),
        "acceptance_target_recorded": lambda: _target_recorded(),
        "no_product_delta_at_target": lambda: not delta_outside_additive(rd("acceptance_target.json")["acceptance_target_sha"]),
        "no_product_delta_at_head": lambda: not delta_outside_additive("HEAD"),
        "ui_locks_identical": lambda: not git("diff", "--name-only", ENTRY, "--", "artifacts/capstone").strip() and not git("diff", "--name-only", ENTRY, "--", "scripts/verify_capstone_ui_v1.py", "scripts/verify_capstone_ui_v1_1.py", "scripts/verify_capstone_ui_v1_2.py", "scripts/verify_capstone_ui_v1_3.py", "scripts/verify_capstone_ui_v1_4.py").strip(),
        "ui14_ok": lambda: _ui14(),
        "no_new_amendments": lambda: not [p for p in git("diff", "--name-only", "--diff-filter=A", ENTRY).split() if "amendment" in p],
        "e2e_real_clerk_flags": lambda: _flags(),
        "demo_digest": lambda: rd("demo_regression.json")["semantic_sha256"] == DEMO_DIGEST and rd("demo_regression.json")["equals_canonical"] is True,
        "demo_regression": lambda: (d := rd("demo_regression.json"))["status"] == "PASS" and d["demo_auth_works"] is True and d["clerk_global_in_browser"] is False and d["external_requests"] == [] and d["blocked_external_requests"] == [] and d["clerk_origins_contacted"] == [],
        "secret_audit_clean": lambda: _secret_clean(),
        "owner_not_persisted": lambda: rd("secret_and_persistence_audit.json")["owner_binding_persisted_in_sqlite"] == [] and rd("secret_and_persistence_audit.json")["sqlite_tables_with_secret_or_token"] == [],
        "credentials_external": lambda: _credentials(),
        "b_site00_93": lambda: base()["datasets"]["SIM_FL_SITE_00"]["local_example_count"] == 93 and base()["datasets"]["SIM_FL_SITE_00"]["dataset_sha256"].startswith("fca44709"),
        "b_client_count": lambda: base()["client_count"] == 8 and lib.cohort_ok(base()["client_ids"])["ok"],
        "b_rounds": lambda: base()["planned_rounds"] == 3,
        "b_updates": lambda: base()["total_updates"] == 24 and base()["accepted_updates_per_round"] == [8, 8, 8],
        "b_digest": lambda: base()["canonical_candidate_digest"] == lib.CANONICAL_CANDIDATE_DIGEST,
        "b_candidate": lambda: lib.candidate_state_ok(base()["candidate"]),
        "h_scientific": lambda: lib.hash_drift(ROOT, base(), "scientific") == [] and base()["released_monitoring_model"] == "MODEL_V2_FINAL" and base()["calibration"] == "CAL_V2",
        "no_backend_change": lambda: not drift("api", "product", "capstone_persistence", "src", "privacy", "simulation"),
        "no_api_change": lambda: not drift("api", "contracts") and lib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_db_change": lambda: not drift("capstone_persistence") and lib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_fl_change": lambda: not drift("federated", "product/federation", "product/edge", "product/models") and lib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "no_auth_change": lambda: not drift("product/auth", "frontend/src/lib/product/auth.ts", "scripts/run_capstone_clerk_connected.py") and lib.hash_drift(ROOT, base(), "auth") == [],
        "frontend_unchanged": lambda: not drift("frontend"),
        "global_page_unchanged": lambda: not drift("frontend/src/routes/app/federation/clients/+page.svelte") and lib.global_view_binding_audit(ROOT)["ok"],
        "helper_pure": lambda: _presentation_audits(),
        "claims_clean": lambda: _claims(),
        "monitoring_unchanged": lambda: not drift("checkpoints", "reports/model_v2", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json"),
        "clean_clone_a": lambda: _clone_a(),
        "clean_clone_b": lambda: _clone_b(),
        "clean_clone_target_matches": lambda: _clone_target(),
        "fe_tests": lambda: rep()["frontend"]["vitest_returncode"] == 0 and rep()["frontend"]["failed"] == 0 and rep()["frontend"]["passed"] >= 210,
        "fe_check": lambda: rep()["frontend"]["svelte_check"]["returncode"] == 0 and rep()["frontend"]["svelte_check"]["errors"] == 0,
        "fe_build": lambda: rep()["frontend"]["build_returncode"] == 0,
        "py_targeted": lambda: rep()["targeted_python"]["returncode"] == 0 and rep()["targeted_python"]["counts"].get("failed", 0) == 0,
        "py_full": lambda: rep()["full_python"]["returncode"] == 0 and not rep()["full_python"]["failed"] and rep()["inherited_flake"]["status"] == "PASS_INHERITED_FLAKE_POLICY",
        "lint": lambda: rep()["commands"]["ruff"]["returncode"] == 0 and rep()["commands"]["pip_check"]["returncode"] == 0,
        "ci_untouched": lambda: rep()["ci_queried"] is False and rep()["ci_triggered"] is False,
        "mutation_log": lambda: (m := rd("mutation_controls.json"))["all_caught"] and m["all_restored"] and [x["mutation"] for x in m["controls"]] == json.loads(CONFIG.read_text())["mutation_controls"] and len(m["controls"]) == 35,
        "protected_final": lambda: rd("protected_artifact_final.json")["protected_artifact_drift"] is False,
        "lock_ok": lambda: _lock_ok(),
        "task_pass": lambda: registry("task", "task_id").get("UFL-LITE-003") == "PASS",
        "gate_pass": lambda: registry("gate", "gate_id").get("UFLG2") == "PASS",
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

    return all(f()["status"] == "PASS" for f in (v1, v11, v12, v13, v14))


def _target_recorded() -> bool:
    t = rd("acceptance_target.json")
    sha = t["acceptance_target_sha"]
    return (bool(re.fullmatch(r"[0-9a-f]{40}", sha)) and sha != ENTRY and t["pushed_to_origin_main_at_record"] is True and t["protected_tree_delta_from_entry"] == [] and t["canonical_evidence_existed_at_target"] is False
            and subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=ROOT).returncode == 0
            and all(subprocess.run(["git", "cat-file", "-e", f"{sha}:{p}"], cwd=ROOT).returncode == 0 for p in json.loads(LOCK.read_text())["bound_files"]))


def _flags() -> bool:
    a = rd("owner_e2e_analysis.json")
    obs = observations()
    return (a["label"] == "CANONICAL" and a["real_clerk_test_instance"] is True and a["mocked_clerk"] is False and a["demo_fallback"] is False and all(all(c.values()) for g, c in obs.items() if g != "clerk_network") and all(a["groups"][g]["all_pass"] for g in a["groups"])
            and a["clerk_hosts_contacted"] is True)


def _secret_clean() -> bool:
    s = rd("secret_and_persistence_audit.json")
    if not s["clean"] or any(s["scopes"].values()):
        return False
    secret = os.environ.get("CLERK_SECRET_KEY", "")
    if not secret:
        return False
    hit = subprocess.run(["git", "grep", "-lF", "--untracked", "-e", secret], cwd=ROOT, capture_output=True, text=True).stdout.split()
    scan = [str(p.relative_to(ROOT)) for p in EVD.rglob("*") if p.is_file() and secret.encode() in p.read_bytes()]
    return not hit and not scan


def _credentials() -> bool:
    secret = os.environ.get("CLERK_SECRET_KEY", "")
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=ROOT, capture_output=True).returncode == 0
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    staged = subprocess.run(["git", "grep", "-lF", "--cached", "-e", secret], cwd=ROOT, capture_output=True, text=True).stdout.split() if secret else ["NO_SECRET_IN_ENV"]
    return not tracked and ignored and not staged


def _presentation_audits() -> bool:
    from scripts import ufl_lite_002_lib as plib

    return plib.helper_audit()["ok"] and plib.grid_audit()["ok"] and plib.live_audit()["ok"]


def _claims() -> bool:
    from scripts import ufl_lite_002_lib as plib

    return plib.text_audit()["ok"]


def _clone() -> dict[str, Any]:
    return json.loads((EVD / "clean_clone/clean_clone.json").read_text())


def _clone_a() -> bool:
    c = _clone()
    return c["status"] == "PASS" and c["proof_a_clean_clone"]["status"] == "PASS" and c["proof_a_clean_clone"]["tree_clean_after_checkout"] is True and c["proof_a_clean_clone"]["pre_install_audit_ok"] is True and c["proof_a_clean_clone"]["fresh_venv_created_by_run"] is True and c["developer_env_or_db_or_cookie_copied"] is False


def _clone_b() -> bool:
    c = _clone()
    obs = observations("owner_e2e_observations.json", EVD / "clean_clone")
    return c["proof_b_connected_in_clone"]["status"] == "PASS" and all(all(v.values()) for g, v in obs.items() if g != "clerk_network") and obs["clerk_network"]["clerk_hosts_contacted"] and json.loads((EVD / "clean_clone/secret_and_persistence_audit.json").read_text())["clean"] is True


def _clone_target() -> bool:
    c, t = _clone(), rd("acceptance_target.json")["acceptance_target_sha"]
    return c["target_sha"] == t and c["proof_a_clean_clone"]["checkout_sha"] == t and c["proof_a_clean_clone"]["checkout_matches_target"] is True and c["tracked_modified_after_execution"] == []


def _lock_ok() -> bool:
    lock = json.loads(LOCK.read_text())
    return all(lib.sha(ROOT / p) == h for p, h in lock["bound_files"].items()) and lock["criteria_count"] == json.loads(CONFIG.read_text())["criteria_count"]


def evaluate() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text())
    frozen = config["uflg2_criteria"]
    if len(frozen) != config["criteria_count"]:
        raise RuntimeError("UFLG2_FROZEN_CRITERIA_CHANGED")
    from scripts.ufl_lite_003_protected_audit import final as protected_final

    protected_final()
    checks = build_checks()
    cache: dict[str, tuple[bool, str]] = {}

    def run(name: str) -> tuple[bool, str]:
        if name not in cache:
            if PRE and name in DEFERRED:
                cache[name] = (True, "DEFERRED")
            else:
                try:
                    cache[name] = (_g(name[2:]) if name.startswith("G:") else bool(checks[name]()), "")
                except Exception as e:
                    cache[name] = (False, f"{type(e).__name__}:{str(e)[:120]}")
        return cache[name]

    rows = []
    for row in frozen:
        res = [(c, *run(c)) for c in row["checks"]]
        rows.append({"id": row["id"], "text": row["text"], "pass": all(r[1] for r in res), "checks": [{"check": n, "pass": ok, **({"note": w} if w else {})} for n, ok, w in res]})
    return {"gate": "UFLG2", "mode": "PRE_TRANSITION" if PRE else "FINAL", "criteria_count": len(rows), "all_decided_pass": all(r["pass"] for r in rows), "failed": [r["id"] for r in rows if not r["pass"]], "criteria": rows}


def main() -> int:
    r = evaluate()
    (EVD / ("uflg2_pre_transition.json" if PRE else "uflg2_criteria.json")).write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"mode": r["mode"], "all_decided_pass": r["all_decided_pass"], "failed": r["failed"]}))
    return 0 if r["all_decided_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
