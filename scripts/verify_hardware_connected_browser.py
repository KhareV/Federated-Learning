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
        result = subprocess.run(command, cwd=ROOT, env=run_env, capture_output=True, text=True, timeout=int(os.environ.get("NHM_DRIVER_TIMEOUT", "1800")))      # the full matrix of ~19 runs needs more than the default half hour
    finally:
        browser.close(); shutil.rmtree(profile, ignore_errors=True)
    if result.returncode or not out.exists():
        raise RuntimeError(f"browser {mode} failed: {(result.stdout + result.stderr)[-1200:]}")
    return json.loads(out.read_text())


def _floats(text: str) -> list[float]:
    import re

    return [float(x) for x in re.findall(r"-?\d+\.\d+", text or "")]


def ui_round_mismatches(step: dict, run_dir: Path) -> list[str]:
    """The values the page showed for each round against the stored evaluation records (the UI rounds its numbers: a match is within the display precision)."""
    problems = []
    for entry in step.get("ui_rounds", []):
        r = int(entry["button"].rsplit("R", 1)[1])
        path = run_dir / "eval" / f"R{r:02d}" / "record.json"
        if not path.exists():
            problems.append(f"R{r}: no stored record")
            continue
        stored = json.loads(path.read_text())["metric_result"]
        for key in ("AUPRC", "AUROC", "F1", "BCE", "accuracy", "precision", "recall", "specificity"):
            shown = _floats(entry.get(key, ""))
            if stored.get(key) is None or not shown:
                continue                                                                       # an undefined metric is shown as such, never as a number
            if not any(abs(v - float(stored[key])) <= 6e-7 for v in shown):
                problems.append(f"R{r} {key}: page {shown} vs stored {stored[key]}")
    return problems


