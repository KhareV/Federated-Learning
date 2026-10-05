"""CAP-009 canonical real-browser history/research E2E; offline DEMO, real V1_3 + V2 runtime.

Execute only after CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1 method/UI freeze.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from product.contracts import load_contract
from scripts.run_capstone_frontend_e2e import chrome, preview_server
from scripts.run_capstone_monitoring_e2e import launch_released_inference
from scripts.run_capstone_persistent_e2e import free_port

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OUT = ROOT / "reports/capstone/cap_009"
ACK = load_contract("auth_policy")["demo_provider"]["acknowledgement_value"]


def save(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


@contextlib.contextmanager
def product_v13(root: Path, inference_url: str) -> Iterator[tuple[str, int]]:
    root.mkdir(parents=True, exist_ok=True)
    port = free_port()
    env = {
        **os.environ,
        "PYTHONPATH": "src:.",
        "NHM_PRODUCT_AUTH_MODE": "DEMO",
        "NHM_PRODUCT_DEMO_AUTH_ACK": ACK,
        "NHM_PRODUCT_DEMO_USER_ID": "demo:faculty",
        "NHM_PRODUCT_DB_PATH": str(root / "product.sqlite3"),
        "NHM_PRODUCT_INFERENCE_URL": inference_url,
        "NHM_PRODUCT_TIMING_MODE": "ACCELERATED",
        "NHM_FEDERATION_ARTIFACT_ROOT": str(root / "federation"),
        "NHM_FL_CANDIDATE_ROOT": str(root / "candidates"),
        "NHM_FEDERATION_AUTO_RESUME": "0",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_capstone_product_v1_3", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}/product/v1"
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if process.poll() is not None:
                detail = process.stdout.read()[-2000:] if process.stdout else ""
                raise RuntimeError(f"PRODUCT_V13_PROCESS_EXITED:{detail}")
            try:
                response = httpx.get(base + "/system", timeout=2)
                if response.status_code == 200:
                    if response.json()["product_api_implementation"] != "CAPSTONE_PRODUCT_API_V1_3":
                        raise RuntimeError("WRONG_PRODUCT_API_IMPLEMENTATION")
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        else:
            raise RuntimeError("PRODUCT_V13_LAUNCH_TIMEOUT")
        yield base, port
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def db_assertions(
    db: Path, session_id: str, summary: dict[str, Any], timeline: dict[str, Any]
) -> dict[str, Any]:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        inference = connection.execute(
            "SELECT monitoring_state, ecg_quality FROM inference_events WHERE session_id=?",
            (session_id,),
        ).fetchall()
        context = connection.execute(
            "SELECT hr_ecg_bpm, spo2_pct, spo2_valid FROM context_snapshots "
            "WHERE session_id=? ORDER BY sequence_index, snapshot_id",
            (session_id,),
        ).fetchall()
        state_change_count = connection.execute(
            "SELECT count(*) FROM monitoring_state_events WHERE session_id=?", (session_id,)
        ).fetchone()[0]
        lifecycle = connection.execute(
            "SELECT event_type FROM device_connections WHERE session_id=?", (session_id,)
        ).fetchall()
        session = connection.execute(
            "SELECT started_at_us, ended_at_us, state FROM monitoring_sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        quality_changes = connection.execute(
            "SELECT count(*) FROM signal_quality_events WHERE session_id=?", (session_id,)
        ).fetchone()[0]
        summary_rows = connection.execute(
            "SELECT count(*) FROM session_summaries WHERE session_id=?", (session_id,)
        ).fetchone()[0]
        preview_rows = connection.execute(
            "SELECT count(*) FROM waveform_previews WHERE session_id=?", (session_id,)
        ).fetchone()[0]
    hr = [r["hr_ecg_bpm"] for r in context
          if r["hr_ecg_bpm"] is not None and math.isfinite(r["hr_ecg_bpm"])]
    spo2 = [r["spo2_pct"] for r in context
            if r["spo2_valid"] and r["spo2_pct"] is not None
            and math.isfinite(r["spo2_pct"])]

    def stats(values: list[float]) -> tuple[float | None, float | None, float | None]:
        return (
            (min(values), sum(values) / len(values), max(values)) if values else (None, None, None)
        )

    state_counts = dict(Counter(r["monitoring_state"] for r in inference))
    quality_counts = dict(Counter(r["ecg_quality"] for r in inference))
    device_counts = Counter(r["event_type"] for r in lifecycle)
    checks = {
        "completed": session["state"] == "COMPLETED",
        "windows_inferred": summary["windows_inferred"] == len(inference),
        "state_counts": summary["state_counts"] == state_counts,
        "quality_counts": summary["quality_counts"] == quality_counts,
        "hr_stats": tuple(summary[k] for k in ("hr_min", "hr_mean", "hr_max")) == stats(hr),
        "spo2_stats": tuple(summary[k] for k in ("spo2_min", "spo2_mean", "spo2_max"))
        == stats(spo2),
        "duration": summary["duration_ms"]
        == (session["ended_at_us"] - session["started_at_us"]) // 1000,
        "disconnects": summary["disconnect_count"] == device_counts["DEVICE_DISCONNECTED"],
        "reconnects": summary["reconnect_count"] == device_counts["DEVICE_RECONNECTED"],
        "one_summary_row": summary_rows == 1,
        "preview_stored": preview_rows == len(timeline["waveform_previews"]) and preview_rows > 0,
        "source_timeline_count": len(timeline["source_timeline"])
        == (
            len(inference)
            + len(context)
            + quality_changes
            + state_change_count
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"HISTORY_RELATIONAL_MISMATCH:{checks}")
    return {
        "checks": checks,
        "inference_rows": len(inference),
        "quality_change_rows": quality_changes,
        "preview_rows": preview_rows,
        "summary_rows": summary_rows,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    shots = OUT / "screenshots"
    shots.mkdir(exist_ok=True)
    browser_out = OUT / "browser_raw.json"
    with tempfile.TemporaryDirectory(prefix="cap009-") as tmp:
        root = Path(tmp)
        with launch_released_inference() as (inference_url, inference_info):
            with product_v13(root, inference_url) as (base, port), preview_server(port) as origin:
                debug_port = free_port()
                with chrome(debug_port, str(root / "chrome-profile")):
                    driver = subprocess.run(
                        [
                            "node",
                            str(ROOT / "scripts/cap_009_cdp_driver.mjs"),
                            str(debug_port),
                            origin,
                            str(browser_out),
                            str(shots),
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        timeout=500,
                    )
                save(
                    "browser_driver_log.json",
                    {
                        "exit": driver.returncode,
                        "stdout": driver.stdout[-2000:],
                        "stderr": driver.stderr[-4000:],
                    },
                )
                if driver.returncode != 0:
                    raise RuntimeError("CANONICAL_BROWSER_DRIVER_FAILED")
                browser = json.loads(browser_out.read_text(encoding="utf-8"))
                identity = httpx.get(base + "/system").json()
                api = browser["api"]
                if any(
                    api[key]["status"] != 200
                    for key in ("session", "summary", "timeline", "ml", "fl")
                ):
                    raise RuntimeError("CANONICAL_BROWSER_API_STATUS_NOT_200")
                checks = db_assertions(
                    root / "product.sqlite3",
                    browser["session_id"],
                    api["summary"]["body"],
                    api["timeline"]["body"],
                )
                before = {
                    key: digest(api[key]["body"])
                    for key in ("session", "summary", "timeline", "ml", "fl")
                }
            with product_v13(root, inference_url) as (base_after, _port):
                after = {
                    key: digest(httpx.get(base_after + path).json())
                    for key, path in {
                        "session": f"/sessions/{browser['session_id']}",
                        "summary": f"/sessions/{browser['session_id']}/summary",
                        "timeline": f"/sessions/{browser['session_id']}/timeline",
                        "ml": "/research/ml",
                        "fl": "/research/fl",
                    }.items()
                }
                if after != before:
                    raise RuntimeError("HISTORY_RESTART_EVIDENCE_CHANGED")
    steps = {row["name"]: row for row in browser["steps"]}
    if (browser["external_requests"] or browser["blocked_external_requests"]
            or browser["console_errors"]):
        raise RuntimeError("BROWSER_EXTERNAL_REQUEST_OR_CONSOLE_ERROR")
    if not all(row["scrollWidth"] <= row["width"] + 1 for row in browser["responsive"].values()):
        raise RuntimeError("CAP009_HORIZONTAL_OVERFLOW")
    if not all(row["h1"] == 1 and row["main"] == 1 for row in browser["accessibility"].values()):
        raise RuntimeError("CAP009_LANDMARK_OR_H1_ERROR")
    save(
        "canonical_history_browser_e2e.json",
        {
            "status": "PASS",
            "auth": steps["auth"],
            "monitoring": steps["monitoring"],
            "history_list": steps["history-list"],
            "history_detail": steps["history-detail"],
            "database": checks,
            "inference_service": {
                k: v for k, v in inference_info.items() if k not in ("pid", "port")
            },
            "product_system": identity,
            "browser_api_digests": before,
        },
    )
    save("history_restart_e2e.json", {"status": "PASS", "before": before, "after": after})
    save(
        "canonical_research_browser_e2e.json",
        {
            "status": "PASS",
            "ml": steps["research-ml"],
            "fl": steps["research-fl"],
            "catalog_digest_ml": before["ml"],
            "catalog_digest_fl": before["fl"],
        },
    )
    save(
        "offline_network_audit.json",
        {
            "status": "PASS",
            "external_requests": browser["external_requests"],
            "blocked_external_requests": browser["blocked_external_requests"],
            "external_network_policy": "ACTIVE_CDP_REQUEST_INTERCEPTION_LOOPBACK_ONLY",
            "request_count": len(browser["requests"]),
            "console_errors": browser["console_errors"],
        },
    )
    save("responsive_audit.json", {"status": "PASS", "measurements": browser["responsive"]})
    save(
        "accessibility_audit.json",
        {
            "status": "PASS",
            "measurements": browser["accessibility"],
            "formal_wcag_certification_claimed": False,
        },
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "session_id": browser["session_id"],
                "windows_inferred": checks["inference_rows"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
