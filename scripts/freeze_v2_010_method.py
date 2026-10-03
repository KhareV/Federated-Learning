#!/usr/bin/env python3
"""V2-010 method freeze: arm all THREE independent one-shot second-look guards
(V2_INTERNAL_TEST_SECOND_LOOK, V2_INCART_SECOND_LOOK, V2_NSTDB_SECOND_LOOK) BEFORE any
INTERNAL_TEST/INCART/NSTDB access, binding every upstream identity this phase depends on. No
waveform access, no neural fit, no comparative metric computed here.
"""

from __future__ import annotations

import csv
import json

import scripts._v2_010_lib as lib
from nhm.model_v2_second_look_guard import DATASETS, arm_guard

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_010"


def _historical_population_expectations() -> dict:
    """Mechanically re-derive (never hard-code) the historical population counts this phase's
    closure audits depend on, from frozen V1 artifacts only -- no V2 access."""
    with (ROOT / "reports/internal_test_predictions.csv").open(newline="") as handle:
        internal_rows = list(csv.DictReader(handle))
    with (ROOT / "manifests/splits/MITDB_SPLIT_V1.csv").open(newline="") as handle:
        split_rows = list(csv.DictReader(handle))
    with (ROOT / "reports/external_incart_predictions.csv").open(newline="") as handle:
        incart_rows = list(csv.DictReader(handle))
    with (ROOT / "reports/t019/nstdb_predictions.csv").open(newline="") as handle:
        nstdb_rows = list(csv.DictReader(handle))

    internal_frozen_groups = sorted(
        {row["participant_group_id"] for row in split_rows if row["partition"] == "INTERNAL_TEST"}
    )
    internal_contributing_groups = sorted({row["participant_group_id"] for row in internal_rows})

    return {
        "INTERNAL_TEST": {
            "frozen_group_count": len(internal_frozen_groups),
            "contributing_group_count": len(internal_contributing_groups),
            "eligible_windows": len(internal_rows),
            "positive_windows": sum(1 for row in internal_rows if row["label"] == "1"),
            "negative_windows": sum(1 for row in internal_rows if row["label"] == "0"),
        },
        "INCART": {
            "record_count": len({row["record_id"] for row in incart_rows}),
            "patient_cluster_count": len({row["participant_group_id"] for row in incart_rows}),
            "eligible_windows": len(incart_rows),
        },
        "NSTDB": {
            "base_record_ids": sorted({row["base_record_id"] for row in nstdb_rows}),
            "snr_levels": sorted({int(row["snr_db"]) for row in nstdb_rows}, reverse=True),
            "pair_id_count": len({row["pair_id"] for row in nstdb_rows}),
            "prediction_row_count": len(nstdb_rows),
        },
        "matches_phase_prompt_expectations": {
            "internal_test": (
                len(internal_frozen_groups) == 7
                and len(internal_contributing_groups) == 6
                and len(internal_rows) == 2157
                and sum(1 for row in internal_rows if row["label"] == "1") == 1156
                and sum(1 for row in internal_rows if row["label"] == "0") == 1001
            ),
            "incart": (
                len({row["record_id"] for row in incart_rows}) == 75
                and len({row["participant_group_id"] for row in incart_rows}) == 32
                and len(incart_rows) == 26864
            ),
            "nstdb": (
                sorted({row["base_record_id"] for row in nstdb_rows}) == ["118", "119"]
                and sorted({int(row["snr_db"]) for row in nstdb_rows}, reverse=True)
                == [24, 18, 12, 6, 0, -6]
                and len({row["pair_id"] for row in nstdb_rows}) == 720
                and len(nstdb_rows) == 4320
            ),
        },
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    population = _historical_population_expectations()
    if not all(population["matches_phase_prompt_expectations"].values()):
        raise RuntimeError("V2_010_HISTORICAL_POPULATION_EXPECTATION_MISMATCH")

    method_freeze = {
        "owner_task": "V2-010",
        "historical_population_expectations": population,
        "datasets": {},
    }
    for dataset in DATASETS:
        preconditions = lib.observed_preconditions(ROOT, dataset)
        guard_state = arm_guard(ROOT, dataset, preconditions=preconditions)
        method_freeze["datasets"][dataset] = {
            "guard_armed": guard_state["state"] == "ARMED",
            "preconditions": preconditions,
            "second_look_result_exists_at_method_commit": False,
        }
    method_freeze["status"] = "PASS"
    (OUT_DIR / "method_freeze.json").write_text(
        json.dumps(method_freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("V2-010 method freeze complete: all three second-look guards ARMED.")


if __name__ == "__main__":
    main()
