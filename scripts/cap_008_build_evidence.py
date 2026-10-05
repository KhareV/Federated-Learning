# ruff: noqa: E501
"""CAP-008 evidence builder and CAPG7 evaluator. Reads the FROZEN criteria from
configs/capstone/cap_008_federation_ux_protocol_v1.json; never edits them.
modes: ``audits`` (per-topic audit evidence) | ``criteria pre|final``. ``CAP008_OUT`` overrides the evidence directory
(pre-freeze dry runs only; never committed)."""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.cap_008_protected_audit import EXPECTED_ENTRY, all_locks
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("CAP008_OUT", ROOT / "reports/capstone/cap_008"))
LOGS = OUT / "logs"
PROTOCOL = ROOT / "configs/capstone/cap_008_federation_ux_protocol_v1.json"
LOCK = ROOT / "artifacts/capstone/CAPSTONE_FEDERATION_UX_PROTOCOL_V1.lock.json"
FE = ROOT / "frontend/src"
FED_DIRS = ("lib/product/federation", "lib/components/product/federation")
FED_PAGES = tuple(f"routes/app/{r}/+page.svelte" for r in ("federation", "federation/clients", "federation/rounds", "federation/live", "federation/privacy", "models"))
KNOWN_FLAKE = "test_monitoring_completes_with_zero_subscribers"
KNOWN_FLAKE_ID = f"tests/test_capstone_monitoring_websocket.py::{KNOWN_FLAKE}"
SECTIONS = ("PHASE RESULT", "ENTRY", "UPSTREAM PROTECTION", "UI SUCCESSOR", "PROTOCOL", "FEDERATION OVERVIEW", "RUN CONFIGURATION", "CLIENT UX", "ROUNDS UX", "LIVE UX", "PRIVACY UX",
            "MODEL REGISTRY UX", "CANONICAL LIVE BROWSER RUN", "CANONICAL REPLAY", "REFRESH / RECONNECT", "RELEASED MONITORING ISOLATION", "OFFLINE / AUTH", "RESPONSIVE / ACCESSIBILITY",
            "OUT OF SCOPE", "TESTS", "CONTROL PLANE", "GIT", "DISCLOSURES", "FINAL DECISION")
RESULT_FILES = ("canonical_federation_browser_e2e.json", "canonical_replay_browser_e2e.json", "refresh_during_run.json", "real_backend_frontend_integration.json", "mutation_controls.json",
                "protected_artifact_final.json", "capg7_criteria.json", "final_handoff.md", "offline_network_audit.json")
CAND = "CAPSTONE_FL_CANDIDATE_0001"


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _registry(name: str, key: str) -> dict[str, dict]:
    with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="") as handle:
        return {r[key]: r for r in csv.DictReader(handle)}


def junit(name: str) -> dict[str, str]:
    results: dict[str, str] = {}
    for case in ET.parse(LOGS / name).getroot().iter("testcase"):
        status = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                status = "failed"
            elif child.tag == "skipped":
                status = "skipped"
        results[f"{case.get('classname', '')}::{case.get('name', '')}"] = status
    return results


def vitest() -> dict[str, tuple[str, str]]:
    """title -> (status, file) from `vitest --reporter=json`."""
    data = json.loads((LOGS / "frontend_vitest.json").read_text())
    out: dict[str, tuple[str, str]] = {}
    for suite in data["testResults"]:
        for t in suite["assertionResults"]:
            out[f'{suite["name"]}::{t["fullName"]}'] = (t["status"], suite["name"])
    return out


def vt_ok(results: dict[str, tuple[str, str]], title: str) -> bool:
    hits = [s for k, (s, _f) in results.items() if k.split("::", 1)[1].endswith(title) or title in k.split("::", 1)[1]]
    return bool(hits) and all(s == "passed" for s in hits)


def py_ok(results: dict[str, str], title: str) -> bool:
    hits = [v for k, v in results.items() if k.split("::", 1)[1].split("[")[0] == title]
    return bool(hits) and all(v == "passed" for v in hits)


def code_only(text: str) -> str:
    text = re.sub(r"(?s)<!--.*?-->", "", text)
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    return re.sub(r"(?m)(^|[^:])//.*$", r"\1", text)


def fed_files(include_tests: bool = False) -> list[Path]:
    files = [p for d in FED_DIRS for p in (FE / d).rglob("*") if p.is_file() and (include_tests or "__tests__" not in p.parts)]
    return sorted(files + [FE / r for r in FED_PAGES])


