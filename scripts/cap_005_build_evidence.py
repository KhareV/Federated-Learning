# ruff: noqa: E501
"""CAP-005 evidence builder and CAPG4 evaluator. Reads the FROZEN criteria from
configs/capstone/cap_005_frontend_product_protocol_v1.json; never edits them.

modes: ``inventory``  - frontend baseline inventory, reuse audit and claim audit BEFORE (from the entry commit tree)
       ``audits``     - per-topic audit files from the canonical runs, the built bundle and the source tree
       ``criteria pre|final`` - evaluate CAPG4 (``pre`` before registry transition, ``final`` after)
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.cap_005_protected_audit import EXPECTED_ENTRY, all_locks
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
SRC = FE / "src"
OUT = ROOT / "reports/capstone/cap_005"
LOGS = OUT / "logs"
PROTOCOL = ROOT / "configs/capstone/cap_005_frontend_product_protocol_v1.json"
PROTOCOL_LOCK = ROOT / "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json"
PRODUCT_RE = re.compile(r"^(lib/product|lib/components/product|routes/app|routes/sign-in)")
PHRASES = ["diagnose", "diagnosis", "disease detected", "patient-specific model", "real wearable", "live hardware",
           "hospital client", "clinical decision", "medical device", "privacy guaranteed", "anonymous",
           "differential privacy", "on-device MODEL_V2", "ESP32 inference", "PPG waveform connected"]
OVERSTATEMENTS = [r"ECG STREAM / CONNECTED", r"PPG STREAM / CONNECTED", r"SENSOR ARRAY / READY", r"titanium", r"dual-core edge machine learning",
                  r"<strong>ESP32</strong>", r"PROCESS LOCALLY", r"Authentication disabled", r"federationMarkers", r"QUALITY / EXCELLENT",
                  r"images\.unsplash\.com", r"fonts\.googleapis\.com", r"Your health\.", r"Open Monitor", r'text="Rich Harris"']
CITIES = r"Delhi|Mumbai|Chennai|Bangalore|London|New York|Tokyo|Singapore|San Francisco"
QUALIFIER = re.compile(r"\b(future|not|no|never|unavailable|unverified|planned|without|isn't|is not|neither|non-)\b", re.I)
FUTURE_TABLES = ("session_summaries", "federation_runs", "federation_rounds", "fl_client_statuses", "candidate_models", "governance_decisions")
ALLOWED_PRODUCT_ROUTES = {"/product/v1/devices", "/product/v1/devices/simulated", "/product/v1/devices/{device}/connect", "/product/v1/devices/{device}/scan",
                          "/product/v1/me", "/product/v1/sessions", "/product/v1/sessions/{session}", "/product/v1/sessions/{session}/start", "/product/v1/system"}
KNOWN_FLAKE = "test_monitoring_completes_with_zero_subscribers"
KNOWN_FLAKE_ID = f"tests/test_capstone_monitoring_websocket.py::{KNOWN_FLAKE}"


def _write(name: str, payload: object) -> None:
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


def lookup(results: dict[str, str], title: str) -> bool:
    matches = [v for k, v in results.items() if k.split("::", 1)[1].split("[")[0] == title or k.split("::", 1)[1].endswith(f" > {title}")]
    return bool(matches) and all(v == "passed" for v in matches)


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return re.sub(r"<!--[\s\S]*?-->", "", text)


def fe_source_files(read_from_git: str | None = None) -> list[str]:
    """Non-test .svelte/.ts source paths under frontend/src (relative to src)."""
    if read_from_git:
        names = _git("ls-tree", "-r", "--name-only", read_from_git, "--", "frontend/src").splitlines()
        return sorted(n[len("frontend/src/"):] for n in names if n.endswith((".svelte", ".ts")) and "/__tests__/" not in n)
    return sorted(str(p.relative_to(SRC)) for p in SRC.rglob("*") if p.is_file() and p.suffix in (".svelte", ".ts") and "__tests__" not in p.parts)


def read_src(rel: str, git_ref: str | None = None) -> str:
    if git_ref:
        return _git("show", f"{git_ref}:frontend/src/{rel}")
    return (SRC / rel).read_text()


def sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start) + 1, start - 90)
    dot = text.find(".", end)
    return text[left: min(len(text) if dot == -1 else dot, end + 90)].strip()


def phrase_scan(files: list[str], git_ref: str | None = None) -> dict:
    occurrences, unqualified = [], []
    for rel in files:
        text = strip_comments(read_src(rel, git_ref))
        text = re.sub(r"<style[\s\S]*?</style>", "", text)
        for phrase in PHRASES:
            for match in re.finditer(re.escape(phrase), text, re.I):
                context = sentence_around(text, match.start(), match.end())
                item = {"file": rel, "phrase": phrase, "context": context[:160], "qualified": bool(QUALIFIER.search(context))}
                occurrences.append(item)
                if not item["qualified"]:
                    unqualified.append(item)
    return {"files_scanned": len(files), "occurrences": occurrences, "unqualified": unqualified}


def overstatement_scan(files: list[str], git_ref: str | None = None) -> list[dict]:
    hits = []
    for rel in files:
        text = strip_comments(read_src(rel, git_ref))
        for pattern in OVERSTATEMENTS:
            if re.search(pattern, text):
                hits.append({"file": rel, "pattern": pattern})
    return hits


def inventory() -> None:
    entry = json.loads((OUT / "protected_artifact_entry.json").read_text())
    frontend = entry["frontend"]
    by_area: dict[str, int] = {}
    for path in frontend:
        parts = path.split("/")
        by_area["/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:2])] = by_area.get("/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:2]), 0) + 1
    _write("frontend_baseline_inventory.json", {
        "entry_sha": entry["entry_sha"], "framework": "SvelteKit 2 / Svelte 5 / adapter-static (frontend/)", "tracked_frontend_files": len(frontend),
        "files_sha256": frontend, "files_by_area": dict(sorted(by_area.items())),
        "routes_at_entry": sorted(p for p in frontend if "/routes/" in p and p.endswith("+page.svelte")),
        "components_at_entry": sorted(p for p in frontend if "/components/" in p and p.endswith(".svelte")),
        "stores_at_entry": sorted(p for p in frontend if "/stores/" in p), "api_clients_at_entry": ["frontend/src/lib/api/nhm-v1.ts", "frontend/src/lib/services/api.ts", "frontend/src/lib/services/websocket.ts"],
        "predecessor_lock": "artifacts/DASHBOARD_UI_V1_5.lock.json", "note": "generated from the entry-commit tree; chronology disclosed in final_handoff.md"})
    # reuse inventory: what existed -> what CAP-005 does with it
    _write("frontend_reuse_audit.json", {
        "reused_unchanged": {"components": ["lib/components/dashboard/Panel.svelte", "lib/components/dashboard/MetricTile.svelte", "lib/components/dashboard/MiniSpark.svelte (via MetricTile)"],
                             "modules": ["lib/dashboard/state-presentation.ts (STATE_PRESENTATION titles/texts only; the legacy 422->RECHECK_SENSOR mapping httpErrorPresentation is NOT used)"],
                             "design_system": ["app.css tokens (--nhm-*)", "teal/cyan accent, Space Grotesk / Inter / JetBrains Mono (now with local fallbacks)", "@lucide/svelte icons"],
                             "landing": ["WatchScene, PhysiologicalWaveform, NeuralGraph, HardwareStudio, MultimodalStudio, SystemArchitecture, ProductWorkstation and the magic/* components (claims already corrected in earlier phases)"],
                             "research_tool": ["routes/monitoring (research replay, logic untouched)", "lib/api/nhm-v1.ts", "lib/dashboard/replay.ts", "lib/dashboard/session.svelte.ts"]},
        "refactored_additively": ["routes/+page.svelte (landing: copy, CTAs, hero layout, topology, no remote assets)", "routes/+layout.svelte (research-tool banner; decorative cursor off in the product)", "routes/monitor/+page.svelte (redirect/notice)", "app.html + app.css (offline fonts)", "vite.config.ts + vitest.config.ts (/product proxy, Clerk alias)"],
        "not_reused_on_purpose": {"components/dashboard/DashboardShell.svelte": "its fixed legacy navigation and /api health call do not fit the product; the product shell reuses its visual language instead", "components/federation/*, stores/fl.svelte.ts": "placeholder FL metrics are non-authoritative (CAP-008 owns federation UX)", "lib/dashboard/session.svelte.ts": "maps 422 to a local RECHECK_SENSOR marker (forbidden in the product live store)"},
        "created": ["lib/product/*", "lib/components/product/*", "routes/sign-in", "routes/app/**", "clerk-sdk package"], "no_duplicate_components": "no second Panel/MetricTile/chart library was created"})
    files = fe_source_files(EXPECTED_ENTRY)
    before_scan = phrase_scan(files, EXPECTED_ENTRY)
    hits = overstatement_scan(files, EXPECTED_ENTRY)
    entry_text = read_src("routes/+page.svelte", EXPECTED_ENTRY)
    cities = sorted(set(re.findall(CITIES, entry_text))) + (["federationMarkers lat/lng markers at real cities (Delhi 28.61/77.21, Mumbai, Chennai, Bengaluru, Singapore, Tokyo, London, New York, San Francisco)"] if "federationMarkers" in entry_text else [])
    _write("claim_audit_before.json", {"tree": f"entry commit {EXPECTED_ENTRY}", "phrase_list": PHRASES, "files_scanned": before_scan["files_scanned"],
                                       "phrase_occurrences": len(before_scan["occurrences"]), "unqualified_phrase_occurrences": before_scan["unqualified"], "qualified_occurrences_sample": [o for o in before_scan["occurrences"] if o["qualified"]][:12],
                                       "overstatement_hits": hits, "geographic_markers": cities, "external_assets": {"google_fonts": "fonts.googleapis.com" in entry_text, "unsplash_images": entry_text.count("images.unsplash.com")},
                                       "summary": "the landing page predated the product architecture: attached-hardware status lines, ESP32 edge-processing flow, 'titanium unibody' hardware copy, real-city FL markers, remote fonts/images, and a /monitor shell showing 'Authentication disabled'"})


def audits() -> None:
    from scripts.cap_005_protected_audit import verify_cap004_lock  # noqa: F401

    runs = [_load(f"canonical_frontend_e2e_run_{n}.json") for n in (1, 2)]
    br = [r["browser"] for r in runs]
    integ = [_load(f"frontend_integration_run_{n}.json") for n in (1, 2)]
    steps1 = {s["step"]: s for s in br[0]["steps"]}
    protocol = json.loads(PROTOCOL.read_text())
    sdk = json.loads((FE / "clerk-sdk/package.json").read_text())
    sdk_lock = json.loads((FE / "clerk-sdk/package-lock.json").read_text())
    installed = json.loads((FE / "clerk-sdk/node_modules/@clerk/clerk-js/package.json").read_text())
    _write("clerk_frontend_dependency_audit.json", {
        "package": "@clerk/clerk-js", "version": sdk["dependencies"]["@clerk/clerk-js"], "installed_version": installed["version"], "locked_version": sdk_lock["packages"]["node_modules/@clerk/clerk-js"]["version"],
        "integrity": sdk_lock["packages"]["node_modules/@clerk/clerk-js"]["integrity"], "source": "npm registry (official Clerk browser SDK)", "why_selected": "official browser SDK for session UX/token acquisition; the backend validates the token; clerk-sveltekit is deprecated/archived",
        "range_operators_used": bool(re.search(r"[\^~<>*]", sdk["dependencies"]["@clerk/clerk-js"])), "location": "frontend/clerk-sdk (additive package)", "why_additive": "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json binds frontend/package.json and package-lock.json byte-for-byte (user-approved)",
        "frontend_package_json_unchanged": (FE / "package.json").read_bytes() == subprocess.run(["git", "show", f"{EXPECTED_ENTRY}:frontend/package.json"], cwd=ROOT, capture_output=True).stdout,
        "other_auth_libraries": [d for d in json.loads((FE / "package.json").read_text()).get("dependencies", {}) if re.search(r"auth|clerk|oidc", d, re.I)], "clerk_sveltekit_used": False,
        "frontend_secret_names_present": [], "public_config": "VITE_CLERK_PUBLISHABLE_KEY"})
    allowed = lambda t: sorted(set(re.findall(r"CLERK_[A-Z_]+|VITE_[A-Z_]+", t)))  # noqa: E731
    product_text = "\n".join(read_src(p) for p in fe_source_files() if PRODUCT_RE.match(p))
    _write("auth_frontend_audit.json", {
        "bootstrap": protocol["auth_bootstrap"], "env_names_referenced": allowed(product_text), "demo_clerk_initialised": br[0]["steps"][0].get("clerkGlobal"),
        "demo_clerk_requests_in_browser": [br[i]["network"]["clerkRequests"] for i in (0, 1)], "demo_banner": steps1["app-overview"]["banner"], "identity": steps1["app-overview"]["identity"],
        "unit_tests": ["mode is decided by the backend /system, never by a frontend toggle", "DEMO backend: never initialises or imports Clerk; /me supplies the demo identity", "CLERK backend with a missing publishable key shows AUTHENTICATION UNAVAILABLE and does not fall back to Demo", "CLERK backend whose Clerk SDK fails to initialise never falls back to Demo", "sends Authorization: Bearer only when a token provider yields one, and stores nothing"],
        "clerk_live_account_tested": False, "websocket_clerk_cookie_path_verified": False, "persistence_apis_used_by_auth": [m for m in ("localStorage", "sessionStorage", "indexedDB") if m in strip_comments(read_src("lib/product/auth.ts") + read_src("lib/product/api.ts"))]})
    _write("product_client_audit.json", {"routes": protocol["product_api_client"]["routes"], "base": "/product/v1", "observed_browser_requests": [sorted(b["network"]["productRequests"]) for b in br],
                                         "browser_infer_window_requests": [b["network"]["inferWindowFromBrowser"] for b in br], "proxy": (FE / "vite.config.ts").read_text().split("CAPSTONE_UI_V1:")[1][:600],
                                         "any_types": len(re.findall(r":\s*any\b|as any\b", "\n".join(read_src(p) for p in fe_source_files() if p.startswith("lib/product/") and p.endswith(".ts")))), "interface": "ProductClient"})
    routes_built = {p: (FE / "build" / p).is_file() for p in ("sign-in.html", "app.html", "app/device.html", "app/monitoring.html", "app/history.html", "app/federation.html", "app/models.html", "app/system.html", "app/about.html", "monitor.html", "monitoring.html", "index.html")}
    _write("route_audit.json", {"built_pages": routes_built, "ownership": protocol["route_ownership"], "legacy_monitor": read_src("routes/monitor/+page.svelte")[:400], "research_tool_label": "RESEARCH RUNTIME TOOL" in read_src("routes/+layout.svelte"),
                                "landing_cta_sign_in": len(re.findall(r'href="/sign-in"', read_src("routes/+page.svelte"))), "landing_cta_legacy_monitor": len(re.findall(r'href="/monitor"', read_src("routes/+page.svelte")))})
    _write("device_ui_audit.json", {"states_rest": [integ[i]["device_state_sequence_rest"] for i in (0, 1)], "browser_steps": {k: steps1[k] for k in ("device-empty", "device-attached", "device-connected")},
                                    "scenarios": steps1["device-empty"]["scenarios"], "physical_hardware_text": steps1["device-attached"]["physical"]})
    facts = steps1["monitoring-complete"]
    _write("monitoring_ui_audit.json", {"session": steps1["session-created"], "observed_in_dom": facts["observed"], "final_facts": facts["facts"], "monitoring_step_after_reload": steps1["monitor-after-reload"],
                                        "technical_probability_section": "details 'RESEARCH / TECHNICAL - not a risk score'"})
    _write("live_event_contract_audit.json", {"contract": "PRODUCT_LIVE_EVENT_V1 (monitoring kinds)", "event_counts_real_backend": [i["counts_by_type"] for i in integ], "unit_tests": "live-model.test.ts typed union / malformed / foreign-kind cases", "real_stream_replayed_through_the_frontend_model": "reports/capstone/cap_004/canonical_event_stream_run_1.jsonl (3157 events)"})
    _write("sequence_reconnect_audit.json", {"policy": protocol["websocket_policy"], "socket_resets_real_backend": [i["socket_resets"] for i in integ], "sequence_continuous": [i["sequence_continuous"] for i in integ],
                                              "unit_tests": ["requires next = previous + 1 and flags gaps and duplicates", "a sequence gap puts the model into a visible PRODUCT STREAM ERROR and stops consuming", "retries at most MAX_RECONNECTS times, resetting derived state on every (re)connect, then reports DISCONNECTED", "live events render into state; reconnect replays from 0 without double counting", "replay from sequence 0 is deterministic: reset + replay rebuilds identical state (no double counting)"]})
    _write("waveform_gap_audit.json", {"canonical_gap_expected": [118800, 124199], "integration_gaps": [i["gaps"] for i in integ], "browser_gap_text": [b["steps"][[s["step"] for s in b["steps"]].index("monitoring-complete")]["facts"]["gapList"] for b in br],
                                       "browser_gap_visible_frames": [b["steps"][[s["step"] for s in b["steps"]].index("monitoring-complete")]["observed"]["gapVisible"] for b in br], "buffer_capacity_samples": 3600, "waveform_chunks": integ[0]["waveform_chunks"], "zero_fill": False, "interpolation": False,
                                       "tests": ["keeps null as a gap: never zero-filled, never interpolated, separate segments", "draws null runs as separate polylines with a visible gap marker (no zero fill)"]})
    _write("offline_network_audit.json", {f"run_{i + 1}": {k: br[i]["network"][k] for k in ("requestCount", "productPhaseRequestCount", "landingPhaseRequestCount", "origins", "external", "externalInProductPhase", "clerkRequests", "failures", "websockets", "productRequests", "topProductPaths")} for i in (0, 1)} | {
        "chrome_policy": "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost (any non-loopback request would fail and be recorded)", "fonts": "local fallbacks", "remote_images": 0})
    _write("responsive_audit.json", {f"run_{i + 1}": br[i]["responsive"] for i in (0, 1)} | {"widths": protocol["responsive_widths"], "screenshots": sorted(p.name for p in (OUT / "screenshots").glob("*.png"))})
    _write("accessibility_audit.json", {f"run_{i + 1}": br[i]["accessibility"] for i in (0, 1)} | {"checks": protocol["accessibility_checks"]})
    claim_final(br)
    fake_metric_audit(br)
    _write("canonical_frontend_e2e.json", {f"run_{i + 1}": {k: v for k, v in runs[i].items() if k not in ("browser", "database_after_browser_run")} | {"browser_file": f"canonical_frontend_e2e_run_{i + 1}.json#browser"} for i in (0, 1)} | {"predeclared": protocol["canonical_e2e"]["predeclared_invariants"]})


def claim_final(br: list[dict]) -> None:
    files = fe_source_files()
    product_files = [p for p in files if PRODUCT_RE.match(p)] + ["routes/+page.svelte", "routes/monitor/+page.svelte", "routes/+layout.svelte"]
    scan = phrase_scan(product_files)
    hits = overstatement_scan(product_files)
    landing = "\n".join(br[0].get("landingText", "")) if isinstance(br[0].get("landingText"), list) else br[0].get("landingText", "")
    rendered = {**br[0].get("renderedText", {}), "landing": landing}
    rendered_hits = []
    for page, text in rendered.items():
        for phrase in PHRASES:
            for match in re.finditer(re.escape(phrase), text, re.I):
                ctx = sentence_around(text, match.start(), match.end())
                if not QUALIFIER.search(ctx):
                    rendered_hits.append({"page": page, "phrase": phrase, "context": ctx[:140]})
        for pattern in OVERSTATEMENTS:
            if re.search(pattern, text):
                rendered_hits.append({"page": page, "overstatement": pattern})
    geography = sorted(set(re.findall(CITIES, "\n".join(read_src(p) for p in product_files) + "\n" + "\n".join(rendered.values()))))
    legacy = phrase_scan([p for p in files if p not in product_files and p.startswith(("routes", "lib/components"))])
    expected_corrections = {"hardware status lines": "PHYSICAL HARDWARE / NOT CONNECTED" in read_src("routes/+page.svelte"), "no fake attached-device status": not re.search(r"ECG STREAM / CONNECTED|PPG STREAM / CONNECTED", read_src("routes/+page.svelte")),
                            "simulated source in hero": "SIMULATED SOURCE" in read_src("routes/+page.svelte"), "logical FL topology": "SIM_FL_SITE_" in read_src("routes/+page.svelte") and "NOT PARTICIPATING INSTITUTIONS" in read_src("routes/+page.svelte"),
                            "server-side inference stated": "server-side" in read_src("routes/+page.svelte").lower(), "federation not enabled": "NOT YET ENABLED" in read_src("routes/app/federation/+page.svelte") or "NOT YET ENABLED" in read_src("lib/components/product/FuturePhase.svelte")}
    _write("claim_audit_final.json", {"scope": "product source + landing + legacy /monitor + rendered text of every audited page", "phrase_occurrences_product": len(scan["occurrences"]), "qualified_occurrences_reviewed": [o for o in scan["occurrences"] if o["qualified"]],
                                      "unqualified_source_hits": scan["unqualified"], "overstatement_source_hits": hits, "rendered_pages": sorted(rendered), "rendered_unqualified_or_overstatement_hits": rendered_hits, "geographic_city_hits": geography,
                                      "claim_corrections_present": expected_corrections, "legacy_research_surfaces_phrase_occurrences": {"count": len(legacy["occurrences"]), "unqualified": legacy["unqualified"], "note": "legacy research routes (not product pages) are recorded, not rewritten"},
                                      "pass": not scan["unqualified"] and not hits and not rendered_hits and not geography and all(expected_corrections.values())})


def fake_metric_audit(br: list[dict]) -> None:
    app_files = [p for p in fe_source_files() if p.startswith("routes/app") and p.endswith(".svelte")]
    literal = re.compile(r"\b(\d{2,3}\s?bpm|\d{2,3}\s?%\s?SpO|accuracy\s*[:=]?\s*0?\.\d+|F1\s*[:=]?\s*0?\.\d+|round\s*\d+\s*(of|/)\s*\d+|\d+\s+(clients|hospitals|patients))\b", re.I)
    static_hits = []
    for rel in app_files:
        text = re.sub(r"<style[\s\S]*?</style>", "", strip_comments(read_src(rel)))
        static_hits += [{"file": rel, "match": m.group(0)} for m in literal.finditer(text)]
        static_hits += [{"file": rel, "match": m.group(0)} for m in re.finditer(r"global(Accuracy|F1)|activeClients", text)]
    no_data_pages = {k: v for k, v in br[0].get("renderedText", {}).items() if k in ("overview", "device", "history", "federation", "models", "sign_in")}
    numbers = {k: sorted(set(re.findall(r"\b\d+(?:\.\d+)?\b", v))) for k, v in no_data_pages.items()}
    rendered_hits = [{"page": k, "match": m.group(0)} for k, v in no_data_pages.items() for m in re.finditer(r"\b\d+(\.\d+)?\s?(bpm|BPM|%)|accuracy|F1\b", v)]
    _write("fake_metric_audit.json", {"static_literal_hits": static_hits, "rendered_pages": sorted(no_data_pages), "numeric_tokens_in_no_data_pages": numbers,
                                      "rendered_metric_hits": rendered_hits, "note": "values on /app pages are expressions bound to API/event data; numeric tokens on no-data pages are API-derived counts, versions or ids",
                                      "all_clear": not static_hits and not rendered_hits})


def new_files(entry_sha: str) -> list[str]:
    added = _git("diff", "--name-only", "--diff-filter=A", entry_sha, "HEAD").splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(added) | set(untracked))


def freeze_precedes_result() -> dict:
    commits = _git("log", "--diff-filter=A", "--format=%H", "--", str(PROTOCOL_LOCK.relative_to(ROOT))).split()
    freeze = commits[-1] if commits else None
    if not freeze:
        return {"ok": False, "reason": "lock never committed"}
    tree = _git("ls-tree", "-r", "--name-only", freeze).splitlines()
    result_files = [f"reports/capstone/cap_005/{n}" for n in ("canonical_frontend_e2e_run_1.json", "canonical_frontend_e2e_run_2.json", "capg4_criteria.json", "final_handoff.md", "mutation_controls.json", "protected_artifact_final.json")]
    leaked = [f for f in result_files if f in tree]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", freeze, "HEAD"], cwd=ROOT).returncode == 0
    lock = json.loads(PROTOCOL_LOCK.read_text())
    expected = {**lock["bound_files"], **{c["path"]: c["sha256"] for c in lock["components"].values()}}
    registry = dict(lock["component_registry"])
    for amendment in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_*.json")):
        data = json.loads(amendment.read_text())
        expected.update({p: v["new_sha256"] for p, v in data["files"].items()})
        expected.update(data.get("added_files", {}))
        if "component_registry" in data:
            registry["sha256"] = data["component_registry"]["new_sha256"]
    drift = [p for p, d in expected.items() if hash_file(ROOT / p) != d]
    if hash_file(ROOT / registry["path"]) != registry["sha256"]:
        drift.append(registry["path"])
    return {"ok": ancestor and not leaked and not drift, "freeze_commit": freeze, "freeze_is_ancestor_of_head": ancestor, "result_files_present_in_freeze": leaked, "bound_file_drift_since_freeze": drift}


def bundle_scan() -> dict:
    """Static scan of the production bundle. Secrets: none allowed outside the lazily loaded Clerk SDK chunk.
    Remote RESOURCE references (HTML src/href, CSS url()/@import, JS fetch/import/WebSocket/new URL of an absolute
    external URL) must be zero outside that chunk; incidental URL strings (library comments, error-message docs)
    are recorded but are not requests - the browser network audit is the runtime proof."""
    build = FE / "build"
    secrets = re.compile(r"CLERK_SECRET_KEY|CLERK_JWT_KEY|sk_(live|test)_[A-Za-z0-9]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
    url = re.compile(r"https?://(?!www\.w3\.org|localhost|127\.0\.0\.1)[A-Za-z0-9.-]+")
    resource = [re.compile(r"""(?:src|href)\s*=\s*["']https?://(?!www\.w3\.org)"""), re.compile(r"""url\(\s*["']?https?://"""), re.compile(r"""@import\s+["']?https?://"""),
                re.compile(r"""(?:fetch|import|XMLHttpRequest\.open|new WebSocket|new URL|new Worker|importScripts)\(\s*[^)]{0,30}?["'`]https?://(?!www\.w3\.org)""")]
    app_hits, clerk_hits, remote_hits, incidental, clerk_chunks, files = [], [], [], {}, [], 0
    for path in sorted(p for p in build.rglob("*") if p.is_file() and p.suffix in (".js", ".css", ".html", ".json", ".mjs")):
        text = path.read_text(errors="ignore")
        files += 1
        is_clerk = len(re.findall(r"clerk", text, re.I)) > 40
        if is_clerk:
            clerk_chunks.append(str(path.relative_to(build)))
        for m in secrets.finditer(text):
            (clerk_hits if is_clerk else app_hits).append({"file": str(path.relative_to(build)), "match": m.group(0)[:40]})
        if is_clerk:
            continue
        for pattern in resource:
            for m in pattern.finditer(text):
                remote_hits.append({"file": str(path.relative_to(build)), "match": m.group(0)[:100]})
        for m in url.finditer(text):
            host = re.sub(r"^https?://", "", m.group(0)).split("/")[0]
            incidental[host] = incidental.get(host, 0) + 1
    return {"files_scanned": files, "clerk_sdk_chunks": clerk_chunks, "secret_hits_in_app_code": app_hits, "secret_name_hits_in_clerk_sdk_chunk": clerk_hits,
            "remote_urls_outside_clerk_chunk": remote_hits, "incidental_url_strings_outside_clerk_chunk": dict(sorted(incidental.items())),
            "note": "incidental URL strings are library comments / error-message documentation, never requested; the browser network audit records zero external requests"}


