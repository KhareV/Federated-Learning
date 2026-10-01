#!/usr/bin/env python3
"""Freeze the pre-result T028 SecAgg+ method."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    bound = [
        "configs/secagg_v1.yaml",
        "docs/privacy_threat_model.md",
        "privacy/secagg_app.py",
        "privacy/server_visibility.py",
        "privacy/accounting.py",
        "manifests/clients/CLIENTS_IID_V1.csv",
        "artifacts/FL_CONFIG_V1.lock.json",
        "federated/aggregation.py",
        "configs/fl_state_transport_v1.yaml",
        "reports/t028/flower_secagg_api_audit.json",
        "reports/t028/clipping_preflight.json",
    ]
    payload = {
        "lock_id": "SECAGG_METHOD_V1",
        "status": "FROZEN_PRE_RESULT_METHOD",
        "Flower_version": "1.39.0",
        "base_condition": "FL_IID_V1",
        "protocol": "Flower SecAggPlusWorkflow + secaggplus_mod",
        "configuration": {
            "clients": 8,
            "num_shares": 5,
            "reconstruction_threshold": 4,
            "max_weight": 4096.0,
            "clipping_range": 8.0,
            "quantization_range": 2**22,
            "modulus_range": 2**32,
            "injected_dropout": 0,
        },
        "correctness_tolerance": {"max_absolute": 1e-4, "relative_L2": 1e-4},
        "visibility_boundary": "FLOWER_APPLICATION_SERVER_AGGREGATION_INTERFACE_V1",
        "byte_accounting": "FLOWER_APPLICATION_PAYLOAD_BYTES_V1",
        "runtime_trials": {"warmup": 1, "measured": 10},
        "claim_boundary": "narrow application-interface observation only",
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound},
    }
    destination = ROOT / "artifacts/SECAGG_METHOD_V1.lock.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(destination))


if __name__ == "__main__":
    main()
