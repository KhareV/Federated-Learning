"""Run the two real-Atlas telemetry scenarios and recorded-data demo FL.

The URI is read from NHM_HARDWARE_MONGO_URI (or an ignored --env-file).  Only
documents carrying this invocation's nhmTestRun tags are removed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from capstone_persistence.store import CapstoneSqliteStore
from product.hardware_telemetry import HardwareSessions, MongoTelemetry
from scripts.run_capstone_clerk_connected import parse_env_file
from studio.hardware_demo import HardwareDemoService

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "nhm_integration_test"
OWNER = "atlas-scenario-owner"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def publisher(env: dict[str, str], tag: str, count: int, log: Path, *extra: str) -> subprocess.Popen[str]:
    command = [
        sys.executable, "-m", "scripts.publish_hardware_test", "--count", str(count),
        "--rate", "20", "--run-tag", tag, *extra,
    ]
    log.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(command, cwd=ROOT, env={**os.environ, **env}, stdout=log.open("w"), stderr=subprocess.STDOUT, text=True)


def poll_for(sessions: HardwareSessions, sid: str, seconds: float, states: list[str]) -> dict[str, Any]:
    end = time.monotonic() + seconds
    result: dict[str, Any] = {}
    while time.monotonic() < end:
        result = sessions.poll(sid, OWNER)
        if not states or result["source_state"] != states[-1]:
            states.append(result["source_state"])
        time.sleep(0.5)
    return result


def poll_until_process(sessions: HardwareSessions, sid: str, process: subprocess.Popen[str], states: list[str], timeout: float) -> dict[str, Any]:
    end = time.monotonic() + timeout
    result: dict[str, Any] = {}
    while process.poll() is None and time.monotonic() < end:
        result = sessions.poll(sid, OWNER)
        if not states or result["source_state"] != states[-1]:
            states.append(result["source_state"])
        time.sleep(0.5)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
        raise RuntimeError("publisher timed out while session was polling")
    if process.returncode:
        raise RuntimeError(f"publisher exited {process.returncode}")
    # Consume the final insert batch and leave enough time to classify it LIVE.
    result = sessions.poll(sid, OWNER)
    if not states or result["source_state"] != states[-1]:
        states.append(result["source_state"])
    return result


def wait_process(process: subprocess.Popen[str], timeout: float) -> None:
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        code = process.wait(timeout=10)
        raise RuntimeError("publisher timed out")
    if code:
        raise RuntimeError(f"publisher exited {code}")


def compact_documents(collection: Any, tag: str) -> dict[str, Any]:
    rows = list(collection.find({"nhmTestRun": tag}).sort("_id", 1))
    selected = rows[:3] + (rows[-3:] if len(rows) > 3 else [])
    return {
        "tag": tag,
        "count": len(rows),
        "selected": [
            {"id": str(r["_id"]), "timestamp": r.get("timestamp"), "sequence": r.get("sequence"),
             "ecg": r.get("ecg"), "bpm": r.get("bpm"), "spo2": r.get("spo2")}
            for r in selected
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--out", default=str(ROOT / "reports/hardware/final_demo"))
    parser.add_argument("--a-delay", type=float, default=10.0)
    parser.add_argument("--a-count", type=int, default=1200)
    parser.add_argument("--b-preseconds", type=float, default=18.0)
    parser.add_argument("--b-first-seconds", type=float, default=60.0)
    parser.add_argument("--b-second-seconds", type=float, default=25.0)
    parser.add_argument("--b-count", type=int, default=2400)
    args = parser.parse_args()
    env = {**parse_env_file(Path(args.env_file)), **os.environ}
    uri = env.get("NHM_HARDWARE_MONGO_URI")
    if not uri:
        parser.error("NHM_HARDWARE_MONGO_URI is required")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    tag_a, tag_a_post, tag_b = (f"NHM-FINAL-A-{run_stamp}", f"NHM-FINAL-A-POST-{run_stamp}", f"NHM-FINAL-B-{run_stamp}")
    tags = [tag_a, tag_a_post, tag_b]
    atlas = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
    collection = atlas[env.get("NHM_HARDWARE_MONGO_DATABASE", "health_db")][COLLECTION]
    source = MongoTelemetry(uri, env.get("NHM_HARDWARE_MONGO_DATABASE", "health_db"), COLLECTION)
    work = Path(tempfile.mkdtemp(prefix="nhm-final-atlas-"))
    db = work / "product.sqlite3"
    store = CapstoneSqliteStore(db)
    sessions = HardwareSessions(store, source)
    results: dict[str, Any] = {"schema": "NHM_FINAL_ATLAS_SCENARIOS_V1", "started_at": datetime.now(UTC), "collection": f"health_db.{COLLECTION}", "synthetic": True}
    try:
        # A: session first, delayed publisher, genuine stale interval, recovery, stop.
        a_states: list[str] = []
        a = sessions.start(OWNER)
        a_sid = a["session_id"]
        a_states.append(a["source_state"])
        time.sleep(args.a_delay)
        a_before = sessions.poll(a_sid, OWNER)
        process_a = publisher(env, tag_a, args.a_count, out / "scenario_a" / "publisher.log", "--pause-at", "25", "--pause-duration", "7")
        a_live = poll_until_process(sessions, a_sid, process_a, a_states, args.a_count / 20.0 + 45.0)
        a_repeat = sessions.poll(a_sid, OWNER)
        a_stopped = sessions.stop(a_sid, OWNER)
        stable_count = a_stopped["record_count"]
        process_post = publisher(env, tag_a_post, 20, out / "scenario_a" / "post_stop_publisher.log")
        wait_process(process_post, 10)
        after_stop = sessions.poll(a_sid, OWNER)
        a_docs = compact_documents(collection, tag_a)
        trace_by_id = {r["id"]: r for r in a_stopped["readings"]}
        mapping = [{**doc, "captured": doc["id"] in trace_by_id,
                    "captured_ordinal": trace_by_id.get(doc["id"], {}).get("ordinal")} for doc in a_docs["selected"]]
        results["scenario_a"] = {
            "session_id": a_sid, "states_seen": a_states, "delay_seconds": args.a_delay,
            "waiting_before_emission": a_before["source_state"] == "WAITING FOR DATA" and a_before["record_count"] == 0,
            "inserted": a_docs, "captured_count": stable_count, "repeat_poll_count": a_repeat["record_count"],
            "duplicate_free": len({r["id"] for r in a_stopped["readings"]}) == len(a_stopped["readings"]),
            "stale_seen": "STALE DATA" in a_states, "recovered_live": a_states.count("LIVE DATA RECEIVED") >= 1 and a_states[-1] == "LIVE DATA RECEIVED",
            "stopped": a_stopped["status"] == "STOPPED", "post_stop_count": after_stop["record_count"],
            "post_stop_stable": after_stop["record_count"] == stable_count, "document_to_trace": mapping,
        }
        # Restart persistence before training.
        source.close(); store.close()
        store = CapstoneSqliteStore(db)
        source = MongoTelemetry(uri, env.get("NHM_HARDWARE_MONGO_DATABASE", "health_db"), COLLECTION)
        sessions = HardwareSessions(store, source)
        a_restart = sessions.detail(a_sid, OWNER)
        results["scenario_a"]["history_after_restart"] = {"status": a_restart["status"], "record_count": a_restart["record_count"], "readings": len(a_restart["readings"])}
        demo = HardwareDemoService(store, work / "studio")
        avg3 = demo.run(OWNER, session_ids=[a_sid], rounds=3, algorithm="FEDAVG", secagg_mode="SECAGG_SHADOW", label_seed=20261015)
        prox3 = demo.run(OWNER, session_ids=[a_sid], rounds=3, algorithm="FEDPROX", secagg_mode="SECAGG_SHADOW", label_seed=20261015)
        results["scenario_a"]["demo_fl"] = {"fedavg": avg3, "fedprox": prox3}

        # B: publisher first, fresh high-water mark, stop while it continues, then a separate session.
        b_log = out / "scenario_b" / "publisher.log"
        process_b = publisher(env, tag_b, args.b_count, b_log)
        time.sleep(args.b_preseconds)
        pre = compact_documents(collection, tag_b)
        b1_states: list[str] = []
        b1 = sessions.start(OWNER); b1_sid = b1["session_id"]
        b1_states.append(b1["source_state"])
        b1_live = poll_for(sessions, b1_sid, args.b_first_seconds, b1_states)
        b1_stop = sessions.stop(b1_sid, OWNER)
        b1_count = b1_stop["record_count"]
        time.sleep(3)
        b1_after = sessions.poll(b1_sid, OWNER)
        b2_states: list[str] = []
        b2 = sessions.start(OWNER); b2_sid = b2["session_id"]
        b2_states.append(b2["source_state"])
        b2_live = poll_for(sessions, b2_sid, args.b_second_seconds, b2_states)
        b2_stop = sessions.stop(b2_sid, OWNER)
        wait_process(process_b, max(20.0, args.b_count / 20.0 + 15.0))
        b_docs = compact_documents(collection, tag_b)
        b1_ids = {r["id"] for r in b1_stop["readings"]}
        pre_ids = {d["id"] for d in pre["selected"]}
        results["scenario_b"] = {
            "preexisting_count": pre["count"], "preexisting_selected_ids": sorted(pre_ids),
            "first_session_id": b1_sid, "first_states_seen": b1_states, "first_count": b1_count,
            "old_selected_excluded": not bool(pre_ids & b1_ids), "first_post_stop_count": b1_after["record_count"],
            "first_post_stop_stable": b1_after["record_count"] == b1_count,
            "second_session_id": b2_sid, "second_states_seen": b2_states, "second_count": b2_stop["record_count"],
            "separate_ids": b1_sid != b2_sid, "trace_overlap": len(b1_ids & {r["id"] for r in b2_stop["readings"]}),
            "inserted": b_docs,
        }
        avg10 = demo.run(OWNER, session_ids=[b1_sid], rounds=10, algorithm="FEDAVG", secagg_mode="SECAGG_SHADOW", label_seed=20261015)
        prox10 = demo.run(OWNER, session_ids=[b1_sid], rounds=10, algorithm="FEDPROX", secagg_mode="SECAGG_SHADOW", label_seed=20261015)
        results["scenario_b"]["demo_fl"] = {"fedavg": avg10, "fedprox": prox10}
        results["completed_at"] = datetime.now(UTC)
        required = [
            results["scenario_a"]["waiting_before_emission"], results["scenario_a"]["stale_seen"],
            results["scenario_a"]["recovered_live"], results["scenario_a"]["post_stop_stable"],
            results["scenario_b"]["old_selected_excluded"], results["scenario_b"]["first_post_stop_stable"],
            results["scenario_b"]["separate_ids"], results["scenario_b"]["trace_overlap"] == 0,
        ]
        results["status"] = "PASS" if all(required) else "FAIL"
        write_json(out / "atlas_scenarios.json", results)
        print(json.dumps({"status": results["status"], "evidence": str(out / "atlas_scenarios.json"), "scenario_a": a_sid, "scenario_b": [b1_sid, b2_sid]}))
        return 0 if results["status"] == "PASS" else 1
    finally:
        cleanup = {tag: collection.delete_many({"nhmTestRun": tag}).deleted_count for tag in tags}
        write_json(out / "atlas_cleanup.json", {"collection": f"health_db.{COLLECTION}", "deleted_by_tag": cleanup, "production_data_deleted": False})
        source.close()
        store.close()
        atlas.close()


if __name__ == "__main__":
    raise SystemExit(main())
