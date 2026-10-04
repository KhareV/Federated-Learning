"""V2-FL-002: matched MODEL_V2_TCN_MEAN FedAvg under the four frozen T026 heterogeneity conditions.

Mirrors federated.non_iid_runner (T026) with the V2-FL-001 model family and local-training
function; client manifests, the NSTDB feature-noise transform, aggregation, transport, evaluation
and checkpoint rule are the frozen V1-lineage implementations, reused unchanged. Reads ONLY
MIT-BIH TRAIN, VALIDATION and (feature/combined) the NSTDB pure-noise records through the frozen
FL_FEATURE_NOISE_V1 training construction; every access is firewall-gated and ledgered, and NSTDB
is ledgered as NSTDB_PURE_NOISE_TRAINING_RESOURCE (never an evaluation access)."""

from __future__ import annotations

import copy
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from sklearn.metrics import average_precision_score, roc_auc_score

from federated.aggregation import ClientUpdate, aggregate_weighted_deltas
from federated.client_manifest import SITE_IDS
from federated.evaluation import evaluate_model
from federated.feature_noise import build_noise_bank, transform_population
from federated.fedavg_runner import (
    _write_csv,
    _write_json,
    choose_best_round,
    flower_reference_parity,
    normalized_population,
    stable_convergence,
)
from federated.model_adapter import restore_state, serialize_state
from federated.model_v2_fl import (
    fresh_initial_state_v2,
    fresh_model_v2,
    set_determinism,
    state_sha,
    train_local_epoch_v2,
)
from federated.non_iid_runner import load_sites
from nhm.hashing import hash_file
from nhm.model_v2_partition_guard import _append_ledger, check_partition_allowed
from training.train_central import WindowPopulation, load_population

STAGE_ID = "V2-FL-002"
ALLOWED = ("TRAIN", "VALIDATION", "NSTDB")  # NSTDB only as pure-noise TRAINING resource
CONFIG_RELATIVE = "configs/model_v2/fl_non_iid_model_v2_v1.yaml"
OUT_RELATIVE = "reports/model_v2/v2_fl_002"
CKPT_RELATIVE = "checkpoints/model_v2/v2_fl_002"
NSTDB_ROLE = "NSTDB_PURE_NOISE_TRAINING_RESOURCE"
ORDER = ("label", "quantity", "feature", "combined")


def _ledger(root: Path, partition: str, access_type: str, rows: int | None,
            condition: str, source: str) -> None:
    _append_ledger(root, {
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "stage_id": STAGE_ID, "experiment_id": condition, "partition": partition,
        "access_type": access_type, "rows": rows, "source_path": source})


def guarded_population(root: Path, partition: str, condition: str) -> WindowPopulation:
    if partition not in ("TRAIN", "VALIDATION"):
        check_partition_allowed(partition, STAGE_ID, ("TRAIN", "VALIDATION"))
    population = load_population(partition)
    _ledger(root, partition, "waveform_read", int(population.labels.size), condition,
            "frozen MITDB_WINDOWS_V1 caches (load_population)")
    return population


def guarded_noise_bank(root: Path, condition: str) -> dict[str, np.ndarray]:
    check_partition_allowed("NSTDB", STAGE_ID, ALLOWED)
    bank, _ = build_noise_bank(root)
    _ledger(root, "NSTDB", NSTDB_ROLE, sum(int(v.size) for v in bank.values()), condition,
            "data/raw/nstdb/1.0.0/{bw,em,ma} (FL_FEATURE_NOISE_V1 pure-noise records)")
    return bank


def per_patient_metrics(labels: np.ndarray, probs: np.ndarray, groups: np.ndarray) -> dict:
    """Per-VALIDATION-patient AUPRC/AUROC/F1@0.5 with undefined values preserved as None.
    Validation patient groups are evaluation units, not federated clients."""
    rows = []
    for group in sorted(set(groups.tolist())):
        mask = groups == group
        y, p = labels[mask], probs[mask]
        pos, neg = int(np.sum(y == 1)), int(np.sum(y == 0))
        pred = p >= 0.5
        tp = int(np.sum(pred & (y == 1)))
        fp = int(np.sum(pred & (y == 0)))
        fn = int(np.sum(~pred & (y == 1)))
        denominator = 2 * tp + fp + fn
        rows.append({
            "participant_group_id": group, "windows": int(mask.sum()), "positives": pos,
            "negatives": neg,
            "AUPRC": float(average_precision_score(y, p)) if pos > 0 else None,
            "AUROC": float(roc_auc_score(y, p)) if pos > 0 and neg > 0 else None,
            "F1_at_0_5": (2 * tp / denominator) if denominator > 0 else None,
            "true_positives": tp, "false_positives": fp, "false_negatives": fn})
    finite = [r["AUPRC"] for r in rows if r["AUPRC"] is not None and math.isfinite(r["AUPRC"])]
    return {
        "per_group": rows, "evaluation_unit": "MITDB_VALIDATION_PARTICIPANT_GROUP",
        "validation_patients_are_clients": False,
        "VALIDATION_PATIENT_MACRO_AUPRC_V2": float(np.mean(finite)) if finite else None,
        "VALIDATION_PATIENT_WORST_AUPRC_V2": float(np.min(finite)) if finite else None,
        "finite_AUPRC_patients": len(finite), "undefined_AUPRC_patients": len(rows) - len(finite),
        "semantics": "FEDPROX_SELECTION_SEMANTICS_V1 (unweighted over finite per-patient values)"}


