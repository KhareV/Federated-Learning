#!/usr/bin/env python3
"""V2-FL-001 method freeze + synthetic/metadata-only preflight. Runs strictly BEFORE the first real
MODEL_V2 federated run: no patient waveform is read and no outcome exists. Writes the protocol /
initialization / config locks, the state-transport decision evidence and method_freeze.json."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

from federated.aggregation import ClientUpdate, aggregate_weighted_deltas
from federated.local_training import train_local_epoch
from federated.model_adapter import (
    deserialize_state,
    extract_state,
    fresh_model_v1,
    restore_state,
    serialize_state,
)
from federated.model_v2_fl import (
    EXPERIMENT_ID,
    classify_state_entries,
    count_trainable_parameters,
    fresh_initial_state_v2,
    fresh_model_v2,
    state_sha,
    train_local_epoch_v2,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_001"
SEED = 20260927
METHOD_FILES = [
    "configs/model_v2/fl_protocol_v1.yaml", "configs/model_v2/fl_init_v2.yaml",
    "configs/model_v2/fl_iid_model_v2_v1.yaml", "federated/model_v2_fl.py",
    "federated/model_v2_fedavg_runner.py", "scripts/freeze_v2_fl_001_method.py",
    "scripts/run_v2_fl_001.py",
    # reused unchanged (hash-pinned so the method cannot drift after the first outcome)
    "federated/aggregation.py", "federated/model_adapter.py", "federated/local_training.py",
    "federated/evaluation.py", "federated/fedavg_runner.py", "federated/client_manifest.py",
    "federated/validation_group_metrics.py", "models/model_v2_architectures.py",
    "manifests/clients/CLIENTS_IID_V1.csv", "configs/fl_iid_v1.yaml",
    "artifacts/FL_CONFIG_V1.lock.json", "configs/fl_state_transport_v1.yaml",
]


def _write(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fresh_process_init_sha() -> str:
    code = ("from federated.model_v2_fl import fresh_initial_state_v2, state_sha;"
            f"print(state_sha(fresh_initial_state_v2({SEED})))")
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                            text=True, check=True, env={"PYTHONPATH": "src:.", "PATH": ""})
    return result.stdout.strip().splitlines()[-1]


def state_transport_audit() -> dict:
    model = fresh_model_v2()
    rows = classify_state_entries(model)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["role"]] = counts.get(row["role"], 0) + 1
    torch.manual_seed(5)
    model.train()
    x = torch.randn(8, 1, 2500)
    for _ in range(3):
        model(x)
    model.eval()
    reference = model(x).detach().numpy()
    state = extract_state(model)
    restored = deserialize_state(serialize_state(state))
    rebuilt = fresh_model_v2()
    restore_state(rebuilt, restored)
    delta = float(np.max(np.abs(rebuilt.eval()(x).detach().numpy() - reference)))
    identical = (list(restored) == list(state)
                 and all(restored[k].shape == v.shape and restored[k].dtype == v.dtype
                         and np.array_equal(restored[k], v) for k, v in state.items()))
    fresh = fresh_initial_state_v2(SEED)
    d1 = {k: (np.full_like(v, 0.25) if np.issubdtype(v.dtype, np.floating)
              else np.zeros_like(v)) for k, v in fresh.items()}
    d2 = {k: (np.full_like(v, -0.5) if np.issubdtype(v.dtype, np.floating)
              else np.zeros_like(v)) for k, v in fresh.items()}
    new_state, _ = aggregate_weighted_deltas(fresh, [ClientUpdate("A", 3, d1),
                                                     ClientUpdate("B", 1, d2)])
    expected = np.float32((3 * 0.25 - 0.5) / 4)
    toy_ok = all(np.allclose(new_state[k], fresh[k] + expected, atol=1e-7)
                 if np.issubdtype(v.dtype, np.floating) else np.array_equal(new_state[k], v)
                 for k, v in fresh.items())
    data = {
        "transport_id": "FL_STATE_TRANSPORT_V1", "decision": "REUSE_UNCHANGED",
        "FL_STATE_TRANSPORT_V2_created": False,
        "v1_specific_logic_found_in_transport": False,
        "v1_named_items_not_used_here": ["federated.local_training.fresh_model_v1 factory",
                                         "error-message wording in restore_state"],
        "state_entries": len(rows), "role_counts": counts,
        "floating_entries_aggregated": counts.get("floating_trainable_parameter", 0)
        + counts.get("floating_non_trainable_buffer", 0),
        "integer_entries_preserved_server_side": counts.get("integer_bookkeeping_buffer", 0),
        "batchnorm_num_batches_tracked_keys": [r["key"] for r in rows
                                               if r["role"] == "integer_bookkeeping_buffer"],
        "entries": rows, "parameter_count": count_trainable_parameters(model),
        "adapter_round_trip_identical_keys_shapes_dtypes_values": identical,
        "adapter_round_trip_max_abs_raw_logit_delta": delta,
        "toy_analytic_fedavg_with_model_v2_shaped_state": "PASS" if toy_ok else "FAIL",
        "status": "PASS" if identical and delta == 0.0 and toy_ok else "FAIL"}
    _write("state_transport_audit.json", data)
    return data


def initialization_audit() -> dict:
    first = state_sha(fresh_initial_state_v2(SEED))
    second = state_sha(fresh_initial_state_v2(SEED))
    third = _fresh_process_init_sha()
    central = torch.load(ROOT / "checkpoints/MODEL_V2_FINAL.pt", map_location="cpu",
                         weights_only=False)["state_dict"]
    central_sha = state_sha({k: v.numpy().copy() for k, v in central.items()})
    data = {
        "initialization_id": "FL_INIT_V2", "architecture": "MODEL_V2_TCN_MEAN", "seed": SEED,
        "algorithm": "set_determinism(seed); ModelV2TcnMean() default PyTorch initialization",
        "state_dict_keys": len(fresh_initial_state_v2(SEED)), "parameter_count": 57553,
        "round_0_state_sha256": first, "repeat_in_process_sha256": second,
        "repeat_fresh_process_sha256": third,
        "identical": first == second == third,
        "MODEL_V2_FINAL_state_sha256_audit_only": central_sha,
        "equal_to_trained_checkpoint": first == central_sha,
        "trained_central_checkpoint_loaded_as_initialization": False,
        "status": "PASS" if first == second == third != central_sha else "FAIL"}
    _write("initialization_audit.json", data)
    return data


def local_training_equivalence() -> dict:
    rng = np.random.default_rng(11)
    x = rng.normal(size=(130, 1, 2500)).astype(np.float32)
    y = (np.arange(130) % 3 == 0).astype(np.int64)
    state = extract_state(fresh_model_v1())
    kwargs = dict(global_state=state, inputs=x, labels=y, site_id="SITE_03", round_number=2,
                  experiment_id="FL_IID_V1", base_seed=SEED, batch_size=64, learning_rate=1e-3,
                  weight_decay=1e-4, pos_weight=1.7157717177396683)
    ref = train_local_epoch(**kwargs)
    cand = train_local_epoch_v2(**kwargs, model_factory=fresh_model_v1)
    exact = all(np.array_equal(cand.update.delta[k], ref.update.delta[k]) for k in ref.update.delta)
    data = {"comparison": "train_local_epoch_v2(model_factory=MODEL_V1) vs T025 train_local_epoch",
            "bit_identical_delta": exact, "mean_loss_identical": cand.mean_loss == ref.mean_loss,
            "batch_count": cand.batch_count, "T025_semantics": [
                "AdamW reset per client per round", "BCEWithLogitsLoss(global pos_weight)",
                "shuffle=True seeded DataLoader generator", "drop_last=False",
                "no augmentation", "no scheduler", "no gradient clipping",
                "torch.manual_seed(per-client-round seed)"],
            "intentional_difference": "model factory only",
            "status": "PASS" if exact and cand.mean_loss == ref.mean_loss else "FAIL"}
    _write("local_training_equivalence.json", data)
    return data


def manifest_audit() -> dict:
    import csv

    config = yaml.safe_load((ROOT / "configs/model_v2/fl_iid_model_v2_v1.yaml").read_text())
    path = ROOT / config["client_manifest"]["path"]
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (ROOT / "manifests/splits/MITDB_SPLIT_V1.csv").open(newline="") as handle:
        split = list(csv.DictReader(handle))
    patients = [r["participant_group_id"] for r in rows]
    sites: dict[str, int] = {}
    for r in rows:
        sites[r["site_id"]] = sites.get(r["site_id"], 0) + 1
    overlap = {part: sorted(set(patients) & {r["participant_group_id"] for r in split
                                              if r["partition"] == part})
               for part in ("VALIDATION", "CALIBRATION", "INTERNAL_TEST")}
    train_groups = {r["participant_group_id"] for r in split if r["partition"] == "TRAIN"}
    pos, neg = (sum(int(r[k]) for r in rows) for k in ("positive_window_count",
                                                        "negative_window_count"))
    data = {"client_manifest_id": "CLIENTS_IID_V1", "manifest_sha256": hash_file(path),
            "expected_sha256": config["client_manifest"]["sha256"],
            "manifest_regenerated": False, "patient_groups": len(set(patients)),
            "duplicate_patients": len(patients) - len(set(patients)),
            "omitted_train_patients": sorted(train_groups - set(patients)),
            "windows": sum(int(r["eligible_window_count"]) for r in rows),
            "positive": pos, "negative": neg, "sites": len(sites),
            "site_patient_counts": sorted(sites.values(), reverse=True),
            "partition_overlap": overlap, "pos_weight": neg / pos,
            "status": "PASS" if (hash_file(path) == config["client_manifest"]["sha256"]
                                 and len(set(patients)) == 27 == len(patients)
                                 and not any(overlap.values()) and pos == 3557 and neg == 6103
                                 and set(patients) == train_groups) else "FAIL"}
    _write("client_manifest_audit.json", data)
    return data


PROTECTED = [
    "checkpoints/MODEL_V1.pt", "artifacts/CAL_V1.json", "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
    "manifests/preprocessing/PREPROC_V1.lock.json", "manifests/labels/AAMI_SVF_MAP_V1.yaml",
    "manifests/splits/MITDB_SPLIT_V1.csv", "configs/quality_v1.yaml", "preprocessing/quality.py",
    "checkpoints/MODEL_V2_FINAL.pt", "artifacts/CAL_V2.json",
    "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts",
    "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
    "artifacts/ALERT_POLICY_V1.lock.json", "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json",
    "artifacts/API_RUNTIME_V2.lock.json", "artifacts/API_RUNTIME_V2_1.lock.json",
    "artifacts/FL_CONFIG_V1.lock.json", "artifacts/FL_IID_V1.lock.json",
    "artifacts/FL_IID_METHOD_V1.lock.json", "artifacts/FEDPROX_METHOD_V1.lock.json",
    "artifacts/FEDPROX_MU_V1.lock.json", "artifacts/SECAGG_CONFIG_V1.lock.json",
    "manifests/clients/CLIENTS_IID_V1.csv", "reports/fl_iid.json",
    "reports/t025/fl_iid_rounds.csv", "reports/t025/fl_iid_validation_predictions.csv",
    "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
    "reports/model_v2/v2_013/artifact_hashes.json",
    "reports/model_v2/c_v2_013_quality_flatline/artifact_hashes.json",
    "reports/model_v2/v2_012/artifact_hashes.json",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "protected_baseline.json").write_text(json.dumps(
        {"artifacts": {p: hash_file(ROOT / p) for p in PROTECTED}}, indent=2,
        sort_keys=True) + "\n", encoding="utf-8")
    audits = {"state_transport": state_transport_audit(),
              "initialization": initialization_audit(),
              "local_training": local_training_equivalence(),
              "client_manifest": manifest_audit()}
    if any(a["status"] != "PASS" for a in audits.values()):
        sys.exit(f"V2_FL_001_PREFLIGHT_FAILED:{ {k: v['status'] for k, v in audits.items()} }")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    protocol = {
        "lock_id": "MODEL_V2_FL_PROTOCOL_V1", "status": "FROZEN_BEFORE_FIRST_V2_FL_OUTCOME",
        "owner_task": "V2-FL-001",
        "bound_artifacts": {p: hash_file(ROOT / p) for p in (
            "configs/model_v2/fl_protocol_v1.yaml", "configs/model_v2/fl_init_v2.yaml",
            "configs/model_v2/fl_iid_model_v2_v1.yaml", "manifests/clients/CLIENTS_IID_V1.csv",
            "manifests/clients/NONIID_LABEL_V1.csv", "manifests/clients/NONIID_QUANTITY_V1.csv",
            "manifests/clients/NONIID_FEATURE_V1.csv", "manifests/clients/NONIID_COMBINED_V1.csv",
            "configs/fl_feature_noise_v1.yaml", "configs/fl_non_iid_v1.yaml",
            "configs/fl_iid_v1.yaml", "artifacts/FL_CONFIG_V1.lock.json",
            "configs/fl_state_transport_v1.yaml",
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json")},
        "state_transport_decision": "REUSE_FL_STATE_TRANSPORT_V1_UNCHANGED",
        "initialization": {"id": "FL_INIT_V2", "round_0_state_sha256":
                           audits["initialization"]["round_0_state_sha256"]},
        "future_phases_predeclared": ["V2-FL-002", "V2-FL-003", "V2-FL-004", "V2-FL-005"],
        "synthetic_wearable_role": "ENGINEERING_EVIDENCE_NOT_EFFICACY",
        "change_control": "Any change requires a successor protocol; the V2-FL-001 method must "
        "not be modified in response to results."}
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json"
    lock_path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write("method_freeze.json", {
        "owner_task": "V2-FL-001", "experiment_id": EXPERIMENT_ID, "entry_head": head,
        "protocol_lock_sha256": hash_file(lock_path),
        "method_file_sha256": {p: hash_file(ROOT / p) for p in METHOD_FILES},
        "real_outcome_exists_at_method_freeze": False,
        "patient_waveforms_read_during_preflight": False,
        "preflight": {k: v["status"] for k, v in audits.items()},
        "decision_codes_frozen": [
            "checkpoint=best pooled VALIDATION AUPRC rounds 1-50, earliest tie",
            "no retuning of FL budget", "PASS_WITH_SCIENTIFIC_WARNING rule"],
        "status": "PASS"})
    print("V2-FL-001 method frozen at", head)


if __name__ == "__main__":
    main()
