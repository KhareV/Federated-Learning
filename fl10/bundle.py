# ruff: noqa: E501
"""The single authoritative numeric bundle for one FL10 run: read ONLY from the run directory, the evaluation directory and frozen configs/reports. No numbers are typed here."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fl10 import LIVE_LABEL
from fl10.evaluate import PROTOCOL, ROOT
from fl10.evaluate import sha256_path as sha_path

SCHEMA = "NHM_FL10_BUNDLE_V1"
HISTORICAL = Path("reports/final_showcase/synth_fl_eval/synth_fl_eval_results.json")


def _json(path: Path) -> Any:
    return json.loads(path.read_text())


def build_bundle(run_dir: Path, eval_dir: Path, *, source_label: str = "RECORDED VERIFIED RUN") -> dict[str, Any]:
    run = _json(run_dir / "run_report.json")
    ev = _json(eval_dir / "evaluation_results.json")
    if run["status"] != "COMPLETED" or run["rounds_committed"] != 10:
        raise ValueError("RUN_NOT_A_COMPLETED_TEN_ROUND_RUN")
    if ev["run_id"] != run["run_id"] or ev["final_candidate_digest"] != run["candidate"]["state_sha256"]:
        raise ValueError("EVALUATION_DOES_NOT_BELONG_TO_RUN")
    protocol = _json(ROOT / PROTOCOL)
    link_path = run_dir / "monitoring_link.json"
    historical = _json(ROOT / HISTORICAL)
    from final_showcase import research

    for block in ev["states"].values():                       # per-participant histograms are not needed downstream (pooled histograms are kept)
        for m in block["participants"].values():
            m.pop("histogram", None)
    sci = research.bundle()
    bridge = {"comparability_rows": sci["comparability"]["rows"], "verdict": sci["comparability"]["verdict"], "limitations": sci["limitations"], "route": "/app/observatory/outcomes",
              "note": "Scientific real-ECG FL results (lane B) and historical centralized references (lane H) are unchanged and are NOT comparable to the synthetic engineering metrics below."}
    hist_states = {k: {m: v["pooled"][m] for m in ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE", "TP", "FP", "TN", "FN", "windows")} for k, v in historical["results"].items()}
    return {
        "schema_version": SCHEMA, "source_label": source_label, "mode": run["mode"], "run_id": run["run_id"], "synthetic_label": protocol["boundary_label"], "live_label": LIVE_LABEL if run["mode"] == "B" else None,
        "protocol": {"id": protocol["protocol_id"], "sha256": sha_path(ROOT / PROTOCOL), "holdout_manifest_sha256": protocol["holdout"]["manifest_sha256"], "uncertainty": protocol["uncertainty"], "threshold": protocol["decision_threshold"],
                     "research_question": protocol["research_question"], "primary_comparison": protocol["primary_comparison"], "interpretation_boundaries": protocol["interpretation_boundaries"], "metric_definitions": protocol["metrics"]["definitions"],
                     "probability_histogram": protocol["metrics"]["probability_histogram"]},
        "run": {k: run[k] for k in ("run_id", "mode", "status", "git_commit", "protocol_sha256", "planned_rounds", "rounds_committed", "started_at", "finished_at", "total_seconds", "settings", "environment", "accepted_updates_total",
                                     "example_exposures_total", "unique_training_windows", "candidate", "coordinator_identity", "cohort_manifest_sha256", "prefix_equals_frozen_reference", "federation_engine")},
        "state_progression": run["state_progression"], "rounds": run["rounds"], "client_rounds": run["client_rounds"], "batches": run["batches"], "updates": run["updates"],
        "monitoring_link": _json(link_path) if link_path.exists() else None,
        "evaluation": {k: ev[k] for k in ("protocol_sha256", "holdout_manifest_sha256", "method_freeze_commit", "state_digests", "separation", "holdout_participants", "threshold", "calibration", "round_selection", "windows", "states", "paired")},
        "evaluation_files": {n: sha_path(eval_dir / n) for n in ("evaluation_results.json", "holdout_predictions.csv", "participant_metrics.csv")},
        "run_files": {n: sha_path(run_dir / n) for n in ("run_report.json", "client_rounds.csv", "batches.csv", "rounds.csv", "updates.csv")},
        "historical_exposed": {"label": "PREVIOUSLY EXPOSED SYNTHETIC EVALUATION", "caveat": "8-participant holdout already examined by NHM_FINAL_SHOWCASE_001; continuity only, never used for decisions", "source": str(HISTORICAL),
                               "sha256": hashlib.sha256((ROOT / HISTORICAL).read_bytes()).hexdigest(), "states": hist_states},
        "scientific_bridge": bridge,
    }
