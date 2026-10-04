"""WEARABLE_SIM_FL_SYSTEM_V1 ENGINEERING runner: cohort -> client-local datasets -> three FedAvg
rounds through the envelope/router/coordinator -> restart/resume -> one-round SecAgg shadow ->
finite-logit smoke. ENGINEERING ONLY: no efficacy metric is computed anywhere in this module, no
checkpoint is written, the final state is disposable."""

from __future__ import annotations

import json
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import torch

from federated.model_adapter import deserialize_state, restore_state, serialize_state
from federated.model_v2_fl import (
    fresh_initial_state_v2,
    fresh_model_v2,
    state_sha,
    train_local_epoch_v2,
)
from federated.virtual_client_source_v1 import LocalDataset, build_local_dataset
from federated.wearable_fl_system_v1 import (
    EXPERIMENT_ID,
    PROTOCOL_ID,
    REPLAY_ID,
    ROUNDS,
    Coordinator,
    CoordinatorError,
    canonical_order,
    extract_meta,
    make_envelope,
    scan_forbidden,
    semantic_digest,
    state_spec_sha,
)
from federated.wearable_sim_local_labels import SyntheticEventLabelProvider, SyntheticObservedSource
from nhm.hashing import hash_bytes
from simulation.fl_cohort_v1 import COHORT_ID, SOURCE_RATE_HZ, cohort_profiles, provenance

BASE_SEED = 20260927
LEARNING_RATE, WEIGHT_DECAY, BATCH_SIZE = 0.001, 0.0001, 64
# reused code-path fixture from FL_IID_MODEL_V2_V1; NOT a synthetic-prevalence weight
POS_WEIGHT = 1.7157717177396683
REVERSE_ROUND = 2
PERMUTATION = (3, 0, 6, 1, 7, 4, 2, 5)
FORBIDDEN_LOADER_MODULES = ("training.train_central", "preprocessing.mitdb_windows",
                            "datasets.mitdb", "datasets.incart")


class _CountingSource(SyntheticObservedSource):
    count = 0

    def records(self):
        for record in super().records():
            self.count += 1
            yield record


def build_cohort() -> tuple[list[Any], list[LocalDataset], dict[str, dict[str, str]]]:
    profiles = list(cohort_profiles())
    datasets: list[LocalDataset] = []
    for profile in profiles:
        source = _CountingSource(profile)
        dataset = build_local_dataset(source, SyntheticEventLabelProvider(profile))
        dataset.counts["source_records"] = source.count
        datasets.append(dataset)
    manifest = {d.client_id: {"participant_id": d.participant_id, "session_id": d.session_id,
                              "dataset_sha": d.dataset_sha256} for d in datasets}
    return profiles, datasets, manifest


def structural_coverage(datasets: list[LocalDataset]) -> list[str]:
    bad = []
    for d in datasets:
        c = d.counts
        if c["trainable"] < 32 or c["synthetic_positive"] < 8 or c["synthetic_negative"] < 8:
            bad.append(d.client_id)
    return bad


def cohort_manifest(profiles: list[Any], datasets: list[LocalDataset]) -> dict[str, Any]:
    clients = []
    for p, d in zip(profiles, datasets, strict=True):
        clients.append({
            "client_id": p.client_id, "participant_id": p.participant_id,
            "session_id": p.session_id, "seed": p.seed, "duration_s": 480,
            "source_rate_hz": SOURCE_RATE_HZ, "base_hr_bpm": p.base_hr_bpm,
            "coverage": list(p.coverage),
            "events": [{"time_s": e.time_s, "kind": e.kind + " SYNTHETIC / ENGINEERING EVENT"}
                       for e in p.events],
            "faults": [[f.kind, f.start_s, f.end_s] for f in p.faults],
            "context": [[c.mode, c.start_s, c.end_s] for c in p.context],
            "provenance": provenance(p), "counts": d.counts, "dataset_sha256": d.dataset_sha256})
    return {"cohort_id": COHORT_ID, "base_seed": BASE_SEED, "label_contract":
            "WEARABLE_SIM_EVENT_WINDOW_V1", "clients": clients}


def _floating_keys(state: dict[str, np.ndarray]) -> list[str]:
    return [k for k, v in state.items() if np.issubdtype(np.asarray(v).dtype, np.floating)]


