# ruff: noqa: E501
"""Assemble the run-scoped numeric bundle (FL10 bundle schema, partial-evaluation aware) from the run directory and the evaluation observer.
Numbers are read ONLY from the run report, the persisted evaluation records/curves and frozen configs; nothing is typed here and nothing is carried over from another run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fl10 import holdout as fl10_holdout
from fl10.bundle import HISTORICAL
from fl10.evaluate import MANIFEST, PROTOCOL, ROOT
from studio import holdout_cache
from studio.constants import COHORT_USE_DETAIL, COHORT_USE_LABEL, EVAL_PROTOCOL_ID
from studio.observer import EvaluationObserver, round_key
from studio.specs import comparison_pair

SCHEMA = "STUDIO_LIVE_BUNDLE_V1"
FROZEN_EVAL = ROOT / "reports/fl10/eval/modeA/evaluation_results.json"
_STATIC: dict[str, Any] = {}


def _json(path: Path) -> Any:
    return json.loads(path.read_text())


def read_run_report(run_dir: Path) -> dict[str, Any] | None:
    for name in ("run_report.json", "run_report.partial.json"):
        path = run_dir / name
        if path.exists():
            return _json(path)
    return None


def _holdout_info() -> dict[str, Any]:
    """Holdout participants + leakage audit. RECOMPUTED once the observer has loaded the frozen holdout; before that, the FL10 frozen evidence for the same cohort (labelled)."""
    cached = holdout_cache._CACHE
    if cached is not None:
        return {"entries": cached.entries, "separation": cached.separation, "windows": cached.windows, "separation_source": "RECOMPUTED_BY_OBSERVER_IN_THIS_PROCESS", "protocol_sha256": cached.protocol_sha256, "manifest_sha256": cached.manifest_sha256}
    if "frozen" not in _STATIC:
        frozen = _json(FROZEN_EVAL)
        _STATIC["frozen"] = {"entries": frozen["holdout_participants"], "separation": frozen["separation"], "windows": frozen["windows"], "separation_source": "FL10_FROZEN_EVIDENCE_SAME_COHORT_RECOMPUTED_WHEN_OBSERVER_LOADS",
                             "protocol_sha256": frozen["protocol_sha256"], "manifest_sha256": frozen["holdout_manifest_sha256"]}
    return _STATIC["frozen"]


def _static() -> dict[str, Any]:
    if "protocol" not in _STATIC:
        protocol = _json(ROOT / PROTOCOL)
        historical = _json(ROOT / HISTORICAL)
        keys = ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE", "TP", "FP", "TN", "FN", "windows")
        _STATIC["protocol"] = protocol
        from final_showcase import research

        sci = research.bundle()
        _STATIC["bridge"] = {"comparability_rows": sci["comparability"]["rows"], "verdict": sci["comparability"]["verdict"], "limitations": sci["limitations"], "route": "/app/observatory/outcomes",
                             "note": "Scientific real-ECG FL results (lane B) and historical centralized references (lane H) are unchanged and are NOT comparable to the synthetic engineering metrics of a Studio run."}
        _STATIC["historical"] = {"label": "PREVIOUSLY EXPOSED SYNTHETIC EVALUATION", "caveat": "8-participant holdout already examined by NHM_FINAL_SHOWCASE_001; continuity only, never used for decisions", "source": str(HISTORICAL),
                                 "sha256": hashlib.sha256((ROOT / HISTORICAL).read_bytes()).hexdigest(), "states": {k: {m: v["pooled"][m] for m in keys} for k, v in historical["results"].items()}}
    return _STATIC


def build_live_bundle(*, run_id: str, run_length: int, run_dir: Path, observer: EvaluationObserver, mode: str, engine: str, status: str, source_label: str = "LIVE RUN (this session)",
                      eval_run_id: str | None = None, training_cohort: list[dict[str, Any]] | None = None, replay_of: str | None = None) -> dict[str, Any]:
    static = _static()
    protocol, info = static["protocol"], _holdout_info()
    report = read_run_report(run_dir) or {"status": status, "rounds": [], "client_rounds": [], "batches": [], "updates": [], "state_progression": {}}
    eval_id = eval_run_id or run_id
    records = observer.records(eval_id)
    base = observer.run_dir(eval_id)
    states: dict[str, Any] = {}
    statuses: dict[str, str] = {}
    failures: dict[str, dict[str, str]] = {}
    digests: dict[str, str] = {}
    for rec in records:
        key = round_key(rec.round_id)
        statuses[key] = rec.evaluation_status
        digests[key] = rec.global_state_digest
        if rec.failure:
            failures[key] = rec.failure.model_dump()
        if rec.evaluation_status == "COMPLETED":
            curves = _json(base / rec.curve_artifact_reference.path) if rec.curve_artifact_reference else None  # type: ignore[union-attr]
            states[key] = {"pooled": rec.metric_result, "participants": rec.participant_metrics, "curves": curves, **(rec.participant_summary or {})}
    a, e = comparison_pair(run_length)
    cohort = training_cohort if training_cohort is not None else report.get("training_cohort") or []
    paired = observer.paired(eval_id)
    run = {k: report.get(k) for k in ("run_id", "mode", "status", "planned_rounds", "rounds_committed", "started_at", "finished_at", "settings", "accepted_updates_total", "example_exposures_total", "unique_training_windows", "candidate",
                                      "coordinator_identity", "prefix_equals_frozen_reference", "federation_engine", "failure")}
    run["status"] = report.get("status", status)
    link = run_dir / "monitoring_link.json"
    return {
        "schema_version": SCHEMA, "source_label": source_label, "run_id": run_id, "run_length": run_length, "planned_rounds": run_length, "engine": engine, "mode": mode, "replay_of": replay_of,
        "synthetic_label": protocol["boundary_label"], "live_label": protocol["live_label"] if mode == "B" else None,
        "protocol": {"id": protocol["protocol_id"], "evaluation_protocol_id": EVAL_PROTOCOL_ID, "sha256": info["protocol_sha256"], "holdout_manifest_sha256": info["manifest_sha256"], "uncertainty": protocol["uncertainty"], "threshold": protocol["decision_threshold"],
                     "metric_definitions": protocol["metrics"], "probability_histogram": protocol["metrics"]["probability_histogram"],
                     "interpretation_boundaries": protocol["interpretation_boundaries"], "research_question": protocol["research_question"], "primary_comparison": protocol["primary_comparison"]},
        "run": run, "state_progression": report.get("state_progression", {}), "rounds": report.get("rounds", []), "client_rounds": report.get("client_rounds", []), "batches": report.get("batches", []), "updates": report.get("updates", []),
        "training_cohort": cohort, "monitoring_link": _json(link) if link.exists() else None,
        "evaluation": {"states": states, "status": statuses, "failures": failures, "state_digests": digests, "windows": info["windows"], "holdout_participants": info["entries"], "separation": info["separation"], "separation_source": info["separation_source"],
                       "threshold": 0.5, "calibration": "NONE", "round_selection": "NONE - no round, threshold or candidate is selected from diagnostic evaluation", "paired": paired, "comparator": f"R{a:02d}", "endpoint": f"R{e:02d}",
                       "cohort_use": COHORT_USE_LABEL, "cohort_use_detail": COHORT_USE_DETAIL, "cohort_id": fl10_holdout.COHORT_ID, "protocol_sha256": info["protocol_sha256"], "holdout_manifest_sha256": info["manifest_sha256"],
                       "method_freeze_commit": "f91a96a6c5a38432e4fc84f7e760c21874ce2d40"},
        "historical_exposed": static["historical"], "scientific_bridge": static["bridge"], "revision": observer.revision(eval_id)}
