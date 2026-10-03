"""V2-FL-001: real deterministic 50-round whole-patient IID FedAvg for MODEL_V2_TCN_MEAN.

Mirrors federated.fedavg_runner (T025) step for step; the only scientific change is the model
family. Reads ONLY MIT-BIH TRAIN (client training) and VALIDATION (server development
evaluation), each gated by the MODEL_V2 partition firewall and logged to the access ledger.
Outputs live under reports/model_v2/v2_fl_001/ and checkpoints/model_v2/v2_fl_001/; no V1 FL
artifact is written."""

from __future__ import annotations

import copy
import json
import math
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from federated.aggregation import ClientUpdate, aggregate_weighted_deltas
from federated.client_manifest import SITE_IDS
from federated.evaluation import evaluate_model
from federated.fedavg_runner import (
    _write_csv,
    _write_json,
    choose_best_round,
    flower_reference_parity,
    load_manifest_sites,
    normalized_population,
    stable_convergence,
)
from federated.model_adapter import restore_state, serialize_state
from federated.model_v2_fl import (
    EXPERIMENT_ID,
    INITIALIZATION_ID,
    fresh_initial_state_v2,
    fresh_model_v2,
    set_determinism,
    state_sha,
    train_local_epoch_v2,
)
from nhm.hashing import hash_file
from nhm.model_v2_partition_guard import _append_ledger, check_partition_allowed
from training.train_central import WindowPopulation, load_population

STAGE_ID = "V2-FL-001"
ALLOWED_PARTITIONS = ("TRAIN", "VALIDATION")
CONFIG_RELATIVE = "configs/model_v2/fl_iid_model_v2_v1.yaml"
OUT_RELATIVE = "reports/model_v2/v2_fl_001"
CKPT_RELATIVE = "checkpoints/model_v2/v2_fl_001"


def guarded_population(root: Path, partition: str) -> WindowPopulation:
    check_partition_allowed(partition, STAGE_ID, ALLOWED_PARTITIONS)
    population = load_population(partition)
    _append_ledger(root, {"timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                          "stage_id": STAGE_ID, "experiment_id": EXPERIMENT_ID,
                          "partition": partition, "access_type": "waveform_read",
                          "rows": int(population.labels.size),
                          "source_path": "frozen MITDB_WINDOWS_V1 caches (load_population)"})
    return population


