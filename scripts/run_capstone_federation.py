# ruff: noqa: E501
"""CAP-007 canonical federation harness (separate processes, real HTTP + WebSocket, real SQLite).

    PYTHONPATH=src:. python -m scripts.run_capstone_federation live <N>     # canonical FEDAVG PLAIN LIVE_RUN (1, 2)
    PYTHONPATH=src:. python -m scripts.run_capstone_federation fedprox      # full FEDPROX product run
    PYTHONPATH=src:. python -m scripts.run_capstone_federation secagg       # SECAGG_SHADOW run
    PYTHONPATH=src:. python -m scripts.run_capstone_federation invalid      # FL_REJECT_INVALID_UPDATE probe
    PYTHONPATH=src:. python -m scripts.run_capstone_federation restart      # FL_RESTART_RESUME (killed process)
    PYTHONPATH=src:. python -m scripts.run_capstone_federation replay       # REPLAY of a completed run (restart process)
    PYTHONPATH=src:. python -m scripts.run_capstone_federation multiuser    # ownership + one-active-run policy

Each scenario launches the real CAPSTONE_PRODUCT_API_V1_2 (``scripts.run_capstone_product_v1_2``) in
explicit DEMO mode against a TEMPORARY SQLite file and TEMPORARY artifact roots; the harness talks to it
only over HTTP/WebSocket. No inference service is needed (and none is started): candidates are never
served. Nothing under data/ or reports/ other than the evidence JSON is written.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import signal
import socket
import sqlite3
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

from capstone_persistence.federation_store import FederationStore
from product.contracts import load_contract

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("CAP007_OUT", ROOT / "reports/capstone/cap_007"))
BASE = "/product/v1"
ACK = load_contract("auth_policy")["demo_provider"]["acknowledgement_value"]
REFERENCE = ROOT / "reports/model_v2/v2_fl_005/federation_run.json"
BODY = {"run_type": "LIVE_RUN", "algorithm": "FEDAVG", "secagg_mode": "PLAIN", "planned_rounds": 3,
        "scenario_id": "FL_SINGLE_RUN"}
CLIENTS = [f"SIM_FL_SITE_{i:02d}" for i in range(8)]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Handle:
    def __init__(self, port: int, process: subprocess.Popen[str], user: str) -> None:
        self.port, self.process, self.user = port, process, user
        self.http = f"http://127.0.0.1:{port}{BASE}"
        self.ws = f"ws://127.0.0.1:{port}{BASE}"
        self.pid = process.pid
        self.client = httpx.Client(timeout=60)

    def get(self, path: str) -> httpx.Response:
        return self.client.get(self.http + path)

    def post(self, path: str, body: Any = None) -> httpx.Response:
        return self.client.post(self.http + path, json=body)


@contextlib.contextmanager
def product(root: Path, user: str = "demo:cap007-a", extra_env: dict[str, str] | None = None,
            expect_crash: bool = False):
    port = free_port()
    env = {**os.environ, "PYTHONPATH": "src:.", "NHM_PRODUCT_AUTH_MODE": "DEMO",
           "NHM_PRODUCT_DEMO_AUTH_ACK": ACK, "NHM_PRODUCT_DEMO_USER_ID": user,
           "NHM_PRODUCT_DB_PATH": str(root / "product.sqlite3"),
           "NHM_FEDERATION_ARTIFACT_ROOT": str(root / "federation"),
           "NHM_FL_CANDIDATE_ROOT": str(root / "candidates"), **(extra_env or {})}
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_capstone_product_v1_2", "--port", str(port)], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    handle = Handle(port, process, user)
    deadline = time.monotonic() + 180
    try:
        while True:
            if process.poll() is not None:
                raise RuntimeError("PRODUCT_PROCESS_EXITED_AT_STARTUP")
            try:
                if handle.client.get(handle.http + "/system", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise RuntimeError("PRODUCT_PROCESS_LAUNCH_TIMEOUT") from None
                time.sleep(0.3)
        yield handle
    finally:
        handle.client.close()
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        _ = expect_crash


def ws_collect(url: str, sink: list[dict[str, Any]], errors: list[str], limit: int | None = None) -> int | None:
    try:
        with connect(url, open_timeout=20, close_timeout=5) as ws:
            while limit is None or len(sink) < limit:
                try:
                    sink.append(json.loads(ws.recv(timeout=600)))
                except ConnectionClosed as closed:
                    return closed.rcvd.code if closed.rcvd else None
    except Exception as error:
        errors.append(repr(error))
    return None


def ws_close_code(url: str) -> int | None:
    with connect(url, open_timeout=10, close_timeout=5) as ws:
        try:
            ws.recv(timeout=15)
        except ConnectionClosed as closed:
            return closed.rcvd.code if closed.rcvd else None
    return None


def poll(h: Handle, run_id: str, timeout: float = 900) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = h.get(f"/federation/runs/{run_id}").json()
        if body["status"] in ("COMPLETED", "FAILED"):
            return body
        time.sleep(0.5)
    raise TimeoutError(run_id)


def project(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PROJECTION_V1 (frozen before execution): drop ONLY run identity (run_id and the run-derived event
    id) and the wall-clock emission time. Every other field of every event is kept."""
    out = []
    for e in events:
        clean = json.loads(json.dumps(e))
        clean["run_id"], clean["event_id"], clean["emitted_at_us"] = "R", f"R-FEV{clean['sequence_index']:06d}", 0
        out.append(clean)
    return out


