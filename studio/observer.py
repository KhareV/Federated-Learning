# ruff: noqa: E501
"""Run-scoped checkpoint evaluation observer.

``submit`` receives an immutable copy of a committed global state, verifies its digest, queues it, and ONE background worker scores it on the frozen
diagnostic holdout with the unchanged FL10 evaluator. The observer never trains, never mutates a state, never changes aggregation, never tunes the
threshold (fixed 0.5), never calibrates, and never selects a round. Training does not wait for evaluation: results appear as they finish and anything
unfinished stays QUEUED/EVALUATING; a failure is stored and shown, never replaced by a number."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import queue
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from federated.model_adapter import deserialize_state, serialize_state
from federated.model_v2_fl import state_sha
from fl10 import evaluate as ev
from fl10 import metrics as fl10_metrics
from fl10.runner import atomic_write
from studio.constants import COHORT_USE_LABEL, EVAL_PROTOCOL_ID, MAX_QUEUE, OBSERVER_ID
from studio.holdout_cache import FrozenHoldout
from studio.holdout_cache import load as load_holdout
from studio.isolated_eval import evaluate_isolated, prepare_template
from studio.records import ArtifactRef, EvaluationRecord, Failure


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def round_key(round_id: int) -> str:
    return f"R{round_id:02d}"


def predictions_csv(holdout: FrozenHoldout, logits: np.ndarray) -> bytes:
    """Full-precision (repr) logits so every metric can be recomputed bit-for-bit from this file."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["holdout_id", "participant_id", "window_index", "label", "logit"])
    n = 0
    for d in holdout.datasets:
        for i in range(len(d.labels)):
            writer.writerow([d.client_id, d.participant_id, i, int(d.labels[i]), repr(float(logits[n]))])
            n += 1
    return buf.getvalue().encode()


def read_predictions(data: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(io.StringIO(data.decode())))
    return (np.array([r["participant_id"] for r in rows]), np.array([int(r["label"]) for r in rows]), np.array([float(r["logit"]) for r in rows], dtype=np.float64))


