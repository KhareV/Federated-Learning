#!/usr/bin/env python3
"""V2-004: write d2_not_run.json when D1 produced zero qualifiers (no D2 matrix constructed).
Also writes a NOT_EVALUABLE hybrid_trigger.json and a NOT_AVAILABLE best_learned_only.json so
the required report tree is complete even in the negative-result branch."""

from __future__ import annotations

import json

import scripts._v2_004_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_004"


def main() -> None:
    (OUT_DIR / "d2_not_run.json").write_text(
        json.dumps(
            {
                "d2_ran": False,
                "reason": "D1_ZERO_QUALIFIERS",
                "v2_004_outcome": "D1_ZERO_QUALIFIERS",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "hybrid_trigger.json").write_text(
        json.dumps(
            {
                "best_reduced_rf_v1_auprc": 0.713140103147974,
                "threshold": 0.03,
                "comparator": ">=",
                "best_learned_only_mean_auprc": None,
                "gap": None,
                "trigger": None,
                "status": "NOT_EVALUABLE_NEURAL_SEARCH_STOPPED",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "best_learned_only.json").write_text(
        json.dumps(
            {"component_id": "BEST_LEARNED_ONLY_V2_CV_V1", "status": "NOT_AVAILABLE"},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print("d2_not_run.json written")


if __name__ == "__main__":
    main()