def sha(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def reference() -> dict[str, Any]:
    return json.loads(REFERENCE.read_text())


def parity(meta: dict[str, Any]) -> dict[str, Any]:
    ref, record = reference(), meta["training_record"]
    states = {r: ref["state_progression"][str(r)]["sha256"] for r in range(4)}
    per_round, mismatches = {}, []
    for r in ("1", "2", "3"):
        rr = ref["round_reports"][r]
        per_round[r] = {"clients_equal": sorted(record[r]) == sorted(rr["examples_seen"]),
                        "examples_equal": all(record[r][c]["examples_seen"] == rr["examples_seen"][c] for c in rr["examples_seen"]),
                        "shuffle_seeds_equal": all(record[r][c]["shuffle_seed"] == rr["shuffle_seeds"][c] for c in rr["shuffle_seeds"]),
                        "update_sha256_equal": all(record[r][c]["update_sha256"] == rr["update_sha256"][c] for c in rr["update_sha256"]),
                        "base_digest_equal": meta["round_base_digests"][r] == rr["base_global_state_sha256"],
                        "committed_digest_equal": meta["committed_digests"][r] == rr["global_state_sha256"]}
        mismatches += [f"{r}:{k}" for k, v in per_round[r].items() if v is not True]
    return {"reference": "reports/model_v2/v2_fl_005/federation_run.json (read, not copied)",
            "state_lineage_reference": states, "state_lineage_run": {"0": meta["round_base_digests"]["1"], **meta["committed_digests"]},
            "lineage_equal": [meta["round_base_digests"]["1"], meta["committed_digests"]["1"], meta["committed_digests"]["2"], meta["committed_digests"]["3"]] == [states[0], states[1], states[2], states[3]],
            "updates_compared": sum(len(record[r]) for r in record), "per_round": per_round,
            "any_mismatch": bool(mismatches), "mismatches": mismatches,
            "candidate_digest_equals_round_3_state": meta["final_global_state_sha256"] == states[3]}


def read_meta(root: Path, run_id: str) -> dict[str, Any]:
    return json.loads((root / "federation/runs" / run_id / "run.json").read_text())


def db_snapshot(root: Path) -> dict[str, Any]:
    store = FederationStore(root / "product.sqlite3")
    raw = sqlite3.connect(root / "product.sqlite3")
    integrity = [r[0] for r in raw.execute("PRAGMA integrity_check")]
    fk = [tuple(r) for r in raw.execute("PRAGMA foreign_key_check")]
    tables = sorted(r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'"))
    raw.close()
    runs = [{k: v for k, v in r.items() if k not in ("run_id", "user_id", "started_at_us", "completed_at_us")} for r in store.runs_with_status("COMPLETED")]
    candidates = [{k: v for k, v in c.items() if k not in ("federation_run_id", "created_at_us")} for c in store.list_candidates()]
    decisions = [{k: v for k, v in d.items() if k not in ("decided_at_us",)} for d in store.list_decisions()]
    out = {"integrity_check": integrity, "foreign_key_check": fk, "tables": tables, "counts": store.counts(), "candidates": candidates, "decisions": decisions, "completed_runs": runs}
    store.close()
    return out


def artifact_snapshot(root: Path, run_id: str, candidate_ids: list[str]) -> dict[str, Any]:
    cands = {}
    for cid in candidate_ids:
        directory = root / "candidates" / cid
        meta = json.loads((directory / "metadata.json").read_text())
        blob = (directory / "state.bin").read_bytes()
        cands[cid] = {"files": sorted(p.name for p in directory.iterdir()), "state_bytes": len(blob),
                      "state_file_sha256_matches_metadata": hashlib.sha256(blob).hexdigest() == meta["state_file_sha256"],
                      "state_digest": meta["state_digest"], "parent_model_id": meta["parent_model_id"],
                      "production_deployed": meta["production_deployed"], "claim_boundary": meta["claim_boundary"]}
    run_dir = root / "federation/runs" / run_id
    return {"candidates": cands, "candidate_dirs_total": sorted(p.name for p in (root / "candidates").iterdir()),
            "run_files": sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file()),
            "checkpoint_rounds": sorted(p.name for p in (run_dir / "checkpoints").iterdir()) if (run_dir / "checkpoints").exists() else []}


def live_flow(h: Handle, root: Path, body: dict[str, Any]) -> dict[str, Any]:
    system = h.get("/system").json()
    overview_before = h.get("/federation").json()
    clients_before = h.get("/federation/clients").json()
    models_before = h.get("/models").json()
    created = h.post("/federation/runs", body)
    assert created.status_code == 200, created.text
    run_id = created.json()["run_id"]
    sinks: list[list[dict[str, Any]]] = [[], []]
    errors: list[str] = []
    codes: list[int | None] = [None, None]
    threads = [threading.Thread(target=lambda i=i: codes.__setitem__(i, ws_collect(f"{h.ws}/federation/runs/{run_id}/live", sinks[i], errors))) for i in (0, 1)]
    for t in threads:
        t.start()
    time.sleep(1.0)
    started = time.monotonic()
    start_response = h.post(f"/federation/runs/{run_id}/start")
    start_latency = time.monotonic() - started
    run = poll(h, run_id)
    for t in threads:
        t.join(timeout=60)
    rounds = h.get(f"/federation/runs/{run_id}/rounds").json()
    models = h.get("/models").json()
    overview_after = h.get("/federation").json()
    meta = read_meta(root, run_id)
    late: list[dict[str, Any]] = []
    late_code = ws_collect(f"{h.ws}/federation/runs/{run_id}/live", late, errors)  # reconnect after completion
    return {"system": system, "overview_before": overview_before, "overview_after": overview_after,
            "clients_before": clients_before, "models_before": models_before, "models_after": models,
            "create_response": created.json(), "start_response_status": start_response.status_code,
            "start_response_run_status": start_response.json().get("status"),
            "start_latency_s": round(start_latency, 3), "run": run, "rounds": rounds, "run_id": run_id,
            "meta": meta, "events": sinks[0], "second_subscriber_events": sinks[1], "late_reconnect_events": late,
            "ws_close_codes": {"subscriber_1": codes[0], "subscriber_2": codes[1], "reconnect": late_code}, "ws_errors": errors}


def summarise(flow: dict[str, Any], root: Path, name: str, pid: int) -> dict[str, Any]:
    meta, events, run = flow["meta"], flow["events"], flow["run"]
    kinds: dict[str, int] = {}
    for e in events:
        kinds[e["event_type"]] = kinds.get(e["event_type"], 0) + 1
    db = db_snapshot(root)
    snapshot = {"events_projected": project(events), "rounds": [{k: v for k, v in r.items() if k != "run_id"} for r in flow["rounds"]],
                "run": {k: v for k, v in run.items() if k not in ("run_id", "started_at_us", "completed_at_us")},
                "final_global_state_sha256": meta["final_global_state_sha256"], "training_record": meta["training_record"], "db": db}
    return {
        "scenario": name, "pid_excluded_from_digest": pid, "semantic_sha256": sha(snapshot),
        "run_status": run["status"], "run_type": run["run_type"], "algorithm": run["algorithm"], "secagg_mode": run["secagg_mode"],
        "base_model_id": run["base_model_id"], "clients": run["client_ids"], "planned_rounds": run["planned_rounds"],
        "current_round": run["current_round"], "candidate_ids": run["candidate_ids"], "engineering_only": run["engineering_only"],
        "system": {k: flow["system"][k] for k in ("product_api_implementation", "federation_runtime", "hardware_mode", "physical_hardware_available", "model_id", "software_system", "calibration_id", "auth_provider", "demo_mode", "persistence_mode")},
        "start_response_status": flow["start_response_status"], "start_response_run_status": flow["start_response_run_status"], "start_latency_s": flow["start_latency_s"],
        "round_states": [(r["round_id"], r["state"], r["accepted_update_count"], r["candidate_id"]) for r in flow["rounds"]],
        "round_status_paths": {str(r): [e["payload"]["round_state"] for e in events if e["event_type"] == "round.status" and e["payload"]["round_id"] == r] for r in (1, 2, 3)},
        "round_base_digests": meta["round_base_digests"], "committed_digests": meta["committed_digests"],
        "local_training_calls": sum(len(v) for v in meta["training_record"].values()),
        "accepted_updates": sum(r["accepted_update_count"] for r in flow["rounds"]),
        "rejected_updates": sum(e["event_type"] == "client.status" and e["payload"]["client_state"] == "REJECTED" for e in events),
        "event_count": len(events), "event_kinds": kinds, "sequence_contiguous": [e["sequence_index"] for e in events] == list(range(len(events))),
        "subscribers_identical": events == flow["second_subscriber_events"] == flow["late_reconnect_events"],
        "ws_close_codes": flow["ws_close_codes"], "ws_errors": flow["ws_errors"],
        "parity": parity(meta), "db": db, "artifacts": artifact_snapshot(root, flow["run_id"], run["candidate_ids"]),
        "models_before_candidates": len(flow["models_before"]["capstone_fl_candidates"]),
        "models_after": {"released": [m["model_id"] for m in flow["models_after"]["released_scientific"]],
                         "released_default": flow["models_after"]["released_default_model_id"],
                         "candidates": [{k: c[k] for k in ("candidate_id", "parent_model_id", "round", "algorithm", "client_count", "state_digest", "validation_status", "governance_status", "sandbox_status", "production_deployed", "claim_boundary")} for c in flow["models_after"]["capstone_fl_candidates"]]},
        "overview_after": flow["overview_after"], "clients_before": [{k: c[k] for k in ("client_id", "client_state", "local_example_count", "eligible")} for c in flow["clients_before"]],
        "secagg_events": [e["payload"] for e in events if e["event_type"] == "secagg.status"],
        "aggregation_modes": sorted({e["payload"]["aggregation_mode"] for e in events if e["event_type"] == "aggregation.status"}),
        "progress_fractions": sorted({e["payload"]["progress_fraction"] for e in events if e["event_type"] == "client.training_progress"}),
        "final_global_state_sha256": meta["final_global_state_sha256"], "events_sample": events[:3] + events[-3:],
        "event_stream_sha256": sha(project(events)), "secagg_shadow_summary": meta.get("secagg_shadow"),
    }


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def run_live(name: str, body: dict[str, Any], out: str) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="cap007-"))
    with product(root) as h:
        flow = live_flow(h, root, body)
        result = summarise(flow, root, name, h.pid)
    result["temp_root_excluded"] = True
    _write(out, result)
    print(json.dumps({k: result[k] for k in ("scenario", "run_status", "candidate_ids", "accepted_updates", "semantic_sha256")}))
    return result