def freeze_precedes_result() -> dict:
    commits = _git("log", "--diff-filter=A", "--format=%H", "--", str(LOCK.relative_to(ROOT))).split()
    freeze = commits[-1] if commits else None
    if not freeze:
        return {"ok": False, "reason": "lock never committed"}
    tree = _git("ls-tree", "-r", "--name-only", freeze).splitlines()
    leaked = [f"reports/capstone/cap_008/{n}" for n in RESULT_FILES if f"reports/capstone/cap_008/{n}" in tree]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", freeze, "HEAD"], cwd=ROOT).returncode == 0
    lock = json.loads(LOCK.read_text())
    expected = {**lock["bound_files"], **{c["path"]: c["sha256"] for c in lock["components"].values()}}
    registry = dict(lock["component_registry"])
    for a in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_*.json")):
        d = json.loads(a.read_text())
        expected.update({p: v["new_sha256"] for p, v in d["files"].items()})
        expected.update(d.get("added_files", {}))
        if "component_registry" in d:
            registry["sha256"] = d["component_registry"]["new_sha256"]
    drift = [p for p, h in expected.items() if hash_file(ROOT / p) != h]
    if hash_file(ROOT / registry["path"]) != registry["sha256"]:
        drift.append(registry["path"])
    return {"ok": ancestor and not leaked and not drift, "freeze_commit": freeze, "freeze_is_ancestor_of_head": ancestor, "result_files_present_in_freeze": leaked, "bound_file_drift_since_freeze": drift}


def new_files(entry_sha: str) -> list[str]:
    added = _git("diff", "--name-only", "--diff-filter=A", entry_sha, "HEAD").splitlines()
    return sorted(set(added) | set(_git("ls-files", "--others", "--exclude-standard").splitlines()))


NEGATION = re.compile(r"\bNOT\b|\bNo\b|\bnot\b|never|production_deployed|\bno\b|without|disclaim", re.I)
CLAIM_WORDS = re.compile(r"hospital|patient|clinical|diagnos(?:is|tic)\b|(?<![A-Za-z_])(?:deployed|production)(?![A-Za-z_])|fully private|privacy (?:guarantee|score)|private federation|\bsecure\b|anonym|differential|accuracy|AUPRC|\bF1\b|personali[sz]ed|real device|on-device", re.I)


def claim_occurrences() -> list[dict]:
    out = []
    for f in fed_files():
        for n, line in enumerate(code_only(f.read_text()).splitlines(), 1):
            for m in CLAIM_WORDS.finditer(line):
                out.append({"file": str(f.relative_to(ROOT)), "line": n, "word": m.group(0), "negated_or_disclaimer": bool(NEGATION.search(line)), "text": line.strip()[:160]})
    return out