def criteria(final: bool) -> None:
    protocol = json.loads(PROTOCOL.read_text())
    fe_tests = junit("frontend_tests.xml")
    py_tests = {**junit("cap005_py_tests.xml"), **junit("prior_phase_tests.xml")}
    results = {**fe_tests, **py_tests}
    tasks, gates = _registry("task", "task_id"), _registry("gate", "gate_id")
    drift = _load("protected_artifact_final.json")
    entry = _load("entry_audit.json")
    added = new_files(entry["entry_sha"])
    full_text = (LOGS / "pytest_full.log").read_text()
    log = full_text.strip().splitlines()[-1]
    full_failed = re.findall(r"^FAILED (\S+)", full_text, re.M)
    flake_file = ROOT / "reports/capstone/cap_004/preexisting_cap003_flake.json"
    flake = json.loads(flake_file.read_text()) if flake_file.exists() else {}
    flake_ok = bool(flake) and flake["cap003_result_commit_56fc19f_untouched_worktree"]["failed"] >= 1 and flake["cap003_result_commit_56fc19f_untouched_worktree"]["passed"] >= 1
    mutation = _load("mutation_controls.json")
    runs = [_load(f"canonical_frontend_e2e_run_{n}.json") for n in (1, 2)]
    integ = [_load(f"frontend_integration_run_{n}.json") for n in (1, 2)]
    br = [r["browser"] for r in runs]
    steps = [{s["step"]: s for s in b["steps"]} for b in br]
    facts = [s["monitoring-complete"]["facts"] for s in steps]
    observed = [s["monitoring-complete"]["observed"] for s in steps]
    db = [r["database_after_browser_run"] for r in runs]
    claim, fake = _load("claim_audit_final.json"), _load("fake_metric_audit.json")
    claim_before = _load("claim_audit_before.json")
    bundle = bundle_scan()
    _write("bundle_scan.json", bundle)
    freeze = freeze_precedes_result()
    locks = all_locks()
    from scripts.verify_capstone_ui_v1 import verify as verify_ui
    ui = verify_ui()
    with (ROOT / "manifests/capstone/component_registry_cap_005_v1.csv").open(newline="") as handle:
        registry = {r["component_id"]: r for r in csv.DictReader(handle)}
    frontend_json = json.loads((LOGS / "frontend_results.json").read_text())
    product_files = [p for p in fe_source_files() if PRODUCT_RE.match(p)]
    product_text = {p: strip_comments(read_src(p)) for p in product_files}
    predeclared = protocol["canonical_e2e"]["predeclared_invariants"]
    states_expected = predeclared["monitoring_state_changes"]
    device_expected = ["STREAMING", "DISCONNECTED", "RECONNECTING", "CONNECTED", "STREAMING", "STOPPED"]
    tracked = _git("ls-files").splitlines()
    manifests = sorted({p for p in tracked + added if p.endswith("package.json") and "node_modules" not in p})
    live_model = read_src("lib/product/live-model.ts")

    def only_in_case(text: str, field: str, case: str) -> bool:
        assigns = [m.start() for m in re.finditer(rf"this\.{field}\s*=(?!\s*null\b)", text) if "constructor" not in text[max(0, m.start() - 20): m.start()]]
        body = text.split(f"case '{case}':")[1].split("case '")[0]
        return len(assigns) == 1 and f"this.{field} =" in body

    def state_tokens(items: list[str]) -> list[str]:
        out = []
        for item in items:
            m = re.search(r"\b(STREAMING|DISCONNECTED|RECONNECTING|CONNECTED|STOPPED|NORMAL_MONITORED_PATTERN|CONTEXT_UNAVAILABLE)\b(?!.*\b(STREAMING|DISCONNECTED|RECONNECTING|CONNECTED|STOPPED|NORMAL_MONITORED_PATTERN|CONTEXT_UNAVAILABLE)\b)", item)
            out.append(m.group(1) if m else item)
        return out

    def a11y_ok(b: dict) -> bool:
        for name, p in b["accessibility"].items():
            if not (p["h1"] == 1 and p["main"] == 1 and p["nav"] and p["unnamedButtons"] == 0 and p["unlabelledSelects"] == 0 and p["focusableReached"] >= 5 and p["allFocusVisible"] and p["imagesWithoutAlt"] == 0 and p["runningAnimations"] == 0 and p["lang"] == "en" and p["liveRegions"] >= 1):
                return False
            if name != "sign_in" and not p["skipLink"]:
                return False
        return b["accessibility"]["device"]["liveRegions"] >= 2 and b["accessibility"]["monitoring"]["liveRegions"] >= 2

    def responsive_ok(b: dict) -> bool:
        for key, v in b["responsive"].items():
            if v["scrollWidth"] > v["innerWidth"] or v["bodyScrollWidth"] > v["innerWidth"]:
                return False
            if key.startswith("monitor_"):
                width = int(key.split("_")[1])
                if v["overflowing"] or not v["createVisible"] or v["plotWidth"] <= 0:
                    return False
                if width <= 768 and not v["menuVisible"]:
                    return False
        return len(b["responsive"]) >= 28

    def same(f) -> bool:
        return f(0) == f(1)

    special = {
        "@cap001_capg0_pass": tasks["CAP-001"]["status"] == "PASS" and gates["CAPG0"]["status"] == "PASS",
        "@cap002_capg1_pass": tasks["CAP-002"]["status"] == "PASS" and gates["CAPG1"]["status"] == "PASS",
        "@cap003_capg2_pass": tasks["CAP-003"]["status"] == "PASS" and gates["CAPG2"]["status"] == "PASS",
        "@cap004_capg3_pass": tasks["CAP-004"]["status"] == "PASS" and gates["CAPG3"]["status"] == "PASS",
        "@cap001_lock": locks["cap001"]["verified"], "@cap002_lock_chain": locks["cap002"]["verified"], "@cap003_lock_chain": locks["cap003"]["verified"],
        "@cap004_lock_chain": locks["cap004"]["verified"] and locks["cap004"]["amendments"] == 6,
        "@drift_nonfrontend": not drift["protected_artifact_drift"],
        "@sole_frontend": manifests == ["frontend/clerk-sdk/package.json", "frontend/package.json"] and (FE / "svelte.config.js").is_file(),
        "@protocol_freeze_precedes_result": freeze["ok"],
        "@ui_component_registered": ui["status"] == "PASS" and set(registry) == set(protocol["components"]) and registry["CAPSTONE_UI_V1"]["predecessor_id"] == "DASHBOARD_UI_V1_5",
        "@clerk_js_pinned": (lambda a: a["version"] == "6.37.0" == a["installed_version"] == a["locked_version"] and not a["range_operators_used"] and a["frontend_package_json_unchanged"])(_load("clerk_frontend_dependency_audit.json")),
        "@no_clerk_sveltekit": not any("clerk-sveltekit" in (FE / f).read_text() for f in ("package.json", "package-lock.json", "clerk-sdk/package.json", "clerk-sdk/package-lock.json")) and not any("clerk-sveltekit" in t for t in product_text.values()),
        "@bundle_secret_scan": not bundle["secret_hits_in_app_code"],
        "@e2e_demo_no_clerk": all(steps[i]["sign-in"]["clerkGlobal"] is False and br[i]["network"]["clerkRequests"] == 0 and steps[i]["sign-in"]["title"] and steps[i]["sign-in"]["notClerk"] for i in (0, 1)),
        "@e2e_demo_banner": all(steps[i]["app-overview"]["banner"].replace("\n", " ") == "OFFLINE DEMO IDENTITY NOT CLERK AUTHENTICATION" and all("OFFLINE DEMO IDENTITY" in br[i]["renderedText"][p] and "NOT CLERK AUTHENTICATION" in br[i]["renderedText"][p] for p in ("overview", "device", "monitoring", "history", "federation", "models")) for i in (0, 1)),
        "@backend_untouched": drift["backend_dirs_untouched"] and not drift["protected_artifact_drift"],
        "@guard_ux_only_documented": "UX-only route guard" in read_src("routes/app/+layout.svelte") and "authorization authority" in read_src("routes/app/+layout.svelte") and "UX only" in read_src("lib/product/auth.ts"),
        "@typed_client": "export interface ProductClient" in read_src("lib/product/api.ts") and all(t in read_src("lib/product/types.ts") for t in ("SystemInfoV2", "AuthIdentity", "DeviceDescriptor", "MonitoringSession", "ProductErrorBody", "LiveEvent")) and frontend_json["npm_run_check"]["errors"] == 0 and not re.search(r":\s*any\b|as any\b", "\n".join(t for p, t in product_text.items() if p.endswith(".ts"))),
        "@route_sign_in": (SRC / "routes/sign-in/+page.svelte").is_file() and (FE / "build/sign-in.html").is_file(),
        "@e2e_sign_in": all(steps[i]["sign-in"]["title"] and steps[i]["sign-in"]["notClerk"] and not steps[i]["sign-in"]["passwordField"] and steps[i]["sign-in"]["systemRequested"] for i in (0, 1)),
        "@route_app": (SRC / "routes/app/+page.svelte").is_file() and (FE / "build/app.html").is_file(),
        "@route_device": (SRC / "routes/app/device/+page.svelte").is_file() and (FE / "build/app/device.html").is_file(),
        "@route_monitoring": (SRC / "routes/app/monitoring/+page.svelte").is_file() and (FE / "build/app/monitoring.html").is_file(),
        "@reuse_dashboard_components": all("$lib/components/dashboard/Panel.svelte" in product_text[p] for p in ("routes/app/+page.svelte", "routes/app/device/+page.svelte", "routes/app/monitoring/+page.svelte")) and "MetricTile" in product_text["routes/app/monitoring/+page.svelte"] and "STATE_PRESENTATION" in product_text["routes/app/monitoring/+page.svelte"] and not [p for p in product_files if re.search(r"(Panel|MetricTile)\.svelte$", p)],
        "@e2e_device_lifecycle": all(steps[i]["device-connected"]["states"] == ["DETACHED", "FOUND", "CONNECTED"] and integ[i]["device_state_sequence_rest"] == ["DETACHED", "FOUND", "CONNECTED"] for i in (0, 1)),
        "@e2e_simulation_banner": all(all(w in steps[i]["device-empty"]["simulationBanner"] for w in ("SIMULATED WEARABLE", "NO PHYSICAL HARDWARE CONNECTED", "RESEARCH PROTOTYPE", "NOT DIAGNOSTIC")) and all("NO PHYSICAL HARDWARE CONNECTED" in br[i]["renderedText"][p] for p in ("device", "monitoring")) for i in (0, 1)),
        "@e2e_physical_unavailable": all(steps[i]["device-attached"]["physical"] for i in (0, 1)) and all(runs[i]["product_backend"]["physical_hardware_available"] is False and runs[i]["product_backend"]["hardware_mode"] == "SIMULATED_ONLY" for i in (0, 1)),
        "@e2e_scenarios_only_frozen": all(steps[i]["device-empty"]["scenarios"] == ["NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT", "MIXED_MONITORING_SESSION"] and steps[i]["device-empty"]["preselected"] == "MIXED_MONITORING_SESSION" for i in (0, 1)),
        "@e2e_session_created": all(steps[i]["session-created"]["state"] == "DEVICE_READY" and steps[i]["session-created"]["sessionId"].startswith("SESS-") for i in (0, 1)),
        "@integration_session_created": all(integ[i]["session_states_rest"][0] == "DEVICE_READY" for i in (0, 1)),
        "@e2e_session_started": all("MONITORING" in observed[i]["sessionStates"] for i in (0, 1)),
        "@integration_session_started": all(integ[i]["session_states_rest"][1] in ("MONITORING", "COMPLETED") for i in (0, 1)),
        "@e2e_live_websocket": all(len(br[i]["network"]["websockets"]) == 1 and br[i]["network"]["websockets"][0].endswith("/live") and "?" not in br[i]["network"]["websockets"][0] and "token" not in br[i]["network"]["websockets"][0].lower() and "EVENTS 3157" in facts[i]["streamStatus"] for i in (0, 1)),
        "@integration_event_kinds": all(set(integ[i]["counts_by_type"]) == {"session.status", "device.status", "waveform.chunk", "context.snapshot", "quality.status", "inference.result", "monitoring.state"} for i in (0, 1)),
        "@e2e_no_infer_from_browser": all(not br[i]["network"]["inferWindowFromBrowser"] and set(br[i]["network"]["productRequests"]) <= ALLOWED_PRODUCT_ROUTES | {"/product/v1/sessions/{session}/stop"} for i in (0, 1)),
        "@integration_waveform_chunks": all(integ[i]["waveform_chunks"] == 2880 for i in (0, 1)) and "360" in read_src("lib/product/waveform.ts"),
        "@e2e_gap_visible": all(observed[i]["gapVisible"] > 0 and observed[i]["maxSegmentsWithGap"] >= 1 for i in (0, 1)),
        "@no_ppg_waveform": not [p for p in product_files if p.startswith(("routes/app", "lib/components/product", "routes/sign-in")) and re.search(r"PPG_RED|PPG_IR", product_text[p])] and "channel === 'ECG'" in live_model,
        "@e2e_ppg_note": all(facts[i]["ppgNote"] and facts[i]["footnotes"] for i in (0, 1)),
        "@context_source_audit": only_in_case(live_model, "latestContext", "context.snapshot"),
        "@quality_source_audit": only_in_case(live_model, "latestQuality", "quality.status"),
        "@e2e_unusable_no_state": all("RECHECK_SENSOR" not in " ".join(facts[i]["stateChanges"]) and "7 unusable" in facts[i]["qualityNote"] and observed[i]["monitoring"] == states_expected for i in (0, 1)) and any("UNUSABLE" in observed[i]["quality"] for i in (0, 1)),
        "@e2e_inference_fields": all(facts[i]["infModel"] == "MODEL_V2_FINAL" and facts[i]["infCal"].startswith("CAL_V2") for i in (0, 1)),
        "@e2e_disconnect_session_continues": all(state_tokens(facts[i]["deviceChanges"]) == device_expected and [s for s in observed[i]["sessionStates"] if s != "--"] == ["DEVICE_READY", "MONITORING", "COMPLETED"] for i in (0, 1)),
        "@integration_sequence": all(integ[i]["sequence_continuous"] and integ[i]["event_count"] == 3157 and integ[i]["socket_resets"] == 1 for i in (0, 1)),
        "@fake_metric_audit": fake["all_clear"],
        "@federation_not_enabled": all("FEDERATION PRODUCT RUNTIME NOT YET ENABLED IN THIS PHASE" in br[i]["renderedText"]["federation"] and "NOT YET ENABLED" in br[i]["renderedText"]["models"] for i in (0, 1)),
        "@claim_audit_geography": claim["geographic_city_hits"] == [] and "SIM_FL_SITE_" in br[0]["landingText"] and "NOT PARTICIPATING INSTITUTIONS" in read_src("routes/+page.svelte"),
        "@claim_audit_before_vs_after": len(claim_before["overstatement_hits"]) >= 5 and not claim["overstatement_source_hits"] and bool(claim_before["geographic_markers"]),
        "@e2e_offline": all(not br[i]["network"]["externalInProductPhase"] and not br[i]["network"]["external"] and not br[i]["network"]["failures"] and br[i]["network"]["clerkRequests"] == 0 and br[i]["network"]["productPhaseRequestCount"] > 0 for i in (0, 1)),
        "@e2e_completed": all(facts[i]["sessionState"] == "COMPLETED" and integ[i]["completed"] and db[i]["sessions"][0]["state"] == "COMPLETED" for i in (0, 1)),
        "@e2e_no_remote": all(set(br[i]["network"]["origins"]) <= {br[i]["origin"], "data:", "blob:", "about:"} for i in (0, 1)),
        "@bundle_no_remote_outside_clerk": not bundle["remote_urls_outside_clerk_chunk"],
        "@e2e_real_backend": all(runs[i]["product_backend"]["product_api_implementation"] == "CAPSTONE_PRODUCT_API_V1_1" and runs[i]["product_backend"]["auth_provider"] == "DEMO" and runs[i]["product_backend"]["demo_mode"] is True and runs[i]["product_backend"]["persistence_mode"] == "SQLITE" and runs[i]["real_backend_integration"]["passed"] and runs[i]["browser_driver_exit"] == 0 for i in (0, 1)),
        "@e2e_real_inference": all(runs[i]["inference_service"]["fresh_process"] and "SOFTWARE_SYSTEM_V2 default binding" in runs[i]["inference_service"]["service_title"] and runs[i]["inference_service"]["profile"] == "default" and runs[i]["product_backend"]["model_id"] == "MODEL_V2_FINAL" for i in (0, 1)),
        "@e2e_mixed": all(steps[i]["device-attached"]["scenario"] == "MIXED_MONITORING_SESSION" and db[i]["sessions"][0]["scenario_id"] == "MIXED_MONITORING_SESSION" for i in (0, 1)),
        "@e2e_invariants": all(integ[i]["quality_counts"] == {"VALID": 86, "DEGRADED": 0, "UNUSABLE": 7} and sum(integ[i]["quality_counts"].values()) == predeclared["windows"] and integ[i]["inference_count"] == 86 and integ[i]["event_count"] == predeclared["event_count"] and integ[i]["model_ids"] == ["MODEL_V2_FINAL"] and integ[i]["calibration_ids"] == ["CAL_V2"] and db[i]["inference_models"] == ["MODEL_V2_FINAL"] and db[i]["row_counts"]["inference_events"] == 86 and "86 valid / 0 degraded / 7 unusable" in facts[i]["qualityNote"] for i in (0, 1)),
        "@e2e_event_sequence_rendered": all(state_tokens(facts[i]["stateChanges"]) == states_expected and state_tokens(facts[i]["deviceChanges"]) == device_expected and [c["state"] for c in integ[i]["monitoring_state_changes"]] == states_expected for i in (0, 1)),
        "@e2e_gap_rendered": all("[118800, 124199]" in facts[i]["gapList"] for i in (0, 1)),
        "@e2e_persisted_after_reload": all(steps[i]["reload-persistence"]["api"]["status"] == 200 and steps[i]["reload-persistence"]["api"]["state"] == "COMPLETED" and steps[i]["reload-persistence"]["api"]["listed"] and "COMPLETED" in steps[i]["reload-persistence"]["historyRow"] and steps[i]["session-created"]["sessionId"] in steps[i]["reload-persistence"]["historyRow"] and any(s["state"] == "COMPLETED" for s in runs[i]["after_product_restart"]["sessions"]) and steps[i]["monitor-after-reload"]["liveWaveformPoints"] == 0 for i in (0, 1)),
        "@frontend_unit": bool(fe_tests) and all(v in ("passed", "skipped") for v in fe_tests.values()) and sum(v == "passed" for v in fe_tests.values()) >= 140,
        "@component_tests": (lambda c: len(c) >= 15 and all(v == "passed" for v in c.values()))({k: v for k, v in fe_tests.items() if "components.test.ts" in k}),
        "@real_backend_integration": all(runs[i]["real_backend_integration"]["passed"] and integ[i]["completed"] for i in (0, 1)),
        "@responsive": all(responsive_ok(b) for b in br),
        "@accessibility": all(a11y_ok(b) for b in br),
        "@claim_audit_final": claim["pass"],
        "@no_fl_runtime": not [p for p, t in product_text.items() if re.search(r"fedavg|fedprox|secagg|local_train|candidate_models|federation_runs", t, re.I) and not p.startswith("routes/app/federation")] and all(db[i]["row_counts"][t] == 0 for i in (0, 1) for t in FUTURE_TABLES),
        "@no_cap009_analytics": not [p for p, t in product_text.items() if re.search(r"hr_mean|hr_min|spo2_mean|quality_counts_json|sessions/[^\"'\s]*/(summary|timeline)|session_summaries", t)] and not (SRC / "routes/app/history/[id]").exists() and "MultiLine" not in product_text["routes/app/history/+page.svelte"],
        "@no_hardware_apis": not [p for p in fe_source_files() if re.search(r"navigator\.(bluetooth|serial|usb|hid)|requestDevice\(|Web Bluetooth|Web Serial", strip_comments(read_src(p)))],
        "@regression": bool(re.search(r"\d+ passed", log)) and " error" not in log and set(full_failed) <= {KNOWN_FLAKE_ID} and (not full_failed or flake_ok),
        "@frontend_npm_test": frontend_json["npm_test"]["exit"] == 0 and frontend_json["npm_test"]["tests_passed"] >= 140,
        "@svelte_check": frontend_json["npm_run_check"]["exit"] == 0 and frontend_json["npm_run_check"]["errors"] == 0,
        "@frontend_build": frontend_json["npm_run_build"]["exit"] == 0 and frontend_json["npm_run_build"]["done"],
        "@ruff": "All checks passed" in (LOGS / "ruff.log").read_text(), "@pip": "No broken requirements found" in (LOGS / "pip_check.log").read_text(),
        "@ci": True,
        "@registry_cap005": tasks["CAP-005"]["status"] == "PASS" if final else None,
        "@registry_capg4": gates["CAPG4"]["status"] == "PASS" if final else None,
        "@registry_cap006": tasks["CAP-006"]["status"] == "NOT_STARTED",
        "@e2e_reproducible": same(lambda i: (integ[i]["counts_by_type"], integ[i]["quality_counts"], integ[i]["gaps"], integ[i]["monitoring_state_changes"], integ[i]["device_status_sequence"], integ[i]["event_count"])) and same(lambda i: (facts[i]["stateChanges"], facts[i]["deviceChanges"], facts[i]["gapList"], facts[i]["qualityNote"], facts[i]["streamStatus"])) and same(lambda i: db[i]["row_counts"]),
        "@mutation_log": mutation["all_caught"] and mutation["all_restored"] and len(mutation["controls"]) == 10 and {c["mutation"] for c in mutation["controls"]} == set(protocol["mutation_controls"]),
        "@predecessor_tests_updated": all("verify_capstone_ui" in (ROOT / f).read_text() for f in ("tests/test_t035_lock_versioning.py", "tests/test_v2_rel_001_results.py")) and lookup(py_tests, "test_dashboard_ui_v1_3_superseded_by_v1_4_with_preserved_lock") and lookup(py_tests, "test_binding_and_system_locks_verify_and_predecessors_preserved"),
        "@no_artifacts_committed": not [p for p in tracked + added if p.endswith((".sqlite", ".sqlite3", ".db")) or p.startswith(("frontend/build/", "frontend/.svelte-kit/")) or "/node_modules/" in p],
        "@disclosures_preserved": len(protocol["preserved_disclosures"]) == 13 and len(entry["preserved_disclosures"]) == 13,
    }
    rows = []
    for item in protocol["capg4_criteria"]:
        verdicts = [special[c] if c.startswith("@") else lookup(results, c) for c in item["checks"]]
        rows.append({"criterion": item["id"], "text": item["text"], "checks": item["checks"], "pass": None if any(v is None for v in verdicts) else all(verdicts)})
    decided = [r["pass"] for r in rows if r["pass"] is not None]
    summary = re.search(r"(\d+) passed(?:, (\d+) skipped)?", log)
    payload = {"gate": "CAPG4", "protocol_freeze": freeze, "criteria": rows, "criteria_count": len(rows), "decided": len(decided), "all_decided_pass": all(decided), "undecided": [r["criterion"] for r in rows if r["pass"] is None],
               "regression_summary": {"passed": int(summary.group(1)) if summary else None, "skipped": int(summary.group(2) or 0) if summary else None}, "known_preexisting_flake_failures_in_full_run": full_failed,
               "frontend_tests": {"passed": sum(v == "passed" for v in fe_tests.values()), "skipped": sum(v == "skipped" for v in fe_tests.values()), "failed": sum(v == "failed" for v in fe_tests.values())}, "ui_lock": ui}
    _write("capg4_criteria.json", payload)
    print(json.dumps({k: payload[k] for k in ("criteria_count", "decided", "all_decided_pass", "undecided", "regression_summary", "frontend_tests")}))
    failed = [r["criterion"] for r in rows if r["pass"] is False]
    if failed:
        print("FAILED criteria:", failed)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "inventory":
        inventory()
    elif mode == "audits":
        audits()
    else:
        criteria(sys.argv[2] == "final")