def save_checkpoint(path: Path, *, state: dict[str, np.ndarray], round_number: int,
                    validation_auprc: float, config_sha: str, manifest_sha: str) -> None:
    model = fresh_model_v2()
    restore_state(model, state)
    payload = {
        "checkpoint_id": EXPERIMENT_ID, "model_architecture_id": "MODEL_V2_TCN_MEAN",
        "initialization_id": INITIALIZATION_ID, "round": round_number,
        "validation_AUPRC": validation_auprc, "config_sha256": config_sha,
        "client_manifest_sha256": manifest_sha, "preproc_id": "PREPROC_V1",
        "transport_id": "FL_STATE_TRANSPORT_V1",
        "aggregation_id": "SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1",
        "calibration": "NONE", "supersedes_model_v2_final": False,
        "state_dict": copy.deepcopy(model.state_dict()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)


def _round_row(round_number: int, metrics: dict[str, Any], sha: str, n_val: int,
               **extra: Any) -> dict[str, Any]:
    base = {
        "round": round_number, "client_count": 0, "total_examples": 0,
        "training_weighted_mean_loss": "", "validation_windows": n_val,
        "validation_AUPRC": metrics["AUPRC"], "validation_AUROC": metrics["AUROC"],
        "validation_raw_F1_at_0_5": metrics["pooled_F1"],
        "validation_precision_at_0_5": metrics["precision"],
        "validation_sensitivity_at_0_5": metrics["sensitivity"],
        "validation_specificity_at_0_5": metrics["specificity"],
        "validation_patient_macro_F1_at_0_5": metrics["patient_macro_F1"],
        "validation_BCE": metrics["BCE"], "global_state_sha256": sha,
        "bytes_received": 0, "bytes_sent": 0, "finite_state": True,
        "selected_best_so_far": False, "round_wall_seconds": ""}
    base.update(extra)
    return base


def run(root: Path) -> dict[str, Any]:
    out = root / OUT_RELATIVE
    config_path = root / CONFIG_RELATIVE
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    manifest_path = root / config["client_manifest"]["path"]
    manifest_sha = hash_file(manifest_path)
    if manifest_sha != config["client_manifest"]["sha256"]:
        raise RuntimeError("CLIENTS_IID_V1_MANIFEST_SHA_MISMATCH")
    sites = load_manifest_sites(manifest_path)
    seed = int(config["initialization"]["seed"])
    set_determinism(seed)
    train = guarded_population(root, "TRAIN")
    validation = guarded_population(root, "VALIDATION")
    train_inputs = normalized_population(train)
    validation_inputs = normalized_population(validation)
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    if not math.isclose(pos_weight, float(config["loss"]["pos_weight"]), rel_tol=0,
                        abs_tol=1e-15):
        raise RuntimeError("global TRAIN pos_weight mismatch")
    site_indices = {site: np.flatnonzero(np.isin(train.participant_group_ids, groups))
                    for site, groups in sites.items()}
    global_state = fresh_initial_state_v2(seed)
    initial_sha = state_sha(global_state)
    final_ckpt = torch.load(root / "checkpoints/MODEL_V2_FINAL.pt", map_location="cpu",
                            weights_only=False)["state_dict"]
    trained_sha = state_sha(OrderedDict((k, v.numpy().copy()) for k, v in final_ckpt.items()))
    if initial_sha == trained_sha:
        raise RuntimeError("central MODEL_V2_FINAL checkpoint warm start detected")
    model = fresh_model_v2()
    restore_state(model, global_state)
    metrics0, _, _ = evaluate_model(model, validation_inputs, validation.labels,
                                    validation.participant_group_ids, pos_weight=pos_weight,
                                    partition="VALIDATION")
    round_rows = [_round_row(0, metrics0, initial_sha, int(validation.labels.size))]
    client_rows: list[dict[str, Any]] = []
    states: dict[int, dict[str, np.ndarray]] = {0: copy.deepcopy(global_state)}
    server_payload = len(serialize_state(global_state))
    parity: dict[str, Any] | None = None
    for round_number in range(1, int(config["training"]["rounds"]) + 1):
        started = time.monotonic()
        updates: list[ClientUpdate] = []
        losses: list[tuple[float, int]] = []
        for site in SITE_IDS:
            indices = site_indices[site]
            result = train_local_epoch_v2(
                global_state=global_state, inputs=train_inputs[indices],
                labels=train.labels[indices], site_id=site, round_number=round_number,
                experiment_id=config["shuffle_seed_namespace"], base_seed=seed,
                batch_size=int(config["training"]["batch_size"]),
                learning_rate=float(config["optimizer"]["learning_rate"]),
                weight_decay=float(config["optimizer"]["weight_decay"]), pos_weight=pos_weight)
            if result.examples_seen != indices.size:
                raise RuntimeError("client sample-count weight mismatch")
            updates.append(result.update)
            losses.append((result.mean_loss, result.examples_seen))
            labels = train.labels[indices]
            client_rows.append({
                "round": round_number, "site_id": site, "patient_count": len(sites[site]),
                "num_examples": result.examples_seen,
                "positive_examples": int(np.sum(labels == 1)),
                "negative_examples": int(np.sum(labels == 0)),
                "shuffle_seed": result.shuffle_seed, "batch_count": result.batch_count,
                "local_epoch": 1, "optimizer": "AdamW",
                "learning_rate": config["optimizer"]["learning_rate"],
                "weight_decay": config["optimizer"]["weight_decay"],
                "local_training_loss": result.mean_loss, "update_norm": result.update_norm,
                "update_bytes": result.update_bytes, "status": "PASS"})
        if round_number == 1:
            parity = flower_reference_parity(global_state, updates)
            if parity["status"] != "PASS":
                raise RuntimeError("Flower/reference aggregation mismatch")
        global_state, _ = aggregate_weighted_deltas(global_state, updates)
        if not all(np.isfinite(v).all() for v in global_state.values()
                   if np.issubdtype(v.dtype, np.floating)):
            raise RuntimeError("nonfinite global state")
        states[round_number] = copy.deepcopy(global_state)
        model = fresh_model_v2()
        restore_state(model, global_state)
        metrics, _, _ = evaluate_model(model, validation_inputs, validation.labels,
                                       validation.participant_group_ids,
                                       pos_weight=pos_weight, partition="VALIDATION")
        total = sum(u.num_examples for u in updates)
        weighted_loss = sum(loss * n for loss, n in losses) / total
        best_so_far = max([float(r["validation_AUPRC"]) for r in round_rows
                           if int(r["round"]) >= 1] + [-math.inf])
        round_rows.append(_round_row(
            round_number, metrics, state_sha(global_state), int(validation.labels.size),
            client_count=len(updates), total_examples=total,
            training_weighted_mean_loss=weighted_loss,
            bytes_received=sum(r["update_bytes"] for r in client_rows[-8:]),
            bytes_sent=server_payload * 8,
            selected_best_so_far=float(metrics["AUPRC"]) > best_so_far,
            round_wall_seconds=round(time.monotonic() - started, 3)))
        print(f"round {round_number:02d} AUPRC={metrics['AUPRC']:.4f} "
              f"loss={weighted_loss:.4f}", flush=True)
    best_round = choose_best_round(round_rows)
    best_row = next(r for r in round_rows if int(r["round"]) == best_round)
    best_state = states[best_round]
    config_sha = hash_file(config_path)
    ckpt_dir = root / CKPT_RELATIVE
    best_path = ckpt_dir / f"{EXPERIMENT_ID}_best.pt"
    rounds = int(config["training"]["rounds"])
    final_path = ckpt_dir / f"{EXPERIMENT_ID}_round{rounds}.pt"
    save_checkpoint(best_path, state=best_state, round_number=best_round,
                    validation_auprc=float(best_row["validation_AUPRC"]),
                    config_sha=config_sha, manifest_sha=manifest_sha)
    save_checkpoint(final_path, state=states[rounds], round_number=rounds,
                    validation_auprc=float(round_rows[-1]["validation_AUPRC"]),
                    config_sha=config_sha, manifest_sha=manifest_sha)
    best_model = fresh_model_v2()
    restore_state(best_model, best_state)
    best_metrics, best_logits, best_probs = evaluate_model(
        best_model, validation_inputs, validation.labels, validation.participant_group_ids,
        pos_weight=pos_weight, partition="VALIDATION")
    predictions = [{
        "example_id": eid, "participant_group_id": group, "label": int(label),
        "raw_logit": format(float(logit), ".17g"),
        "raw_sigmoid_probability": format(float(prob), ".17g"),
        "prediction_at_0_5": int(prob >= 0.5), "round": best_round}
        for eid, group, label, logit, prob in zip(
            validation.example_ids, validation.participant_group_ids, validation.labels,
            best_logits, best_probs, strict=True)]
    _write_csv(out / "validation_predictions_best_round.csv", predictions)
    from federated.validation_group_metrics import validation_patient_metrics

    patient_metrics = validation_patient_metrics(
        validation.labels, best_probs, validation.participant_group_ids)
    _write_json(out / "validation_patient_metrics_best_round.json", patient_metrics)
    diagnostics: dict[str, Any] = {}
    for site in SITE_IDS:
        idx = site_indices[site]
        site_metrics, _, _ = evaluate_model(
            best_model, train_inputs[idx], train.labels[idx], train.participant_group_ids[idx],
            pos_weight=pos_weight, partition="SITE_LOCAL_TRAIN_DIAGNOSTIC")
        diagnostics[site] = site_metrics
    _write_csv(out / "round_log.csv", round_rows)
    _write_csv(out / "client_rounds.csv", client_rows)
    stability = stable_convergence(round_rows, client_rows)
    _write_json(out / "stability_audit.json", stability)
    if parity is None:
        raise RuntimeError("missing aggregation parity evidence")
    _write_json(out / "aggregation_parity.json", parity)
    local_auprcs = [float(diagnostics[s]["AUPRC"]) for s in SITE_IDS]
    c2s = sum(int(r["update_bytes"]) for r in client_rows[:8])
    report = {
        "experiment_id": EXPERIMENT_ID, "initialization_id": INITIALIZATION_ID,
        "client_manifest_id": "CLIENTS_IID_V1", "client_manifest_sha256": manifest_sha,
        "config_sha256": config_sha, "model_architecture_id": "MODEL_V2_TCN_MEAN",
        "round_0_state_sha256": initial_sha, "trained_MODEL_V2_FINAL_state_sha256": trained_sha,
        "central_checkpoint_loaded_as_initialization": False,
        "best_round": best_round, "round_0_validation": metrics0,
        "best_validation": best_metrics,
        "round_50_validation_AUPRC": round_rows[-1]["validation_AUPRC"],
        "best_checkpoint": f"{CKPT_RELATIVE}/{EXPERIMENT_ID}_best.pt",
        "best_checkpoint_sha256": hash_file(best_path),
        "round_50_checkpoint": f"{CKPT_RELATIVE}/{EXPERIMENT_ID}_round{rounds}.pt",
        "round_50_checkpoint_sha256": hash_file(final_path),
        "best_checkpoint_bytes": best_path.stat().st_size,
        "site_local_train_diagnostics": diagnostics,
        "site_local_train_summary": {
            "mean_AUPRC": float(np.mean(local_auprcs)),
            "median_AUPRC": float(np.median(local_auprcs)),
            "minimum_AUPRC": float(np.min(local_auprcs)),
            "label": "SITE_LOCAL_TRAIN_DIAGNOSTIC", "held_out_client_generalization_claim": False},
        "communication": {
            "server_to_client_bytes_per_round": server_payload * 8,
            "client_to_server_bytes_per_round": c2s,
            "total_server_to_client_bytes": server_payload * 8 * 50,
            "total_client_to_server_bytes": sum(int(r["bytes_received"]) for r in round_rows),
            "network_traffic_measured": False},
        "total_round_wall_seconds": round(sum(
            float(r["round_wall_seconds"]) for r in round_rows if r["round_wall_seconds"] != ""),
            1),
        "stability": stability, "FL_calibration": "NONE", "CAL_V2_applied": False,
        "claim_boundary": {"controlled_simulated_sites": True, "real_hospital_claim": False,
                           "privacy_guarantee": False, "held_out_FL_test_performance": False},
        "status": "COMPLETE"}
    _write_json(out / "fl_iid_model_v2_result.json", report)
    return report


if __name__ == "__main__":
    result = run(Path(__file__).resolve().parents[1])
    print(json.dumps({"status": result["status"], "best_round": result["best_round"]}))
