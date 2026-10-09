# ruff: noqa: E501
"""Frozen NHM_FL10_001 recorded runs presented through the SAME bundle schema as a live run, so one Studio code path (round explorer, metric cards,
figures, tables, exports) serves historical evidence. Everything is read from the recorded FL10 run/evaluation files; the source label states it is recorded,
never a new measurement."""

from __future__ import annotations

from typing import Any

from fl10.bundle import build_bundle
from fl10.constants import RECORDED
from fl10.evaluate import ROOT
from studio.bundle import SCHEMA
from studio.constants import COHORT_USE_DETAIL, COHORT_USE_LABEL, EVAL_PROTOCOL_ID

RECORDED_LABEL = "RECORDED VERIFIED RUN (NHM_FL10_001, frozen evidence — not a new measurement)"
_CACHE: dict[str, dict[str, Any]] = {}


def from_fl10_bundle(b: dict[str, Any], *, source_label: str = RECORDED_LABEL) -> dict[str, Any]:
    ev = b["evaluation"]
    first = {r["client_id"]: r for r in b["client_rounds"] if r["round"] == 1}
    cohort = [{"client_id": c, "participant_id": r["participant_id"], "session_id": r["dataset_id"], "dataset_sha256": r["dataset_sha256"],
               "counts": {"windows_emitted": r["source_window_count"], "trainable": r["quality_eligible_windows"], "DEGRADED": r["excluded_degraded"], "UNUSABLE": r["excluded_unusable"],
                          "excluded_valid_but_incomplete": r["excluded_valid_but_incomplete"], "synthetic_positive": r["positive_labels"], "synthetic_negative": r["negative_labels"]}} for c, r in sorted(first.items())]
    states = {k: {**v, "curves": v.get("curves")} for k, v in ev["states"].items()}
    return {
        "schema_version": SCHEMA, "source_label": source_label, "run_id": b["run_id"], "run_length": 10, "planned_rounds": 10, "engine": "FL10_10R", "mode": b["mode"], "replay_of": None,
        "synthetic_label": b["synthetic_label"], "live_label": b["live_label"],
        "protocol": {**b["protocol"], "evaluation_protocol_id": EVAL_PROTOCOL_ID, "probability_histogram": b["protocol"]["probability_histogram"]},
        "run": b["run"], "state_progression": b["state_progression"], "rounds": b["rounds"], "client_rounds": b["client_rounds"], "batches": b["batches"], "updates": b["updates"], "training_cohort": cohort,
        "monitoring_link": b["monitoring_link"],
        "evaluation": {"states": states, "status": dict.fromkeys(states, "COMPLETED"), "failures": {}, "state_digests": ev["state_digests"], "windows": ev["windows"], "holdout_participants": ev["holdout_participants"], "separation": ev["separation"],
                       "separation_source": "FL10_FROZEN_EVIDENCE", "threshold": ev["threshold"], "calibration": ev["calibration"], "round_selection": ev["round_selection"], "paired": ev["paired"], "comparator": "R03", "endpoint": "R10",
                       "cohort_use": "RECORDED FRESH 16-PARTICIPANT HOLDOUT EVALUATION (NHM_FL10_001) — the cohort has since been exposed; later live scores are diagnostic only", "cohort_use_detail": COHORT_USE_DETAIL, "cohort_id": "WEARABLE_SIM_FL10_EVAL_HOLDOUT_V1",
                       "protocol_sha256": ev["protocol_sha256"], "holdout_manifest_sha256": ev["holdout_manifest_sha256"], "method_freeze_commit": ev["method_freeze_commit"]},
        "historical_exposed": b["historical_exposed"], "scientific_bridge": b["scientific_bridge"], "revision": 0}


def recorded_bundle(key: str) -> dict[str, Any]:
    if key not in RECORDED:
        raise KeyError("UNKNOWN_RECORDED_RUN")
    if key not in _CACHE:
        mode_dir = RECORDED[key][0]
        _CACHE[key] = from_fl10_bundle(build_bundle(ROOT / f"reports/fl10/runs/{mode_dir}", ROOT / f"reports/fl10/eval/{mode_dir}", source_label="RECORDED VERIFIED RUN"))
    return _CACHE[key]


def recorded_records(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-round evaluation summaries in the live-record shape (status COMPLETED, source = recorded)."""
    out = []
    for key, block in sorted(bundle["evaluation"]["states"].items()):
        p = block["pooled"]
        out.append({"schema_version": "STUDIO_ROUND_EVALUATION_V1", "run_id": bundle["run_id"], "run_length": 10, "round_id": int(key[1:]), "global_state_digest": bundle["evaluation"]["state_digests"][key], "candidate_id": None,
                    "cohort_id": bundle["evaluation"]["cohort_id"], "cohort_use": bundle["evaluation"]["cohort_use"], "evaluation_protocol_id": EVAL_PROTOCOL_ID, "evaluation_status": "COMPLETED", "evaluation_queued_at": None,
                    "evaluation_started_at": None, "evaluation_completed_at": None, "failure": None, "threshold": 0.5, "calibration": "NONE", "windows": p["windows"],
                    "metric_result": {k: v for k, v in p.items() if k != "histogram"},
                    "confusion_counts": {k: int(p[k]) for k in ("TP", "FP", "TN", "FN", "predicted_positives", "predicted_negatives")}, "source": "RECORDED"})
    return out
