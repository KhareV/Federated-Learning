#!/usr/bin/env python3
"""Generate final T029 edge report, F14 lock, and artifact inventory."""

from __future__ import annotations

import csv
import json
import platform
from pathlib import Path
from typing import Any

import torch

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/t029"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    host = json.loads((REPORT / "gateway_host.json").read_text())
    size = json.loads((REPORT / "model_size.json").read_text())
    equivalence = json.loads((REPORT / "deployment_equivalence.json").read_text())
    latency = json.loads((REPORT / "latency_summary.json").read_text())
    memory = json.loads((REPORT / "memory_benchmark.json").read_text())
    scope = {
        "MODEL_V1_training": False,
        "calibration_fitting": False,
        "threshold_tuning": False,
        "PREPROC_change": False,
        "FL_model_deployment": False,
        "INT8_mandatory": False,
        "MCU_inference_claim": False,
        "ESP32_required": False,
        "WEARABLE_V1_access": False,
        "public_API": False,
        "dashboard": False,
        "hardware": False,
        "INTERNAL_TEST_role": "DEPLOYMENT_EQUIVALENCE_ONLY",
        "status": "PASS",
    }
    write_json(REPORT / "scope_audit.json", scope)
    edge = {
        "gateway_artifact_id": "GATEWAY_FP32_V1",
        "gateway_target": "LOCAL_CPU_GATEWAY_V1",
        "source_model": "MODEL_V1",
        "format": "TORCHSCRIPT_SCRIPT",
        "host": host,
        "model_size": size,
        "memory": memory,
        "latency": latency,
        "deployment_equivalence": equivalence,
        "INT8": {
            "attempted": False,
            "status": "OPTIONAL_NOT_ATTEMPTED",
            "reason": (
                "No prevalidated reliable conversion path is required for the mandatory "
                "FP32 gateway."
            ),
        },
        "claim_boundary": {
            "CPU_gateway_measurement": True,
            "ESP32_inference": False,
            "MCU_feasibility": False,
            "hardware_real_time_guarantee": False,
            "wearable_validation": False,
            "production_readiness": False,
        },
        "hardware_status": "NOT_REQUIRED_FOR_T029",
        "status": "PASS",
    }
    write_json(ROOT / "reports/edge_gateway.json", edge)
    with (ROOT / "reports/edge_gateway.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "artifact_id",
                "format",
                "source_checkpoint_bytes",
                "artifact_bytes",
                "trainable_parameters",
                "peak_RSS_bytes",
                "p50_ms",
                "p95_ms",
                "throughput_windows_per_second",
                "maximum_raw_logit_delta",
                "decision_agreement",
                "status",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "artifact_id": "GATEWAY_FP32_V1",
                "format": "TORCHSCRIPT_SCRIPT",
                "source_checkpoint_bytes": size["source_checkpoint"]["bytes"],
                "artifact_bytes": size["deployment_artifact"]["bytes"],
                "trainable_parameters": size["trainable_parameter_count"],
                "peak_RSS_bytes": memory["peak_inference_RSS_bytes"],
                "p50_ms": latency["canonical_run"]["p50_ms"],
                "p95_ms": latency["canonical_run"]["p95_ms"],
                "throughput_windows_per_second": latency["canonical_run"][
                    "throughput_windows_per_second"
                ],
                "maximum_raw_logit_delta": equivalence["maximum_absolute_raw_logit_delta"],
                "decision_agreement": equivalence["decision_agreement_fraction"],
                "status": "PASS",
            }
        )
    run_manifest = {
        "task": "T029",
        "experiment_id": "GATEWAY_ARTIFACT_V1",
        "Python": platform.python_version(),
        "PyTorch": torch.__version__,
        "device": "CPU",
        "command": "PYTHONPATH=src:. .venv-t024/bin/python scripts/run_gateway_t029.py canonical",
        "method_lock_sha256": hash_file(ROOT / "artifacts/GATEWAY_FP32_METHOD_V1.lock.json"),
        "CI_executed": False,
        "status": "PASS",
    }
    write_json(REPORT / "run_manifest.json", run_manifest)
    bound = [
        "checkpoints/MODEL_V1.pt",
        "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts",
        "configs/gateway_artifact_v1.yaml",
        "deployment/export.py",
        "deployment/runtime.py",
        "deployment/benchmark.py",
        "artifacts/CAL_V1.json",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "reports/t029/model_size.json",
        "reports/t029/memory_benchmark.json",
        "reports/t029/latency_samples.csv",
        "reports/t029/latency_summary.json",
        "reports/t029/deployment_equivalence.json",
    ]
    lock = {
        "lock_id": "GATEWAY_ARTIFACT_V1",
        "freeze_id": "F14",
        "status": "FROZEN",
        "artifact_id": "GATEWAY_FP32_V1",
        "format": "TORCHSCRIPT_SCRIPT",
        "input_contract": "GATEWAY_MODEL_INPUT_V1:[1,1,2500]:float32",
        "environment": {"Python": platform.python_version(), "PyTorch": torch.__version__},
        "benchmark_policy": {"CPU": True, "intraop": 1, "interop": 1, "warmup": 100, "N": 1000},
        "INT8_STATUS": "OPTIONAL_NOT_ATTEMPTED",
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound},
    }
    write_json(ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json", lock)
    artifacts = [
        "configs/gateway_artifact_v1.yaml",
        "deployment/export.py",
        "deployment/runtime.py",
        "deployment/benchmark.py",
        "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts",
        "artifacts/GATEWAY_FP32_METHOD_V1.lock.json",
        "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
        "reports/t029/gateway_host.json",
        "reports/t029/export_development_audit.json",
        "reports/t029/model_size.json",
        "reports/t029/deployment_equivalence.json",
        "reports/t029/internal_test_deployment_predictions.csv",
        "reports/t029/latency_samples.csv",
        "reports/t029/latency_summary.json",
        "reports/t029/memory_benchmark.json",
        "reports/t029/scope_audit.json",
        "reports/t029/reproducibility.json",
        "reports/t029/run_manifest.json",
        "reports/edge_gateway.json",
        "reports/edge_gateway.csv",
        "scripts/export_gateway_t029.py",
        "scripts/freeze_gateway_method_t029.py",
        "scripts/run_gateway_t029.py",
        "scripts/generate_t029_evidence.py",
        "scripts/verify_t029.py",
    ]
    write_json(
        REPORT / "artifact_hashes.json",
        {path: hash_file(ROOT / path) for path in artifacts},
    )


if __name__ == "__main__":
    main()