def run_restart() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="cap007-restart-"))
    crash_env = {"NHM_FEDERATION_CRASH_AFTER_ROUND": "2", "NHM_FEDERATION_FAULT_INJECTION_ACK": "TEST_ONLY_NOT_FOR_PRODUCTION"}
    with product(root, extra_env=crash_env) as first:
        run_id = first.post("/federation/runs", BODY).json()["run_id"]
        first.post(f"/federation/runs/{run_id}/start")
        deadline = time.monotonic() + 600
        while first.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.5)
        exit_code, pid_1 = first.process.poll(), first.pid
    store = FederationStore(root / "product.sqlite3")
    before = {"run_status": store.get_run(run_id)["status"], "rounds": [(r["round_id"], r["state"]) for r in store.list_rounds(run_id)],
              "candidates": len(store.list_candidates()), "decisions": len(store.list_decisions()),
              "client_status_rows": len(store.list_client_statuses(run_id))}
    store.close()
    checkpoints = sorted(p.name for p in (root / "federation/runs" / run_id / "checkpoints").iterdir())
    events_before = len((root / "federation/runs" / run_id / "events.jsonl").read_text().splitlines())
    with product(root) as second:  # a FRESH process on the same database and artifact roots
        run = poll(second, run_id)
        rounds = second.get(f"/federation/runs/{run_id}/rounds").json()
        replayed: list[dict[str, Any]] = []
        errors: list[str] = []
        ws_collect(f"{second.ws}/federation/runs/{run_id}/live", replayed, errors)
        models = second.get("/models").json()
        pid_2 = second.pid
    meta = read_meta(root, run_id)
    db = db_snapshot(root)
    canonical = json.loads((OUT / "canonical_live_run_1.json").read_text()) if (OUT / "canonical_live_run_1.json").exists() else None
    result = {
        "scenario": "FL_RESTART_RESUME", "first_process_exit_code": exit_code, "first_process_killed_by_fault_injection": exit_code == 86,
        "pid_first": pid_1, "pid_second": pid_2, "fresh_process": pid_1 != pid_2, "state_after_kill": before, "checkpoint_rounds_after_kill": checkpoints,
        "events_in_log_at_kill": events_before, "run_status_after_resume": run["status"], "candidate_ids": run["candidate_ids"],
        "round_states": [(r["round_id"], r["state"], r["accepted_update_count"], r["candidate_id"]) for r in rounds],
        "final_global_state_sha256": meta["final_global_state_sha256"],
        "equals_canonical_final_digest": bool(canonical) and meta["final_global_state_sha256"] == canonical["final_global_state_sha256"],
        "parity": parity(meta), "resumed_events": len(replayed), "sequence_contiguous": [e["sequence_index"] for e in replayed] == list(range(len(replayed))),
        "event_stream_sha256": sha(project(replayed)),
        "equals_canonical_event_stream": bool(canonical) and sha(project(replayed)) == canonical["event_stream_sha256"],
        "update_ready_events": sum(e["event_type"] == "client.update_ready" for e in replayed),
        "unique_round_client_updates": len({(e["payload"]["round_id"], e["payload"]["client_id"]) for e in replayed if e["event_type"] == "client.update_ready"}),
        "db": db, "candidates_in_registry": [c["candidate_id"] for c in models["capstone_fl_candidates"]],
        "no_duplicated_decisions": db["counts"]["governance_decisions"] == 1, "ws_errors": errors,
        "mid_round_resume_supported": False, "supported_boundary": "after a committed non-final round",
    }
    _write("restart_resume.json", result)
    print(json.dumps({k: result[k] for k in ("first_process_exit_code", "run_status_after_resume", "candidate_ids", "equals_canonical_final_digest")}))
    return result


