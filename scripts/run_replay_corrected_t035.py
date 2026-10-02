#!/usr/bin/env python3
"""T035-REPRO corrected replay runner.

Identical mechanics to scripts/run_replay_corrected_c032.py (reused directly via the shared
scripts/run_replay.py helpers, not duplicated) except the upstream-lock verification checks the
latest successors (API_RUNTIME_V1_1, DASHBOARD_UI_V1_3). scripts/run_replay.py and
scripts/run_replay_corrected_c032.py are both left byte-identical; output is written under
reports/t035/ so no C032/C034/T034 evidence is overwritten.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

from scripts.run_replay import (
    _free_port,
    _production_server,
    _public_requests,
    _semantic_digest,
    _send,
    _sim_requests,
    _write_jsonl,
)
from scripts.verify_api_runtime_v1_1_c032 import verify as verify_api_runtime_v1_1
from scripts.verify_dashboard_ui_v1_3_t035 import verify as verify_dashboard_ui_v1_3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/t035"


def _verify_upstream_locks() -> None:
    verify_api_runtime_v1_1()
    verify_dashboard_ui_v1_3()


def run_once(run_label: str, *, speed: float) -> dict[str, Any]:
    _verify_upstream_locks()
    port = _free_port()
    with _production_server(port) as base_url, httpx.Client(timeout=30.0) as client:
        public_requests = _public_requests(f"T035-PUBLIC-REPLAY-CORRECTED-{run_label}")
        public_req_rows, public_resp_rows, public_proj_rows = _send(
            client, base_url, public_requests, speed=speed
        )

        sim_requests = _sim_requests(f"T035-SIM-REPLAY-CORRECTED-{run_label}")
        sim_req_rows, sim_resp_rows, sim_proj_rows = _send(
            client, base_url, sim_requests, speed=speed
        )

    OUT.mkdir(parents=True, exist_ok=True)
    _write_jsonl(OUT / f"{run_label}_public_requests.jsonl", public_req_rows)
    _write_jsonl(OUT / f"{run_label}_public_responses.jsonl", public_resp_rows)
    _write_jsonl(OUT / f"{run_label}_public_dashboard_projection.jsonl", public_proj_rows)
    _write_jsonl(OUT / f"{run_label}_sim_requests.jsonl", sim_req_rows)
    _write_jsonl(OUT / f"{run_label}_sim_responses.jsonl", sim_resp_rows)
    _write_jsonl(OUT / f"{run_label}_sim_dashboard_projection.jsonl", sim_proj_rows)

    result = {
        "run_label": run_label,
        "api_runtime_lock_id": "API_RUNTIME_V1_1",
        "dashboard_ui_lock_id": "DASHBOARD_UI_V1_3",
        "public_requests_sent": len(public_req_rows),
        "public_200": sum(1 for r in public_resp_rows if r.get("http_status") == 200),
        "public_422": sum(1 for r in public_resp_rows if r.get("http_status") == 422),
        "public_500": sum(1 for r in public_resp_rows if r.get("http_status") == 500),
        "sim_requests_sent": len(sim_req_rows),
        "sim_200": sum(1 for r in sim_resp_rows if r.get("http_status") == 200),
        "sim_422": sum(1 for r in sim_resp_rows if r.get("http_status") == 422),
        "public_semantic_digest": _semantic_digest(public_resp_rows),
        "sim_semantic_digest": _semantic_digest(sim_resp_rows),
        "public_monitoring_state_sequence": [
            r.get("monitoring_state") for r in public_resp_rows
        ],
        "status": "PASS",
    }
    (OUT / f"{run_label}.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


ACTIVE_PUBLIC_SEMANTIC_DIGEST = (
    "128fa6d60fab9d9136a6f99f057332c4b6fc2bd16d6ae9e991f60faeb41f30ab"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.0)
    args = parser.parse_args()

    run_1 = run_once("t035_replay_run_1", speed=args.speed)
    run_2 = run_once("t035_replay_run_2", speed=args.speed)

    reproducibility = {
        "run_1_public_semantic_digest": run_1["public_semantic_digest"],
        "run_2_public_semantic_digest": run_2["public_semantic_digest"],
        "run_1_sim_semantic_digest": run_1["sim_semantic_digest"],
        "run_2_sim_semantic_digest": run_2["sim_semantic_digest"],
        "run_1_equals_run_2": (
            run_1["public_semantic_digest"] == run_2["public_semantic_digest"]
            and run_1["sim_semantic_digest"] == run_2["sim_semantic_digest"]
        ),
        "active_e2e_replay_software_v1_2_public_semantic_digest": ACTIVE_PUBLIC_SEMANTIC_DIGEST,
        "matches_active_lock_digest": (
            run_1["public_semantic_digest"] == ACTIVE_PUBLIC_SEMANTIC_DIGEST
        ),
        "status": "PASS",
    }
    if not reproducibility["run_1_equals_run_2"]:
        reproducibility["status"] = "FAIL"
        raise RuntimeError("T035_REPLAY_NOT_REPRODUCIBLE")
    if not reproducibility["matches_active_lock_digest"]:
        reproducibility["status"] = "FAIL"
        raise RuntimeError("T035_REPLAY_DIGEST_MISMATCH_WITH_ACTIVE_LOCK")

    (OUT / "t035_replay_reproducibility.json").write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(reproducibility, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