class EvaluationObserver:
    def __init__(self, root: Path, *, holdout_provider: Callable[[], FrozenHoldout] = load_holdout, evaluator: Callable[..., dict[str, Any]] | None = None,
                 lane_dir: str = "eval", record_cls: type[EvaluationRecord] = EvaluationRecord, cohort_id: str | None = None,
                 on_complete: Callable[[str, int], None] | None = None, before_submit: Callable[[], None] | None = None) -> None:
        """``lane_dir`` / ``record_cls`` / ``cohort_id`` let a second observer score the same committed states on a different cohort (the Generalisation lane) with the same
        isolation, digest verification and fixed threshold. The defaults are the original diagnostic lane, unchanged."""
        self.root = Path(root)
        self._lane_dir = lane_dir
        self._record_cls = record_cls
        self._cohort_id_override = cohort_id
        self._on_complete = on_complete
        self._before_submit = before_submit
        self._mirrors: list[EvaluationObserver] = []
        self._holdout_provider = holdout_provider
        prepare_template()          # the only RNG-consuming model construction happens here, at construction time, before any run can be training
        self._evaluator = evaluator or evaluate_isolated
        self._records: dict[str, dict[int, EvaluationRecord]] = {}
        self._revision: dict[str, int] = {}
        self._pairs: dict[str, tuple[int, int]] = {}
        self._queue: queue.Queue[tuple[str, int, bytes] | None] = queue.Queue(maxsize=MAX_QUEUE)
        self._lock = threading.RLock()
        self._idle = threading.Condition(self._lock)
        self._pending = 0
        self._worker = threading.Thread(target=self._loop, name="studio-evaluation-observer", daemon=True)
        self._worker.start()

    # ---- paths -------------------------------------------------------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id / self._lane_dir

    def _round_dir(self, run_id: str, round_id: int) -> Path:
        return self.run_dir(run_id) / round_key(round_id)

    # ---- public API --------------------------------------------------------------------------------------------------
    def declare_pair(self, run_id: str, comparator: int, endpoint: int) -> None:
        with self._lock:
            self._pairs[run_id] = (comparator, endpoint)

    def add_mirror(self, other: EvaluationObserver) -> None:
        """Every state submitted here is also submitted (same private copy semantics) to ``other``; a mirror can never change this observer's records or training."""
        self._mirrors.append(other)

    def submit(self, *, run_id: str, run_length: int, round_id: int, state: dict[str, np.ndarray], expected_digest: str, candidate_id: str | None = None,
               record_extra: dict[str, Any] | None = None, mirror: bool = True) -> EvaluationRecord:
        """Queue a committed state. The state is serialized (an immutable private copy) before returning, so later mutation by the caller cannot affect scoring."""
        if self._before_submit is not None:
            self._before_submit()
        blob = serialize_state(state)
        digest_ok = state_sha(OrderedDict(state)) == expected_digest
        queued = self._record_cls(run_id=run_id, run_length=run_length, round_id=round_id, global_state_digest=expected_digest, candidate_id=candidate_id, cohort_id=self._cohort(),
                                  evaluation_status="QUEUED" if digest_ok else "FAILED", evaluation_queued_at=_now(), **(record_extra or {}),
                                  failure=None if digest_ok else Failure(code="STATE_DIGEST_MISMATCH", message="submitted state does not hash to the committed digest; not scored"))
        with self._lock:
            if run_id not in self._records:
                self._load_persisted(run_id)
            existing = self._records.get(run_id, {}).get(round_id)
            if existing is not None:
                if existing.global_state_digest != expected_digest:
                    raise ValueError("ROUND_ALREADY_SUBMITTED_WITH_DIFFERENT_STATE")
                return existing
            self._store(queued)
            if digest_ok:
                try:
                    self._queue.put_nowait((run_id, round_id, blob))
                    self._pending += 1
                except queue.Full:
                    self._store(queued.model_copy(update={"evaluation_status": "FAILED", "failure": Failure(code="EVALUATION_QUEUE_FULL", message="bounded evaluation queue is full")}))
        if mirror:
            for other in self._mirrors:
                with contextlib.suppress(ValueError):       # a mirror that already holds this round with a different state keeps its own record; the primary lane is unaffected
                    other.submit(run_id=run_id, run_length=run_length, round_id=round_id, state=state, expected_digest=expected_digest, candidate_id=candidate_id)
        return queued

    def records(self, run_id: str) -> list[EvaluationRecord]:
        with self._lock:
            if run_id not in self._records:
                self._load_persisted(run_id)
            return [self._records.get(run_id, {})[k] for k in sorted(self._records.get(run_id, {}))]

    def get(self, run_id: str, round_id: int) -> EvaluationRecord | None:
        with self._lock:
            if run_id not in self._records:
                self._load_persisted(run_id)
            return self._records.get(run_id, {}).get(round_id)

    def revision(self, run_id: str) -> int:
        with self._lock:
            return self._revision.get(run_id, 0)

    def wait_idle(self, timeout: float = 600.0) -> bool:
        end = time.monotonic() + timeout
        with self._idle:
            while self._pending > 0:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    return False
                self._idle.wait(remaining)
        return True

    def close(self) -> None:
        self._queue.put(None)

    # ---- persistence -------------------------------------------------------------------------------------------------
    def _store(self, record: EvaluationRecord) -> None:
        with self._lock:
            self._records.setdefault(record.run_id, {})[record.round_id] = record
            self._revision[record.run_id] = self._revision.get(record.run_id, 0) + 1
            directory = self._round_dir(record.run_id, record.round_id)
            atomic_write(directory / "record.json", (json.dumps(record.model_dump(mode="json"), indent=1, sort_keys=True) + "\n").encode())

    def _load_persisted(self, run_id: str) -> None:
        base = self.run_dir(run_id)
        if not base.is_dir():
            return
        for path in sorted(base.glob("R*/record.json")):
            record = self._record_cls.model_validate_json(path.read_text())
            if record.evaluation_status in ("QUEUED", "EVALUATING"):   # interrupted by a restart: never silently resumed or invented
                record = record.model_copy(update={"evaluation_status": "FAILED", "failure": Failure(code="INTERRUPTED_BY_RESTART", message="evaluation was interrupted; the state is not re-scored automatically")})
            self._records.setdefault(run_id, {})[record.round_id] = record
        self._revision[run_id] = self._revision.get(run_id, 0) + 1

    # ---- worker ------------------------------------------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            run_id, round_id, blob = item
            try:
                self._evaluate(run_id, round_id, blob)
            except Exception as error:  # a failure is recorded and displayed, never swallowed into a number
                with self._lock:
                    current = self._records[run_id][round_id]
                    self._store(current.model_copy(update={"evaluation_status": "FAILED", "evaluation_completed_at": _now(),
                                                           "failure": Failure(code=getattr(error, "code", type(error).__name__), message=str(error)[:300])}))
            finally:
                with self._idle:
                    self._pending -= 1
                    self._idle.notify_all()
            self._maybe_pair(run_id)
            if self._on_complete is not None:
                with contextlib.suppress(Exception):       # a derived-comparison failure never touches the stored evaluation records
                    self._on_complete(run_id, round_id)

    def _evaluate(self, run_id: str, round_id: int, blob: bytes) -> None:
        with self._lock:
            queued = self._records[run_id][round_id]
            self._store(queued.model_copy(update={"evaluation_status": "EVALUATING", "evaluation_started_at": _now()}))
        state = deserialize_state(blob)
        if state_sha(OrderedDict(state)) != queued.global_state_digest:     # verified again on the private copy, before scoring
            raise ev.Fl10EvalError("STATE_DIGEST_MISMATCH", round_key(round_id))
        holdout = self._holdout_provider()
        name = round_key(round_id)
        result = self._evaluator({name: state}, list(holdout.datasets), replicates=0, seed=0)
        logits = result["_logits"][name]
        if not np.isfinite(logits).all():
            raise ev.Fl10EvalError("NONFINITE_LOGITS", name)
        block = result["states"][name]
        pooled = block["pooled"]
        participants = {pid: {k: v for k, v in m.items() if k != "histogram"} for pid, m in block["participants"].items()}
        directory = self._round_dir(run_id, round_id)
        pred = predictions_csv(holdout, logits)
        curves = (json.dumps(block["curves"], sort_keys=True) + "\n").encode()
        atomic_write(directory / "predictions.csv", pred)
        atomic_write(directory / "curves.json", curves)
        source = _sha(json.dumps({"state": queued.global_state_digest, "protocol_sha256": holdout.protocol_sha256, "manifest_sha256": holdout.manifest_sha256, "threshold": fl10_metrics.THRESHOLD,
                                  "observer": OBSERVER_ID}, sort_keys=True).encode())
        with self._lock:
            current = self._records[run_id][round_id]
            self._store(current.model_copy(update={
                "evaluation_status": "COMPLETED", "evaluation_completed_at": _now(), "windows": holdout.windows, "metric_result": pooled, "participant_metrics": participants,
                "participant_summary": {"participant_macro_F1": block["participant_macro_F1"], "participants_defined": block["participants_defined"], "participants_undefined": block["participants_undefined"]},
                "confusion_counts": {k: int(pooled[k]) for k in ("TP", "FP", "TN", "FN", "predicted_positives", "predicted_negatives")},
                "curve_artifact_reference": ArtifactRef(path=f"{round_key(round_id)}/curves.json", sha256=_sha(curves)),
                "prediction_artifact_reference": ArtifactRef(path=f"{round_key(round_id)}/predictions.csv", sha256=_sha(pred)), "source_digest": source}))

    def _maybe_pair(self, run_id: str) -> None:
        pair = self._pairs.get(run_id)
        if pair is None or (self.run_dir(run_id) / "paired.json").exists():
            return
        a, b = (self.get(run_id, pair[0]), self.get(run_id, pair[1]))
        if a is None or b is None or a.evaluation_status != "COMPLETED" or b.evaluation_status != "COMPLETED":
            return
        holdout = self._holdout_provider()
        base = self.run_dir(run_id)
        oa, ya, za = read_predictions((base / a.prediction_artifact_reference.path).read_bytes())  # type: ignore[union-attr]
        ob, yb, zb = read_predictions((base / b.prediction_artifact_reference.path).read_bytes())  # type: ignore[union-attr]
        if not (np.array_equal(oa, ob) and np.array_equal(ya, yb)):
            return
        boot = holdout.protocol["uncertainty"]
        paired = fl10_metrics.paired_cluster_bootstrap(oa, ya, za, zb, replicates=boot["replicates"], seed=boot["seed"])
        body = {"comparator": round_key(pair[0]), "endpoint": round_key(pair[1]), "cohort_use": COHORT_USE_LABEL, "evaluation_protocol_id": EVAL_PROTOCOL_ID, **paired}
        atomic_write(base / "paired.json", (json.dumps(body, indent=1, sort_keys=True) + "\n").encode())
        with self._lock:
            self._revision[run_id] = self._revision.get(run_id, 0) + 1

    def _cohort(self) -> str:
        return self._cohort_id_override or _default_cohort_id()

    def paired(self, run_id: str) -> dict[str, Any] | None:
        path = self.run_dir(run_id) / "paired.json"
        return json.loads(path.read_text()) if path.exists() else None


def _default_cohort_id() -> str:
    from fl10 import holdout

    return holdout.COHORT_ID