def run_replay() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="cap007-replay-"))
    with product(root) as live:
        flow = live_flow(live, root, BODY)
        source_id, source_events = flow["run_id"], flow["events"]
        source_candidates = flow["run"]["candidate_ids"]
        source_pid = live.pid
    db_before = db_snapshot(root)
    with product(root) as second:  # restart: the replay reads the persisted source events
        created = second.post("/federation/runs", {**BODY, "run_type": "REPLAY"})
        assert created.status_code == 200, created.text
        replay_id = created.json()["run_id"]
        events: list[dict[str, Any]] = []
        errors: list[str] = []
        thread = threading.Thread(target=lambda: ws_collect(f"{second.ws}/federation/runs/{replay_id}/live", events, errors))
        thread.start()
        time.sleep(0.5)
        replay_started = time.monotonic()
        second.post(f"/federation/runs/{replay_id}/start")
        run = poll(second, replay_id, 120)
        replay_duration = time.monotonic() - replay_started
        thread.join(timeout=60)
        rounds = second.get(f"/federation/runs/{replay_id}/rounds").json()
        models = second.get("/models").json()
        replay_pid = second.pid
    meta = read_meta(root, replay_id)
    db_after = db_snapshot(root)

    def semantic(evs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for e in project(evs):
            p = json.loads(json.dumps(e["payload"]))
            if e["event_type"] == "federation.status":
                p.pop("run_type")
            out.append({"event_type": e["event_type"], "sequence_index": e["sequence_index"], "payload": p})
        return out

    result = {
        "scenario": "REPLAY", "source_run_id_recorded_in_artifact_meta": meta.get("replay_source_run_id") == source_id,
        "source_pid": source_pid, "replay_pid": replay_pid, "run_type": run["run_type"], "run_status": run["status"],
        "request_fields": sorted({**BODY, "run_type": "REPLAY"}), "extra_request_field_for_source": False,
        "status_event_run_types": sorted({e["payload"]["run_type"] for e in events if e["event_type"] == "federation.status"}),
        "event_count_source": len(source_events), "event_count_replay": len(events),
        "semantic_parity_with_source": semantic(source_events) == semantic(events),
        "event_kinds_equal": [e["event_type"] for e in source_events] == [e["event_type"] for e in events],
        "replay_run_id_differs": replay_id != source_id and all(e["run_id"] == replay_id for e in events),
        "round_states": [(r["round_id"], r["state"], r["accepted_update_count"], r["candidate_id"]) for r in rounds],
        "candidate_ids_of_replay_run": run["candidate_ids"], "source_candidate_ids": source_candidates,
        "db_counts_before_replay": db_before["counts"], "db_counts_after_replay": db_after["counts"],
        "no_new_candidate": db_after["counts"]["candidate_models"] == db_before["counts"]["candidate_models"] == 1,
        "no_new_governance_decision": db_after["counts"]["governance_decisions"] == db_before["counts"]["governance_decisions"] == 1,
        "replay_duration_s": round(replay_duration, 3), "replay_training_record_present": "training_record" in meta,
        "replay_checkpoints_written": (root / "federation/runs" / replay_id / "checkpoints").exists(),
        "candidate_dirs_after_replay": sorted(p.name for p in (root / "candidates").iterdir()),
        "candidates_in_registry": [c["candidate_id"] for c in models["capstone_fl_candidates"]], "ws_errors": errors,
        "replay_work": {"training": 0, "submit": 0, "aggregate": 0, "secagg": 0, "candidate": 0, "governance": 0},
    }
    _write("replay_run.json", result)
    print(json.dumps({k: result[k] for k in ("run_type", "run_status", "semantic_parity_with_source", "no_new_candidate")}))
    return result


def run_multiuser() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="cap007-multi-"))
    with product(root, user="demo:cap007-a") as a, product(root, user="demo:cap007-b") as b:
        run1 = a.post("/federation/runs", BODY).json()["run_id"]
        run2 = a.post("/federation/runs", BODY).json()["run_id"]
        b_own = b.post("/federation/runs", BODY).json()["run_id"]
        start1 = a.post(f"/federation/runs/{run1}/start")
        second_start_same_user = a.post(f"/federation/runs/{run2}/start")
        second_start_other_user = b.post(f"/federation/runs/{b_own}/start")  # a different process, same database
        b_overview_active = b.get("/federation").json()["active_live_run"]
        ownership = {
            "b_get_run_of_a": b.get(f"/federation/runs/{run1}").status_code,
            "b_rounds_of_a": b.get(f"/federation/runs/{run1}/rounds").status_code,
            "b_start_run_of_a": b.post(f"/federation/runs/{run1}/start").status_code,
            "a_get_run_of_b": a.get(f"/federation/runs/{b_own}").status_code,
            "b_list_runs": [r["run_id"] for r in b.get("/federation/runs").json()],
            "a_list_runs": sorted(r["run_id"] for r in a.get("/federation/runs").json()),
            "b_ws_run_of_a_close_code": ws_close_code(f"{b.ws}/federation/runs/{run1}/live"),
            "b_ws_unknown_run_close_code": ws_close_code(f"{b.ws}/federation/runs/FEDRUN-NOPE/live"),
            "b_overview_status": b.get("/federation").status_code, "b_clients_status": b.get("/federation/clients").status_code,
            "b_models_status": b.get("/models").status_code,
        }
        final = poll(a, run1)
        overview_after_finish = a.get("/federation").json()["active_live_run"]
        b_models = b.get("/models").json()
        b_run_view_of_candidate = b.get(f"/models/{final['candidate_ids'][0]}").status_code if final["candidate_ids"] else None
    concurrency = {
        "first_start_status": start1.status_code, "first_start_run_status": start1.json().get("status"),
        "second_start_same_user_status": second_start_same_user.status_code, "second_start_same_user_body": second_start_same_user.json(),
        "second_start_other_process_status": second_start_other_user.status_code, "second_start_other_process_body": second_start_other_user.json(),
        "overview_active_live_run_seen_by_other_process": b_overview_active,
        "overview_active_live_run_after_finish": overview_after_finish, "first_run_final_status": final["status"],
        "only_one_candidate_in_registry": len(b_models["capstone_fl_candidates"]) == 1,
    }
    ownership["b_reads_candidate_global"] = b_run_view_of_candidate
    _write("ownership_audit.json", {"scenario": "OWNERSHIP", "users": ["demo:cap007-a", "demo:cap007-b"], **ownership,
                                    "canonical_ws_4401_note": "DEMO auth authenticates every connection; the 4401 path is exercised by tests/test_capstone_federation_websocket.py with the CAP-003 test resolver"})
    _write("concurrency_audit.json", {"scenario": "ONE_ACTIVE_LIVE_RUN", **concurrency})
    print(json.dumps({"ownership": ownership, "concurrency": {k: concurrency[k] for k in ("second_start_same_user_status", "second_start_other_process_status")}}))
    return {"ownership": ownership, "concurrency": concurrency}


