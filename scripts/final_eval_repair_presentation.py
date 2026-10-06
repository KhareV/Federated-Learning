# ruff: noqa: E501
"""FINAL_EVALUATOR_PRESENTATION_V1: fail-closed current-presentation guard. Pure functions over a repository ROOT (real tree or a disposable shadow copy).
Validates the evaluator-facing application against the machine-readable truth contract (configs/final_eval_repair/evaluator_truth_v1.json), not against remembered strings."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts import final_eval_repair_lib as lib

ROOT = lib.ROOT
SRC = "frontend/src"
CURRENT_CLASSES = {"CURRENT_PUBLIC", "CURRENT_PRODUCT", "CURRENT_RESEARCH", "CURRENT_COMPATIBILITY", "INTERNAL_DYNAMIC"}
NEGATORS = re.compile(r"\b(not|no|never|nor|without|neither|isn't|cannot|n't|rather than|instead of|unverified|unavailable|absent)\b", re.I)
# (id, pattern): a hit counts only when no negator appears in the 110 characters before it (or in the same short clause after it for 'deployed')
CLAIMS: tuple[tuple[str, str], ...] = (
    ("hospital_or_institution", r"\b(hospitals?|institutions?)\b"), ("production", r"\bproduction[- ](system|secure|security|grade|ready|identity|authentication)\b"),
    ("personalized_fl", r"\bpersonali[sz]ed (federated|FL|model|learning)\b|\bpersonal model\b|\bpatient-specific\b|\buser-trained\b|\bself-learning\b|\bmy ECG trains\b|\bmy monitoring data trains\b|\b(your|the user's|my) (ECG|physiology|monitoring data|sessions?) (trains|is used to train|feeds)\b(?! nothing)"),
    ("candidate_deployed", r"\b(candidate|federated model|global model)\b[^.<]{0,40}\bdeployed\b"), ("dp_or_anonymity", r"\bdifferential privacy\b|\banonymi[sz]ed?\b|\banonymity\b|(?<!['\"])\banonymous\b(?!['\"])"),
    ("diagnostic_or_clinical", r"\b(clinical|medical)[- ](grade|validation|validated|use|deployment|decision|system|certified)\b|\bdiagnostic (tool|system|device|use|result)s?\b|\bis (a )?diagnostic\b|\bmedical device\b"), ("physical_hardware", r"\b(physical wearable|real hardware|physical hardware)\b[^.<]{0,30}\b(connected|validated|verified)\b"),
)
STALE = re.compile(r"not yet enabled|NOT ENABLED IN THIS PHASE|FEDERATION RUNTIME / NOT|federation (product )?runtime is not|federation is (disabled|deferred)|intentionally deferred|Federated learning is deferred", re.I)
STALE_ALLOWED = ("FEDERATION BACKEND NOT ENABLED",)       # shown only when the backend itself reports no federation runtime (truthful conditional)


def truth(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / "configs/final_eval_repair/evaluator_truth_v1.json").read_text())["facts"]


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def strip_comments(text: str) -> str:
    text = re.sub(r"<!--[\s\S]*?-->", "", re.sub(r"/\*[\s\S]*?\*/", "", text))
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


CLAUSE_BREAK = re.compile(r"[.;!?]\s|\n|</li>|<li>")


def unnegated_hits(text: str) -> list[dict[str, str]]:
    """Claim patterns whose OWN clause (text since the previous sentence/line/bullet break, <=110 chars, plus the match) carries no negator."""
    hits = []
    for cid, pat in CLAIMS:
        for m in re.finditer(pat, text, re.I):
            window = text[max(0, m.start() - 110):m.start()]
            cut = list(CLAUSE_BREAK.finditer(window))
            clause = (window[cut[-1].end():] if cut else window) + text[m.start():m.end()]
            after = text[m.end():m.end() + 25] if cid == "candidate_deployed" else ""
            if not NEGATORS.search(clause) and not NEGATORS.search(after) and "production_deployed" not in text[max(0, m.start() - 20):m.end() + 20]:
                hits.append({"claim": cid, "text": text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")})
    return hits


def policy(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / "configs/final_eval_repair/legacy_route_policy_v1.json").read_text())


def ts_redirects(root: Path = ROOT) -> dict[str, str]:
    text = read(root, f"{SRC}/lib/product/route-policy.ts")
    body = text[text.index("LEGACY_REDIRECTS"):text.index("};")]
    return dict(re.findall(r"'(/[^']*)':\s*'(/[^']*)'", body))


def current_files(root: Path = ROOT) -> list[str]:
    """Frontend files reachable (static import graph) from CURRENT/retained route pages and the root layout, comments excluded at scan time."""
    pol = policy(root)
    seeds = [r["file"] for r in pol["routes"] if r["class"] in CURRENT_CLASSES | {"LEGACY_RETAINED_RESEARCH_TOOL"}] + [f"{SRC}/routes/+layout.svelte"]
    seen: set[str] = set()
    stack = [s for s in seeds if (root / s).exists()]
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        text = read(root, f)
        for spec in re.findall(r"from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]", text) and [a or b for a, b in re.findall(r"from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]", text)]:
            base = None
            if spec.startswith("$lib/"):
                base = root / SRC / "lib" / spec[5:]
            elif spec.startswith("."):
                base = (root / f).parent / spec
            if base is None:
                continue
            for cand in (base, Path(str(base) + ".ts"), Path(str(base) + ".svelte"), base / "index.ts"):
                if cand.is_file():
                    rel = cand.resolve().relative_to(root.resolve()).as_posix()
                    if rel not in seen:
                        stack.append(rel)
                    break
    return sorted(seen)


def current_text(root: Path = ROOT) -> dict[str, str]:
    return {f: strip_comments(read(root, f)) for f in current_files(root)}


# ---------------------------------------------------------------- checks (each returns bool; details via *_detail)
def about_ok(root: Path = ROOT) -> dict[str, Any]:
    t = strip_comments(read(root, f"{SRC}/routes/app/about/+page.svelte"))
    need = [r"research\s+prototype", r"not diagnostic", r"not a medical device", r"SIMULATED ONLY", r"No physical wearable", r"MODEL_V2_FINAL", r"SOFTWARE_SYSTEM_V2", r"simulated source ECG", r"PPG waveform is unavailable", r"engineering federation runtime is enabled", r"eight logical, synthetic",
            r"one demonstration machine", r"not hospitals or institutions", r"MY EDGE CLIENT", r"SIM_FL_SITE_00", r"does not train any model", r"no personal or personalized model", r"sandbox", r"never automatically deployed", r"does not replace the released MODEL_V2_FINAL", r"research outputs"]
    missing = [n for n in need if not re.search(n, re.sub(r"<[^>]+>", "", t), re.I)]
    stale = [m.group(0) for m in STALE.finditer(t)]
    return {"ok": not missing and not stale and not unnegated_hits(re.sub(r"<[^>]+>", "", t)), "missing": missing, "stale": stale, "claims": unnegated_hits(re.sub(r"<[^>]+>", "", t))}


def landing_ok(root: Path = ROOT) -> dict[str, Any]:
    raw = read(root, f"{SRC}/routes/+page.svelte")
    t = strip_comments(raw)
    plain = re.sub(r"<[^>]+>", " ", t)
    need = [r"FEDERATION RUNTIME / ENGINEERING ENABLED", r"engineering federation runtime is enabled", r"eight logical synthetic clients", r"one demonstration machine", r"genuine local optimization", r"sandbox", r"never replaces the released MODEL_V2_FINAL", r"not hospitals or institutions",
            r"not personalized federated learning", r"not differential privacy or anonymity", r"not diagnostic"]
    missing = [n for n in need if not re.search(n, plain, re.I)]
    stale = [m.group(0) for m in STALE.finditer(plain)]
    overreach = [x for x in ("MY EDGE CLIENT", "AUTHENTICATED OWNER") if x in plain]
    font = [x for x in ("Lastoria", "<Signature") if x in raw]
    return {"ok": not (missing or stale or overreach or font) and not unnegated_hits(plain), "missing": missing, "stale": stale, "owner_binding_overreach": overreach, "font_refs": font, "claims": unnegated_hits(plain)}


def landing_claims_ok(root: Path = ROOT) -> bool:
    return not unnegated_hits(re.sub(r"<[^>]+>", " ", strip_comments(read(root, f"{SRC}/routes/+page.svelte"))))


def stale_feature_status(root: Path = ROOT) -> dict[str, Any]:
    hits = []
    for f, t in current_text(root).items():
        for m in STALE.finditer(t):
            ctx = t[max(0, m.start() - 20):m.end() + 20]
            if not any(a.lower() in ctx.lower() for a in STALE_ALLOWED):
                hits.append({"file": f, "text": m.group(0)})
    return {"ok": not hits, "hits": hits, "files_scanned": len(current_files(root))}


GUARD_WORD_LISTS = ("frontend/src/lib/dashboard/state-presentation.ts",)   # a banned-words list (the guard itself), not a claim


def claims_ok(root: Path = ROOT) -> dict[str, Any]:
    hits = []
    for f, t in current_text(root).items():
        if f in GUARD_WORD_LISTS:
            continue
        plain = re.sub(r"<[^>]+>", " ", t) if f.endswith(".svelte") else t
        for h in unnegated_hits(plain):
            hits.append({"file": f, **h})
    return {"ok": not hits, "hits": hits}


def routes_ok(root: Path = ROOT) -> dict[str, Any]:
    pol = policy(root)
    found = {r["pattern"]: r for r in lib.discover_routes(root)}
    listed = {r["pattern"]: r for r in pol["routes"]}
    classes = set(pol["classes"])
    unclassified = sorted(set(found) - set(listed))
    stale_entries = sorted(set(listed) - set(found))
    bad_class = sorted(p for p, r in listed.items() if r["class"] not in classes)
    redirects = {p: r["redirect_to"] for p, r in listed.items() if r["class"] == "LEGACY_REDIRECT"}
    current = {p for p, r in listed.items() if r["class"] in CURRENT_CLASSES | {"LEGACY_RETAINED_RESEARCH_TOOL", "CATCH_ALL"}}
    loops = sorted(p for p, to in redirects.items() if to == p or to in redirects)
    external = sorted(p for p, to in redirects.items() if not re.fullmatch(r"/app(/[a-z0-9\-/]*)?", to) or "//" in to)
    dangling = sorted(p for p, to in redirects.items() if to not in current)
    ts = ts_redirects(root)
    mirror = ts == redirects
    layout = read(root, f"{SRC}/routes/+layout.ts")
    wired = "legacyRedirect" in layout and "redirect(307" in layout
    retired_current = sorted(p for p in current if p in ts)
    known = {"/fl/overview": "/app/federation", "/fl/personal-models": "/app/federation", "/ai/insights": "/app/research/ml", "/overview": "/app"}
    known_bad = sorted(p for p, to in known.items() if redirects.get(p) != to or ts.get(p) != to)
    monitoring = listed.get("/monitoring", {}).get("class") == "LEGACY_RETAINED_RESEARCH_TOOL" and "monitoring_decision" in pol and "research-tool-banner" in read(root, f"{SRC}/routes/+layout.svelte")
    counts = {"routes": len(found), "legacy_redirect": len(redirects), "retained": sum(1 for r in listed.values() if r["class"] == "LEGACY_RETAINED_RESEARCH_TOOL"), "unclassified": len(unclassified)}
    return {"ok": not (unclassified or stale_entries or bad_class or loops or external or dangling or retired_current or known_bad) and mirror and wired and monitoring, "unclassified": unclassified, "stale_entries": stale_entries, "bad_class": bad_class, "loops": loops, "external": external, "dangling": dangling,
            "mirror_ts_equals_json": mirror, "layout_wired": wired, "retired_current": retired_current, "known_bad_unclosed": known_bad, "monitoring_decision_ok": monitoring, "counts": counts,
            "checks": {"routes_all_classified": not (unclassified or stale_entries or bad_class), "redirect_policy_safe": not (loops or external or dangling) and mirror and wired, "current_routes_not_retired": not retired_current, "known_bad_routes_redirect": not known_bad, "monitoring_decision_documented": monitoring}}


def runbook_ok(root: Path = ROOT) -> dict[str, Any]:
    p = root / "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1_1.md"
    if not p.exists():
        return {"ok": False, "missing": ["runbook_v1_1_absent"]}
    t = p.read_text(encoding="utf-8")
    need = [r"MY EDGE CLIENT", r"SIM_FL_SITE_00", r"SYNTHETIC PEER", r"CONNECTED CLERK \+ LIVE_RUN", r"presentation role only", r"synthetic engineering training data", r"not\*\* the authenticated user's physiology", r"never feed federation", r"no personal model", r"not personalized federated learning", r"not persisted",
            r"OFFLINE DEMO \(DemoAuth\)", r"REPLAY", r"global clients view", r"show \*\*no owner binding\*\*", r"8 clients, 3 rounds, 24 updates", r"sandbox", r"supersedes", r"exactly as in the offline mode"]
    missing = [n for n in need if not re.search(n, t, re.I)]
    # the old sentence may appear ONLY inside the correction note
    old = [m.start() for m in re.finditer(r"behave exactly as in the offline mode", t)]
    stale = [i for i in old if "corrected in section 4a" not in t[max(0, i - 300):i + 300]]
    hits = unnegated_hits(t)
    return {"ok": not missing and not stale and not [h for h in hits if h["claim"] in ("personalized_fl", "candidate_deployed", "dp_or_anonymity")], "missing": missing, "stale_sentence_positions": stale, "claims": hits}


def truth_contract_ok(root: Path = ROOT) -> dict[str, Any]:
    f = truth(root)
    api = read(root, "api/product_app_v1_3.py")
    part = read(root, f"{SRC}/lib/product/federation/participation.ts")
    checks = {"federation_runtime_backend": f["federation_runtime"] == "ENABLED_ENGINEERING" and 'federation_runtime="ENABLED_ENGINEERING"' in api, "hardware_backend": f["hardware_mode"] == "SIMULATED_ONLY" and "SIMULATED_ONLY" in api, "model": f["released_model"] == "MODEL_V2_FINAL" and f["calibration"] == "CAL_V2" and lib_ufl().load_baseline(root)["released_monitoring_model"] == "MODEL_V2_FINAL" and lib_ufl().load_baseline(root)["calibration"] == "CAL_V2",
              "owner_binding": f["owner_binding_client"] in part and f["owner_binding_auth"] == "CLERK" and f["owner_binding_run_type"] == "LIVE_RUN" and "authProvider === 'CLERK'" in part and "runType === 'LIVE_RUN'" in part,
              "flags_false": not any(f[k] for k in ("diagnostic", "medical_device", "physical_hardware_connected", "demo_owner_binding", "replay_owner_binding", "global_clients_owner_binding", "monitoring_data_used_for_fl", "personalized_fl", "personal_model", "candidate_deployed")),
              "candidate_digest": f["canonical_candidate_digest"] == lib_ufl().CANONICAL_CANDIDATE_DIGEST, "client_count": f["federation_client_count"] == 8 and len(lib_ufl().CLIENT_IDS) == 8}
    return {"ok": all(checks.values()), "checks": checks}


def lib_ufl():
    from scripts import ufl_lite_lib

    return ufl_lite_lib


def unbound_ok(root: Path = ROOT) -> dict[str, Any]:
    from scripts import ufl_lite_002_lib as plib

    return {"ok": plib.helper_audit(root)["ok"] and plib.grid_audit(root)["ok"] and plib.live_audit(root)["ok"] and plib.global_page_ok(root), "helper": plib.helper_audit(root)["ok"], "grid": plib.grid_audit(root)["ok"], "live": plib.live_audit(root)["ok"], "global_page_unbound": plib.global_page_ok(root)}


def pages_ok(root: Path = ROOT) -> dict[str, Any]:
    ml, fl, models = (read(root, f"{SRC}/routes/app/{p}/+page.svelte") for p in ("research/ml", "research/fl", "models"))
    clients, fed = read(root, f"{SRC}/routes/app/federation/clients/+page.svelte"), read(root, f"{SRC}/routes/app/federation/+page.svelte")
    checks = {"ml_distinction": "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED" in ml and re.search(r"promot", ml, re.I) is not None, "fl_engineering_separation": "V2-FL-005 is not scientific efficacy" in fl, "models_namespaces": "RELEASED SCIENTIFIC" in models and "ENGINEERING FEDERATED CANDIDATES" in models and "never used for live monitoring" in models,
              "clients_synthetic": "NOT HOSPITALS OR INSTITUTIONS" in clients and "one demonstration machine" in clients, "federation_landing_one_machine": "one demonstration machine" in fed and "SANDBOX REGISTRY ONLY" in fed}
    return {"ok": all(checks.values()), "checks": checks}


def lastoria_absent(root: Path = ROOT) -> bool:
    return not any("Lastoria" in p.read_text(errors="ignore") for p in (root / SRC).rglob("*") if (p.is_file() and p.suffix in {".svelte", ".ts", ".css", ".js"} and "components/spell/signature" not in p.as_posix()) or False) and (root / "frontend/static/LastoriaBoldRegular.otf").exists() is not False


def lastoria_unreferenced(root: Path = ROOT) -> dict[str, Any]:
    """No CURRENT/reachable frontend file requests the missing font (the unused Signature component is not reachable from any route)."""
    refs = [f for f, t in current_text(root).items() if "Lastoria" in t]
    return {"ok": not refs, "refs": refs, "signature_reachable": any("spell/signature" in f for f in current_files(root))}


def verify_all(root: Path = ROOT) -> dict[str, Any]:
    parts = {"about": about_ok(root), "landing": landing_ok(root), "stale": stale_feature_status(root), "claims": claims_ok(root), "routes": routes_ok(root), "runbook": runbook_ok(root), "truth": truth_contract_ok(root), "unbound": unbound_ok(root), "pages": pages_ok(root), "font": lastoria_unreferenced(root)}
    return {"ok": all(p["ok"] for p in parts.values()), "parts": parts}


if __name__ == "__main__":
    r = verify_all()
    print(json.dumps({"ok": r["ok"], **{k: v["ok"] for k, v in r["parts"].items()}}))
    if not r["ok"]:
        for k, v in r["parts"].items():
            if not v["ok"]:
                print(k, json.dumps(v)[:900])
        raise SystemExit(1)
