#!/usr/bin/env python3
"""One-command RESEARCH V2 software demo (V2-013). Not the operational default.

    python -m scripts.run_research_v2_demo            # replay once, write demo report, exit
    python -m scripts.run_research_v2_demo --serve    # keep API + built frontend running

Starts API_RUNTIME_V2 (127.0.0.1, ephemeral port), builds the frontend with the research request
model id, serves it with the same proxy as the E2E path, replays the deterministic
WEARABLE_SIM_V2_REPLAY_V1 session through the real stack and prints the open-in-browser URL
(/monitoring?mode=replay&replay=WEARABLE_SIM_V2_REPLAY_V1). The operational default
(`uvicorn api.app:app`, MODEL_V1) is unaffected. Simulated sessions are virtual participants,
not humans; nothing here is a clinical claim.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import scripts._v2_013_lib as lib
import scripts.run_v2_013_replay as rep

REPLAY_ID = rep.REPLAY_ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serve", action="store_true", help="keep serving until interrupted")
    args = parser.parse_args()
    rep.OUT.mkdir(parents=True, exist_ok=True)
    events = rep._events()
    build = rep._build_frontend()
    with lib.launch_api("v2") as (base, pid):
        preview, port = rep._spawn_preview(int(base.rsplit(":", 1)[1]))
        try:
            rows = lib.direct_replay(base, "V2-013-DEMO", events)
            digest = lib.canonical_digest(rows)
            url = f"http://127.0.0.1:{port}/monitoring?mode=replay&replay={REPLAY_ID}"
            report = {
                "demo": "RESEARCH_V2_SOFTWARE_DEMO", "runtime": "API_RUNTIME_V2",
                "operational_default_unchanged": True, "api_base": base, "api_pid": pid,
                "frontend_url": url, "window_count": len(rows),
                "http_status_counts": {str(s): sum(r["http_status"] == s for r in rows)
                                       for s in sorted({r["http_status"] for r in rows})},
                "semantic_digest_sha256": digest["sha256"], "frontend_build": build,
                "claim_boundary": "software demonstration of a recorded simulated session; "
                "not a clinical result, not a real wearable",
            }
            (rep.OUT / "demo_report.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2, sort_keys=True))
            if args.serve:
                print(f"\nServing. Open {url}\nCtrl-C to stop.", flush=True)
                try:
                    while True:
                        time.sleep(3600)
                except KeyboardInterrupt:
                    pass
        finally:
            rep._stop(preview)
    sys.exit(0)


if __name__ == "__main__":
    main()
