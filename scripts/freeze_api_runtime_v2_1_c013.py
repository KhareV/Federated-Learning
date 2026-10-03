#!/usr/bin/env python3
"""C-V2-013: API_RUNTIME_V2_1 successor lock. The only bound file that changed relative to
API_RUNTIME_V2 is simulation/stream_runtime_v2013.py (an empty-chunk guard; all V2-013 outputs are
reproduced byte-for-byte). API_RUNTIME_V2 is preserved unchanged. No scientific, API, runtime or
quality semantics change."""

from __future__ import annotations

import json
import sys

from nhm.hashing import hash_file
from scripts._v2_013_lib import ROOT

PRED = ROOT / "artifacts/API_RUNTIME_V2.lock.json"
DEST = ROOT / "artifacts/API_RUNTIME_V2_1.lock.json"
EVID = "reports/model_v2/c_v2_013_quality_flatline"
EXTRA = [
    "simulation/flatline_scenario_c_v2_013.py",
    "scripts/build_wearable_sim_v2_flatline_replay_c013.py",
    "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.json",
    "tests/fixtures/e2e/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.manifest.json",
    f"{EVID}/frozen_contract_audit.json", f"{EVID}/direct_quality_flatline_test.json",
    f"{EVID}/full_pipeline_flatline_reproduction.json",
    f"{EVID}/zero_source_flatline_scenarios.json", f"{EVID}/classification.json",
    f"{EVID}/replay/flatline_replay_summary.json",
    f"{EVID}/replay/replay_semantic_digest.json",
]


def main() -> None:
    summary = json.loads((ROOT / f"{EVID}/replay/flatline_replay_summary.json").read_text())
    if summary["status"] != "PASS":
        sys.exit("C_V2_013_FREEZE_REFUSED")
    predecessor = json.loads(PRED.read_text())
    changed = sorted(p for p, d in predecessor["bound_artifacts"].items()
                     if hash_file(ROOT / p) != d)
    if changed != ["simulation/stream_runtime_v2013.py"]:
        sys.exit(f"C_V2_013_UNEXPECTED_BOUND_FILE_CHANGE:{changed}")
    lock = {k: v for k, v in predecessor.items()
            if k not in ("lock_id", "bound_artifacts", "software_replay")}
    lock |= {
        "lock_id": "API_RUNTIME_V2_1", "predecessor_id": "API_RUNTIME_V2",
        "predecessor_sha256": hash_file(PRED), "checkpoint": "C-V2-013-QUALITY-FLATLINE-AUDIT",
        "status": "FROZEN_RESEARCH_RUNTIME",
        "reason": "empty-chunk guard in the streaming adapter (a short tail chunk could yield no "
                  "resampler output and crash ingest) and an additive true-flatline replay "
                  "scenario; QUALITY_V1/PREPROC_V1/runtime/API/scientific artifacts unchanged",
        "changed_bound_files": changed, "quality_v1_changed": False, "preproc_v1_changed": False,
        "original_v2_013_replay_reproduced_byte_for_byte": True,
        "software_replay": predecessor["software_replay"],
        "flatline_replay": {"replay_id": summary["replay_id"],
                            "window_count": summary["window_count"],
                            "flatline_windows": summary["flatline_windows"],
                            "digest": summary["digest_run_1"],
                            "runs_identical": summary["all_four_digests_identical"]},
        "bound_artifacts": {p: hash_file(ROOT / p)
                            for p in [*predecessor["bound_artifacts"], *EXTRA]},
    }
    DEST.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "artifacts/API_RUNTIME_V2_1.supersedes.json").write_text(json.dumps({
        "successor_id": "API_RUNTIME_V2_1", "predecessor_id": "API_RUNTIME_V2",
        "predecessor_sha256": hash_file(PRED), "predecessor_preserved_unchanged": True,
        "reason": lock["reason"], "checkpoint": lock["checkpoint"]}, indent=2,
        sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(DEST))


if __name__ == "__main__":
    main()
