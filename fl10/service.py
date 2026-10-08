# ruff: noqa: E501
"""Bundle assembly for the app: overview + chart specs + tables for one run (recorded or freshly executed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fl10 import charts, tables
from fl10.bundle import build_bundle
from fl10.constants import RECORDED
from fl10.evaluate import ROOT

CACHE: dict[str, dict[str, Any]] = {}


def payload(run_dir: Path, eval_dir: Path, *, source_label: str) -> dict[str, Any]:
    b = build_bundle(run_dir, eval_dir, source_label=source_label)
    ev = b["evaluation"]
    overview = {
        "source_label": b["source_label"], "mode": b["mode"], "run_id": b["run_id"], "synthetic_label": b["synthetic_label"], "live_label": b["live_label"], "protocol": b["protocol"], "run": b["run"],
        "state_progression": b["state_progression"], "monitoring_link": b["monitoring_link"], "historical_exposed": b["historical_exposed"], "scientific_bridge": b["scientific_bridge"],
        "evaluation": {k: ev[k] for k in ("method_freeze_commit", "state_digests", "separation", "threshold", "calibration", "round_selection", "windows")} | {"paired": ev["paired"], "holdout_participants": ev["holdout_participants"],
                                                                                                                                                         "headline": {s: {m: ev["states"][s]["pooled"][m] for m in ("AUPRC", "AUROC", "F1", "recall", "specificity", "BCE", "Brier", "TP", "FP", "TN", "FN", "windows")} for s in ev["states"]}},
        "evaluation_files": b["evaluation_files"], "run_files": b["run_files"],
        "rounds": [{k: r[k] for k in ("round", "accepted_updates", "rejected_updates", "weighted_mean_training_loss", "global_state_sha256", "candidate_status", "round_duration_seconds", "aggregated_update_norm")} for r in b["rounds"]],
    }
    return {"overview": overview, "specs": charts.build_specs(b), "tables": tables.build_tables(b)}


def recorded(run_key: str) -> dict[str, Any]:
    if run_key not in RECORDED:
        raise KeyError("UNKNOWN_RECORDED_RUN")
    if run_key not in CACHE:
        mode_dir = RECORDED[run_key][0]
        CACHE[run_key] = payload(ROOT / f"reports/fl10/runs/{mode_dir}", ROOT / f"reports/fl10/eval/{mode_dir}", source_label="RECORDED VERIFIED RUN")
    return CACHE[run_key]


def recorded_index() -> list[dict[str, Any]]:
    out = []
    for key, (mode_dir, label) in RECORDED.items():
        report = json.loads((ROOT / f"reports/fl10/runs/{mode_dir}/run_report.json").read_text())
        out.append({"key": key, "label": label, "mode": report["mode"], "run_id": report["run_id"], "candidate_sha256": report["candidate"]["state_sha256"], "status": report["status"]})
    return out