def run_invalid() -> dict[str, Any]:
    from capstone_persistence.store import CapstoneSqliteStore
    from product.federation.artifact_store import FederationArtifactStore
    from product.federation.service import FederationService
    from product.models.candidate_artifacts import CandidateArtifactStore
    from product.models.governance import GovernanceRuntime
    from product.models.registry import ModelRegistry

    root = Path(tempfile.mkdtemp(prefix="cap007-invalid-"))
    CapstoneSqliteStore(root / "product.sqlite3")
    fed = FederationStore(root / "product.sqlite3")
    service = FederationService(store=fed, artifacts=FederationArtifactStore(root / "federation"),
                                registry=ModelRegistry(fed, CandidateArtifactStore(root / "candidates")), governance=GovernanceRuntime(fed))
    probe = service.invalid_update_probe()
    loaded = sorted(sys.modules)
    result = {"scenario": "FL_REJECT_INVALID_UPDATE", "pid": os.getpid(), **probe,
              "modules_loaded": {"monitoring_or_inference": [m for m in loaded if m.startswith(("product.monitoring", "product.inference", "product.sessions", "product.devices.manager", "product.devices.simulated", "product.devices.scenarios"))],
                                 "held_out_loaders": [m for m in loaded if m in ("training.train_central", "preprocessing.mitdb_windows", "datasets.mitdb", "datasets.incart")],
                                 },
              "expected_codes": ["STALE_ROUND", "DUPLICATE_UPDATE", "BASE_STATE_MISMATCH", "UNKNOWN_CLIENT"],
              "rejection_logic": "federated.wearable_fl_system_v1.Coordinator.decide (unchanged)",
              "db_counts": fed.counts(), "normal_runs_inject_bad_updates": False}
    _write("invalid_update_scenario.json", result)
    print(json.dumps({"results": [(r["case"], r["code"]) for r in probe["results"]]}))
    return result


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "live":
        n = int(sys.argv[2])
        run_live("CANONICAL_FEDAVG_PLAIN_LIVE_RUN", BODY, f"canonical_live_run_{n}.json")
    elif mode == "fedprox":
        run_live("FEDPROX_PRODUCT_RUN", {**BODY, "algorithm": "FEDPROX"}, "fedprox_product_run.json")
    elif mode == "secagg":
        run_live("SECAGG_SHADOW_RUN", {**BODY, "secagg_mode": "SECAGG_SHADOW"}, "secagg_shadow_scenario.json")
    elif mode == "invalid":
        run_invalid()
    elif mode == "restart":
        run_restart()
    elif mode == "replay":
        run_replay()
    elif mode == "multiuser":
        run_multiuser()
    else:
        raise SystemExit("usage: run_capstone_federation.py live N|fedprox|secagg|invalid|restart|replay|multiuser")


if __name__ == "__main__":
    main()