def fl_matrix_checks(mx: dict, verification: dict | None = None, studio_root: Path | None = None) -> dict[str, bool]:
    """Checks of the federated-run matrix browser run: per run, labels, scoring, the journal replay and (for candidate starts) the starting model."""
    metric_id = {"ORIGINAL": "FL10", "REALISTIC": "REALISTIC_EVAL_COHORT_V2", "REALISTIC_NSTDB": "REALISTIC_EVAL_COHORT_V3"}
    checks: dict[str, bool] = {}
    for st in mx["steps"]:
        tag, plan = st["tag"], st["plan"]
        live, replay = st.get("live"), st.get("replay")
        ok = "error" not in st and live is not None and replay is not None
        if verification is not None and studio_root is not None and st.get("run_id") in verification and "error" not in st:
            v = verification[st["run_id"]]
            checks[f"{tag}_every_round_value_verified_independently"] = bool(v["ok"]) and len(v["rounds"]) == st["plan"]["rounds"] + 1
            checks[f"{tag}_the_page_shows_the_stored_value_of_every_round"] = not ui_round_mismatches(st, studio_root / st["run_id"]) and len(st.get("ui_rounds", [])) == st["plan"]["rounds"] + 1
        checks[f"{tag}_ran_without_error"] = ok
        if not ok:
            continue
        cohort, rounds = plan["cohort"], plan["rounds"]
        checks[f"{tag}_completed_with_eight_clients_and_scores"] = ("COMPLETED" in live["status_line"] and live["clients"] == [f"SIM_FL_SITE_0{i}" for i in range(8)]
                                                                   and bool(live["metric_auprc"]) and not any(w in live["metric_auprc"] for w in ("NOT YET", "EVALUATING", "QUEUED")) and not live["alerts"])
        if not plan.get("frozenForm"):                                      # the frozen 3-round contract has its own evaluation wording
            checks[f"{tag}_scored_on_its_cohorts_holdout"] = metric_id[cohort] in live["metric_cohort"]
        checks[f"{tag}_badge_names_the_cohort"] = (("RECORDED NOISE" in live["badge"]) if cohort == "REALISTIC_NSTDB" else ("REALISTIC" in live["badge"] and "RECORDED NOISE" not in live["badge"]) if cohort == "REALISTIC" else "REALISTIC" not in live["badge"])
        if replay.get("skipped"):                                            # the frozen product 3-round run is not a Studio run
            continue
        b, a = replay["before"], replay["after"]
        checks[f"{tag}_replay_lists_every_round_and_is_labelled"] = b["jumps"] == len({1, (rounds + 1) // 2, rounds}) and "NO LOCAL TRAINING" in b["label"] and b["clients"] >= 8 and not a["alerts"] and bool(b["scrub"])
        checks[f"{tag}_replay_shows_the_candidate_at_the_end"] = a["from_record"] or "andidate" in a["candidate_text"]
        if plan["init"] == "CANDIDATE":
            cf = st.get("candidate_form") or {}
            checks[f"{tag}_started_from_the_stored_candidate"] = plan.get("candidateId", "FL10_CANDIDATE_") in live["start_candidate"] and "Round 0 is that candidate" in live["start_candidate"] and bool(cf.get("note"))
            if plan.get("candidateId", "").startswith("RESEARCH_"):
                checks[f"{tag}_names_real_patients_not_a_synthetic_cohort"] = "no synthetic cohort" in live["start_candidate"]
    lib = mx.get("library") or {"cards": [], "groups": 0, "alerts": ["missing"]}
    cohorts_listed = {c["cohort"] for c in lib["cards"]}
    checks["models_page_lists_the_imported_and_every_cohort_candidate"] = ({"REAL_ECG", "ORIGINAL", "REALISTIC", "REALISTIC_NSTDB"} <= cohorts_listed and any(c["id"] == "RESEARCH_FL_V2_FL001_R50" for c in lib["cards"]) and lib["groups"] >= 2 and not lib["alerts"])
    groups = lib.get("training_groups") or []
    order = ["ORIGINAL", "REALISTIC", "REALISTIC_NSTDB", "REAL_ECG"]
    checks["models_page_segregates_candidates_by_the_cohort_they_were_trained_on"] = (bool(groups) and [g["cohort"] for g in groups] == [c for c in order if c in {g["cohort"] for g in groups}]
                                                                                     and all(g["member_cohorts"] and set(g["member_cohorts"]) == {g["cohort"]} for g in groups) and sum(len(g["member_cohorts"]) for g in groups) == len(lib["cards"]))
    sl = lib.get("shortlist") or {}
    entries = sl.get("entries") or []
    checks["upgrade_shortlist_lists_every_stored_candidate_and_is_read_only"] = (bool(sl.get("present")) and {e["id"] for e in entries} == {c["id"] for c in lib["cards"]} and "NOT AN UPGRADE" in sl.get("boundary", "") and sl.get("buttons") == 0)
    checks["upgrade_shortlist_never_shortlists_a_synthetic_or_assigned_label_candidate"] = all(e["tier"] == "NOT_SHORTLISTED" for e in entries if not e["id"].startswith("RESEARCH_")) and all(e["tier"] in ("COMPARABLE_NOT_BETTER", "SHORTLISTED_FOR_REVIEW") for e in entries if e["id"].startswith("RESEARCH_"))
    return checks


def hardware_combos_checks(hc: dict, verification: dict | None = None, studio_root: Path | None = None) -> dict[str, bool]:
    """Checks of the hardware starting-model x cohort matrix: every combination starts, completes, says what it started from and is scored on its cohort's holdout."""
    metric_id = {"ORIGINAL": "FL10", "REALISTIC": "REALISTIC_EVAL_COHORT_V2", "REALISTIC_NSTDB": "REALISTIC_EVAL_COHORT_V3"}
    checks: dict[str, bool] = {}
    first = next((s.get("run_id") for s in hc["steps"] if s["plan"]["init"] == "MODEL_V2_FINAL"), None)
    for st in hc["steps"]:
        tag, plan = st["tag"], st["plan"]
        live, form = st.get("live"), st.get("form") or {}
        ok = "error" not in st and live is not None
        checks[f"{tag}_started_completed_and_scored"] = ok and "COMPLETED" in live["status_line"] and live["badge"] == "RECORDED HARDWARE" and not live["backend_error"] and not live["alerts"] and not form.get("start_disabled") and bool(live["metric_auprc"]) and not any(w in live["metric_auprc"] for w in ("NOT YET", "EVALUATING", "QUEUED"))
        if not ok:
            continue
        if plan["init"] == "FRESH_SEEDED":
            checks[f"{tag}_tabular_clients_and_cohort_note"] = all(c.startswith("RECORDED_DEMO_CLIENT") for c in live["clients"]) and len(live["clients"]) == 8 and (("not used by this run" in form.get("unused_note", "")) == (plan["cohort"] != "ORIGINAL"))
            continue
        checks[f"{tag}_one_recorded_client_plus_seven_peers"] = len(live["clients"]) == 8 and live["clients"][0] == "RECORDED_DEMO_CLIENT_00" and all(c.startswith("SIM_FL_SITE_") for c in live["clients"][1:])
        windows = {"ORIGINAL": 1446, "REALISTIC": 1433, "REALISTIC_NSTDB": 1446}[plan["cohort"]]
        checks[f"{tag}_scored_on_its_cohorts_holdout"] = f"{windows} windows" in live["metric_cohort"] and "16 participants" in live["metric_cohort"] and metric_id[plan["cohort"]] in live["metric_cohort"]
        if plan["init"] == "FL_INIT_V2":
            checks[f"{tag}_says_it_started_untrained"] = "untrained V2 network (FL_INIT_V2)" in live["start_untrained"] and "untrained V2" in live["glance"] and "pretrained" not in live["start_untrained"].lower().replace("nothing is pretrained", "")
        elif plan["init"] == "CANDIDATE":
            picker = st.get("candidate_picker") or {}
            checks[f"{tag}_started_from_the_stored_candidate"] = bool(first) and first in live["start_candidate"] and "Round 0 is that candidate" in live["start_candidate"] and bool(picker.get("groups"))
        else:
            checks[f"{tag}_says_pretrained"] = "pretrained V2" in live["glance"] and not live["start_untrained"]
        if verification is not None and studio_root is not None and st.get("run_id") in verification:
            v = verification[st["run_id"]]
            checks[f"{tag}_every_round_value_verified_independently"] = bool(v["ok"]) and len(v["rounds"]) == plan["rounds"] + 1
    lib = hc.get("library") or {"cards": [], "training_groups": []}
    groups = lib.get("training_groups") or []
    checks["models_page_segregates_the_new_candidates_by_training_cohort"] = (bool(groups) and all(g["member_cohorts"] and set(g["member_cohorts"]) == {g["cohort"]} for g in groups) and sum(len(g["member_cohorts"]) for g in groups) == len(lib["cards"])
                                                                              and {c["cohort"] for c in lib["cards"]} >= {"ORIGINAL", "REALISTIC", "REALISTIC_NSTDB"} and lib.get("shortlist_entries") == len(lib["cards"]))
    return checks


def recorded_noise_checks(rn: dict) -> dict[str, bool]:
    """Checks of the recorded-noise cohort browser run."""
    r = rn["run"]
    d, c, live = r["defaults"], r["chosen"], r["live"]
    return {
        "three_cohort_buttons_offered": d["buttons"] == ["cohort-original", "cohort-realistic", "cohort-realistic-nstdb"],
        "original_is_still_the_default": d["original_checked"] == "true" and d["nstdb_checked"] == "false",
        "recorded_noise_choice_is_kept": c["nstdb_checked"] == "true" and c["realistic_checked"] == "false" and c["fixed_cohort"] == "REALISTIC_NSTDB",
        "note_names_the_recorded_noise": "recorded" in c["note"].lower() and "noise" in c["note"].lower() and "frozen" not in c["source_note"].lower(),
        "run_completed": "COMPLETED" in live["status_line"],
        "badge_names_the_recorded_noise_cohort": "RECORDED NOISE" in live["badge"],
        "eight_site_clients": live["clients"] == [f"SIM_FL_SITE_0{i}" for i in range(8)],
        "scored_on_its_own_holdout": "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3" in live["metric_cohort"] and live["body_has_recorded_noise_use"] and not live["body_has_frozen_reuse"],
        "metrics_shown": bool(live["metric_auprc"]) and not any(w in live["metric_auprc"] for w in ("NOT YET", "EVALUATING", "QUEUED")),
        "no_alerts": not live["alerts"],
    }


def external_check_checks(ec: dict) -> dict[str, bool]:
    """Checks of the external-check page browser run."""
    p = ec["primary"]
    return {
        "reached_from_the_observatory_nav": p["h1"].startswith("External check"),
        "boundaries_are_shown": "NOT AAMI-SVF" in p["label"] and "NOT CLINICAL" in p["label"] and "no clinical" in p["boundary"].lower() and p["body_has_removed_scope"],
        "all_six_models_are_listed": len(p["models"]) == 6 and p["models"][0].startswith("MODEL_V1") and any("round 50" in m for m in p["models"]),
        "values_come_from_the_report": "0.911" in p["first_row"] or "0.701" in p["first_row"],
        "label_rules_and_error_analysis_shown": "rule" in p["rules"].lower() or "union" in p["rules"].lower(),
        "report_and_protocol_hashes_shown": "SHA-256" in p["hashes"] and "verified" in p["hashes"],
        "no_alerts": not p["alerts"],
        "set_selector_switches_to_replication": "17,199 records" in ec["replication"]["text"] and ec["replication"]["pressed"] == "true",
        "no_horizontal_scroll_on_a_phone": ec["phone"]["scroll"] <= ec["phone"]["inner"],
    }


def demo_path_checks(dp: dict) -> dict[str, bool]:
    """Checks of the guided-demonstration-path browser run."""
    steps = dp["page"]["steps"]
    hrefs = [x["href"] for x in steps]
    modes = {x["mode"] for x in steps}
    return {
        "reached_from_the_overview": dp["page"]["h1"].startswith("One story"),
        "eight_steps_with_four_fields_each": len(steps) == 8 and all(x["fields"] == 4 for x in steps),
        "every_step_names_how_its_evidence_is_produced": all(x["mode"] for x in steps) and dp["page"]["mode_legend"] == 6,
        "live_and_recorded_modes_are_distinct": any("LIVE" in m for m in modes) and any("RECORDED" in m or "FROZEN" in m for m in modes),
        "heading_receives_focus_after_navigation": dp["page"]["focused_tag"] == "H1",
        "keyboard_reaches_every_step_link_in_order": dp["keyboard_reached"][: len(hrefs)] == hrefs,
        "every_target_page_exists": all(t["h1"] and not t["not_found"] for t in dp["targets"]),
        "no_alerts": not dp["page"]["alerts"],
        "tour_and_storyboard_link_back": bool(dp["banner_tour"]) and bool(dp["banner_storyboard"]),
        "no_horizontal_scroll_on_a_phone": dp["phone"]["scroll"] <= dp["phone"]["inner"],
        "presenter_mode_starts_steps_pauses_and_stops": (dp["presenter"]["before"] == "" and "1/8" in dp["presenter"]["started"] and "2/8" in dp["presenter"]["after_next"] and "1/8" in dp["presenter"]["after_prev"]
                                                          and dp["presenter"]["covered"].startswith("1") and dp["presenter"]["paused_stable"] and dp["presenter"]["after_escape"] == ""),
    }


def candidate_library_checks(cl: dict, library_files_ok: bool) -> dict[str, bool]:
    """Checks of the candidate-library browser run. Card text is the page's textContent, in which a label and its value are separate elements (no space between them), so patterns allow zero whitespace."""
    import re

    first_cards, after_cards = cl["models"]["cards"], cl["models_after"]["cards"]
    first_id = first_cards[0]["id"] if first_cards else ""
    second = cl["second"]["live"]
    return {
        "first_run_completed": "COMPLETED" in cl["first"]["live"]["status_line"] and "REALISTIC" in cl["first"]["live"]["badge"],
        "candidate_listed_on_models_page": len(first_cards) == 1 and first_cards[0]["cohort"] == "REALISTIC",
        "candidate_labelled_not_deployed": bool(first_cards) and "NOT DEPLOYED" in first_cards[0]["text"] and "NEVER USED FOR MONITORING" in first_cards[0]["text"],
        "candidate_carries_scores": bool(first_cards) and re.search(r"AUPRC\s*\d\.\d+", first_cards[0]["text"]) is not None,
        "form_offers_the_candidate": first_id in cl["second_form"]["options"] and "R0 is the final state of the candidate chosen below" in cl["second_form"]["init_note"],
        "form_says_cross_cohort": "This run uses the original cohort" in cl["second_form"]["note"],
        "second_run_completed": "COMPLETED" in second["status_line"],
        "second_run_names_its_candidate": first_id in second["start_candidate"] and "trained on the realistic cohort" in second["start_candidate"] and "this run uses the original cohort" in second["start_candidate"],
        "second_run_method_says_candidate_start": "stored candidate start" in second["glance"],
        "second_run_is_original_cohort": "REALISTIC" not in second["badge"],
        "second_run_metrics_shown": bool(second["metric_auprc"]) and not any(w in second["metric_auprc"] for w in ("NOT YET", "EVALUATING", "QUEUED")),
        "library_now_has_both": len(after_cards) == 2 and {c["cohort"] for c in after_cards} == {"REALISTIC", "ORIGINAL"},
        "second_candidate_descends_from_first": any(c["id"] != first_id and re.search(r"Started from\s*candidate\s*" + re.escape(first_id), c["text"]) is not None for c in after_cards),
        "library_files_exist_on_disk": library_files_ok,
        "no_alerts": not cl["first"]["live"]["alerts"] and not second["alerts"],
    }


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
    parser.add_argument("--demo-path", action="store_true", help="the guided demonstration path through the real UI: reachable from the Overview, every step link resolves, keyboard order, phone width")
    parser.add_argument("--external-check", action="store_true", help="the Observatory external-check page through the real UI: reachable, boundaries first, evidence loaded from the hash-verified route, set selector, phone width")
    parser.add_argument("--recorded-noise-cohort", action="store_true", help="the realistic cohort with recorded NSTDB noise through the real starter: a third cohort button and a 3-round pretrained run described, evaluated and labelled as recorded-noise")
    parser.add_argument("--hardware-combos", action="store_true", help="every starting model x synthetic cohort for a recorded-hardware run from one stored session: pretrained V2, untrained V2, stored candidate and the tabular model on the original / realistic / recorded-noise cohort")
    parser.add_argument("--fl-matrix", action="store_true", help="every federated-run flow through the real UI: 3 and 10 rounds, every cohort, untrained and pretrained starts, runs started from stored candidates (one imported research checkpoint), each opened in the Observatory journal replay")
    parser.add_argument("--candidate-library", action="store_true", help="engineering candidates through the real UI: a realistic run is stored, listed on the Models page, and starts a second run on the other cohort")
    parser.add_argument("--realistic-cohort", action="store_true", help="the synthetic-cohort option through the real starter: a realistic 3-round pretrained run and a realistic live-monitored site run")
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
    env["NHM_HARDWARE_DEMO_DATABASE"] = database           # generated demo collections stay in the isolated database too (never the operator's own demo database)
    env["NHM_HARDWARE_MONGO_COLLECTION"] = "records_*" if ws_mode else "nhm_integration_test"
    if not env.get("NHM_CANDIDATE_LIBRARY_DIR"):             # no gate may write its test candidates into the operator's real candidate library (data/studio_candidates): every mode gets a throwaway one
        import atexit

        gate_library = Path(tempfile.mkdtemp(prefix="nhm-gate-library-"))
        env["NHM_CANDIDATE_LIBRARY_DIR"] = str(gate_library)
        atexit.register(shutil.rmtree, gate_library, ignore_errors=True)
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
        if args.fl_matrix:
            library = Path(tempfile.mkdtemp(prefix="nhm-fl-matrix-library-"))
            env["NHM_CANDIDATE_LIBRARY_DIR"] = str(library)            # the gate never touches the real library
            owner = json.loads(Path(args.users_file).read_text())["A"]["user_id"]
            from scripts.register_research_candidates import register_all

            register_all(owner, library)                                  # the two imported 50-round research checkpoints, owned by the gate's user
            running, origin = stack(env, workspace, python)
            try:
                mx = drive("fl-matrix", origin, Path(args.users_file), out / "fl_matrix.json", out / "mx_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            from scripts.verify_fl_rounds import run_dirs, verify_run

            studio_root = workspace / "federation" / "studio_runs"
            verification = {d.name: verify_run(d, rederive={1, 2, 3, 10}) for d in run_dirs(studio_root, None)}
            (out / "fl_round_verification.json").write_text(json.dumps(verification, indent=1, sort_keys=True, default=float) + "\n")
            checks = fl_matrix_checks(mx, verification, studio_root)
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "fl_matrix", "runs": {st["tag"]: st.get("run_id") for st in mx["steps"]}, "checks": checks,
                       "rounds_verified_independently": sum(len(v["rounds"]) for v in verification.values()), "aggregations_rederived_bit_exact": sum(sum(1 for r in v["rounds"].values() if r.get("aggregation_rederivation", {}).get("bit_identical")) for v in verification.values())}
            (out / "fl_matrix_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            shutil.rmtree(library, ignore_errors=True)
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.recorded_noise_cohort:
            running, origin = stack(env, workspace, python)
            try:
                rn = drive("recorded-noise-cohort", origin, Path(args.users_file), out / "recorded_noise_cohort.json", out / "rn_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            checks = recorded_noise_checks(rn)
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "recorded_noise_cohort", "checks": checks, "run": rn["run"]["run_id"]}
            (out / "recorded_noise_cohort_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.external_check:
            running, origin = stack(env, workspace, python)
            try:
                ec = drive("external-check", origin, Path(args.users_file), out / "external_check.json", out / "ec_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            checks = external_check_checks(ec)
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "external_check", "checks": checks}
            (out / "external_check_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.demo_path:
            running, origin = stack(env, workspace, python)
            try:
                dp = drive("demo-path", origin, Path(args.users_file), out / "demo_path.json", out / "dp_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            checks = demo_path_checks(dp)
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "demo_path", "checks": checks}
            (out / "demo_path_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.candidate_library:
            library = Path(tempfile.mkdtemp(prefix="nhm-candidate-library-gate-"))
            env["NHM_CANDIDATE_LIBRARY_DIR"] = str(library)            # the gate never touches the real library
            running, origin = stack(env, workspace, python)
            try:
                cl = drive("candidate-library", origin, Path(args.users_file), out / "candidate_library.json", out / "cl_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            checks = candidate_library_checks(cl, len(list(library.rglob("candidate.json"))) == 2 and len(list(library.rglob("state.bin"))) == 2)
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "candidate_library", "checks": checks, "first_run": cl["first"]["run_id"], "second_run": cl["second"]["run_id"]}
            (out / "candidate_library_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            shutil.rmtree(library, ignore_errors=True)
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
        if args.realistic_cohort:
            running, origin = stack(env, workspace, python)
            try:
                rc = drive("realistic-cohort", origin, Path(args.users_file), out / "realistic_cohort.json", out / "rc_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            checks = {}
            for tag in ("canonical", "monitored"):
                r = rc[tag]
                live, ov = r["live"], r["overview"]
                checks |= {
                    f"{tag}_original_is_the_default": r["defaults"]["original_checked"] == "true" and r["defaults"]["realistic_checked"] == "false",
                    f"{tag}_realistic_choice_is_kept": r["chosen"]["realistic_checked"] == "true" and r["chosen"]["fixed_cohort"] == "REALISTIC" and "premature ectopic beats" in r["chosen"]["note"],
                    f"{tag}_run_completed": "COMPLETED" in live["status_line"],
                    f"{tag}_badge_names_the_realistic_cohort": "REALISTIC" in live["badge"],
                    f"{tag}_eight_site_clients": live["clients"] == [f"SIM_FL_SITE_0{i}" for i in range(8)],
                    f"{tag}_scored_on_the_realistic_holdout": "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2" in live["metric_cohort"] and live["body_has_realistic_use"] and not live["body_has_frozen_reuse"],
                    f"{tag}_metrics_shown": bool(live["metric_auprc"]) and not any(w in live["metric_auprc"] for w in ("NOT YET", "EVALUATING", "QUEUED")),
                    f"{tag}_overview_states_the_realistic_use": "realistic ECG generator" in ov["limits"],
                    f"{tag}_no_alerts": not live["alerts"],
                }
            checks["monitored_site_overview_names_the_link"] = "Source mode:" in rc["monitored"]["overview"]["monitoring_link"] and "simulated stream" in rc["monitored"]["overview"]["monitoring_link"]
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "realistic_cohort", "checks": checks, "canonical_run": rc["canonical"]["run_id"], "monitored_run": rc["monitored"]["run_id"]}
            (out / "realistic_cohort_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            print(json.dumps(verdict))
            return 0 if verdict["status"] == "PASS" else 1
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
                "v2_refuses_the_highgain_recording_with_reason": "NOT ENOUGH" in v2["preview_c"]["text"] and "graded VALID" in v2["preview_c"]["text"] and "accepted for EXPERIMENTAL training" in v2["preview_c"]["text"] and v2["preview_c"]["start_disabled"],      # V2 trains on every complete window whatever its grade; this short, clipped session is refused for too few windows and its quality is reported separately
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
            from product.hardware_demo_session import DEMO_COLLECTION, LONG_DEMO_COLLECTION

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
            seeded_long = MongoClient(env["NHM_HARDWARE_MONGO_URI"], serverSelectionTimeoutMS=5000)[database][LONG_DEMO_COLLECTION].count_documents({})       # the long showcase session (listed first) and the original one are seeded by the same app-init path
            r = demo["replay"]
            checks = {
                "app_init_created_the_collection_in_mongo": seeded > 4000,
                "listed_in_history_as_saved": demo["session_id"].startswith("HW-SHOWCASE-") and "SAVED" in demo["history_row"] and (f"{seeded} readings" in demo["history_row"] or f"{seeded_long} readings" in demo["history_row"]) and seeded_long > 4000,
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
        if args.hardware_combos:
            from product.hardware_demo_session import DEMO_COLLECTION

            library = Path(tempfile.mkdtemp(prefix="nhm-hw-combos-library-"))
            env["NHM_CANDIDATE_LIBRARY_DIR"] = str(library)             # the gate never touches the real library
            owner = json.loads(Path(args.users_file).read_text())["A"]["user_id"]
            from scripts.register_research_candidates import register_all

            register_all(owner, library)
            demo_collection = MongoClient(env["NHM_HARDWARE_MONGO_URI"], serverSelectionTimeoutMS=5000)[database][DEMO_COLLECTION]
            demo_collection.drop()
            env.pop("NHM_HARDWARE_DEMO_COLLECTION", None)
            running, origin = stack(env, workspace, python)
            try:
                hc = drive("hardware-combos", origin, Path(args.users_file), out / "hardware_combos.json", out / "hc_shots", out / "publisher_logs", env)
            finally:
                running.shutdown()
            from scripts.verify_fl_rounds import verify_hardware_run

            studio_root = workspace / "federation" / "studio_runs"
            verification = {d.name: verify_hardware_run(d, studio_root / d.name) for d in sorted((workspace / "federation" / "hardware_demo").glob("HDFLRUN-*")) if (studio_root / d.name / "eval").exists()}
            (out / "hardware_combos_round_verification.json").write_text(json.dumps(verification, indent=1, sort_keys=True, default=float) + "\n")
            checks = hardware_combos_checks(hc, verification, studio_root)
            verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "mode": "hardware_combos", "checks": checks, "runs": {st["tag"]: st.get("run_id") for st in hc["steps"]}, "session_id": hc.get("session_id"),
                       "rounds_verified_independently": sum(len(v["rounds"]) for v in verification.values()), "database": database, "evidence_level": "VERIFIED_LOCAL_RENDER_REPLICA", "physical_esp32_verified": False, "generated_not_recorded": True}
            (out / "hardware_combos_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
            shutil.rmtree(library, ignore_errors=True)
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
