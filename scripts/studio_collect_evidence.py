# ruff: noqa: E501
"""Collect run-specific evidence of the genuinely executed 3-round and 10-round Studio runs from a running isolated stack (DemoAuth).
Writes full per-round metric tables (JSON + Markdown), evaluation timing behaviour, state-digest lineage, update accounting, export manifest hashes and the comparison with the
recorded NHM_FL10_001 evidence. Reads only; evidence contains digests, counts and metrics, no credential."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE", "Brier", "TP", "FP", "TN", "FN", "predicted_positives", "predicted_negatives", "windows", "positives", "negatives"]


def get(base: str, path: str) -> Any:
    with urllib.request.urlopen(base + path, timeout=120) as response:
        return json.load(response)


def run_evidence(base: str, run_id: str, rounds: int) -> dict[str, Any]:
    descriptor = get(base, f"/studio/runs/{run_id}")
    summary = get(base, f"/studio/runs/{run_id}/evaluation")
    recorded = get(base, "/studio/runs/recorded-A/evaluation")["records"]
    table, timing, lineage, accounting = [], [], [], []
    for record in summary["records"]:
        detail = get(base, f"/studio/runs/{run_id}/rounds/{record['round_id']}")
        ref = recorded[record["round_id"]] if rounds == 10 or record["round_id"] <= 3 else None
        table.append({"round": record["round_id"], "state_digest": record["global_state_digest"], "status": record["evaluation_status"], **{k: record["metric_result"][k] for k in KEYS}})
        timing.append({"round": record["round_id"], "queued_at": record["evaluation_queued_at"], "started_at": record["evaluation_started_at"], "completed_at": record["evaluation_completed_at"]})
        if detail["committed"]:
            accounting.append({"round": record["round_id"], "accepted_updates": detail["round"]["accepted_updates"], "weights_sum": sum(c["aggregation_weight"] for c in detail["client_rounds"]), "clients": len(detail["client_rounds"]),
                               "weighted_mean_training_loss": detail["round"]["weighted_mean_training_loss"], "parity_with_frozen": (detail["round"].get("parity") or {}).get("equals_frozen_reference")})
        lineage.append({"round": record["round_id"], "equals_recorded_fl10_digest": ref is not None and ref["global_state_digest"] == record["global_state_digest"],
                        "equals_recorded_fl10_metrics": ref is not None and all(ref["metric_result"][k] == record["metric_result"][k] for k in ("AUPRC", "AUROC", "F1", "BCE", "Brier", "TP", "FP", "TN", "FN"))})
    manifest = get(base, f"/studio/runs/{run_id}/exports")
    figures, tables = get(base, f"/studio/runs/{run_id}/figures")["specs"], get(base, f"/studio/runs/{run_id}/tables")["tables"]
    overview = get(base, f"/studio/runs/{run_id}/overview")
    return {"run_id": run_id, "run_length": rounds, "engine": descriptor["engine"], "source_mode": descriptor["source_mode"], "status": descriptor["status"], "candidate": descriptor["candidate"], "cohort_use": summary["cohort_use"],
            "evaluation_protocol_id": summary["evaluation_protocol_id"], "threshold": summary["threshold"], "calibration": summary["calibration"], "metric_table": table, "evaluation_timing": timing, "round_accounting": accounting,
            "accepted_updates_total": overview["run"]["accepted_updates_total"], "lineage_vs_recorded": lineage, "paired_available": summary["comparison"]["paired_available"],
            "figures": {k: v["availability"] for k, v in figures.items()}, "tables": {k: {"rows": len(v["rows"]), "availability": v["availability"]} for k, v in tables.items()},
            "export_manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(), "export_counts": {"figures": len(manifest["figures"]), "tables": len(manifest["tables"]), "data": len(manifest["data"])}}


def markdown(ev: dict[str, Any]) -> str:
    cols = ["round", "AUPRC", "AUROC", "F1", "specificity", "recall", "accuracy", "BCE", "Brier", "TP", "FP", "TN", "FN"]
    head = f"# {ev['run_length']}-round run {ev['run_id']} — measured per-round evaluation\n\nEngine {ev['engine']} · source {ev['source_mode']} · status {ev['status']} · {ev['accepted_updates_total']} accepted updates · threshold {ev['threshold']} · calibration {ev['calibration']}\n\n{ev['cohort_use']}\n\n"
    rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in ev["metric_table"]:
        rows.append("| " + " | ".join(f"{r[c]:.6f}" if isinstance(r[c], float) else str(r[c]) for c in cols) + " |")
    equal = sum(1 for x in ev["lineage_vs_recorded"] if x["equals_recorded_fl10_digest"] and x["equals_recorded_fl10_metrics"])
    return head + "\n".join(rows) + f"\n\nStates and metrics equal to the recorded NHM_FL10_001 evidence (measured on this run, not preloaded): {equal} of {len(ev['lineage_vs_recorded'])} rounds.\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8102/product/v1")
    ap.add_argument("--run3", required=True)
    ap.add_argument("--run10", required=True)
    ap.add_argument("--run10-b", help="a 10-round run in source mode LIVE_MONITORED_SITE_00")
    ap.add_argument("--out", default="reports/unified_live_fl")
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(a.run3, 3, ""), (a.run10, 10, "")] + ([(a.run10_b, 10, "_modeB")] if a.run10_b else [])
    for run_id, rounds, suffix in jobs:
        evidence = run_evidence(a.base, run_id, rounds)
        (out / f"run_evidence_{rounds}round{suffix}.json").write_text(json.dumps(evidence, indent=1, sort_keys=True) + "\n")
        (out / f"run_evidence_{rounds}round{suffix}.md").write_text(markdown(evidence))
        print(rounds, suffix or "A", run_id, evidence["accepted_updates_total"], sum(1 for x in evidence["lineage_vs_recorded"] if x["equals_recorded_fl10_digest"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
