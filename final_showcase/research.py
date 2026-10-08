# ruff: noqa: E501
"""Authoritative numeric bundle for the final showcase (workstreams C and D).

One source of truth: every figure, table, dashboard value and manuscript number is read from this bundle, which is read only from
hash-verified frozen artifacts (plus the committed synthetic-evaluation result). No new inference, training or statistics are computed here;
the only arithmetic is subtraction of two frozen point values for the comparability matrix (flagged as ``derived_subtraction``)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from functools import lru_cache
from typing import Any

from product.observatory import evidence

ROOT = evidence.ROOT
MODEL_V2 = "reports/model_v2"
SYNTH = "reports/final_showcase/synth_fl_eval/synth_fl_eval_results.json"
SCHEMA = "NHM_FINAL_SHOWCASE_RESEARCH_BUNDLE_V1"

# (algorithm, condition) -> (experiment folder holding the hash manifest, round_log path relative to repo)
ROUND_LOGS: dict[tuple[str, str], tuple[str, str]] = {
    ("FedAvg", "iid"): ("v2_fl_001", f"{MODEL_V2}/v2_fl_001/round_log.csv"),
    **{("FedAvg", c): ("v2_fl_002", f"{MODEL_V2}/v2_fl_002/{c}_round_log.csv") for c in ("label", "feature", "quantity", "combined")},
    **{("FedProx", c): ("v2_fl_003", f"{MODEL_V2}/v2_fl_003/transfer/{c}/round_log.csv") for c in ("iid", "feature", "quantity", "combined")},
    ("FedProx", "label"): ("v2_fl_003", f"{MODEL_V2}/v2_fl_003/candidates/mu_0p1/round_log.csv"),
}
CONDITIONS = ("iid", "label", "feature", "quantity", "combined")
LANES = {"A": "MODEL_V2_FINAL + CAL_V2 — runtime monitoring", "B": "Scientific federated learning — AAMI_SVF_WINDOW_V1",
         "C": "Synthetic engineering federated learning — WEARABLE_SIM_EVENT_WINDOW_V1", "H": "Historical centralized reference (frozen, not re-run)"}


class ResearchError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=8)
def _manifest(experiment: str) -> dict[str, str]:
    return dict(json.loads((ROOT / MODEL_V2 / experiment / "artifact_hashes.json").read_bytes())["artifacts"])


def _verified(experiment: str, relative: str) -> bytes:
    expected = _manifest(experiment).get(relative)
    if expected is None:
        raise ResearchError(f"NOT_IN_FROZEN_MANIFEST:{relative}")
    data = (ROOT / relative).read_bytes()
    if _sha(data) != expected:
        raise ResearchError(f"HASH_MISMATCH:{relative}")
    return data


@lru_cache(maxsize=16)
def round_log(algorithm: str, condition: str) -> dict[str, Any]:
    experiment, relative = ROUND_LOGS[(algorithm, condition)]
    data = _verified(experiment, relative)
    rows = list(csv.DictReader(io.StringIO(data.decode())))
    pick = {"round": int, "training_weighted_mean_loss": float, "validation_AUPRC": float, "validation_AUROC": float, "validation_BCE": float, "selected_best_so_far": lambda v: v == "True"}
    series = []
    for r in rows:
        series.append({k: (cast(r[k]) if r[k] != "" else None) for k, cast in pick.items()})
    best = [s["round"] for s in series if s["selected_best_so_far"]]
    return {"algorithm": algorithm, "condition": condition, "source": relative, "sha256": _sha(data), "rounds": len(series) - 1,
            "metric_scope": "DEVELOPMENT VALIDATION (model-selection split) — not test evidence", "series": series, "best_round_by_selection": best[-1] if best else None}


def _historical() -> dict[str, Any]:
    relative = f"{evidence.EVAL_DIR}/historical_frozen_centralized_references.json"
    return json.loads(evidence._verified_bytes(relative)) | {"source": relative, "sha256": evidence._hash_manifest()[relative]}


def _dataset_note(index: dict[str, Any], name: str) -> dict[str, Any]:
    d = index["datasets"][name]
    return {"claim_label": d["claim_label"], "clusters": d["clusters"], "windows": d["windows"], "source": d["source"]}


def comparability_audit(index: dict[str, Any], hist: dict[str, Any]) -> dict[str, Any]:
    """Read-only audit of what may and may not be compared between the historical centralized V2 and the federated V2 models."""
    rows = []
    for dataset, key in (("INTERNAL_TEST", "internal_test"), ("INCART", "incart")):
        fed = next(m for m in index["datasets"][dataset]["models"] if m["model_id"] == "V2_FEDAVG_IID")
        central = hist[f"MODEL_V2_FINAL_{key}"]
        rows.append({"dataset": dataset, "centralized_V2_AUPRC": central["AUPRC"], "federated_V2_FedAvg_IID_AUPRC": fed["point"]["AUPRC"],
                     "AUPRC_difference_federated_minus_centralized": fed["point"]["AUPRC"] - central["AUPRC"], "centralized_V2_AUROC": central["AUROC"],
                     "federated_V2_FedAvg_IID_AUROC": fed["point"]["AUROC"], "AUROC_difference_federated_minus_centralized": fed["point"]["AUROC"] - central["AUROC"],
                     "derived_subtraction": True, "paired_ci_available": False})
    checks = [
        {"item": "Same model family", "status": "SAME", "detail": "Both are the V2 TCN-mean architecture (MODEL_V2_FINAL vs FL V2 models)."},
        {"item": "Same evaluation windows / labels", "status": "SAME", "detail": "Population report records identical ordered example ids across all 20 FL models; V2-010 prediction tables for the centralized V2 model hold 2157 (INTERNAL_TEST) and 26864 (INCART) rows, equal to these populations."},
        {"item": "Same evaluation pass", "status": "DIFFERENT", "detail": "Centralized values are historical frozen references; they were NOT re-run in the one-shot FL evaluation."},
        {"item": "Threshold-free metrics only", "status": "SAME", "detail": "AUPRC and AUROC do not depend on the decision threshold or calibration; F1/precision/recall were evaluated under different thresholds/calibration and are not compared."},
        {"item": "Training procedure", "status": "DIFFERENT", "detail": "Centralized: pooled training. Federated: 8 clients, 50 rounds, FedAvg; optimisation budget and selection path differ."},
        {"item": "Paired uncertainty", "status": "NOT_AVAILABLE", "detail": "No paired patient-cluster bootstrap exists between a centralized and a federated model; differences below are point differences with no interval."},
        {"item": "Dataset exposure", "status": "LIMITED", "detail": "INTERNAL_TEST is federated-lineage held-out but not project-globally unseen (6 clusters); INCART is a post-freeze second look on a project-exposed dataset."}]
    interpretations = [
        {"id": "I1", "reading": "Near parity on INTERNAL_TEST", "support": "Both AUPRC values exceed 0.998 (ceiling region); the point difference is in the fourth decimal.", "limit": "6 clusters; ceiling effects make small differences uninformative; no paired interval."},
        {"id": "I2", "reading": "Federated V2 higher than centralized on INCART", "support": "Point AUPRC/AUROC of the federated model exceed the centralized reference.", "limit": "Different training/selection paths, no paired interval, project-exposed dataset; cannot be read as federated superiority."},
        {"id": "I3", "reading": "Direction differs by dataset", "support": "Federated is lower on INTERNAL_TEST and higher on INCART.", "limit": "Opposite signs with no uncertainty are consistent with noise or dataset-specific effects; no causal explanation is offered."},
        {"id": "I4", "reading": "No claim that FL is better or worse than centralized training", "support": "Evidence supports 'comparable on these frozen evaluations'.", "limit": "A designed paired comparison with matched budgets would be needed to say more."}]
    return {"rows": rows, "checks": checks, "interpretations": interpretations, "verdict": "DESCRIPTIVE POINT COMPARISON ONLY — NO SUPERIORITY OR NON-INFERIORITY CLAIM"}


LIVE = "reports/final_showcase/live_link"


def live_link_summary() -> dict[str, Any] | None:
    """Recorded evidence of the opt-in live-monitored SITE_00 run (and its separate synthetic evaluation), if present."""
    result_path, eval_path = ROOT / LIVE / "live_link_result.json", ROOT / LIVE / "synth_eval/synth_fl_eval_results.json"
    if not result_path.exists():
        return None
    result = json.loads(result_path.read_text())
    summary: dict[str, Any] = {"source": f"{LIVE}/live_link_result.json", "sha256": _sha(result_path.read_bytes()), "phase": result["phase"], "status": result.get("status"), "run_id": result.get("run_id"),
                               "candidate_ids": result.get("candidate_ids"), "candidate_state_digest": result.get("candidate_state_digest"), "canonical_candidate_digest": result.get("canonical_candidate_digest"),
                               "candidate_digest_equals_canonical": result.get("candidate_digest_equals_canonical"), "parity": result.get("parity"), "monitoring": result.get("monitoring"),
                               "blocked": result.get("blocked"), "link_label": result.get("link_label"), "inference_service": result.get("inference_service")}
    if eval_path.exists():
        live, canon = json.loads(eval_path.read_text()), json.loads((ROOT / SYNTH).read_text())
        summary["synthetic_evaluation"] = {"source": f"{LIVE}/synth_eval/synth_fl_eval_results.json", "sha256": _sha(eval_path.read_bytes()), "evaluated_source": live["evaluated_source"],
                                           "state_digests": live["state_digests"], "state_digests_equal_canonical": live["state_digests_equal_canonical"],
                                           "pooled_metrics_equal_canonical_run": all(live["results"][k]["pooled"] == canon["results"][k]["pooled"] for k in live["results"]),
                                           "round_3_AUPRC": live["results"]["round_3_candidate"]["pooled"]["AUPRC"], "round_3_AUROC": live["results"]["round_3_candidate"]["pooled"]["AUROC"]}
    return summary


@lru_cache(maxsize=1)
def bundle() -> dict[str, Any]:
    index = evidence.fl_eval_index()
    hist = _historical()
    logs = {f"{a}|{c}": round_log(a, c) for (a, c) in ROUND_LOGS}
    synth_path = ROOT / SYNTH
    synth = json.loads(synth_path.read_text()) if synth_path.exists() else None
    models = []
    for dataset, d in index["datasets"].items():
        for m in d["models"]:
            models.append({"dataset": dataset, **{k: m[k] for k in ("model_id", "generation", "algorithm", "condition", "mu", "checkpoint_sha256")}, "point": m["point"], "ci_95": m["ci_95"]})
    return {"schema_version": SCHEMA, "lanes": LANES, "datasets": {n: _dataset_note(index, n) for n in index["datasets"]}, "models": models,
            "comparisons": {n: d["comparisons"] for n, d in index["datasets"].items()}, "historical_centralized": hist, "round_logs": logs,
            "comparability": comparability_audit(index, hist), "limitations": index["limitations"], "live_link": live_link_summary(),
            "synthetic": {"source": SYNTH, "sha256": _sha(synth_path.read_bytes()), "boundary_label": synth["boundary_label"], "protocol_sha256": synth["protocol_sha256"],
                          "method_freeze_commit": synth["method_freeze_commit"], "candidate_digest": synth["candidate_digest"], "state_digests": synth["state_digests"],
                          "holdout_windows": synth["holdout_windows"],
                          "states": {k: {"pooled": {m: v for m, v in r["pooled"].items() if m != "undefined"}, "undefined": r["pooled"]["undefined"], "participant_macro_F1": r["participant_macro_F1"]["value"],
                                         "uncertainty": r["uncertainty"], "per_participant": {c: {m: v for m, v in p.items() if m != "undefined"} for c, p in r["per_participant"].items()},
                                         "training_buffer_pooled": {m: r["training_buffer_secondary"]["pooled"][m] for m in ("AUPRC", "AUROC", "F1", "accuracy", "BCE", "windows")}, "curves": r["curves"]}
                                     for k, r in synth["results"].items()}} if synth else None}