def state_info(state: dict[str, np.ndarray]) -> dict[str, Any]:
    keys = _floating_keys(state)
    return {"sha256": state_sha(state), "floating_tensors": len(keys),
            "integer_buffers": len(state) - len(keys),
            "finite": all(bool(np.isfinite(state[k]).all()) for k in keys)}


def _event(log: list[dict[str, Any]], kind: str, **fields: Any) -> None:
    log.append({"seq": len(log), "type": kind, **fields})


def arrival_order(round_id: int, clients: list[str]) -> list[str]:
    ordered = canonical_order(clients)
    if round_id == 1:
        return ordered
    if round_id == REVERSE_ROUND:
        return list(reversed(ordered))
    return ordered


def execute_round(round_id: int, global_state: dict[str, np.ndarray], coord: Coordinator,
                  datasets: list[LocalDataset], log: list[dict[str, Any]], report: dict[str, Any],
                  collect: dict[str, Any] | None = None) -> dict[str, np.ndarray]:
    by_client = {d.client_id: d for d in datasets}
    base_sha = state_sha(global_state)
    spec_sha = coord.spec_sha
    _event(log, "ROUND_OPENED", round_id=round_id, base_global_state_sha256=base_sha)
    coord.open(round_id, base_sha)
    _event(log, "GLOBAL_STATE_BROADCAST", round_id=round_id, global_state_sha256=base_sha)
    results, envelopes = {}, {}
    for client in canonical_order(list(by_client)):
        d = by_client[client]
        result = train_local_epoch_v2(
            global_state=global_state, inputs=d.inputs, labels=d.labels, site_id=client,
            round_number=round_id, experiment_id=EXPERIMENT_ID, base_seed=BASE_SEED,
            batch_size=BATCH_SIZE, learning_rate=LEARNING_RATE, weight_decay=WEIGHT_DECAY,
            pos_weight=POS_WEIGHT)
        results[client] = result
        envelopes[client] = make_envelope(
            round_id=round_id, client_id=client, participant_id=d.participant_id,
            session_id=d.session_id, base_sha=base_sha, dataset_sha=d.dataset_sha256,
            spec_sha=spec_sha, examples=result.examples_seen, delta=dict(result.update.delta))
    round_report = report.setdefault("rounds", {})[str(round_id)] = {
        "base_global_state_sha256": base_sha,
        "local_training_calls": len(results),
        "shuffle_seeds": {c: str(r.shuffle_seed) for c, r in results.items()},
        "update_sha256": {c: e["update_sha256"] for c, e in envelopes.items()},
        "examples_seen": {c: r.examples_seen for c, r in results.items()},
        "diagnostics_not_in_digest": {c: {"mean_loss": r.mean_loss, "update_norm": r.update_norm,
                                          "payload_bytes": r.update_bytes}
                                      for c, r in results.items()},
        "rejections": []}
    if collect is not None and round_id == 1:
        keys = _floating_keys(global_state)
        collect["global_floating"] = [np.array(global_state[k], copy=True) for k in keys]
        collect["client_floating"] = {c: [np.asarray(global_state[k] + results[c].update.delta[k],
                                                     dtype=global_state[k].dtype) for k in keys]
                                      for c in results}
        collect["examples"] = {c: results[c].examples_seen for c in results}
    submissions: list[tuple[str, dict[str, Any]]] = [
        ("valid", envelopes[c]) for c in arrival_order(round_id, list(envelopes))]
    if round_id == 3:
        ordered = canonical_order(list(envelopes))
        prev = report["rounds"]["2"]["base_global_state_sha256"]
        stale = dict(envelopes[ordered[3]], round_id=2, base_global_state_sha256=prev)
        wrong_base = dict(envelopes[ordered[5]], base_global_state_sha256=report["rounds"]["1"][
            "base_global_state_sha256"])
        unknown = dict(envelopes[ordered[1]], client_id="SIM_FL_SITE_99")
        first = envelopes[ordered[0]]
        rest = [("valid", envelopes[c]) for c in ordered[1:]]
        submissions = [("INJECT_STALE", stale), ("valid", first), ("INJECT_DUPLICATE", first),
                       ("INJECT_WRONG_BASE", wrong_base), ("INJECT_UNKNOWN_CLIENT", unknown),
                       *rest]
    locality_hits: list[str] = []
    for kind, envelope in submissions:
        locality_hits.extend(scan_forbidden(envelope))
        meta = extract_meta(envelope, global_state)
        decision = coord.submit_meta(meta)
        if decision["decision"] == "ACCEPTED":
            coord.deltas[meta["client_id"]] = envelope["payload"]["delta"]
        _event(log, "CLIENT_UPDATE_ACCEPTED" if decision["decision"] == "ACCEPTED"
               else "CLIENT_UPDATE_REJECTED", round_id=round_id, update_id=decision["update_id"],
               client_id=decision["client_id"], decision=decision["decision"],
               code=decision["code"], meta=meta, injected=kind != "valid")
        if decision["decision"] == "REJECTED":
            round_report["rejections"].append({
                "injection": kind, "client_id": decision["client_id"], "code": decision["code"]})
    round_report["accepted"] = len(coord.accepted)
    round_report["server_boundary_forbidden_hits"] = locality_hits
    new_state = coord.aggregate(global_state)
    # arrival-order invariance: every arrival sequence maps to the canonical sorted order
    clients = canonical_order(list(coord.accepted))
    shas = {}
    for name, order in (("canonical", clients), ("reverse", list(reversed(clients))),
                        ("permutation", [clients[i] for i in PERMUTATION])):
        shadow = Coordinator(coord.manifest, coord.spec_sha)
        shadow.accepted = {c: coord.accepted[c] for c in order}
        shadow.deltas = {c: coord.deltas[c] for c in order}
        shadow.open_round = round_id
        shas[name] = state_sha(shadow.aggregate(global_state))
    round_report["order_invariance"] = {"aggregate_sha256": shas, "all_equal": len(
        set(shas.values())) == 1, "equals_committed": set(shas.values()) == {state_sha(new_state)}}
    new_sha = state_sha(new_state)
    _event(log, "ROUND_AGGREGATED", round_id=round_id, global_state_sha256=new_sha)
    coord.commit(round_id, new_sha)
    _event(log, "ROUND_COMMITTED", round_id=round_id, global_state_sha256=new_sha)
    try:
        coord.commit(round_id, new_sha)
        round_report["second_commit"] = "ACCEPTED_UNEXPECTEDLY"
    except CoordinatorError as exc:
        round_report["second_commit"] = exc.code
    round_report["global_state_sha256"] = new_sha
    return new_state


