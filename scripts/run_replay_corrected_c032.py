#!/usr/bin/env python3
"""C032-NORM-RUNTIME corrected replay runner.

Re-runs the exact same real-HTTP production replay mechanics as scripts/run_replay.py (T034) --
same request builders, same server bring-up, same per-request logging -- against the NOW-
CORRECTED production app (api.app.app, built on the fixed ProductionRuntime that applies
PREPROC_V1 PER_WINDOW_ZSCORE_V1 normalization before MODEL_V1/gateway inference).

scripts/run_replay.py itself is left byte-identical (it remains correctly bound by the
preserved E2E_REPLAY_SOFTWARE_V1_1 lock); this script only swaps the upstream-lock
verification step to check the new successors (API_RUNTIME_V1_1, DASHBOARD_UI_V1_2) and
writes its output under reports/c032_norm_runtime/ instead of reports/t034/, so no C034/T034
evidence is overwritten.
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
from scripts.verify_dashboard_ui_v1_2_c032 import verify as verify_dashboard_ui_v1_2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/c032_norm_runtime"


def _verify_upstream_locks() -> None:
    verify_api_runtime_v1_1()
    verify_dashboard_ui_v1_2()


def run_once(run_label: str, *, speed: float) -> dict[str, Any]:
    _verify_upstream_locks()
    port = _free_port()
    with _production_server(port) as base_url, httpx.Client(timeout=30.0) as client:
        # Unique session_id per run_label: both runs execute in the SAME python process (the
        # production `api.app.app` singleton and its in-memory session store are imported
        # once), so reusing one session_id across determinism-check runs would spuriously
        # trip the monotonic-timestamp guard on the second run. session_id never appears in
        # the response rows the semantic digest is computed over, so this does not affect
        # comparability of run_1 vs run_2 digests.
        public_requests = _public_requests(f"C032-PUBLIC-REPLAY-CORRECTED-{run_label}")
        public_req_rows, public_resp_rows, public_proj_rows = _send(
            client, base_url, public_requests, speed=speed
        )

        sim_requests = _sim_requests(f"C032-SIM-REPLAY-CORRECTED-{run_label}")
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
        "dashboard_ui_lock_id": "DASHBOARD_UI_V1_2",
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


SUPERSEDED_UNNORMALIZED_RUNTIME_DIGEST = (
    "e3f8607617d3fc7cce7be58752340047d120815653cce36acfac5e8b8bc099b3"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.0)
    args = parser.parse_args()

    run_1 = run_once("corrected_replay_run_1", speed=args.speed)
    run_2 = run_once("corrected_replay_run_2", speed=args.speed)

    reproducibility = {
        "run_1_public_semantic_digest": run_1["public_semantic_digest"],
        "run_2_public_semantic_digest": run_2["public_semantic_digest"],
        "run_1_sim_semantic_digest": run_1["sim_semantic_digest"],
        "run_2_sim_semantic_digest": run_2["sim_semantic_digest"],
        "run_1_equals_run_2": (
            run_1["public_semantic_digest"] == run_2["public_semantic_digest"]
            and run_1["sim_semantic_digest"] == run_2["sim_semantic_digest"]
        ),
        "superseded_unnormalized_runtime_digest": SUPERSEDED_UNNORMALIZED_RUNTIME_DIGEST,
        "corrected_digest_differs_from_superseded_digest": (
            run_1["public_semantic_digest"] != SUPERSEDED_UNNORMALIZED_RUNTIME_DIGEST
        ),
        "status": "PASS",
    }
    if not reproducibility["run_1_equals_run_2"]:
        reproducibility["status"] = "FAIL"
        raise RuntimeError("CORRECTED_REPLAY_NOT_REPRODUCIBLE")

    (OUT / "corrected_replay_reproducibility.json").write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(reproducibility, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