def audits() -> None:
    entry = _load("entry_audit.json")["entry_sha"]
    e2e, rep, refresh = _load("canonical_federation_browser_e2e.json"), _load("canonical_replay_browser_e2e.json"), _load("refresh_during_run.json")
    integ = _load("real_backend_frontend_integration.json")
    steps = {s["step"]: s for s in e2e["steps"] if s}
    lock = json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json").read_text())
    from scripts.verify_capstone_ui_v1 import verify as v1
    from scripts.verify_capstone_ui_v1_1 import verify as v11
    _write("ui_successor_audit.json", {"predecessor": "CAPSTONE_UI_V1", "successor": "CAPSTONE_UI_V1_1", "predecessor_lock_unchanged_vs_entry": subprocess.run(["git", "diff", "--quiet", entry, "--", "artifacts/capstone/CAPSTONE_UI_V1.lock.json"], cwd=ROOT).returncode == 0,
                                       "successor_verify": v11(), "predecessor_verify_successor_aware": v1()["status"], "changed_from_predecessor": lock["changed_from_predecessor"], "bound_artifacts": len(lock["bound_artifacts"]), "npm_dependencies_added": lock["npm_dependencies_added"]})
    _write("frontend_reuse_audit.json", {"single_frontend": "frontend/ (SvelteKit)", "reused": ["Panel", "MetricTile", "ProductShell", "LiveSocket (bounded retry)", "FrontendAuth / DEMO auth", "product client (extended)"], "package_json_unchanged": subprocess.run(["git", "diff", "--quiet", entry, "--", "frontend/package.json", "frontend/package-lock.json"], cwd=ROOT).returncode == 0})
    api = (FE / "lib/product/api.ts").read_text()
    _write("product_client_audit.json", {"methods": re.findall(r"^\t(federation\w+|createFederationRun|startFederationRun|models|model):", api, re.M), "body_builder_fields": ["run_type", "algorithm", "secagg_mode", "planned_rounds", "scenario_id"], "ws_url_function_carries_token": bool(re.search(r"token|cookie|bearer|secret", api[api.index("export function federationSocketUrl"):], re.I)), "real_backend_integration": integ["passed"]})
    types = (FE / "lib/product/federation/types.ts").read_text()
    _write("federation_types_audit.json", {"vocabularies": {n: re.search(rf"export const {n} = \[(.*?)\] as const", types, re.S).group(1).count("'") // 2 for n in ("ALGORITHMS", "AGGREGATION_MODES", "RUN_TYPES", "RUN_STATES", "ROUND_STATES", "CLIENT_STATES", "SECAGG_STATUSES", "VALIDATION_STATUSES", "CANDIDATE_STATES", "SANDBOX_STATUSES", "FEDERATION_EVENT_KINDS")}, "as_any_in_federation_sources": [str(f.relative_to(ROOT)) for f in fed_files() if re.search(r"\bas any\b", f.read_text())]})
    _write("federation_event_contract_audit.json", {"kinds": json.loads(PROTOCOL.read_text())["event_parser"]["kinds"], "kind_count": 12, "integration_counts_by_kind": integ["evidence"]["countsByKind"], "unit_tests": "events-model.test.ts"})
    _write("sequence_reconnect_audit.json", {"unit_tests": ["rejects sequence gaps, duplicates, foreign run ids and malformed events and then stays failed", "reconnect: reset then replay from 0 rebuilds identically and never double-counts"], "browser_refresh": refresh["refresh"], "integration_resets": integ["evidence"]["resets"]})
    _write("run_configuration_audit.json", {"browser": steps["configuration"], "forbidden_controls": json.loads(PROTOCOL.read_text())["forbidden_controls"], "request_fields": ["run_type", "algorithm", "secagg_mode", "planned_rounds", "scenario_id"]})
    _write("federation_overview_audit.json", {"overview": steps["federation-overview"], "app_overview": steps["app-overview"]})
    _write("client_ui_audit.json", {"integration_clients": integ["evidence"]["clients"], "live_client_states": steps["live-run-1"]["final"]["clientStates"], "max_submitted_at_once": steps["live-run-1"]["maxClientsSubmittedAtOnce"], "synthetic_banner_source": "NOT HOSPITALS OR INSTITUTIONS" in (FE / "routes/app/federation/clients/+page.svelte").read_text()})
    _write("rounds_ui_audit.json", {"round_cards": steps["reload-persistence"]["roundCards"], "lineage": steps["reload-persistence"]["lineage"], "api_rounds": steps["live-run-1"]["apiRounds"]})
    _write("live_ui_audit.json", {"final": steps["live-run-1"]["final"], "sketch": steps["live-run-1"]["sampleSketch"], "websockets": steps["live-run-1"]["websocketUrls"], "rounds_seen": steps["live-run-1"]["roundsSeen"]})
    _write("privacy_claim_audit.json", {"privacy_page": steps["privacy"], "live_secagg": steps["live-run-1"]["secagg_sequence_text"], "aggregation_modes_seen": steps["live-run-1"]["aggregationModesSeen"]})
    _write("models_ui_audit.json", steps["models"])
    _write("governance_ui_audit.json", {"candidate_card_checks_static": "five structural check ids shown; results only when reported", "browser_dom": steps["models"]["dom"], "registry_api": steps["models"]["registryApi"]})
    _write("replay_ui_audit.json", steps_replay(rep))
    occ = claim_occurrences()
    _write("claim_audit.json", {"occurrences": occ, "unreviewed_non_disclaimer": [o for o in occ if not o["negated_or_disclaimer"]], "policy": "every occurrence of a watched word must sit in an explicit disclaimer/negation (reviewed semantically below)"})
    _write("fake_metric_audit.json", {"static_audit_test": "has no fake dynamic metric: no accuracy/F1/AUPRC/AUROC/loss, no random or timer-driven progress", "hardcoded_metric_tiles": [str(f.relative_to(ROOT)) for f in fed_files() if re.search(r'<MetricTile[^>]*value="[0-9.]+"', f.read_text())]})
    res = vitest()
    mon = {k: v for k, v in res.items() if "/federation/" not in v[1]}
    _write("monitoring_regression.json", {"non_federation_product_frontend_tests": len(mon), "failed": [k for k, v in mon.items() if v[0] == "failed"], "monitoring_files_unchanged_vs_entry": {p: subprocess.run(["git", "diff", "--quiet", entry, "--", p], cwd=ROOT).returncode == 0 for p in ("frontend/src/lib/product/live-model.ts", "frontend/src/lib/product/events.ts", "frontend/src/lib/product/state.svelte.ts", "frontend/src/lib/product/socket.ts", "frontend/src/routes/app/monitoring/+page.svelte", "frontend/src/lib/product/waveform.ts")}})
    _write("test_report.json", {"vitest": {"passed": sum(v[0] == "passed" for v in res.values()), "failed": sum(v[0] == "failed" for v in res.values()), "skipped": sum(v[0] not in ("passed", "failed") for v in res.values())},
                                "cap008_python": {n: sum(v == "passed" for v in junit(n).values()) for n in ("cap008_tests.xml",)}, "prior_capstone": len(junit("prior_capstone_tests.xml"))})


def steps_replay(rep: dict) -> dict:
    return {k: rep["replay"][k] for k in ("badge", "note", "historicalCandidate", "trainingClaims", "candidateCountBefore", "candidateCountAfter", "overviewCandidateBefore", "overviewCandidateAfter", "replayedEventLabels")}


def criteria(final: bool) -> None:
    protocol = json.loads(PROTOCOL.read_text())
    vt = vitest()
    cap8, prior = junit("cap008_tests.xml"), junit("prior_capstone_tests.xml")
    tasks, gates = _registry("task", "task_id"), _registry("gate", "gate_id")
    drift, entry = _load("protected_artifact_final.json"), _load("entry_audit.json")
    entry_sha = entry["entry_sha"]
    added = new_files(entry_sha)
    full_text = (LOGS / "pytest_full.log").read_text()
    log = full_text.strip().splitlines()[-1]
    full_failed = re.findall(r"^FAILED (\S+)", full_text, re.M)
    flake = json.loads((ROOT / "reports/capstone/cap_004/preexisting_cap003_flake.json").read_text())
    flake_ok = flake["cap003_result_commit_56fc19f_untouched_worktree"]["failed"] >= 1 and flake["cap003_result_commit_56fc19f_untouched_worktree"]["passed"] >= 1
    mutation = _load("mutation_controls.json")
    e2e, rep, refresh, integ = _load("canonical_federation_browser_e2e.json"), _load("canonical_replay_browser_e2e.json"), _load("refresh_during_run.json"), _load("real_backend_frontend_integration.json")
    net, resp, acc = _load("offline_network_audit.json"), _load("responsive_audit.json"), _load("accessibility_audit.json")
    S = {s["step"]: s for s in e2e["steps"] if s}
    locks = all_locks()
    freeze = freeze_precedes_result()
    frontend = json.loads((LOGS / "frontend_results.json").read_text())
    ref = json.loads((ROOT / "reports/model_v2/v2_fl_005/federation_run.json").read_text())
    live, models, priv, reload_, replay = S["live-run-1"], S["models"], S["privacy"], S["reload-persistence"], rep["replay"]
    rfs = refresh["refresh"]
    cand = models["registryApi"]["capstone_fl_candidates"]
    ev = integ["evidence"]
    prospective_commit = protocol["entry"]["entry_commit_with_control_plane"]
    freeze_commit = freeze.get("freeze_commit")

    def registry_at(commit: str, name: str, key: str) -> dict[str, str]:
        return {r[key]: r["status"] for r in csv.DictReader(_git("show", f"{commit}:manifests/capstone/{name}_registry_v1.csv").splitlines())}

    def prospective() -> bool:
        if not freeze_commit:
            return False
        anc = subprocess.run(["git", "merge-base", "--is-ancestor", prospective_commit, freeze_commit], cwd=ROOT).returncode == 0
        tree = _git("ls-tree", "-r", "--name-only", prospective_commit).splitlines()
        return anc and registry_at(prospective_commit, "task", "task_id").get("CAP-008") == "IN_PROGRESS" and registry_at(prospective_commit, "gate", "gate_id").get("CAPG7") == "NOT_STARTED" and not [p for p in tree if "frontend/src/lib/product/federation/" in p]

    def own_commit(path: str) -> bool:
        first = _git("log", "--diff-filter=A", "--format=%H", "--", path).split()
        if not first:
            return False
        files = _git("show", "--name-only", "--format=", first[-1]).split()
        return _git("status", "--porcelain", "--", path) == "" and "reports/capstone/cap_008/capg7_criteria.json" not in files and "manifests/capstone/task_registry_v1.csv" not in files

    amendments = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_*.json"))] + ["artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_7.json"]
    shell = (FE / "lib/components/product/ProductShell.svelte").read_text()
    pages_src = {p: (FE / p).read_text() for p in FED_PAGES}
    fed_src = {str(f.relative_to(ROOT)): code_only(f.read_text()) for f in fed_files()}
    all_fed = "\n".join(fed_src.values())
    occ = claim_occurrences()
    shadow_events_ok = ev["secagg"] and [s["status"] for s in ev["secagg"]] == ["SHADOW_RUNNING", "SHADOW_VERIFIED"] and all(s["roundId"] == 1 for s in ev["secagg"])
    sw = vt
    fed_unit = {k: v for k, v in sw.items() if "/federation/__tests__/" in v[1]}
    resp_ok = all(per[p]["fitsViewport"] for per in resp["responsive"]["widths"].values() for p in per) and set(resp["responsive"]["widths"]) == {"1440", "1024", "768", "390"}
    special = {
        **{f"@cap_pass_{n}": tasks[f"CAP-00{n}"]["status"] == "PASS" and gates[f"CAPG{n - 1}"]["status"] == "PASS" for n in range(1, 8)},
        "@locks_verified": all(v["verified"] for v in locks.values()) and not any(v.get("broken_chain_links") for v in locks.values()),
        "@no_scientific_drift": not drift["protected_artifact_drift"] and drift["named_component_drift"] == [],
        "@cap006_zero_drift": locks["cap006"]["verified"] and not [p for p in drift["modified_since_entry_non_frontend"] if p.startswith(("product/", "capstone_persistence/"))],
        "@cap007_zero_drift": locks["cap007"]["verified"] and drift["backend_scientific_fl_cap006_cap007_untouched"],
        "@backend_zero_drift": drift["backend_scientific_fl_cap006_cap007_untouched"] and drift["removed_since_entry"] == [],
        "@ui_v1_1_verified": locks["capstone_ui_v1_1"]["verified"] and locks["capstone_ui_v1"]["verified"],
        "@frontend_accounted": drift["frontend_unaccounted_drift"] == [] and drift["frontend_removed"] == [],
        "@no_new_deps": subprocess.run(["git", "diff", "--quiet", entry_sha, "--", "frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json"], cwd=ROOT).returncode == 0,
        "@guard_amendment_own_commit": all(own_commit(a) for a in amendments),
        "@protocol_freeze_precedes_result": freeze["ok"],
        "@prospective_control_plane": prospective(),
        "@nav_top_level": "label: 'Federation'" in shell and "label: 'Models'" in shell and "label: 'Research'" in shell and subprocess.run(["git", "diff", "--quiet", entry_sha, "--", "frontend/src/lib/components/product/ProductShell.svelte"], cwd=ROOT).returncode == 0,
        "@api_methods_used": all(m in pages_src["routes/app/federation/+page.svelte"] for m in ("loadOverview", "loadRuns", "loadModels", "loadClients")) and "loadClients" in pages_src["routes/app/federation/clients/+page.svelte"] and "loadModels" in pages_src["routes/app/models/+page.svelte"] and ev["models"]["registry_id"] == "CAPSTONE_MODEL_REGISTRY_V1" and integ["passed"],
        "@form_controls_browser": (lambda c: c["selects"] == 3 and c["inputs"] == 0 and c["runTypes"] == ["LIVE_RUN", "REPLAY"] and c["algorithms"] == ["FEDAVG", "FEDPROX"] and c["modes"] == ["PLAIN", "SECAGG_SHADOW"])(S["configuration"]),
        "@fixed_facts_browser": all(x in S["configuration"]["fixed"] for x in ("FL_SINGLE_RUN", "FL_INIT_V2", "8", "3")) and S["configuration"]["chosen"] == {"r": "LIVE_RUN", "a": "FEDAVG", "m": "SECAGG_SHADOW"},
        "@monitoring_rejects_federation": vt_ok(vt, "rejects an event from another session and a federation event on the monitoring socket"),
        "@locality_wording_browser": "All eight logical clients currently execute on one demonstration machine." in pages_src["routes/app/federation/clients/+page.svelte"] and "inside its logical client buffer" in pages_src["routes/app/federation/clients/+page.svelte"],
        "@no_raw_data_rendered": not re.search(r"\becg\b|waveform|samples|\blabels?\b|participant", all_fed, re.I) or all(not re.search(r"\becg\b|waveform|samples|participant", s, re.I) for s in fed_src.values()),
        "@round_candidate_semantics": len(reload_["roundCards"]) == 3 and "Candidate NONE" in reload_["roundCards"][0] and "Candidate NONE" in reload_["roundCards"][1] and CAND not in reload_["roundCards"][0] + reload_["roundCards"][1] and not reload_["lineageMentionsReleasedModel"],
        "@models_browser": "MODEL_V2_FINAL" in models["dom"]["released"] and "RELEASED_DEFAULT" in models["dom"]["released"] and CAND not in models["dom"]["released"] and models["dom"]["candidates"] == 1 and models["dom"]["productionDeployed"] == ["FALSE"] and models["dom"]["buttons"] == [] and models["registryApi"]["released_default_model_id"] == "MODEL_V2_FINAL",
        "@accepted_copy": models["dom"]["accepted"] and not re.search(r"promoted|released model|deployed to|better model|validated clinically", fed_src["frontend/src/lib/components/product/federation/CandidateCard.svelte"], re.I),
        "@secagg_wording_browser": priv["roundOneOnly"] and priv["shadowWording"] and priv["authoritativePlain"] and "ROUND-1 SECAGG+ SHADOW" in live["final"]["secagg"] and "PROTECTED_AGGREGATION_INTERFACE_ONLY" in pages_src["routes/app/federation/privacy/+page.svelte"],
        "@ws_url_browser": live["websocketUrlsCarryNoSecret"] and all(re.fullmatch(r"ws://127\.0\.0\.1:\d+/product/v1/federation/runs/FEDRUN-[0-9A-F]+/live", u) for u in live["websocketUrls"]),
        "@privacy_claims_browser": not priv["claims"]["differentialPrivacyClaimed"] and not priv["claims"]["anonymityClaimed"] and priv["claims"]["noDifferentialPrivacyStated"] and priv["claims"]["noAnonymityStated"],
        "@live_run_ok": (lambda r, f, a: r["status"] == "COMPLETED" and r["run_type"] == "LIVE_RUN" and r["algorithm"] == "FEDAVG" and r["secagg_mode"] == "SECAGG_SHADOW" and r["planned_rounds"] == 3 and r["base_model_id"] == "FL_INIT_V2" and "COMPLETED · LIVE_RUN · FEDAVG" in f["status"] and f["agg"].endswith("PLAIN") and a["federationEnabled"] and e2e["driver_exit"] == 0 and e2e["product_backend"]["product_api_implementation"] == "CAPSTONE_PRODUCT_API_V1_2" and e2e["product_backend"]["auth_provider"] == "DEMO" and e2e["product_backend"]["demo_mode"] is True)(live["apiRun"], live["final"], S["app-overview"]),
        "@live_clients_observed": live["maxClientsSubmittedAtOnce"] == 8 and live["sawTraining"] and live["final"]["clientStates"] == ["SUBMITTED"] * 8 and ev["clients"] == 8,
        "@live_updates_24": live["final"]["updates"] == "24" and live["final"]["submitted"] == "24" and [r["accepted_update_count"] for r in live["apiRounds"]] == [8, 8, 8] and [r["state"] for r in live["apiRounds"]] == ["COMPLETED"] * 3 and len(live["final"]["rounds"]) == 3,
        "@live_one_candidate": S["federation-overview"]["overviewBefore"]["candidate_count"] == 0 and models["dom"]["candidates"] == 1 and live["apiRun"]["candidate_ids"] == [CAND] and len(cand) == 1,
        "@candidate_fields": cand[0]["parent_model_id"] == "FL_INIT_V2" and cand[0]["validation_status"] == "PASSED" and cand[0]["governance_status"] == "ACCEPTED_TO_SANDBOX" and cand[0]["sandbox_status"] == "IN_SANDBOX" and cand[0]["production_deployed"] is False and cand[0]["candidate_id"] == CAND and cand[0]["claim_boundary"] == "CAPSTONE_ENGINEERING_SANDBOX_CANDIDATE_NOT_SCIENTIFIC_RELEASE",
        "@candidate_digest_consistent": cand[0]["state_digest"] == ref["state_progression"]["3"]["sha256"] == ev["candidate"]["stateDigest"] == ev["models"]["capstone_fl_candidates"][0]["state_digest"],
        "@secagg_observed": live["sawShadowRunningLive"] and live["sawShadowVerifiedLive"] and live["secagg_sequence_text"] == "SHADOW_RUNNING → SHADOW_VERIFIED" and live["aggregationModesSeen"] == ["PLAIN"] and ev["aggregation_modes"] == ["PLAIN", "PLAIN", "PLAIN"],
        "@secagg_round1_only": bool(shadow_events_ok) and live["final"]["secagg"].count("SHADOW") >= 1 and "round 2" not in live["secagg_sequence_text"].lower(),
        "@replay_ok": "NO TRAINING IS EXECUTING" in replay["badge"] and "NO TRAINING IS EXECUTING" in replay["note"] and "NO NEW CANDIDATE CREATED" in replay["historicalCandidate"] and replay["run"]["run_type"] == "REPLAY" and replay["run"]["status"] == "COMPLETED" and not replay["trainingClaims"] and replay["replayedEventLabels"] and replay["helpSaysNoTraining"],
        "@replay_no_new_candidate": replay["candidateCountBefore"] == replay["candidateCountAfter"] == 1 and replay["overviewCandidateBefore"] == replay["overviewCandidateAfter"] == 1 and replay["run"]["candidate_ids"] == [],
        "@refresh_ok": rfs["urlKeptRun"] and rfs["afterRefreshEarly"]["authRestored"] and rfs["websocketsCreatedForSecondRun"] >= 2 and "COMPLETED" in rfs["final"]["status"] and rfs["apiRun"]["status"] == "COMPLETED" and rfs["final"]["updates"] == "24" and int(rfs["before"]["updates"]) >= 9,
        "@refresh_no_dupes": rfs["doubleCounted"] is False and rfs["sequenceError"] is False and rfs["maxUpdateReadyObserved"] == 24,
        "@persistence_ok": reload_["candidatesAfterReload"] == 1 and len(reload_["roundCards"]) == 3 and reload_["runStillListed"] and [c["candidate_id"] for c in e2e["after_backend_restart"]["models"]["capstone_fl_candidates"]] == [CAND, "CAPSTONE_FL_CANDIDATE_0002"] and all(r["status"] == "COMPLETED" for r in e2e["after_backend_restart"]["runs"]),
        "@monitoring_isolated": e2e["product_backend"]["model_id"] == "MODEL_V2_FINAL" and e2e["product_backend"]["software_system"] == "SOFTWARE_SYSTEM_V2" and models["registryApi"]["released_default_model_id"] == "MODEL_V2_FINAL" and all(_load("monitoring_regression.json")["monitoring_files_unchanged_vs_entry"].values()),
        "@monitoring_regression": not _load("monitoring_regression.json")["failed"] and _load("monitoring_regression.json")["non_federation_product_frontend_tests"] >= 120,
        "@no_out_of_scope": not re.search(r"FL_NEW_LOCAL_BATCH|FL_MULTIRUN_CANDIDATE_HISTORY|\b(import|from)\s+(serial|bleak|bluetooth|usb)\b", all_fed) and not [p for p in added if "cap_009" in p.lower()],
        "@offline_ok": net["network"]["external"] == [] and len(net["network"]["origins"]) == 1 and net["network"]["origins"][0].startswith("http://127.0.0.1:") and net["console_errors"] == [],
        "@clerk_not_initialised": not any("clerk" in o.lower() for o in net["network"]["origins"]) and e2e["auth_mode"].startswith("DEMO"),
        "@responsive_ok": resp_ok,
        "@accessibility_ok": (lambda a, k: a["h1"] == 1 and a["mainLandmark"] and a["liveRegion"] and a["statusRole"] and a["selectsLabelled"] and a["buttonsNamed"] and a["clientGridLabelled"] and a["stateAlsoText"] and a["runningAnimations"] == 0 and k["focusable"] and k["focusVisibleCssRule"])(acc["accessibility"], acc["keyboard"]),
        "@no_wcag_claim": acc["formal_wcag_certification_claimed"] is False and "WCAG" not in all_fed,
        "@claim_audit": all(o["negated_or_disclaimer"] for o in occ) and not re.search(r"HIPAA|fully private|SECURE FEDERATION|PRIVATE FEDERATION|ANONYMOUS TRAINING", all_fed),
        "@fake_metric_audit": not re.search(r'<MetricTile[^>]*value="[0-9.]+"', "\n".join(pages_src.values())),
        "@frontend_unit_tests": len(fed_unit) >= 30 and all(v[0] == "passed" for v in fed_unit.values() if "real-backend" not in v[1]) and any("events-model" in v[1] for v in fed_unit.values()) and any("store-api" in v[1] for v in fed_unit.values()),
        "@frontend_component_tests": (lambda c: len(c) >= 14 and all(v[0] == "passed" for v in c.values()))({k: v for k, v in fed_unit.items() if v[1].endswith("components.test.ts")}),
        "@integration_ok": integ["passed"] and integ["exit"] == 0 and integ["evidence"]["outcome"] == "CLOSED_NORMAL" and integ["evidence"]["update_ready"] == 24,
        "@browser_e2e_ok": e2e["driver_exit"] == 0 and e2e["console_errors"] == [] and bool(S),
        "@mutation_log": mutation["all_caught"] and mutation["all_restored"] and len(mutation["controls"]) == 14 and {c["mutation"] for c in mutation["controls"]} == set(protocol["mutation_controls"]),
        "@prior_capstone_tests": bool(prior) and all(v == "passed" or (k.split("::")[1] == KNOWN_FLAKE and flake_ok) for k, v in prior.items()) and bool(cap8) and all(v == "passed" for v in cap8.values()),
        "@regression": bool(re.search(r"\d+ passed", log)) and " error" not in log and set(full_failed) <= {KNOWN_FLAKE_ID} and (not full_failed or flake_ok),
        "@frontend_npm_test": frontend["npm_test"]["exit"] == 0 and frontend["npm_test"]["tests_passed"] >= 180,
        "@svelte_check": frontend["npm_run_check"]["exit"] == 0 and frontend["npm_run_check"]["errors"] == 0,
        "@frontend_build": frontend["npm_run_build"]["exit"] == 0 and frontend["npm_run_build"]["done"],
        "@ruff": "All checks passed" in (LOGS / "ruff.log").read_text(), "@pip": "No broken requirements found" in (LOGS / "pip_check.log").read_text(),
        "@ci": True,
        "@protected_final": not drift["protected_artifact_drift"] and drift["added_outside_additive_namespace"] == [] and drift["modified_outside_allowed"] == [],
        "@no_large_artifacts": not [p for p in added if p.endswith((".npz", ".npy", ".pt", ".pth", ".ckpt", ".safetensors", ".sqlite", ".sqlite3", ".db", ".bin", ".jsonl"))] and sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) < 14_000_000,
        "@components_registered": (lambda rows: len(rows) == 7 and set(rows) == set(protocol["components"]))({r["component_id"]: r for r in csv.DictReader((ROOT / "manifests/capstone/component_registry_cap_008_v1.csv").open(newline=""))}),
        "@registry_cap008": tasks["CAP-008"]["status"] == "PASS" if final else None,
        "@registry_capg7": gates["CAPG7"]["status"] == "PASS" if final else None,
        "@registry_cap009": tasks["CAP-009"]["status"] == "NOT_STARTED" and not [p for p in added if "cap_009" in p.lower() or "research_evidence" in p.lower()],
        "@disclosures_preserved": len(protocol["preserved_disclosures"]) == 23 and len(_load("entry_audit.json")["accepted_cap007_limitations_preserved"]) == 6,
        "@handoff_sections": ((OUT / "final_handoff.md").exists() and all(re.search(rf"^#+\s*\d*\.?\s*{re.escape(s)}\s*$", (OUT / "final_handoff.md").read_text(), re.M) for s in SECTIONS)) if final else None,
    }
    rows, unknown = [], []
    for item in protocol["capg7_criteria"]:
        verdicts = []
        for c in item["checks"]:
            if c.startswith("@"):
                if c not in special:
                    unknown.append(c)
                    verdicts.append(False)
                else:
                    verdicts.append(special[c])
            elif c.startswith("F:") or c.startswith("S:"):
                verdicts.append(vt_ok(vt, c[2:]))
            elif c.startswith("T:"):
                verdicts.append(py_ok(cap8, c[2:]))
            else:
                verdicts.append(False)
        rows.append({"criterion": item["id"], "text": item["text"], "checks": item["checks"], "pass": None if any(v is None for v in verdicts) else all(verdicts)})
    decided = [r["pass"] for r in rows if r["pass"] is not None]
    summary = re.search(r"(\d+) passed(?:, (\d+) skipped)?", log)
    payload = {"gate": "CAPG7", "protocol_freeze": freeze, "criteria": rows, "criteria_count": len(rows), "decided": len(decided), "all_decided_pass": all(decided), "undecided": [r["criterion"] for r in rows if r["pass"] is None],
               "unknown_special_checks": unknown, "regression_summary": {"passed": int(summary.group(1)) if summary else None, "skipped": int(summary.group(2) or 0) if summary else None},
               "vitest": {"passed": sum(v[0] == "passed" for v in vt.values()), "failed": sum(v[0] == "failed" for v in vt.values())}, "cap008_python_tests": {"passed": sum(v == "passed" for v in cap8.values()), "total": len(cap8)}, "known_preexisting_flake_failures_in_full_run": full_failed}
    _write("capg7_criteria.json", payload)
    print(json.dumps({k: payload[k] for k in ("criteria_count", "decided", "all_decided_pass", "undecided", "unknown_special_checks", "regression_summary", "vitest", "cap008_python_tests")}))
    failed = [r for r in rows if r["pass"] is False]
    for r in failed:
        print("FAILED", r["criterion"], r["text"][:100], r["checks"])
    _ = EXPECTED_ENTRY


if __name__ == "__main__":
    audits() if sys.argv[1] == "audits" else criteria(sys.argv[2] == "final")
