#!/usr/bin/env python3
"""C-V2-PRE004-CONTROL: create the additive MODEL_V2_RESEARCH_PROTOCOL_V2 successor.

Carries every V1 field forward BYTE-IDENTICAL except the two verified mismatches between the
actual committed V1 protocol and this checkpoint's authoritative staged design:

1. architecture_search_policy: V1's `all_primary_comparisons_use_all_three_seeds: true` and
   `elimination_after_single_seed_forbidden: true` (45 total fits, no staging) are replaced by
   the staged D1 (15 fits, seed 20260927 only) -> D2 (<=20 additional fits, <=2 advanced
   architectures, remaining 2 seeds) design, max 35 fits.
2. official_validation.promotion_requirement: V1's release_seed_validation_auprc_min
   (0.5628608 = V1 release AUPRC + 0.03) hard gate is replaced by: mean three-seed VALIDATION
   AUPRC > 0.646 AND paired patient-cluster-bootstrap delta-AUPRC-vs-MODEL_V1 lower 95% CI
   bound > 0.

Does not touch MODEL_V2_RESEARCH_PROTOCOL_V1 (never mutated in place, per its own
change_control clause) and does not alter architectures, parameter counts, CV manifests,
feature audit, MODEL_V1_CV_REFERENCE_V1, V2-002/V2-003/D0.6 results, bootstrap unit, CAL_V2
method, or external-evaluation policy.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from nhm.hashing import hash_canonical_json, hash_file

ROOT = Path(__file__).resolve().parents[1]
V1_PATH = ROOT / "configs/model_v2/research_protocol_v1.yaml"
V2_PATH = ROOT / "configs/model_v2/research_protocol_v2.yaml"
V2_DOC_PATH = ROOT / "docs/MODEL_V2_RESEARCH_PROTOCOL_V2.md"
V2_LOCK_PATH = ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json"


def build_v2_config() -> dict:
    v1 = yaml.safe_load(V1_PATH.read_text(encoding="utf-8"))
    v2 = copy.deepcopy(v1)

    v2["protocol_id"] = "MODEL_V2_RESEARCH_PROTOCOL_V2"
    v2["parent_protocol"] = "MODEL_V2_RESEARCH_PROTOCOL_V1"
    v2["owner_task"] = "C-V2-PRE004-CONTROL"
    v2["status"] = "FROZEN_RESEARCH_PROTOCOL"
    v2["change_reason"] = (
        "Pre-V2-004 correction of two verified mismatches between the committed V1 protocol "
        "text and the authoritative staged architecture-search design: (1) V1 required all "
        "three architectures to receive all three seeds before any elimination (45 total "
        "fits, single-seed elimination explicitly forbidden); the authoritative design stages "
        "this as D1 (15 fits, seed 20260927 only) -> D2 (<=20 additional fits for <=2 "
        "D1-advanced architectures, remaining two seeds), max 35 fits. (2) V1's hard D5 "
        "promotion gate was release_seed_validation_auprc_min=0.5628608 (V1 release AUPRC + "
        "0.03), with the classical LR/RF historical VALIDATION AUPRC values marked "
        "interpretation-benchmarks-only (hard_promotion_gates: false); the authoritative rule "
        "requires mean three-seed VALIDATION AUPRC > 0.646 AND a paired patient-cluster-"
        "bootstrap delta-AUPRC-vs-MODEL_V1 lower 95% CI bound > 0. Both mismatches were "
        "confirmed present in the actual committed V1 YAML text (not merely in V2-001 handoff "
        "prose) by C-V2-PRE004-CONTROL's protocol_authority_audit.json. No other field is "
        "changed from V1."
    )

    # --- Mismatch 1: staged D1/D2 architecture search, replacing the flat 45-fit design -----
    policy = v2["architecture_search_policy"]
    policy["superseded_v1_fields"] = {
        "all_primary_comparisons_use_all_three_seeds": True,
        "elimination_after_single_seed_forbidden": True,
        "primary_experiment_fits": {"architectures": 3, "folds": 5, "seeds": 3, "total": 45},
        "note": (
            "These V1 fields required all three architectures to receive all three seeds "
            "before any elimination (45 fits, no staging). Superseded by stage_D1/stage_D2 "
            "below. V1 itself is unmodified; this block documents what changed and why."
        ),
    }
    del policy["all_primary_comparisons_use_all_three_seeds"]
    del policy["elimination_after_single_seed_forbidden"]
    del policy["primary_experiment_fits"]
    policy["stage_D1"] = {
        "architectures": ["MODEL_V2_CAPCTRL", "MODEL_V2_TCN_MEAN", "MODEL_V2_TCN_MEANMAX"],
        "seed": 20260927,
        "folds": 5,
        "total_fits": 15,
        "disqualification_rules": [
            "non_finite_candidate",
            "pooled_OOF_AUROC_below_frozen_V1_CV_reference_mean_AUROC",
            "trainable_parameters_above_120000",
        ],
        "ranking": "pooled_OOF_AUPRC",
        "advancement_rule": (
            "paired_patient_cluster_bootstrap_delta_AUPRC_vs_MODEL_V1_CV_REFERENCE_V1_"
            "lower_95_CI_bound_greater_than_0"
        ),
        "max_advancing": 2,
        "tie_rule": "within_one_bootstrap_se_prefer_simpler_lower_variance",
        "zero_candidates_advance_policy": (
            "STOP_NEURAL_ARCHITECTURE_SEARCH_PER_PROTOCOL -- do not manufacture D2 fits, do "
            "not access official VALIDATION"
        ),
    }
    policy["stage_D2"] = {
        "architectures": "at most 2, exactly the D1-advanced set",
        "seeds": [20260928, 20260929],
        "folds": 5,
        "max_additional_fits": 20,
    }
    policy["maximum_v2_004_fits"] = 35
    policy["candidate_ranking"] = "pooled_OOF_AUPRC_within_each_stage"

    # --- Mismatch 2: D5 promotion rule --------------------------------------------------------
    promotion = v2["official_validation"]["promotion_requirement"]
    promotion["superseded_v1_rule"] = {
        "release_seed_validation_auprc_min": 0.5628607838787021,
        "computation": "0.5328607838787021 (V1 release AUPRC) + 0.03",
        "note": (
            "V1's hard D5 gate. Superseded below. The classical LR/RF historical VALIDATION "
            "AUPRC values (0.645879, 0.799672) were marked interpretation-benchmarks-only in "
            "V1 (hard_promotion_gates: false); V2 makes the LR-derived 0.646 value the actual "
            "hard gate threshold."
        ),
    }
    del promotion["release_seed_validation_auprc_min"]
    del promotion["computation"]
    promotion["mean_three_seed_validation_auprc_min"] = 0.646
    promotion["mean_three_seed_validation_auprc_min_derivation"] = (
        "frozen historical LOGISTIC_BASELINE_V1 VALIDATION AUPRC (0.645879), rounded"
    )
    promotion["paired_patient_cluster_bootstrap_delta_auprc_vs_model_v1_lower_95_ci_bound_min"] = (
        0.0
    )
    promotion["paired_comparison_rule_reused_from"] = "patient_cluster_bootstrap (unchanged)"
    v2["official_validation"]["frozen_classical_references_are_interpretation_benchmarks_only"][
        "hard_promotion_gates"
    ] = (
        "PARTIAL -- LR_AUPRC (rounded to 0.646) is now the hard mean-three-seed-VALIDATION-"
        "AUPRC gate; RF_AUPRC remains interpretation-only"
    )

    return v2


def main() -> None:
    v2 = build_v2_config()
    V2_PATH.write_text(
        yaml.safe_dump(v2, sort_keys=False, default_flow_style=False, width=100), encoding="utf-8"
    )

    doc_lines = [
        "# MODEL_V2_RESEARCH_PROTOCOL_V2",
        "",
        "Additive successor to MODEL_V2_RESEARCH_PROTOCOL_V1, created by C-V2-PRE004-CONTROL "
        "before V2-004 begins. V1 is never mutated in place (see its own `change_control` "
        "clause); this document and `configs/model_v2/research_protocol_v2.yaml` are the only "
        "authoritative sources for the two corrections below. All other V1 content (fixed "
        "scientific constants, architectures and parameter counts, feature ablation contract, "
        "hybrid trigger, loss/sampling rules, optimizer experiment, calibration policy, "
        "post-freeze second look, runtime acceptance guardrails, downstream impact) is carried "
        "forward unchanged.",
        "",
        "## Correction 1: staged architecture search (replaces the flat 45-fit design)",
        "",
        "V1's `architecture_search_policy` required `all_primary_comparisons_use_all_three_"
        "seeds: true` and `elimination_after_single_seed_forbidden: true` -- i.e. all three "
        "architectures receive all three seeds (45 total fits) before any elimination. V2 "
        "replaces this with:",
        "",
        "- **Stage D1**: 3 architectures x 5 folds x seed 20260927 only = 15 fits. "
        "Disqualify any non-finite candidate, any candidate with pooled OOF AUROC below the "
        "frozen MODEL_V1_CV_REFERENCE_V1 mean AUROC, or any candidate with more than 120,000 "
        "trainable parameters. Rank survivors by pooled OOF AUPRC. A candidate advances only "
        "if its paired patient-cluster-bootstrap delta-AUPRC vs MODEL_V1_CV_REFERENCE_V1 has a "
        "lower 95% CI bound greater than 0. At most 2 advance, using the one-bootstrap-SE "
        "simplicity tie rule. If zero candidates advance, the neural architecture search "
        "stops per protocol: no D2 fits are manufactured, official VALIDATION is not accessed.",
        "- **Stage D2**: at most 2 D1-advanced architectures x 5 folds x the remaining two "
        "seeds (20260928, 20260929) = at most 20 additional fits.",
        "- **Maximum V2-004 fits: 35** (15 + 20), never 45.",
        "",
        "## Correction 2: D5 promotion rule (replaces the 0.5628608 hard gate)",
        "",
        "V1's hard D5 gate was `release_seed_validation_auprc_min = 0.5628607838787021` "
        "(V1 release AUPRC 0.5328608 + 0.03), with the historical classical LR/RF VALIDATION "
        "AUPRC values (0.645879, 0.799672) marked interpretation-benchmarks-only "
        "(`hard_promotion_gates: false`). V2's rule instead requires BOTH:",
        "",
        "1. mean three-seed official VALIDATION AUPRC > 0.646 "
        "(the frozen historical LOGISTIC_BASELINE_V1 VALIDATION AUPRC, 0.645879, rounded); and",
        "2. the paired patient-cluster-bootstrap delta-AUPRC vs MODEL_V1 has a lower 95% CI "
        "bound > 0, for the required release-seed / three-seed comparisons.",
        "",
        "`three_seed_confirmation_required` and `auroc_material_regression_forbidden` are "
        "carried forward unchanged from V1.",
        "",
        "## What is unchanged",
        "",
        "Target, split, PREPROC_V1, architecture identities and parameter counts "
        "(MODEL_V2_CAPCTRL=51969, MODEL_V2_TCN_MEAN=57553, MODEL_V2_TCN_MEANMAX=57577, TCN "
        "analytic receptive field=3063), CV manifests, the feature-information audit, "
        "MODEL_V1_CV_REFERENCE_V1, V2-002/V2-003/D0.6 results, the patient-cluster bootstrap "
        "unit and procedure, the CAL_V2 method, and the post-freeze external-evaluation "
        "policy are all carried forward byte-for-byte from V1 and are not altered by this "
        "successor.",
        "",
    ]
    V2_DOC_PATH.write_text("\n".join(doc_lines), encoding="utf-8")

    lock = {
        "protocol_id": "MODEL_V2_RESEARCH_PROTOCOL_V2",
        "parent_protocol": "MODEL_V2_RESEARCH_PROTOCOL_V1",
        "parent_protocol_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
        ),
        "status": "FROZEN_RESEARCH_PROTOCOL",
        "owner_task": "C-V2-PRE004-CONTROL",
        "config_sha256": hash_file(V2_PATH),
        "config_canonical_hash": hash_canonical_json(yaml.safe_load(V2_PATH.read_text())),
        "doc_sha256": hash_file(V2_DOC_PATH),
        "v1_unmodified": True,
        "v1_lock_path": "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json",
        "corrections": [
            "architecture_search_policy: staged D1(15)/D2(<=20)=<=35 fits, replacing the flat "
            "45-fit all-three-seeds design",
            "official_validation.promotion_requirement: mean 3-seed VALIDATION AUPRC > 0.646 "
            "AND paired-bootstrap lower-95%-CI delta-AUPRC-vs-V1 > 0, replacing the "
            "release_seed_validation_auprc_min=0.5628608 hard gate",
        ],
        "unchanged_from_v1": [
            "fixed_scientific_constants",
            "model_seeds",
            "primary_metrics",
            "patient_cluster_bootstrap",
            "architectures (identities and parameter counts)",
            "feature_ablation_contract",
            "hybrid_trigger",
            "loss_and_sampling",
            "optimizer_experiment",
            "calibration_policy",
            "post_freeze_second_look",
            "runtime_acceptance_guardrails",
            "downstream_impact",
        ],
        "change_control": (
            "This lock is never mutated in place. A further correction requires an additive "
            "MODEL_V2_RESEARCH_PROTOCOL_V3 successor with this lock preserved byte-identical "
            "as its predecessor."
        ),
    }
    V2_LOCK_PATH.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(V2_LOCK_PATH))


if __name__ == "__main__":
    main()
