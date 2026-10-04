#!/usr/bin/env python3
"""V2-014: run the repository-native V2-013 software replay (WEARABLE_SIM_V2_REPLAY_V1) or the
additive C-V2-013 exact-zero flatline replay with ALL outputs redirected to an EXTERNAL directory
(V2_013_OUT), so a verification clone is never written to. Same orchestrator, same digest function.

Usage: python -m scripts.run_v2_014_replay {v2013|flatline} <external_output_dir>
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    mode, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    os.environ["V2_013_OUT"] = str(out)  # must precede importing the shared lib
    import scripts.run_v2_013_replay as rep

    if mode == "flatline":
        import simulation.flatline_scenario_c_v2_013 as scen

        rep.REPLAY_ID = "WEARABLE_SIM_V2_REPLAY_V2_FLATLINE"
        rep.BUNDLE = ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.json"
        rep.prof = types.SimpleNamespace(
            LIVE_EXCERPT_PROFILE=scen.EXCERPT_FLATLINE_PROFILE,
            iter_observed_records=scen.iter_flatline_records)
    elif mode != "v2013":
        raise SystemExit("mode must be v2013 or flatline")
    try:
        rep.main()
    except SystemExit as exit_info:
        print("replay orchestrator exit:", exit_info)


if __name__ == "__main__":
    main()