def save_checkpoint(path: Path, state: dict[str, np.ndarray], *, experiment_id: str,
                    round_number: int, auprc: float, config_sha: str, manifest_sha: str) -> None:
    model = fresh_model_v2()
    restore_state(model, state)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "checkpoint_id": experiment_id, "model_architecture_id": "MODEL_V2_TCN_MEAN",
        "initialization_id": "FL_INIT_V2", "FL_family": "FL_NON_IID_MODEL_V2_V1",
        "round": round_number, "validation_AUPRC": auprc, "config_sha256": config_sha,
        "client_manifest_sha256": manifest_sha, "transport_id": "FL_STATE_TRANSPORT_V1",
        "aggregation_id": "SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1", "calibration": "NONE",
        "supersedes_model_v2_final": False, "state_dict": copy.deepcopy(model.state_dict())},
        path)


def verify_entry(root: Path) -> dict[str, Any]:
    """Re-verify the committed V2-FL-001 reference and every frozen reference before training."""
    config = yaml.safe_load((root / CONFIG_RELATIVE).read_text())
    problems = []
    for name, ref in config["references"].items():
        if "sha256" in ref and hash_file(root / ref["path"]) != ref["sha256"]:
            problems.append(name)
    for key, cond in config["conditions"].items():
        if hash_file(root / "manifests/clients" / f"{cond['manifest']}.csv") != cond[
                "manifest_sha256"]:
            problems.append(f"manifest:{key}")
    if hash_file(root / "manifests/clients/CLIENTS_IID_V1.csv") != (
            "80f38fa25c508f9b4e2a4fd49e29c4c8d0034443ec67f7c24bc0954912b6c32a"):
        problems.append("CLIENTS_IID_V1")
    iid = config["v2_iid_reference"]
    result = json.loads((root / "reports/model_v2/v2_fl_001/fl_iid_model_v2_result.json"
                         ).read_text())
    ckpt_dir = root / "checkpoints/model_v2/v2_fl_001"
    checks = {
        "best_ckpt": hash_file(ckpt_dir / "FL_IID_MODEL_V2_V1_best.pt")
        == iid["best_checkpoint_sha256"],
        "round50_ckpt": hash_file(ckpt_dir / "FL_IID_MODEL_V2_V1_round50.pt")
        == iid["round_50_checkpoint_sha256"],
        "best_round": result["best_round"] == iid["best_round"],
        "best_auprc": result["best_validation"]["AUPRC"] == iid["best_validation_AUPRC"],
        "round50_auprc": result["round_50_validation_AUPRC"] == iid["round_50_AUPRC"],
        "init_sha": result["round_0_state_sha256"] == config["initialization"][
            "round_0_state_sha256"],
        "round0_auprc": result["round_0_validation"]["AUPRC"] == config["initialization"][
            "round_0_validation_AUPRC"]}
    problems += [k for k, ok in checks.items() if not ok]
    freeze = json.loads((root / "reports/model_v2/v2_fl_001/method_freeze.json").read_text())
    problems += [f"v2_fl_001_method:{p}" for p, d in freeze["method_file_sha256"].items()
                 if hash_file(root / p) != d]
    return {"problems": problems, "status": "PASS" if not problems else "FAIL"}


