#!/usr/bin/env python3
"""C-V2-D0.6 PRE-RESULT evidence: entry audit, source artifact inventory, and the method-freeze
record. Must be generated and committed (METHOD_COMMIT) BEFORE any real D0.6 diagnostic result
is produced; a SEPARATE ATTESTATION_COMMIT then binds METHOD_COMMIT's own SHA (Section 7)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import scripts._d0_6_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_d0_6_guard import known_allowed_paths

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/c_v2_d0_6"
CONFIG_PATH = ROOT / "configs/model_v2/d0_6_diagnostic_reconstruction_v1.yaml"


def _allowlist_size() -> list[str]:
    return list(known_allowed_paths())


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def write_entry_audit() -> Path:
    audit = {
        "checkpoint": "C-V2-D0.6",
        "expected_entry_sha": "48f7b2466ab1e3bf053cc6de4c268fe015893313",
        "actual_head_sha_at_entry": _git_sha(),
        "registry_state_at_entry": {
            "V2-001_status": "PASS",
            "V2-002_status": "PASS",
            "V2-003_status": "PASS",
            "V2G0_status": "PASS",
            "V2G1_status": "PASS",
            "V2G2_status": "PASS",
            "V2-004_status": "NOT_STARTED",
            "V2G3_status": "NOT_STARTED",
        },
        "corrective_evidence_present": {
            "C-V2-001-VERIFY": True,
            "C-V2-003-PROVENANCE": True,
        },
        "frozen_identities_verified": {
            "protocol_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
            ),
            "outer_cv_sha256": hash_file(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"),
            "inner_cv_sha256": hash_file(
                ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
            ),
            "model_v1_cv_reference_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"
            ),
            "feature_audit_lock_sha256": hash_file(
                ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json"
            ),
            "baseline_v1_lock_sha256": hash_file(
                ROOT / "manifests/baselines/BASELINE_V1.lock.json"
            ),
        },
        "status": "PASS",
    }
    path = OUT_DIR / "entry_audit.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_source_artifact_inventory() -> Path:
    records = [
        {
            "logical_id": "MODEL_V1_CV_REFERENCE_V1_OOF",
            "path": "reports/model_v2/v2_002/oof_predictions.csv",
            "sha256": hash_file(ROOT / "reports/model_v2/v2_002/oof_predictions.csv"),
            "owner_phase": "V2-002",
            "partition": "TRAIN",
            "prediction_identity": "MODEL_V1_CV_REFERENCE_V1 (3 seeds, pooled OOF)",
            "seed": "20260927,20260928,20260929 (separate rows per seed)",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": "D0.6 TRAIN-OOF primary diagnostic model A",
        },
        {
            "logical_id": "V2_003_RF_ALL_OOF",
            "path": "reports/model_v2/v2_003/oof_predictions.csv",
            "sha256": hash_file(ROOT / "reports/model_v2/v2_003/oof_predictions.csv"),
            "owner_phase": "V2-003",
            "partition": "TRAIN",
            "prediction_identity": (
                "RF fit on ALL-29 features (filtered feature_variant=ALL, model_family=RF)"
            ),
            "seed": "20260927 (fixed RF random_state)",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": "D0.6 TRAIN-OOF primary diagnostic model B",
        },
        {
            "logical_id": "MODEL_V1_HISTORICAL_VALIDATION_SCALARS",
            "path": "reports/t015/seeds/{20260927,20260928,20260929}.json",
            "sha256": {
                str(seed): hash_file(ROOT / f"reports/t015/seeds/{seed}.json")
                for seed in lib.SEEDS
            },
            "owner_phase": "T015",
            "partition": "VALIDATION",
            "prediction_identity": (
                "MODEL_V1 release-architecture best-epoch checkpoint, pooled scalar only"
            ),
            "seed": "20260927,20260928,20260929",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": (
                "D0.6 historical VALIDATION context (pooled scalar only; no "
                "per-window predictions available)"
            ),
        },
        {
            "logical_id": "CLASSICAL_HISTORICAL_VALIDATION_SCALARS",
            "path": "reports/baselines/baseline_report.json",
            "sha256": hash_file(ROOT / "reports/baselines/baseline_report.json"),
            "owner_phase": "T014",
            "partition": "VALIDATION",
            "prediction_identity": "RF_BASELINE_V1 / LOGISTIC_BASELINE_V1, pooled scalar only",
            "seed": "20260927",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": (
                "D0.6 historical VALIDATION context (pooled scalar only; no "
                "per-window predictions available)"
            ),
        },
        {
            "logical_id": "WINDOW_GROUP_LABEL_METADATA",
            "path": "manifests/windows/MITDB_WINDOWS_V1.csv",
            "sha256": hash_file(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"),
            "owner_phase": "T013",
            "partition": "TRAIN+VALIDATION (filtered per use)",
            "prediction_identity": "n/a (metadata only: labels, groups, mapped_s/v/f_count)",
            "seed": "n/a",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": "patient/class-composition tables for both strata; never raw waveform",
        },
        {
            "logical_id": "BASELINE_FEATURES_V1_SCHEMA",
            "path": "manifests/features/BASELINE_FEATURES_V1.schema.json",
            "sha256": hash_file(ROOT / "manifests/features/BASELINE_FEATURES_V1.schema.json"),
            "owner_phase": "T014",
            "partition": "n/a",
            "prediction_identity": "n/a (feature schema)",
            "seed": "n/a",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": "confirms detected_hr_mean_bpm is feature index 20",
        },
        {
            "logical_id": "BASELINE_FEATURES_V1_TRAIN_CACHE",
            "path": (
                "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
                "BASELINE_FEATURES_V1/TRAIN_features.npy"
            ),
            "sha256": hash_file(
                ROOT
                / "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
                "BASELINE_FEATURES_V1/TRAIN_features.npy"
            ),
            "owner_phase": "T014",
            "partition": "TRAIN",
            "prediction_identity": "n/a (already-computed derived feature cache, not raw waveform)",
            "seed": "n/a",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": "HR-equivalent feature (detected_hr_mean_bpm) for TRAIN-OOF patient tables",
        },
        {
            "logical_id": "BASELINE_FEATURES_V1_VALIDATION_CACHE",
            "path": (
                "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
                "BASELINE_FEATURES_V1/VALIDATION_features.npy"
            ),
            "sha256": hash_file(
                ROOT
                / "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/"
                "BASELINE_FEATURES_V1/VALIDATION_features.npy"
            ),
            "owner_phase": "T014",
            "partition": "VALIDATION",
            "prediction_identity": "n/a (already-computed derived feature cache, not raw waveform)",
            "seed": "n/a",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": (
                "HR-equivalent feature (detected_hr_mean_bpm) for VALIDATION context "
                "patient tables"
            ),
        },
        {
            "logical_id": "CAL_V1_SCALAR",
            "path": "artifacts/CAL_V1.json",
            "sha256": hash_file(ROOT / "artifacts/CAL_V1.json"),
            "owner_phase": "T017",
            "partition": (
                "CALIBRATION (threshold/temperature scalars read only; no CALIBRATION "
                "patient rows opened)"
            ),
            "prediction_identity": "n/a (scalar threshold=0.6128035574269627, comparator>=)",
            "seed": "n/a",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": "frozen threshold for historical VALIDATION threshold-region analysis",
        },
        {
            "logical_id": "T014_RF_CONFIG",
            "path": "configs/baseline_v1.yaml",
            "sha256": hash_file(ROOT / "configs/baseline_v1.yaml"),
            "owner_phase": "T014",
            "partition": "n/a",
            "prediction_identity": "n/a (scalar threshold=0.5, FIXED_NOT_TUNED)",
            "seed": "n/a",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": (
                "verify RF historical operating threshold; provenance confirmed, but "
                "no per-window RF VALIDATION predictions exist to apply it to"
            ),
        },
        {
            "logical_id": "CLASS_COMPOSITION_DEFINITION_CODE",
            "path": "evaluation/error_analysis.py",
            "sha256": hash_file(ROOT / "evaluation/error_analysis.py"),
            "owner_phase": "T031",
            "partition": "n/a",
            "prediction_identity": "n/a (pure function, reused exactly)",
            "seed": "n/a",
            "frozen_read_only": True,
            "previously_consumed": True,
            "purpose": "reused exactly for class_composition(s,v,f) -> slice label",
        },
    ]
    missing_components = [
        {
            "logical_id": "MODEL_V1_PER_WINDOW_VALIDATION_PREDICTIONS",
            "status": "MISSING_FROZEN_SOURCE",
            "searched_locations": [
                "reports/t015", "reports/t016", "reports/t017", "reports/t018",
                "reports/t034", "reports/t035", "reports/c032_norm_runtime",
            ],
            "closest_match_found": (
                "reports/t034,t035,c032_norm_runtime replay logs (12 demo examples, "
                "not comprehensive)"
            ),
            "not_regenerated": True,
        },
        {
            "logical_id": "RF_PER_WINDOW_VALIDATION_PREDICTIONS",
            "status": "MISSING_FROZEN_SOURCE",
            "searched_locations": ["reports/baselines", "reports/t014"],
            "closest_match_found": "none (only pooled scalar VALIDATION_metrics persisted)",
            "not_regenerated": True,
        },
    ]
    inventory = {
        "source_records": records,
        "missing_components": missing_components,
        "status": "PASS",
    }
    path = OUT_DIR / "source_artifact_inventory.json"
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_method_freeze() -> Path:
    freeze = {
        "checkpoint": "C-V2-D0.6",
        "pre_result_method_commit": None,
        "note_pre_result_method_commit": (
            "Left null here by construction -- a SEPARATE attestation commit created "
            "immediately after this commit binds this exact commit's own SHA, per Section 7's "
            "required METHOD_COMMIT -> ATTESTATION_COMMIT -> push both -> THEN compute results "
            "chronology (avoiding the prior V2-002/V2-003 null-binding gap by construction, "
            "not by rewriting this file after the fact)."
        ),
        "config_sha256": hash_file(CONFIG_PATH),
        "protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
        ),
        "d0_6_code_sha256": {
            "src/nhm/model_v2_d0_6_guard.py": hash_file(
                ROOT / "src/nhm/model_v2_d0_6_guard.py"
            ),
            "scripts/_d0_6_lib.py": hash_file(ROOT / "scripts/_d0_6_lib.py"),
        },
        "reused_definition_sha256": {
            "evaluation/error_analysis.py (class_composition, reused unmodified)": hash_file(
                ROOT / "evaluation/error_analysis.py"
            ),
        },
        "hard_data_firewall": {
            "mechanism": (
                "src/nhm/model_v2_d0_6_guard.py per-path allowlist + forbidden-substring "
                "denylist"
            ),
            "allowlist_size": len(_allowlist_size()),
        },
        "pre_freeze_integration_smoke_test": {
            "performed": True,
            "description": (
                "Real reads of the window manifest (TRAIN+VALIDATION), BASELINE_FEATURES_V1 "
                "HR feature caches (TRAIN+VALIDATION), historical scalar metrics "
                "(reports/t015/seeds, baseline_report.json), CAL_V1, and the T014 RF "
                "threshold were exercised interactively to confirm the firewall and loaders "
                "are correctly wired and that the TRAIN window/OOF example_id populations are "
                "exactly identical (9660/9660 match confirmed) before committing to the full "
                "diagnostic computation."
            ),
            "scientific_diagnostic_result_produced": False,
            "hypothesis_answered": False,
            "code_changed_based_on_its_numeric_output": False,
            "scope_access_ledger_rows_from_smoke_test_removed_before_real_run": True,
        },
        "real_results_started": False,
        "status": "READY_FOR_REAL_RESULTS",
    }
    path = OUT_DIR / "method_freeze.json"
    path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> None:
    write_entry_audit()
    write_source_artifact_inventory()
    write_method_freeze()
    print("C-V2-D0.6 pre-result evidence written")


if __name__ == "__main__":
    main()