def new_session() -> tuple[OrderedDict[str, np.ndarray], str]:
    state = fresh_initial_state_v2(BASE_SEED)
    return state, state_spec_sha(state)


def smoke_inference(state: dict[str, np.ndarray], datasets: list[LocalDataset]) -> dict[str, Any]:
    model = fresh_model_v2()
    restore_state(model, state)
    model.eval()
    per_client, windows, finite = {}, 0, True
    with torch.no_grad():
        for d in datasets:
            logits = model(torch.from_numpy(d.inputs)).numpy()
            ok = bool(np.isfinite(logits).all()) and logits.shape == (d.inputs.shape[0], 1)
            finite &= ok
            windows += int(logits.shape[0])
            per_client[d.client_id] = {"windows": int(logits.shape[0]), "finite_and_shaped": ok}
    return {"windows_checked": windows, "all_logits_finite": finite, "per_client": per_client,
            "labels_read": False, "classification_metrics_computed": False}


def run_full(datasets: list[LocalDataset], manifest: dict[str, dict[str, str]], *,
             shadow: bool) -> dict[str, Any]:
    state, spec_sha = new_session()
    coord = Coordinator(manifest, spec_sha)
    log: list[dict[str, Any]] = []
    report: dict[str, Any] = {"state_progression": {"0": state_info(state)}}
    _event(log, "COHORT_READY", cohort_id=COHORT_ID,
           dataset_sha256={c: m["dataset_sha"] for c, m in manifest.items()})
    collect: dict[str, Any] = {}
    for round_id in range(1, ROUNDS + 1):
        state = execute_round(round_id, state, coord, datasets, log, report, collect)
        report["state_progression"][str(round_id)] = state_info(state)
    if shadow:
        from federated.wearable_fl_secagg_shadow_v1 import run_shadow
        report["secagg_shadow"] = run_shadow(
            collect["global_floating"], collect["client_floating"], collect["examples"])
        _event(log, "SECAGG_SHADOW_VERIFIED", status=report["secagg_shadow"]["status"],
               round_id=1)
    report["inference_smoke"] = smoke_inference(state, datasets)
    report["final_global_state_sha256"] = state_sha(state)
    report["coordinator_identity"] = coord.identity()
    _event(log, "RUN_COMPLETE", final_global_state_sha256=report["final_global_state_sha256"])
    return {"report": report, "events": log, "state": state}