def run_condition(root: Path, condition: str) -> dict[str, Any]:
    started = time.monotonic()
    out = root / OUT_RELATIVE
    config_path = root / CONFIG_RELATIVE
    config = yaml.safe_load(config_path.read_text())
    cond = config["conditions"][condition]
    experiment_id = cond["experiment_id"]
    manifest_path = root / "manifests/clients" / f"{cond['manifest']}.csv"
    sites = load_sites(manifest_path)
    seed = int(config["initialization"]["seed"])
    set_determinism(seed)
    train = guarded_population(root, "TRAIN", condition)
    validation = guarded_population(root, "VALIDATION", condition)
    clean_train = normalized_population(train)
    validation_inputs = normalized_population(validation)
    group_to_site = {g: s for s, groups in sites.items() for g in groups}
    site_indices = {s: np.flatnonzero(np.isin(train.participant_group_ids, groups))
                    for s, groups in sites.items()}
    train_inputs, noise_fixtures = clean_train, []
    if cond["feature_noise"]:
        bank = guarded_noise_bank(root, condition)
        site_for_example = {str(e): group_to_site[str(g)] for e, g in zip(
            train.example_ids, train.participant_group_ids, strict=True)}
        train_inputs, noise_fixtures = transform_population(
            np.asarray(train.waveforms, dtype=np.float64), train.example_ids,
            site_for_example, bank)
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    if not math.isclose(pos_weight, float(config["loss"]["pos_weight"]), rel_tol=0,
                        abs_tol=1e-15):
        raise RuntimeError("global TRAIN pos_weight mismatch")
    global_state = fresh_initial_state_v2(seed)
    initial_sha = state_sha(global_state)
    if initial_sha != config["initialization"]["round_0_state_sha256"]:
        raise RuntimeError("ROUND0_STATE_NOT_FL_INIT_V2")
    model = fresh_model_v2()
    restore_state(model, global_state)
    metrics0, _, _ = evaluate_model(model, validation_inputs, validation.labels,
                                    validation.participant_group_ids, pos_weight=pos_weight,
                                    partition="VALIDATION")
    if metrics0["AUPRC"] != config["initialization"]["round_0_validation_AUPRC"]:
        raise RuntimeError("ROUND0_VALIDATION_DIFFERS_FROM_V2_FL_001: STOP")

    def row(round_number: int, metrics: dict[str, Any], sha: str, **extra: Any) -> dict[str, Any]:
        base = {
            "round": round_number, "client_count": 0, "total_examples": 0,
            "training_weighted_mean_loss": "", "validation_windows": int(validation.labels.size),
            "validation_AUPRC": metrics["AUPRC"], "validation_AUROC": metrics["AUROC"],
            "validation_raw_F1_at_0_5": metrics["pooled_F1"],
            "validation_precision_at_0_5": metrics["precision"],
            "validation_sensitivity_at_0_5": metrics["sensitivity"],
            "validation_specificity_at_0_5": metrics["specificity"],
            "validation_patient_macro_F1_at_0_5": metrics["patient_macro_F1"],
            "validation_BCE": metrics["BCE"], "global_state_sha256": sha, "bytes_received": 0,
            "bytes_sent": 0, "finite_state": True, "selected_best_so_far": False,
            "round_wall_seconds": ""}
        base.update(extra)
        return base

    rounds = [row(0, metrics0, initial_sha)]
    clients: list[dict[str, Any]] = []
    states: dict[int, dict[str, np.ndarray]] = {0: copy.deepcopy(global_state)}
    server_payload = len(serialize_state(global_state))
    parity: dict[str, Any] | None = None
    total_rounds = int(config["training"]["rounds"])
    for round_number in range(1, total_rounds + 1):
        tick = time.monotonic()
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
            clients.append({
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
                raise RuntimeError("aggregation parity")
        global_state, _ = aggregate_weighted_deltas(global_state, updates)
        if not all(np.isfinite(v).all() for v in global_state.values()
                   if np.issubdtype(v.dtype, np.floating)):
            raise RuntimeError("nonfinite state")
        states[round_number] = copy.deepcopy(global_state)
        model = fresh_model_v2()
        restore_state(model, global_state)
        metrics, _, _ = evaluate_model(model, validation_inputs, validation.labels,
                                       validation.participant_group_ids,
                                       pos_weight=pos_weight, partition="VALIDATION")
        total = sum(u.num_examples for u in updates)
        prior = max([float(r["validation_AUPRC"]) for r in rounds if int(r["round"]) >= 1]
                    + [-math.inf])
        rounds.append(row(
            round_number, metrics, state_sha(global_state), client_count=len(updates),
            total_examples=total,
            training_weighted_mean_loss=sum(a * n for a, n in losses) / total,
            bytes_received=sum(int(r["update_bytes"]) for r in clients[-8:]),
            bytes_sent=server_payload * 8,
            selected_best_so_far=float(metrics["AUPRC"]) > prior,
            round_wall_seconds=round(time.monotonic() - tick, 3)))
        print(f"{condition} round {round_number:02d} AUPRC={metrics['AUPRC']:.4f}", flush=True)
    best_round = choose_best_round(rounds)
    best_row = next(r for r in rounds if int(r["round"]) == best_round)
    config_sha, manifest_sha = hash_file(config_path), hash_file(manifest_path)
    ckpt_dir = root / CKPT_RELATIVE
    best_path = ckpt_dir / f"{experiment_id}_best.pt"
    final_path = ckpt_dir / f"{experiment_id}_round{total_rounds}.pt"
    save_checkpoint(best_path, states[best_round], experiment_id=experiment_id,
                    round_number=best_round, auprc=float(best_row["validation_AUPRC"]),
                    config_sha=config_sha, manifest_sha=manifest_sha)
    save_checkpoint(final_path, states[total_rounds], experiment_id=experiment_id,
                    round_number=total_rounds, auprc=float(rounds[-1]["validation_AUPRC"]),
                    config_sha=config_sha, manifest_sha=manifest_sha)
    best_model = fresh_model_v2()
    restore_state(best_model, states[best_round])
    best_metrics, logits, probs = evaluate_model(
        best_model, validation_inputs, validation.labels, validation.participant_group_ids,
        pos_weight=pos_weight, partition="VALIDATION")
    predictions = [{
        "example_id": str(e), "participant_group_id": str(g), "label": int(y),
        "raw_logit": format(float(lg), ".17g"), "raw_sigmoid_probability": format(float(p), ".17g"),
        "prediction_at_0_5": int(p >= 0.5), "round": best_round}
        for e, g, y, lg, p in zip(validation.example_ids, validation.participant_group_ids,
                                  validation.labels, logits, probs, strict=True)]
    _write_csv(out / f"{condition}_validation_predictions.csv", predictions)
    patient = per_patient_metrics(validation.labels, probs, validation.participant_group_ids)
    _write_json(out / f"{condition}_validation_patient_metrics.json", patient)
    diagnostics, defined = {}, []
    for site in SITE_IDS:
        idx = site_indices[site]
        labels = train.labels[idx]
        site_metrics, _, _ = evaluate_model(
            best_model, clean_train[idx], labels, train.participant_group_ids[idx],
            pos_weight=pos_weight, partition="SITE_LOCAL_TRAIN_DIAGNOSTIC")
        if len(np.unique(labels)) < 2:
            site_metrics["AUPRC"] = None  # undefined stays undefined
        else:
            defined.append(float(site_metrics["AUPRC"]))
        diagnostics[site] = {**site_metrics, "label": "SITE_LOCAL_TRAIN_DIAGNOSTIC"}
    _write_csv(out / f"{condition}_round_log.csv", rounds)
    _write_csv(out / f"{condition}_client_rounds.csv", clients)
    stability = stable_convergence(rounds, clients)
    sent = sum(int(r["bytes_sent"]) for r in rounds)
    received = sum(int(r["bytes_received"]) for r in rounds)
    report = {
        "condition": condition, "experiment_id": experiment_id,
        "manifest_id": cond["manifest"], "manifest_sha256": manifest_sha,
        "config_sha256": config_sha, "round_0_state_sha256": initial_sha,
        "round_0_validation": metrics0, "best_round": best_round, "best_validation": best_metrics,
        "round_50_validation_AUPRC": rounds[-1]["validation_AUPRC"],
        "round_50_validation": next(r for r in rounds if int(r["round"]) == total_rounds),
        "best_checkpoint": f"{CKPT_RELATIVE}/{experiment_id}_best.pt",
        "best_checkpoint_sha256": hash_file(best_path),
        "round_50_checkpoint": f"{CKPT_RELATIVE}/{experiment_id}_round{total_rounds}.pt",
        "round_50_checkpoint_sha256": hash_file(final_path),
        "client_updates": len(clients), "stability": stability, "aggregation_parity": parity,
        "site_local_train_diagnostics": diagnostics,
        "site_local_train_summary": {
            "defined_AUPRC_sites": len(defined), "undefined_AUPRC_sites": 8 - len(defined),
            "mean_AUPRC": float(np.mean(defined)) if defined else None,
            "minimum_AUPRC": float(np.min(defined)) if defined else None,
            "label": "SITE_LOCAL_TRAIN_DIAGNOSTIC", "held_out_client_generalization_claim": False},
        "validation_patient_summary": {k: patient[k] for k in (
            "VALIDATION_PATIENT_MACRO_AUPRC_V2", "VALIDATION_PATIENT_WORST_AUPRC_V2",
            "finite_AUPRC_patients", "undefined_AUPRC_patients")},
        "communication": {
            "server_to_client_bytes_per_round": server_payload * 8,
            "client_to_server_bytes_per_round": int(sum(
                int(c["update_bytes"]) for c in clients[:8])),
            "total_logical_payload_bytes": sent + received, "network_traffic_measured": False},
        "wall_seconds": round(time.monotonic() - started, 1),
        "noise_fixtures": noise_fixtures,
        "nstdb_role": NSTDB_ROLE if cond["feature_noise"] else None,
        "CAL_V2_applied": False, "central_checkpoint_loaded_as_initialization": False,
        "status": "COMPLETE"}
    _write_json(out / f"{condition}_result.json", report)
    return report


__all__ = ["ORDER", "run_condition", "verify_entry"]
