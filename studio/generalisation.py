# ruff: noqa: E501
"""The Generalisation lane: every committed global state of a run, AND the unchanged frozen V2 checkpoint, are scored on the unseen G1 synthetic cohort.

* A second ``EvaluationObserver`` (same isolation, digest verification, fixed 0.5 threshold, no calibration) mirrors the primary observer's submissions.
* The frozen V2 baseline is scored ONCE per process/cohort (cached on disk under its own run id) and compared with every round by a paired participant-cluster bootstrap
  (comparator = frozen V2, endpoint = the round; difference = round - V2) using the protocol's predeclared replicates and seed.
* Nothing here trains, selects a round, tunes a threshold, calibrates, or promotes anything. Every number comes from stored predictions and is recomputable."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from fl10 import metrics as fl10_metrics
from fl10.runner import atomic_write
from studio import g1_cohort, v2_init
from studio.constants import (
    BASELINE_RUN_ID,
    G1_CLAIM_BOUNDARY,
    G1_COHORT_USE_LABEL,
    GENERALISATION_OBSERVER_ID,
    GENERALISATION_SCHEMA,
)
from studio.observer import EvaluationObserver, read_predictions, round_key
from studio.records import GeneralisationRecord

HEADLINE = ("AUPRC", "AUROC", "F1", "specificity", "recall", "BCE", "Brier")
LOWER_IS_BETTER = {"BCE", "Brier"}
BASELINE_LABEL = "FROZEN V2 (MODEL_V2_FINAL) — unchanged, zero-shot on this task"
BASELINE_DETAIL = ("The unchanged pretrained V2 checkpoint, scored on the same windows with the same fixed 0.5 threshold. It was trained on the AAMI-SVF real-ECG task, so on this synthetic "
                   "engineering-event target it is a transfer reference, not a like-for-like trained competitor.")


def _light(record: GeneralisationRecord | None) -> dict[str, Any] | None:
    return None if record is None else record.light()


def _fmt(value: float | None, digits: int = 3) -> str:
    return "undefined" if value is None else f"{value:.{digits}f}"


class GeneralisationLane:
    def __init__(self, root: Path, primary: EvaluationObserver, *, holdout_provider: Any = g1_cohort.load) -> None:
        self.root = Path(root)
        self._provider = holdout_provider
        self._baseline_lock = threading.Lock()
        self._baseline_started = False
        self._pair_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="studio-generalisation-pairs")
        self.observer = EvaluationObserver(self.root, holdout_provider=holdout_provider, lane_dir="eval_g1", record_cls=GeneralisationRecord, cohort_id=g1_cohort.COHORT_ID,
                                           on_complete=self._after, before_submit=self.ensure_baseline)
        primary.add_mirror(self.observer)
        self._baseline_audit: dict[str, Any] | None = None

    # ---- frozen V2 baseline ---------------------------------------------------------------------------------------------
    def ensure_baseline(self) -> None:
        """Idempotent. Queues the unchanged V2 checkpoint (digest-verified) for scoring on G1; a cached record from an earlier process is reused as-is."""
        with self._baseline_lock:
            if self._baseline_started:
                return
            self._baseline_started = True
        try:
            state, audit = v2_init.load_v2_final()
            self._baseline_audit = audit
            self.observer.submit(run_id=BASELINE_RUN_ID, run_length=0, round_id=0, state=state, expected_digest=audit["state_sha256"], record_extra={"subject": "FROZEN_V2_BASELINE"}, mirror=False)
        except Exception:
            with self._baseline_lock:
                self._baseline_started = False       # retried on the next submission; the failure is never turned into a number
            raise

    def baseline(self) -> GeneralisationRecord | None:
        return self.observer.get(BASELINE_RUN_ID, 0)  # type: ignore[return-value]

    # ---- paired comparison against the baseline -----------------------------------------------------------------------------
    def pair_path(self, run_id: str, round_id: int) -> Path:
        return self.observer.run_dir(run_id) / f"paired_vs_v2_{round_key(round_id)}.json"

    def _after(self, run_id: str, round_id: int) -> None:
        self._pool.submit(self._pair_everything)

    def _pair_everything(self) -> None:
        with self._pair_lock:
            base = self.baseline()
            if base is None or base.evaluation_status != "COMPLETED":
                return
            for run_id in list(self.observer._records):
                if run_id == BASELINE_RUN_ID:
                    continue
                for record in self.observer.records(run_id):
                    if record.evaluation_status == "COMPLETED" and not self.pair_path(run_id, record.round_id).exists():
                        self._pair_one(base, record)

    def _pair_one(self, base: GeneralisationRecord, record: GeneralisationRecord) -> None:
        root_b, root_r = self.observer.run_dir(BASELINE_RUN_ID), self.observer.run_dir(record.run_id)
        ob, yb, zb = read_predictions((root_b / base.prediction_artifact_reference.path).read_bytes())    # type: ignore[union-attr]
        orr, yr, zr = read_predictions((root_r / record.prediction_artifact_reference.path).read_bytes())  # type: ignore[union-attr]
        if not (np.array_equal(ob, orr) and np.array_equal(yb, yr)):
            return                                                                                       # different populations: never compared
        boot = self._provider().protocol["uncertainty"]
        paired = fl10_metrics.paired_cluster_bootstrap(ob, yb, zb, zr, replicates=boot["replicates"], seed=boot["seed"])
        body = {"comparator": "FROZEN_V2", "endpoint": round_key(record.round_id), "difference": "round minus frozen V2", "cohort_id": g1_cohort.COHORT_ID, "cohort_use": G1_COHORT_USE_LABEL, **paired,
                "identical_predictions": bool(np.array_equal(zb, zr))}
        atomic_write(self.pair_path(record.run_id, record.round_id), (json.dumps(body, indent=1, sort_keys=True) + "\n").encode())
        with self.observer._lock:
            self.observer._revision[record.run_id] = self.observer._revision.get(record.run_id, 0) + 1

    def paired(self, run_id: str, round_id: int) -> dict[str, Any] | None:
        path = self.pair_path(run_id, round_id)
        return json.loads(path.read_text()) if path.exists() else None

    # ---- payloads -----------------------------------------------------------------------------------------------------------
    def cohort_summary(self) -> dict[str, Any]:
        manifest = json.loads((g1_cohort.ROOT / g1_cohort.MANIFEST).read_text())
        entries = manifest["participants"]
        positives = sum(int(e["counts"].get("synthetic_positive", 0)) for e in entries)
        windows = sum(int(e["counts"].get("trainable", 0)) for e in entries)
        loaded = g1_cohort._CACHE
        return {"cohort_id": g1_cohort.COHORT_ID, "label": G1_COHORT_USE_LABEL, "detail": g1_cohort.COHORT_USE_DETAIL, "participants": len(entries), "windows": windows, "positive_windows": positives,
                "participant_ids": [e["participant_id"] for e in entries], "site_conditions": sorted({e["site_condition"] for e in entries}), "manifest_sha256": loaded.manifest_sha256 if loaded else None,
                "separation": loaded.separation if loaded else None, "separation_note": None if loaded else "the zero-overlap proof is computed when the cohort is first built in this server process"}

    def revision(self, run_id: str) -> int:
        return self.observer.revision(run_id) + self.observer.revision(BASELINE_RUN_ID)

    def bundle(self, run_id: str, *, run_length: int, init: dict[str, Any] | None) -> dict[str, Any]:
        base = self.baseline()
        records = self.observer.records(run_id)
        by_round = {r.round_id: r for r in records}
        rounds = []
        for r in range(run_length + 1):
            rec = by_round.get(r)
            pair = self.paired(run_id, r) if rec is not None else None
            rounds.append({"round_id": r, "record": _light(rec), "paired_vs_v2": None if pair is None else {k: pair[k] for k in ("clusters", "replicates", "seed", "method", "multiplicity", "metrics", "identical_predictions")}})
        r0, b = by_round.get(0), base
        integrity: dict[str, Any] = {"r0_digest_equals_frozen_v2": None, "r0_predictions_equal_frozen_v2": None}
        if r0 is not None and b is not None:
            integrity["r0_digest_equals_frozen_v2"] = r0.global_state_digest == b.global_state_digest
            if r0.prediction_artifact_reference and b.prediction_artifact_reference:
                integrity["r0_predictions_equal_frozen_v2"] = r0.prediction_artifact_reference.sha256 == b.prediction_artifact_reference.sha256
        out = {"schema_version": GENERALISATION_SCHEMA, "run_id": run_id, "run_length": run_length, "observer_id": GENERALISATION_OBSERVER_ID, "claim_boundary": G1_CLAIM_BOUNDARY, "threshold": 0.5, "calibration": "NONE",
               "base_model": init or {"model_id": v2_init.INIT_FRESH, "label": v2_init.INIT_LABELS[v2_init.INIT_FRESH]}, "cohort": self.cohort_summary(),
               "baseline": {"label": BASELINE_LABEL, "detail": BASELINE_DETAIL, "record": _light(b), "state_sha256": b.global_state_digest if b else None, "audit": self._baseline_audit},
               "rounds": rounds, "integrity": integrity, "metrics_order": list(HEADLINE), "lower_is_better": sorted(LOWER_IS_BETTER), "revision": self.revision(run_id)}
        out["interpretation"] = interpret(out)
        return out

    def curves(self, run_id: str, round_id: int) -> dict[str, Any]:
        rec, base = self.observer.get(run_id, round_id), self.baseline()
        if rec is None or rec.curve_artifact_reference is None:
            return {"run_id": run_id, "round_id": round_id, "available": False, "reason": "this round has not been evaluated on the G1 cohort yet; nothing is invented"}
        out: dict[str, Any] = {"run_id": run_id, "round_id": round_id, "available": True, "round": json.loads((self.observer.run_dir(run_id) / rec.curve_artifact_reference.path).read_text()), "baseline": None}
        if base is not None and base.curve_artifact_reference is not None:
            out["baseline"] = json.loads((self.observer.run_dir(BASELINE_RUN_ID) / base.curve_artifact_reference.path).read_text())
        return out

    def participants(self, run_id: str, round_id: int) -> dict[str, Any]:
        rec, base = self.observer.get(run_id, round_id), self.baseline()
        if rec is None or rec.participant_metrics is None:
            return {"run_id": run_id, "round_id": round_id, "available": False}
        return {"run_id": run_id, "round_id": round_id, "available": True, "round": rec.participant_metrics, "baseline": None if base is None else base.participant_metrics}

    def settled(self, run_id: str, rounds: int) -> bool:
        """Every round of the run and frozen V2 have finished (completed or failed) and every completed round has its paired comparison."""
        records = self.observer.records(run_id)
        base = self.baseline()
        if len(records) != rounds + 1 or base is None or any(r.evaluation_status in ("QUEUED", "EVALUATING") for r in [base, *records]):
            return False
        if base.evaluation_status != "COMPLETED":
            return True
        return all(r.evaluation_status != "COMPLETED" or self.pair_path(run_id, r.round_id).exists() for r in records)

    def wait_settled(self, run_id: str, rounds: int, timeout: float = 1800.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.settled(run_id, rounds):
                return True
            time.sleep(0.5)
        return False

    def close(self) -> None:
        self.observer.close()
        self._pool.shutdown(wait=False, cancel_futures=True)


def interpret(bundle: dict[str, Any]) -> list[str]:
    """Plain, number-derived statements about the latest evaluated round versus frozen V2. No verdict words beyond the measured sign; nominal intervals are labelled as such."""
    base = bundle["baseline"]["record"]
    done = [r for r in bundle["rounds"] if r["record"] and r["record"]["evaluation_status"] == "COMPLETED"]
    if base is None or base["evaluation_status"] != "COMPLETED":
        return ["Frozen V2 has not finished scoring on the unseen cohort yet; no comparison is shown until it has."]
    if not done:
        return ["No round has finished scoring on the unseen cohort yet."]
    latest = done[-1]
    metrics, bm = latest["record"]["metric_result"], base["metric_result"]
    lines = [f"R{latest['round_id']:02d} versus frozen V2 on the unseen cohort (fixed 0.5 threshold, no calibration):"]
    pair = latest["paired_vs_v2"]
    for name in ("AUPRC", "AUROC", "specificity", "BCE", "Brier"):
        a, b = bm.get(name), metrics.get(name)
        if a is None or b is None:
            lines.append(f"{name}: undefined for at least one model.")
            continue
        d = b - a
        direction = "lower" if d < 0 else "higher" if d > 0 else "equal"
        favourable = (d < 0) == (name in LOWER_IS_BETTER) and d != 0
        text = f"{name}: round {_fmt(b)} vs V2 {_fmt(a)} ({'+' if d >= 0 else ''}{_fmt(d)}, {direction}{'; favourable direction' if favourable else ''})."
        if pair is not None:
            iv = pair["metrics"].get(name, {}).get("difference_interval") or {}
            if iv.get("lower") is not None:
                text += f" Nominal participant-cluster interval (95 percent) of the difference [{_fmt(iv['lower'])}, {_fmt(iv['upper'])}], not a significance test."
        lines.append(text)
    if bundle["integrity"].get("r0_predictions_equal_frozen_v2"):
        lines.append("R0 predictions are identical to frozen V2 (the run started from the pretrained weights).")
    lines.append("This measures the synthetic engineering-event task on unseen synthetic participants. It is not AAMI-SVF performance and not clinical evidence.")
    return lines
