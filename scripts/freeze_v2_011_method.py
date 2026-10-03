#!/usr/bin/env python3
"""V2-011 method + case freeze (run BEFORE METHOD_COMMIT). Generates the four-case manifest from
the frozen V2-010 INTERNAL_TEST prediction table only, audits the C031 noise protocol binding,
writes the TRAIN-defined HR-bin provenance, and arms the two one-shot guards. No waveform
access, no IG, no V2 noise-type output.
"""

from __future__ import annotations

import json

import scripts._v2_011_analysis as analysis
import scripts._v2_011_cases as cases
from nhm.hashing import hash_file
from nhm.model_v2_explainability_guard import GUARDS, arm_guard

ROOT = cases.ROOT
OUT = cases.OUT


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, counts = cases.build_case_manifest_rows(ROOT)
    cases.write_csv(cases.CASE_MANIFEST_PATH, manifest, cases.MANIFEST_FIELDS)
    cases.write_json(
        OUT / "case_selection_audit.json",
        {
            "source_table": "reports/model_v2/v2_010/internal_v2_predictions.csv",
            "source_table_sha256": hash_file(cases.PREDICTIONS_PATH),
            "candidate_counts": counts,
            "selected_ids": {m["case_type"]: m["example_id"] for m in manifest},
            "selection_rules": cases.SELECTION_RULES,
            "tie_rule": cases.TIE_RULE,
            "manual_selection": False,
            "model_rerun_for_selection": False,
            "waveform_access_for_selection": False,
            "case_manifest_sha256": hash_file(cases.CASE_MANIFEST_PATH),
            "status": "PASS",
        },
    )
    protocol = analysis.verify_noise_protocol(ROOT)
    cases.write_json(OUT / "noise_type_protocol_audit.json", protocol)
    if protocol["status"] != "PASS":
        raise RuntimeError("V2_011_C031_NOISE_PROTOCOL_NOT_REPRODUCIBLE")

    config = analysis.load_error_config(ROOT)["heart_rate_slice"]
    frozen = json.loads((ROOT / "reports/t031/hr_bins.json").read_text())
    cases.write_json(
        OUT / "hr_bins.json",
        {
            "id": "HR_ANALYSIS_BINS_V1_REUSED_BY_V2_011",
            "source": "reports/t031/hr_bins.json",
            "source_sha256": hash_file(ROOT / "reports/t031/hr_bins.json"),
            "derivation_partition": frozen["derivation_partition"],
            "Q1_bpm": frozen["Q1_bpm"],
            "Q2_bpm": frozen["Q2_bpm"],
            "Q3_bpm": frozen["Q3_bpm"],
            "recomputed_from_internal_incart_or_v2_predictions": False,
            "config_matches_frozen_source": (config["Q1_bpm"], config["Q2_bpm"], config["Q3_bpm"])
            == (frozen["Q1_bpm"], frozen["Q2_bpm"], frozen["Q3_bpm"]),
        },
    )

    guard_states = {}
    for guard in GUARDS:
        state = arm_guard(ROOT, guard, preconditions=cases.observed_preconditions(ROOT, guard))
        guard_states[guard] = state["state"]

    cases.write_json(
        OUT / "method_freeze.json",
        {
            "owner_task": "V2-011",
            "method_artifact_sha256": {p: hash_file(ROOT / p) for p in cases.METHOD_PATHS},
            "case_ids": {m["case_type"]: m["example_id"] for m in manifest},
            "case_manifest_sha256": hash_file(cases.CASE_MANIFEST_PATH),
            "guards": guard_states,
            "real_ig_result_exists": (OUT / "cases").exists(),
            "v2_noise_type_result_exists": (OUT / "noise_type_v2_predictions.csv").exists(),
            "status": "PASS",
        },
    )
    print("V2-011 method + case freeze complete")


if __name__ == "__main__":
    main()
