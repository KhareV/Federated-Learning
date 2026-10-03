#!/usr/bin/env python3
"""C-V2-PRE006-AUTHORITY-REPAIR: create the additive MODEL_V2_RESEARCH_PROTOCOL_V3 successor.

Carries every V2 field forward BYTE-IDENTICAL except the implementation-drift fields
explicitly identified by the self-contained MODEL_V2 authority contract supplied in the
C-V2-PRE006-AUTHORITY-REPAIR checkpoint prompt:

1. official_validation.early_stopping_checkpoint_selection: V2 carried forward V1's
   OFFICIAL_VALIDATION_LOCKED_V2.2_ROLE value unchanged (official VALIDATION itself governs
   early stopping/scheduler/checkpoint selection for the V2-007 finalists). V3 replaces this
   with a dedicated TRAIN-only final inner-validation split (MITDB_TRAIN_FINAL_INNER_V2_V1):
   OPTIMISE groups update weights/pos_weight; FINAL_INNER_VALIDATION groups control
   scheduler/early-stopping/checkpoint selection; official VALIDATION is evaluation/finalist-
   comparison only, after each candidate checkpoint is already fixed.
2. official_validation.promotion_requirement.auroc_material_regression_forbidden: V2 carried
   this forward from V1 as an active hard D5 promotion gate. V3 supersedes it: AUROC remains
   a reported secondary diagnostic, not an additional hard D5/D6 promotion criterion. The two
   hard criteria remain the mean-three-seed-AUPRC and paired-bootstrap-CI rules (unchanged).
   The separate runtime-acceptance/INCART AUROC guardrail is unchanged and stays distinct.
3. Adds an explicit search_budget section: MODEL_V2 D0-D5 ceiling is 90 neural fits (not the
   100 figure used as an uncontested-but-unauthoritative control-plane convention in prior
   V2-002..V2-005 evidence). This does not change any historical fit count.
4. Adds explicit cal_v2_ordering and model_v2_final_vs_runtime_acceptance sections making
   already-implied chronology/separation machine-explicit.

Does not touch MODEL_V2_RESEARCH_PROTOCOL_V1 or MODEL_V2_RESEARCH_PROTOCOL_V2 (never mutated
in place, per their own change_control clauses) and does not alter architectures, parameter
counts, outer-CV manifests, feature audit, MODEL_V1_CV_REFERENCE_V1, V2-002/V2-003/V2-004/
V2-005 results, bootstrap unit, CAL_V2 method, or post-freeze second-look policy.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from nhm.hashing import hash_canonical_json, hash_file

ROOT = Path(__file__).resolve().parents[1]
V2_PATH = ROOT / "configs/model_v2/research_protocol_v2.yaml"
V3_PATH = ROOT / "configs/model_v2/research_protocol_v3.yaml"
V3_DOC_PATH = ROOT / "docs/MODEL_V2_RESEARCH_PROTOCOL_V3.md"
V3_LOCK_PATH = ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"


def build_v3_config() -> dict:
    v2 = yaml.safe_load(V2_PATH.read_text(encoding="utf-8"))
    v3 = copy.deepcopy(v2)

    v3["protocol_id"] = "MODEL_V2_RESEARCH_PROTOCOL_V3"
    v3["parent_protocol"] = "MODEL_V2_RESEARCH_PROTOCOL_V2"
    v3["owner_task"] = "C-V2-PRE006-AUTHORITY-REPAIR"
    v3["status"] = "FROZEN_RESEARCH_PROTOCOL"
    v3["change_reason"] = (
        "Pre-V2-006 correction of implementation drift relative to the self-contained "
        "MODEL_V2 authority contract supplied in the C-V2-PRE006-AUTHORITY-REPAIR checkpoint "
        "prompt: (1) official VALIDATION must never govern early stopping, scheduler "
        "decisions, or checkpoint selection for the V2-007 finalists -- V2 had carried "
        "forward V1's OFFICIAL_VALIDATION_LOCKED_V2.2_ROLE value unchanged, which assigned "
        "exactly that role to official VALIDATION; V3 replaces it with a dedicated TRAIN-"
        "only final inner-validation split (MITDB_TRAIN_FINAL_INNER_V2_V1). (2) AUROC is a "
        "reported secondary diagnostic at D5, not an additional hard promotion gate -- V2 "
        "had carried forward V1's auroc_material_regression_forbidden=true hard gate "
        "unchanged; V3 supersedes it, leaving the two hard AUPRC criteria unchanged. (3) The "
        "MODEL_V2 D0-D5 neural-fit search ceiling is explicitly 90, not the 100 figure used "
        "as an unauthoritative control-plane convention in prior V2-002..V2-005 evidence. "
        "No historical fit count, architecture result, or hybrid disposition changes."
    )

    # --- Drift 1: final TRAIN-only role split replaces official-VALIDATION checkpoint role --
    official_validation = v3["official_validation"]
    official_validation["superseded_v2_checkpoint_selection_rule"] = {
        "early_stopping_checkpoint_selection": "OFFICIAL_VALIDATION_LOCKED_V2.2_ROLE",
        "note": (
            "V2 carried this value forward unchanged from V1 (byte-identical field), which "
            "assigned early-stopping/checkpoint-selection to official VALIDATION itself for "
            "the V2-007 finalists (V1 doc Section K's explicit prose). Superseded below."
        ),
    }
    del official_validation["early_stopping_checkpoint_selection"]
    official_validation["early_stopping_checkpoint_selection"] = (
        "FINAL_TRAIN_INNER_VALIDATION_LOCKED_V3_ROLE"
    )
    official_validation["official_validation_role"] = (
        "EVALUATION_AND_FINALIST_COMPARISON_ONLY_AFTER_CHECKPOINT_FIXED"
    )

    v3["final_train_role_split"] = {
        "component_id": "MITDB_TRAIN_FINAL_INNER_V2_V1",
        "historical_outer_cv_inner_manifest_unchanged": "MITDB_TRAIN_INNER_V2_V1",
        "population": "ALL_27_TRAIN_PATIENT_GROUPS",
        "roles": ["OPTIMISE", "FINAL_INNER_VALIDATION"],
        "expected_optimise_count_approx": 22,
        "expected_final_inner_validation_count_approx": 5,
        "optimise_controls": ["gradient_updates", "pos_weight", "train_augmentation"],
        "final_inner_validation_controls": [
            "scheduler_metric", "early_stopping_metric", "checkpoint_selection_metric",
        ],
        "official_validation_forbidden_roles": [
            "gradient_updates", "pos_weight", "scheduler", "early_stopping",
            "checkpoint_selection", "architecture_modification", "hyperparameter_tuning",
        ],
        "pos_weight_formula": "negative_OPTIMISE_windows / positive_OPTIMISE_windows",
        "v1_comparison_asymmetry_note": (
            "Historical MODEL_V1 used official VALIDATION for early stopping/checkpoint "
            "selection (carried forward unchanged into V1/V2's "
            "early_stopping_checkpoint_selection field). MODEL_V2 V2-007 finalist training "
            "deliberately uses MITDB_TRAIN_FINAL_INNER_V2_V1 instead -- a documented, "
            "deliberate methodological difference. V1 is never retroactively retrained or "
            "'fixed' because of this difference; the V2-vs-V1 official-validation comparison "
            "carries this known asymmetry."
        ),
    }

    # --- Drift 2: AUROC is secondary at D5, not an additional hard promotion gate -----------
    promotion = official_validation["promotion_requirement"]
    promotion["superseded_v2_auroc_rule"] = {
        "auroc_material_regression_forbidden": True,
        "note": (
            "V2 carried this forward unchanged from V1 as an active hard D5 promotion gate. "
            "Superseded below: AUROC remains reported but is not an additional hard D5/D6 "
            "promotion criterion. The two hard criteria are the mean-three-seed-AUPRC and "
            "paired-bootstrap-CI rules, both unchanged. The separate runtime-acceptance/"
            "INCART AUROC guardrail (runtime_acceptance_guardrails) is unchanged and remains "
            "distinct from scientific promotion."
        ),
    }
    del promotion["auroc_material_regression_forbidden"]
    promotion["auroc_material_regression_forbidden"] = False
    promotion["auroc_role"] = "SECONDARY_DIAGNOSTIC_REPORTED_NOT_A_D5_HARD_GATE"

    # --- Drift 3: explicit MODEL_V2 D0-D5 search budget (new section, no V2 predecessor) ----
    v3["search_budget"] = {
        "d0_d5_max_neural_fits": 90,
        "v2_006_local_max_new_fits": 15,
        "v2_007_max_new_fits": 6,
        "completed_neural_fits_before_v2_006": 50,
        "max_cumulative_after_v2_006": 65,
        "max_cumulative_through_v2_007": 71,
        "cap_is_search_control_ceiling_not_performance_target": True,
        "superseded_fields": {
            "prior_evidence_denominator": 100,
            "note": (
                "V2-002/V2-003/V2-004/V2-005 evidence (search_budget.json files) reported a "
                "100-fit denominator that was never actually defined as an authoritative "
                "field in Protocol V1 or V2 -- an unauthoritative control-plane reporting "
                "convention. V3 establishes the authoritative MODEL_V2 D0-D5 ceiling of 90. "
                "This does not change any historical fit count: completed fits remain 50 "
                "(V2-002=15, V2-004=35, V2-005=0); no prior zero-fit decision is invalidated; "
                "historical evidence text is not rewritten."
            ),
        },
    }

    # --- Explicit CAL_V2 ordering (machine-explicit; chronology itself was already derivable
    # from calibration_policy.timing + post_freeze_second_look.timing, unchanged here) -------
    v3["cal_v2_ordering"] = {
        "chronology": [
            "MODEL_V2_official_validation",
            "MODEL_V2_FINAL_freeze",
            "CAL_V2_fit_freeze",
            "post_freeze_second_look_INTERNAL_TEST_INCART_NSTDB",
            "runtime_acceptance_decision",
            "gateway_api_frontend_integration_only_if_accepted",
        ],
        "cal_v2_contingent_on_runtime_acceptance": False,
        "governing_fields": [
            "calibration_policy.timing", "post_freeze_second_look.timing",
        ],
    }

    # --- Explicit MODEL_V2_FINAL vs runtime-acceptance separation (already implied by
    # runtime_acceptance_guardrails.note; made machine-explicit here) ------------------------
    v3["model_v2_final_vs_runtime_acceptance"] = {
        "model_v2_final": "SCIENTIFICALLY_SELECTED_AND_FROZEN_AFTER_OFFICIAL_VALIDATION",
        "model_v2_runtime_accepted": "DETERMINED_LATER_AFTER_POST_FREEZE_SECOND_LOOK",
        "frozen_v2_may_remain_non_operational_if_guardrails_fail": True,
        "model_v1_remains_operational_if_v2_not_runtime_accepted": True,
    }

    return v3


def main() -> None:
    v3 = build_v3_config()
    V3_PATH.write_text(
        yaml.safe_dump(v3, sort_keys=False, default_flow_style=False, width=100), encoding="utf-8"
    )

    doc_lines = [
        "# MODEL_V2_RESEARCH_PROTOCOL_V3",
        "",
        "Additive successor to MODEL_V2_RESEARCH_PROTOCOL_V2, created by "
        "C-V2-PRE006-AUTHORITY-REPAIR before V2-006 begins. V1 and V2 are never mutated in "
        "place (see their own `change_control` clauses); this document and "
        "`configs/model_v2/research_protocol_v3.yaml` are the only authoritative sources for "
        "the corrections below. All other V2 content (fixed scientific constants, "
        "architectures and parameter counts, outer-CV manifests, feature audit, "
        "MODEL_V1_CV_REFERENCE_V1, V2-002/V2-003/V2-004/V2-005 results, the hybrid trigger, "
        "the two hard AUPRC promotion criteria, the patient-cluster bootstrap unit, the "
        "CAL_V2 method, and the post-freeze second-look policy) is carried forward unchanged.",
        "",
        "## Correction 1: final TRAIN-only inner split replaces official-VALIDATION "
        "checkpoint selection",
        "",
        "V2 carried forward V1's `early_stopping_checkpoint_selection = "
        "OFFICIAL_VALIDATION_LOCKED_V2.2_ROLE` field unchanged, which assigned early-stopping/"
        "scheduler/checkpoint-selection to official VALIDATION itself for the V2-007 "
        "finalists. V3 replaces this with a dedicated additive component, "
        "`MITDB_TRAIN_FINAL_INNER_V2_V1`, covering all 27 TRAIN groups split once into "
        "approximately 22 `OPTIMISE` groups and approximately 5 `FINAL_INNER_VALIDATION` "
        "groups:",
        "",
        "- **OPTIMISE**: receives gradient updates, determines pos_weight "
        "(`negative_OPTIMISE_windows / positive_OPTIMISE_windows`), receives TRAIN "
        "augmentation.",
        "- **FINAL_INNER_VALIDATION**: no gradient updates, no augmentation; controls the "
        "scheduler metric, the early-stopping metric, and checkpoint selection.",
        "- **Official VALIDATION**: never provides gradient updates, never determines "
        "pos_weight, never drives the scheduler or early stopping, never selects the epoch "
        "or checkpoint, never modifies architecture/hyperparameters. It is accessed only "
        "after each finalist's checkpoint is already fixed, for the predeclared finalist "
        "comparison and promotion evaluation.",
        "",
        "This is a documented, deliberate methodological difference from historical MODEL_V1 "
        "(which used official VALIDATION for early stopping/checkpoint selection). V1 is "
        "never retroactively retrained because of this difference.",
        "",
        "## Correction 2: AUROC is a secondary D5 diagnostic, not an additional hard gate",
        "",
        "V2 carried forward V1's `auroc_material_regression_forbidden = true` as an active "
        "hard D5 promotion gate. V3 supersedes it (`false`, with `auroc_role = "
        "SECONDARY_DIAGNOSTIC_REPORTED_NOT_A_D5_HARD_GATE`). The two hard D5 promotion "
        "criteria remain exactly:",
        "",
        "1. mean three-seed official VALIDATION AUPRC > 0.646; and",
        "2. the paired patient-cluster-bootstrap delta-AUPRC vs MODEL_V1 has a lower 95% CI "
        "bound > 0, for the required release-seed/three-seed comparisons.",
        "",
        "AUROC remains reported. The separate runtime-acceptance/INCART AUROC guardrail "
        "(`runtime_acceptance_guardrails`) is unchanged and remains distinct from scientific "
        "promotion.",
        "",
        "## Correction 3: explicit MODEL_V2 D0-D5 search budget",
        "",
        "V3 adds an explicit `search_budget` section: the MODEL_V2 D0-D5 neural-fit ceiling "
        "is **90** (not the 100 figure used as an unauthoritative control-plane convention "
        "in prior V2-002..V2-005 evidence, and never actually defined in Protocol V1 or V2). "
        "Completed neural fits before V2-006: 50 (V2-002=15, V2-004=35, V2-005=0). V2-006's "
        "local maximum is 15 (max cumulative 65); V2-007's maximum is 6 finalist seed-fits "
        "(max cumulative through official VALIDATION: 71). The 90-fit ceiling is not "
        "currently restrictive but remains a frozen search-control rule. No historical fit "
        "count changes.",
        "",
        "## Correction 4: explicit CAL_V2 ordering and MODEL_V2_FINAL/runtime-acceptance "
        "separation",
        "",
        "V3 adds explicit `cal_v2_ordering` and `model_v2_final_vs_runtime_acceptance` "
        "sections making already-implied chronology and separation machine-explicit: "
        "official VALIDATION -> MODEL_V2_FINAL freeze -> CAL_V2 fit/freeze -> post-freeze "
        "INTERNAL_TEST/INCART/NSTDB second look -> runtime-acceptance decision -> gateway/"
        "API/frontend integration only if accepted. CAL_V2 is never contingent on runtime "
        "acceptance. MODEL_V2_FINAL (scientific freeze) and runtime acceptance (operational) "
        "remain separate decisions; MODEL_V1 stays operational if V2 is not runtime-accepted.",
        "",
        "## What is unchanged",
        "",
        "Target, split, PREPROC_V1, architecture identities and parameter counts, outer-CV "
        "manifests (MITDB_TRAIN_CV_V2_V1, MITDB_TRAIN_INNER_V2_V1 -- both byte-unchanged), "
        "the feature-information audit, MODEL_V1_CV_REFERENCE_V1, V2-002/V2-003/V2-004/"
        "V2-005 results (including the hybrid trigger and BEST_LEARNED_ONLY_V2_CV_V1 "
        "selection), the mean-three-seed-AUPRC and paired-bootstrap-CI hard promotion "
        "criteria, the release-seed=20260927 rule, the patient-cluster bootstrap unit and "
        "procedure, the CAL_V2 method, and the post-freeze second-look policy are all "
        "carried forward byte-for-byte from V2 and are not altered by this successor.",
        "",
    ]
    V3_DOC_PATH.write_text("\n".join(doc_lines), encoding="utf-8")

    lock = {
        "protocol_id": "MODEL_V2_RESEARCH_PROTOCOL_V3",
        "parent_protocol": "MODEL_V2_RESEARCH_PROTOCOL_V2",
        "parent_protocol_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json"
        ),
        "status": "FROZEN_RESEARCH_PROTOCOL",
        "owner_task": "C-V2-PRE006-AUTHORITY-REPAIR",
        "config_sha256": hash_file(V3_PATH),
        "config_canonical_hash": hash_canonical_json(yaml.safe_load(V3_PATH.read_text())),
        "doc_sha256": hash_file(V3_DOC_PATH),
        "v1_unmodified": True,
        "v2_unmodified": True,
        "v1_lock_path": "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json",
        "v2_lock_path": "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json",
        "corrections": [
            "official_validation.early_stopping_checkpoint_selection: "
            "FINAL_TRAIN_INNER_VALIDATION_LOCKED_V3_ROLE, replacing "
            "OFFICIAL_VALIDATION_LOCKED_V2.2_ROLE",
            "final_train_role_split: new section binding MITDB_TRAIN_FINAL_INNER_V2_V1 "
            "(OPTIMISE/FINAL_INNER_VALIDATION) and forbidding official VALIDATION from "
            "gradient/pos_weight/scheduler/early-stop/checkpoint/architecture roles",
            "official_validation.promotion_requirement.auroc_material_regression_forbidden: "
            "false (secondary diagnostic only), replacing the V1/V2 hard gate",
            "search_budget: new section, d0_d5_max_neural_fits=90, replacing the "
            "unauthoritative 100 convention used in prior evidence",
            "cal_v2_ordering: new section making the already-implied CAL_V2 chronology "
            "machine-explicit",
            "model_v2_final_vs_runtime_acceptance: new section making the already-implied "
            "separation machine-explicit",
        ],
        "unchanged_from_v2": [
            "fixed_scientific_constants",
            "model_seeds",
            "primary_metrics",
            "patient_cluster_bootstrap",
            "architectures (identities and parameter counts)",
            "architecture_search_policy (D1/D2 staged design, 35-fit V2-004 cap)",
            "feature_ablation_contract",
            "hybrid_trigger",
            "loss_and_sampling",
            "optimizer_experiment",
            "official_validation.promotion_requirement's two hard AUPRC criteria "
            "(mean_three_seed_validation_auprc_min=0.646, "
            "paired_patient_cluster_bootstrap_delta_auprc_vs_model_v1_lower_95_ci_bound_min="
            "0.0)",
            "official_validation.release_checkpoint_seed=20260927",
            "calibration_policy",
            "post_freeze_second_look",
            "runtime_acceptance_guardrails",
            "downstream_impact",
        ],
        "change_control": (
            "This lock is never mutated in place. A further correction requires an additive "
            "MODEL_V2_RESEARCH_PROTOCOL_V4 successor with this lock preserved byte-identical "
            "as its predecessor."
        ),
    }
    V3_LOCK_PATH.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(V3_LOCK_PATH))


if __name__ == "__main__":
    main()
