# ruff: noqa: E501
"""Pure analysis of the real-browser route crawl (sanitized observations) against LEGACY_ROUTE_POLICY_V1. Re-derived by the frozen FERG0 evaluator; recorded verdicts are never trusted."""

from __future__ import annotations

import re
from typing import Any

from scripts import final_eval_repair_presentation as pres

CURRENT = {"CURRENT_PUBLIC", "CURRENT_PRODUCT", "CURRENT_RESEARCH", "CURRENT_COMPATIBILITY"}
LEGACY_CONTENT = re.compile(r"Anomaly score|Make uncertainty legible|Personalization at the edge|Request failed with status 5\d\d|CORE / OFFLINE|DEFERRED OUT OF SCOPE|AUTH / DISABLED BY SCOPE|The baseline is personal|intentionally deferred|not part of the centralized", re.I)
SID = re.compile(r"user_[A-Za-z0-9]{12,}")
FIVEXX = lambda bad: [b for b in bad if b["status"] >= 500]  # noqa: E731
SAFE_404 = ("/this-route-does-not-exist",)


def sanitize(crawl: dict[str, Any]) -> dict[str, Any]:
    import json

    return json.loads(SID.sub("user_<REDACTED>", json.dumps(crawl)))


def expected_landing(pattern: str, row: dict[str, Any], sample: dict[str, str]) -> str:
    if row["class"] == "LEGACY_REDIRECT":
        return row["redirect_to"]
    if pattern == "/monitor":
        return "/app/monitoring"
    if pattern == "/sign-in":
        return "/app"                      # an already signed-in user is sent into the workspace
    return sample.get(pattern, pattern)


def analyze_crawl(crawl: dict[str, Any], policy: dict[str, Any], sample: dict[str, str]) -> dict[str, Any]:
    by_path = {r["route"].split("?")[0]: r for r in crawl["routes"]}
    checks: dict[str, bool] = {}
    detail: dict[str, Any] = {"per_route": []}
    covered = True
    stale_rendered, fabricated, redirect_wrong, errors, fivexx, h1_bad, overflow = [], [], [], [], [], [], []
    for row in policy["routes"]:
        pat = row["pattern"]
        if row["class"] in {"CATCH_ALL"}:
            continue
        probe = sample.get(pat, pat)
        r = by_path.get(probe.split("?")[0])
        if r is None:
            covered = False
            detail["per_route"].append({"pattern": pat, "covered": False})
            continue
        landed = r["landed"]
        want = expected_landing(pat, row, sample)
        text = r["text"]
        ok_landing = landed == want.split("?")[0]
        if not ok_landing:
            redirect_wrong.append({"route": pat, "landed": landed, "want": want})
        if pres.STALE.search(text) and "FEDERATION BACKEND NOT ENABLED" not in text:
            stale_rendered.append(pat)
        if LEGACY_CONTENT.search(text):
            fabricated.append(pat)
        if r["errors"]:
            errors.append({"route": pat, "errors": r["errors"][:2]})
        if FIVEXX(r["bad"]):
            fivexx.append(pat)
        if r["h1"] != 1 and row["class"] != "LEGACY_REDIRECT":
            h1_bad.append(pat)
        if any(w["overflow"] for w in r["widths"].values()):
            overflow.append(pat)
        detail["per_route"].append({"pattern": pat, "class": row["class"], "landed": landed, "expected": want, "title": r["title"], "h1": r["h1text"], "status": r["status"], "console_errors": len(r["errors"]), "bad_requests": r["bad"], "hosts": [h for h in r["hosts"] if h and "127.0.0.1" not in h]})
    landing = by_path.get("/", {})
    unknown = by_path.get("/this-route-does-not-exist", {})
    deep = [r for r in crawl["routes"] if r.get("after_reload")]
    checks["every_route_crawled"] = covered
    checks["legacy_and_compat_land_on_expected_current_route"] = not redirect_wrong
    checks["zero_stale_feature_status_rendered"] = not stale_rendered
    checks["zero_fabricated_or_legacy_content_rendered"] = not fabricated
    checks["zero_console_errors"] = not errors
    checks["zero_5xx"] = not fivexx
    checks["one_h1_on_every_rendered_route"] = not h1_bad
    checks["no_horizontal_overflow"] = not overflow
    checks["landing_zero_failed_or_404_requests"] = bool(landing) and landing["failed"] == [] and landing["bad"] == [] and landing["errors"] == []
    checks["unknown_route_is_a_clean_404"] = bool(unknown) and unknown["status"] == 404
    checks["deep_links_reload_clean"] = bool(deep) and all(r["after_reload"]["identityChip"] and not r["after_reload"]["visibleError"] and r["after_reload"]["h1"] == 1 and not r["after_reload"]["errors"] for r in deep)
    detail.update({"stale_rendered": stale_rendered, "fabricated_rendered": fabricated, "redirect_wrong": redirect_wrong, "console_errors": errors, "fivexx": fivexx, "h1_bad": h1_bad, "overflow": overflow, "deep_link_routes": [r["route"] for r in deep]})
    return {"checks": checks, "all_pass": all(checks.values()), "detail": detail}


FED_PAGES = ("/", "/app", "/app/about", "/app/system", "/app/federation", "/app/federation/clients", "/app/federation/live", "/app/federation/privacy", "/app/models", "/app/research/ml", "/app/research/fl")


def truth_matrix(crawl: dict[str, Any], sample: dict[str, str]) -> dict[str, Any]:
    by_path = {r["route"].split("?")[0]: r for r in crawl["routes"]}
    rows = []
    for p in FED_PAGES:
        r = by_path.get(sample.get(p, p).split("?")[0])
        t = r["text"] if r else ""
        rows.append({"page": p, "present": bool(r), "says_federation_enabled": bool(re.search(r"ENGINEERING (RUNTIME )?ENABLED|federation_runtime\s*\|?\s*ENABLED_ENGINEERING|engineering federation runtime is enabled", t, re.I)), "says_federation_disabled": bool(pres.STALE.search(t)) and "FEDERATION BACKEND NOT ENABLED" not in t,
                     "mentions_synthetic_clients": bool(re.search(r"synthetic", t, re.I)), "mentions_one_machine": bool(re.search(r"one demonstration machine", t, re.I)), "says_hospitals_real": bool(re.search(r"(?<!not )(?<!not\s)\bhospital federation\b", t, re.I)),
                     "says_personalized_fl": bool(pres.unnegated_hits(t) and any(h["claim"] == "personalized_fl" for h in pres.unnegated_hits(t))), "says_candidate_deployed": any(h["claim"] == "candidate_deployed" for h in pres.unnegated_hits(t)), "says_diagnostic": any(h["claim"] == "diagnostic_or_clinical" for h in pres.unnegated_hits(t))})
    contradictions = [r["page"] for r in rows if r["says_federation_disabled"] or r["says_hospitals_real"] or r["says_personalized_fl"] or r["says_candidate_deployed"] or r["says_diagnostic"] or not r["present"]]
    positive = [r["page"] for r in rows if r["says_federation_enabled"]]
    return {"rows": rows, "contradictions": contradictions, "pages_stating_federation_enabled": positive, "consistent": not contradictions and {"/", "/app", "/app/about", "/app/system"} <= set(positive)}
