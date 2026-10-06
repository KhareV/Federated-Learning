# ruff: noqa: E501
"""FER-001 entry evidence (facts about the ENTRY tree only): reproduction of F-01..F-07 from source, dynamic route inventory, failed-audit crawl facts."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from scripts import final_eval_repair_lib as lib

ROOT, OUT = lib.ROOT, lib.ROOT / "reports/final_eval_repair/fer_001"


def lines_matching(rel: str, pat: str) -> list[dict]:
    return [{"file": rel, "line": i, "text": ln.strip()[:240]} for i, ln in enumerate((ROOT / rel).read_text().splitlines(), 1) if re.search(pat, ln, re.I)]


def main(audit_raw: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    wr = lambda n, d: (OUT / n).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")  # noqa: E731
    routes = lib.discover_routes()
    wr("route_inventory_entry.json", {"entry_sha": lib.git("rev-parse", "HEAD"), "route_count": len(routes), "dynamic_count": sum(r["dynamic"] for r in routes), "routes": routes})
    crawl = json.loads((Path(audit_raw) / "crawl_authed_A.json").read_text())["routes"]
    pat = re.compile(r"not yet enabled|intentionally deferred|personali[sz]|anomaly score|baseline is personal|Request failed with status 500|DEFERRED", re.I)
    facts = [{"route": r["route"], "status": r["status"], "title": r["title"], "h1": r["h1text"], "stale_hits": sorted({m.group(0).lower() for m in pat.finditer(r["text"])}), "bad_requests": r["bad"]} for r in crawl]
    wr("legacy_route_crawl_entry.json", {"source": "FINAL_EVALUATOR_AUDIT_V1 real-browser crawl of this exact entry SHA (raw file not committed; sha256 recorded)", "raw_sha256": hashlib.sha256((Path(audit_raw) / "crawl_authed_A.json").read_bytes()).hexdigest(), "routes": facts})
    f = {
        "F-01": lines_matching("frontend/src/routes/app/about/+page.svelte", r"not yet enabled"),
        "F-02": lines_matching("frontend/src/routes/+page.svelte", r"not yet enabled"),
        "F-03": {"routable_page_files": len(routes), "legacy_namespaces_rendering_stale_content": sorted({r["route"].split("/")[1] for r in facts if r["stale_hits"] and not r["route"].startswith(("/app", "/sign-in"))}), "examples": {k: next((r["stale_hits"] for r in facts if r["route"] == k), None) for k in ("/fl/overview", "/fl/personal-models", "/ai/insights", "/overview")}},
        "F-04": lines_matching("docs/capstone/CLERK_CONNECTED_RUNBOOK_V1.md", r"exactly as in the offline"),
        "F-05": {"finding": "no frozen guard evaluates current evaluator-facing feature-status copy; UFLG2 65/65 PASS with F-01/F-02 present"},
        "F-06": lines_matching("frontend/src/lib/components/spell/signature/signature.svelte", r"Lastoria"),
        "F-07": {"adapter": "frontend/svelte.config.js adapter-static fallback=index.html, handleUnseenRoutes=ignore; launcher serves frontend with `npm run preview` (vite preview)", "observation_source": "audit crawl: /app/history/<id> document status 404 with SPA content rendered"},
    }
    wr("failed_findings_reproduction.json", {"entry_sha": lib.git("rev-parse", "HEAD"), "findings": f, "all_reproduced": bool(f["F-01"] and f["F-02"] and f["F-03"]["legacy_namespaces_rendering_stale_content"] and f["F-04"] and f["F-06"])})
    wr("font_404_entry.json", {"missing_asset": "/LastoriaBoldRegular.otf", "present_in_static_or_src": (ROOT / "frontend/static/LastoriaBoldRegular.otf").exists(), "initiator": "frontend/src/lib/components/spell/signature/signature.svelte fetch(); used by <Signature> twice on the landing page (decorative handwriting animation: 'NHM', 'Context is everything.')", "landing_usages": lines_matching("frontend/src/routes/+page.svelte", r"<Signature"), "network_observation": "audit crawl: two 404 requests on /"})
    print(json.dumps({"routes": len(routes), "reproduced": json.load(open(OUT / "failed_findings_reproduction.json"))["all_reproduced"]}))


if __name__ == "__main__":
    main(sys.argv[1])