def save_resume(directory: Path, state: dict[str, np.ndarray], coord: Coordinator,
                cohort_sha: str) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    blob = serialize_state(state)
    (directory / "state.bin").write_bytes(blob)
    record = {"protocol_id": PROTOCOL_ID, "experiment_id": EXPERIMENT_ID,
              "cohort_manifest_sha256": cohort_sha, "last_committed_round": len(coord.committed),
              "committed": list(coord.committed.items()), "global_state_sha256": state_sha(state),
              "state_file_sha256": hash_bytes(blob)}
    (directory / "coordinator.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    return {"coordinator_json_sha256": hash_bytes((directory / "coordinator.json").read_bytes()),
            "state_file_sha256": record["state_file_sha256"]}


def run_part1(datasets: list[LocalDataset], manifest: dict[str, dict[str, str]],
              directory: Path, cohort_sha: str) -> dict[str, Any]:
    state, spec_sha = new_session()
    coord = Coordinator(manifest, spec_sha)
    log: list[dict[str, Any]] = []
    report: dict[str, Any] = {"state_progression": {"0": state_info(state)}}
    for round_id in (1, 2):
        state = execute_round(round_id, state, coord, datasets, log, report)
    saved = save_resume(directory, state, coord, cohort_sha)
    return {"rounds_completed": 2, "global_state_sha256": state_sha(state), "resume": saved,
            "pid": os.getpid(), "round_reports": report["rounds"]}


def run_part2(datasets: list[LocalDataset], manifest: dict[str, dict[str, str]],
              directory: Path, cohort_sha: str) -> dict[str, Any]:
    record = json.loads((directory / "coordinator.json").read_text())
    blob = (directory / "state.bin").read_bytes()
    if (record["protocol_id"] != PROTOCOL_ID or record["experiment_id"] != EXPERIMENT_ID
            or record["cohort_manifest_sha256"] != cohort_sha
            or hash_bytes(blob) != record["state_file_sha256"]):
        raise RuntimeError("RESUME_IDENTITY_MISMATCH")
    state = deserialize_state(blob)
    if state_sha(state) != record["global_state_sha256"]:
        raise RuntimeError("RESUME_STATE_HASH_MISMATCH")
    spec_sha = state_spec_sha(state)
    coord = Coordinator(manifest, spec_sha)
    for round_id, sha in record["committed"]:
        coord.committed[int(round_id)] = sha
    log: list[dict[str, Any]] = []
    report: dict[str, Any] = {"rounds": {
        "1": {"base_global_state_sha256": new_session_hash()},
        "2": {"base_global_state_sha256": record["committed"][0][1]}}}
    state = execute_round(3, state, coord, datasets, log, report)
    return {"final_global_state_sha256": state_sha(state), "pid": os.getpid(),
            "resumed_from_round": record["last_committed_round"],
            "round_3_rejections": report["rounds"]["3"]["rejections"]}


def new_session_hash() -> str:
    return state_sha(fresh_initial_state_v2(BASE_SEED))


def firewall_audit() -> dict[str, Any]:
    present = [m for m in FORBIDDEN_LOADER_MODULES if m in sys.modules]
    return {"real_loader_modules_imported": present, "real_partitions_read": [],
            "waveform_source": "WEARABLE_SIM_V1 only"}


def run_digest(summary: dict[str, Any], events: list[dict[str, Any]],
               restart: dict[str, Any]) -> str:
    report = summary
    return semantic_digest({
        "replay_id": REPLAY_ID, "cohort_id": COHORT_ID,
        "events": events,
        "rounds": {r: {k: v for k, v in body.items() if k != "diagnostics_not_in_digest"}
                   for r, body in report["rounds"].items()},
        "state_progression": report["state_progression"],
        "secagg": {"status": report.get("secagg_shadow", {}).get("status"),
                   "plain_clear": report.get("secagg_shadow", {}).get("plain_clear_update_count"),
                   "protected_clear": report.get("secagg_shadow", {}).get(
                       "protected_clear_update_count")},
        "restart": restart, "final": report["final_global_state_sha256"]})
