#!/usr/bin/env python3
"""Create the MODEL_V2_OPTIMIZER_CORRECTION_V1 and MODEL_V2_FINALIST_SHORTLIST_V1 component
locks (V2-006), binding every upstream and V2-006-produced artifact that determines the
result. Additive V2 component locks, NOT canonical Fxx freeze registry rows. Run only after
V2G5's full evidence/test gate passes."""

from __future__ import annotations

import json
import subprocess

import scripts._v2_006_lib as lib
from nhm.hashing import hash_file

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_006"
OPT_CORRECTION_LOCK = ROOT / "manifests/model_v2/MODEL_V2_OPTIMIZER_CORRECTION_V1.lock.json"
SHORTLIST_LOCK = ROOT / "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json"


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def main() -> None:
    comparison = json.loads((OUT_DIR / "optimizer_comparison.json").read_text())
    decision = json.loads((OUT_DIR / "adoption_decision.json").read_text())
    shortlist = json.loads((OUT_DIR / "finalist_shortlist.json").read_text())

    opt_lock = {
        "component_id": "MODEL_V2_OPTIMIZER_CORRECTION_V1",
        "status": "FROZEN_OPTIMIZER_CORRECTION",
        "owner_task": "V2-006",
        "not_a_canonical_freeze_row": True,
        "active_protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ),
        "architecture_source_sha256": hash_file(ROOT / "models/model_v2_architectures.py"),
        "training_source_sha256": hash_file(ROOT / "training/train_central.py"),
        "optimizer_correction_config_sha256": hash_file(lib.V2_006_CONFIG_PATH),
        "frozen_training_contract_config_sha256": hash_file(lib.CONFIG_PATH),
        "outer_cv_manifest_sha256": hash_file(lib.OUTER_CV_CSV),
        "inner_cv_manifest_sha256": hash_file(lib.INNER_CV_CSV),
        "v2_004_arch_causality_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json"
        ),
        "bootstrap_draws_sha256_reused_from_v2_002": (
            "e51124bb7675fa2fa175c14194fd6df1f3f218ff85fbd1f8f42fa49deb0d4071"
        ),
        "control_architecture": comparison["control_architecture"],
        "control_schedule_id": comparison["control_schedule_id"],
        "challenger_schedule_id": comparison["challenger_schedule_id"],
        "challenger_oof_predictions_sha256": hash_file(OUT_DIR / "challenger_oof_predictions.csv"),
        "control_mean_AUPRC": comparison["control_mean_AUPRC"],
        "challenger_mean_AUPRC": comparison["challenger_mean_AUPRC"],
        "POINT_DELTA": comparison["POINT_DELTA"],
        "BOOTSTRAP_SE_DELTA": comparison["BOOTSTRAP_SE_DELTA"],
        "control_seed_SD": comparison["control_seed_SD"],
        "challenger_seed_SD": comparison["challenger_seed_SD"],
        "adoption_decision_sha256": hash_file(OUT_DIR / "adoption_decision.json"),
        "decision": decision["decision"],
        "corrected_schedule_adopted": decision["corrected_schedule_adopted"],
        "git_sha": _git_sha(),
        "change_control": (
            "This lock is never mutated in place. A corrected optimizer-experiment result "
            "requires a new, additive MODEL_V2_OPTIMIZER_CORRECTION_V2 successor with this "
            "lock preserved byte-identical as its predecessor."
        ),
    }
    OPT_CORRECTION_LOCK.write_text(
        json.dumps(opt_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    shortlist_lock = {
        "component_id": "MODEL_V2_FINALIST_SHORTLIST_V1",
        "status": "FROZEN_FINALIST_SHORTLIST",
        "owner_task": "V2-006",
        "not_a_canonical_freeze_row": True,
        "not_a_model_v2_final_selection": True,
        "active_protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ),
        "optimizer_correction_lock_sha256": hash_file(OPT_CORRECTION_LOCK),
        "finalist_shortlist_json_sha256": hash_file(OUT_DIR / "finalist_shortlist.json"),
        "shortlist_count": shortlist["shortlist_count"],
        "finalists": shortlist["finalists"],
        "final_inner_manifest_for_v2_007": shortlist["bindings"]["final_inner_manifest_for_v2_007"],
        "seeds_for_v2_007": shortlist["seeds_for_v2_007"],
        "model_v2_final_selected": shortlist["model_v2_final_selected"],
        "git_sha": _git_sha(),
        "change_control": (
            "This lock is never mutated in place. A corrected finalist shortlist requires a "
            "new, additive MODEL_V2_FINALIST_SHORTLIST_V2 successor with this lock preserved "
            "byte-identical as its predecessor."
        ),
    }
    SHORTLIST_LOCK.write_text(
        json.dumps(shortlist_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print("MODEL_V2_OPTIMIZER_CORRECTION_V1:", hash_file(OPT_CORRECTION_LOCK))
    print("MODEL_V2_FINALIST_SHORTLIST_V1:", hash_file(SHORTLIST_LOCK))


if __name__ == "__main__":
    main()
