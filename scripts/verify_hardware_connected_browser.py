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
    parser.add_argument("--journey", action="store_true", help="full simulated-hardware journey: sketch-faithful emulator -> local Render replica -> Atlas rehearsal DB -> live monitoring, recording, History, Observatory replay + trace, tabular and pretrained-V2 FL, high-gain negative case")
    parser.add_argument("--demo-session", action="store_true", help="the prerecorded DEMO hardware session: seeded in its own Atlas rehearsal collection, imported into History, Observatory replay + trace, pretrained-V2 and tabular runs")
    parser.add_argument("--ui-shots", action="store_true", help="screenshots of the federation starter in every source-mode state")
    parser.add_argument("--history-source", action="store_true", help="a completed simulated monitoring session from History as the signal of one federation client")
    parser.add_argument("--hardware-v2", action="store_true", help="pretrained-V2 recorded-hardware path: two recordings, Observatory replay + trace, V2 run, generalisation tab, federation journal replay")
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
        if args.ui_shots:
            running, origin = stack(env, workspace, python)
            try:
                drive("ui-shots", origin, Path(args.users_file), out / "ui_shots.json", out / "shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            print(json.dumps({"status": "UI_SHOTS_DONE", "dir": str(out / "shots")}))
            return 0
        if args.history_source:
            running, origin = stack(env, workspace, python)
            try:
                hs = drive("history-source", origin, Path(args.users_file), out / "history_source.json", out / "hs_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            live = hs["live"]
            checks = {
                "run_completed": "COMPLETED" in live["status_line"],
                "badge_names_history_session_and_site": live["badge"] == "HISTORY SESSION · SITE_00",
                "eight_synthetic_namespace_clients": len(live["clients"]) == 8 and all(c.startswith("SIM_FL_SITE_") for c in live["clients"]),
                "session_signal_is_the_chosen_clients_data": any(c == "SIM_FL_SITE_00" and n not in (None, "--", "93") for c, n in live["local_examples"]),
                "labels_are_named_synthetic_assigned": "synthetic-assigned" in hs["source_note"],
                "overview_names_history_session": "HISTORY MONITORING SESSION SIGNAL" in hs["overview"] and "Monitoring sessions executed: 0" in hs["overview"],
                "metrics_shown": bool(live["metric_auprc"]) and "NOT YET" not in live["metric_auprc"],
                "no_alerts": not live["alerts"] and not hs["replay"]["alerts"],
                "federation_replay_opens": hs["replay"]["controls"],
            }
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "history_source", "checks": checks, "run_id": hs["run_id"], "session_id": hs["session_id"]}
            (out / "history_source_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.journey:
            if not ws_mode:
                raise SystemExit("--journey needs --producer ws")
            import re

            env["NHM_VITALS"] = "sketch"
            running, origin = stack(env, workspace, python)
            try:
                j = drive("journey", origin, Path(args.users_file), out / "journey.json", out / "journey_shots", out / "publisher_logs", env)
                tags.extend(f"{j['tag']}-{n}" for n in ("A", "B", "C"))
            finally:
                running.shutdown()
            inserted = [e for e in (replica.events() if replica else []) if e.get("event") == "insert_ok"]

            def wall_ms(e):
                return datetime.fromisoformat(e["t_wall"]).timestamp() * 1000

            def inserts_of(x):
                return sum(1 for e in inserted if x["started_ms"] - 2000 <= wall_ms(e) <= x["ended_ms"] + 4000)

            A, B, C = (j["sessions"][k] for k in ("A", "B", "C"))
            snap = lambda x, name: next(sn for sn in x["snaps"] if sn["name"] == name)  # noqa: E731
            num = lambda t: int(t) if str(t).strip().isdigit() else None  # noqa: E731
            sc = lambda t: int(m.group(1)) if (m := re.search(r"(\d+) scored", t)) else -1  # noqa: E731
            rej = lambda t: int(m.group(1)) if (m := re.search(r"(\d+) rejected", t)) else -1  # noqa: E731
            emitted = lambda t: int(m.group(1)) if (m := re.search(r"(\d+) windows emitted", t)) else -1  # noqa: E731
            live, fr, lo, again = snap(A, "live"), snap(A, "finger_removed"), snap(A, "leads_off"), snap(A, "recovered_live")
            asleep, woken, stale = snap(A, "render_asleep"), snap(A, "render_woken_after_14s"), snap(A, "wifi_dropped_stale")
            rejected_handshakes = sum(1 for e in (replica.events() if replica else []) if e.get("event") == "handshake_rejected")
            ra, rc = j["replay"]["A"], j["replay"]["C"]
            tv, tb = j["trace"]["valid"], j["trace"]["rejected"]
            ta, tB = j["tabular"]["A"], j["tabular"]["B"]
            v2 = j["v2"]
            checks = {
                "live_monitoring_receives_and_plots": "LIVE" in live["state"] and live["count"] > 100 and live["points"] > 0,
                "render_cold_start_waits_without_fabricating_data": asleep["state"] == "WAITING FOR DATA" and asleep["count"] == 0 and woken["count"] == 0 and rejected_handshakes >= 1,
                "wifi_drop_goes_stale_then_recovers": "STALE" in stale["state"] and "LIVE" in again["state"],
                "bpm_is_the_firmwares_mock_72_to_81": num(live["bpm"]) is not None and 72 <= num(live["bpm"]) <= 81,
                "spo2_is_ratio_based_90_to_100": bool(re.fullmatch(r"(9\d|100)%", live["spo2"])),
                "finger_removed_shows_unavailable_not_zero": fr["bpm"] == "Unavailable" and fr["spo2"] == "Unavailable",
                "leads_off_shows_the_flat_placeholder": lo["latest_ecg"] == 2048,
                "stops_cleanly_and_keeps_the_count": snap(A, "stopped")["state"] == "SESSION STOPPED" and snap(A, "stopped")["count"] >= 1900,
                "mongo_count_equals_replica_inserts_A": snap(A, "stopped")["count"] == inserts_of(A),
                "mongo_count_equals_replica_inserts_B": snap(B, "stopped")["count"] == inserts_of(B),
                "mongo_count_equals_replica_inserts_C": snap(C, "stopped")["count"] == inserts_of(C),
                "history_links": all(j["detail"].values()),
                "replay_A_scores_every_usable_window": sc(ra["summary"]) > 5 and "pending" not in ra["summary"] and ra["controls"] and ra["chart_points"] > 0 and bool(ra["transitions"]),
                "replay_A_rejects_the_leads_off_stretch": rej(ra["summary"]) >= 1,
                "replay_A_clean": not ra["alerts"] and not ra["errors"],
                "replay_C_highgain_all_rejected_and_explained": emitted(rc["summary"]) > 0 and rej(rc["summary"]) == emitted(rc["summary"]) and sc(rc["summary"]) == 0 and "quality gate" in rc["empty"],
                "replay_C_clean": not rc["alerts"] and not rc["errors"],
                "trace_valid_window": "RECORDED HARDWARE" in tv["classification"] and tv["stages"] >= 4 and bool(tv["inference"]),
                "trace_rejected_window_has_no_invented_result": bool(tb) and "UNUSABLE" in tb["window"] and not tb["has_inference"] and "no model result" in tb["none"],
                "tabular_fedavg_completed": "COMPLETED" in ta["status_line"] and len(ta["card_tags"] if isinstance(ta["card_tags"], list) else []) >= 0 and ta["card_tags"] == 8 and bool(ta["metric_auprc"]),
                "tabular_fedprox_shadow_verified": "COMPLETED" in tB["status_line"] and "VERIFIED" in tB["secagg"].upper() and tB["card_tags"] == 8,
                "v2_refuses_the_highgain_recording_with_reason": "NOT ENOUGH" in v2["preview_c"]["text"] and "CLIPPING" in v2["preview_c"]["text"] and v2["preview_c"]["start_disabled"],
                "v2_accepts_the_good_recordings": "ENOUGH USABLE" in v2["preview_ab"]["text"] and not v2["preview_ab"]["start_disabled"],
                "v2_run_one_recorded_client_plus_seven_peers": v2["live"]["badge"] == "RECORDED HARDWARE" and v2["live"]["clients"][0] == "RECORDED_DEMO_CLIENT_00" and all(c.startswith("SIM_FL_SITE_") for c in v2["live"]["clients"][1:]) and len(v2["live"]["clients"]) == 8,
                "v2_run_has_metrics_and_generalisation": "pretrained V2" in v2["live"]["label"] and bool(v2["live"]["metric_auprc"]) and v2["generalisation"].startswith("4/4") and not v2["live"]["alerts"],
            }
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "simulated_hardware_journey", "checks": checks, "plan": j["plan"], "plan_b": j.get("plan_b"), "rejected_handshakes": rejected_handshakes, "v2_run_id": v2["run_id"],
                       "replica_inserts_total": len(inserted), "sessions": {k: j["sessions"][k]["sid"] for k in ("A", "B", "C")},
                       "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA", "real_render_verified": False, "physical_esp32_verified": False,
                       "firmware_behaviour_modelled": "supplied sketch: mock BPM random(72,82) every 2 s, drifting ratio SpO2, hyper-realistic AD8232 ECG (HRV, respiration, mains pickup aliased by ~17 Hz sampling, motion bursts, ~1860-count module offset), boot with electrodes off during a Render cold start (handshakes rejected ~14 s), finger removal, leads off, 9 s Wi-Fi drop; high-gain variant for the negative case"}
            (out / "journey_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.hardware_v2:
            if not ws_mode:
                raise SystemExit("--hardware-v2 needs --producer ws (the AD8232-amplitude emulator pattern through the local replica)")
            env["NHM_PATTERN"] = "ecg_ad8232"
            running, origin = stack(env, workspace, python)
            try:
                v2 = drive("v2", origin, Path(args.users_file), out / "v2.json", out / "v2_shots", out / "publisher_logs", env)
                tags.extend(f"{v2['tag']}-{n}" for n in (1, 2))
            finally:
                running.shutdown()
            live, gen, single, both = v2["live"], v2["generalisation"], v2["single_session_preview"], v2["two_session_preview"]
            rounds_scored = gen["progress"].split(" ")[0]
            checks = {
                "history_links": bool(v2["history_links"]["replay"]) and bool(v2["history_links"]["trace"]) and v2["monitor_replay_link"],
                "replay_hardware_tag": "RECORDED HARDWARE" in v2["replay"]["tag"] and "NOT DIAGNOSTIC" in v2["replay"]["tag"],
                "replay_scored_windows": "scored" in v2["replay"]["summary"] and v2["replay"]["has_controls"] and v2["replay"]["chart_points"] > 0 and "calibrated" in v2["replay"]["state"],
                "replay_no_alerts": not v2["replay"]["alerts"],
                "replay_every_usable_window_scored": "pending" not in v2["replay"]["summary"] and "0 rejected" in v2["replay"]["summary"] or "rejected by the quality gate" in v2["replay"]["summary"] and "pending" not in v2["replay"]["summary"],
                "trace_recorded_hardware": "RECORDED HARDWARE" in v2["trace"]["classification"] and v2["trace"]["stages"] >= 4 and not v2["trace"]["alerts"],
                "trace_next_window_moves": v2["trace_next_window"] != v2["trace"]["window_control"],
                "observatory_no_console_or_http_errors": not v2["observatory_console_errors"],
                "v2_option_enabled": any(o["value"] == "MODEL_V2_FINAL" and not o["disabled"] for o in v2["init_options"]),
                "single_session_preview_reported": "training" in single["text"] and "holdout" in single["text"] and (single["start_disabled"] == ("NOT ENOUGH" in single["text"])),
                "two_sessions_accepted": "ENOUGH USABLE" in both["text"] and "NOT ENOUGH" not in both["text"] and not both["start_disabled"],
                "run_completed": "COMPLETED" in live["status_line"],
                "run_is_recorded_hardware_v2": live["badge"] == "RECORDED HARDWARE" and "pretrained V2" in live["label"] and len(live["clients"]) == 8 and live["clients"][0] == "RECORDED_DEMO_CLIENT_00" and all(c.startswith("SIM_FL_SITE_") for c in live["clients"][1:]),
                "one_recorded_card_and_seven_peers": live["recorded_cards"] == 1 and live["peer_cards"] == 7 and "seven" in live["hw_participation"],
                "run_metrics_shown": bool(live["metric_auprc"]) and "NOT YET" not in live["metric_auprc"],
                "secagg_shadow_reported": "VERIF" in live["secagg"].upper() or "SHADOW" in live["secagg"].upper(),
                "generalisation_available": bool(gen["progress"]) and not gen["unavailable"] and "MODEL_V2_FINAL" in gen["base_model"],
                "generalisation_all_rounds_scored": rounds_scored.split("/")[0] == rounds_scored.split("/")[-1] if "/" in rounds_scored else False,
                "r0_identical_to_frozen_v2": gen["r0_identical"],
                "federation_replay_lists_hardware_run": "RECORDED HARDWARE" in (v2["fed_replay"]["option"] or "") and len(v2["fed_replay"]["clients"]) == 8 and v2["fed_replay"]["clients"][0] == "RECORDED_DEMO_CLIENT_00" and all(c.startswith("SIM_FL_SITE_") for c in v2["fed_replay"]["clients"][1:]),
                "federation_replay_round_jumps": len(v2["fed_replay"]["jumps"]) >= 2 and not v2["fed_replay"]["alerts"],
            }
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "hardware_v2", "checks": checks, "run_id": v2["run_id"], "sessions": v2["session_ids"],
                       "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA", "real_render_verified": False, "physical_esp32_verified": False, "observatory_console_errors": v2["observatory_console_errors"]}
            (out / "hardware_v2_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.demo_session:
            if not ws_mode:
                raise SystemExit("--demo-session needs --producer ws (isolated rehearsal database)")
            from pymongo import MongoClient

            from product.hardware_demo_session import DEMO_COLLECTION

            # App-init path under test: the collection is removed first, and no demo setting is passed, so the product app itself must create it (default-on) and import it into History.
            demo_collection = MongoClient(env["NHM_HARDWARE_MONGO_URI"], serverSelectionTimeoutMS=5000)[database][DEMO_COLLECTION]
            demo_collection.drop()
            env.pop("NHM_HARDWARE_DEMO_COLLECTION", None)
            running, origin = stack(env, workspace, python)
            try:
                demo = drive("demo-session", origin, Path(args.users_file), out / "demo_session.json", out / "demo_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            seeded = demo_collection.count_documents({})
            r = demo["replay"]
            checks = {
                "app_init_created_the_collection_in_mongo": seeded > 4000,
                "listed_in_history_as_saved": demo["session_id"].startswith("HW-SHOWCASE-") and "SAVED" in demo["history_row"] and str(seeded) in demo["history_row"],
                "history_links": bool(demo["history_links"]["replay"]) and bool(demo["history_links"]["trace"]),
                "history_evidence_scored_windows": demo["evidence"]["rows"] >= 25 and demo["evidence"]["events"] > 25 and bool(demo["evidence"]["states"]) and not demo["evidence"]["alerts"] and "CONTEXT_UNAVAILABLE" not in " ".join(demo["evidence"]["states"]),
                "replay_hardware_tag": "RECORDED HARDWARE" in r["tag"] and "NOT DIAGNOSTIC" in r["tag"],
                "replay_scored_windows": "scored" in r["summary"] and "pending" not in r["summary"] and r["has_controls"] and r["chart_points"] > 0,
                "replay_no_alerts": not r["alerts"],
                "trace_recorded_hardware": "RECORDED HARDWARE" in demo["trace"]["classification"] and demo["trace"]["stages"] >= 4 and not demo["trace"]["alerts"],
                "observatory_no_console_or_http_errors": not demo["observatory_console_errors"],
                "single_demo_session_enough_for_v2": all("ENOUGH USABLE" in x["preview"]["text"] and not x["preview"]["start_disabled"] for x in demo["v2_runs"]),
                **{f"v2_{x['rounds']}_rounds_completed_one_recorded_plus_seven": "COMPLETED" in x["live"]["status_line"] and x["live"]["badge"] == "RECORDED HARDWARE" and "pretrained V2" in x["live"]["label"] and x["live"]["recorded_cards"] == 1 and x["live"]["peer_cards"] == 7 and bool(x["live"]["metric_auprc"]) and f"{x['rounds']}-round" in x["live"]["label"] for x in demo["v2_runs"]},
                **{f"v2_{x['rounds']}_rounds_same_evaluation_as_synthetic_v2": "1446 windows" in x["live"]["metric_cohort"] and any(ch.isdigit() for ch in x["live"]["metric_auprc"]) and "16 participants" in x["live"]["metric_cohort"] and x["live"]["candidate_panel"] and not x["live"]["backend_error"] and not x["live"]["final_state_panel"] and any("1 recorded client" in c for c in x["live"]["chips"]) for x in demo["v2_runs"]},
                **{f"tabular_{x['rounds']}_rounds_completed": "COMPLETED" in x["live"]["status_line"] and bool(x["live"]["metric_auprc"]) and not x["live"]["alerts"] for x in demo["tabular_runs"]},
            }
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "demo_session", "checks": checks, "session_id": demo["session_id"], "v2_run_ids": [x["run_id"] for x in demo["v2_runs"]], "documents_seeded": seeded,
                       "database": database, "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA", "real_render_verified": False, "physical_esp32_verified": False, "generated_not_recorded": True}
            (out / "demo_session_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
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
