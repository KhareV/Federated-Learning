# ruff: noqa: E501
"""Evidence-backed CAPG9 adjudication of the 104 prospectively frozen criteria.
``--pre-transition`` defers only the registry-transition, handoff and disclosure checks (the result commit
transitions the registries and writes the handoff); the strict run (no flag) must pass before the result commit."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.cap_008_protected_audit import all_locks
from scripts.verify_capstone_faculty_demo import verify as verify_protocol

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_010"
CONFIG = ROOT / "configs/capstone/cap_010_faculty_demo_protocol_v1.json"
ENTRY = "be778d4ced186639155064e94516ff096751a81f"
PRE = "--pre-transition" in sys.argv
SECTIONS = ["PHASE RESULT", "ENTRY", "UPSTREAM PROTECTION", "PROTOCOL", "DEMO LAUNCHER", "WORKSPACE", "PREFLIGHT", "SERVICE SUPERVISION", "PREWARM", "RUNBOOK", "FULL DEMO SCENARIO COVERAGE",
            "CANONICAL FULL DEMO RUN 1", "CANONICAL FULL DEMO RUN 2", "REPRODUCIBILITY", "MONITORING", "FEDERATION", "RESEARCH", "RESTART / RESUME", "OFFLINE", "RELEASED DEFAULT ISOLATION",
            "OUT OF SCOPE", "TESTS", "CONTROL PLANE", "GIT", "DISCLOSURES", "FINAL DECISION"]


def rd(name: str) -> dict[str, Any]:
    return json.loads((OUT / name).read_text())


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def drift(*paths: str) -> list[str]:
    return git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *paths).split()


def registry(name: str, key: str) -> dict[str, dict[str, str]]:
    with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        return {r[key]: r for r in csv.DictReader(h)}


def step(run: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in run["browser"]["steps"] if s["step"] == name)


def runs() -> tuple[dict[str, Any], dict[str, Any]]:
    return rd("full_browser_demo_run_1.json"), rd("full_browser_demo_run_2.json")


def run_ok(run: dict[str, Any]) -> bool:
    names = [s["step"] for s in run["browser"]["steps"]]
    stop = run["stopped"]
    return (run["driver_exit"] == 0 and not run["browser"]["console_errors"] and stop["launcher_exit_code"] == 0 and not stop["child_pids_still_alive"]
            and {"sign-in", "overview", "device", "monitoring", "history", "federation", "models", "research-ml", "research-fl", "system", "about"} <= set(names)
            and step(run, "monitoring")["finalState"] == "COMPLETED" and step(run, "federation")["final"]["status"].startswith("COMPLETED") and run["workspace_outside_repository"] is True)


def both(fn: Callable[[dict[str, Any]], bool]) -> bool:
    return all(fn(r) for r in runs())


def junit_names() -> dict[str, str]:
    return {k: v for k, v in rd("test_report.json")["targeted"]["tests"].items()}


def test_ok(prefix: str) -> bool:
    title = prefix[2:]
    wanted = "test_capstone_full_demo" if prefix[0] == "T" else None
    def named(k: str) -> bool:
        return k.split("::")[-1] == title or k.split("::")[-1].startswith(title + "[")

    hits = [v for k, v in junit_names().items() if named(k) and (wanted is None or wanted in k) and (wanted or "test_capstone_full_demo" not in k)]
    if not hits:   # the frozen criteria text mislabels one title's file prefix; the title itself is unique across the CAP-010 files
        hits = [v for k, v in junit_names().items() if named(k)]
    return bool(hits) and all(v == "passed" for v in hits)


def status_file(name: str) -> bool:
    return rd(name).get("status") == "PASS"


def commit_of_lock() -> str:
    return git("log", "--diff-filter=A", "--format=%H", "--", "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json").splitlines()[-1]


def freeze_precedes() -> bool:
    freeze = commit_of_lock()
    for name in ("full_browser_demo_run_1.json", "full_browser_demo_run_2.json", "full_demo_scenario_coverage.json", "demo_restart.json"):
        first = git("log", "--diff-filter=A", "--format=%H", "--", f"reports/capstone/cap_010/{name}").splitlines()
        if first and subprocess.run(["git", "merge-base", "--is-ancestor", freeze, first[-1]], cwd=ROOT).returncode != 0:
            return False
    return True


def amendment_hygiene() -> bool:
    freeze = commit_of_lock()
    for commit in git("rev-list", f"{freeze}..HEAD").split():
        subject = git("log", "-1", "--format=%s", commit)
        files = git("show", "--name-only", "--format=", commit).split()
        if subject.startswith("result(cap-010)"):
            continue
        if not subject.startswith("amend(cap-010)") or any(f.startswith("reports/capstone/cap_010/") for f in files):
            return False
    return True


def no_large() -> bool:
    bad = []
    for p in (OUT).rglob("*"):
        if p.is_file() and (p.stat().st_size > 2_000_000 or p.suffix in {".db", ".sqlite", ".sqlite3", ".pt", ".npz", ".npy"}):
            bad.append(str(p))
    return not bad


def cap011_absent() -> bool:
    names = git("ls-files").split() + git("ls-files", "--others", "--exclude-standard").split()
    return not any(re.search(r"cap_011|CAP-011|CAP011", n) for n in names)


def gate_pass(n: int) -> bool:
    task = registry("task", "task_id")[f"CAP-{n:03d}"]["status"]
    gate = registry("gate", "gate_id")[f"CAPG{n - 1}"]["status"]
    return task == "PASS" and gate == "PASS"


def registry_state(task_or_gate: str, which: str, final: str) -> bool:
    row = registry("task" if which == "task" else "gate", "task_id" if which == "task" else "gate_id")[task_or_gate]
    if row["status"] == final:
        return True
    return PRE and row["status"] in ({"IN_PROGRESS"} if which == "task" else {"NOT_STARTED", "IN_PROGRESS"})


def handoff_sections() -> bool:
    path = OUT / "final_handoff.md"
    if not path.exists():
        return PRE
    text = path.read_text()
    found = re.findall(r"^#{1,3} \**(?:\d+\.\s+)?([A-Z][A-Z0-9 /]+?)\**\s*$", text, re.M)
    names = [f.strip() for f in found]
    positions = [names.index(s) for s in SECTIONS if s in names]
    return all(s in names for s in SECTIONS) and positions == sorted(positions)


def disclosures_preserved() -> bool:
    path = OUT / "final_handoff.md"
    if not path.exists():
        return PRE
    text = path.read_text().lower()
    markers = ["accelerated", "logical", "round-1", "not deployed", "physical wearable", "clerk", "cap-003", "machine-specific", "85fe0b3", "distributed lock", "no inference runtime", "advisor", "2022329", "dry run"]
    return all(m in text for m in markers)


def readiness_clean(readiness: Path) -> bool:
    text = readiness.read_text()
    return len(text) < 20_000 and not re.search(r"sk_live|sk_test|Bearer |BEGIN [A-Z ]*PRIVATE KEY|\"waveform\"|\"weights\"|\"training_examples\"|\"state_dict\"", text)


def no_deps() -> bool:
    return not git("diff", "--name-only", ENTRY, "--", "pyproject.toml", "requirements-dev.lock", "frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json").strip()


def coverage(name: str) -> bool:
    full = rd("full_demo_scenario_coverage.json")
    raw = rd("scenario_coverage.json")["scenarios"][name]
    return full["coverage"][name]["status"] == "PASS" and raw["pass"] is True and all(raw.get("invariants", {"x": True}).values())


def build_checks() -> dict[str, Callable[[], bool]]:
    c: dict[str, Callable[[], bool]] = {}
    for n in range(1, 10):
        c[f"cap_pass_{n}"] = (lambda n=n: gate_pass(n))
    sem = lambda: rd("full_browser_demo_run_1.json")["semantic_projection"]  # noqa: E731
    tr = lambda: rd("test_report.json")  # noqa: E731
    cmd = lambda name: tr()["commands"][name]["returncode"] == 0  # noqa: E731
    for name in ("NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT", "FL_SINGLE_RUN", "FL_SECAGG_SHADOW"):
        c[f"coverage_{name}"] = (lambda name=name: coverage(name))
    c.update({
        "locks_verified": lambda: all(v["verified"] for v in all_locks().values()) and verify_protocol()["status"] == "PASS",
        "entry_audit_immutable": lambda: git("diff", "a7bd1a7", "--", "reports/capstone/cap_010/entry_audit.json") == "",
        "no_scientific_drift": lambda: not drift("checkpoints", "reports/model_v2", "src", "simulation", "privacy", "contracts", ":(glob)artifacts/*.json"),
        "released_runtime_zero_drift": lambda: not drift("artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "api/inference_app.py", "src"),
        "v2fl_zero_drift": lambda: not drift("federated", "reports/model_v2", "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "artifacts/FEDPROX_MU_V2.lock.json"),
        "cap006_007_zero_drift": lambda: not drift("product/edge", "product/federation", "product/models", "capstone_persistence/federation_store.py", "capstone_persistence/store.py"),
        "api_zero_drift": lambda: not drift("api", "capstone_persistence"),
        "ui_zero_drift": lambda: not drift("frontend", "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json"),
        "history_research_zero_drift": lambda: not drift("product/history", "product/research", "capstone_persistence/session_evidence_store.py", "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json"),
        "no_new_deps": no_deps,
        "protocol_freeze_precedes_result": freeze_precedes,
        "binding_audit": lambda: status_file("full_demo_binding_audit.json"),
        "launcher_audit": lambda: status_file("launcher_audit.json"),
        "launcher_negative": lambda: status_file("launcher_negative_tests.json"),
        "workspace_tests": lambda: status_file("workspace_safety_audit.json"),
        "supervision_tests": lambda: status_file("process_supervision_audit.json"),
        "workspace_outside_repo": lambda: both(lambda r: r["workspace_outside_repository"] is True),
        "preflight_audit": lambda: status_file("preflight_audit.json"),
        "preflight_real": lambda: rd("preflight_audit.json")["real_preflight_returncode"] == 0,
        "prewarm_audit": lambda: status_file("prewarm_audit.json") and both(lambda r: r["prewarm"]["side_effect_free"] and r["prewarm"]["training_calls"] == 0 and r["prewarm"]["federation_runs_created"] == 0 and r["prewarm"]["candidates_created"] == 0 and not r["prewarm"]["released_binding_changed"]),
        "runbook_audit": lambda: status_file("faculty_runbook_audit.json"),
        "launcher_ready_order": lambda: status_file("process_supervision_audit.json"),
        "identity_inference": lambda: sem()["runtime"]["software_system"] == "SOFTWARE_SYSTEM_V2" and sem()["runtime"]["model_id"] == "MODEL_V2_FINAL" and sem()["runtime"]["calibration_id"] == "CAL_V2",
        "identity_product": lambda: sem()["runtime"]["product_api_implementation"] == "CAPSTONE_PRODUCT_API_V1_3" and sem()["runtime"]["auth_provider"] == "DEMO" and sem()["runtime"]["persistence_mode"] == "SQLITE" and sem()["runtime"]["demo_mode"] is True,
        "identity_frontend": lambda: both(lambda r: r["browser"]["network"]["frontendHost"] == "127.0.0.1:4173") and tr()["commands"]["build"]["returncode"] == 0,
        "sigint_shutdown": lambda: both(lambda r: r["stopped"]["launcher_exit_code"] == 0 and r["stopped"]["stopped_in_reverse_order_log"] is True),
        "no_orphans": lambda: both(lambda r: not r["stopped"]["child_pids_still_alive"] and not r["stopped"]["launcher_reported_orphans"]),
        "log_scan_clean": lambda: both(lambda r: r["stopped"]["secret_scan"]["clean"] is True),
        "logs_in_workspace": lambda: both(lambda r: sorted(r["stopped"]["secret_scan"]["logs_scanned"]) == ["frontend.log", "inference.log", "product.log"]),
        "coverage_real": lambda: rd("scenario_coverage.json")["mocks_used"] is False and len(rd("scenario_coverage.json")["real_components"]) == 4 and rd("full_demo_scenario_coverage.json")["scientific_evidence"] is False,
        "no_outcome_tuning": lambda: rd("full_demo_scenario_coverage.json")["outcome_tuning"] is False and rd("full_demo_scenario_coverage.json")["model_outcome_required"] is False and all(s.get("model_outcome_asserted") is False and s.get("outcome_tuned") is False for k, s in rd("scenario_coverage.json")["scenarios"].items() if "model_outcome_asserted" in s),
        "hero_mixed": lambda: both(lambda r: step(r, "device")["scenario"] == "MIXED_MONITORING_SESSION" and step(r, "device")["simulatedVisible"] is True and step(r, "monitoring")["simulationVisible"] is True),
        "hero_complete": lambda: both(lambda r: (m := step(r, "monitoring"))["finalState"] == "COMPLETED" and m["models"] == ["MODEL_V2_FINAL"] and m["calibrations"][0].startswith("CAL_V2") and m["gapSeen"] and "RECONNECTING" in m["deviceStatesSeen"] and m["contextUnavailableSeen"]),
        "history_loads": lambda: both(lambda r: (h := step(r, "history"))["summaryStatus"] == 200 and h["timelineStatus"] == 200 and h["previews"] >= 1 and h["previewIsBounded"] and h["listed"]),
        "history_semantics": lambda: both(lambda r: (h := step(r, "history"))["countBasis"] and h["timeDomains"] and h["probabilityLabel"]),
        "fl_config": lambda: both(lambda r: (k := r["semantic_projection"]["federation"]["config"])["run_type"] == "LIVE_RUN" and k["algorithm"] == "FEDAVG" and k["secagg_mode"] == "SECAGG_SHADOW" and k["status"] == "COMPLETED" and k["base_model_id"] == "FL_INIT_V2"),
        "fl_counts": lambda: both(lambda r: len(r["semantic_projection"]["federation"]["config"]["client_ids"]) == 8 and r["semantic_projection"]["federation"]["config"]["planned_rounds"] == 3
                               and [x["accepted_update_count"] for x in r["semantic_projection"]["federation"]["rounds"]] == [8, 8, 8] and step(r, "federation")["final"]["updates"] == "24" and step(r, "federation")["maxClientsSubmittedAtOnce"] == 8),
        "fl_secagg": lambda: both(lambda r: r["semantic_projection"]["federation"]["secagg"] == "PASS" and step(r, "federation")["aggregationSeen"] == ["PLAIN"] and step(r, "federation")["shadowVerifiedSeen"]),
        "candidate_ok": lambda: both(lambda r: len(r["semantic_projection"]["candidates"]) == 1 and (k := r["semantic_projection"]["candidates"][0])["validation_status"] == "PASSED" and k["governance_status"] == "ACCEPTED_TO_SANDBOX"
                                 and k["sandbox_status"] == "IN_SANDBOX" and k["production_deployed"] is False and k["parent_model_id"] == "FL_INIT_V2" and r["post_run_snapshot"]["db_counts"]["candidate_models"] == 1),
        "released_default": lambda: both(lambda r: r["semantic_projection"]["released"] == "MODEL_V2_FINAL" and rd("demo_restart.json")["released_default"] == "MODEL_V2_FINAL"),
        "models_page": lambda: both(lambda r: (m := step(r, "models"))["controls"] == [] and m["productionDeployed"] == ["FALSE"] and "RELEASED_DEFAULT" in m["released"] and m["acceptedCopy"]),
        "research_ml": lambda: both(lambda r: all(step(r, "research-ml")[k] for k in ("calibrationCaveat", "promotion", "provenance", "softwareRelease")) and step(r, "research-ml")["status"] == 200),
        "research_fl": lambda: both(lambda r: all(step(r, "research-fl")[k] for k in ("engineeringSeparate", "fedproxCaveat", "phases", "provenance", "secaggCaveat")) and step(r, "research-fl")["status"] == 200),
        "no_science": lambda: rd("preflight_audit.json")["status"] == "PASS" and both(lambda r: r["prewarm"]["training_calls"] == 0),
        "hardware_visible": lambda: both(lambda r: (s := step(r, "system"))["physicalHardwareAvailable"] is False and s["pageShowsSimulatedOnly"] and s["pageShowsNoHardware"] and step(r, "about")["noPhysicalWearable"]),
        "browser_real_stack": lambda: both(lambda r: "--acknowledge-demo-auth" in r["launcher_command"] and r["driver_exit"] == 0 and len(r["browser"]["network"]["websockets"]) == 2 and r["semantic_projection"]["runtime"]["software_system"] == "SOFTWARE_SYSTEM_V2"),
        "browser_complete": lambda: both(run_ok),
        "offline_ok": lambda: status_file("offline_network_audit.json") and rd("demo_restart.json")["network"]["external"] == [],
        "clerk_not_initialised": lambda: both(lambda r: (s := step(r, "sign-in"))["clerkGlobal"] is False and s["notClerk"] is True),
        "restart_ok": lambda: (d := rd("demo_restart.json"))["same_workspace"] is True and d["driver_exit"] == 0 and d["stopped"]["launcher_exit_code"] == 0 and not d["console_errors"],
        "restart_preserves": lambda: (d := rd("demo_restart.json"))["semantic_identical"] and d["counts_unchanged"] and d["no_new_federation_run"] and d["no_new_candidate"] and not d["monitoring_rerun"] and not d["fl_rerun"] and all(d["byte_equal_payloads"].values()),
        "restart_catalog": lambda: rd("demo_restart.json")["research_catalog_file_unchanged"] is True,
        "run1_ok": lambda: run_ok(runs()[0]),
        "run2_ok": lambda: run_ok(runs()[1]),
        "reproducible": lambda: status_file("full_demo_reproducibility.json"),
        "exclusions_documented": lambda: len(rd("full_demo_reproducibility.json")["excluded_from_digest"]) >= 5,
        "no_fakery": lambda: rd("scenario_coverage.json")["mocks_used"] is False and not drift("api", "product", "frontend"),
        "out_of_scope": lambda: cap011_absent() and not drift("api", "product", "frontend", "capstone_persistence", "federated") and not [p for p in git("ls-files", "--others", "--exclude-standard").split() if p.startswith(("product/", "api/", "frontend/src"))],
        "mutation_log": lambda: (m := rd("mutation_controls.json"))["all_caught"] and m["all_restored"] and [x["mutation"] for x in m["controls"]] == json.loads(CONFIG.read_text())["mutation_controls"],
        "targeted_tests": lambda: tr()["targeted"]["returncode"] == 0,
        "prior_capstone_tests": lambda: tr()["prior_capstone_tests"]["total"] > 0 and not tr()["prior_capstone_tests"]["failed"] and rd("inherited_cap003_flake.json")["status"] == "PASS_INHERITED_FLAKE_POLICY",
        "regression": lambda: tr()["full_regression"]["returncode"] == 0 and not tr()["full_regression"]["failed"] and tr()["inherited_flake"]["status"] == "PASS_INHERITED_FLAKE_POLICY",
        "frontend_npm_test": lambda: cmd("npm_test"),
        "svelte_check": lambda: cmd("svelte_check") and tr()["frontend_summary"]["svelte_check_zero_errors"],
        "frontend_build": lambda: cmd("build") and tr()["frontend_summary"]["build_done"],
        "ruff": lambda: cmd("ruff"),
        "pip": lambda: cmd("pip_check"),
        "ci": lambda: tr()["ci_queried"] is False and tr()["ci_triggered"] is False and not any(re.search(r"\"gh\"|'gh'|api\.github|actions/runs", (ROOT / p).read_text()) for p in git("ls-files", "scripts/cap_010_*", "scripts/run_capstone_*demo*", "scripts/capstone_demo_*").split() if p.endswith(".py") and "evaluate_gate" not in p),
        "resource_audit": lambda: status_file("resource_telemetry.json") and "not a requirement" in rd("resource_telemetry.json")["note"],
        "protected_final": lambda: rd("protected_artifact_final.json")["protected_artifact_drift"] is False,
        "no_large_artifacts": no_large,
        "amendment_hygiene": amendment_hygiene,
        "components_registered": lambda: len(registry("task", "task_id")) > 0 and len(list(csv.DictReader((ROOT / "manifests/capstone/component_registry_cap_010_v1.csv").open()))) == 7 and len(json.loads((ROOT / "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json").read_text())["components"]) == 5,
        "registry_cap010": lambda: registry_state("CAP-010", "task", "PASS"),
        "registry_capg9": lambda: registry_state("CAPG9", "gate", "PASS"),
        "registry_cap011": lambda: registry("task", "task_id")["CAP-011"]["status"] == "NOT_STARTED" and cap011_absent(),
        "disclosures_preserved": disclosures_preserved,
        "handoff_sections": handoff_sections,
    })
    return c


def main() -> int:
    config = json.loads(CONFIG.read_text())
    frozen = config["capg9_criteria"]
    if len(frozen) != 104 or [r["id"] for r in frozen] != [f"CAPG9-{i:03d}" for i in range(1, 105)]:
        raise RuntimeError("CAPG9_FROZEN_CRITERIA_CHANGED")
    checks = build_checks()
    readiness = OUT / "demo_readiness.json"
    cache: dict[str, tuple[bool, str]] = {}

    def run_check(name: str) -> tuple[bool, str]:
        if name not in cache:
            try:
                if name == "readiness_clean":
                    cache[name] = (readiness.exists() and readiness_clean(readiness), "")
                else:
                    cache[name] = (bool(checks[name]()), "")
            except Exception as error:  # a failed check, never a crash
                cache[name] = (False, f"{type(error).__name__}:{str(error)[:160]}")
        return cache[name]

    def evaluate() -> list[dict[str, Any]]:
        out = []
        for row in frozen:
            results = []
            for chk in row["checks"]:
                if chk[:2] in ("T:", "S:"):
                    try:
                        results.append((chk, test_ok(chk), ""))
                    except Exception as error:
                        results.append((chk, False, f"{type(error).__name__}:{str(error)[:160]}"))
                else:
                    ok, why = run_check(chk[1:])
                    results.append((chk, ok, why))
            out.append({"id": row["id"], "text": row["text"], "pass": all(r[1] for r in results), "checks": [{"check": c_, "pass": ok, **({"error": why} if why else {})} for c_, ok, why in results]})
        return out

    rows = evaluate()
    non_readiness_pass = all(r["pass"] for r in rows if "@readiness_clean" not in [c_["check"] for c_ in r["checks"]])
    protocol = json.loads(CONFIG.read_text())
    readiness.write_text(json.dumps({
        "readiness_id": "CAPSTONE_DEMO_READINESS_V1", "gate": "CAPG9", "capg9_all_other_criteria_pass": non_readiness_pass, "claim_allowed_only_if_capg9_pass": protocol["claim_boundary"]["allowed"],
        "not_claimed": protocol["claim_boundary"]["not_claimed"], "launch_command": "python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth --mode FRESH --workspace <path outside the repository>",
        "runbook": "docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md", "hardware": "SIMULATED_ONLY", "released_default": "MODEL_V2_FINAL", "candidate_deployed": False, "timing": "ACCELERATED_FOR_PRESENTATION"}, indent=1, sort_keys=True) + "\n")
    cache.pop("readiness_clean", None)
    rows = evaluate()
    result = {"gate": "CAPG9", "criteria_count": len(rows), "decided": len(rows), "mode": "PRE_TRANSITION" if PRE else "FINAL", "all_decided_pass": all(r["pass"] for r in rows),
              "failed": [r["id"] for r in rows if not r["pass"]], "criteria": rows,
              "self_transition_note": "Registry CAP-010/CAPG9 PASS, the handoff sections and the disclosures are authorised by this gate; the pre-transition run defers exactly those checks, the final run requires them."}
    (OUT / ("capg9_criteria_pre_transition.json" if PRE else "capg9_criteria.json")).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"all_decided_pass": result["all_decided_pass"], "count": len(rows), "failed": result["failed"]}))
    return 0 if result["all_decided_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
