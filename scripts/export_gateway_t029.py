#!/usr/bin/env python3
"""Build GATEWAY_FP32_V1 using development-only F08/synthetic evidence."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path

import numpy as np
import torch

from deployment.benchmark import configure_cpu_threads
from deployment.export import write_export_audit
from models.model_freeze import load_frozen_model_v1
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"


def command(*args: str) -> str | None:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    configure_cpu_threads()
    audit = write_export_audit(ROOT, ARTIFACT)
    model, _ = load_frozen_model_v1(ROOT)
    host = {
        "OS": platform.system(),
        "OS_version": platform.mac_ver()[0] or platform.release(),
        "architecture": platform.machine(),
        "CPU_model": command("sysctl", "-n", "machdep.cpu.brand_string")
        or command("sysctl", "-n", "hw.model")
        or "unavailable",
        "physical_cores": int(command("sysctl", "-n", "hw.physicalcpu") or 0),
        "logical_cores": os.cpu_count(),
        "total_RAM_bytes": int(command("sysctl", "-n", "hw.memsize") or 0),
        "Python": platform.python_version(),
        "PyTorch": torch.__version__,
        "NumPy": np.__version__,
        "device": "CPU",
        "torch_intraop_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "hardware_required": False,
    }
    report = ROOT / "reports/t029/gateway_host.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(host, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    size = {
        "source_checkpoint": {
            "path": "checkpoints/MODEL_V1.pt",
            "sha256": hash_file(ROOT / "checkpoints/MODEL_V1.pt"),
            "bytes": (ROOT / "checkpoints/MODEL_V1.pt").stat().st_size,
        },
        "deployment_artifact": {
            "path": str(ARTIFACT.relative_to(ROOT)),
            "sha256": hash_file(ARTIFACT),
            "bytes": ARTIFACT.stat().st_size,
            "format": audit["format"],
        },
        "deployment_to_source_size_ratio": ARTIFACT.stat().st_size
        / (ROOT / "checkpoints/MODEL_V1.pt").stat().st_size,
        "trainable_parameter_count": sum(
            parameter.numel() for parameter in model.parameters() if parameter.requires_grad
        ),
        "total_parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "total_state_entries": len(model.state_dict()),
        "total_state_values": sum(value.numel() for value in model.state_dict().values()),
        "theoretical_FP32_trainable_parameter_bytes": 4
        * sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad),
        "status": "PASS",
    }
    (ROOT / "reports/t029/model_size.json").write_text(
        json.dumps(size, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"export": audit["status"], "artifact": audit["artifact_sha256"]}))


if __name__ == "__main__":
    main()
