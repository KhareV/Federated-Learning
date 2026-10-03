#!/usr/bin/env python3
"""C-V2-013 revalidation: replay the additive WEARABLE_SIM_V2_REPLAY_V2_FLATLINE bundle twice from
fresh processes through the real API_RUNTIME_V2 and the real built frontend (same orchestrator and
digest function as V2-013), and assert the flatline windows return HTTP 422 / RECHECK_SENSOR with no
model inference. The original V2-013 replay evidence is not touched (separate output directory)."""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/c_v2_013_quality_flatline/replay"
OUT_DIR.mkdir(parents=True, exist_ok=True)
os.environ["V2_013_OUT"] = str(OUT_DIR)  # must precede importing the shared lib

import scripts._v2_013_lib as lib  # noqa: E402
import scripts.run_v2_013_replay as rep  # noqa: E402
import simulation.flatline_scenario_c_v2_013 as scen  # noqa: E402

REPLAY_ID = "WEARABLE_SIM_V2_REPLAY_V2_FLATLINE"


def main() -> None:
    rep.REPLAY_ID = REPLAY_ID
    rep.BUNDLE = ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.json"
    rep.prof = types.SimpleNamespace(  # live/accelerated invariance on a flatline excerpt
        LIVE_EXCERPT_PROFILE=scen.EXCERPT_FLATLINE_PROFILE,
        iter_observed_records=scen.iter_flatline_records)
    try:
        rep.main()
    except SystemExit as exit_info:
        print("replay orchestrator exit:", exit_info)
    digest = json.loads((OUT_DIR / "replay_semantic_digest.json").read_text())
    rows = [json.loads(line) for line in (OUT_DIR / "replay_run_1.jsonl").read_text().splitlines()]
    flat_ids = set(json.loads((ROOT / "tests/fixtures/e2e/"
                               "WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.manifest.json"
                               ).read_text())["flatline_window_ids"])
    flat_rows = [r for r in rows if r["window_id"] in flat_ids]
    summary = {
        "replay_id": REPLAY_ID, "window_count": len(rows),
        "flatline_windows": len(flat_rows),
        "flatline_windows_http_422": sum(r["http_status"] == 422 for r in flat_rows),
        "flatline_error_type": sorted({(r["error"] or {}).get("error_type") for r in flat_rows}),
        "flatline_windows_request_quality": sorted({r["request_ecg_quality"] for r in flat_rows}),
        "model_inference_suppressed": all(r["response"] is None for r in flat_rows),
        "all_four_digests_identical": digest["all_four_identical"],
        "digest_run_1": digest["digests"]["run_1_frontend_path"],
        "digest_run_2": digest["digests"]["run_2_frontend_path"],
        "http_status_counts": digest["http_status_counts"],
        "live_speed_equals_accelerated": json.loads(
            (OUT_DIR / "replay_mode_invariance.json").read_text())["semantic_outputs_identical"],
        "original_v2_013_digest_not_expected_to_match": True,
    }
    summary["status"] = "PASS" if (
        summary["flatline_windows"] >= 1
        and summary["flatline_windows_http_422"] == summary["flatline_windows"]
        and summary["model_inference_suppressed"] and summary["all_four_digests_identical"]
        and summary["live_speed_equals_accelerated"]
        and digest["status"] == "PASS") else "FAIL"
    (OUT_DIR / "flatline_replay_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    if summary["status"] != "PASS":
        sys.exit("C_V2_013_FLATLINE_REPLAY_FAILED")
    assert lib


if __name__ == "__main__":
    main()
