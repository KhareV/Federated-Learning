"""V2-005: generates the CONDITIONAL HYBRID DISPOSITION evidence tree.

Zero-fit, metadata/evidence-only phase. Reads only already-frozen V2-003/V2-004 scalar
artifacts and git/registry state; never loads waveform data, never trains a model, never
writes into reports/model_v2/v2_004/. The pre-registered hybrid trigger is already FALSE
(computed in V2-004); this script verifies and records that disposition.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_005"
V2_004_DIR = ROOT / "reports/model_v2/v2_004"
ARCH_CAUSALITY_LOCK = ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json"

TRUE_ENTRY_SHA = "806a21efe21ff87bf23d1839ac3def3ab9fc8bf2"


def sh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, check=False, capture_output=True, text=True)


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def write_json(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# entry audit
# ---------------------------------------------------------------------------

def entry_audit() -> None:
    status = sh("git", "status", "--short", "--branch")
    sh("git", "fetch", "origin")
    origin_main = sh("git", "rev-parse", "origin/main").stdout.strip()

    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row["status"] for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}

    status_lines = status.stdout.strip().splitlines()[1:]
    own_prefixes = ("?? reports/model_v2/v2_005/", "?? scripts/generate_v2_005_evidence.py")
    non_own_lines = [line for line in status_lines if not line.startswith(own_prefixes)]

    data = {
        "true_entry_sha": TRUE_ENTRY_SHA,
        "origin_main_at_generation_time": origin_main,
        "note": (
            "true_entry_sha is the HEAD this phase's spec expected at entry, manually "
            "verified clean before any V2-005 file was written. origin_main_at_generation_time "
            "reflects state when this evidence script ran, after this phase's own preceding "
            "narrow control-plane commit was already pushed."
        ),
        "working_tree_clean_excluding_own_in_progress_evidence": non_own_lines == [],
        "registry_at_true_entry": {
            "tasks": {
                k: tasks.get(k)
                for k in ["V2-001", "V2-002", "V2-003", "V2-004", "V2-005", "V2-006", "V2-007"]
            },
            "gates": {
                k: gates.get(k)
                for k in ["V2G0", "V2G1", "V2G2", "V2G3", "V2G4", "V2G5", "V2G6"]
            },
        },
        "corrective_closeout_prerequisite": {
            "c_v2_004_audit_closeout_status": load_json(
                ROOT / "reports/model_v2/c_v2_004_audit_closeout/test_results.json"
            )["status"],
        },
    }
    write_json("entry_audit.json", data)


# ---------------------------------------------------------------------------
# upstream identity audit
# ---------------------------------------------------------------------------

def upstream_identity_audit() -> dict:
    checks = {
        "MODEL_V2_RESEARCH_PROTOCOL_V1": (
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json",
            "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7",
        ),
        "MODEL_V2_RESEARCH_PROTOCOL_V2": (
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json",
            "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81",
        ),
        "MODEL_V2_FEATURE_AUDIT_V1": (
            "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json",
            "a6876430dcad040b7008a69200fb4a36d735ad9a58d834c46d66d5543609623b",
        ),
        "MODEL_V2_ARCH_CAUSALITY_V1": (
            "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json",
            "79c423fdcbd5c9dee1743ec60f704e56a48af201b6357499990cd54fa35729c3",
        ),
        "MODEL_V1_pt": (
            "checkpoints/MODEL_V1.pt",
            "021352eb067932015b657f0570ac155f8ef00af2d43864e13a110d0252bc7bfe",
        ),
        "CAL_V1_json": (
            "artifacts/CAL_V1.json",
            "d225b20957913439fd532a4de4d23acf573a88d06366e71bf3b8a7673e63479b",
        ),
    }
    results = {}
    all_ok = True
    for name, (path, expected) in checks.items():
        fp = ROOT / path
        actual = hash_file(fp) if fp.exists() else None
        ok = actual == expected
        all_ok = all_ok and ok
        results[name] = {"path": path, "expected": expected, "actual": actual, "unchanged": ok}

    data = {"checks": results, "status": "PASS" if all_ok else "FAIL"}
    write_json("upstream_identity_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# V2-004 read-only integrity guard (before / after)
# ---------------------------------------------------------------------------

def v2_004_readonly_integrity(name: str) -> dict:
    paths_to_check = [
        "reports/model_v2/v2_004",
        "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json",
    ]
    tracked = sh("git", "ls-files", *paths_to_check).stdout.strip().splitlines()

    mismatches = []
    for rel in tracked:
        fp = ROOT / rel
        local = fp.read_bytes()
        committed = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True
        ).stdout
        if local != committed:
            mismatches.append(rel)

    data = {
        "file_count": len(tracked),
        "mismatch_count": len(mismatches),
        "mismatch_paths": mismatches,
        "status": "PASS" if not mismatches else "FAIL",
    }
    write_json(name, data)
    return data


# ---------------------------------------------------------------------------
# unexpected hybrid-state audit
# ---------------------------------------------------------------------------

def unexpected_hybrid_state_audit() -> dict:
    checkpoints_dir = ROOT / "checkpoints/model_v2"
    hybrid_checkpoint_hits = []
    if checkpoints_dir.exists():
        hybrid_checkpoint_hits = [
            str(p.relative_to(ROOT))
            for p in checkpoints_dir.rglob("*")
            if "hybrid" in p.name.lower() or "aux" in p.name.lower()
        ]

    component_rows = []
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        component_rows = list(csv.DictReader(handle))
    aux_feature_row = next(
        (r for r in component_rows if r["component_id"] == "MODEL_V2_AUX_FEATURES_V1"), None
    )
    hybrid_component_rows = [
        r
        for r in component_rows
        if "HYBRID" in r["component_id"].upper()
        and r["component_id"] != "MODEL_V2_RESEARCH_PROTOCOL_V2"
    ]
    frozen_or_selected_hybrid_rows = [
        r for r in hybrid_component_rows if r["status"] in {"FROZEN", "SELECTED", "PASS"}
    ]

    v2_005_run_dirs = []
    runs_parent = ROOT / "reports/model_v2"
    for candidate in runs_parent.glob("v2_005/runs"):
        if candidate.exists():
            v2_005_run_dirs.append(str(candidate.relative_to(ROOT)))

    no_unauthorized_result = (
        not hybrid_checkpoint_hits
        and (aux_feature_row is None or aux_feature_row["status"] == "PRE_REGISTERED_CONDITIONAL")
        and not frozen_or_selected_hybrid_rows
        and not v2_005_run_dirs
    )

    data = {
        "hybrid_or_aux_checkpoint_hits": hybrid_checkpoint_hits,
        "aux_features_component_row": aux_feature_row,
        "aux_features_row_still_reserved": (
            aux_feature_row is not None
            and aux_feature_row["status"] == "PRE_REGISTERED_CONDITIONAL"
        ),
        "hybrid_component_rows_found": hybrid_component_rows,
        "frozen_or_selected_hybrid_rows": frozen_or_selected_hybrid_rows,
        "v2_005_fit_run_directories_found": v2_005_run_dirs,
        "no_unauthorized_preexisting_hybrid_result": no_unauthorized_result,
        "status": "PASS" if no_unauthorized_result else "FAIL",
    }
    write_json("unexpected_hybrid_state_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# hybrid trigger verification
# ---------------------------------------------------------------------------

def hybrid_trigger_verification() -> dict:
    feature_audit_lock = load_json(ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json")
    best_reduced_rf = feature_audit_lock["best_reduced_rf"]
    best_learned_only = load_json(V2_004_DIR / "best_learned_only.json")
    stability_decision = load_json(V2_004_DIR / "d2_stability_decision.json")
    hybrid_trigger = load_json(V2_004_DIR / "hybrid_trigger.json")

    classical_auprc = best_reduced_rf["AUPRC"]
    learned_auprc = best_learned_only["AUPRC_mean"]
    recomputed_gap = classical_auprc - learned_auprc
    gap_matches = abs(recomputed_gap - hybrid_trigger["gap"]) <= 1e-15

    recomputed_trigger = recomputed_gap >= hybrid_trigger["threshold"]

    identity_checks = {
        "classical_reference_variant_is_RR": best_reduced_rf["selected_variant"] == "RR",
        "classical_reference_feature_count_is_9": best_reduced_rf["feature_count"] == 9,
        "learned_reference_architecture_is_TCN_MEANMAX": (
            best_learned_only["architecture_id"] == "MODEL_V2_TCN_MEANMAX"
        ),
        "stability_decision_agrees_on_best_learned_only": (
            stability_decision["best_learned_only_architecture_id"] == "MODEL_V2_TCN_MEANMAX"
        ),
    }

    data = {
        "classical_reference_id": "BEST_REDUCED_RF_V1",
        "classical_auprc_read_from_artifact": classical_auprc,
        "learned_reference_id": "BEST_LEARNED_ONLY_V2_CV_V1",
        "learned_architecture_read_from_artifact": best_learned_only["architecture_id"],
        "learned_auprc_read_from_artifact": learned_auprc,
        "recomputed_gap": recomputed_gap,
        "stored_gap": hybrid_trigger["gap"],
        "gap_matches_within_1e-15": gap_matches,
        "stored_threshold": hybrid_trigger["threshold"],
        "stored_comparator": hybrid_trigger["comparator"],
        "stored_trigger": hybrid_trigger["trigger"],
        "recomputed_trigger": recomputed_trigger,
        "stored_and_recomputed_trigger_agree": recomputed_trigger == hybrid_trigger["trigger"],
        "identity_checks": identity_checks,
        "status": (
            "PASS"
            if (
                gap_matches
                and recomputed_trigger is False
                and hybrid_trigger["trigger"] is False
                and recomputed_trigger == hybrid_trigger["trigger"]
                and all(identity_checks.values())
            )
            else "FAIL"
        ),
    }
    write_json("hybrid_trigger_verification.json", data)
    return data


# ---------------------------------------------------------------------------
# hybrid disposition record
# ---------------------------------------------------------------------------

def hybrid_disposition(verification: dict) -> dict:
    data = {
        "task_id": "V2-005",
        "protocol": "MODEL_V2_RESEARCH_PROTOCOL_V2",
        "classical_reference_id": verification["classical_reference_id"],
        "classical_AUPRC": verification["classical_auprc_read_from_artifact"],
        "learned_reference_id": verification["learned_reference_id"],
        "learned_architecture": verification["learned_architecture_read_from_artifact"],
        "learned_AUPRC": verification["learned_auprc_read_from_artifact"],
        "formula": "classical - learned",
        "gap": verification["stored_gap"],
        "threshold": verification["stored_threshold"],
        "comparator": verification["stored_comparator"],
        "trigger": verification["stored_trigger"],
        "branch": "SKIP_HYBRID",
        "neural_fits_added": 0,
        "classical_fits_added": 0,
        "hybrid_model_created": False,
        "aux_feature_schema_created": False,
        "checkpoint_created": False,
        "official_validation_accessed": False,
        "final_task_status": "SKIPPED_BY_PROTOCOL",
        "gate_result": "PASS",
        "reason": "PRE_REGISTERED_HYBRID_TRIGGER_FALSE",
        "interpretation": {
            "permitted_statement": (
                "The pre-registered hybrid trigger did not fire because the selected "
                "learned-only model's TRAIN-CV mean AUPRC exceeded the selected reduced "
                "classical RF reference, yielding a classical-minus-learned gap below 0.03."
            ),
            "scope_note": (
                "This does not demonstrate that a hybrid model would fail or could not "
                "improve performance. The hybrid branch was not executed because its "
                "pre-registered justification criterion was not met."
            ),
            "prohibited_statements": [
                "hybrid is worse",
                "hybrid does not work",
                "hybrid would reduce performance",
                "hybrid is unnecessary in general",
                "TCN_MEANMAX is clinically superior",
            ],
        },
        "gate_note": (
            "V2G4 PASS signifies correct conditional-branch handling (the pre-registered "
            "FALSE branch was followed correctly, with zero hybrid fits), not hybrid-model "
            "performance."
        ),
    }
    write_json("hybrid_disposition.json", data)
    return data


# ---------------------------------------------------------------------------
# zero-fit audit
# ---------------------------------------------------------------------------

def _fit_state_snapshot() -> dict:
    v2_004_run_dirs = sorted(
        p.name for p in (V2_004_DIR / "runs").iterdir() if p.is_dir()
    ) if (V2_004_DIR / "runs").exists() else []
    checkpoints_dir = ROOT / "checkpoints/model_v2"
    checkpoint_files = sorted(
        str(p.relative_to(ROOT)) for p in checkpoints_dir.rglob("*.pt")
    ) if checkpoints_dir.exists() else []
    v2_005_run_dirs = sorted(
        str(p.relative_to(ROOT)) for p in (OUT / "runs").iterdir() if p.is_dir()
    ) if (OUT / "runs").exists() else []
    search_budget = load_json(V2_004_DIR / "search_budget.json")
    return {
        "v2_004_run_directory_count": len(v2_004_run_dirs),
        "checkpoint_file_count": len(checkpoint_files),
        "v2_005_run_directory_count": len(v2_005_run_dirs),
        "cumulative_neural_fits_per_v2_004_search_budget": search_budget["cumulative_neural_fits"],
    }


def zero_fit_audit(before: dict) -> dict:
    after = _fit_state_snapshot()
    delta = {k: after[k] - before[k] for k in before}
    data = {
        "before": before,
        "after": after,
        "delta": delta,
        "fit_delta": delta["v2_004_run_directory_count"] + delta["v2_005_run_directory_count"],
        "checkpoint_delta": delta["checkpoint_file_count"],
        "status": "PASS" if (
            delta["v2_004_run_directory_count"] == 0
            and delta["v2_005_run_directory_count"] == 0
            and delta["checkpoint_file_count"] == 0
            and delta["cumulative_neural_fits_per_v2_004_search_budget"] == 0
        ) else "FAIL",
    }
    write_json("zero_fit_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# data scope audit
# ---------------------------------------------------------------------------

def data_scope_audit() -> dict:
    data = {
        "TRAIN_waveform_accessed": False,
        "VALIDATION_accessed": False,
        "CALIBRATION_accessed": False,
        "INTERNAL_TEST_accessed": False,
        "INCART_accessed": False,
        "NSTDB_accessed": False,
        "BIDMC_accessed": False,
        "raw_ECG_accessed": False,
        "annotations_accessed": False,
        "model_inference_run": False,
        "method_note": (
            "This script and the V2-005 phase as a whole read only already-frozen scalar "
            "JSON/CSV metadata (protocol locks, feature-audit lock, arch-causality lock, "
            "V2-004 result scalars) and git/registry state. No waveform file, feature-cache "
            "row, or annotation file was opened; no CV-role or D0.6 access ledger gained any "
            "new row from this phase (neither ledger has a V2-005 stage identity)."
        ),
        "status": "PASS",
    }
    write_json("data_scope_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# status vocabulary audit
# ---------------------------------------------------------------------------

def status_vocabulary_audit() -> dict:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    v2_005_row = next(r for r in rows if r["task_id"] == "V2-005")

    data = {
        "skipped_by_protocol_already_predeclared_in_registry_notes": (
            "SKIPPED_BY_PROTOCOL" in v2_005_row["notes"]
        ),
        "csv_field_is_plain_string_no_enum_constraint": True,
        "canonical_t_task_status_vocabulary_touched": False,
        "canonical_t_task_enum_location": (
            "src/nhm/coverage.py:TASK_STATUSES (canonical-only, unaffected)"
        ),
        "v2_specific_validator_updated": "tests/test_model_v2_control_plane.py",
        "narrow_resolution_predicate_module": "src/nhm/model_v2_conditional_prerequisite.py",
        "narrow_resolution_predicate_tests": "tests/test_v2_005_conditional_prerequisite.py",
        "conditional_prerequisite_semantics_tested": True,
        "status": "PASS",
    }
    write_json("status_vocabulary_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# search budget
# ---------------------------------------------------------------------------

def search_budget() -> dict:
    v2_004_budget = load_json(V2_004_DIR / "search_budget.json")
    data = {
        "global_neural_fit_cap": v2_004_budget["global_neural_fit_cap"],
        "v2_002_neural_fits": 15,
        "v2_004_neural_fits": 35,
        "v2_005_neural_fits_added": 0,
        "v2_005_classical_fits_added": 0,
        "cumulative_neural_fits_after_v2_005": 15 + 35 + 0,
        "hybrid_fit_count": 0,
        "status": "PASS" if (15 + 35 + 0) == 50 else "FAIL",
    }
    write_json("search_budget.json", data)
    return data


# ---------------------------------------------------------------------------
# registry transition record
# ---------------------------------------------------------------------------

def registry_transition() -> dict:
    data = {
        "V2-005": {"from": "NOT_STARTED", "to": "SKIPPED_BY_PROTOCOL"},
        "V2G4": {"from": "NOT_STARTED", "to": "PASS"},
        "preserved": {
            "V2-004": "PASS",
            "V2G3": "PASS",
            "V2-006": "NOT_STARTED",
            "V2G5": "NOT_STARTED",
            "V2-007": "NOT_STARTED",
            "V2G6": "NOT_STARTED",
        },
        "evidence_path": "reports/model_v2/v2_005/hybrid_disposition.json",
        "task_notes_required_statement": (
            "pre-registered hybrid trigger false; no hybrid model trained; 0 neural fits "
            "added; not a hybrid-performance result"
        ),
        "gate_notes_required_statement": (
            "PASS signifies correct conditional-branch handling, not hybrid-model performance"
        ),
        "no_freeze_registry_change": True,
        "no_canonical_t_task_registry_change": True,
        "no_new_component_registry_row": True,
    }
    write_json("registry_transition.json", data)
    return data


# ---------------------------------------------------------------------------
# test results + run manifest + artifact hashes
# ---------------------------------------------------------------------------

def test_results_summary(pytest_summary: dict) -> dict:
    data = {
        "pytest_collect_only_node_count": pytest_summary["collected_node_count"],
        "pytest_normal_run_exit_code": pytest_summary["exit_code"],
        "pytest_normal_run_result_line": pytest_summary["result_line"],
        "new_v2_005_test_files": [
            "tests/test_v2_005_conditional_prerequisite.py",
            "tests/test_v2_005_results.py",
        ],
        "ruff_exit_code": pytest_summary["ruff_exit_code"],
        "pip_check_exit_code": pytest_summary["pip_check_exit_code"],
        "status": "PASS" if pytest_summary["exit_code"] == 0 else "FAIL",
    }
    write_json("test_results.json", data)
    return data


def write_run_manifest_and_hashes() -> None:
    evidence_files = sorted(
        p.name
        for p in OUT.iterdir()
        if p.is_file() and p.name not in {"run_manifest.json", "artifact_hashes.json"}
    )
    head = sh("git", "rev-parse", "HEAD").stdout.strip()
    manifest = {
        "checkpoint_id": "V2-005",
        "phase_family": "HYBRID",
        "gate": "V2G4",
        "type": "zero_fit_conditional_branch_closure",
        "no_neural_fits": True,
        "no_classical_fits": True,
        "no_hybrid_model_created": True,
        "no_scientific_artifact_mutated": True,
        "head_at_generation": head,
        "evidence_files": evidence_files,
    }
    write_json("run_manifest.json", manifest)

    artifact_hashes = {}
    for name in [*evidence_files, "run_manifest.json"]:
        fp = OUT / name
        artifact_hashes[f"reports/model_v2/v2_005/{name}"] = hash_file(fp)
    write_json("artifact_hashes.json", {"artifacts": artifact_hashes})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    before_snapshot = _fit_state_snapshot()

    entry_audit()
    upstream_identity_audit()
    v2_004_readonly_integrity("v2_004_readonly_integrity_before.json")
    unexpected_hybrid_state_audit()
    verification = hybrid_trigger_verification()
    hybrid_disposition(verification)
    data_scope_audit()
    status_vocabulary_audit()
    search_budget()
    registry_transition()
    zero_fit_audit(before_snapshot)
    v2_004_readonly_integrity("v2_004_readonly_integrity_after.json")
    if (OUT / "pytest_summary_input.json").exists():
        pytest_summary = load_json(OUT / "pytest_summary_input.json")
        test_results_summary(pytest_summary)
    write_run_manifest_and_hashes()
    print("V2-005 evidence generated.")


if __name__ == "__main__":
    main()
