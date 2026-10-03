#!/usr/bin/env python3
"""Create the MODEL_V2_ARCH_CAUSALITY_V1 component lock (V2-004), binding every upstream and
V2-004-produced artifact that determines its result. Additive V2 component lock, NOT a
canonical Fxx freeze registry row. Run only after V2G3's full evidence/test gate passes."""

from __future__ import annotations

import json
import subprocess

import scripts._v2_004_lib as lib
from nhm.hashing import hash_file

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_004"
DESTINATION = ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json"


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def main() -> None:
    d1_decision = json.loads((OUT_DIR / "d1_decision.json").read_text())
    d2_decision = json.loads((OUT_DIR / "d2_stability_decision.json").read_text())
    hybrid = json.loads((OUT_DIR / "hybrid_trigger.json").read_text())
    best_learned_only = json.loads((OUT_DIR / "best_learned_only.json").read_text())

    lock = {
        "component_id": "MODEL_V2_ARCH_CAUSALITY_V1",
        "status": "FROZEN_ARCH_CAUSALITY",
        "owner_task": "V2-004",
        "not_a_canonical_freeze_row": True,
        "active_protocol_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json"
        ),
        "architecture_source_sha256": hash_file(ROOT / "models/model_v2_architectures.py"),
        "training_source_sha256": hash_file(ROOT / "training/train_central.py"),
        "v2_004_config_sha256": hash_file(lib.V2_CONFIG_PATH),
        "outer_cv_manifest_sha256": hash_file(lib.OUTER_CV_CSV),
        "inner_cv_manifest_sha256": hash_file(lib.INNER_CV_CSV),
        "model_v1_cv_reference_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json"
        ),
        "bootstrap_draws_sha256_reused_from_v2_002": (
            "e51124bb7675fa2fa175c14194fd6df1f3f218ff85fbd1f8f42fa49deb0d4071"
        ),
        "d1_oof_predictions_sha256": hash_file(OUT_DIR / "d1_oof_predictions.csv"),
        "d1_decision_sha256": hash_file(OUT_DIR / "d1_decision.json"),
        "d1_point_metrics": {arch: entry for arch, entry in d1_decision["point_metrics"].items()},
        "d1_causal_hypotheses": d1_decision["causal_hypotheses"],
        "d1_qualified": d1_decision["qualified"],
        "d1_d2_advancement_list": d1_decision["one_se_rule"]["d2_advancement_list"],
        "d2_ran": True,
        "d2_oof_predictions_sha256": hash_file(OUT_DIR / "d2_oof_predictions.csv"),
        "d2_stability_decision_sha256": hash_file(OUT_DIR / "d2_stability_decision.json"),
        "d2_survivors": d2_decision["survivors"],
        "d2_outcome": d2_decision["v2_004_outcome"],
        "best_learned_only_sha256": hash_file(OUT_DIR / "best_learned_only.json"),
        "best_learned_only_architecture_id": best_learned_only.get("architecture_id"),
        "hybrid_trigger_sha256": hash_file(OUT_DIR / "hybrid_trigger.json"),
        "hybrid_trigger_status": hybrid["status"],
        "git_sha": _git_sha(),
        "change_control": (
            "This lock is never mutated in place. A corrected architecture-causality result "
            "requires a new, additive MODEL_V2_ARCH_CAUSALITY_V2 successor with this lock "
            "preserved byte-identical as its predecessor."
        ),
    }

    DESTINATION.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(DESTINATION))


if __name__ == "__main__":
    main()
