# ruff: noqa: E501
"""The 10-round FedAvg runner (opt-in, synthetic engineering data only).

One round = the original protocol: open -> broadcast -> eight real local optimisations through the unchanged ``train_local_epoch_v2`` -> envelopes validated by the
unchanged ``Coordinator`` -> weighted FedAvg by ``Coordinator.aggregate`` (-> ``aggregate_weighted_deltas``) -> commit. Every committed state is persisted atomically.
The frozen 3-round product contract is not touched."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from federated.model_adapter import deserialize_state, serialize_state
from federated.model_v2_fl import state_sha, train_local_epoch_v2
from federated.virtual_client_source_v1 import LocalDataset
from federated.wearable_fl_runner_v1 import (
    BASE_SEED,
    BATCH_SIZE,
    LEARNING_RATE,
    POS_WEIGHT,
    WEIGHT_DECAY,
    new_session,
    state_info,
)
from federated.wearable_fl_system_v1 import EXPERIMENT_ID as FL_EXPERIMENT_ID
from federated.wearable_fl_system_v1 import (
    Coordinator,
    CoordinatorError,
    canonical_order,
    extract_meta,
    make_envelope,
    scan_forbidden,
)
from fl10 import ROUNDS

FROZEN_RUN = "reports/model_v2/v2_fl_005/federation_run.json"
ROOT = Path(__file__).resolve().parents[1]
MAX_PARITY_ROUNDS = 3


class Fl10Error(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}")
        self.code, self.detail = code, detail


def frozen_progression() -> dict[str, str]:
    prog = json.loads((ROOT / FROZEN_RUN).read_text())["state_progression"]
    return {k: v["sha256"] for k, v in prog.items()}


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _floating(state: dict[str, np.ndarray]) -> list[str]:
    return [k for k, v in state.items() if np.issubdtype(np.asarray(v).dtype, np.floating)]


def aggregate_update_norm(old: dict[str, np.ndarray], new: dict[str, np.ndarray]) -> float:
    return math.sqrt(sum(float(np.sum((np.asarray(new[k], dtype=np.float64) - np.asarray(old[k], dtype=np.float64)) ** 2)) for k in _floating(old)))


def _injections(round_id: int, envelopes: dict[str, dict[str, Any]], prev_base: str | None, state: dict[str, np.ndarray], spec_sha: str, datasets: dict[str, LocalDataset], base_sha: str) -> list[tuple[str, dict[str, Any]]]:
    """Adversarial submissions evaluated by the unchanged coordinator in EVERY round (expected rejection codes are asserted by the caller)."""
    order = canonical_order(list(envelopes))
    first, second = envelopes[order[0]], envelopes[order[1]]
    out: list[tuple[str, dict[str, Any]]] = [("INJECT_DUPLICATE", first),
                                             ("INJECT_WRONG_BASE", dict(second, base_global_state_sha256="0" * 64)),
                                             ("INJECT_UNKNOWN_CLIENT", dict(second, client_id="SIM_FL_SITE_99")),
                                             ("INJECT_INVALID_DIGEST", dict(second, update_sha256="f" * 64))]
    malformed = {k: v for k, v in second.items() if k != "state_spec_sha256"}
    out.append(("INJECT_MALFORMED", malformed))
    bad_delta = {k: np.array(v, copy=True) for k, v in second["payload"]["delta"].items()}
    key = next(k for k in bad_delta if np.issubdtype(bad_delta[k].dtype, np.floating))
    bad_delta[key].flat[0] = np.nan
    out.append(("INJECT_NONFINITE", make_envelope(round_id=round_id, client_id=order[2], participant_id=envelopes[order[2]]["participant_id"], session_id=envelopes[order[2]]["session_id"], base_sha=base_sha,
                                                  dataset_sha=envelopes[order[2]]["client_dataset_sha256"], spec_sha=spec_sha, examples=envelopes[order[2]]["examples_seen"], delta=bad_delta)))
    if prev_base is not None:
        out.insert(0, ("INJECT_STALE", dict(second, round_id=round_id - 1, base_global_state_sha256=prev_base)))
    return out


EXPECTED_CODE = {"INJECT_STALE": "STALE_ROUND", "INJECT_DUPLICATE": "DUPLICATE_UPDATE", "INJECT_WRONG_BASE": "BASE_STATE_MISMATCH", "INJECT_UNKNOWN_CLIENT": "UNKNOWN_CLIENT",
                 "INJECT_INVALID_DIGEST": "UPDATE_SHA_MISMATCH", "INJECT_MALFORMED": "SCHEMA_MISMATCH", "INJECT_NONFINITE": "NONFINITE_UPDATE"}


def run_training(*, mode: str, run_id: str, out_dir: Path, datasets: list[LocalDataset], manifest: dict[str, dict[str, str]], rounds: int = ROUNDS, require_prefix_parity: bool = True,
                 capture_batches: bool = True, progress: Callable[[dict[str, Any]], None] | None = None, git_commit: str = "UNKNOWN", protocol_sha256: str = "UNKNOWN",
                 tamper_before_round: Callable[[int, dict[str, np.ndarray]], dict[str, np.ndarray]] | None = None,
                 initial_state: dict[str, np.ndarray] | None = None, initialisation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute ``rounds`` genuine FedAvg rounds. Fails closed (raises, run marked incomplete) on any parity, digest, acceptance or finiteness violation.

    ``initial_state`` (additive, default None) starts the rounds from a verified pretrained state instead of ``FL_INIT_V2``. That is a separately identified mode: the frozen
    FL_INIT_V2 reference (initial digest and prefix parity) does not apply to it, so those checks are skipped and the report carries ``initialisation`` instead."""
    if capture_batches:
        from api.observatory_batch_capture import BatchCapture
    emit = progress or (lambda event: None)
    by_client = {d.client_id: d for d in datasets}
    if sorted(by_client) != sorted(manifest) or len(by_client) != 8:
        raise Fl10Error("COHORT_MANIFEST_MISMATCH")
    for client, dataset in by_client.items():
        if manifest[client]["dataset_sha"] != dataset.dataset_sha256:
            raise Fl10Error("DATASET_DIGEST_MISMATCH", client)
    frozen = frozen_progression()
    state, spec_sha = new_session()
    if initial_state is None:
        if state_sha(state) != frozen["0"]:
            raise Fl10Error("WRONG_INITIAL_STATE", state_sha(state))
    else:
        if require_prefix_parity:
            raise Fl10Error("PREFIX_PARITY_NOT_DEFINED_FOR_PRETRAINED_START")
        if list(initial_state) != list(state) or any(initial_state[k].shape != state[k].shape or initial_state[k].dtype != state[k].dtype for k in state):
            raise Fl10Error("INITIAL_STATE_LAYOUT_MISMATCH")
        state = OrderedDict(initial_state)       # same layout and spec digest as FL_INIT_V2 (checked above); only the weights differ
    coord = Coordinator(manifest, spec_sha)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise Fl10Error("RUN_ARTIFACT_DIRECTORY_NOT_EMPTY", str(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(out_dir / "states/R00.bin", serialize_state(state))
    started = datetime.now(UTC).isoformat()
    t_run = time.perf_counter()
    report: dict[str, Any] = {"run_id": run_id, "mode": mode, "status": "RUNNING", "git_commit": git_commit, "protocol_sha256": protocol_sha256, "experiment_id": "NHM_FL10_SYNTHETIC_ENGINEERING_V1",
                              "federation_engine": "federated.wearable_fl_system_v1.Coordinator + federated.model_v2_fl.train_local_epoch_v2 (unchanged)", "planned_rounds": rounds, "started_at": started,
                              "settings": {"base_seed": BASE_SEED, "experiment_id_for_seeds": FL_EXPERIMENT_ID, "batch_size": BATCH_SIZE, "learning_rate": LEARNING_RATE, "weight_decay": WEIGHT_DECAY,
                                           "pos_weight": POS_WEIGHT, "optimizer": "AdamW (reset every local epoch)", "local_epochs": 1, "aggregation": "weighted FedAvg by accepted example count"},
                              "environment": {"python": platform.python_version(), "platform": platform.platform(), "numpy": np.__version__}, "frozen_reference": FROZEN_RUN if initial_state is None else None, "initialisation": initialisation or {"model_id": "FL_INIT_V2"},
                              "state_progression": {"0": {**state_info(state), "committed_at": started}}, "rounds": [], "client_rounds": [], "batches": [], "updates": []}
    try:
        import sklearn
        import torch

        report["environment"].update(torch=torch.__version__, sklearn=sklearn.__version__)
    except ImportError:  # pragma: no cover
        pass
    cumulative_exposures = cumulative_updates = cumulative_bytes = 0
    prev_base: str | None = None
    try:
        for round_id in range(1, rounds + 1):
            t_round = time.perf_counter()
            if tamper_before_round is not None:
                state = tamper_before_round(round_id, state)                      # test hook (negative controls only)
            base_sha = state_sha(state)
            expected_base = state_sha(deserialize_state((out_dir / f"states/R{round_id - 1:02d}.bin").read_bytes()))
            if base_sha != expected_base or (round_id > 1 and base_sha != coord.committed[round_id - 1]):
                raise Fl10Error("INCORRECT_PREVIOUS_ROUND_BASE", f"round {round_id}")
            coord.open(round_id, base_sha)
            emit({"event": "ROUND_OPENED", "round": round_id, "base_state_sha256": base_sha})
            envelopes: dict[str, dict[str, Any]] = {}
            results: dict[str, Any] = {}
            captures: dict[str, Any] = {}
            durations: dict[str, float] = {}
            for client in canonical_order(list(by_client)):
                d = by_client[client]
                emit({"event": "CLIENT_TRAINING_STARTED", "round": round_id, "client_id": client})
                t0 = time.perf_counter()
                kwargs = dict(global_state=state, inputs=d.inputs, labels=d.labels, site_id=client, round_number=round_id, experiment_id=FL_EXPERIMENT_ID, base_seed=BASE_SEED,
                              batch_size=BATCH_SIZE, learning_rate=LEARNING_RATE, weight_decay=WEIGHT_DECAY, pos_weight=POS_WEIGHT)
                if capture_batches:
                    with BatchCapture() as cap:
                        result = train_local_epoch_v2(**kwargs)
                    captures[client] = cap
                else:
                    result = train_local_epoch_v2(**kwargs)
                durations[client] = time.perf_counter() - t0
                results[client] = result
                envelopes[client] = make_envelope(round_id=round_id, client_id=client, participant_id=d.participant_id, session_id=d.session_id, base_sha=base_sha, dataset_sha=d.dataset_sha256,
                                                  spec_sha=spec_sha, examples=result.examples_seen, delta=dict(result.update.delta))
                emit({"event": "CLIENT_TRAINING_FINISHED", "round": round_id, "client_id": client, "mean_loss": result.mean_loss, "examples": result.examples_seen, "update_sha256": envelopes[client]["update_sha256"]})
            decisions: dict[str, dict[str, Any]] = {}
            injected: list[dict[str, Any]] = []
            order = canonical_order(list(envelopes))
            injections = _injections(round_id, envelopes, prev_base, state, spec_sha, by_client, base_sha)
            submissions = [("valid", envelopes[order[0]])] + injections + [("valid", envelopes[c]) for c in order[1:]]
            locality_hits: list[str] = []
            for kind, envelope in submissions:
                locality_hits.extend(scan_forbidden(envelope))
                meta = extract_meta(envelope, state)
                decision = coord.submit_meta(meta)
                if decision["decision"] == "ACCEPTED":
                    coord.deltas[meta["client_id"]] = envelope["payload"]["delta"]
                    decisions[meta["client_id"]] = decision
                elif kind == "valid":
                    raise Fl10Error("VALID_UPDATE_REJECTED", f"{meta['client_id']}:{decision['code']}")
                if kind != "valid":
                    injected.append({"injection": kind, "client_id": decision["client_id"], "decision": decision["decision"], "code": decision["code"], "expected_code": EXPECTED_CODE[kind]})
                    if decision["decision"] != "REJECTED" or decision["code"] != EXPECTED_CODE[kind]:
                        raise Fl10Error("INJECTED_UPDATE_NOT_REJECTED_AS_EXPECTED", f"{kind}:{decision['code']}")
            if len(coord.accepted) != 8 or sorted(coord.accepted) != order:
                raise Fl10Error("INCOMPLETE_OR_UNEXPECTED_ACCEPTANCE", str(sorted(coord.accepted)))
            emit({"event": "UPDATES_ACCEPTED", "round": round_id, "accepted_clients": order, "accepted_updates": len(coord.accepted)})
            probe = Coordinator(coord.manifest, coord.spec_sha)           # missing-client probe: the unchanged coordinator refuses to aggregate seven updates
            probe.open_round, probe.base_sha = round_id, base_sha
            probe.accepted = {c: coord.accepted[c] for c in order[:-1]}
            probe.deltas = {c: coord.deltas[c] for c in order[:-1]}
            try:
                probe.aggregate(state)
                raise Fl10Error("MISSING_CLIENT_NOT_REFUSED")
            except CoordinatorError as error:
                missing_probe = error.code
            emit({"event": "AGGREGATION_STARTED", "round": round_id, "accepted_updates": len(coord.accepted)})
            new_state = coord.aggregate(state)
            info = state_info(new_state)
            if not info["finite"]:
                raise Fl10Error("NONFINITE_GLOBAL_STATE", f"round {round_id}")
            new_sha = state_sha(new_state)
            coord.commit(round_id, new_sha)
            try:
                coord.commit(round_id, new_sha)
                second_commit = "ACCEPTED_UNEXPECTEDLY"
            except CoordinatorError as error:
                second_commit = error.code
            atomic_write(out_dir / f"states/R{round_id:02d}.bin", serialize_state(new_state))
            total_examples = sum(int(coord.accepted[c]["examples_seen"]) for c in order)
            weights = {c: int(coord.accepted[c]["examples_seen"]) / total_examples for c in order}
            weighted_loss = sum(weights[c] * results[c].mean_loss for c in order)
            round_bytes = sum(results[c].update_bytes for c in order)
            cumulative_exposures += total_examples
            cumulative_updates += len(order)
            cumulative_bytes += round_bytes
            parity = None
            if round_id <= MAX_PARITY_ROUNDS and initial_state is None:
                parity = {"frozen_reference_sha256": frozen[str(round_id)], "equals_frozen_reference": new_sha == frozen[str(round_id)]}
                if require_prefix_parity and not parity["equals_frozen_reference"]:
                    raise Fl10Error("PREFIX_PARITY_MISMATCH", f"round {round_id}: {new_sha} != {frozen[str(round_id)]}")
            for client in order:
                d, r = by_client[client], results[client]
                cap = captures[client].batches if capture_batches else []
                for b in cap:
                    report["batches"].append({"run_id": run_id, "round": round_id, "client_id": client, "epoch": 1, **b})
                losses = [b["loss"] for b in cap]
                grads = [b["gradient_l2_norm"] for b in cap]
                counts = d.counts
                report["client_rounds"].append({
                    "run_id": run_id, "round": round_id, "client_id": client, "participant_id": d.participant_id, "dataset_id": d.session_id, "dataset_sha256": d.dataset_sha256, "base_state_sha256": base_sha,
                    "source_window_count": counts.get("windows_emitted"), "quality_eligible_windows": counts.get("trainable"), "excluded_degraded": counts.get("DEGRADED"), "excluded_unusable": counts.get("UNUSABLE"),
                    "excluded_valid_but_incomplete": counts.get("excluded_valid_but_incomplete"), "positive_labels": counts.get("synthetic_positive"), "negative_labels": counts.get("synthetic_negative"),
                    "class_prevalence": counts["synthetic_positive"] / counts["trainable"], "examples_processed": r.examples_seen, "unique_local_examples": len(d.labels), "local_epochs": 1,
                    "batch_count": r.batch_count, "mean_training_loss": r.mean_loss, "final_batch_loss": losses[-1] if losses else None, "batch_loss_min": min(losses) if losses else None,
                    "batch_loss_max": max(losses) if losses else None, "learning_rate": LEARNING_RATE, "optimizer_steps": len(cap) if capture_batches else None,
                    "gradient_norm_mean": float(np.mean(grads)) if grads else None, "gradient_norm_max": max(grads) if grads else None, "local_update_norm": r.update_norm,
                    "update_payload_bytes": r.update_bytes, "update_sha256": envelopes[client]["update_sha256"], "submission_status": "SUBMITTED", "acceptance_status": decisions[client]["decision"],
                    "rejection_reason": None, "aggregation_weight": weights[client], "client_duration_seconds": durations[client], "shuffle_seed": str(r.shuffle_seed)})
                report["updates"].append({"run_id": run_id, "round": round_id, "client_id": client, "update_id": decisions[client]["update_id"], "update_sha256": envelopes[client]["update_sha256"],
                                          "examples_seen": r.examples_seen, "decision": decisions[client]["decision"]})
            round_row = {"run_id": run_id, "round": round_id, "expected_clients": 8, "received_updates": 8 + len(injected), "valid_updates_received": 8, "accepted_updates": 8,
                         "rejected_updates": len(injected), "rejections": injected, "total_accepted_example_weight": total_examples, "weights": weights, "weighted_mean_training_loss": weighted_loss,
                         "aggregation_state": "COMPLETE", "global_state_sha256": new_sha, "base_state_sha256": base_sha, "aggregated_update_norm": aggregate_update_norm(state, new_state),
                         "update_payload_bytes_total": round_bytes, "payload_accounting": "serialized logical update payload bytes measured on the single-machine transport; not network traffic",
                         "round_duration_seconds": time.perf_counter() - t_round, "cumulative_accepted_updates": cumulative_updates, "cumulative_example_exposures": cumulative_exposures,
                         "cumulative_payload_bytes": cumulative_bytes, "missing_client_probe": missing_probe, "second_commit": second_commit, "server_boundary_forbidden_hits": locality_hits,
                         "parity": parity, "state_info": info, "candidate_status": "INTERMEDIATE_STATE" if round_id < rounds else "FINAL_CANDIDATE"}
            report["rounds"].append(round_row)
            report["state_progression"][str(round_id)] = {**info, "committed_at": datetime.now(UTC).isoformat()}
            emit({"event": "ROUND_COMMITTED", "round": round_id, "global_state_sha256": new_sha, "weighted_mean_training_loss": weighted_loss})
            prev_base, state = base_sha, new_state
            atomic_write(out_dir / "run_report.partial.json", (json.dumps({**report, "status": "RUNNING", "rounds_committed": round_id}, indent=1, sort_keys=True, default=str) + "\n").encode())
    except Exception as error:
        report.update(status="INCOMPLETE_NOT_A_CANDIDATE", failure={"type": type(error).__name__, "message": str(error)[:500]}, rounds_committed=len(report["rounds"]), finished_at=datetime.now(UTC).isoformat())
        atomic_write(out_dir / "run_report.json", (json.dumps(report, indent=1, sort_keys=True, default=str) + "\n").encode())
        raise
    final_sha = state_sha(state)
    report.update(status="COMPLETED", rounds_committed=rounds, finished_at=datetime.now(UTC).isoformat(), total_seconds=time.perf_counter() - t_run, accepted_updates_total=cumulative_updates,
                  example_exposures_total=cumulative_exposures, unique_training_windows=sum(len(d.labels) for d in datasets),
                  candidate={"candidate_id": f"FL10_CANDIDATE_{run_id}", "state_sha256": final_sha, "rounds": rounds, "round": rounds, "released_model_changed": False, "promoted": False, "deployed": False,
                             "registered_in_product_registry": False, "label": "ENGINEERING CANDIDATE - NOT PROMOTED - NOT CLINICAL"},
                  coordinator_identity=coord.identity(), cohort_manifest_sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
                  prefix_equals_frozen_reference={str(r): report["rounds"][r - 1]["parity"]["equals_frozen_reference"] for r in range(1, min(rounds, MAX_PARITY_ROUNDS) + 1)} if initial_state is None else {})
    atomic_write(out_dir / "run_report.json", (json.dumps(report, indent=1, sort_keys=True, default=str) + "\n").encode())
    (out_dir / "run_report.partial.json").unlink(missing_ok=True)
    write_tables(out_dir, report)
    return report


def write_tables(out_dir: Path, report: dict[str, Any]) -> None:
    for name, key in (("client_rounds.csv", "client_rounds"), ("batches.csv", "batches"), ("updates.csv", "updates")):
        rows = report[key]
        if not rows:
            continue
        with (out_dir / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    flat = [{k: v for k, v in r.items() if k not in ("weights", "rejections", "state_info", "parity")} | {"rejected_codes": ";".join(x["code"] for x in r["rejections"]), "state_finite": r["state_info"]["finite"]} for r in report["rounds"]]
    with (out_dir / "rounds.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(flat[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(flat)


def load_state(run_dir: Path, round_id: int, expected_sha: str) -> dict[str, np.ndarray]:
    state = deserialize_state((run_dir / f"states/R{round_id:02d}.bin").read_bytes())
    if state_sha(OrderedDict(state)) != expected_sha:
        raise Fl10Error("STATE_ARTIFACT_DIGEST_MISMATCH", f"R{round_id}")
    return state
