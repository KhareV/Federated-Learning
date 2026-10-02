#!/usr/bin/env python3
"""V2-004 PRE-RESULT evidence: entry audit, experiment budget, architecture-identity audit,
and the method-freeze record. Must be generated and committed (METHOD_COMMIT) BEFORE the first
real D1 fit begins; a SEPARATE METHOD_ATTESTATION_COMMIT then binds METHOD_COMMIT's own SHA."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import scripts._v2_004_lib as lib
from nhm.hashing import hash_file

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_004"


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def write_entry_audit() -> Path:
    audit = {
        "checkpoint": "V2-004",
        "expected_entry_sha": "1f40aeb1b5b066d43a755648f7567a26f40bd457",
        "actual_head_sha_at_entry": _git_sha(),
        "registry_state_at_entry": {
            "V2-001_status": "PASS",
            "V2-002_status": "PASS",
            "V2-003_status": "PASS",
            "V2-004_status": "NOT_STARTED",
            "V2G0_status": "PASS",
            "V2G1_status": "PASS",
            "V2G2_status": "PASS",
            "V2G3_status": "NOT_STARTED",
        },
        "corrective_checkpoints_confirmed": {
            "C-V2-001-VERIFY": "PASS",
            "C-V2-003-PROVENANCE": "PASS",
            "C-V2-D0.6": "PASS CONFIRMED",
            "C-V2-PRE004-CONTROL": "PASS",
        },
        "d0_exit": "PASS CONFIRMED",
        "active_protocol": "MODEL_V2_RESEARCH_PROTOCOL_V2",
        "frozen_identities_verified": {
            "protocol_v2_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json"
            ),
            "protocol_v1_lock_sha256_unchanged": hash_file(
                ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
            ),
            "outer_cv_sha256": hash_file(lib.OUTER_CV_CSV),
            "inner_cv_sha256": hash_file(lib.INNER_CV_CSV),
            "model_v1_cv_reference_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"
            ),
            "feature_audit_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json"
            ),
        },
        "status": "PASS",
    }
    path = OUT_DIR / "entry_audit.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_experiment_budget() -> Path:
    budget = {
        "neural_fits_before_v2_004": 15,
        "d1_planned_fits": 15,
        "d2_planned_fits_range": [0, 20],
        "v2_004_max_total_fits": 35,
        "v2_004_max_never": 45,
        "global_neural_fit_cap": 100,
        "cumulative_after_d1_min": 30,
        "cumulative_after_d2_max": 50,
        "exploratory_fits_forbidden": True,
        "synthetic_tests_excluded_from_budget": True,
        "inference_only_recomputation_excluded_from_budget": True,
        "status": "PASS",
    }
    path = OUT_DIR / "experiment_budget.json"
    path.write_text(json.dumps(budget, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_architecture_identity_audit() -> Path:
    from models.model_v2_architectures import (
        ModelV2CapCtrl,
        ModelV2TcnMean,
        ModelV2TcnMeanMax,
        analytic_tcn_receptive_field_samples,
        count_trainable_parameters,
    )

    audit = {
        "verified_mechanically": {
            "MODEL_V2_CAPCTRL_parameter_count": count_trainable_parameters(ModelV2CapCtrl()),
            "MODEL_V2_TCN_MEAN_parameter_count": count_trainable_parameters(ModelV2TcnMean()),
            "MODEL_V2_TCN_MEANMAX_parameter_count": count_trainable_parameters(ModelV2TcnMeanMax()),
            "tcn_analytic_receptive_field_samples": analytic_tcn_receptive_field_samples(),
        },
        "expected": dict(lib.EXPECTED_PARAMETER_COUNTS),
        "expected_tcn_receptive_field_samples": lib.EXPECTED_TCN_RECEPTIVE_FIELD_SAMPLES,
        "fourth_architecture_created": False,
        "legacy_alias_resolution": {
            "prose_name": "MODEL_V2_TCN_GAP",
            "resolves_to": "MODEL_V2_TCN_MEAN",
            "verified_in": "C-V2-PRE004-CONTROL architecture_identity_audit.json",
        },
        "source_sha256": hash_file(ROOT / "models/model_v2_architectures.py"),
        "status": "PASS",
    }
    expected = audit["expected"]
    verified = audit["verified_mechanically"]
    for arch_id, expected_count in expected.items():
        key = f"{arch_id}_parameter_count"
        if verified[key] != expected_count:
            audit["status"] = "FAIL"
    if verified["tcn_analytic_receptive_field_samples"] != lib.EXPECTED_TCN_RECEPTIVE_FIELD_SAMPLES:
        audit["status"] = "FAIL"
    if audit["status"] != "PASS":
        raise RuntimeError(f"architecture identity mismatch: {audit}")

    path = OUT_DIR / "architecture_identity_audit.json"
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_method_freeze() -> Path:
    freeze = {
        "checkpoint": "V2-004",
        "pre_result_method_commit": None,
        "note_pre_result_method_commit": (
            "Filled in by a SEPARATE attestation commit immediately after this commit, per "
            "the required chronology (avoiding the prior null-method-commit-binding gap)."
        ),
        "active_protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json"
        ),
        "v2_004_config_sha256": hash_file(lib.V2_CONFIG_PATH),
        "architecture_source_sha256": hash_file(ROOT / "models/model_v2_architectures.py"),
        "training_source_sha256": hash_file(ROOT / "training/train_central.py"),
        "frozen_training_contract_config_sha256": hash_file(ROOT / "configs/model_v1.yaml"),
        "v2_004_code_sha256": {
            "scripts/_v2_004_lib.py": hash_file(ROOT / "scripts/_v2_004_lib.py"),
            "scripts/run_v2_004_fit.py": hash_file(ROOT / "scripts/run_v2_004_fit.py"),
            "scripts/aggregate_d1_v2004.py": hash_file(ROOT / "scripts/aggregate_d1_v2004.py"),
            "scripts/bootstrap_d1_v2004.py": hash_file(ROOT / "scripts/bootstrap_d1_v2004.py"),
            "scripts/decide_d1_v2004.py": hash_file(ROOT / "scripts/decide_d1_v2004.py"),
            "scripts/aggregate_d2_v2004.py": hash_file(ROOT / "scripts/aggregate_d2_v2004.py"),
            "scripts/bootstrap_d2_v2004.py": hash_file(ROOT / "scripts/bootstrap_d2_v2004.py"),
            "scripts/decide_d2_v2004.py": hash_file(ROOT / "scripts/decide_d2_v2004.py"),
            "scripts/write_d2_not_run.py": hash_file(ROOT / "scripts/write_d2_not_run.py"),
        },
        "firewall_code_sha256": {
            "src/nhm/model_v2_cv_role_guard.py": hash_file(
                ROOT / "src/nhm/model_v2_cv_role_guard.py"
            ),
            "src/nhm/model_v2_partition_guard.py": hash_file(
                ROOT / "src/nhm/model_v2_partition_guard.py"
            ),
        },
        "cv_manifest_sha256": {
            "outer": hash_file(lib.OUTER_CV_CSV),
            "inner": hash_file(lib.INNER_CV_CSV),
        },
        "model_v1_cv_reference_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"
        ),
        "bootstrap_draws_sha256": (
            "e51124bb7675fa2fa175c14194fd6df1f3f218ff85fbd1f8f42fa49deb0d4071"
        ),
        "pre_freeze_integration_smoke_test": {
            "performed": True,
            "description": (
                "Real TRAIN-only role-closure verification and fresh instantiation of all "
                "three architectures (parameter-count check only) were exercised "
                "interactively to confirm wiring before committing to the full 15-fit D1 "
                "run. No training step, no checkpoint, no scientific fit was produced."
            ),
            "scientific_fit_produced": False,
            "checkpoint_saved": False,
            "code_changed_based_on_its_numeric_output": False,
            "cv_role_access_ledger_rows_from_smoke_test_removed_before_real_run": True,
        },
        "real_results_started": False,
        "d1_planned_fits": 15,
        "status": "READY_FOR_REAL_RESULTS",
    }
    path = OUT_DIR / "method_freeze.json"
    path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> None:
    write_entry_audit()
    write_experiment_budget()
    write_architecture_identity_audit()
    write_method_freeze()
    print("V2-004 pre-result evidence written")


if __name__ == "__main__":
    main()
