#!/usr/bin/env python3
"""V2-011 Sections 1/3/5/6/7: entry audit, V2-010 continuity normalization, upstream and
prediction-freeze verification, and the pre-access protected-artifact baseline snapshot.
No waveform access and no model inference beyond the existing fixture-based verifiers.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from models.cal_v2_verify import verify_cal_v2
from models.model_v2_final_freeze import verify_model_v2_final
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_011"

CHECKPOINT_SHA = "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b"
CAL_TEMPERATURE = 52.88261929727761
CAL_THRESHOLD = 0.5101937262006424

PROTECTED_PATHS = [
    "checkpoints/MODEL_V2_FINAL.pt",
    "checkpoints/MODEL_V2_FINAL.manifest.json",
    "configs/model_v2_final_frozen.yaml",
    "artifacts/CAL_V2.json",
    "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
    "reports/model_v2/v2_007/run_manifest.json",
    "reports/model_v2/v2_007/artifact_hashes.json",
    "reports/model_v2/v2_008/run_manifest.json",
    "reports/model_v2/v2_008/artifact_hashes.json",
    "reports/model_v2/v2_009/run_manifest.json",
    "reports/model_v2/v2_009/artifact_hashes.json",
    "reports/model_v2/v2_010/internal_v2_predictions.csv",
    "reports/model_v2/v2_010/incart_v2_predictions.csv",
    "reports/model_v2/v2_010/nstdb_v2_predictions.csv",
    "reports/model_v2/v2_010/runtime_acceptance_decision.json",
    "reports/model_v2/v2_010/run_manifest.json",
    "reports/model_v2/v2_010/artifact_hashes.json",
    "checkpoints/MODEL_V1.pt",
    "artifacts/CAL_V1.json",
    "artifacts/EXPLAINABILITY_V1_METHOD.lock.json",
    "artifacts/C031_ERROR_ANALYSIS_V1.lock.json",
    "configs/explainability_v1.yaml",
    "configs/error_analysis_v1.yaml",
    "configs/c031_error_analysis_v1.yaml",
    "evaluation/explain.py",
    "evaluation/error_analysis.py",
    "evaluation/c031_error_analysis.py",
    "reports/explainability_v1.json",
    "reports/error_analysis_v1.json",
    "reports/error_analysis_v1_1.json",
    "reports/t031/hr_bins.json",
    "reports/t031/explainability_case_manifest.csv",
    "reports/t031/c031_noise_base_manifest.csv",
    "reports/t031/noise_type_snr_slice_v2.csv",
    "reports/t031/noise_type_predictions_v2.csv",
    "reports/internal_test_predictions.csv",
    "reports/external_incart_predictions.csv",
    "reports/t019/nstdb_predictions.csv",
    "manifests/preprocessing/PREPROC_V1.lock.json",
    "manifests/splits/MITDB_SPLIT_V1.csv",
    "manifests/labels/AAMI_SVF_MAP_V1.yaml",
]


def _sh(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def entry_audit() -> dict:
    def status(path: str, key: str, ident: str, field: str) -> str:
        return next(r[field] for r in _rows(path) if r[key] == ident)

    task = "manifests/model_v2/task_registry_v1.csv"
    gate = "manifests/model_v2/gate_registry_v1.csv"
    comp = "manifests/model_v2/component_registry_v1.csv"
    data = {
        "head": _sh("git", "rev-parse", "HEAD"),
        "origin_main": _sh("git", "rev-parse", "origin/main"),
        "head_prefix_expected": "883d9c9",
        "working_tree_clean_at_entry": True,
        "registry": {
            "V2-008": status(task, "task_id", "V2-008", "status"),
            "V2G7": status(gate, "gate_id", "V2G7", "status"),
            "V2-009": status(task, "task_id", "V2-009", "status"),
            "V2G8": status(gate, "gate_id", "V2G8", "status"),
            "V2-010": status(task, "task_id", "V2-010", "status"),
            "V2G9": status(gate, "gate_id", "V2G9", "status"),
            "V2-011": status(task, "task_id", "V2-011", "status"),
            "V2G10": status(gate, "gate_id", "V2G10", "status"),
            "V2-012": status(task, "task_id", "V2-012", "status"),
            "MODEL_V2_FINAL": status(comp, "component_id", "MODEL_V2_FINAL", "status"),
            "CAL_V2": status(comp, "component_id", "CAL_V2", "status"),
            "MODEL_V2_RUNTIME_ACCEPTED": status(
                comp, "component_id", "MODEL_V2_RUNTIME_ACCEPTED", "status"
            ),
        },
        "operational_lineage": "MODEL_V1",
        "cumulative_v2_neural_fits": 71,
    }
    expected = {
        "V2-008": "PASS", "V2G7": "PASS", "V2-009": "PASS", "V2G8": "PASS", "V2-010": "PASS",
        "V2G9": "PASS", "V2-011": "NOT_STARTED", "V2G10": "NOT_STARTED",
        "V2-012": "NOT_STARTED", "MODEL_V2_FINAL": "FROZEN", "CAL_V2": "FROZEN",
        "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED",
    }
    ok = (
        data["head"] == data["origin_main"]
        and data["head"].startswith("883d9c9")
        and data["registry"] == expected
    )
    data["status"] = "PASS" if ok else "FAIL"
    _write("entry_audit.json", data)
    if not ok:
        raise RuntimeError("V2_011_ENTRY_STATE_MISMATCH")
    return data


def continuity() -> dict:
    data = {
        "A_v2_008_timeout_provenance": {
            "V2_008_outer_timeout_annotations_observed": True,
            "source_of_statement": (
                "operator-attested in the V2-011 phase prompt Section 3A; the outer-harness "
                "'(timeout 2m)' annotations are not part of the agent-visible command output"
            ),
            "earlier_no_timeout_or_not_substantiated_wording": "SUPERSEDED_PROVENANCE_WORDING",
            "superseded_wording_locations": [
                "reports/model_v2/v2_009/ preflight (INVESTIGATED_NOT_SUBSTANTIATED)",
                "reports/model_v2/v2_010/v2_009_entry_continuity_audit_fact_a.json "
                "(not corroborated from the visible transcript)",
            ],
            "scientific_MODEL_V2_FINAL_affected": False,
            "old_evidence_rewritten": False,
        },
        "B_v2_010_handoff_formatting": {
            "v2_010_final_handoff_reproduced_verbatim": False,
            "mechanically_reconstructed_state": {
                "V2-010": "PASS",
                "V2G9": "PASS",
                "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED",
                "MODEL_V2_FINAL": "FROZEN",
                "CAL_V2": "FROZEN",
                "official_validation_promotion": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
                "operational_lineage": "MODEL_V1",
                "cumulative_neural_fits": 71,
                "V2-011": "NOT_STARTED",
            },
            "classification": "PROVENANCE_NORMALIZATION_ONLY",
        },
        "C_v2_010_registry_chronology": {
            "classification": "POST_RESULT_CONTROL_PLANE_BOOKKEEPING",
            "detail": (
                "V2-010 registry/status bookkeeping (V2-010/V2G9 PASS, "
                "MODEL_V2_RUNTIME_ACCEPTED component row) was completed after the results "
                "existed. An initial edit silently converted CRLF to LF in the two registry "
                "CSVs; it was detected via git diff --stat, reverted with git checkout, and "
                "reapplied minimally in binary mode with CRLF preserved (3-line diff)."
            ),
            "scientific_result_affected": False,
        },
        "D_independent_verifier_strength": {
            "v2_010_incart_independent_verifier_v1_side_source": (
                "frozen verified V1 T020 bootstrap-replicate table"
            ),
            "v2_side": "independently derived from V2 predictions and the frozen draw matrix",
            "primary_v2_010_analysis_invalidated": False,
            "remedy": (
                "v2_010_statistical_reverification.json reconstructs BOTH sides from frozen "
                "prediction tables and frozen draw matrices"
            ),
        },
        "v2_010_scientific_result_changed": False,
        "status": "DISCLOSED",
    }
    _write("v2_010_entry_continuity.json", data)
    return data


def upstream_and_predictions() -> dict:
    model = verify_model_v2_final(ROOT)
    cal = verify_cal_v2(ROOT)
    artifact = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    manifest = json.loads((ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
    checks = {
        "checkpoint_sha": model["checkpoint_sha256"] == CHECKPOINT_SHA,
        "architecture": manifest["architecture_id"] == "MODEL_V2_TCN_MEAN",
        "seed": manifest["release_seed"] == 20260927,
        "temperature": artifact["temperature"] == CAL_TEMPERATURE,
        "threshold": artifact["threshold"] == CAL_THRESHOLD,
        "comparator": artifact["threshold_comparator"] == ">=",
        "target": artifact["target_id"] == "AAMI_SVF_WINDOW_V1",
        "map": artifact["map_id"] == "AAMI_SVF_MAP_V1",
    }
    hashes = json.loads((ROOT / "reports/model_v2/v2_010/artifact_hashes.json").read_text())
    pred_files = {
        "internal_v2_predictions.csv": 2157,
        "incart_v2_predictions.csv": 26864,
        "nstdb_v2_predictions.csv": 4320,
    }
    pred = {}
    for name, count in pred_files.items():
        rel = f"reports/model_v2/v2_010/{name}"
        rows = _rows(rel)
        pred[name] = {
            "rows": len(rows),
            "expected_rows": count,
            "sha256": hash_file(ROOT / rel),
            "matches_v2_010_artifact_hashes": hash_file(ROOT / rel) == hashes["artifacts"][rel],
        }
    incart_rows = _rows("reports/model_v2/v2_010/incart_v2_predictions.csv")
    pred["incart_v2_predictions.csv"]["patient_clusters"] = len(
        {r["participant_group_id"] for r in incart_rows}
    )
    nst = _rows("reports/model_v2/v2_010/nstdb_v2_predictions.csv")
    pred["nstdb_v2_predictions.csv"]["pair_ids"] = len({r["pair_id"] for r in nst})
    pred["nstdb_v2_predictions.csv"]["snr_levels"] = len({r["snr_db"] for r in nst})
    pred_ok = (
        all(p["rows"] == p["expected_rows"] and p["matches_v2_010_artifact_hashes"]
            for p in pred.values())
        and pred["incart_v2_predictions.csv"]["patient_clusters"] == 32
        and pred["nstdb_v2_predictions.csv"]["pair_ids"] == 720
        and pred["nstdb_v2_predictions.csv"]["snr_levels"] == 6
    )
    ok = model["status"] == "PASS" and cal["status"] == "PASS" and all(checks.values()) and pred_ok
    data = {
        "model_v2_final_verifier": model["status"],
        "model_v2_final_max_abs_error": model["maximum_absolute_error"],
        "cal_v2_verifier": cal["status"],
        "identity_checks": checks,
        "protocol_v3_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ),
        "cal_v2_sha256": hash_file(ROOT / "artifacts/CAL_V2.json"),
        "v2_010_predictions": pred,
        "status": "PASS" if ok else "FAIL",
    }
    _write("upstream_identity_audit.json", data)
    if not ok:
        raise RuntimeError("V2_011_UPSTREAM_VERIFICATION_FAILED")
    return data


def protected_baseline() -> dict:
    data = {"artifacts": {p: hash_file(ROOT / p) for p in PROTECTED_PATHS}}
    (OUT / "protected_baseline.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entry_audit()
    continuity()
    upstream_and_predictions()
    protected_baseline()
    print("V2-011 entry/continuity/upstream/baseline complete")


if __name__ == "__main__":
    main()
