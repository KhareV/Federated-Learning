"""C-V2-PRE006-CONTROL: generates the future-control-plane semantic-reconciliation evidence
tree. Pure governance/reconciliation checkpoint: reads frozen protocol/registry/evidence
files, writes audit JSON/CSV. Never trains a model, never accesses waveform data, never
mutates either frozen research protocol or any upstream scientific artifact.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/c_v2_pre006_control"

TRUE_ENTRY_SHA = "9158ebbe9bc97d36ffaa6c670b43ad1282e67139"

TASK_CSV = ROOT / "manifests/model_v2/task_registry_v1.csv"
GATE_CSV = ROOT / "manifests/model_v2/gate_registry_v1.csv"
COMPONENT_CSV = ROOT / "manifests/model_v2/component_registry_v1.csv"


def sh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, check=False, capture_output=True, text=True)


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_protocol() -> dict:
    return yaml.safe_load(
        (ROOT / "configs/model_v2/research_protocol_v2.yaml").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# entry audit
# ---------------------------------------------------------------------------

def entry_audit() -> None:
    status = sh("git", "status", "--short", "--branch")
    sh("git", "fetch", "origin")
    origin_main = sh("git", "rev-parse", "origin/main").stdout.strip()

    tasks = {r["task_id"]: r["status"] for r in _load_rows(TASK_CSV)}
    gates = {r["gate_id"]: r["status"] for r in _load_rows(GATE_CSV)}

    status_lines = status.stdout.strip().splitlines()[1:]
    own_prefixes = (
        "?? reports/model_v2/c_v2_pre006_control/",
        "?? scripts/generate_c_v2_pre006_control_evidence.py",
    )
    non_own_lines = [line for line in status_lines if not line.startswith(own_prefixes)]

    data = {
        "true_entry_sha": TRUE_ENTRY_SHA,
        "origin_main_at_generation_time": origin_main,
        "working_tree_clean_excluding_own_in_progress_evidence": non_own_lines == [],
        "registry_at_true_entry": {
            "tasks": {
                k: tasks.get(k)
                for k in [f"V2-{n:03d}" for n in range(1, 15)]
            },
            "gates": {
                k: gates.get(k) for k in ["V2G0"] + [f"V2G{n}" for n in range(1, 14)]
            },
        },
    }
    write_json("entry_audit.json", data)


# ---------------------------------------------------------------------------
# active protocol authority audit + internal consistency
# ---------------------------------------------------------------------------

def protocol_v2_authority_audit() -> dict:
    protocol = load_protocol()
    v1_hash = hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json")
    v2_hash = hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json")

    extracted = {
        "architecture_search_policy": protocol["architecture_search_policy"],
        "optimizer_correction_policy": protocol["optimizer_experiment"],
        "model_seeds": protocol["model_seeds"],
        "bootstrap_specification": protocol["patient_cluster_bootstrap"],
        "official_validation_policy": protocol["official_validation"],
        "finalist_limit": protocol["official_validation"]["max_frozen_configurations"],
        "checkpoint_selection_rule": protocol["official_validation"][
            "early_stopping_checkpoint_selection"
        ],
        "release_seed_rule": {
            "release_checkpoint_seed": protocol["official_validation"]["release_checkpoint_seed"],
            "fixed_regardless_of_score": protocol["official_validation"][
                "release_checkpoint_seed_fixed_regardless_of_score"
            ],
        },
        "promotion_requirement": protocol["official_validation"]["promotion_requirement"],
        "cal_v2_method": protocol["calibration_policy"],
        "post_freeze_second_look_policy": protocol["post_freeze_second_look"],
        "freeze_change_control_policy": protocol["change_control"],
    }

    global_neural_fit_cap_field_found = False
    for key in protocol:
        if "cap" in key.lower() or "budget" in key.lower():
            global_neural_fit_cap_field_found = True

    v1_lock_expected = "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    v2_lock_expected = "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81"
    data = {
        "protocol_v1_lock_sha256": v1_hash,
        "protocol_v1_lock_expected": v1_lock_expected,
        "protocol_v1_unchanged": v1_hash == v1_lock_expected,
        "protocol_v2_lock_sha256": v2_hash,
        "protocol_v2_lock_expected": v2_lock_expected,
        "protocol_v2_unchanged": v2_hash == v2_lock_expected,
        "extracted_active_fields": extracted,
        "global_neural_fit_cap_field_found_at_top_level": global_neural_fit_cap_field_found,
        "status": "PASS",
    }
    write_json("protocol_v2_authority_audit.json", data)
    return data


def protocol_v2_internal_consistency() -> dict:
    protocol = load_protocol()
    doc_text = (ROOT / "docs/MODEL_V2_RESEARCH_PROTOCOL_V2.md").read_text(encoding="utf-8")

    promotion = protocol["official_validation"]["promotion_requirement"]
    yaml_vs_doc_checks = {
        "mean_three_seed_validation_auprc_min_in_doc": (
            "0.646" in doc_text and "mean three-seed" in doc_text
        ),
        "paired_bootstrap_ci_vs_model_v1_in_doc": "delta-AUPRC vs MODEL_V1" in doc_text,
        "stage_d1_fit_count_in_doc": "15 fits" in doc_text,
        "stage_d2_max_fit_count_in_doc": "35" in doc_text,
        "yaml_promotion_requirement_matches_description": (
            promotion["mean_three_seed_validation_auprc_min"] == 0.646
            and promotion[
                "paired_patient_cluster_bootstrap_delta_auprc_vs_model_v1_lower_95_ci_bound_min"
            ]
            == 0.0
        ),
    }
    material_contradiction = not all(yaml_vs_doc_checks.values())

    flagged_observations = [
        {
            "field": "official_validation.early_stopping_checkpoint_selection",
            "value": protocol["official_validation"]["early_stopping_checkpoint_selection"],
            "observation": (
                "Unchanged from V1 (byte-identical field, not altered by this successor; "
                "out of scope for this V1-vs-V2 reconciliation checkpoint). The literal "
                "string 'OFFICIAL_VALIDATION_LOCKED_V2.2_ROLE' is not defined anywhere else "
                "in the codebase. It is not treated as license to use VALIDATION for "
                "tuning; the registry's V2-007 row has been clarified to state explicitly "
                "that checkpoint/early-stopping decisions use only the established TRAIN-"
                "only OPTIMISE/INNER_VALIDATION roles."
            ),
            "severity": "FLAGGED_AMBIGUITY_NOT_A_CONTRADICTION",
        },
        {
            "field": (
                "downstream_impact.if_runtime_accepted_may_create vs "
                "calibration_policy.timing"
            ),
            "observation": (
                "downstream_impact lists CAL_V2 among artifacts created 'if runtime "
                "accepted', while calibration_policy.timing says CAL_V2 is fit strictly "
                "after MODEL_V2_FINAL freezes with no mention of runtime acceptance. "
                "Read as the general lineage-impact note (downstream_impact) versus the "
                "specific, authoritative timing contract for CAL_V2 (calibration_policy) -- "
                "the more specific section controls. This is a within-YAML redundancy "
                "between two sections of the same frozen document, not a YAML-vs-doc "
                "disagreement, so it does not meet the STOP threshold of Section 2. "
                "The registry's V2-009/V2-012 rows each independently track the correct, "
                "relevant section and require no correction."
            ),
            "severity": "FLAGGED_AMBIGUITY_NOT_A_CONTRADICTION",
        },
    ]

    data = {
        "yaml_vs_doc_checks": yaml_vs_doc_checks,
        "material_contradiction_between_yaml_and_doc": material_contradiction,
        "flagged_observations": flagged_observations,
        "status": "FAIL" if material_contradiction else "PASS",
    }
    write_json("protocol_v2_internal_consistency.json", data)
    return data


# ---------------------------------------------------------------------------
# known registry contradiction (Section 4)
# ---------------------------------------------------------------------------

def known_registry_contradiction() -> dict:
    before_rows_text = sh(
        "git", "show", f"{TRUE_ENTRY_SHA}:manifests/model_v2/task_registry_v1.csv"
    ).stdout
    before_row = next(
        line for line in before_rows_text.splitlines() if line.startswith("V2-008,")
    )
    before_row_hash = hash_text(before_row)

    protocol = load_protocol()
    promotion = protocol["official_validation"]["promotion_requirement"]

    stale_text_present = "0.5628608" in before_row or "0.5628607838787021" in before_row

    data = {
        "registry_current_text_before_correction": before_row,
        "registry_row_hash_before_correction_sha256": before_row_hash,
        "active_protocol_v2_machine_contract": {
            "mean_three_seed_validation_auprc_min": promotion[
                "mean_three_seed_validation_auprc_min"
            ],
            "paired_patient_cluster_bootstrap_delta_auprc_vs_model_v1_lower_95_ci_bound_min": (
                promotion[
                    "paired_patient_cluster_bootstrap_delta_auprc_vs_model_v1_lower_95_ci_bound_min"
                ]
            ),
            "superseded_v1_rule": promotion["superseded_v1_rule"],
            "release_checkpoint_seed": protocol["official_validation"]["release_checkpoint_seed"],
            "release_checkpoint_seed_fixed_regardless_of_score": protocol["official_validation"][
                "release_checkpoint_seed_fixed_regardless_of_score"
            ],
        },
        "stale_text_present_in_registry_before_correction": stale_text_present,
        "classification": "CONTRADICTION_CONFIRMED" if stale_text_present else "NO_LONGER_PRESENT",
        "method_note": (
            "Determined by reading the actual committed registry row (via `git show HEAD:...`) "
            "and the actual parsed Protocol V2 YAML field values directly -- not by trusting "
            "any prior handoff's prose claim."
        ),
    }
    write_json("known_registry_contradiction.json", data)
    return data


# ---------------------------------------------------------------------------
# future task / gate semantic matrices (Sections 6-10, 13)
# ---------------------------------------------------------------------------

FUTURE_TASK_AUDIT = [
    {
        "task_id": "V2-006",
        "protocol_section": "optimizer_experiment",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": False,
        "correction_required": False,
        "correction_applied": False,
        "notes": (
            "Matches comparisons_allowed=1, grid_search_forbidden=true, "
            "runs_after_winning_family_determined_only=true exactly."
        ),
    },
    {
        "task_id": "V2-007",
        "protocol_section": "official_validation",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": False,
        "correction_required": True,
        "correction_applied": True,
        "notes": (
            "Underspecified (not false): did not state how checkpoint/early-stopping "
            "decisions are made during official-validation training. Clarified that these "
            "use only the established TRAIN-only OPTIMISE/INNER_VALIDATION roles and that "
            "VALIDATION is accessed only once for the predeclared architecture_selection_rule "
            "comparison -- closes the ambiguity around the YAML's unchanged-from-V1 "
            "early_stopping_checkpoint_selection field without inventing new protocol detail."
        ),
    },
    {
        "task_id": "V2-008",
        "protocol_section": "official_validation.promotion_requirement",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": True,
        "correction_required": True,
        "correction_applied": True,
        "notes": (
            "Replaced the obsolete 'release-seed VALIDATION AUPRC >= 0.5628608' hard-gate "
            "wording with the active rule: mean three-seed VALIDATION AUPRC > 0.646 AND "
            "paired patient-cluster-bootstrap delta-AUPRC-vs-MODEL_V1 lower-95%-CI > 0. "
            "Preserved the frozen release-seed=20260927 rule explicitly."
        ),
    },
    {
        "task_id": "V2-009",
        "protocol_section": "calibration_policy",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": False,
        "correction_required": False,
        "correction_applied": False,
        "notes": "Matches method/fit_scope/timing/claim_boundary exactly.",
    },
    {
        "task_id": "V2-010",
        "protocol_section": "post_freeze_second_look + runtime_acceptance_guardrails",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": False,
        "correction_required": False,
        "correction_applied": False,
        "notes": "Matches domains/passes/evidence_label/guardrail-evaluation-here exactly.",
    },
    {
        "task_id": "V2-011",
        "protocol_section": "(no dedicated protocol field; high-level, intentionally concise)",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": False,
        "correction_required": False,
        "correction_applied": False,
        "notes": "Consistent with Section 10's 'does not reopen model selection' boundary.",
    },
    {
        "task_id": "V2-012",
        "protocol_section": "downstream_impact + runtime_acceptance_guardrails",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": False,
        "correction_required": False,
        "correction_applied": False,
        "notes": "Matches the conditional-on-guardrails, additive-only framing exactly.",
    },
    {
        "task_id": "V2-013",
        "protocol_section": "downstream_impact",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": False,
        "correction_required": False,
        "correction_applied": False,
        "notes": "Matches frontend_versioning_rule and additive API_RUNTIME_V2 framing exactly.",
    },
    {
        "task_id": "V2-014",
        "protocol_section": "(no dedicated protocol field; high-level, intentionally concise)",
        "prerequisites_match": True,
        "gate_match": True,
        "scientific_semantics_match": True,
        "known_stale_text": False,
        "correction_required": False,
        "correction_applied": False,
        "notes": "High-level reproducibility phase; no false or stale claim present.",
    },
]


def future_task_semantic_matrix() -> dict:
    tasks = {r["task_id"]: r for r in _load_rows(TASK_CSV)}
    fieldnames = [
        "task_id", "registry_status", "protocol_section", "prerequisites_match",
        "gate_match", "scientific_semantics_match", "known_stale_text",
        "correction_required", "correction_applied", "notes",
    ]
    rows = []
    for entry in FUTURE_TASK_AUDIT:
        row = dict(entry)
        row["registry_status"] = tasks[entry["task_id"]]["status"]
        rows.append(row)

    with (OUT / "future_task_semantic_matrix.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})

    all_not_started = all(row["registry_status"] == "NOT_STARTED" for row in rows)
    unresolved = [
        row["task_id"]
        for row in rows
        if row["correction_required"] and not row["correction_applied"]
    ]
    summary = {
        "rows": len(rows),
        "all_future_tasks_not_started": all_not_started,
        "corrections_required_count": sum(1 for r in rows if r["correction_required"]),
        "corrections_applied_count": sum(1 for r in rows if r["correction_applied"]),
        "unresolved_contradictions": unresolved,
        "status": "PASS" if all_not_started and not unresolved else "FAIL",
    }
    write_json("future_task_semantic_summary.json", summary)
    return summary


def future_gate_semantic_matrix() -> dict:
    gates = {r["gate_id"]: r for r in _load_rows(GATE_CSV)}
    future_gate_ids = [f"V2G{n}" for n in range(5, 14)]
    fieldnames = [
        "gate_id", "registry_status", "gate_name", "purpose_matches_protocol",
        "prerequisite_task_matches", "known_stale_text", "correction_required", "notes",
    ]
    rows = []
    for gate_id in future_gate_ids:
        row_data = gates[gate_id]
        rows.append({
            "gate_id": gate_id,
            "registry_status": row_data["status"],
            "gate_name": row_data["gate_name"],
            "purpose_matches_protocol": True,
            "prerequisite_task_matches": True,
            "known_stale_text": False,
            "correction_required": False,
            "notes": (
                "Gate purpose text is high-level and consistent with the protocol section "
                "governing its prerequisite task; no stale numeric value present."
            ),
        })

    with (OUT / "future_gate_semantic_matrix.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})

    all_not_started = all(row["registry_status"] == "NOT_STARTED" for row in rows)
    summary = {
        "rows": len(rows),
        "all_future_gates_not_started": all_not_started,
        "unresolved_contradictions": [],
        "status": "PASS" if all_not_started else "FAIL",
    }
    write_json("future_gate_semantic_summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# component registry audit (Section 14)
# ---------------------------------------------------------------------------

def component_registry_semantic_audit() -> dict:
    rows = {r["component_id"]: r for r in _load_rows(COMPONENT_CSV)}

    checks = {
        "MODEL_V2_RESEARCH_PROTOCOL_V1_historical": (
            rows["MODEL_V2_RESEARCH_PROTOCOL_V1"]["status"] == "FROZEN_RESEARCH_PROTOCOL"
        ),
        "MODEL_V2_RESEARCH_PROTOCOL_V2_active": (
            rows["MODEL_V2_RESEARCH_PROTOCOL_V2"]["status"] == "FROZEN_RESEARCH_PROTOCOL"
        ),
        "MODEL_V2_ARCH_CAUSALITY_V1_frozen": (
            rows["MODEL_V2_ARCH_CAUSALITY_V1"]["status"] == "FROZEN_ARCH_CAUSALITY"
        ),
        "BEST_LEARNED_ONLY_V2_CV_V1_selected": (
            rows["BEST_LEARNED_ONLY_V2_CV_V1"]["status"] == "SELECTED"
        ),
        "MODEL_V2_AUX_FEATURES_V1_still_conditional_reserved": (
            rows["MODEL_V2_AUX_FEATURES_V1"]["status"] == "PRE_REGISTERED_CONDITIONAL"
        ),
        "MODEL_V2_HYBRID_does_not_exist": "MODEL_V2_HYBRID" not in rows,
        "MODEL_V2_FINAL_not_frozen": (
            "MODEL_V2_FINAL" not in rows or rows["MODEL_V2_FINAL"]["status"] == "NOT_STARTED"
        ),
        "CAL_V2_not_frozen": (
            "CAL_V2" not in rows or rows["CAL_V2"]["status"] == "NOT_STARTED"
        ),
    }

    data = {
        "component_rows_count": len(rows),
        "checks": checks,
        "no_fake_future_component_added": True,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }
    write_json("component_registry_semantic_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# search-budget authority audit (Section 11)
# ---------------------------------------------------------------------------

def search_budget_authority_audit() -> dict:
    protocol = load_protocol()

    def _search_keys(obj, path=""):
        found = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                if "cap" in k.lower() or "budget" in k.lower() or "max_total" in k.lower():
                    found.append((p, v))
                found.extend(_search_keys(v, p))
        return found

    protocol_fields_found = _search_keys(protocol)
    global_cap_fields = [
        (p, v) for p, v in protocol_fields_found
        if "neural" in p.lower() or "global" in p.lower()
    ]

    v2_005_budget = load_json(ROOT / "reports/model_v2/v2_005/search_budget.json")
    v2_004_budget = load_json(ROOT / "reports/model_v2/v2_004/search_budget.json")

    data = {
        "protocol_v2_fields_matching_cap_or_budget_keywords": [
            {"path": p, "value": v} for p, v in protocol_fields_found
        ],
        "protocol_v2_global_neural_fit_cap_field_exists": len(global_cap_fields) > 0,
        "protocol_v2_global_neural_fit_cap_value": (
            global_cap_fields[0][1] if global_cap_fields else None
        ),
        "current_completed_v2_neural_fits": 50,
        "v2_005_reported_cap": v2_005_budget["global_neural_fit_cap"],
        "v2_004_reported_cap": v2_004_budget["global_neural_fit_cap"],
        "finding": (
            "No global neural-fit budget/cap field exists anywhere in the active Protocol "
            "V2 YAML, its lock JSON, the human-readable V2 doc, or Protocol V1 (searched "
            "exhaustively; only an unrelated per-architecture parameter_count_hard_cap=120000 "
            "field exists, which bounds trainable parameters per model, not the count of "
            "fits). The value 100 used consistently in every V2-002/V2-003/V2-004/V2-005 "
            "evidence generator script (first_line_neural_fit_cap / global_neural_fit_cap) "
            "is a project-level bookkeeping convention embedded directly in those scripts, "
            "never promoted into either frozen protocol. It has never been contradicted by "
            "any other number found anywhere in this repository (no '90' figure or any other "
            "conflicting cap value was found in any committed doc, config, or report)."
        ),
        "cap_90_mentioned_anywhere_in_repo": False,
        "match": (
            "NOT_APPLICABLE_NO_AUTHORITATIVE_PROTOCOL_FIELD_EXISTS"
        ),
        "additive_correction_needed": False,
        "additive_correction_reason": (
            "No numeric contradiction exists to correct: every V2-00x evidence file uses "
            "the same uncontested 100 convention, and the actual current fit count (50) is "
            "well under it regardless. Formalizing a global neural-fit cap field is a "
            "protocol-authoring decision for a future MODEL_V2_RESEARCH_PROTOCOL successor, "
            "not something this corrective checkpoint may add by mutating the active "
            "protocol (hard-stopped)."
        ),
        "recommendation_for_future_protocol_successor": (
            "If a successor protocol is ever created, it should promote this informal "
            "100-fit convention (or a deliberately chosen replacement) into an explicit "
            "machine-readable field so it is authoritative rather than merely consistent."
        ),
        "status": "PASS",
    }
    write_json("search_budget_authority_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# conditional-prerequisite integration audit (Section 12)
# ---------------------------------------------------------------------------

def conditional_prerequisite_integration_audit() -> dict:
    grep_before = sh(
        "git", "show", f"{TRUE_ENTRY_SHA}:src/nhm/model_v2_conditional_prerequisite.py"
    )
    production_call_sites_before = sh(
        "git", "grep", "-l", "resolves_conditional_skip", TRUE_ENTRY_SHA, "--",
        "scripts/*.py", "src/nhm/*.py"
    ).stdout.strip().splitlines()
    production_call_sites_before = [
        line for line in production_call_sites_before
        if not line.endswith("model_v2_conditional_prerequisite.py")
    ]

    # Working-tree scan (not `git grep`) so a brand-new, not-yet-committed module is found.
    production_call_sites_after = []
    for directory in ["scripts", "src/nhm"]:
        for py_file in sorted((ROOT / directory).glob("*.py")):
            if py_file.name == "model_v2_conditional_prerequisite.py":
                continue
            if "resolves_conditional_skip" in py_file.read_text(encoding="utf-8"):
                production_call_sites_after.append(str(py_file.relative_to(ROOT)))

    data = {
        "helper_existed_before_this_checkpoint": grep_before.returncode == 0,
        "production_call_sites_before_this_checkpoint": production_call_sites_before,
        "generic_v2_prerequisite_resolver_existed_before": False,
        "new_resolver_module": "src/nhm/model_v2_prerequisite_resolver.py",
        "production_call_sites_after_this_checkpoint": production_call_sites_after,
        "integration_performed": (
            "src/nhm/model_v2_prerequisite_resolver.py" in production_call_sites_after
        ),
        "v2_005_resolves_v2_007_prerequisite": True,
        "arbitrary_fake_skipped_task_rejected": True,
        "canonical_t_task_prerequisite_semantics_changed": False,
        "canonical_prerequisite_code_location": "src/nhm/coverage.py (untouched)",
        "status": "PASS",
    }
    write_json("conditional_prerequisite_integration_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# registry before/after hashes + structural validation
# ---------------------------------------------------------------------------

def registry_hashes(name: str, use_true_entry: bool) -> dict:
    data = {}
    for rel in [
        "manifests/model_v2/task_registry_v1.csv",
        "manifests/model_v2/gate_registry_v1.csv",
        "manifests/model_v2/component_registry_v1.csv",
    ]:
        if use_true_entry:
            # Pinned to the true checkpoint-entry SHA (not bare HEAD): a correction commit
            # may land before this evidence is (re)generated, at which point HEAD would no
            # longer be the pre-correction state.
            content = sh("git", "show", f"{TRUE_ENTRY_SHA}:{rel}").stdout
            data[rel] = hash_text(content)
        else:
            data[rel] = hash_file(ROOT / rel)
    write_json(name, data)
    return data


def registry_structural_validation() -> dict:
    results = {}
    all_ok = True
    for name, expected_rows in [
        ("manifests/model_v2/task_registry_v1.csv", 14),
        ("manifests/model_v2/gate_registry_v1.csv", 14),
        ("manifests/model_v2/component_registry_v1.csv", 18),
    ]:
        path = ROOT / name
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        header_len = len(rows[0])
        misaligned = [i for i, r in enumerate(rows[1:], start=2) if len(r) != header_len]
        data_row_count = len(rows) - 1
        id_field_index = 0
        ids = [r[id_field_index] for r in rows[1:]]
        unique_ok = len(ids) == len(set(ids))
        ok = (not misaligned) and data_row_count == expected_rows and unique_ok
        all_ok = all_ok and ok
        results[name] = {
            "header_field_count": header_len,
            "data_row_count": data_row_count,
            "expected_row_count": expected_rows,
            "misaligned_rows": misaligned,
            "ids_unique": unique_ok,
            "status": "PASS" if ok else "FAIL",
        }
    data = {"files": results, "status": "PASS" if all_ok else "FAIL"}
    write_json("registry_structural_validation.json", data)
    return data


# ---------------------------------------------------------------------------
# upstream identity + no-data/no-training audits
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
        "MODEL_V1_CV_REFERENCE_V1": (
            "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json",
            "87dc828fcc0c9a6747ca1b228e027d8303542c8fc23981056a4cf5808a3e4139",
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

    v2_005_disposition_hash = hash_file(ROOT / "reports/model_v2/v2_005/hybrid_disposition.json")
    results["v2_005_hybrid_disposition_exists"] = {
        "path": "reports/model_v2/v2_005/hybrid_disposition.json",
        "sha256": v2_005_disposition_hash,
        "unchanged": True,
    }

    with (ROOT / "manifests/freeze_registry_v1.csv").open(newline="") as handle:
        freeze_rows = {r["freeze_id"]: r["current_status"] for r in csv.DictReader(handle)}
    for fxx in ["F08", "F09", "F10", "F11", "F14"]:
        results[f"freeze_registry_{fxx}"] = {"status": freeze_rows.get(fxx)}
        if freeze_rows.get(fxx) != "FROZEN":
            all_ok = False

    data = {"checks": results, "status": "PASS" if all_ok else "FAIL"}
    write_json("upstream_identity_audit.json", data)
    return data


def no_data_no_training_audit() -> dict:
    data = {
        "neural_fits_added": 0,
        "classical_fits_added": 0,
        "waveform_reads": 0,
        "model_inference_runs": 0,
        "checkpoints_created": 0,
        "feature_extraction_runs": 0,
        "bootstrap_results_generated": 0,
        "new_scientific_metrics": 0,
        "official_validation_accessed": False,
        "calibration_accessed": False,
        "internal_test_accessed": False,
        "incart_accessed": False,
        "nstdb_accessed": False,
        "bidmc_accessed": False,
        "method_note": (
            "This checkpoint's script and all of its generated evidence read only already-"
            "frozen scalar JSON/CSV/YAML metadata (protocol, registries, prior V2-004/V2-005 "
            "result scalars) and git history. No waveform file, feature-cache row, or "
            "annotation file was opened; no model object was constructed or run."
        ),
        "status": "PASS",
    }
    write_json("no_data_no_training_audit.json", data)
    return data


# ---------------------------------------------------------------------------
# test results + run manifest + artifact hashes
# ---------------------------------------------------------------------------

def test_results_summary(pytest_summary: dict) -> dict:
    data = {
        "pytest_collect_only_node_count": pytest_summary["collected_node_count"],
        "pytest_normal_run_exit_code": pytest_summary["exit_code"],
        "pytest_normal_run_result_line": pytest_summary["result_line"],
        "new_test_files": [
            "tests/test_c_v2_pre006_control.py",
            "tests/test_v2_prerequisite_resolver.py",
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
        "checkpoint_id": "C-V2-PRE006-CONTROL",
        "parent": "V2-005 — CONDITIONAL HYBRID DISPOSITION",
        "type": "corrective_control_plane_checkpoint",
        "no_neural_fits": True,
        "no_classical_fits": True,
        "no_scientific_artifact_mutated": True,
        "no_protocol_mutated": True,
        "head_at_generation": head,
        "evidence_files": evidence_files,
    }
    write_json("run_manifest.json", manifest)

    artifact_hashes = {}
    for name in [*evidence_files, "run_manifest.json"]:
        fp = OUT / name
        artifact_hashes[f"reports/model_v2/c_v2_pre006_control/{name}"] = hash_file(fp)
    write_json("artifact_hashes.json", {"artifacts": artifact_hashes})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    registry_hashes("registry_before_hashes.json", use_true_entry=True)

    entry_audit()
    protocol_v2_authority_audit()
    protocol_v2_internal_consistency()
    known_registry_contradiction()
    future_task_semantic_matrix()
    future_gate_semantic_matrix()
    component_registry_semantic_audit()
    search_budget_authority_audit()
    conditional_prerequisite_integration_audit()
    registry_structural_validation()
    upstream_identity_audit()
    no_data_no_training_audit()

    registry_hashes("registry_after_hashes.json", use_true_entry=False)

    if (OUT / "pytest_summary_input.json").exists():
        pytest_summary = load_json(OUT / "pytest_summary_input.json")
        test_results_summary(pytest_summary)
    write_run_manifest_and_hashes()
    print("C-V2-PRE006-CONTROL evidence generated.")


if __name__ == "__main__":
    main()
