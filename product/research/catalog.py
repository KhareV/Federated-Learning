"""Declarative direct-copy locators for approved frozen research summary facts.

No prediction table, dataset reader, scientific calculation, or training import belongs here.
"""

from __future__ import annotations

from typing import NamedTuple


class FactSpec(NamedTuple):
    fact_id: str
    phase: str
    source: str
    locator: tuple[str | int, ...]
    role: str
    unit: str | None = None


ML = (
    FactSpec(
        "promotion_decision",
        "V2-007",
        "v2_007/promotion_decision.json",
        ("decision",),
        "HISTORICAL_MODEL_PROMOTION",
    ),
    FactSpec(
        "promotion_eligible",
        "V2-007",
        "v2_007/promotion_decision.json",
        ("promotion_eligible",),
        "HISTORICAL_MODEL_PROMOTION",
    ),
    FactSpec(
        "release_ci_lower",
        "V2-007",
        "v2_007/promotion_decision.json",
        ("release_ci", "lower"),
        "HISTORICAL_MODEL_PROMOTION",
        "AUPRC_DELTA",
    ),
    FactSpec(
        "release_ci_upper",
        "V2-007",
        "v2_007/promotion_decision.json",
        ("release_ci", "upper"),
        "HISTORICAL_MODEL_PROMOTION",
        "AUPRC_DELTA",
    ),
    FactSpec(
        "v1_reference_auprc",
        "V2-007",
        "v2_007/historical_reference_metrics.json",
        ("v1_release_seed_auprc",),
        "HISTORICAL_REFERENCE",
        "AUPRC",
    ),
    FactSpec(
        "model_id",
        "V2-008",
        "v2_008/model_v2_final_verification.json",
        ("model_id",),
        "CENTRAL_MODEL_IDENTITY",
    ),
    FactSpec(
        "checkpoint_sha256",
        "V2-008",
        "v2_008/model_v2_final_verification.json",
        ("checkpoint_sha256",),
        "CENTRAL_MODEL_IDENTITY",
    ),
    FactSpec(
        "temperature",
        "V2-009",
        "../artifacts/CAL_V2.json",
        ("temperature",),
        "MIT_BIH_SOURCE_DOMAIN_CALIBRATION",
    ),
    FactSpec(
        "threshold",
        "V2-009",
        "../artifacts/CAL_V2.json",
        ("threshold",),
        "MIT_BIH_SOURCE_DOMAIN_CALIBRATION",
    ),
    FactSpec(
        "calibration_domain",
        "V2-009",
        "../artifacts/CAL_V2.json",
        ("calibration_domain",),
        "MIT_BIH_SOURCE_DOMAIN_CALIBRATION",
    ),
    FactSpec(
        "calibrated_ece",
        "V2-009",
        "v2_009/calibration_metrics.json",
        ("calibrated_ece",),
        "MIT_BIH_SOURCE_DOMAIN_CALIBRATION",
        "ECE",
    ),
    FactSpec(
        "runtime_acceptance",
        "V2-010",
        "v2_010/runtime_acceptance_decision.json",
        ("MODEL_V2_RUNTIME_ACCEPTED",),
        "POST_FREEZE_RUNTIME",
    ),
    FactSpec(
        "internal_test_hard_gate",
        "V2-010",
        "v2_010/runtime_acceptance_decision.json",
        ("internal_test_participates_in_decision",),
        "POST_FREEZE_RUNTIME",
    ),
    FactSpec(
        "internal_test_auprc",
        "V2-010",
        "v2_010/internal_comparison.json",
        ("v2_point_metrics", "AUPRC"),
        "POST_FREEZE_SECOND_LOOK",
        "AUPRC",
    ),
    FactSpec(
        "incart_auprc",
        "V2-010",
        "v2_010/incart_comparison.json",
        ("v2_point_metrics", "AUPRC"),
        "POST_FREEZE_EXTERNAL_DOMAIN",
        "AUPRC",
    ),
    FactSpec(
        "operational_default",
        "V2-REL-001",
        "v2_rel_001/system_v2_release_manifest.json",
        ("operational_default",),
        "LATER_SOFTWARE_RELEASE",
    ),
    FactSpec(
        "known_limitations",
        "V2-REL-001",
        "v2_rel_001/system_v2_release_manifest.json",
        ("known_limitations",),
        "LATER_SOFTWARE_RELEASE",
    ),
    FactSpec(
        "system_release_accepted",
        "V2-REL-001",
        "v2_rel_001/system_v2_release_decision.json",
        ("SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED",),
        "LATER_SOFTWARE_RELEASE",
    ),
)

