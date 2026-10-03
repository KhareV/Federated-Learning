#!/usr/bin/env python3
"""Create the MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1, MODEL_V2_OFFICIAL_VALIDATION_V1, and
MODEL_V2_VALIDATION_DECISION_V1 component locks (V2-007), binding every upstream and
V2-007-produced artifact that determines the result. Additive V2 component locks, NOT
canonical Fxx freeze registry rows. Packaging-only: serializes/hashes already-frozen results,
performs no new scientific computation. Run only after the full V2-007 evidence/test gate
passes.
"""

from __future__ import annotations

import json
import subprocess

import scripts._v2_007_lib as lib
from nhm.hashing import hash_file

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_007"

DRAWS_LOCK = ROOT / "manifests/model_v2/MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1.lock.json"
OFFICIAL_VALIDATION_LOCK = ROOT / "manifests/model_v2/MODEL_V2_OFFICIAL_VALIDATION_V1.lock.json"
DECISION_LOCK = ROOT / "manifests/model_v2/MODEL_V2_VALIDATION_DECISION_V1.lock.json"


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def main() -> None:
    draws_manifest = json.loads(
        (OUT_DIR / "validation_bootstrap_draws_manifest.json").read_text(encoding="utf-8")
    )
    selection = json.loads((OUT_DIR / "finalist_selection.json").read_text(encoding="utf-8"))
    promotion = json.loads((OUT_DIR / "promotion_decision.json").read_text(encoding="utf-8"))
    access_audit = json.loads(
        (OUT_DIR / "official_validation_access_audit.json").read_text(encoding="utf-8")
    )

    draws_lock = {
        "component_id": "MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1",
        "status": "FROZEN_BOOTSTRAP_DRAWS",
        "owner_task": "V2-007",
        "not_a_canonical_freeze_row": True,
        "bootstrap_seed": draws_manifest["bootstrap_seed"],
        "replicates": draws_manifest["replicates"],
        "slots_per_replicate": draws_manifest["slots_per_replicate"],
        "sorted_patient_index_mapping": draws_manifest["sorted_patient_index_mapping"],
        "draws_npz_sha256": draws_manifest["draws_npz_sha256"],
        "frozen_before_any_official_validation_prediction": True,
        "git_sha": _git_sha(),
        "change_control": (
            "This lock is never mutated in place. A corrected bootstrap-draw definition "
            "requires a new, additive MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V2 successor."
        ),
    }
    DRAWS_LOCK.write_text(json.dumps(draws_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    official_validation_lock = {
        "component_id": "MODEL_V2_OFFICIAL_VALIDATION_V1",
        "status": "FROZEN_OFFICIAL_VALIDATION_RESULT",
        "owner_task": "V2-007",
        "not_a_canonical_freeze_row": True,
        "not_a_model_v2_final_selection": True,
        "active_protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ),
        "shortlist_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json"
        ),
        "final_inner_manifest_sha256": hash_file(lib.FINAL_INNER_CSV),
        "bootstrap_draws_lock_sha256": hash_file(DRAWS_LOCK),
        "official_validation_predictions_sha256": hash_file(
            OUT_DIR / "official_validation_predictions.csv"
        ),
        "v1_reference_predictions_sha256": hash_file(
            OUT_DIR / "v1_reference_validation_predictions.csv"
        ),
        "v2_prediction_rows": access_audit["v2_prediction_rows"],
        "v1_prediction_rows": access_audit["v1_prediction_rows"],
        "session_count": access_audit["session_count"],
        "git_sha": _git_sha(),
        "change_control": (
            "This lock is never mutated in place. Official VALIDATION was consumed exactly "
            "once for MODEL_V2; no successor may re-access it. A corrected downstream "
            "analysis requires a new, additive MODEL_V2_OFFICIAL_VALIDATION_V2 successor "
            "bound to the same frozen predictions, never a re-score."
        ),
    }
    OFFICIAL_VALIDATION_LOCK.write_text(
        json.dumps(official_validation_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    decision_lock = {
        "component_id": "MODEL_V2_VALIDATION_DECISION_V1",
        "status": "FROZEN_VALIDATION_DECISION",
        "owner_task": "V2-007",
        "not_a_canonical_freeze_row": True,
        "not_a_model_v2_final_freeze": True,
        "official_validation_lock_sha256": hash_file(OFFICIAL_VALIDATION_LOCK),
        "selected_finalist": selection["selected_finalist"],
        "selected_architecture_id": selection["selected_architecture_id"],
        "selected_schedule_id": selection["selected_schedule_id"],
        "selected_three_seed_mean_auprc": selection["selected_three_seed_mean_auprc"],
        "release_seed": promotion["release_seed"],
        "promotion_decision": promotion["decision"],
        "promotion_eligible": promotion["promotion_eligible"],
        "finalist_selection_sha256": hash_file(OUT_DIR / "finalist_selection.json"),
        "promotion_decision_sha256": hash_file(OUT_DIR / "promotion_decision.json"),
        "git_sha": _git_sha(),
        "change_control": (
            "This lock is never mutated in place. A corrected validation decision requires "
            "a new, additive MODEL_V2_VALIDATION_DECISION_V2 successor with this lock "
            "preserved byte-identical as its predecessor. V2-008 owns any MODEL_V2_FINAL "
            "freeze/disposition decision; this lock makes no such freeze."
        ),
    }
    DECISION_LOCK.write_text(
        json.dumps(decision_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print("MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1:", hash_file(DRAWS_LOCK))
    print("MODEL_V2_OFFICIAL_VALIDATION_V1:", hash_file(OFFICIAL_VALIDATION_LOCK))
    print("MODEL_V2_VALIDATION_DECISION_V1:", hash_file(DECISION_LOCK))


if __name__ == "__main__":
    main()
