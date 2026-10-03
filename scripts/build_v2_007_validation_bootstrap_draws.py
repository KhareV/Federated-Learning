#!/usr/bin/env python3
"""V2-007 Section 22: freeze MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1.

Sampling unit: official-VALIDATION participant_group_id (7 source clusters, 7 replicate
slots, sampled WITH replacement, multiplicity preserved -- never converted to a set). B=2000,
RNG=numpy.random.default_rng(20260927). Group identities come only from already-public split
manifests (manifests/splits/MITDB_SPLIT_V1.csv) -- no waveform/label/probability data is
touched, so this can run and be committed strictly BEFORE any V2 or V1 official-VALIDATION
prediction exists.
"""

from __future__ import annotations

import json

import numpy as np

import scripts._v2_007_lib as lib
from nhm.hashing import hash_file

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"
DRAWS_PATH = OUT_DIR / "validation_bootstrap_draws.npz"
MANIFEST_PATH = OUT_DIR / "validation_bootstrap_draws_manifest.json"

BOOTSTRAP_ID = "MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1"
B = 2000
BOOTSTRAP_SEED = 20260927


def build() -> dict:
    groups = lib.official_validation_groups()
    if len(groups) != 7:
        raise RuntimeError(
            f"expected exactly 7 official-VALIDATION patient clusters, got {len(groups)}"
        )

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.integers(0, len(groups), size=(B, len(groups)))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(DRAWS_PATH, draws=draws)
    draws_sha256 = hash_file(DRAWS_PATH)

    manifest = {
        "bootstrap_id": BOOTSTRAP_ID,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "rng": "numpy.random.default_rng",
        "replicates": B,
        "slots_per_replicate": len(groups),
        "sampling": "WITH_REPLACEMENT_MULTIPLICITY_PRESERVED_NO_REDRAW",
        "sorted_patient_index_mapping": groups,
        "interval": {
            "method": "percentile_linear",
            "lower_quantile": 0.025,
            "upper_quantile": 0.975,
        },
        "degenerate_draw_policy": "RECORD_AS_NAN_NO_REDRAW",
        "draws_npz_sha256": draws_sha256,
        "draws_shape": list(draws.shape),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, indent=2))
