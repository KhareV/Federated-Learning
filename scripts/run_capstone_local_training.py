# ruff: noqa: E501
"""CAP-006 canonical LOCAL training run (fresh process each time).

    PYTHONPATH=src:. python scripts/run_capstone_local_training.py run <N>     # 8 clients, FedAvg, round 1, FL_INIT_V2
    PYTHONPATH=src:. python scripts/run_capstone_local_training.py fedprox     # one-client FedProx local smoke

LOCAL TRAINING ONLY: no aggregation, no coordinator call, no SecAgg, no federation run, no candidate, no
metric. Runtime tripwires make any aggregation/coordinator call raise and are reported. Evidence is bounded
metadata (digests/counts); no tensor, dataset or checkpoint is written.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import federated.aggregation as aggregation_module
import federated.wearable_fl_system_v1 as system_module
import product.federation.client as client_module
from federated.model_v2_fl import state_sha
from federated.wearable_fl_runner_v1 import FORBIDDEN_LOADER_MODULES, new_session
from federated.wearable_fl_system_v1 import state_spec_sha
from product.federation.base import Algorithm
from product.federation.client import frozen_fedprox_mu
from product.federation.local_cohort import build_client
from product.federation.update_bridge import export_envelope, submission_from_envelope

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_006"
TRIPS: dict[str, int] = {"aggregation_or_coordinator_calls": 0}
CALLS: dict[str, int] = {"train_local_epoch_v2": 0, "train_local_fedprox_epoch_v2": 0}


def _trip(*_a: Any, **_k: Any) -> None:
    TRIPS["aggregation_or_coordinator_calls"] += 1
    raise AssertionError("AGGREGATION_OR_COORDINATOR_CALL_FORBIDDEN_IN_CAP_006")


def install_guards() -> None:
    aggregation_module.aggregate_weighted_deltas = _trip  # type: ignore[assignment]
    system_module.aggregate_weighted_deltas = _trip  # type: ignore[assignment]
    for name in ("submit", "submit_meta", "aggregate", "commit", "open"):
        setattr(system_module.Coordinator, name, _trip)
    for name in ("train_local_epoch_v2", "train_local_fedprox_epoch_v2"):
        real = getattr(client_module, name)

        def counted(*, _real=real, _name=name, **kwargs: Any):
            CALLS[_name] += 1
            return _real(**kwargs)
        setattr(client_module, name, counted)


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def client_record(client: Any, buffer: Any, base_state: Any, algorithm: Algorithm) -> dict[str, Any]:
    envelope, report = export_envelope(client, base_state)
    submission = submission_from_envelope(envelope)
    produced = asyncio.run(client.produce_update())
    diagnostics = client._training_diagnostics()
    manifest = buffer.manifest()
    counts = buffer.counts
    record = {
        "client_id": client.identity.client_id, "participant_id": buffer.participant_id,
        "edge_node_id": client.identity.edge_node_id, "buffer_batch_id": manifest["buffer_batch_ids"][0],
        "dataset_sha256": manifest["dataset_sha256"], "buffer_semantic_sha256": manifest["buffer_semantic_sha256"],
        "source_records": counts["source_records"], "windows_emitted": counts["windows_emitted"],
        "quality_counts": {k: counts[k] for k in ("VALID", "DEGRADED", "UNUSABLE")},
        "eligible_examples": manifest["eligible_count"], "buffer_record_count": manifest["record_count"],
        "synthetic_positive": manifest["synthetic_positive"], "synthetic_negative": manifest["synthetic_negative"],
        "base_model_id": client.identity.base_model_id, "base_state_sha256": client.base_state_sha,
        "round": client.identity.global_round, "algorithm": algorithm.value,
        "examples_seen": diagnostics["examples_seen"], "batch_count": diagnostics["batch_count"],
        "shuffle_seed": diagnostics["shuffle_seed"], "update_sha256": envelope["update_sha256"],
        "update_finite": report["all_floating_finite"], "payload_bytes": diagnostics["update_bytes"],
        "state_spec_sha256": envelope["state_spec_sha256"],
        "server_envelope_forbidden_findings": report["forbidden_findings"],
        "envelope_checks": {k: report[k] for k in ("envelope_fields_exact", "keys_match_base", "shapes_match_base", "dtypes_match_base", "integer_buffers_zero_delta", "update_digest_matches_payload", "floating_tensors", "integer_buffers")},
        "update_submission": submission.model_dump(), "produce_update_equals_envelope_projection": produced == submission,
        "client_state": client.identity.client_state.value, "metrics_computed": False, "aggregation_performed": False,
        "engineering_only": True}
    record["diagnostics_not_in_digest"] = {"mean_loss": diagnostics["mean_loss_diagnostic_only"],
                                          "update_norm": diagnostics["update_norm_diagnostic_only"]}
    return record


def environment_audit() -> dict[str, Any]:
    loaded = sys.modules
    return {"privacy_secagg_app_loaded": "privacy.secagg_app" in loaded,
            "wearable_fl_secagg_shadow_loaded": "federated.wearable_fl_secagg_shadow_v1" in loaded,
            "held_out_loader_modules_loaded": [m for m in FORBIDDEN_LOADER_MODULES if m in loaded],
            "central_persistence_loaded": [m for m in loaded if m.startswith(("capstone_persistence", "product.persistence", "product.sessions"))],
            "monitoring_modules_loaded": [m for m in loaded if m.startswith(("product.monitoring", "product.inference", "product.auth", "api."))],
            "truth_modules_loaded_via_sanctioned_federated_adapter_only": sorted(m for m in loaded if m in ("simulation.fl_cohort_truth_v1", "simulation.truth_v2013"))}


def run_canonical(n: int) -> dict[str, Any]:
    install_guards()
    started = time.time()
    base_state, _ = new_session()
    base_sha, spec_sha = state_sha(base_state), state_spec_sha(base_state)
    clients = []
    for index in range(8):
        client, buffer = build_client(index, base_state, algorithm=Algorithm.FEDAVG)
        client.prepare()
        asyncio.run(client.local_train(1, client.base_state_sha))
        clients.append(client_record(client, buffer, base_state, Algorithm.FEDAVG))
    semantic = {"base_state_sha256": base_sha, "state_spec_sha256": spec_sha,
                "clients": [{k: v for k, v in c.items() if k != "diagnostics_not_in_digest"} for c in clients]}
    return {"run": n, "kind": "CANONICAL_FEDAVG_LOCAL_TRAINING", "pid_excluded_from_digest": os.getpid(),
            "base_model_id": "FL_INIT_V2", "base_state_sha256": base_sha, "state_spec_sha256": spec_sha,
            "algorithm": "FEDAVG", "round": 1, "local_training_calls": dict(CALLS),
            "aggregation_or_coordinator_calls": TRIPS["aggregation_or_coordinator_calls"],
            "clients": clients, "environment": environment_audit(), "metrics_computed": False,
            "aggregation_performed": False, "coordinator_submit_called": False, "federation_run_created": False,
            "candidate_created": False, "secagg_run": False, "semantic_sha256": hashlib.sha256(canonical_json(semantic)).hexdigest(),
            "elapsed_s_diagnostic_only": round(time.time() - started, 1)}


def run_fedprox_smoke() -> dict[str, Any]:
    install_guards()
    base_state, _ = new_session()
    client, buffer = build_client(0, base_state, algorithm=Algorithm.FEDPROX)
    client.prepare()
    asyncio.run(client.local_train(1, client.base_state_sha))
    record = client_record(client, buffer, base_state, Algorithm.FEDPROX)
    return {"kind": "FEDPROX_LOCAL_SMOKE", "classification": "product-adapter compatibility smoke; NOT research efficacy and NOT part of the V2-FL-005 FedAvg parity digest",
            "client_id": record["client_id"], "mu": frozen_fedprox_mu(), "mu_source": "artifacts/FEDPROX_MU_V2.lock.json selected_mu", "mu_search_performed": False,
            "existing_implementation": "federated.model_v2_fedprox.train_local_fedprox_epoch_v2", "local_training_calls": dict(CALLS),
            "examples_seen": record["examples_seen"], "eligible_examples": record["eligible_examples"], "examples_account_exactly": record["examples_seen"] == record["eligible_examples"],
            "update_finite": record["update_finite"], "state_spec_valid": all(record["envelope_checks"][k] for k in ("keys_match_base", "shapes_match_base", "dtypes_match_base", "integer_buffers_zero_delta")),
            "update_digest": record["update_sha256"], "update_digest_matches_payload": record["envelope_checks"]["update_digest_matches_payload"],
            "base_state_sha256": record["base_state_sha256"], "forbidden_findings": record["server_envelope_forbidden_findings"],
            "aggregation_performed": False, "metrics_computed": False, "fedprox_global_model_created": False,
            "aggregation_or_coordinator_calls": TRIPS["aggregation_or_coordinator_calls"], "environment": environment_audit(), "record": record}


def main() -> None:
    mode = sys.argv[1]
    if mode == "run":
        n = int(sys.argv[2])
        result = run_canonical(n)
        (OUT / f"canonical_local_run_{n}.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
        print(json.dumps({"run": n, "semantic_sha256": result["semantic_sha256"], "calls": result["local_training_calls"], "trips": result["aggregation_or_coordinator_calls"]}))
    elif mode == "fedprox":
        result = run_fedprox_smoke()
        (OUT / "fedprox_local_smoke.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
        print(json.dumps({"fedprox": result["update_digest"], "calls": result["local_training_calls"]}))
    else:
        raise SystemExit("usage: run <N> | fedprox")


if __name__ == "__main__":
    main()