FL = (
    FactSpec(
        "heldout_threshold_rule",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/final_handoff.md",
        ("line", 16),
        "ONE_SHOT_HELD_OUT_EVALUATION_RULE",
    ),
    FactSpec(
        "iid_best_round",
        "V2-FL-001",
        "v2_fl_001/fl_iid_model_v2_result.json",
        ("best_round",),
        "VALIDATION_SELECTION",
        "ROUND",
    ),
    FactSpec(
        "iid_best_auprc",
        "V2-FL-001",
        "v2_fl_001/fl_iid_model_v2_result.json",
        ("best_validation", "AUPRC"),
        "VALIDATION_SELECTION",
        "AUPRC",
    ),
    FactSpec(
        "iid_initial_auprc",
        "V2-FL-001",
        "v2_fl_001/fl_iid_model_v2_result.json",
        ("round_0_validation", "AUPRC"),
        "VALIDATION_SELECTION",
        "AUPRC",
    ),
    FactSpec(
        "iid_v2_minus_v1_auprc",
        "V2-FL-001",
        "v2_fl_001/v1_vs_v2_iid_comparison.json",
        ("best_AUPRC", "delta_V2_minus_V1"),
        "PAIRED_RESEARCH_COMPARISON",
        "AUPRC_DELTA",
    ),
    FactSpec(
        "iid_v2_minus_v1_auprc_ci_lower",
        "V2-FL-001",
        "v2_fl_001/v1_vs_v2_iid_comparison.json",
        ("paired_bootstrap", "ci95", 0),
        "PAIRED_RESEARCH_COMPARISON",
        "AUPRC_DELTA",
    ),
    FactSpec(
        "iid_v2_minus_v1_auprc_ci_upper",
        "V2-FL-001",
        "v2_fl_001/v1_vs_v2_iid_comparison.json",
        ("paired_bootstrap", "ci95", 1),
        "PAIRED_RESEARCH_COMPARISON",
        "AUPRC_DELTA",
    ),
    *(
        FactSpec(
            f"{condition.lower()}_best_auprc",
            "V2-FL-002",
            "v2_fl_002/results_table.json",
            ("conditions", condition, "best_AUPRC"),
            "SYNTHETIC_PARTITION_VALIDATION",
            "AUPRC",
        )
        for condition in ("IID", "label", "quantity", "feature", "combined")
    ),
    FactSpec(
        "fedprox_mu",
        "V2-FL-003",
        "v2_fl_003/selection_audit.json",
        ("lock_selected_mu",),
        "SELECTED_CONFIGURATION",
    ),
    FactSpec(
        "fedprox_no_general_win",
        "V2-FL-003",
        "v2_fl_003/fedavg_vs_fedprox_comparison.json",
        ("no_claim_that_fedprox_wins",),
        "MIXED_TRANSFER",
    ),
    FactSpec(
        "internal_claim_label",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/internal_test_statistics.json",
        ("claim_label",),
        "ONE_SHOT_HELD_OUT",
    ),
    FactSpec(
        "internal_groups",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/internal_test_statistics.json",
        ("clusters",),
        "ONE_SHOT_HELD_OUT",
        "PATIENT_GROUPS",
    ),
    FactSpec(
        "internal_iid_auprc",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/internal_test_statistics.json",
        ("models", "V2_FEDAVG_IID", "bootstrap_95", "AUPRC", "point_estimate"),
        "ONE_SHOT_HELD_OUT",
        "AUPRC",
    ),
    FactSpec(
        "internal_iid_auprc_ci_lower",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/internal_test_statistics.json",
        ("models", "V2_FEDAVG_IID", "bootstrap_95", "AUPRC", "ci_lower_95"),
        "ONE_SHOT_HELD_OUT",
        "AUPRC",
    ),
    FactSpec(
        "internal_iid_auprc_ci_upper",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/internal_test_statistics.json",
        ("models", "V2_FEDAVG_IID", "bootstrap_95", "AUPRC", "ci_upper_95"),
        "ONE_SHOT_HELD_OUT",
        "AUPRC",
    ),
    FactSpec(
        "incart_claim_label",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/incart_statistics.json",
        ("claim_label",),
        "POST_FREEZE_SECOND_LOOK",
    ),
    FactSpec(
        "incart_iid_auprc",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/incart_statistics.json",
        ("models", "V2_FEDAVG_IID", "bootstrap_95", "AUPRC", "point_estimate"),
        "POST_FREEZE_SECOND_LOOK",
        "AUPRC",
    ),
    FactSpec(
        "incart_iid_auprc_ci_lower",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/incart_statistics.json",
        ("models", "V2_FEDAVG_IID", "bootstrap_95", "AUPRC", "ci_lower_95"),
        "POST_FREEZE_SECOND_LOOK",
        "AUPRC",
    ),
    FactSpec(
        "incart_iid_auprc_ci_upper",
        "V2-FL-EVAL-001",
        "v2_fl_eval_001/incart_statistics.json",
        ("models", "V2_FEDAVG_IID", "bootstrap_95", "AUPRC", "ci_upper_95"),
        "POST_FREEZE_SECOND_LOOK",
        "AUPRC",
    ),
    FactSpec(
        "secagg_max_abs_difference",
        "V2-FL-004",
        "v2_fl_004/aggregate_correctness.json",
        ("MODEL_V2_shaped", "maximum_absolute_difference"),
        "AGGREGATION_INTERFACE_ONLY",
    ),
    FactSpec(
        "plain_clear_updates",
        "V2-FL-004",
        "v2_fl_004/server_visibility_audit.json",
        ("plain_clear_update_count",),
        "AGGREGATION_INTERFACE_ONLY",
        "UPDATES",
    ),
    FactSpec(
        "protected_clear_updates",
        "V2-FL-004",
        "v2_fl_004/server_visibility_audit.json",
        ("protected_clear_update_count",),
        "AGGREGATION_INTERFACE_ONLY",
        "UPDATES",
    ),
    FactSpec(
        "masked_vectors_visible",
        "V2-FL-004",
        "v2_fl_004/server_visibility_audit.json",
        ("protected_interface", "masked_vectors_visible"),
        "AGGREGATION_INTERFACE_ONLY",
        "VECTORS",
    ),
    FactSpec(
        "secagg_overhead_boundary",
        "V2-FL-004",
        "v2_fl_004/overhead_summary.json",
        ("accounting_boundary",),
        "AGGREGATION_PROTOCOL_ONLY",
    ),
    FactSpec(
        "secagg_network_bytes_exact",
        "V2-FL-004",
        "v2_fl_004/overhead_summary.json",
        ("application_payload_bytes", "exact_network_bytes"),
        "AGGREGATION_PROTOCOL_ONLY",
    ),
    FactSpec(
        "secagg_supported_claim",
        "V2-FL-004",
        "v2_fl_004/privacy_claim_audit.json",
        ("supported_claim",),
        "AGGREGATION_INTERFACE_ONLY",
    ),
    FactSpec(
        "secagg_unsupported_claims",
        "V2-FL-004",
        "v2_fl_004/privacy_claim_audit.json",
        ("unsupported_claims",),
        "AGGREGATION_INTERFACE_ONLY",
    ),
)

SCIENTIFIC_FL_PHASES = ("V2-FL-001", "V2-FL-002", "V2-FL-003", "V2-FL-EVAL-001", "V2-FL-004")
