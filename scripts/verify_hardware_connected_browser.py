"""Run both hardware scenarios through real Chrome and a real Clerk test instance."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pymongo import MongoClient

from scripts.run_capstone_clerk_connected import build_frontend, build_services, parse_env_file, resolve_config
from scripts.run_capstone_clerk_connected_e2e import Browser, free_port
from scripts.run_capstone_faculty_demo import DemoOrchestrator
from scripts.capstone_demo_workspace import SENTINEL, Workspace

DRIVER = ROOT / "scripts/hardware_final_cdp_driver.mjs"


def stack(env: dict[str, str], workspace: Path, python: str) -> tuple[DemoOrchestrator, str]:
    ports = {"inference": 8001, "product": 8002, "frontend": 4173}
    cfg = resolve_config(env, ports["frontend"])
    ws = Workspace.create_fresh(workspace) if not (workspace / SENTINEL).exists() else Workspace.open_resume(workspace)
    services = build_services(ws, ports, cfg, env, python=python)
    services[1].argv = [python, "-m", "scripts.run_observatory_product", "--host", "127.0.0.1", "--port", str(ports["product"])]
    orchestrator = DemoOrchestrator(services, ready_timeout=240, say=lambda message: print(message, flush=True))
    if not orchestrator.start_and_wait_ready():
        raise RuntimeError(orchestrator.failed or "stack failed")
    return orchestrator, f"http://127.0.0.1:{ports['frontend']}"


def drive(mode: str, origin: str, users: Path, out: Path, shots: Path, logs: Path, env: dict[str, str], *, who: str = "A", expected: str | None = None) -> dict:
    profile = Path(tempfile.mkdtemp(prefix=f"nhm-hardware-{mode}-"))
    browser = Browser(profile, free_port())
    command = ["node", str(DRIVER), mode, str(browser.port), origin, str(users), str(out), str(shots), str(logs)]
    run_env = {**os.environ, **env, "NHM_TEST_PYTHON": str(ROOT / ".venv-studio311/bin/python"), "NHM_BROWSER_USER": who}
    if expected:
        run_env["NHM_EXPECT_SESSION"] = expected
    try:
        result = subprocess.run(command, cwd=ROOT, env=run_env, capture_output=True, text=True, timeout=1800)
    finally:
        browser.close(); shutil.rmtree(profile, ignore_errors=True)
    if result.returncode or not out.exists():
        raise RuntimeError(f"browser {mode} failed: {(result.stdout + result.stderr)[-1200:]}")
    return json.loads(out.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--users-file", required=True)
    parser.add_argument("--out", default=str(ROOT / "reports/hardware/final_demo/browser"))
    parser.add_argument("--producer", choices=["direct", "ws"], default="direct",
                        help="direct: publisher inserts into Atlas; ws: ESP32 emulator -> local ingestion replica -> Atlas")
    parser.add_argument("--database", default=None, help="Atlas database (ws mode defaults to the isolated nhm_rehearsal)")
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--latency-seconds", type=int, default=0, help="measure Atlas-ack -> browser-display latency for this many seconds")
    parser.add_argument("--away-seconds", type=int, default=0, help="lifecycle audit: leave the Monitor page for this many seconds while the emitter continues")
    parser.add_argument("--run-switch", action="store_true", help="real-browser run-switch check: hardware <-> recorded synthetic evidence via the selector, back/forward and reload")
    parser.add_argument("--ui-tour", action="store_true", help="seed a hardware session + run, then tour every route at desktop and phone width")
    parser.add_argument("--soak-seconds", type=int, default=0, help="run only the long browser soak for this many seconds")
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    env = {**parse_env_file(Path(args.env_file)), **os.environ}
    env["NHM_HARDWARE_MONGO_ENABLED"] = "true"
    ws_mode = args.producer == "ws"
    database = args.database or ("nhm_rehearsal" if ws_mode else "health_db")
    if database == "health_db" and ws_mode:
        raise SystemExit("ws producer mode must not target health_db")
    env["NHM_HARDWARE_MONGO_DATABASE"] = database
    env["NHM_HARDWARE_MONGO_COLLECTION"] = "records_*" if ws_mode else "nhm_integration_test"
    replica = None
    if ws_mode:
        from scripts.hardware_chain import Replica
        replica = Replica(out / "replica", database=database)
        replica.workdir.mkdir(parents=True, exist_ok=True)
        replica.start()
        env["NHM_PRODUCER"] = "ws"
        env["NHM_WS_URL"] = replica.url
    cfg = resolve_config(env, 4173)
    python = str(ROOT / ".venv-studio311/bin/python")
    build_frontend(cfg, env)
    workspace = Path(tempfile.mkdtemp(prefix="nhm-hardware-browser-workspace-")) / "workspace"
    tags: list[str] = []
    first = second = owner = None
    try:
        if args.latency_seconds:
            from scripts.hardware_chain import browser_latency
            running, origin = stack(env, workspace, python)
            try:
                env["NHM_LATENCY_SECONDS"] = str(args.latency_seconds)
                lat = drive("latency", origin, Path(args.users_file), out / "latency.json", out / "latency_shots", out / "publisher_logs", env)
                tags.append(lat["tag"])
            finally:
                running.shutdown()
            log_dir = out / "publisher_logs"
            emulator_events = [json.loads(x) for x in (log_dir / f"{lat['tag']}.events.jsonl").read_text().splitlines() if x.strip()] if (log_dir / f"{lat['tag']}.events.jsonl").exists() else []
            replica_events = replica.events() if replica else []
            report = browser_latency({k: float(v) for k, v in lat["seen"].items()}, replica_events, emulator_events)
            report |= {"session_id": lat["session_id"], "seconds": lat["seconds"], "producer": "ws" if ws_mode else "direct",
                       "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA" if ws_mode else "VERIFIED_DIRECT_ATLAS_INJECTION"}
            (out / "browser_latency.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            print(json.dumps(report))
            return 0
        if args.run_switch:
            running, origin = stack(env, workspace, python)
            try:
                sw = drive("switch", origin, Path(args.users_file), out / "switch.json", out / "switch_shots", out / "publisher_logs", env)
                tags.append(sw["tag"])
            finally:
                running.shutdown()
            steps = sw["steps"]
            def ok(step):
                if step.get("expect_path"):
                    return step.get("path") == step["expect_path"]
                hw = step["expected_badge"] == "RECORDED HARDWARE"
                names = [c or "" for c in step["clients"]]
                right_ns = len(names) == 8 and all(n.startswith("RECORDED_DEMO_CLIENT_" if hw else "SIM_FL_SITE_") for n in names)
                return (step["url_run"] == step["expected_run"] and step["selector"] == step["expected_run"] and step["badge"] == step["expected_badge"] and right_ns
                        and step["hw_participation"] == hw and (not hw or (not step["owner_label"] and step["peer_labels"] == 0)) and step["replay_note"] == (not hw))
            results = [{"step": st["step"], "pass": ok(st), "badge": st.get("badge"), "url_run": st.get("url_run"), "client_namespace": ((st.get("clients") or [""])[0] or "")[:14], "auprc": st.get("auprc")} for st in steps]
            verdict = {"status": "PASS" if all(r["pass"] for r in results) else "FAIL", "mode": "run_switch", "steps": results,
                       "hardware_vs_recorded_metric_differs": len({st.get("auprc") for st in steps if st.get("auprc")}) > 1,
                       "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA" if ws_mode else "VERIFIED_DIRECT_ATLAS_INJECTION"}
            (out / "run_switch_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.ui_tour:
            running, origin = stack(env, workspace, python)
            try:
                tour = drive("tour", origin, Path(args.users_file), out / "tour.json", out / "tour_shots", out / "publisher_logs", env)
                tags.append(tour["tag"])
            finally:
                running.shutdown()
            print(json.dumps({"status": "TOUR_DONE", "routes": tour["routes_toured"], "hardware_run": tour["hardware_run"]["run_id"]}))
            return 0
        if args.away_seconds:
            running, origin = stack(env, workspace, python)
            try:
                env["NHM_AWAY_SECONDS"] = str(args.away_seconds)
                away = drive("away", origin, Path(args.users_file), out / "away.json", out / "away_shots", out / "publisher_logs", env)
                tags.append(away["tag"])
            finally:
                running.shutdown()
            inserted = [e for e in (replica.events() if replica else []) if e.get("event") == "insert_ok"]
            def wall_ms(e):
                return datetime.fromisoformat(e["t_wall"]).timestamp() * 1000
            during = [e for e in inserted if away["left_at_ms"] <= wall_ms(e) <= away["returned_at_ms"]]
            final = away["stopped"]["count"]
            checks = {
                "same_session_after_return": away["session_id"] == away["session_id_after_return"],
                "session_active_while_away": away["history_shows_active_while_away"],
                "monitor_reattached_not_restarted": away["just_returned"]["count"] >= away["before_leave"]["count"],
                "records_written_while_away": len(during),
                "count_equals_replica_inserts": final == len(inserted),
                "missed_readings_captured": final >= away["before_leave"]["count"] + len(during),
                "stopped_count_stable": away["stopped"]["count"] == away["stopped_stable"]["count"],
                "retention_not_exceeded": len(inserted) <= 2000,
            }
            ok = all(v is True or (isinstance(v, int) and not isinstance(v, bool)) for v in checks.values()) and checks["records_written_while_away"] > 0
            verdict = {"status": "PASS" if ok else "FAIL", "mode": "away_lifecycle", "away_seconds": away["away_seconds"], "checks": checks,
                       "replica_inserts_total": len(inserted), "count_before_leave": away["before_leave"]["count"],
                       "count_just_returned": away["just_returned"]["count"], "count_after_catch_up": away["after_catch_up"]["count"],
                       "count_final_stopped": final, "demo_fl_completed": bool(away["demo_fl"]["fedavg"]),
                       "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA" if ws_mode else "VERIFIED_DIRECT_ATLAS_INJECTION"}
            (out / "away_lifecycle_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if ok else 1
        if args.soak_seconds:
            running, origin = stack(env, workspace, python)
            try:
                env["NHM_SOAK_SECONDS"] = str(args.soak_seconds)
                soak = drive("soak", origin, Path(args.users_file), out / "soak.json", out / "soak_shots", out / "publisher_logs", env)
                tags.append(soak["tag"])
            finally:
                running.shutdown()
            samples = soak["samples"]
            heaps = [x["heap"] for x in samples if x.get("heap")]
            verdict = {"status": "PASS" if samples and not any(x["alert"] for x in samples) and soak["stopped"]["state"] == "SESSION STOPPED" else "FAIL",
                       "mode": "browser_soak", "seconds": soak["seconds"], "samples": len(samples), "any_poll_error_banner": any(x["alert"] for x in samples),
                       "heap_bytes_first_last_max": [heaps[0], heaps[-1], max(heaps)] if heaps else None,
                       "dom_nodes_first_last": [samples[0]["nodes"], samples[-1]["nodes"]] if samples else None,
                       "plotted_points_max": max((x.get("points") or 0) for x in samples) if samples else None,
                       "record_count_final": soak["stopped"]["count"], "producer": "ESP32_WEBSOCKET_EMULATOR_VIA_LOCAL_RENDER_REPLICA" if ws_mode else "DIRECT",
                       "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA" if ws_mode else "VERIFIED_DIRECT_ATLAS_INJECTION"}
            (out / "browser_soak_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        running, origin = stack(env, workspace, python)
        try:
            first = drive("scenario-a", origin, Path(args.users_file), out / "scenario_a.json", out / "scenario_a_shots", out / "publisher_logs", env)
            tags.append(first["tag"])
        finally:
            running.shutdown()
        # A real backend restart against the same SQLite and artifact workspace.
        running, origin = stack(env, workspace, python)
        try:
            second = drive("scenario-b", origin, Path(args.users_file), out / "scenario_b.json", out / "scenario_b_shots", out / "publisher_logs", env, expected=first["session_id"])
            tags.append(second["tag"])
            owner = drive("owner-probe", origin, Path(args.users_file), out / "owner_probe.json", out / "owner_probe_shots", out / "publisher_logs", env, who="B", expected=first["session_id"])
        finally:
            running.shutdown()
        verdict = {
            "status": "PASS" if (
                first["waiting"]["state"] == "WAITING FOR DATA" and first["live"]["points"] > 0 and
                abs(first["live"]["latest_y"] - first["live"]["expected_y"]) < 1e-9 and first["live"]["latest_x"] == 1000 and
                first["stale"]["state"] == "STALE DATA" and first["recovered"]["state"] == "LIVE DATA RECEIVED" and
                first["stopped"]["state"] == "SESSION STOPPED" and second["prior_history_after_restart"] and
                second["first_stop"]["count"] == second["first_after_stop"]["count"] and second["separate_sessions"] and
                owner["detail_refused"] and owner["target_absent_from_demo_sources"]
            ) else "FAIL",
            "real_chrome": True, "real_clerk_test_users": 2,
            "actual_atlas_collection": f"{database}.records_*" if ws_mode else "health_db.nhm_integration_test",
            "producer": "ESP32_WEBSOCKET_EMULATOR_VIA_LOCAL_RENDER_REPLICA" if ws_mode else "DIRECT_ATLAS_INJECTION",
            "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA" if ws_mode else "VERIFIED_DIRECT_ATLAS_INJECTION",
            "real_render_verified": False, "physical_esp32_verified": False,
            "scenario_a_session": first["session_id"], "scenario_b_sessions": [second["first_session_id"], second["second_session_id"]],
            "backend_restart_between_scenarios": True, "owner_probe": owner,
            "screenshots": sorted(str(p.relative_to(out)) for p in out.rglob("*.png")),
        }
        (out / "browser_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": verdict["status"], "evidence": str(out / "browser_verdict.json")}))
        return 0 if verdict["status"] == "PASS" else 1
    finally:
        if replica is not None:
            replica.stop()
        uri = env.get("NHM_HARDWARE_MONGO_URI")
        if uri and tags:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            db = client[database]
            if ws_mode:
                cleanup, dropped = {}, []
                for name in db.list_collection_names():
                    if name.startswith("records_"):
                        for tag in tags:
                            n = db[name].delete_many({"nhmTestRun": tag}).deleted_count
                            if n:
                                cleanup[f"{name}:{tag}"] = n
                        if db[name].estimated_document_count() == 0:
                            db.drop_collection(name)
                            dropped.append(name)
                payload = {"deleted_by_tag": cleanup, "dropped_empty_collections": dropped, "production_data_deleted": False, "database": database}
            else:
                collection = db["nhm_integration_test"]
                payload = {"deleted_by_tag": {tag: collection.delete_many({"nhmTestRun": tag}).deleted_count for tag in tags}, "production_data_deleted": False}
            (out / "browser_atlas_cleanup.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            client.close()

if __name__ == "__main__":
    raise SystemExit(main())
