# ruff: noqa: E501
"""CAPSTONE_RELEASE_PROTOCOL_V1 / CAPG10 frozen evaluator: the code that decides clean-clone PASS/FAIL. It exists and is
frozen in the release-target commit BEFORE Clone A. It only reads imported clone evidence, the repository and git; it
never defines criteria (they are frozen in configs/capstone/cap_011_release_protocol_v1.json).

  --pre-decision   evaluate everything except the checks that depend on the decision/result transition
  --write-decision (with --pre-decision) write reports/capstone/cap_011/release_decision.json iff every non-deferred hard blocker passes
  (no flag)        strict final evaluation of all 136 criteria; writes capg10_criteria.json"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.capstone_release_lib import (
    MANIFEST_PATH,
    audit_release_text,
    case_audit,
    guide_commands,
    portability_audit,
    sha256_file,
    verify_checkout,
    verify_clone_result,
    verify_final_diff,
)

ROOT = Path(__file__).resolve().parents[1]
EVD = ROOT / "reports/capstone/cap_011"
CONFIG = ROOT / "configs/capstone/cap_011_release_protocol_v1.json"
POLICY = ROOT / "configs/capstone/cap_011_release_policy_v1.json"
CLEAN = ROOT / "configs/capstone/cap_011_clean_clone_protocol_v1.json"
GUIDE = ROOT / "docs/capstone/CAPSTONE_RELEASE_GUIDE_V1.md"
LOCK = ROOT / "artifacts/capstone/CAPSTONE_RELEASE_PROTOCOL_V1.lock.json"
ENTRY = "af60c1e2bc6a645852d0826815ff16a678c9d0d1"
PRE = "--pre-decision" in sys.argv
WRITE_DECISION = "--write-decision" in sys.argv
DEFERRED = {"decision_accept", "decision_override_false", "final_evidence_only", "final_diff_ok", "cap011_pass", "capg10_pass", "all_tasks_pass", "all_gates_pass", "no_cap012_final", "claim_exact_decision"}
STEP_NAMES = ("sign-in", "overview", "device", "monitoring", "history", "federation", "models", "research-ml", "research-fl", "system", "about")
HANDOFF_SECTIONS: list[str] = []


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def rd(name: str) -> dict[str, Any]:
    return json.loads((EVD / name).read_text(encoding="utf-8"))


def target() -> str:
    return rd("release_target.json")["release_target_sha"]


def clone(x: str, kind: str) -> dict[str, Any]:
    data = rd(f"clean_clone_{x}_{kind}.json")
    check = verify_clone_result(data, target())
    if not check["ok"] or data["label"] != x.upper():
        raise ValueError(f"CLONE_RESULT_REJECTED:{x}:{kind}:{check['failures']}")
    return data


def statuses() -> tuple[dict[str, str], dict[str, str]]:
    out = []
    for name, key in (("task", "task_id"), ("gate", "gate_id")):
        with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
            out.append({r[key]: r["status"] for r in csv.DictReader(h)})
    return out[0], out[1]


def drift(*paths: str) -> list[str]:
    return git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *paths).split()


def added_since_entry() -> list[str]:
    return git("diff", "--name-only", "--diff-filter=A", ENTRY).split() + git("ls-files", "--others", "--exclude-standard").split()


def step(demo: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in demo["browser"]["steps"] if s["step"] == name)


def bound_since_target(path: str) -> bool:
    """The file is bound by the release lock AND byte-identical to its content in the release-target commit."""
    lock = json.loads(LOCK.read_text())
    if path not in lock["bound_files"]:
        return False
    blob = subprocess.run(["git", "show", f"{target()}:{path}"], cwd=ROOT, capture_output=True)
    return blob.returncode == 0 and __import__("hashlib").sha256(blob.stdout).hexdigest() == sha256_file(ROOT / path) == lock["bound_files"][path]


def lock_ok() -> bool:
    from scripts.cap_006_protected_audit import verify_amended_lock

    r = verify_amended_lock(LOCK, "CAPSTONE_RELEASE_PROTOCOL_V1.amendment_*.json")
    return not r["mismatches"] and not r["broken_chain_links"]


def lock_commit() -> str:
    return git("log", "--diff-filter=A", "--format=%H", "--", "artifacts/capstone/CAPSTONE_RELEASE_PROTOCOL_V1.lock.json").splitlines()[-1]


def is_ancestor(a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ROOT).returncode == 0


def frozen_before_clones(path: str) -> bool:
    return lock_ok() and bound_since_target(path) and is_ancestor(lock_commit(), target())


def exec_ids(x: str) -> list[dict[str, Any]]:
    return clone(x, "bundle")["executed_commands"]


def clone_checks(x: str) -> dict[str, Callable[[], bool]]:
    def env() -> dict[str, Any]:
        return clone(x, "environment")

    def inst() -> dict[str, Any]:
        return clone(x, "install")

    def tests() -> dict[str, Any]:
        return clone(x, "tests")

    def fe() -> dict[str, Any]:
        return clone(x, "frontend")

    def demo() -> dict[str, Any]:
        return clone(x, "demo")

    def gitau() -> dict[str, Any]:
        return clone(x, "git_audit")

    def rc(cid: str) -> int:
        return next(c["returncode"] for c in inst()["commands"] if c["id"] == cid)

    def kinds() -> set[str]:
        return {v["kind"] for v in env()["clone"]["pre_install_audit"]["violations"]}

    def proj() -> dict[str, Any]:
        return demo()["semantic_projection"]

    def demo_complete() -> bool:
        d = demo()
        names = [s["step"] for s in d["browser"]["steps"]]
        return (d["status"] == "PASS" and d["driver_exit"] == 0 and not d["browser"]["console_errors"] and set(STEP_NAMES) <= set(names) and step(d, "monitoring")["finalState"] == "COMPLETED"
                and step(d, "federation")["final"]["status"].startswith("COMPLETED") and d["stopped"]["launcher_exit_code"] == 0 and d["workspace_outside_repository"] is True)

    def fed() -> dict[str, Any]:
        return proj()["federation"]

    def cand() -> dict[str, Any]:
        return proj()["candidates"][0]

    def restart() -> bool:
        d = clone(x, "restart")
        return (d["status"] == "PASS" and d["same_workspace"] is True and d["semantic_identical"] and d["counts_unchanged"] and d["no_new_federation_run"] and d["no_new_candidate"] and not d["monitoring_rerun"]
                and not d["fl_rerun"] and all(d["byte_equal_payloads"].values()) and d["research_catalog_file_unchanged"] is True and d["stopped"]["launcher_exit_code"] == 0 and not d["console_errors"] and d["network"]["external"] == []
                and d["released_default"] == "MODEL_V2_FINAL")

    def targeted_ok() -> bool:
        t = tests()["targeted"]
        return t["returncode"] == 0 and t["counts"].get("failed", 0) == 0 and t["counts"].get("passed", 0) > 0

    return {
        "from_remote": lambda: env()["clone"]["clone_source"].startswith("remote") and not env()["clone"]["alternates_present"] and env()["clone"]["git_dir_is_directory"] and not env()["clone"]["worktree_used"] and not env()["clone"]["clone_inside_development_checkout"] and env()["clone"]["target_reachable_from_remote_main"],
        "exact_sha": lambda: verify_checkout(env()["clone"]["checkout_sha"], target())["ok"] and env()["clone"]["checkout_matches_target"],
        "no_manual_copy": lambda: env()["clone"]["pre_install_audit"]["ok"] and env()["clone"]["tree_clean_after_checkout"] and env()["clone"]["ignored_paths_after_checkout"] == [] and env()["clone"]["manual_copies"] is False and env()["clone"]["harness_matches_clone"],
        "fresh_python": lambda: env()["venv"]["created_by_this_run"] and env()["venv"]["python_executable_inside_clone_venv"] and not env()["venv"]["development_venv_used"] and rc("venv") == 0 and rc("pip_dev") == 0 and rc("pip_auth") == 0 and env()["python"].startswith("Python 3.11") and "copied_python_environment" not in kinds(),
        "clean_npm": lambda: rc("npm_app") == 0 and inst()["frontend_installed_from_committed_lock"] and not fe()["development_node_modules_reused"] and "copied_node_modules" not in kinds() and inst()["lock_sha256"]["frontend/package-lock.json"] == json.loads((ROOT / MANIFEST_PATH).read_text())["dependency_locks"]["frontend/package-lock.json"],
        "clean_clerk": lambda: rc("npm_clerk") == 0 and inst()["clerk_sdk_installed_from_committed_lock"] and inst()["lock_sha256"]["frontend/clerk-sdk/package-lock.json"] == json.loads((ROOT / MANIFEST_PATH).read_text())["dependency_locks"]["frontend/clerk-sdk/package-lock.json"],
        "no_dotenv": lambda: inst()["dotenv_present_in_clone"] is False and "developer_dotenv" not in kinds(),
        "no_dev_venv": lambda: "copied_python_environment" not in kinds() and not env()["venv"]["development_venv_used"],
        "no_dev_node_modules": lambda: "copied_node_modules" not in kinds() and not fe()["development_node_modules_reused"],
        "no_dev_build": lambda: "copied_frontend_build" not in kinds() and not fe()["development_build_reused"] and fe()["frontend_build_produced_by_clean_install"],
        "no_dev_sqlite": lambda: "copied_runtime_state" not in kinds() and gitau()["runtime_artifacts_leaked_into_repository"] == [] and demo()["development_artifacts_required"] is False,
        "no_dev_candidate": lambda: "copied_candidate_artifact" not in kinds() and demo()["development_artifacts_required"] is False,
        "no_raw_data": lambda: "copied_raw_data" not in kinds() and demo()["raw_biomedical_data_required"] is False and gitau()["raw_biomedical_files_present"] == [] and tests()["raw_biomedical_data_present"] is False,
        "verifier": lambda: tests()["release_verifier"]["returncode"] == 0 and tests()["release_verifier"]["result"]["status"] == "PASS",
        "lineage": lambda: tests()["prior_lineage_verified"] is True,
        "targeted": targeted_ok,
        "regression": lambda: tests()["status"] == "PASS" and tests()["regression"]["returncode"] == 0 and tests()["regression"]["counts"].get("failed", 0) == 0 and tests()["regression"]["counts"].get("errors", 0) == 0 and tests()["regression"]["counts"].get("passed", 0) > 1000,
        "unexpected_skips": lambda: tests()["regression"]["skip_categories"]["UNEXPECTED"] == 0 and tests()["regression"]["unexpected_skips"] == [],
        "cap003": lambda: tests()["cap003_race"]["status"] == "PASS" and any(a["passed"] for a in tests()["cap003_race"]["attempts"]) and all(a["passed"] or a["known_signature"] for a in tests()["cap003_race"]["attempts"]),
        "pip_check": lambda: tests()["pip_check_returncode"] == 0 and rc("pip_check") == 0,
        "npm_test": lambda: fe()["npm_test_returncode"] == 0 and (fe()["vitest_tests_passed"] or 0) > 0,
        "svelte": lambda: fe()["svelte_check_returncode"] == 0 and fe()["svelte_check_errors"] == 0,
        "build": lambda: fe()["build_returncode"] == 0 and fe()["frontend_build_produced_by_clean_install"],
        "preflight": lambda: preflight_ok(demo()["preflight"]),
        "demo_complete": demo_complete,
        "model": lambda: proj()["runtime"]["model_id"] == "MODEL_V2_FINAL" and proj()["runtime"]["software_system"] == "SOFTWARE_SYSTEM_V2" and step(demo(), "monitoring")["models"] == ["MODEL_V2_FINAL"],
        "cal": lambda: proj()["runtime"]["calibration_id"] == "CAL_V2" and step(demo(), "monitoring")["calibrations"][0].startswith("CAL_V2"),
        "history": lambda: (h := step(demo(), "history"))["summaryStatus"] == 200 and h["timelineStatus"] == 200 and h["previews"] >= 1 and h["previewIsBounded"] and h["listed"],
        "clients8": lambda: len(fed()["config"]["client_ids"]) == 8,
        "rounds3": lambda: fed()["config"]["planned_rounds"] == 3 and len(fed()["rounds"]) == 3 and all(r["state"] == "COMPLETED" for r in fed()["rounds"]),
        "updates24": lambda: sum(r["accepted_update_count"] for r in fed()["rounds"]) == 24 and step(demo(), "federation")["final"]["updates"] == "24" and fed()["config"]["run_type"] == "LIVE_RUN" and fed()["config"]["algorithm"] == "FEDAVG",
        "plain": lambda: step(demo(), "federation")["aggregationSeen"] == ["PLAIN"],
        "secagg": lambda: fed()["secagg"] == "PASS" and step(demo(), "federation")["shadowVerifiedSeen"] and fed()["config"]["secagg_mode"] == "SECAGG_SHADOW",
        "one_candidate": lambda: len(proj()["candidates"]) == 1 and demo()["post_run_snapshot"]["db_counts"]["candidate_models"] == 1,
        "candidate_sandbox": lambda: cand()["validation_status"] == "PASSED" and cand()["governance_status"] == "ACCEPTED_TO_SANDBOX" and cand()["sandbox_status"] == "IN_SANDBOX" and cand()["parent_model_id"] == "FL_INIT_V2",
        "not_deployed": lambda: cand()["production_deployed"] is False and step(demo(), "models")["productionDeployed"] == ["FALSE"],
        "default": lambda: proj()["released"] == "MODEL_V2_FINAL" and step(demo(), "models")["controls"] == [] and "RELEASED_DEFAULT" in step(demo(), "models")["released"],
        "catalog": lambda: all(step(demo(), "research-ml")[k] for k in ("calibrationCaveat", "promotion", "provenance", "softwareRelease")) and all(step(demo(), "research-fl")[k] for k in ("engineeringSeparate", "fedproxCaveat", "phases", "provenance", "secaggCaveat"))
        and step(demo(), "research-ml")["status"] == 200 and step(demo(), "research-fl")["status"] == 200 and proj()["research"]["catalog_file_sha256"] == sha256_file(ROOT / "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json"),
        "hardware": lambda: (s := step(demo(), "system"))["hardwareMode"] == "SIMULATED_ONLY" and s["physicalHardwareAvailable"] is False and s["pageShowsSimulatedOnly"] and step(demo(), "about")["noPhysicalWearable"],
        "offline": lambda: demo()["browser"]["network"]["external"] == [] and demo()["browser"]["network"]["blockedExternal"] == [] and demo()["browser"]["network"]["origins"] == ["http://127.0.0.1:4173"],
        "clerk_off": lambda: (s := step(demo(), "sign-in"))["clerkGlobal"] is False and s["notClerk"] is True,
        "restart": restart,
        "tracked_unchanged": lambda: gitau()["tracked_modified_or_deleted"] == [] and gitau()["head_unchanged"] is True,
        "no_leak": lambda: gitau()["runtime_artifacts_leaked_into_repository"] == [] and gitau()["raw_biomedical_files_present"] == [] and demo()["workspace_outside_repository"] is True,
        "no_secret": lambda: demo()["stopped"]["secret_scan"]["clean"] is True,
        "no_orphan": lambda: demo()["stopped"]["child_pids_still_alive"] == [] and demo()["stopped"]["launcher_reported_orphans"] == [],
        "distinct": lambda: True,
    }


def tests_title_ok(title: str) -> bool:
    names = clone("a", "tests")["targeted"]["tests"]
    hit = [v for k, v in names.items() if k.split("::")[-1] == title or k.split("::")[-1].startswith(title + "[")]
    return bool(hit) and all(v == "PASSED" for v in hit)


def preflight_ok(p: dict[str, Any]) -> bool:
    parsed = p["parsed"].get("preflight", {})
    return p["returncode"] == 0 and bool(parsed) and all(v is True for v in parsed.values())


def build_checks() -> dict[str, Callable[[], bool]]:
    c: dict[str, Callable[[], bool]] = {}
    for n in range(1, 11):
        c[f"cap_pass_{n}"] = (lambda n=n: statuses()[0].get(f"CAP-{n:03d}") == "PASS" and statuses()[1].get(f"CAPG{n - 1}") == "PASS")
    for x in ("a", "b"):
        for name, fn in clone_checks(x).items():
            c[f"{x}_{name}"] = fn
    manifest = lambda: json.loads((ROOT / MANIFEST_PATH).read_text())  # noqa: E731
    policy = lambda: json.loads(POLICY.read_text())  # noqa: E731
    decision = lambda: rd("release_decision.json")  # noqa: E731
    dev = lambda: rd("dev_test_report.json")  # noqa: E731
    text = lambda: GUIDE.read_text(encoding="utf-8")  # noqa: E731
    final_audit = lambda: rd("protected_artifact_final.json")  # noqa: E731
    deps = ("pyproject.toml", "requirements-dev.lock", "requirements-capstone-auth.lock")
    npm = ("frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json")
    scan_exts = (".py", ".mjs", ".js", ".ts", ".svelte")
    c.update({
        "locks_verified": lambda: subprocess.run([sys.executable, "-m", "scripts.verify_capstone_release_v1"], cwd=ROOT, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": "src:."}).returncode == 0,
        "entry_audit_immutable": lambda: git("diff", git("log", "--diff-filter=A", "--format=%H", "--", "reports/capstone/cap_011/entry_audit.json").splitlines()[-1], "--", "reports/capstone/cap_011/entry_audit.json") == "",
        "historical_untouched": lambda: final_audit()["historical_release_lineage_unchanged"] is True,
        "protected_final_clean": lambda: final_audit()["protected_artifact_drift"] is False,
        "no_sci_drift": lambda: not drift("checkpoints", "reports/model_v2", "src", "simulation", "privacy", "contracts", ":(glob)artifacts/*.json"),
        "no_runtime_drift": lambda: not drift("artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/ROLLBACK_RUNTIME_BINDING_V1.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "api", "src"),
        "no_fl_drift": lambda: not drift("federated", "reports/model_v2", "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "artifacts/FEDPROX_MU_V2.lock.json", "product/federation", "product/models"),
        "no_frontend_drift": lambda: not drift("frontend", "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json"),
        "no_backend_drift": lambda: not drift("api", "product", "capstone_persistence"),
        "no_cap010_drift": lambda: not drift("scripts/run_capstone_faculty_demo.py", "scripts/capstone_demo_preflight.py", "scripts/capstone_demo_workspace.py", "scripts/run_capstone_full_demo_e2e.py", "scripts/cap_010_cdp_driver.mjs",
                                             "docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md", "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_1.json", "reports/capstone/cap_010"),
        "no_new_functionality": lambda: not drift("api", "product", "capstone_persistence", "federated", "privacy", "simulation", "frontend", "src") and not [p for p in added_since_entry() if p.startswith(("api/", "product/", "capstone_persistence/", "federated/", "privacy/", "simulation/", "frontend/", "src/"))],
        "policy_frozen": lambda: frozen_before_clones("configs/capstone/cap_011_release_policy_v1.json"),
        "override_false": lambda: policy()["manual_override_allowed"] is False and policy()["waivers_allowed"] is False and manifest()["manual_override_allowed"] is False,
        "protocol_frozen": lambda: frozen_before_clones("configs/capstone/cap_011_release_protocol_v1.json"),
        "cc_protocol_frozen": lambda: frozen_before_clones("configs/capstone/cap_011_clean_clone_protocol_v1.json"),
        "manifest_frozen": lambda: frozen_before_clones(MANIFEST_PATH),
        "verifier_frozen": lambda: frozen_before_clones("scripts/verify_capstone_release_v1.py") and frozen_before_clones("scripts/capstone_release_lib.py"),
        "harness_frozen": lambda: frozen_before_clones("scripts/run_capstone_clean_release.py"),
        "criteria_frozen": lambda: frozen_before_clones("scripts/cap_011_evaluate_gate.py") and frozen_before_clones("configs/capstone/cap_011_release_protocol_v1.json"),
        "target_clean": lambda: rd("release_target.json")["working_tree_clean"] is True and rd("release_target.json")["local_head"] == target(),
        "target_pushed": lambda: rd("release_target.json")["pushed"] is True and rd("release_target.json")["origin_main"] == target(),
        "target_equals_clone_origin": lambda: all(clone(x, "environment")["clone"]["remote_main_sha_at_clone"] == target() for x in ("a", "b")),
        "b_distinct": lambda: clone("a", "environment")["clone_root_id"] != clone("b", "environment")["clone_root_id"],
        "no_rescue": lambda: all(clone(x, "install")["manual_rescue_install"] is False and clone(x, "install")["manual_npm_install"] is False and clone(x, "git_audit")["manual_dependency_rescue"] is False for x in ("a", "b"))
        and not [p for p in EVD.glob("attempt_*_FAIL_*.json") if json.loads(p.read_text()).get("contaminated") and not json.loads(p.read_text()).get("discarded")],
        "no_manual_copy_both": lambda: all(clone(x, "environment")["clone"]["manual_copies"] is False and clone(x, "environment")["clone"]["pre_install_audit"]["ok"] for x in ("a", "b")),
        "no_raw_execution": lambda: all(clone(x, "tests")["raw_biomedical_data_present"] is False and clone(x, "git_audit")["raw_biomedical_files_present"] == [] for x in ("a", "b")),
        "no_heldout": lambda: not any(re.search(r"heldout|held_out|internal_test|incart|external", " ".join(cmd["argv"] or []), re.I) for cmd in json.loads(CLEAN.read_text())["commands"] if cmd["argv"]),
        "no_retrain": lambda: not any(re.search(r"train|calibrat|fit_", " ".join(cmd["argv"] or []), re.I) for cmd in json.loads(CLEAN.read_text())["commands"] if cmd["argv"]) and all(clone(x, "demo")["prewarm"]["training_calls"] == 0 for x in ("a", "b")),
        "no_candidate_eval": lambda: all(not set(k.lower() for k in clone(x, "demo")["semantic_projection"]["candidates"][0]) & {"auc", "metric", "metrics", "f1", "evaluation"} for x in ("a", "b")),
        "ab_identical": lambda: clone("a", "demo")["semantic_sha256"] == clone("b", "demo")["semantic_sha256"] and clone("a", "demo")["semantic_projection"] == clone("b", "demo")["semantic_projection"] and rd("clean_clone_reproducibility.json")["identical"] is True
        and rd("clean_clone_reproducibility.json")["clone_a_semantic_sha256"] == clone("a", "demo")["semantic_sha256"] and rd("clean_clone_reproducibility.json")["clone_b_semantic_sha256"] == clone("b", "demo")["semantic_sha256"],
        "guide_commands_tested": lambda: guide_cmds_tested(),
        "guide_network": lambda: "Initial dependency installation may require Internet access" in text() and "requires only loopback networking" in text() and "air-gapped installation is claimed" in text(),
        "guide_scope": lambda: "does not claim full raw-data retraining/evaluation from a clean clone" in text() and "No raw biomedical dataset download is required" in text() and "software, artifact and product-demonstration reproducibility only" in text(),
        "guide_claims": lambda: audit_release_text(text())["ok"],
        "manifest_hashes": lambda: all((ROOT / p).is_file() and sha256_file(ROOT / p) == h for g in ("key_artifacts", "dependency_locks") for p, h in manifest()[g].items()),
        "limitations_complete": lambda: all(x["text"] in text() and x["text"] in manifest()["limitations"] for x in policy()["limitations"]) and len(policy()["limitations"]) == 21,
        "env_inventory": lambda: all(all(clone(x, "environment").get(k) for k in ("python", "pip", "node", "npm", "git", "browser", "platform", "architecture")) and clone(x, "environment")["lock_sha256"] == {k: v for k, v in manifest()["dependency_locks"].items()} for x in ("a", "b")),
        "tested_platform": lambda: all(clone(x, "environment")["system"] == "Darwin" for x in ("a", "b")) and "Tested platform: macOS (Darwin) on arm64" in text(),
        "no_xplat_claim": lambda: audit_release_text(text())["ok"] and "Other operating systems are not verified" in text(),
        "no_new_py_dep": lambda: not git("diff", "--name-only", ENTRY, "--", *deps).strip(),
        "no_new_npm_dep": lambda: not git("diff", "--name-only", ENTRY, "--", *npm).strip(),
        "no_large_artifacts": lambda: not [p for p in (EVD.rglob("*")) if p.is_file() and (p.stat().st_size > 2_000_000 or p.suffix in {".db", ".sqlite", ".sqlite3", ".pt", ".npz", ".npy", ".whl"})],
        "no_archive": lambda: not [p for p in added_since_entry() if re.search(r"\.(zip|tar|tgz|gz|bz2|xz|7z)$", p)],
        "decision_accept": lambda: decision()["decision"] == "ACCEPT" and decision()["release_id"] == "CAPSTONE_RELEASE_V1" and decision()["release_target_sha"] == target() and decision()["policy"] == "CAPSTONE_RELEASE_POLICY_V1"
        and decision()["clean_clone_a"] == "PASS" and decision()["clean_clone_b"] == "PASS" and "scientific_promotion" not in decision(),
        "decision_override_false": lambda: decision()["manual_override"] is False,
        "final_evidence_only": lambda: verify_final_diff(ROOT, target())["ok"],
        "final_diff_ok": lambda: verify_final_diff(ROOT, target())["ok"],
        "claim_exact": lambda: manifest()["release_claim"] == policy()["release_claim"] == json.loads(CONFIG.read_text())["release_claim"] and (not (EVD / "release_decision.json").exists() or decision()["release_claim"] == policy()["release_claim"]),
        "promotion_preserved": lambda: policy()["decision_separation"]["MODEL_V2_NOT_PROMOTED_RELEASE_CI"] == "preserved" and not drift("artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json", "artifacts/MODEL_V2_COMPLETE_REPRO_V1.lock.json") and "MODEL_V2_NOT_PROMOTED_RELEASE_CI" in text(),
        "system_release_preserved": lambda: policy()["decision_separation"]["SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED"] == "preserved" and "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED" in text(),
        "candidate_not_deployed_all": lambda: manifest()["candidate"]["production_deployed"] is False and manifest()["released_monitoring"]["candidate_used_for_monitoring"] is False and all(clone(x, "demo")["semantic_projection"]["candidates"][0]["production_deployed"] is False for x in ("a", "b"))
        and (not (EVD / "release_decision.json").exists() or decision()["candidate_deployed"] is False),
        "no_personal_model": lambda: "No personal model is trained" in text() and not [p for p in added_since_entry() if re.search(r"personal_model|personali[sz]", p, re.I)],
        "no_hardware": lambda: manifest()["hardware"]["physical_hardware_available"] is False and not [p for p in added_since_entry() if re.search(r"ble_|bluetooth|serial_port|firmware", p, re.I)],
        "no_candidate_runtime": lambda: manifest()["released_monitoring"]["candidate_inference"] is False and not [p for p in added_since_entry() if re.search(r"sandbox_runtime|candidate_inference", p, re.I)],
        "no_new_local_batch": lambda: not [p for p in added_since_entry() if p.endswith(scan_exts) and p.startswith(("scripts/", "tests/")) and "cap_011_evaluate_gate" not in p and "FL_NEW_LOCAL_BATCH" in (ROOT / p).read_text(errors="ignore") and "mutation" not in p],
        "no_multirun": lambda: not [p for p in added_since_entry() if p.endswith(scan_exts) and p.startswith(("scripts/", "tests/")) and "cap_011_evaluate_gate" not in p and "FL_MULTIRUN" in (ROOT / p).read_text(errors="ignore") and "mutation" not in p],
        "dev_targeted": lambda: dev()["targeted"]["returncode"] == 0,
        "dev_regression": lambda: dev()["full_regression"]["returncode"] == 0 and not dev()["full_regression"]["failed"] and dev()["inherited_flake"]["status"] == "PASS_INHERITED_FLAKE_POLICY",
        "dev_ruff": lambda: dev()["commands"]["ruff"]["returncode"] == 0,
        "dev_pip": lambda: dev()["commands"]["pip_check"]["returncode"] == 0,
        "ci_not_queried": lambda: dev()["ci_queried"] is False and clone("a", "tests")["ci_queried"] is False and clone("b", "tests")["ci_queried"] is False,
        "ci_not_triggered": lambda: dev()["ci_triggered"] is False and not [p for p in git("ls-files", "scripts/cap_011_*", "scripts/run_capstone_clean_release.py", "scripts/capstone_release_*", "scripts/verify_capstone_release_v1.py").split() if re.search(r"\"gh\"|'gh'|api\.github|actions/runs", (ROOT / p).read_text()) and "evaluate_gate" not in p],
        "cap011_pass": lambda: statuses()[0].get("CAP-011") == "PASS",
        "capg10_pass": lambda: statuses()[1].get("CAPG10") == "PASS",
        "all_tasks_pass": lambda: set(statuses()[0]) == {f"CAP-{i:03d}" for i in range(1, 12)} and all(v == "PASS" for v in statuses()[0].values()),
        "all_gates_pass": lambda: set(statuses()[1]) == {f"CAPG{i}" for i in range(11)} and all(v == "PASS" for v in statuses()[1].values()),
        "no_cap012": lambda: "CAP-012" not in statuses()[0] and not [p for p in git("ls-files").split() + git("ls-files", "--others", "--exclude-standard").split() if re.search(r"cap_012|CAP-012", p)],
        "portability": lambda: portability_audit(ROOT)["ok"],
        "case_audit": lambda: case_audit(ROOT)["ok"],
        "harness_static_audit": lambda: harness_static_ok(),
        "mutation_log": lambda: (m := rd("mutation_controls.json"))["all_caught"] and m["all_restored"] and [x["mutation"] for x in m["controls"]] == json.loads(CONFIG.read_text())["mutation_controls"] and len(m["controls"]) == 20,
    })
    return c


def guide_cmds_tested() -> bool:
    proto = json.loads(CLEAN.read_text())
    displays = {cmd["id"]: cmd["display"] for cmd in proto["commands"]}
    gcmds = set(guide_commands(GUIDE.read_text(encoding="utf-8")))
    if not set(displays.values()) <= gcmds:
        return False
    for x in ("a", "b"):
        ran = {e["id"]: e for e in exec_ids(x)}
        for cmd in proto["commands"]:
            if cmd["argv"] is None:
                continue
            key = cmd["id"] if cmd["id"] in ran else (f"{cmd['id']}_1" if f"{cmd['id']}_1" in ran else None)
            if key is None or ([a.replace("<ROOT>", "") for a in ran[key]["argv"]] != cmd["argv"] and cmd["id"] not in ("demo",)):
                return False
            if cmd["id"] != "cap003_isolated" and ran[key]["returncode"] != 0:
                return False
        launch = clone(x, "demo")["launcher_command"] or ""
        if not all(flag in launch for flag in ("--acknowledge-demo-auth", "--build", "--prewarm-federation", "--workspace")):
            return False
    return True


def harness_static_ok() -> bool:
    body = (ROOT / "scripts/run_capstone_clean_release.py").read_text()
    code = re.sub(r'""".*?"""', "", body, flags=re.S)
    code = "\n".join(ln for ln in code.splitlines() if not ln.strip().startswith("#"))
    forbidden = (r"shutil\.copy", r"shutil\.move", r"copytree", r"\"cp\"", r"\"rsync\"", r"os\.symlink", r"--force", r"pip.{0,12}install.{0,40}--no-deps", r"git.{0,12}worktree", r"\"--reference\"", r"\"--shared\"", r"\"--local\"")
    return not [pat for pat in forbidden if re.search(pat, code)]


def evaluate() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    frozen = config["capg10_criteria"]
    if len(frozen) != 136 or [r["id"] for r in frozen] != [f"CAPG10-{i:03d}" for i in range(1, 137)]:
        raise RuntimeError("CAPG10_FROZEN_CRITERIA_CHANGED")
    # protected-artifact final audit (release-layer allow-list) before the checks that consume it
    from scripts.cap_011_protected_audit import final as protected_final

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
                except Exception as error:  # a failed check, never a crash
                    cache[name] = (False, f"{type(error).__name__}:{str(error)[:160]}")
        return cache[name]

    rows = []
    for row in frozen:
        results = []
        for chk in row["checks"]:
            if chk.startswith("T:"):
                try:
                    results.append((chk, tests_title_ok(chk[2:]), ""))
                except Exception as error:
                    results.append((chk, False, f"{type(error).__name__}:{str(error)[:160]}"))
            else:
                ok, why = run_check(chk)
                results.append((chk, ok, why))
        rows.append({"id": row["id"], "text": row["text"], "blockers": row["blockers"], "pass": all(r[1] for r in results),
                     "checks": [{"check": c_, "pass": ok, **({"note": why} if why else {})} for c_, ok, why in results]})
    policy = json.loads(POLICY.read_text())
    blockers = []
    for b in policy["hard_blockers"]:
        members = [r for r in rows if b["id"] in r["blockers"]]
        blockers.append({"id": b["id"], "text": b["text"], "criteria": len(members), "pass": bool(members) and all(r["pass"] for r in members)})
    return {"gate": "CAPG10", "mode": "PRE_DECISION" if PRE else "FINAL", "criteria_count": len(rows), "all_decided_pass": all(r["pass"] for r in rows), "failed": [r["id"] for r in rows if not r["pass"]],
            "hard_blockers": blockers, "all_hard_blockers_pass": all(b["pass"] for b in blockers), "manual_override": False, "criteria": rows}


def write_decision(result: dict[str, Any]) -> None:
    policy = json.loads(POLICY.read_text())
    manifest = json.loads((ROOT / MANIFEST_PATH).read_text())
    ea, eb = clone("a", "environment"), clone("b", "environment")
    decision = {
        "decision_id": "CAPSTONE_RELEASE_DECISION_V1", "release_id": "CAPSTONE_RELEASE_V1", "release_target_sha": target(), "policy": "CAPSTONE_RELEASE_POLICY_V1", "decision": "ACCEPT",
        "manual_override": False, "clean_clone_a": "PASS", "clean_clone_b": "PASS", "hard_blockers_evaluated": len(result["hard_blockers"]), "hard_blockers_passed": sum(b["pass"] for b in result["hard_blockers"]),
        "release_scope": manifest["release_scope"], "release_claim": policy["release_claim"], "release_claim_excludes": policy["release_claim_excludes"], "clean_clone_claim": policy["clean_clone_claim"],
        "installation_claim": policy["installation_vs_runtime"]["installation"], "runtime_offline_claim": policy["installation_vs_runtime"]["runtime"],
        "tested_platform": {"clone_a": {"platform": ea["platform"], "architecture": ea["architecture"], "python": ea["python"], "node": ea["node"], "npm": ea["npm"], "browser": ea["browser"]},
                            "clone_b": {"platform": eb["platform"], "architecture": eb["architecture"], "python": eb["python"], "node": eb["node"], "npm": eb["npm"], "browser": eb["browser"]}},
        "candidate_deployed": False, "released_default_model": "MODEL_V2_FINAL", "decision_separation": policy["decision_separation"], "limitations": [x["text"] for x in policy["limitations"]],
        "note": "This decision is about the software/demo package only. It does not promote any model and does not alter MODEL_V2_NOT_PROMOTED_RELEASE_CI or SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED.",
    }
    (EVD / "release_decision.json").write_text(json.dumps(decision, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    result = evaluate()
    name = "capg10_pre_decision.json" if PRE else "capg10_criteria.json"
    (EVD / name).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"mode": result["mode"], "all_decided_pass": result["all_decided_pass"], "failed": result["failed"], "all_hard_blockers_pass": result["all_hard_blockers_pass"]}))
    if PRE and WRITE_DECISION:
        if result["all_decided_pass"] and result["all_hard_blockers_pass"]:
            write_decision(result)
            print("release_decision.json written: ACCEPT")
        else:
            print("NO DECISION WRITTEN: a hard blocker failed (no manual override exists)")
            return 1
    return 0 if result["all_decided_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
