#!/usr/bin/env python3
"""Create the MODEL_V2_FEATURE_AUDIT_V1 component lock (V2-003), binding every upstream and
V2-003-produced artifact that determines its result. Additive V2 component lock, NOT a
canonical Fxx freeze registry row. Run only after V2G2's full evidence/test gate passes."""

from __future__ import annotations

import json
import subprocess

import scripts._v2_003_lib as lib
from nhm.hashing import hash_file

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_003"
DESTINATION = ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json"


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def main() -> None:
    oof_metrics = json.loads((OUT_DIR / "oof_metrics.json").read_text(encoding="utf-8"))
    closure = json.loads((OUT_DIR / "oof_closure_audit.json").read_text(encoding="utf-8"))
    minimal_subset = json.loads(
        (OUT_DIR / "minimal_adequate_subset.json").read_text(encoding="utf-8")
    )
    best_reduced = json.loads((OUT_DIR / "best_reduced_rf.json").read_text(encoding="utf-8"))
    v1_comparison = json.loads(
        (OUT_DIR / "v1_reference_comparison.json").read_text(encoding="utf-8")
    )
    reproducibility = json.loads((OUT_DIR / "reproducibility.json").read_text(encoding="utf-8"))

    lock = {
        "component_id": "MODEL_V2_FEATURE_AUDIT_V1",
        "status": "FROZEN_FEATURE_AUDIT",
        "owner_task": "V2-003",
        "not_a_canonical_freeze_row": True,
        "new_baseline_v1_artifacts_created": False,
        "hybrid_trigger_status": "PENDING_V2_004",
        "research_protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
        ),
        "outer_cv_manifest_sha256": hash_file(
            ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"
        ),
        "inner_cv_manifest_sha256": hash_file(
            ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
        ),
        "model_v1_cv_reference_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"
        ),
        "baseline_v1_lock_sha256": hash_file(lib.BASELINE_V1_LOCK),
        "feature_schema_sha256": hash_file(lib.FEATURE_SCHEMA_PATH),
        "feature_implementation_sha256": hash_file(ROOT / "features/ecg.py"),
        "baseline_config_sha256": hash_file(ROOT / "configs/baseline_v1.yaml"),
        "v2_003_method_config_sha256": hash_file(lib.V2_003_CONFIG_PATH),
        "oof_predictions_sha256": hash_file(OUT_DIR / "oof_predictions.csv"),
        "oof_metrics_sha256": hash_file(OUT_DIR / "oof_metrics.json"),
        "oof_closure_status": closure["status"],
        "bootstrap_draws_identity_sha256_reused_from_v2_002": (
            "e51124bb7675fa2fa175c14194fd6df1f3f218ff85fbd1f8f42fa49deb0d4071"
        ),
        "paired_variant_bootstrap_summary_sha256": hash_file(
            OUT_DIR / "paired_variant_bootstrap_summary.json"
        ),
        "grouped_permutation_summary_sha256": hash_file(
            OUT_DIR / "grouped_permutation_summary.json"
        ),
        "v1_reference_comparison_sha256": hash_file(OUT_DIR / "v1_reference_comparison.json"),
        "reproducibility_status": reproducibility["status"],
        "three_seed_summary_reference": "MODEL_V1_CV_REFERENCE_V1 (unchanged, not retrained)",
        "per_variant_model_pooled_OOF_AUPRC": {
            key: entry["pooled_OOF_AUPRC"]
            for key, entry in oof_metrics["per_variant_model"].items()
        },
        "minimal_adequate_feature_subset": {
            "component_id": "MODEL_V2_MINIMAL_ADEQUATE_FEATURE_SUBSET_V1",
            "selected_variant": minimal_subset["selected_variant"],
            "selected_feature_count": minimal_subset["selected_feature_count"],
            "selected_RF_AUPRC": minimal_subset["selected_RF_AUPRC"],
        },
        "best_reduced_rf": {
            "component_id": "BEST_REDUCED_RF_V1",
            "selected_variant": best_reduced["selected_variant"],
            "feature_count": best_reduced["feature_count"],
            "AUPRC": best_reduced["AUPRC"],
            "AUROC": best_reduced["AUROC"],
        },
        "v1_reference_comparison_summary": {
            key: entry["delta_AUPRC_point"] for key, entry in v1_comparison["comparisons"].items()
        },
        "git_sha": _git_sha(),
        "change_control": (
            "This lock is never mutated in place. A corrected feature audit requires a new, "
            "additive MODEL_V2_FEATURE_AUDIT_V2 successor with this lock preserved "
            "byte-identical as its predecessor. BASELINE_FEATURES_V1 itself is never mutated."
        ),
    }

    DESTINATION.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(DESTINATION))


if __name__ == "__main__":
    main()
