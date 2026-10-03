#!/usr/bin/env python3
"""V2-008 Sections 1-11 preflight: entry/upstream/continuity/promotion/source-checkpoint
verification and the freeze-ID decision, all performed BEFORE any canonical MODEL_V2_FINAL
artifact is created. Pure read-only checks -- no waveform/patient data access, no neural fit,
no official VALIDATION access.
"""

from __future__ import annotations

import csv
import json
import subprocess

from nhm.hashing import hash_file

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_008"

EXPECTED_ENTRY_SHA_PREFIX = "1c23214"
EXPECTED_RELEASE_SHA = "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b"


def _sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False).stdout


def write_json(name: str, data: dict) -> None:
    (OUT_DIR / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _registry() -> tuple[dict, dict]:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {r["task_id"]: r["status"] for r in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {r["gate_id"]: r["status"] for r in csv.DictReader(handle)}
    return tasks, gates


def entry_audit() -> dict:
    head = _sh("git", "rev-parse", "HEAD").strip()
    origin_main = _sh("git", "rev-parse", "origin/main").strip()
    tasks, gates = _registry()
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        components = {r["component_id"]: r["status"] for r in csv.DictReader(handle)}
    data = {
        "head": head,
        "origin_main": origin_main,
        "head_equals_origin_main": head == origin_main,
        "head_matches_expected_prefix": head.startswith(EXPECTED_ENTRY_SHA_PREFIX),
        "registry": {
            k: tasks.get(k) for k in [
                "V2-001", "V2-002", "V2-003", "V2-004", "V2-005", "V2-006", "V2-007",
                "V2-008", "V2-009",
            ]
        } | {
            k: gates.get(k) for k in [
                "V2G0", "V2G1", "V2G2", "V2G3", "V2G4", "V2G5", "V2G6", "V2G7", "V2G8",
            ]
        },
        "model_v2_final_absent": components.get("MODEL_V2_FINAL") == "NOT_STARTED",
        "cal_v2_absent": components.get("CAL_V2") == "NOT_STARTED",
        "status": "PASS" if (
            head == origin_main
            and tasks.get("V2-007") == "PASS" and gates.get("V2G6") == "PASS"
            and tasks.get("V2-008") == "NOT_STARTED" and gates.get("V2G7") == "NOT_STARTED"
            and components.get("MODEL_V2_FINAL") == "NOT_STARTED"
            and components.get("CAL_V2") == "NOT_STARTED"
        ) else "FAIL",
    }
    write_json("entry_audit.json", data)
    return data


def upstream_identity_audit() -> dict:
    hashes = {
        "protocol_v1_lock": (
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json",
            "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7",
        ),
        "protocol_v2_lock": (
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json",
            "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81",
        ),
        "protocol_v3_lock": (
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
            "287aff4ff3fcf583524f06e6af51f23bd65949a75abef14cde80ff0936873db8",
        ),
    }
    checks = {}
    for name, (rel, expected) in hashes.items():
        observed = hash_file(ROOT / rel)
        checks[name] = {"path": rel, "expected": expected, "observed": observed,
                         "match": observed == expected}
    data = {
        "checks": checks,
        "status": "PASS" if all(c["match"] for c in checks.values()) else "FAIL",
    }
    write_json("upstream_identity_audit.json", data)
    return data


def v2_007_continuity_audit() -> dict:
    immutability = json.loads(
        (ROOT / "reports/model_v2/v2_007/training_method_immutability_diff.json").read_text(
            encoding="utf-8"
        )
    )
    diagnostic = json.loads(
        (ROOT / "reports/model_v2/v2_007/source_train_diagnostic_audit.json").read_text(
            encoding="utf-8"
        )
    )
    chronology = json.loads(
        (ROOT / "reports/model_v2/v2_007/orchestration_code_chronology_disclosure.json").read_text(
            encoding="utf-8"
        )
    )
    chunked = json.loads(
        (ROOT / "reports/model_v2/v2_007/chunked_regression_proof_core.json").read_text(
            encoding="utf-8"
        )
    )
    continuity_commit_exists = subprocess.run(
        ["git", "cat-file", "-e", "1c23214f76331fd4cc50b3318e133a164f4c7b58"],
        cwd=ROOT, capture_output=True, check=False,
    ).returncode == 0
    data = {
        "continuity_audit_commit": "1c23214f76331fd4cc50b3318e133a164f4c7b58",
        "continuity_commit_exists": continuity_commit_exists,
        "training_method_immutability": immutability["status"],
        "source_train_diagnostic_27_groups_9660_windows": diagnostic[
            "all_six_cover_27_groups_9660_windows"
        ],
        "orchestration_chronology_classification": chronology["classification"],
        "orchestration_rerun_warranted": chronology["rerun_warranted"],
        "orchestration_rerun_performed": chronology["rerun_performed"],
        "official_validation_reaccessed_during_continuity_audit": False,
        "new_fits_during_continuity_audit": 0,
        "chunked_collected": chunked["collected_node_count"],
        "chunked_executed_unique": chunked["executed_unique_count"],
        "chunked_chunk_count": chunked["chunk_count"],
        "chunked_missing": chunked["missing"],
        "chunked_duplicates": chunked["duplicates"],
        "chunked_unexpected": chunked["unexpected"],
        "chunked_failed_tests": chunked["failed_tests"],
        "chunked_failed_chunks": chunked["failed_chunks"],
        "status": "PASS" if (
            continuity_commit_exists
            and immutability["status"] == "PASS"
            and diagnostic["all_six_cover_27_groups_9660_windows"]
            and chronology["rerun_performed"] is False
            and chunked["status"] == "PASS"
            and chunked["collected_node_count"] == 1680
            and chunked["executed_unique_count"] == 1680
            and chunked["chunk_count"] == 21
            and chunked["missing"] == 0 and chunked["duplicates"] == 0
            and chunked["unexpected"] == 0 and chunked["failed_tests"] == 0
            and chunked["failed_chunks"] == 0
        ) else "FAIL",
    }
    write_json("v2_007_continuity_audit.json", data)
    return data


def promotion_disposition() -> dict:
    promotion = json.loads(
        (ROOT / "reports/model_v2/v2_007/promotion_decision.json").read_text(encoding="utf-8")
    )
    data = {
        "decision": promotion["decision"],
        "promotion_eligible": promotion["promotion_eligible"],
        "criterion_a": promotion["criterion_a_mean_auprc_gt_0_646"],
        "criterion_b1": promotion["criterion_b1_release_delta_lower_ci_gt_0"],
        "criterion_b2": promotion["criterion_b2_three_seed_mean_delta_lower_ci_gt_0"],
        "release_point_delta": promotion["release_point_delta_vs_v1"],
        "release_ci": promotion["release_ci"],
        "three_seed_point_delta": promotion["three_seed_point_delta_vs_v1"],
        "three_seed_ci": promotion["three_seed_ci"],
        "selected_architecture_id": promotion["selected_architecture_id"],
        "selected_schedule_id": promotion["selected_schedule_id"],
        "release_seed": promotion["release_seed"],
        "scientific_model_id": "MODEL_V2_FINAL",
        "scientific_final_frozen": True,
        "official_validation_promotion_eligible": False,
        "official_validation_promotion_decision": promotion["decision"],
        "operational_lineage": "MODEL_V1",
        "runtime_acceptance_status": "NOT_EVALUATED",
        "deployment_authorized": False,
        "status": "PASS" if (
            promotion["decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
            and promotion["criterion_a_mean_auprc_gt_0_646"] is True
            and promotion["criterion_b1_release_delta_lower_ci_gt_0"] is False
            and promotion["criterion_b2_three_seed_mean_delta_lower_ci_gt_0"] is True
            and promotion["promotion_eligible"] is False
            and promotion["selected_architecture_id"] == "MODEL_V2_TCN_MEAN"
            and promotion["release_seed"] == 20260927
        ) else "FAIL",
    }
    write_json("promotion_disposition.json", data)
    return data


def source_checkpoint_identity() -> dict:
    rows = json.loads(
        (ROOT / "reports/model_v2/v2_007/validation_ready_checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    row = next(
        r for r in rows if r["architecture_id"] == "MODEL_V2_TCN_MEAN" and r["seed"] == 20260927
    )
    path = ROOT / row["checkpoint_path"]
    exists = path.exists()
    observed_sha = hash_file(path) if exists else None
    data = {
        "architecture_id": row["architecture_id"],
        "schedule_id": row["schedule_id"],
        "seed": row["seed"],
        "selected_epoch": row["selected_epoch"],
        "checkpoint_path": row["checkpoint_path"],
        "expected_sha256": EXPECTED_RELEASE_SHA,
        "manifest_sha256": row["checkpoint_sha256"],
        "bytes_available": exists,
        "observed_sha256": observed_sha,
        "match": observed_sha == EXPECTED_RELEASE_SHA,
        "best_scoring_seed_not_substituted": row["seed"] == 20260927,
        "status": "PASS" if (
            exists and observed_sha == EXPECTED_RELEASE_SHA
            and row["checkpoint_sha256"] == EXPECTED_RELEASE_SHA
            and row["selected_epoch"] == 5
            and row["architecture_id"] == "MODEL_V2_TCN_MEAN"
            and row["schedule_id"] == "CONFIG_V2_TCN_MEAN_ORIGINAL_V1"
            and row["seed"] == 20260927
        ) else "BLOCKED_RELEASE_CHECKPOINT_BYTES_UNAVAILABLE",
    }
    write_json("source_checkpoint_identity.json", data)
    return data


def freeze_id_selection() -> dict:
    with (ROOT / "manifests/freeze_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    used_ids = {r["freeze_id"] for r in rows}
    f15_row = next(r for r in rows if r["freeze_id"] == "F15")
    data = {
        "canonical_registry_path": "manifests/freeze_registry_v1.csv",
        "canonical_registry_row_count": len(rows),
        "f15_occupied": "F15" in used_ids,
        "f15_purpose": f15_row["artifact_or_decision"],
        "f15_current_status": f15_row["current_status"],
        "decision": "NO_CANONICAL_FREEZE_ID_ASSIGNED",
        "reasoning": (
            "F15 is already legitimately occupied by the canonical, unrelated "
            "'release package / RELEASE_V1' row bound to gate G22 of the original "
            "T002-T036 project -- not available for MODEL_V2_FINAL. The canonical freeze "
            "registry is additionally locked at exactly 15 rows by an existing test "
            "(tests/test_freeze_registry.py::"
            "test_freeze_registry_covers_required_decisions_without_premature_freezes, "
            "'assert len(rows) == 15'); appending F16 there would both misuse an "
            "unrelated-purpose ID slot and break that passing test. Every prior MODEL_V2 "
            "component (MODEL_V2_ARCH_CAUSALITY_V1, MODEL_V2_OPTIMIZER_CORRECTION_V1, "
            "MODEL_V2_FINALIST_SHORTLIST_V1, MODEL_V2_OFFICIAL_VALIDATION_V1, "
            "MODEL_V2_VALIDATION_DECISION_V1, MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1) was "
            "registered the same way: as an additive manifests/model_v2/component_registry_"
            "v1.csv row explicitly marked not_a_canonical_freeze_row=true, never as a "
            "canonical Fxx row. MODEL_V2_FINAL follows that same, consistent, already-"
            "established convention rather than corrupting the canonical registry for a "
            "non-operational scientific research artifact."
        ),
        "selection_method": "ADDITIVE_MODEL_V2_COMPONENT_REGISTRY_ENTRY",
        "predecessor_freeze_state": "none (first MODEL_V2_FINAL freeze)",
        "canonical_registry_modified": False,
        "canonical_registry_row_count_after": len(rows),
        "status": "PASS",
    }
    write_json("freeze_id_selection.json", data)
    return data


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entry = entry_audit()
    upstream = upstream_identity_audit()
    continuity = v2_007_continuity_audit()
    promotion = promotion_disposition()
    source = source_checkpoint_identity()
    freeze_id = freeze_id_selection()
    print(json.dumps({
        "entry": entry["status"], "upstream": upstream["status"],
        "continuity": continuity["status"], "promotion": promotion["status"],
        "source": source["status"], "freeze_id": freeze_id["status"],
    }, indent=2))
    if any(
        r["status"] != "PASS" for r in [entry, upstream, continuity, promotion, freeze_id]
    ):
        raise RuntimeError("V2-008 preflight FAILED")
    if source["status"] != "PASS":
        print("V2-008 = BLOCKED_RELEASE_CHECKPOINT_BYTES_UNAVAILABLE")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
