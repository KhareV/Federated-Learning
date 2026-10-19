# ruff: noqa: E501
"""Assemble the run-scoped numeric bundle (FL10 bundle schema, partial-evaluation aware) from the run directory and the evaluation observer.
Numbers are read ONLY from the run report, the persisted evaluation records/curves and frozen configs; nothing is typed here and nothing is carried over from another run."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from fl10.bundle import HISTORICAL
from fl10.evaluate import PROTOCOL, ROOT
from studio import cohorts, holdout_cache
from studio.constants import EVAL_PROTOCOL_ID
from studio.observer import EvaluationObserver, round_key
from studio.specs import comparison_pair

SCHEMA = "STUDIO_LIVE_BUNDLE_V1"
# A run whose monitored client got its signal from a COMPLETED History session did not monitor anything live: the signal was regenerated from the frozen scenario, and that client's labels are assigned (a session has no scheduled events)
HISTORY_SOURCE_LABEL = "HISTORY MONITORING SESSION SIGNAL (REGENERATED, NOT LIVE-MONITORED) — NOT A REAL PHYSIOLOGICAL PATIENT"
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


def _holdout_info(cohort: str = cohorts.ORIGINAL) -> dict[str, Any]:
    """Holdout participants + leakage audit. RECOMPUTED once the observer has loaded the frozen holdout; before that, the FL10 frozen evidence for the same cohort (labelled)."""
    if cohorts.is_realistic(cohort):
        loaded = cohorts.loaded_holdout(cohort)
        if loaded is None:
            return cohorts.static_info(cohort)
        return {"entries": loaded.entries, "separation": loaded.separation, "windows": loaded.windows, "separation_source": "RECOMPUTED_BY_OBSERVER_IN_THIS_PROCESS", "protocol_sha256": loaded.protocol_sha256, "manifest_sha256": loaded.manifest_sha256}
    cached = holdout_cache._CACHE
    if cached is not None:
        return {"entries": cached.entries, "separation": cached.separation, "windows": cached.windows, "separation_source": "RECOMPUTED_BY_OBSERVER_IN_THIS_PROCESS", "protocol_sha256": cached.protocol_sha256, "manifest_sha256": cached.manifest_sha256}
    if "frozen" not in _STATIC:
        frozen = _json(FROZEN_EVAL)
        _STATIC["frozen"] = {"entries": frozen["holdout_participants"], "separation": frozen["separation"], "windows": frozen["windows"], "separation_source": "FL10_FROZEN_EVIDENCE_SAME_COHORT_RECOMPUTED_WHEN_OBSERVER_LOADS",
                             "protocol_sha256": frozen["protocol_sha256"], "manifest_sha256": frozen["holdout_manifest_sha256"]}
    return _STATIC["frozen"]


_STATIC_LOCK = threading.Lock()


def _static() -> dict[str, Any]:
    """The pinned protocol, scientific bridge and historical reference. Built once under a lock and published with "protocol" LAST: a concurrent first request used to see the half-built cache and fail with KeyError: 'historical'."""
    if "protocol" in _STATIC:
        return _STATIC
    with _STATIC_LOCK:
        if "protocol" not in _STATIC:
            protocol = _json(ROOT / PROTOCOL)
            historical = _json(ROOT / HISTORICAL)
            keys = ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE", "TP", "FP", "TN", "FN", "windows")
            from final_showcase import research

            sci = research.bundle()
            _STATIC["bridge"] = {"comparability_rows": sci["comparability"]["rows"], "verdict": sci["comparability"]["verdict"], "limitations": sci["limitations"], "route": "/app/observatory/outcomes",
                                 "note": "Scientific real-ECG FL results (lane B) and historical centralized references (lane H) are unchanged and are NOT comparable to the synthetic engineering metrics of a Studio run."}
            _STATIC["historical"] = {"label": "PREVIOUSLY EXPOSED SYNTHETIC EVALUATION", "caveat": "8-participant holdout already examined by NHM_FINAL_SHOWCASE_001; continuity only, never used for decisions", "source": str(HISTORICAL),
                                     "sha256": hashlib.sha256((ROOT / HISTORICAL).read_bytes()).hexdigest(), "states": {k: {m: v["pooled"][m] for m in keys} for k, v in historical["results"].items()}}
            _STATIC["protocol"] = protocol
    return _STATIC


def build_live_bundle(*, run_id: str, run_length: int, run_dir: Path, observer: EvaluationObserver, mode: str, engine: str, status: str, source_label: str = "LIVE RUN (this session)",
                      eval_run_id: str | None = None, training_cohort: list[dict[str, Any]] | None = None, replay_of: str | None = None, cohort: str = cohorts.ORIGINAL) -> dict[str, Any]:
    static = _static()
    spec = cohorts.spec(cohort)
    protocol, info = static["protocol"], _holdout_info(cohort)
    synthetic_label = (protocol["boundary_label"] if cohort == cohorts.ORIGINAL else "SYNTHETIC REALISTIC ECTOPY CLASSIFICATION (ANNOTATION-NOISY LABELS) — NOT AAMI-SVF OR CLINICAL VALIDATION" if cohort == cohorts.REALISTIC
                       else "SYNTHETIC REALISTIC ECTOPY CLASSIFICATION WITH RECORDED NSTDB NOISE (ANNOTATION-NOISY LABELS) — NOT AAMI-SVF OR CLINICAL VALIDATION")
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
    training = training_cohort if training_cohort is not None else report.get("training_cohort") or []
    paired = observer.paired(eval_id)
    run = {k: report.get(k) for k in ("run_id", "mode", "status", "planned_rounds", "rounds_committed", "started_at", "finished_at", "settings", "accepted_updates_total", "example_exposures_total", "unique_training_windows", "candidate",
                                      "coordinator_identity", "prefix_equals_frozen_reference", "federation_engine", "failure", "initialisation", "algorithm", "secagg_mode", "fedprox_mu", "secagg_shadow")}
    run["status"] = report.get("status", status)
    link = run_dir / "monitoring_link.json"
    link_data = _json(link) if link.exists() else None
    from_history = bool(link_data and link_data.get("signal_session"))
    if from_history:
        synthetic_label += f" · SITE_{int(link_data.get('monitored_site') or 0):02d} TRAINS ON YOUR HISTORY SESSION'S REGENERATED SIGNAL (SYNTHETIC-ASSIGNED LABELS; THE OTHER SEVEN CLIENTS USE EVENT-WINDOW LABELS)"
    return {
        "schema_version": SCHEMA, "source_label": source_label, "run_id": run_id, "run_length": run_length, "planned_rounds": run_length, "engine": engine, "mode": mode, "replay_of": replay_of,
        "synthetic_label": synthetic_label, "cohort": cohort, "cohort_label": spec.label, "live_label": (HISTORY_SOURCE_LABEL if from_history else protocol["live_label"]) if mode == "B" else None,
        "protocol": {"id": protocol["protocol_id"], "evaluation_protocol_id": EVAL_PROTOCOL_ID, "sha256": info["protocol_sha256"], "holdout_manifest_sha256": info["manifest_sha256"], "uncertainty": protocol["uncertainty"], "threshold": protocol["decision_threshold"],
                     "metric_definitions": protocol["metrics"], "probability_histogram": protocol["metrics"]["probability_histogram"],
                     "interpretation_boundaries": protocol["interpretation_boundaries"], "research_question": protocol["research_question"], "primary_comparison": protocol["primary_comparison"]},
        "run": run, "state_progression": report.get("state_progression", {}), "rounds": report.get("rounds", []), "client_rounds": report.get("client_rounds", []), "batches": report.get("batches", []), "updates": report.get("updates", []),
        "training_cohort": training, "monitoring_link": link_data,
        "evaluation": {"states": states, "status": statuses, "failures": failures, "state_digests": digests, "windows": info["windows"], "holdout_participants": info["entries"], "separation": info["separation"], "separation_source": info["separation_source"],
                       "threshold": 0.5, "calibration": "NONE", "round_selection": "NONE - no round, threshold or candidate is selected from diagnostic evaluation", "paired": paired, "comparator": f"R{a:02d}", "endpoint": f"R{e:02d}",
                       "cohort_use": spec.use_label, "cohort_use_detail": spec.use_detail, "cohort_id": spec.evaluation_cohort_id, "cohort": cohort, "claim_boundary": spec.claim_boundary, "protocol_sha256": info["protocol_sha256"], "holdout_manifest_sha256": info["manifest_sha256"],
                       "method_freeze_commit": spec.method_freeze},
        "historical_exposed": static["historical"], "scientific_bridge": static["bridge"], "revision": observer.revision(eval_id)}
