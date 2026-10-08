"""Small post-run snapshot of the coordinator maps already held by CAP-007.

This is a separate Observatory sidecar. It does not enter the FL event journal, run
metadata, model state, candidate artifact, or governance inputs. A write failure cannot
change the outcome of a completed federation run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from contextlib import suppress
from pathlib import Path
from typing import Any

from product.federation.artifact_store import FederationArtifactStore, atomic_write
from product.federation.base import RunType
from product.federation.service import FederationService, RunContext

CAPTURE_ID = "NHM_OBSERVATORY_DIRECT_ACCEPTANCE_V1"
FILENAME = "observatory_acceptance_v1.json"


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def capture_file(artifacts: FederationArtifactStore, run_id: str) -> Path:
    return artifacts.run_dir(run_id) / FILENAME


def snapshot(ctx: RunContext, artifacts: FederationArtifactStore,
             diagnostics: dict[str, dict[str, dict[str, Any]]] | None = None) -> None:
    if ctx.run_type is not RunType.LIVE_RUN or ctx.candidate_id is None:
        return
    payload: dict[str, Any] = {
        "capture_id": CAPTURE_ID,
        "run_id": ctx.run_id,
        "candidate_id": ctx.candidate_id,
        "planned_rounds": ctx.planned_rounds,
        "rounds": {
            str(round_id): {
                "base_state_digest": ctx.round_bases[round_id],
                "committed_state_digest": ctx.committed[round_id],
                "accepted_updates": dict(sorted(ctx.coordinator_digests[round_id].items())),
                "training": {client_id: {
                    "examples_seen": int(ctx.training_record[round_id][client_id]["examples_seen"]),
                    "update_sha256": ctx.training_record[round_id][client_id]["update_sha256"],
                } for client_id in sorted(ctx.coordinator_digests[round_id])},
            } for round_id in range(1, ctx.planned_rounds + 1)
        },
    }
    if diagnostics:
        payload["local_training_diagnostics"] = diagnostics
    payload["content_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    atomic_write(capture_file(artifacts, ctx.run_id),
                 (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode())


def read_verified(artifacts: FederationArtifactStore, run_id: str) -> dict[str, Any] | None:
    path = capture_file(artifacts, run_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    expected = data.pop("content_sha256", None)
    if (data.get("capture_id") != CAPTURE_ID or data.get("run_id") != run_id
            or hashlib.sha256(_canonical(data)).hexdigest() != expected):
        raise ValueError("OBSERVATORY_ACCEPTANCE_CAPTURE_HASH_MISMATCH")
    return data

LOG = logging.getLogger("nhm.observatory.fl")


def consistent(batches: list[dict[str, Any]], record: dict[str, Any]) -> bool:
    """Per-batch rows are kept only if they reproduce the end-of-epoch summary."""
    total = sum(b["batch_size"] for b in batches)
    if len(batches) != record["batch_count"] or total != record["examples_seen"]:
        return False
    weighted = sum(b["loss"] * b["batch_size"] for b in batches) / record["examples_seen"]
    return abs(weighted - record["mean_loss_diagnostic_only"]) <= 1e-9


def install(service: FederationService, batch_capture: Any = None) -> None:
    """``batch_capture``: optional factory of a context manager exposing ``batches``."""
    original_finish = service._finish
    original_train = service._train_sync
    original_fail = service._fail
    diagnostics_by_run: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}

    def observing_train(adapter: Any, round_id: int, digest: str) -> None:
        capture = batch_capture() if batch_capture is not None else None
        client = getattr(getattr(adapter, "_buffer", None), "client_id", "?")
        LOG.info("FL round %s | %s | local training started", round_id, client)
        if capture is None:
            original_train(adapter, round_id, digest)
        else:
            with capture:
                original_train(adapter, round_id, digest)
        try:
            raw = adapter.diagnostics()
            mean_loss = float(raw["mean_loss_diagnostic_only"])
            update_norm = float(raw["update_norm_diagnostic_only"])
            if not math.isfinite(mean_loss) or not math.isfinite(update_norm):
                return
            run_id = service._active
            if run_id is not None:
                record = {
                    "examples_seen": int(raw["examples_seen"]),
                    "batch_count": int(raw["batch_count"]),
                    "shuffle_seed": str(raw["shuffle_seed"]),
                    "update_bytes": int(raw["update_bytes"]),
                    "mean_loss_diagnostic_only": mean_loss,
                    "update_norm_diagnostic_only": update_norm,
                }
                if capture is not None and capture.batches and consistent(capture.batches, record):
                    record["per_batch"] = {
                        "batches": capture.batches, "dropped_beyond_bound": capture.dropped,
                        "loss_term": "BCE_WITH_LOGITS_MEAN_OVER_BATCH"}
                LOG.info(
                    "FL round %s | %s | local training done: %d examples, %d batches, "
                    "mean loss %.4f, update norm %.4f", round_id, client,
                    record["examples_seen"], record["batch_count"], mean_loss, update_norm)
                for b in record.get("per_batch", {}).get("batches", []):
                    LOG.info("FL round %s | %s |   batch %d: size %d, loss %.4f, grad norm %.4f",
                             round_id, client, b["batch_index"] + 1, b["batch_size"],
                             b["loss"], b["gradient_l2_norm"])
                diagnostics_by_run.setdefault(run_id, {}).setdefault(str(round_id), {})[
                    adapter._buffer.client_id] = record
        except Exception:
            # An observer failure does not change a completed optimizer call.
            return

    def observing_finish(ctx: RunContext) -> None:
        original_finish(ctx)
        # Diagnostic sidecar failure must not change the already completed FL run.
        with suppress(Exception):
            snapshot(ctx, service.artifacts, diagnostics_by_run.get(ctx.run_id))
        diagnostics_by_run.pop(ctx.run_id, None)

    def observing_fail(ctx: RunContext, tracker: Any, error: Exception) -> None:
        try:
            original_fail(ctx, tracker, error)
        finally:
            diagnostics_by_run.pop(ctx.run_id, None)

    service._train_sync = observing_train  # type: ignore[method-assign]
    service._finish = observing_finish  # type: ignore[method-assign]
    service._fail = observing_fail  # type: ignore[method-assign]
