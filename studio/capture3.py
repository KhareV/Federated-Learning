# ruff: noqa: E501
"""Non-invasive observation of the frozen 3-round product federation.

Instance-level wrappers (the same pattern as the Observatory acceptance capture) are installed on ONE ``FederationService``. They only READ: the committed
states and digests, the per-client optimizer diagnostics (and, read-only, the per-batch hooks) that the unchanged engine produces. They never alter the
request contract, the events, the training, the aggregation or the candidate. Each committed state is handed to the evaluation observer as a private copy.
The result is a run report in the SAME schema ``fl10.runner`` writes, so one figure/table builder serves both run lengths."""

from __future__ import annotations

import contextlib
import json
import logging
import math
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from federated.wearable_fl_runner_v1 import (
    BASE_SEED,
    BATCH_SIZE,
    LEARNING_RATE,
    POS_WEIGHT,
    WEIGHT_DECAY,
    state_info,
)
from federated.wearable_fl_system_v1 import EXPERIMENT_ID as FL_EXPERIMENT_ID
from fl10.runner import aggregate_update_norm, atomic_write, frozen_progression, write_tables
from product.federation.base import AggregationMode, Algorithm, RunType
from product.federation.service import FederationService, RunContext
from studio.observer import EvaluationObserver

LOG = logging.getLogger("nhm.studio.capture")
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reports/model_v2/v2_fl_005/cohort_manifest_run.json"
ENGINE = "product.federation.service.FederationService (frozen 3-round contract; unchanged)"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ProductRunCapture:
    def __init__(self, service: FederationService, observer: EvaluationObserver, root: Path) -> None:
        self.service, self.observer, self.root = service, observer, Path(root)
        self._lock = threading.RLock()
        self._reports: dict[str, dict[str, Any]] = {}
        self._pending: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
        self._manifest: dict[str, dict[str, Any]] | None = None
        self._frozen = frozen_progression()

    # ---- install -----------------------------------------------------------------------------------------------------
    def install(self) -> None:
        service = self.service
        original_round, original_train = service._round, service._train_sync
        original_finish, original_fail = service._finish, service._fail
        capture = self

        async def observing_round(ctx: RunContext, cohort: Any, coordinator: Any, tracker: Any, round_id: int, state: dict[str, np.ndarray], init_digest: str, spec_sha: str) -> dict[str, np.ndarray]:
            live = ctx.run_type is RunType.LIVE_RUN
            if live:
                capture._guard(capture._begin_round, ctx, round_id, state)
            started = time.perf_counter()
            new_state = await original_round(ctx, cohort, coordinator, tracker, round_id, state, init_digest, spec_sha)
            if live:
                capture._guard(capture._end_round, ctx, coordinator, round_id, state, new_state, time.perf_counter() - started)
            return new_state

        def observing_train(adapter: Any, round_id: int, digest: str) -> None:
            run_id = service._active
            client = getattr(getattr(adapter, "_buffer", None), "client_id", None)
            if run_id is None or client is None:
                original_train(adapter, round_id, digest)
                return
            from api.observatory_batch_capture import BatchCapture

            started = time.perf_counter()
            with BatchCapture() as batches:
                original_train(adapter, round_id, digest)
            duration = time.perf_counter() - started
            try:
                capture._record_client(run_id, round_id, client, adapter.diagnostics(), batches.batches, duration)
            except Exception:  # an observer failure never changes a completed optimizer call
                return

        def observing_finish(ctx: RunContext) -> None:
            original_finish(ctx)
            if ctx.run_type is RunType.LIVE_RUN:
                try:
                    capture._finish(ctx)
                except Exception:
                    return

        def observing_fail(ctx: RunContext, tracker: Any, error: Exception) -> None:
            try:
                original_fail(ctx, tracker, error)
            finally:
                if ctx.run_type is RunType.LIVE_RUN:
                    with contextlib.suppress(Exception):
                        capture._fail(ctx, error)

        service._round = observing_round  # type: ignore[method-assign]
        service._train_sync = observing_train  # type: ignore[method-assign]
        service._finish = observing_finish  # type: ignore[method-assign]
        service._fail = observing_fail  # type: ignore[method-assign]

    # ---- helpers -----------------------------------------------------------------------------------------------------
    @staticmethod
    def _guard(function: Any, *args: Any) -> None:
        """The observer can never change the outcome of the observed run: any observation error is logged and the engine continues untouched."""
        try:
            function(*args)
        except Exception:
            LOG.exception("studio capture observation failed (the federation run is unaffected)")

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id / "run"

    def manifest(self) -> dict[str, dict[str, Any]]:
        if self._manifest is None:
            self._manifest = {c["client_id"]: c for c in json.loads(MANIFEST.read_text())["clients"]}
        return self._manifest

    def _report(self, ctx: RunContext) -> dict[str, Any]:
        with self._lock:
            if ctx.run_id not in self._reports:
                self._reports[ctx.run_id] = {
                    "run_id": ctx.run_id, "mode": "PRODUCT_3R", "status": "RUNNING", "git_commit": "UNKNOWN", "protocol_sha256": "UNKNOWN", "experiment_id": "NHM_PRODUCT_FEDERATION_3_ROUND",
                    "federation_engine": ENGINE, "engine": "PRODUCT_3R", "planned_rounds": ctx.planned_rounds, "started_at": _now(), "algorithm": ctx.algorithm.value, "secagg_mode": ctx.secagg_mode.value,
                    "settings": {"base_seed": BASE_SEED, "experiment_id_for_seeds": FL_EXPERIMENT_ID, "batch_size": BATCH_SIZE, "learning_rate": LEARNING_RATE, "weight_decay": WEIGHT_DECAY, "pos_weight": POS_WEIGHT,
                                 "optimizer": "AdamW (reset every local epoch)", "local_epochs": 1, "aggregation": "weighted FedAvg by accepted example count" if ctx.algorithm is Algorithm.FEDAVG else "FedProx configuration frozen by the product protocol"},
                    "environment": {}, "state_progression": {}, "rounds": [], "client_rounds": [], "batches": [], "updates": [], "training_cohort": self._cohort_summary()}
            return self._reports[ctx.run_id]

    def _cohort_summary(self) -> list[dict[str, Any]]:
        return [{"client_id": cid, "participant_id": c["participant_id"], "session_id": c["session_id"], "dataset_sha256": c["dataset_sha256"], "counts": c["counts"]} for cid, c in sorted(self.manifest().items())]

    def _begin_round(self, ctx: RunContext, round_id: int, state: dict[str, np.ndarray]) -> None:
        from federated.model_v2_fl import state_sha

        report = self._report(ctx)
        if round_id == 1 and "0" not in report["state_progression"]:
            digest = state_sha(state)
            report["state_progression"]["0"] = {**state_info(state), "committed_at": _now()}
            self.observer.declare_pair(ctx.run_id, 0, ctx.planned_rounds)
            self.observer.submit(run_id=ctx.run_id, run_length=ctx.planned_rounds, round_id=0, state=state, expected_digest=digest)
            self._persist(ctx, report)

    def _record_client(self, run_id: str, round_id: int, client: str, raw: dict[str, Any], batches: list[dict[str, Any]], duration: float) -> None:
        with self._lock:
            self._pending.setdefault((run_id, round_id), {})[client] = {"raw": dict(raw), "batches": [dict(b) for b in batches], "duration": duration}

    def _end_round(self, ctx: RunContext, coordinator: Any, round_id: int, old: dict[str, np.ndarray], new: dict[str, np.ndarray], duration: float) -> None:
        from federated.model_v2_fl import state_sha

        report = self._report(ctx)
        new_sha = ctx.committed[round_id]
        if state_sha(new) != new_sha:
            raise RuntimeError("COMMITTED_STATE_DIGEST_MISMATCH")
        base_sha = ctx.round_bases[round_id]
        pending = self._pending.pop((ctx.run_id, round_id), {})
        accepted = coordinator.accepted
        order = sorted(accepted)
        total = sum(int(accepted[c]["examples_seen"]) for c in order)
        weights = {c: int(accepted[c]["examples_seen"]) / total for c in order}
        manifest = self.manifest()
        cumulative_updates = len(report["updates"]) + len(order)
        cumulative_exposures = sum(r["examples_processed"] for r in report["client_rounds"]) + total
        round_bytes = 0
        losses: dict[str, float | None] = {}
        for client in order:
            info = pending.get(client, {})
            raw, cap = info.get("raw", {}), info.get("batches", [])
            counts = manifest[client]["counts"]
            mean_loss = raw.get("mean_loss_diagnostic_only")
            losses[client] = float(mean_loss) if mean_loss is not None and math.isfinite(float(mean_loss)) else None
            norm = raw.get("update_norm_diagnostic_only")
            bytes_ = raw.get("update_bytes")
            round_bytes += int(bytes_) if bytes_ is not None else 0
            blosses = [b["loss"] for b in cap]
            grads = [b["gradient_l2_norm"] for b in cap]
            report["client_rounds"].append({
                "run_id": ctx.run_id, "round": round_id, "client_id": client, "participant_id": manifest[client]["participant_id"], "dataset_id": manifest[client]["session_id"],
                "dataset_sha256": manifest[client]["dataset_sha256"], "base_state_sha256": base_sha, "source_window_count": counts.get("windows_emitted"), "quality_eligible_windows": counts.get("trainable"),
                "excluded_degraded": counts.get("DEGRADED"), "excluded_unusable": counts.get("UNUSABLE"), "excluded_valid_but_incomplete": counts.get("excluded_valid_but_incomplete"),
                "positive_labels": counts.get("synthetic_positive"), "negative_labels": counts.get("synthetic_negative"), "class_prevalence": counts["synthetic_positive"] / counts["trainable"],
                "examples_processed": int(accepted[client]["examples_seen"]), "unique_local_examples": counts.get("trainable"), "local_epochs": 1, "batch_count": raw.get("batch_count"),
                "mean_training_loss": losses[client], "final_batch_loss": blosses[-1] if blosses else None, "batch_loss_min": min(blosses) if blosses else None, "batch_loss_max": max(blosses) if blosses else None,
                "learning_rate": LEARNING_RATE, "optimizer_steps": len(cap) if cap else None, "gradient_norm_mean": float(np.mean(grads)) if grads else None, "gradient_norm_max": max(grads) if grads else None,
                "local_update_norm": float(norm) if norm is not None else None, "update_payload_bytes": int(bytes_) if bytes_ is not None else None, "update_sha256": accepted[client]["update_sha256"],
                "submission_status": "SUBMITTED", "acceptance_status": "ACCEPTED", "rejection_reason": None, "aggregation_weight": weights[client], "client_duration_seconds": info.get("duration"),
                "shuffle_seed": str(raw.get("shuffle_seed")) if raw.get("shuffle_seed") is not None else None})
            report["updates"].append({"run_id": ctx.run_id, "round": round_id, "client_id": client, "update_id": None, "update_sha256": accepted[client]["update_sha256"],
                                      "examples_seen": int(accepted[client]["examples_seen"]), "decision": "ACCEPTED"})
            for b in cap:
                report["batches"].append({"run_id": ctx.run_id, "round": round_id, "client_id": client, "epoch": 1, **b})
        weighted = [weights[c] * losses[c] for c in order if losses[c] is not None]
        parity = None
        if ctx.algorithm is Algorithm.FEDAVG and ctx.secagg_mode in (AggregationMode.PLAIN, AggregationMode.SECAGG_SHADOW) and str(round_id) in self._frozen:
            parity = {"frozen_reference_sha256": self._frozen[str(round_id)], "equals_frozen_reference": new_sha == self._frozen[str(round_id)]}
        final = round_id == ctx.planned_rounds
        info = state_info(new)
        report["rounds"].append({
            "run_id": ctx.run_id, "round": round_id, "expected_clients": 8, "received_updates": len(order), "valid_updates_received": len(order), "accepted_updates": len(order), "rejected_updates": 0, "rejections": [],
            "total_accepted_example_weight": total, "weights": weights, "weighted_mean_training_loss": sum(weighted) if len(weighted) == len(order) else None, "aggregation_state": "COMPLETE",
            "global_state_sha256": new_sha, "base_state_sha256": base_sha, "aggregated_update_norm": aggregate_update_norm(old, new), "update_payload_bytes_total": round_bytes,
            "payload_accounting": "serialized logical update payload bytes measured on the single-machine transport; not network traffic", "round_duration_seconds": duration,
            "cumulative_accepted_updates": cumulative_updates, "cumulative_example_exposures": cumulative_exposures, "cumulative_payload_bytes": sum(r["update_payload_bytes_total"] for r in report["rounds"]) + round_bytes,
            "missing_client_probe": None, "second_commit": None, "server_boundary_forbidden_hits": None, "parity": parity, "state_info": info,
            "candidate_status": "FINAL_CANDIDATE" if final else "INTERMEDIATE_STATE", "state_artifact": f"product federation checkpoint round_{round_id}" if not final else "engineering candidate artifact (final round)"})
        report["state_progression"][str(round_id)] = {**info, "committed_at": _now()}
        self._persist(ctx, report)
        self.observer.submit(run_id=ctx.run_id, run_length=ctx.planned_rounds, round_id=round_id, state=new, expected_digest=new_sha, candidate_id=ctx.candidate_id if final else None)

    def _persist(self, ctx: RunContext, report: dict[str, Any]) -> None:
        directory = self.run_dir(ctx.run_id)
        atomic_write(directory / "run_report.partial.json", (json.dumps({**report, "rounds_committed": len(report["rounds"])}, indent=1, sort_keys=True, default=str) + "\n").encode())

    def _finish(self, ctx: RunContext) -> None:
        report = self._report(ctx)
        final = ctx.committed.get(ctx.planned_rounds)
        report.update(status="COMPLETED", rounds_committed=len(report["rounds"]), finished_at=_now(), accepted_updates_total=len(report["updates"]),
                      example_exposures_total=sum(r["examples_processed"] for r in report["client_rounds"]), unique_training_windows=sum(c["counts"]["trainable"] for c in report["training_cohort"]),
                      candidate={"candidate_id": ctx.candidate_id, "state_sha256": final, "rounds": ctx.planned_rounds, "round": ctx.planned_rounds, "released_model_changed": False, "promoted": False, "deployed": False,
                                 "registered_in_product_registry": True, "label": "ENGINEERING CANDIDATE - SANDBOX ONLY - NOT DEPLOYED - NOT CLINICAL"},
                      prefix_equals_frozen_reference={str(r["round"]): r["parity"]["equals_frozen_reference"] for r in report["rounds"] if r.get("parity")})
        directory = self.run_dir(ctx.run_id)
        atomic_write(directory / "run_report.json", (json.dumps(report, indent=1, sort_keys=True, default=str) + "\n").encode())
        (directory / "run_report.partial.json").unlink(missing_ok=True)
        if report["rounds"]:
            write_tables(directory, report)

    def _fail(self, ctx: RunContext, error: Exception) -> None:
        report = self._report(ctx)
        report.update(status="INCOMPLETE_NOT_A_CANDIDATE", failure={"type": type(error).__name__, "message": str(error)[:300]}, rounds_committed=len(report["rounds"]), finished_at=_now())
        atomic_write(self.run_dir(ctx.run_id) / "run_report.json", (json.dumps(report, indent=1, sort_keys=True, default=str) + "\n").encode())
