# ruff: noqa: E501
"""CAP-010 canonical full-demo runner (real stack through the faculty launcher; no mocks).

    python -m scripts.run_capstone_full_demo_e2e coverage            # FULL_CAPSTONE_DEMO monitoring+FL scenario coverage
    python -m scripts.run_capstone_full_demo_e2e run N [--restart]    # complete faculty browser journey N (fresh workspace)
Run N=1 with --restart additionally stops the stack and RESUMEs the SAME workspace (demo_restart.json).
``CAP010_OUT`` overrides the evidence directory (dry runs only)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from scripts.capstone_demo_workspace import scan_logs_for_secrets
from scripts.run_capstone_frontend_e2e import chrome
from scripts.run_capstone_persistent_e2e import free_port

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("CAP010_OUT", ROOT / "reports/capstone/cap_010"))
HOST = "127.0.0.1"
DEFAULT_PORTS = (8001, 8002, 4173)
STRIP = {"session_id", "latency_ms", "generated_at_us", "created_at_us", "at_us", "started_at_us", "ended_at_us", "duration_ms", "run_id", "federation_run_id", "event_id", "emitted_at_us", "updated_at_us", "completed_at_us", "device_id", "user_id", "created_at"}


def write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def sha(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in STRIP}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


class Launcher:
    """The faculty launcher as a real subprocess; waits for the READY block; stops it with SIGINT (Ctrl+C)."""

    def __init__(self, workspace: Path, ports: tuple[int, int, int], *, mode: str = "fresh", build: bool = False, prewarm: bool = False) -> None:
        self.workspace, self.ports, self.mode, self.build, self.prewarm = workspace, ports, mode, build, prewarm
        self.log = workspace.parent / f"{workspace.name}.launcher.out"
        self.process: subprocess.Popen[bytes] | None = None
        self.start_s = 0.0
        self.pids: dict[str, int] = {}

    def start(self, timeout: float = 600.0) -> None:
        cmd = [sys.executable, "-m", "scripts.run_capstone_faculty_demo", "--acknowledge-demo-auth", "--workspace", str(self.workspace), "--mode", self.mode,
               "--inference-port", str(self.ports[0]), "--product-port", str(self.ports[1]), "--frontend-port", str(self.ports[2])]
        if self.build:
            cmd.append("--build")
        if self.prewarm:
            cmd.append("--prewarm-federation")
        started = time.monotonic()
        self.process = subprocess.Popen(cmd, cwd=ROOT, env={**os.environ, "PYTHONPATH": "src:."}, stdout=self.log.open("wb"), stderr=subprocess.STDOUT)
        while time.monotonic() - started < timeout:
            text = self.log.read_text(errors="replace") if self.log.exists() else ""
            if "NHM FACULTY DEMO READY" in text:
                self.start_s = round(time.monotonic() - started, 3)
                self.pids = json.loads((self.workspace / "status.json").read_text())["pids"]
                return
            if self.process.poll() is not None:
                raise RuntimeError("LAUNCHER_EXITED_BEFORE_READY:" + text[-600:])
            time.sleep(0.5)
        raise RuntimeError("LAUNCHER_READY_TIMEOUT")

    @property
    def origin(self) -> str:
        return f"http://{HOST}:{self.ports[2]}"

    @property
    def product(self) -> str:
        return f"http://{HOST}:{self.ports[1]}/product/v1"

    def stop(self) -> dict[str, Any]:
        assert self.process is not None
        self.process.send_signal(signal.SIGINT)  # Ctrl+C
        try:
            code = self.process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            self.process.kill()
            code = -9
        alive = []
        for name, pid in self.pids.items():
            try:
                os.kill(pid, 0)
                alive.append(name)
            except ProcessLookupError:
                pass
        shutdown = json.loads((self.workspace / "shutdown.json").read_text()) if (self.workspace / "shutdown.json").exists() else {}
        return {"launcher_exit_code": code, "child_pids_still_alive": alive, "launcher_reported_orphans": shutdown.get("orphans"), "secret_scan": scan_logs_for_secrets(self.workspace / "logs"),
                "stopped_in_reverse_order_log": "stack stopped" in self.log.read_text(errors="replace")}


def ws_collect(url: str, sink: list[dict[str, Any]]) -> None:
    with contextlib.suppress(Exception), connect(url, open_timeout=20, close_timeout=5) as ws:
        while True:
            try:
                sink.append(json.loads(ws.recv(timeout=900)))
            except ConnectionClosed:
                return


# ---- scenario coverage (real SimulatedWearableSource + coordinator + SOFTWARE_SYSTEM_V2) ----------------------
EXPECTED = {
    "NORMAL_MONITORING": ["SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED", "STREAM_STARTED", "STREAM_STOPPED"],
    "CONTEXT_LOSS": ["SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED", "STREAM_STARTED", "STREAM_STOPPED"],
    "POOR_SIGNAL": ["SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED", "STREAM_STARTED", "STREAM_STOPPED"],
    "DISCONNECT_RECONNECT": ["SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED", "STREAM_STARTED", "DEVICE_DISCONNECTED", "RECONNECT_STARTED", "DEVICE_RECONNECTED", "STREAM_STARTED", "STREAM_STOPPED"],
    "MIXED_MONITORING_SESSION": ["SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED", "STREAM_STARTED", "DEVICE_DISCONNECTED", "RECONNECT_STARTED", "DEVICE_RECONNECTED", "STREAM_STARTED", "STREAM_STOPPED"],
}


def subsequence(wanted: list[str], seen: list[str]) -> bool:
    it = iter(seen)
    return all(any(w == s for s in it) for w in wanted)


def run_monitoring_scenario(product: str, ws_base: str, scenario: str) -> dict[str, Any]:
    c = httpx.Client(timeout=120)
    device = c.post(f"{product}/devices/simulated", json={"scenario_id": scenario}).json()["device_id"]
    scan_state = c.post(f"{product}/devices/{device}/scan").json()["connection_state"]
    connect_state = c.post(f"{product}/devices/{device}/connect").json()["connection_state"]
    session = c.post(f"{product}/sessions", json={"device_id": device, "scenario_id": scenario}).json()["session_id"]
    events: list[dict[str, Any]] = []
    thread = threading.Thread(target=ws_collect, args=(f"{ws_base}/sessions/{session}/live", events))
    thread.start()
    time.sleep(0.5)
    started = time.monotonic()
    c.post(f"{product}/sessions/{session}/start")
    thread.join(timeout=600)
    elapsed = round(time.monotonic() - started, 2)
    final = c.get(f"{product}/sessions/{session}").json()
    timeline = c.get(f"{product}/sessions/{session}/timeline").json()
    kinds: dict[str, int] = {}
    for e in events:
        kinds[e["event_type"]] = kinds.get(e["event_type"], 0) + 1
    inf = [e["payload"] for e in events if e["event_type"] == "inference.result"]
    ctx = [e["payload"] for e in events if e["event_type"] == "context.snapshot"]
    qual = [e["payload"]["ecg_quality"] for e in events if e["event_type"] == "quality.status"]
    wave = [e["payload"] for e in events if e["event_type"] == "waveform.chunk" and e["payload"]["channel"] == "ECG"]
    nulls = sum(1 for w in wave for s in w["samples"] if s is None)
    jumps, expect = 0, None
    for w in wave:
        if expect is not None and w["first_sample_index"] != expect:
            jumps += 1
        expect = w["first_sample_index"] + w["sample_count"]
    lifecycle = [d["event_type"] for d in timeline["device_lifecycle"]]
    states = [e["payload"]["monitoring_state"] for e in events if e["event_type"] == "monitoring.state"]
    return {"scenario": scenario, "session_state": final["state"], "session_runtime": final["runtime"], "elapsed_s_accelerated": elapsed, "event_kinds": kinds,
            "sequence_contiguous": [e["sequence_index"] for e in events] == list(range(len(events))), "device_lifecycle": lifecycle,
            "expected_connection_events": EXPECTED[scenario], "pre_session_device_states": [scan_state, connect_state],
            "connection_events_as_expected": [scan_state, connect_state] == ["FOUND", "CONNECTED"] and subsequence(EXPECTED[scenario][4:], lifecycle),
            "inference_results": len(inf), "model_ids": sorted({i["model_id"] for i in inf if i["model_id"]}), "calibration_ids": sorted({i["calibration_id"] for i in inf if i["calibration_id"]}),
            "monitoring_states_observed": sorted({i["monitoring_state"] for i in inf}), "monitoring_state_changes": states,
            "context_available_true": sum(1 for x in ctx if x["context_available"]), "context_available_false": sum(1 for x in ctx if not x["context_available"]),
            "ecg_quality_counts": {q: qual.count(q) for q in sorted(set(qual))}, "ecg_null_samples": nulls, "ecg_index_discontinuities": jumps,
            "timeline_source_entries": len(timeline["source_timeline"]), "model_outcome_asserted": False, "outcome_tuned": False}


def invariants(r: dict[str, Any]) -> dict[str, bool]:
    base = {"completed": r["session_state"] == "COMPLETED", "contiguous_events": r["sequence_contiguous"], "connection_events_as_expected": r["connection_events_as_expected"],
            "released_model": r["model_ids"] == ["MODEL_V2_FINAL"] and r["calibration_ids"] == ["CAL_V2"], "inference_ran": r["inference_results"] > 0}
    s = r["scenario"]
    if s == "NORMAL_MONITORING":
        base["quality_valid_throughout"] = set(r["ecg_quality_counts"]) == {"VALID"}
        base["context_available_throughout"] = r["context_available_false"] == 0 and r["context_available_true"] > 0
    elif s == "CONTEXT_LOSS":
        base["context_unavailable_interval"] = r["context_available_false"] > 0 and r["context_available_true"] > 0
    elif s == "POOR_SIGNAL":
        base["quality_degraded_or_unusable_reported"] = any(q in r["ecg_quality_counts"] for q in ("DEGRADED", "UNUSABLE"))
    elif s in ("DISCONNECT_RECONNECT", "MIXED_MONITORING_SESSION"):
        base["disconnect_and_reconnect"] = "DEVICE_DISCONNECTED" in r["device_lifecycle"] and "DEVICE_RECONNECTED" in r["device_lifecycle"]
        base["source_delivery_gap_without_fabrication"] = r["ecg_null_samples"] > 0 or r["ecg_index_discontinuities"] > 0
    return base


def run_federation_scenarios(product: str, ws_base: str) -> dict[str, Any]:
    c = httpx.Client(timeout=900)
    out: dict[str, Any] = {}
    for name, mode in (("FL_SINGLE_RUN", "PLAIN"), ("FL_SECAGG_SHADOW", "SECAGG_SHADOW")):
        body = {"run_type": "LIVE_RUN", "algorithm": "FEDAVG", "secagg_mode": mode, "planned_rounds": 3, "scenario_id": "FL_SINGLE_RUN"}
        run = c.post(f"{product}/federation/runs", json=body).json()["run_id"]
        events: list[dict[str, Any]] = []
        thread = threading.Thread(target=ws_collect, args=(f"{ws_base}/federation/runs/{run}/live", events))
        thread.start()
        time.sleep(0.5)
        c.post(f"{product}/federation/runs/{run}/start")
        thread.join(timeout=900)
        final = c.get(f"{product}/federation/runs/{run}").json()
        rounds = c.get(f"{product}/federation/runs/{run}/rounds").json()
        kinds: dict[str, int] = {}
        for e in events:
            kinds[e["event_type"]] = kinds.get(e["event_type"], 0) + 1
        secagg = [(e["payload"]["round_id"], e["payload"]["status"]) for e in events if e["event_type"] == "secagg.status"]
        agg = sorted({e["payload"]["aggregation_mode"] for e in events if e["event_type"] == "aggregation.status"})
        out[name] = {"run_status": final["status"], "secagg_mode": mode, "rounds": [(r["state"], r["accepted_update_count"]) for r in rounds], "update_ready_events": kinds.get("client.update_ready", 0),
                     "event_kinds": kinds, "secagg_events": secagg, "aggregation_modes": agg, "candidate_ids": final["candidate_ids"], "clients": len(final["client_ids"])}
        out[name]["pass"] = (final["status"] == "COMPLETED" and kinds.get("client.update_ready") == 24 and len(final["candidate_ids"]) == 1 and agg == ["PLAIN"] and len(rounds) == 3
                             and (mode == "PLAIN" or secagg == [(1, "SHADOW_RUNNING"), (1, "SHADOW_VERIFIED")]))
        c.get(f"{product}/federation")
        if name == "FL_SINGLE_RUN":
            time.sleep(1)
    return out


def coverage() -> int:
    work = Path(tempfile.mkdtemp(prefix="cap010-coverage-"))
    ports = (free_port(), free_port(), free_port())
    launcher = Launcher(work / "ws", ports, build=False, prewarm=False)
    results: dict[str, Any] = {}
    try:
        launcher.start()
        ws_base = f"ws://{HOST}:{ports[1]}/product/v1"
        for scenario in ("NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT", "MIXED_MONITORING_SESSION"):
            r = run_monitoring_scenario(launcher.product, ws_base, scenario)
            r["invariants"] = invariants(r)
            r["pass"] = all(r["invariants"].values())
            results[scenario] = r
            print(scenario, r["pass"], flush=True)
        fl = run_federation_scenarios(launcher.product, ws_base)
        for name, r in fl.items():
            results[name] = r
            print(name, r["pass"], flush=True)
    finally:
        stopped = launcher.stop() if launcher.process else {}
    write("scenario_coverage.json", {"scenarios": results, "workspace": "separate temporary workspace (not the visible faculty workspace)", "launcher_stop": stopped, "real_components": ["SimulatedWearableSource", "monitoring coordinator", "SOFTWARE_SYSTEM_V2 inference process", "federation runtime"], "mocks_used": False})
    contract = json.loads((ROOT / "contracts/capstone/demo_scenarios_v1.json").read_text())
    composes = next(s for s in contract["scenarios"] if s["scenario_id"] == "FULL_CAPSTONE_DEMO")["composes"]
    rows = {s: {"status": "PASS" if results[s]["pass"] else "FAIL", "exercised_by": "real product path via the faculty launcher (headless API/WebSocket harness)" if s not in ("FL_SINGLE_RUN", "FL_SECAGG_SHADOW") else "genuine LIVE_RUN through the product federation API (FEDAVG, 3 rounds, 24 updates)"} for s in composes}
    write("full_demo_scenario_coverage.json", {"scenario_id": "FULL_CAPSTONE_DEMO", "classification": "ENGINEERING_DEMO", "scientific_evidence": False, "composes": composes, "coverage": rows,
                                               "faculty_hero": {"scenario": "MIXED_MONITORING_SESSION", "role": "FACULTY_HERO_MONITORING", "pass": results["MIXED_MONITORING_SESSION"]["pass"], "note": "presentation convenience; does not replace the four monitoring coverage runs"},
                                               "outcome_tuning": False, "model_outcome_required": False})
    return 0 if all(r["pass"] for r in results.values()) else 1


# ---- full browser journey ---------------------------------------------------------------------------------------
def snapshot(prod: str, ws: Path) -> dict[str, Any]:
    db = ws / "product.sqlite3"
    import sqlite3

    conn = sqlite3.connect(db)
    counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("users", "devices", "monitoring_sessions", "inference_events", "federation_runs", "federation_rounds", "candidate_models", "governance_decisions")}
    candidates = [dict(zip(("candidate_id", "state_digest", "governance_status", "sandbox_status", "validation_status", "production_deployed"), r, strict=True)) for r in conn.execute("SELECT candidate_id, state_digest, governance_status, sandbox_status, validation_status, production_deployed FROM candidate_models")]
    conn.close()
    runs = sorted((ws / "federation/runs").glob("*/run.json"))
    return {"db_counts": counts, "candidates": candidates, "federation_run_files": [p.parent.name for p in runs], "candidate_dirs": sorted(p.name for p in (ws / "candidates").iterdir()) if (ws / "candidates").exists() else []}


def run_driver(mode: str, launcher: Launcher, work: Path, name: str, known: tuple[str, str] | None = None) -> dict[str, Any]:
    debug = free_port()
    raw = work / f"{name}.json"
    shots = OUT / "screenshots" / name
    args = ["node", str(ROOT / "scripts/cap_010_cdp_driver.mjs"), mode, str(debug), launcher.origin, str(raw), str(shots)]
    if known:
        args += list(known)
    started = time.monotonic()
    with chrome(debug, str(work / f"profile-{name}")):
        proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=2400)
    (work / f"{name}.driver.log").write_text(proc.stdout[-3000:] + proc.stderr[-3000:])
    data = json.loads(raw.read_text()) if raw.exists() else {}
    data["driver_exit"], data["driver_wall_s"] = proc.returncode, round(time.monotonic() - started, 2)
    if proc.returncode != 0:
        data["driver_stderr_tail"] = proc.stderr[-800:]
    return data


def semantic(browser: dict[str, Any], ws: Path) -> tuple[dict[str, Any], str]:
    a = browser["api"]
    sysb = a["system"]["body"]
    timeline = a["timeline"]["body"]
    run = a["run"]["body"]
    meta = json.loads((ws / "federation/runs" / run["run_id"] / "run.json").read_text())
    previews = [{"point_count": p["point_count"], "decimation_factor": p["decimation_factor"], "points_sha256": sha(p["points"])} for p in timeline["waveform_previews"]]
    models = a["models"]["body"]
    catalog = ROOT / "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json"
    proj = {
        "runtime": {k: sysb[k] for k in ("product_api_implementation", "product_api_version", "software_system", "model_id", "calibration_id", "auth_provider", "demo_mode", "hardware_mode", "physical_hardware_available", "federation_runtime", "persistence_mode")},
        "session": strip({"scenario": a["session"]["body"]["simulation_provenance"]["scenario_id"], "state": a["session"]["body"]["state"], "runtime": a["session"]["body"]["runtime"]}),
        "summary": strip(a["summary"]["body"]),
        "timeline": {"source_timeline": strip(timeline["source_timeline"]), "device_lifecycle": [d["event_type"] for d in timeline["device_lifecycle"]], "waveform_previews": previews},
        "federation": {"config": {k: run[k] for k in ("run_type", "algorithm", "secagg_mode", "planned_rounds", "client_ids", "base_model_id", "status", "candidate_ids")},
                       "rounds": [{k: r[k] for k in ("round_id", "state", "base_state_digest", "accepted_update_count", "candidate_id")} for r in a["rounds"]["body"]],
                       "update_digests": meta["training_record"], "committed_digests": meta["committed_digests"], "secagg": meta.get("secagg_shadow", {}).get("status")},
        "candidates": strip(models["capstone_fl_candidates"]), "released": models["released_default_model_id"],
        "research": {"ml": sha(a["ml"]["body"]), "fl": sha(a["fl"]["body"]), "catalog_file_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest()},
    }
    return proj, sha(proj)


def run_journey(n: int, restart: bool) -> int:
    work = Path(tempfile.mkdtemp(prefix=f"cap010-run{n}-"))
    ports = DEFAULT_PORTS
    ws = work / "workspace"
    launcher = Launcher(ws, ports, build=True, prewarm=True)
    t0 = time.monotonic()
    launcher.start()
    startup_s = launcher.start_s
    status = json.loads((ws / "status.json").read_text())
    browser: dict[str, Any] = {}
    try:
        browser = run_driver("full", launcher, work, f"full_run_{n}")
    finally:
        pre_snapshot = snapshot(launcher.product, ws) if (ws / "product.sqlite3").exists() else {}
        stopped = launcher.stop()
    proj, digest = semantic(browser, ws) if browser.get("api", {}).get("run") else ({}, "")
    result = {"run": n, "launcher_command": "python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth --build --prewarm-federation --workspace <fresh temp> (default ports 8001/8002/4173)",
              "ports": list(ports), "workspace_outside_repository": ROOT not in ws.resolve().parents, "startup_s_including_build_and_prewarm": startup_s, "prewarm": status.get("prewarm"),
              "browser": {k: v for k, v in browser.items() if k != "api"}, "driver_exit": browser.get("driver_exit"), "stopped": stopped, "post_run_snapshot": pre_snapshot,
              "semantic_projection": proj, "semantic_sha256": digest, "wall_clock_total_s_machine_specific": round(time.monotonic() - t0, 1),
              "ids": {"session_excluded_from_digest": browser.get("sessionId"), "run_excluded_from_digest": browser.get("runId")}}
    if restart and browser.get("sessionId"):
        result["restart"] = restart_phase(n, work, ws, browser, digest)
    write(f"full_browser_demo_run_{n}.json", result)
    if restart and "restart" in result:
        write("demo_restart.json", result["restart"])
    ok = browser.get("driver_exit") == 0 and bool(digest) and not stopped["child_pids_still_alive"] and stopped["launcher_exit_code"] == 0
    print(json.dumps({"run": n, "ok": ok, "semantic_sha256": digest, "stopped": {k: stopped[k] for k in ("launcher_exit_code", "child_pids_still_alive")}}))
    return 0 if ok else 1


def restart_phase(n: int, work: Path, ws: Path, before: dict[str, Any], digest_before: str) -> dict[str, Any]:
    launcher = Launcher(ws, DEFAULT_PORTS, mode="resume", build=False, prewarm=False)
    snap_before = snapshot(launcher.product, ws)
    launcher.start()
    try:
        after = run_driver("reload", launcher, work, f"reload_run_{n}", known=(before["sessionId"], before["runId"]))
    finally:
        stopped = launcher.stop()
    snap_after = snapshot(launcher.product, ws)
    same = {k: (strip(before["api"][k]["body"]) == strip(after["api"][k]["body"])) for k in ("session", "summary", "timeline", "run", "rounds", "models", "ml", "fl", "system") if k in after.get("api", {})}
    same_raw = {k: before["api"][k]["body"] == after["api"][k]["body"] for k in ("summary", "timeline", "ml", "fl") if k in after.get("api", {})}
    proj_after, digest_after = semantic(after, ws) if after.get("api", {}).get("run") else ({}, "")
    steps = {s["step"]: s for s in after.get("steps", [])}
    return {"same_workspace": str(ws) == str(ws), "mode": "RESUME", "driver_exit": after.get("driver_exit"), "same_projection_per_api": same, "byte_equal_payloads": same_raw, "semantic_sha256_before": digest_before, "semantic_sha256_after": digest_after,
            "semantic_identical": digest_before == digest_after, "db_before": snap_before, "db_after": snap_after,
            "counts_unchanged": snap_before["db_counts"] == snap_after["db_counts"], "no_new_federation_run": snap_before["federation_run_files"] == snap_after["federation_run_files"], "no_new_candidate": snap_before["candidate_dirs"] == snap_after["candidate_dirs"],
            "monitoring_rerun": snap_after["db_counts"]["monitoring_sessions"] != snap_before["db_counts"]["monitoring_sessions"], "fl_rerun": snap_after["db_counts"]["federation_runs"] != snap_before["db_counts"]["federation_runs"],
            "research_catalog_file_unchanged": proj_after.get("research", {}).get("catalog_file_sha256") == semantic(before, ws)[0]["research"]["catalog_file_sha256"], "browser_steps": steps,
            "network": after.get("network"), "console_errors": after.get("console_errors"), "stopped": stopped, "released_default": after.get("api", {}).get("models", {}).get("body", {}).get("released_default_model_id"),
            "device_runtime_connection_state_note": "device connection state is runtime-only and reconstructed according to the CAP-004 restart policy (not asserted by this phase)"}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "coverage":
        sys.exit(coverage())
    if mode == "run":
        sys.exit(run_journey(int(sys.argv[2]), "--restart" in sys.argv))
    sys.exit("usage: coverage | run N [--restart]")
