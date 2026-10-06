# ruff: noqa: E501
"""FER-002 entry evidence (facts about the ENTRY tree only): reproduction of F2-01/F2-02/F2-03 and the loader/candidate observations from source, landing import inventory, full landing claim inventory."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from scripts import final_eval_repair_002_provenance as prov
from scripts import final_eval_repair_lib as lib

ROOT = lib.ROOT


def classify(hit: dict[str, str] | None, text: str) -> str:
    if hit is None:
        return "ILLUSTRATIVE_AND_EXPLICITLY_QUALIFIED" if prov.MARKER.search(text) else "SUPPORTED_CURRENT_PRODUCT_FACT"
    return {"LIVE_STATE": "MISLEADING_LIVE_STATE_ASSERTION", "EDGE_INFERENCE": "STALE_PRODUCT_ASSERTION", "HARDWARE_DATA": "MISLEADING_LIVE_STATE_ASSERTION", "FILE_REFERENCE": "UNSUPPORTED_QUANTITATIVE_ASSERTION", "STATUS_LABEL": "MARKETING_METAPHOR"}.get(hit["claim_type"], "UNSUPPORTED_QUANTITATIVE_ASSERTION")


def inventory(root: Path) -> dict:
    files = prov.landing_files(root)
    rows = []
    for f in files:
        if not f.endswith((".svelte", ".ts")):
            continue
        t = (root / f).read_text(encoding="utf-8")
        flagged = {h["text"] for h in prov.scan_text(t)}
        for s in prov.visible_strings(t):
            hits = []
            for rid, ctype, pat, _needs in prov.RULES:
                if re.search(pat, s, re.I):
                    hits.append({"rule": rid, "claim_type": ctype})
            if not hits:
                continue
            unq = s[:140] in flagged
            rows.append({"file": f, "text": s[:160], "rules": [h["rule"] for h in hits], "classification": classify(hits[0] if unq else None, s)})
    by_class: dict[str, int] = {}
    for r in rows:
        by_class[r["classification"]] = by_class.get(r["classification"], 0) + 1
    return {"landing_import_graph": files, "landing_file_count": len(files), "high_risk_strings": len(rows), "by_classification": by_class, "rows": rows}


def lines(rel: str, pat: str) -> list[dict]:
    return [{"file": rel, "line": i, "text": ln.strip()[:200]} for i, ln in enumerate((ROOT / rel).read_text().splitlines(), 1) if re.search(pat, ln, re.I)]


def main() -> None:
    out = ROOT / "reports/final_eval_repair/fer_002"
    out.mkdir(parents=True, exist_ok=True)
    wr = lambda n, d: (out / n).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")  # noqa: E731
    inv = inventory(ROOT)
    wr("landing_claim_inventory_entry.json", {"entry_sha": lib.git("rev-parse", "HEAD"), **inv})
    comps = "frontend/src/lib/components"
    land = (ROOT / "frontend/src/routes/+page.svelte").read_text()
    f = {
        "F2-01": {"neuralgraph": lines(f"{comps}/landing/NeuralGraph.svelte", r"99\.8|LIVE EDGE|real-time"), "scan_hits_by_rule": {r: sum(1 for x in inv["rows"] if r in x["rules"] and x["classification"] not in ("ILLUSTRATIVE_AND_EXPLICITLY_QUALIFIED", "SUPPORTED_CURRENT_PRODUCT_FACT")) for r in {y for x in inv["rows"] for y in x["rules"]}}},
        "F2-02": {"skip_link_present": "skip-link" in land or bool(re.search(r"skip to (main )?content", land, re.I)), "landing_nav_labelled": bool(re.search(r"<nav[^>]*aria-label", land)), "raf_loops_without_reduced_motion_guard": [f for f in ("landing/NeuralGraph.svelte", "landing/WatchScene.svelte", "signals/MultimodalStudio.svelte", "magic/globe/globe.svelte") if "prefers-reduced-motion" not in (ROOT / "frontend/src/lib/components" / f).read_text()]},
        "F2-03": {"source": "FINAL_EVALUATOR_AUDIT_V1 rerun: 0-5 interactive targets below 24px per page at 390px (measured; entry browser audit re-measures them)"},
        "loader_observation": lines("frontend/src/routes/app/+layout.svelte", r"Opening the NHM workspace"),
        "candidate_observation": {"misleading_phrases_found": lines("frontend/src/lib/components/product/federation/CandidateCard.svelte", r"duplicate|same candidate|deployed twice"), "candidate_identity_and_digest_are_separate_fields": ("candidate.candidate_id" in (ROOT / "frontend/src/lib/components/product/federation/CandidateCard.svelte").read_text() and "State digest" in (ROOT / "frontend/src/lib/components/product/federation/CandidateCard.svelte").read_text())},
    }
    wr("failed_findings_reproduction.json", {"entry_sha": lib.git("rev-parse", "HEAD"), "findings": f, "all_reproduced": bool(f["F2-01"]["neuralgraph"]) and not f["F2-02"]["skip_link_present"] and not f["F2-02"]["landing_nav_labelled"] and bool(f["F2-02"]["raf_loops_without_reduced_motion_guard"])})
    print(json.dumps({"landing_files": inv["landing_file_count"], "high_risk": inv["high_risk_strings"], "by_class": inv["by_classification"], "reproduced": json.loads((out / "failed_findings_reproduction.json").read_text())["all_reproduced"]}))


if __name__ == "__main__":
    sys.exit(main())
