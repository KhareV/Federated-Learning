#!/usr/bin/env python3
"""Validate the T004 hardware-deferral and WEARABLE_SIM_V1 contract, emit evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t004"

HARDWARE_CONTRACT = ROOT / "contracts/HARDWARE_DATA_CONTRACT_V1.md"
WEARABLE_SIM_CONTRACT = ROOT / "contracts/WEARABLE_SIM_V1.md"
SIM_CONFIG = ROOT / "configs/simulation/WEARABLE_SIM_V1.yaml"
CI_WORKFLOW = ROOT / ".github/workflows/t001.yml"


def count_verification_required() -> tuple[int, list[str]]:
    contract = HARDWARE_CONTRACT.read_text(encoding="utf-8")
    rows = re.findall(r"\|\s*\d+\s*\|\s*(.+?)\s*\|\s*VERIFICATION_REQUIRED\s*\|", contract)
    return len(rows), rows


def check_task_registry() -> dict[str, Any]:
    rows = {row["task_id"]: row for row in read_csv(ROOT / "manifests/task_registry_v1.csv")}
    t004 = rows["T004"]
    return {
        "t004_status": t004["status"],
        "t004_status_is_blocked": t004["status"] == "BLOCKED",
        "t001_t003_pass": all(rows[f"T{n:03d}"]["status"] == "PASS" for n in (1, 2, 3)),
    }


def check_gate_and_freeze() -> dict[str, Any]:
    gates = {row["gate_id"]: row for row in read_csv(ROOT / "manifests/gate_registry_v1.csv")}
    freezes = {
        row["freeze_id"]: row for row in read_csv(ROOT / "manifests/freeze_registry_v1.csv")
    }
    return {
        "g1_status": gates["G1"]["status"],
        "g1_not_passed": gates["G1"]["status"] != "PASS",
        "g16_status": gates["G16"]["status"],
        "g16_not_passed": gates["G16"]["status"] != "PASS",
        "f02_status": freezes["F02"]["current_status"],
        "f02_not_frozen": freezes["F02"]["current_status"] != "FROZEN",
    }


def check_ci_policy() -> dict[str, Any]:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow.get(True, workflow.get("on", {}))
    trigger_keys = set(triggers) if isinstance(triggers, dict) else set()
    return {
        "trigger_keys": sorted(trigger_keys),
        "manual_only": trigger_keys == {"workflow_dispatch"},
    }


def check_wearable_sim_contract() -> dict[str, Any]:
    text = WEARABLE_SIM_CONTRACT.read_text(encoding="utf-8")
    required_markers = [
        "WEARABLE_SIM_V1",
        "WEARABLE_V1",
        "SimulationTruth",
        "ObservedRecord",
        "SIM_P000001",
        "SYNTHETIC_PHYSIOLOGY",
        "MITDB_REPLAY",
        "BIDMC_REPLAY",
        "FAULT_INJECTION",
        "LONGITUDINAL_COHORT",
        "LIVE_SPEED_REPLAY",
        "ACCELERATED_REPLAY",
    ]
    markers_present = {marker: marker in text for marker in required_markers}
    distinct_from_real = (
        "does **not** replace, alias, or redefine" in text or "distinct" in text.casefold()
    )
    return {"markers_present": markers_present, "distinct_from_wearable_v1": distinct_from_real}


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    unresolved_count, unresolved_items = count_verification_required()
    task_check = check_task_registry()
    gate_check = check_gate_and_freeze()
    ci_check = check_ci_policy()
    sim_check = check_wearable_sim_contract()

    deferral_ok = (
        task_check["t004_status_is_blocked"]
        and task_check["t001_t003_pass"]
        and gate_check["g1_not_passed"]
        and gate_check["g16_not_passed"]
        and gate_check["f02_not_frozen"]
        and unresolved_count == 17
        and ci_check["manual_only"]
    )
    sim_ok = all(sim_check["markers_present"].values()) and sim_check["distinct_from_wearable_v1"]
    status = "PASS" if deferral_ok and sim_ok else "FAIL"

    hardware_deferral = {
        "task_id": "T004",
        "canonical_objective": "Bench hardware verification and firmware packet contract",
        "execution_status": "BLOCKED",
        "block_reason": "BLOCKED_HARDWARE",
        "hardware_available": False,
        "g1_status": "NOT_PASSED",
        "hardware_contract_frozen": False,
        "software_track_may_continue": True,
        "hardware_dependent_claims_blocked": [
            "G1 hardware verification",
            "real WEARABLE_V1 evidence",
            "G16 wearable validation",
            "physical timing/jitter evidence",
            "real ADC scaling evidence",
        ],
        "resume_condition": (
            "Physical ESP32/AD8232/MAX30102 system available for bench testing"
        ),
        "recovery_path": "continue software with fixtures; block wearable evidence",
        "legacy_firmware_findings": "docs/LEGACY_FIRMWARE_V0_FINDINGS.md",
        "hardware_deferred_execution_plan": "docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md",
        "verification_required_count": unresolved_count,
        "unresolved_hardware_items": unresolved_items,
        "task_registry_check": task_check,
        "gate_and_freeze_check": gate_check,
        "ci_policy_check": ci_check,
        "deferral_record_status": "PASS" if deferral_ok else "FAIL",
    }

    simulation_foundation = {
        "simulation_id": "WEARABLE_SIM_V1",
        "distinct_from": "WEARABLE_V1",
        "supported_modes": [
            "SYNTHETIC_PHYSIOLOGY",
            "MITDB_REPLAY",
            "BIDMC_REPLAY",
            "FAULT_INJECTION",
            "LONGITUDINAL_COHORT",
            "LIVE_SPEED_REPLAY",
            "ACCELERATED_REPLAY",
        ],
        "synthetic_provenance_rule": (
            "Every synthetic record carries dataset_id=WEARABLE_SIM_V1, a SYNTHETIC_* source "
            "value, simulation_version, and simulation_seed; synthetic participants are never "
            "identified as real human volunteers."
        ),
        "truth_channel_separation": (
            "ObservedRecord is what production NHM software receives; SimulationTruth is "
            "internal-only and may be consumed only by tests, simulator validation, and "
            "controlled engineering evaluation, never by production code."
        ),
        "primary_model_real_data_rule": (
            "MODEL_V1 is trained, validated, calibrated, internally tested, and externally "
            "evaluated exclusively on real MIT-BIH/INCART data; synthetic physiology never "
            "substitutes at any stage."
        ),
        "primary_fl_real_patient_rule": (
            "The primary FL efficacy experiment's eight simulated sites are built exclusively "
            "from whole real MIT-BIH training patients; synthetic virtual patients are never "
            "substituted into that experiment."
        ),
        "hardware_resume_dependency": (
            "WEARABLE_SIM_V1 is independent of physical hardware and does not resolve or "
            "substitute for any VERIFICATION_REQUIRED hardware fact; it exists to unblock "
            "hardware-independent software work only."
        ),
        "contract_check": sim_check,
        "status": "PASS" if sim_ok else "FAIL",
    }

    def write_json(path: Path, value: object) -> None:
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    write_json(REPORT_DIR / "hardware_deferral.json", hardware_deferral)
    write_json(REPORT_DIR / "simulation_foundation.json", simulation_foundation)

    print(
        f"T004 deferral validation: {status} "
        f"verification_required={unresolved_count} g1={gate_check['g1_status']} "
        f"ci_manual_only={ci_check['manual_only']}"
    )
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
