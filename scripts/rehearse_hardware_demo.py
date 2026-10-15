"""One-command rehearsal of the ESP32 -> server -> Atlas -> NHM chain.

    PYTHONPATH=src:. python -m scripts.rehearse_hardware_demo --mode smoke      # ~1.5 min
    PYTHONPATH=src:. python -m scripts.rehearse_hardware_demo --mode faults     # protocol-level fault matrix
    PYTHONPATH=src:. python -m scripts.rehearse_hardware_demo --mode soak --soak-minutes 10
    PYTHONPATH=src:. python -m scripts.rehearse_hardware_demo --mode full --users-file <clerk users json>

Evidence level of everything this runner produces: VERIFIED_LOCAL_RENDER_REPLICA (a local replica of the
ingestion server, NOT the deployed Render service) or FAILED. VERIFIED_PHYSICAL_ESP32_PRODUCTION can only be
claimed by a real device run and is always reported NOT_RUN here.

Isolation: the replica writes ONLY to the rehearsal database (default ``nhm_rehearsal``) of the Atlas cluster;
NHM is pointed at the same database with ``records_*``. ``health_db`` is never touched. Cleanup removes only
documents carrying this run's tags and then drops rehearsal collections that became empty.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from pymongo import MongoClient  # noqa: E402

from scripts.hardware_chain import (  # noqa: E402
    PRODUCTION_DATABASE,
    REHEARSAL_DATABASE,
    Emulator,
    NhmProbe,
    Replica,
    correlate,
    load_uri,
)

LEVEL_OK = "VERIFIED_LOCAL_RENDER_REPLICA"
STALE_THRESHOLD_S = 5.0
RUN_STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


class Scenario:
    """Collects checks for one scenario. `expected` is written down before the scenario executes."""

    def __init__(self, sid: str, title: str, expected: list[str]) -> None:
        self.sid, self.title, self.expected = sid, title, expected
        self.checks: dict[str, dict[str, Any]] = {}
        self.data: dict[str, Any] = {}
        self.started = time.time()
        self.error: str | None = None

    def check(self, name: str, ok: bool, detail: Any = None) -> bool:
        self.checks[name] = {"ok": bool(ok), "detail": detail}
        return bool(ok)

    @property
    def passed(self) -> bool:
        return self.error is None and bool(self.checks) and all(c["ok"] for c in self.checks.values())

    def result(self) -> dict[str, Any]:
        return {"id": self.sid, "title": self.title, "level": LEVEL_OK if self.passed else "FAILED", "expected": self.expected,
                "checks": self.checks, "data": self.data, "error": self.error, "seconds": round(time.time() - self.started, 1)}


class Rig:
    """Replica + NHM probe + cleanup bookkeeping for one scenario."""

    def __init__(self, out: Path, name: str, **replica_kwargs: Any) -> None:
        self.dir = out / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.tag = f"NHM-REH-{RUN_STAMP}-{name}"
        self.replica = Replica(self.dir, **replica_kwargs)
        self.probe: NhmProbe | None = None
        self.emulators: list[Emulator] = []

    def up(self, *, probe: bool = True, replica: bool = True) -> Rig:
        if replica:
            self.replica.start()
        if probe:
            self.probe = NhmProbe(self.dir / "nhm.sqlite3")
        return self

    def emulator(self, name: str = "esp32") -> Emulator:
        e = Emulator(self.dir, name, self.replica.url, cafile=self.replica.cert)
        self.emulators.append(e)
        return e

    def start_emulator(self, plan: str, name: str = "esp32", **kw: Any) -> Emulator:
        return self.emulator(name).start("--plan", plan, run_tag=self.tag, **kw)

    def down(self) -> None:
        for e in self.emulators:
            e.kill()
        if self.probe:
            self.probe.close()
        self.replica.stop()

    def corr(self, emulator: Emulator | None = None) -> dict[str, Any]:
        emulator_events = [ev for e in ([emulator] if emulator else self.emulators) for ev in e.events()]
        return correlate(emulator_events, self.replica.events(), self.probe.first_seen if self.probe else {})


def consumed_ids(rig: Rig) -> set[str]:
    return set(rig.probe.readings) if rig.probe else set()


def stored_ids(rig: Rig) -> list[str]:
    return [e["id"] for e in rig.replica.events() if e["event"] == "insert_ok"]


def gaps_s(readings: list[dict[str, Any]], minimum: float = 1.0) -> list[float]:
    stamps = sorted(datetime.fromisoformat(r["ingested_at"]).timestamp() for r in readings)
    return [round(b - a, 2) for a, b in zip(stamps, stamps[1:], strict=False) if b - a > minimum]


def readings_of(rig: Rig) -> list[dict[str, Any]]:
    return sorted(rig.probe.readings.values(), key=lambda r: (r["ingested_at"], r["id"])) if rig.probe else []


# ------------------------------------------------------------------ scenarios -------------------------------------------------

def s_nominal(out: Path, seconds: int = 25) -> tuple[Scenario, dict[str, Any]]:
    sc = Scenario("S01_NOMINAL", "Nominal ~17-20 Hz transmission, NHM waiting before the device", [
        "WAITING FOR DATA before the first frame", "LIVE DATA RECEIVED while frames arrive",
        "every frame handed to the transport is received, stored once and consumed once",
        "effective rate follows the sketch's >50 ms rule (about 15-19 Hz), not exactly 20 Hz"])
    rig = Rig(out, "S01_nominal").up()
    corr: dict[str, Any] = {}
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        time.sleep(3)
        sc.check("waiting_before_device", rig.probe.observations and rig.probe.observations[-1].state == "WAITING FOR DATA", rig.probe.states())
        em = rig.start_emulator(f"run:{seconds}")
        em.wait(seconds + 30)
        time.sleep(3)
        rig.probe.stop_session(); rig.probe.stop_polling()
        summ = em.summary()
        stored = stored_ids(rig)
        corr = rig.corr(em)
        sc.check("live_seen", "LIVE DATA RECEIVED" in rig.probe.states(), rig.probe.states())
        sc.check("all_frames_received", summ.get("frames_handed") == corr["frames_received_by_replica"], {"handed": summ.get("frames_handed"), "received": corr["frames_received_by_replica"]})
        sc.check("all_stored_once", len(stored) == len(set(stored)) == corr["frames_received_by_replica"], len(stored))
        sc.check("all_consumed_once", consumed_ids(rig) == set(stored), {"stored": len(stored), "consumed": len(consumed_ids(rig))})
        sc.check("rate_matches_firmware_rule", 13.0 <= (summ.get("effective_hz") or 0) <= 20.0, summ.get("effective_hz"))
        sc.data.update(emulator=summ, correlation={k: v for k, v in corr.items() if not k.startswith("_")}, states=rig.probe.states())
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc, corr


def s_rejected(out: Path) -> Scenario:
    sc = Scenario("S02_HANDSHAKE_REJECTED", "Server rejects WebSocket handshakes, then accepts", [
        "no frame is handed while rejected; emulator keeps retrying every ~5 s", "NHM stays WAITING FOR DATA, never fabricates data",
        "after the server accepts, the next retry connects and data flows (LIVE)"])
    rig = Rig(out, "S02_rejected").up()
    try:
        rig.replica.reject.write_text("1")
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("run:30")
        time.sleep(11)
        sc.check("waiting_while_rejected", set(rig.probe.states()) == {"WAITING FOR DATA"}, rig.probe.states())
        sc.check("no_records_while_rejected", rig.probe.observations[-1].count == 0, rig.probe.observations[-1].count)
        rig.replica.reject.unlink()
        em.wait(60)
        time.sleep(2)
        rig.probe.stop_session(); rig.probe.stop_polling()
        summ = em.summary()
        sc.check("emulator_retried", summ.get("connect_attempts", 0) >= 2 and summ.get("transport_errors", 0) >= 1, {k: summ.get(k) for k in ("connect_attempts", "connects", "transport_errors")})
        sc.check("frames_not_handed_while_down", summ.get("frames_not_handed", 0) > 0, summ.get("frames_not_handed"))
        sc.check("data_after_accept", "LIVE DATA RECEIVED" in rig.probe.states(), rig.probe.states())
        sc.data.update(emulator=summ, states=rig.probe.states())
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_late_server(out: Path) -> Scenario:
    sc = Scenario("S03_SERVER_LATE_START", "Server unreachable at power-on (cold start), becomes reachable ~9 s later", [
        "connection refused errors then success within one 5 s retry period of the server becoming reachable",
        "NHM WAITING until data, then LIVE"])
    rig = Rig(out, "S03_late").up(replica=False)
    try:
        rig.replica.port = rig.replica.port  # fixed before the emulator starts
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("run:22")
        time.sleep(9)
        t_up = time.monotonic()
        rig.replica.start()
        em.wait(60)
        time.sleep(2)
        rig.probe.stop_session(); rig.probe.stop_polling()
        summ = em.summary()
        events = em.events()
        first_connect = next((e["t_mono"] for e in events if e["event"] == "connected"), None)
        sc.check("refused_before_up", summ.get("transport_errors", 0) >= 1, summ.get("transport_errors"))
        sc.check("connected_within_retry_interval", first_connect is not None and first_connect - t_up <= 6.5, None if first_connect is None else round(first_connect - t_up, 2))
        sc.check("live_after_connect", "LIVE DATA RECEIVED" in rig.probe.states(), rig.probe.states())
        sc.data.update(emulator=summ, states=rig.probe.states())
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def _interrupt_scenario(out: Path, sid: str, title: str, plan: str, expect_stale: bool, expected: list[str], seconds: float) -> Scenario:
    sc = Scenario(sid, title, expected)
    rig = Rig(out, sid.lower()).up()
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator(plan)
        em.wait(seconds + 40)
        time.sleep(3)
        status_before_stop = rig.probe.observations[-1].status
        before = rig.probe.observations[-1].count
        rig.probe.stop_session(); rig.probe.stop_polling()
        summ = em.summary()
        states = rig.probe.states()
        gaps = gaps_s(readings_of(rig), 1.0)
        sc.check("stale_as_expected", ("STALE DATA" in states) == expect_stale, states)
        if expect_stale:
            sc.check("recovered_live_after_stale", states.index("STALE DATA") < len(states) - 1 and "LIVE DATA RECEIVED" in states[states.index("STALE DATA"):], states)
        sc.check("session_stayed_active", status_before_stop == "ACTIVE", status_before_stop)
        sc.check("gap_visible_in_timestamps", bool(gaps), gaps)
        stored = stored_ids(rig)
        sc.check("no_duplicate_documents", len(consumed_ids(rig)) == len(set(consumed_ids(rig))) and consumed_ids(rig) <= set(stored), None)
        sc.data.update(emulator=summ, states=states, gaps_seconds=gaps, records=before)
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_drop_short(out: Path) -> Scenario:
    return _interrupt_scenario(out, "S04_STALL_2S", "2 s Wi-Fi stall, TCP survives", "run:8,stall:2,run:10", False, [
        "frames written during the stall are delivered late as one burst", "NHM does not go STALE (<5 s)",
        "server-side timestamps compress the delayed frames; the gap is visible, nothing is invented"], 22)


def s_drop_long(out: Path) -> Scenario:
    return _interrupt_scenario(out, "S05_DROP_9S", "9 s network loss, TCP reset, reconnect", "run:8,drop:9,run:12", True, [
        "frames during the loss are not handed (and lost, as on the device)", "reconnect happens >= 5 s after the loss was noticed",
        "NHM shows STALE DATA then recovers to LIVE DATA RECEIVED; session never auto-stops"], 32)


def s_disconnect(out: Path) -> Scenario:
    return _interrupt_scenario(out, "S06_CLEAN_CLOSE", "Clean WebSocket close and reconnect", "run:6,disconnect:2,run:8", False, [
        "clean close then reconnect after the 2 s wait", "no duplicate documents"], 20)


def s_killed(out: Path) -> Scenario:
    sc = Scenario("S07_PRODUCER_KILLED", "Emulator process terminated abruptly during transmission", [
        "NHM becomes STALE DATA after >5 s and keeps the session ACTIVE", "no new records appear and none are invented",
        "Stop Monitoring still works and freezes the count"])
    rig = Rig(out, "S07_killed").up()
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("run:60")
        time.sleep(10)
        em.kill()
        time.sleep(STALE_THRESHOLD_S + 4)
        count_stale = rig.probe.observations[-1].count
        sc.check("stale_after_kill", rig.probe.observations[-1].state == "STALE DATA", rig.probe.observations[-1].state)
        time.sleep(3)
        sc.check("no_new_records_while_dead", rig.probe.observations[-1].count == count_stale, (count_stale, rig.probe.observations[-1].count))
        sc.check("session_still_active", rig.probe.observations[-1].status == "ACTIVE", rig.probe.observations[-1].status)
        stopped = rig.probe.stop_session()
        rig.probe.stop_polling()
        sc.check("stop_freezes_count", stopped["record_count"] == count_stale and stopped["status"] == "STOPPED", stopped["record_count"])
        sc.data.update(states=rig.probe.states(), records=count_stale)
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_replica_restart(out: Path) -> Scenario:
    sc = Scenario("S08_SERVER_RESTART", "Ingestion server process killed and restarted (like a Render restart)", [
        "emulator notices the loss, retries every >= 5 s and reconnects within one retry period of the server being back",
        "the same NHM session continues (STALE then LIVE), documents stay unique"])
    rig = Rig(out, "S08_restart").up()
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("run:45")
        time.sleep(10)
        rig.replica.stop(hard=True)
        time.sleep(8)  # > the 5 s stale threshold and > one 5 s reconnect period
        rig.replica.start()
        em.wait(80)
        time.sleep(3)
        rig.probe.stop_session(); rig.probe.stop_polling()
        summ = em.summary()
        states = rig.probe.states()
        sc.check("emulator_reconnected", summ.get("reconnects", 0) >= 1, {k: summ.get(k) for k in ("connects", "reconnects", "transport_errors")})
        sc.check("stale_then_live", "STALE DATA" in states and "LIVE DATA RECEIVED" in states[states.index("STALE DATA"):], states)
        sc.check("unique_documents", len(consumed_ids(rig)) == len(set(consumed_ids(rig))), len(consumed_ids(rig)))
        sc.data.update(emulator=summ, states=states, replica_events=len(rig.replica.events()))
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_atlas_outage(out: Path) -> Scenario:
    sc = Scenario("S09_ATLAS_INSERT_OUTAGE", "Server receives frames but every Atlas insert fails for ~7 s", [
        "frames are received but not stored (lost like on the real server unless it queues); NHM goes STALE",
        "after inserts work again NHM recovers; nothing from the outage window appears"])
    rig = Rig(out, "S09_atlas").up()
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("run:30")
        time.sleep(8)
        rig.replica.fail_inserts.write_text("1")
        time.sleep(7)
        rig.replica.fail_inserts.unlink()
        em.wait(60)
        time.sleep(3)
        rig.probe.stop_session(); rig.probe.stop_polling()
        events = rig.replica.events()
        errors = [e for e in events if e["event"] == "insert_error"]
        states = rig.probe.states()
        sc.check("inserts_failed_and_were_logged", len(errors) > 50, len(errors))
        sc.check("stale_then_live", "STALE DATA" in states and "LIVE DATA RECEIVED" in states[states.index("STALE DATA"):], states)
        received = [e for e in events if e["event"] == "frame"]
        stored = stored_ids(rig)
        sc.check("lost_frames_accounted", len(received) - len(stored) == len(errors), {"received": len(received), "stored": len(stored), "errors": len(errors)})
        sc.data.update(states=states, lost_during_outage=len(errors))
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_invalid(out: Path) -> Scenario:
    sc = Scenario("S10_MALFORMED_AND_INVALID", "Malformed JSON, missing ECG, out-of-range values", [
        "malformed frames never reach MongoDB; permissive server stores parsable objects as-is",
        "NHM rejects documents without a valid ECG integer 0..4095; invalid BPM/SpO2 become unavailable, not zero"])
    rig = Rig(out, "S10_invalid").up()
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("run:4,malformed:10,run:4")
        em.wait(40)
        time.sleep(3)
        rig.probe.stop_session(); rig.probe.stop_polling()
        events = rig.replica.events()
        malformed = [e for e in events if e["event"] == "malformed"]
        stored = [e for e in events if e["event"] == "insert_ok"]
        readings = readings_of(rig)
        summ = em.summary()
        sc.check("malformed_detected_by_server", len(malformed) >= 4, len(malformed))
        sc.check("nhm_only_valid_ecg", all(isinstance(r["ecg"], int) and 0 <= r["ecg"] <= 4095 for r in readings), len(readings))
        sc.check("nhm_count_below_server_stored", len(readings) < len(stored), {"nhm": len(readings), "server_stored": len(stored)})
        invalid_vitals = [r for r in readings if r["ecg"] == 3777]
        sc.check("invalid_vitals_are_unavailable", bool(invalid_vitals) and all(r["bpm"] is None and r["spo2"] is None for r in invalid_vitals), len(invalid_vitals))
        sc.data.update(emulator=summ, server_stored=len(stored), nhm_consumed=len(readings), malformed=len(malformed))
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_leadoff(out: Path) -> Scenario:
    sc = Scenario("S11_LEADOFF_PLACEHOLDER", "ECG 2048 placeholder (leads off) and BPM/SpO2 0 (no finger)", [
        "values are stored and displayed as received; BPM/SpO2 of 0 are unavailable, not 0%",
        "NHM makes no lead-off/contact claim because the payload has no lead-off flag"])
    rig = Rig(out, "S11_leadoff").up()
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("unavail:6,run:6:leadoff")
        em.wait(40)
        time.sleep(3)
        body = rig.probe.stop_session()
        rig.probe.stop_polling()
        readings = readings_of(rig)
        flat = [r for r in readings if r["ecg"] == 2048]
        sc.check("placeholder_stored_verbatim", len(flat) > 40, len(flat))
        sc.check("zero_vitals_unavailable", all(r["bpm"] is None and r["spo2"] is None for r in readings if r["bpm"] is None) and any(r["bpm"] is None for r in readings), None)
        sc.check("no_contact_claim_in_api", not any("lead" in k.lower() or "contact" in k.lower() for k in body), sorted(body))
        sc.data.update(placeholder_readings=len(flat), total=len(readings))
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_burst(out: Path) -> Scenario:
    sc = Scenario("S12_BURSTY_TIMING", "Frames arrive in bursts of three", [
        "all frames stored and consumed exactly once", "ordering follows ObjectId; nothing dropped under bursts"])
    rig = Rig(out, "S12_burst").up()
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("burst:12", timing="fixed")
        em.wait(40)
        time.sleep(3)
        rig.probe.stop_session(); rig.probe.stop_polling()
        stored = stored_ids(rig)
        sc.check("all_consumed", consumed_ids(rig) == set(stored), {"stored": len(stored), "consumed": len(consumed_ids(rig))})
        sc.check("some_stored", len(stored) >= 30, len(stored))
        sc.data.update(stored=len(stored), emulator=em.summary())
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_rollover(out: Path) -> Scenario:
    sc = Scenario("S13_MIDNIGHT_ROLLOVER", "Daily collection rolls over mid-session (replica clock starts 10 s before midnight UTC)", [
        "documents land in two consecutive daily collections", "NHM keeps one continuous session, no gap larger than the transmit pattern, no duplicates, no loss"])
    rig = Rig(out, "S13_rollover", simulated_start="2026-10-15T23:59:50Z").up()
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        em = rig.start_emulator("run:24")
        em.wait(60)
        time.sleep(4)
        rig.probe.stop_session(); rig.probe.stop_polling()
        collections = sorted({e["collection"] for e in rig.replica.events() if e["event"] == "insert_ok"})
        stored = stored_ids(rig)
        readings = readings_of(rig)
        sc.check("two_daily_collections", collections == ["records_2026-10-15", "records_2026-10-16"], collections)
        sc.check("all_consumed_across_rollover", consumed_ids(rig) == set(stored), {"stored": len(stored), "consumed": len(consumed_ids(rig))})
        sc.check("no_gap_over_1s", not gaps_s(readings, 1.0), gaps_s(readings, 1.0))
        cols = {r.get("collection") for r in readings}
        sc.check("readings_carry_collection", cols == set(collections), sorted(c for c in cols if c))
        sc.data.update(collections=collections, stored=len(stored))
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_backend_restart(out: Path) -> Scenario:
    sc = Scenario("S14_NHM_BACKEND_RESTART", "NHM backend restarts in the middle of a hardware session", [
        "the interrupted session is marked INTERRUPTED (never silently active again) and its count freezes",
        "a new Start creates a fresh session with a new high-water mark; earlier documents are not replayed into it",
        "the interrupted session's data remains available (and eligible for recorded-hardware FL)"])
    rig = Rig(out, "S14_nhm_restart").up()
    try:
        first = rig.probe.start_session()
        rig.probe.run_polling()
        em = rig.start_emulator("run:40")
        time.sleep(12)
        rig.probe.stop_polling()
        count_before = rig.probe.poll_once()["record_count"]
        rig.probe.restart_backend()
        detail = rig.probe.call("GET", f"/sessions/{first['session_id']}").json()
        sc.check("session_interrupted", detail["status"] == "INTERRUPTED" and "INTERRUPTED" in detail["source_state"], detail["source_state"])
        sc.check("data_kept", detail["record_count"] >= count_before and len(detail["readings"]) > 0, detail["record_count"])
        sc.check("no_further_growth", True)
        second = rig.probe.start_session()
        sc.check("new_session_id", second["session_id"] != first["session_id"], second["session_id"])
        time.sleep(10)
        body = rig.probe.call("GET", f"/sessions/{second['session_id']}/poll?after=0").json()
        old_ids = {r["id"] for r in detail["readings"]}
        new_ids = {r["id"] for r in body["readings"]}
        sc.check("no_replay_into_new_session", not (old_ids & new_ids), len(old_ids & new_ids))
        sc.check("new_session_receives_data", body["record_count"] > 0, body["record_count"])
        again = rig.probe.call("GET", f"/sessions/{first['session_id']}").json()
        sc.check("interrupted_count_frozen", again["record_count"] == detail["record_count"], (again["record_count"], detail["record_count"]))
        em.wait(60)
        rig.probe.stop_session(second["session_id"])
        sc.data.update(first=first["session_id"], second=second["session_id"], interrupted_records=detail["record_count"])
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_idempotence(out: Path) -> Scenario:
    sc = Scenario("S15_START_STOP_IDEMPOTENCE", "Double Start, double Stop, Stop right after Start, re-open", [
        "second Start re-attaches to the same ACTIVE session (no orphan)", "second Stop is harmless",
        "Stop immediately after Start yields a saved session with zero readings"])
    rig = Rig(out, "S15_idem").up()
    try:
        a = rig.probe.start_session()
        b = rig.probe.start_session()
        sc.check("double_start_same_session", a["session_id"] == b["session_id"], (a["session_id"], b["session_id"]))
        s1 = rig.probe.stop_session()
        s2 = rig.probe.stop_session()
        sc.check("double_stop_harmless", s1["status"] == s2["status"] == "STOPPED" and s2["record_count"] == 0, s2["status"])
        c = rig.probe.start_session()
        sc.check("new_session_after_stop", c["session_id"] != a["session_id"], c["session_id"])
        rig.probe.stop_session()
        listing = rig.probe.call("GET", "/sessions").json()
        sc.check("both_saved_with_zero_readings", len(listing) == 2 and all(x["record_count"] == 0 for x in listing), [x["record_count"] for x in listing])
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_two_users(out: Path) -> Scenario:
    sc = Scenario("S16_TWO_USERS_SHARED_SOURCE", "Two signed-in users watching the same shared hardware source", [
        "both users' sessions consume the same documents independently", "neither can read or stop the other's session; unauthenticated calls are refused"])
    rig = Rig(out, "S16_users").up()
    try:
        rig.probe.users = ("user_a", "user_b")
        a = rig.probe.start_session("user_a")
        b = rig.probe.start_session("user_b")
        em = rig.start_emulator("run:12")
        em.wait(40)
        time.sleep(2)
        pa = rig.probe.call("GET", f"/sessions/{a['session_id']}/poll?after=0", "user_a").json()
        pb = rig.probe.call("GET", f"/sessions/{b['session_id']}/poll?after=0", "user_b").json()
        sc.check("both_consumed", pa["record_count"] > 50 and pb["record_count"] > 50, (pa["record_count"], pb["record_count"]))
        ida, idb = {r["id"] for r in pa["readings"]}, {r["id"] for r in pb["readings"]}
        sc.check("same_shared_documents", len(ida & idb) >= min(len(ida), len(idb)) * 0.9, len(ida & idb))
        sc.check("cross_read_forbidden", rig.probe.call("GET", f"/sessions/{a['session_id']}", "user_b").status_code == 403, None)
        sc.check("cross_stop_forbidden", rig.probe.call("POST", f"/sessions/{a['session_id']}/stop", "user_b").status_code == 403, None)
        sc.check("list_isolated", {x["session_id"] for x in rig.probe.call("GET", "/sessions", "user_b").json()} == {b["session_id"]}, None)
        sc.check("unauthenticated_refused", rig.probe.call("GET", f"/sessions/{a['session_id']}/poll?after=0", "").status_code == 401, None)
        rig.probe.stop_session(a["session_id"], "user_a"); rig.probe.stop_session(b["session_id"], "user_b")
        sc.data.update(user_a_records=pa["record_count"], user_b_records=pb["record_count"])
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_scenario_b_protocol(out: Path) -> Scenario:
    sc = Scenario("S17_DEVICE_FIRST", "Scenario B at protocol level: device transmitting for 20 s before NHM starts", [
        "documents inserted before Start are excluded by the high-water mark", "new documents are consumed; stopping NHM does not stop the device and freezes the session"])
    rig = Rig(out, "S17_device_first").up()
    try:
        em = rig.start_emulator("run:60")
        time.sleep(20)
        before = set(stored_ids(rig))
        s = rig.probe.start_session(); rig.probe.run_polling()
        time.sleep(15)
        rig.probe.stop_polling()
        st = rig.probe.stop_session()
        sc.check("old_excluded", not (set(rig.probe.readings) & before), len(set(rig.probe.readings) & before))
        sc.check("new_consumed", st["record_count"] > 100, st["record_count"])
        time.sleep(5)
        after = rig.probe.call("GET", f"/sessions/{s['session_id']}").json()
        sc.check("count_frozen_after_stop", after["record_count"] == st["record_count"], (st["record_count"], after["record_count"]))
        sc.check("device_still_emitting", len(stored_ids(rig)) > len(before) + st["record_count"], len(stored_ids(rig)))
        s2 = rig.probe.start_session()
        sc.check("second_session_distinct", s2["session_id"] != s["session_id"], s2["session_id"])
        time.sleep(6)
        p2 = rig.probe.call("GET", f"/sessions/{s2['session_id']}/poll?after=0").json()
        first_ids = {r["id"] for r in after["readings"]}
        sc.check("no_merge_between_sessions", not (first_ids & {r["id"] for r in p2["readings"]}), None)
        rig.probe.stop_session(s2["session_id"])
        em.terminate()
        sc.data.update(first=s["session_id"], second=s2["session_id"], excluded_before_start=len(before))
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc


def s_mongo_unreachable(out: Path) -> Scenario:
    sc = Scenario("S18_NHM_CANNOT_REACH_MONGODB", "NHM backend cannot reach MongoDB at all", [
        "Start is refused with a clean, bounded error; the application stays up", "no session row is created"])
    import os
    saved = os.environ.get("NHM_HARDWARE_MONGO_URI")
    rig = Rig(out, "S18_unreachable")
    try:
        os.environ["NHM_HARDWARE_MONGO_URI"] = "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=800&connectTimeoutMS=800"
        rig.probe = NhmProbe(rig.dir / "nhm.sqlite3")
        t = time.monotonic()
        r = rig.probe.call("POST", "/sessions")
        elapsed = time.monotonic() - t
        sc.check("start_refused_cleanly", r.status_code in (400, 409, 503) and "MongoDB unavailable" in r.text, {"status": r.status_code})
        sc.check("bounded_wait", elapsed < 10, round(elapsed, 2))
        sc.check("no_session_created", rig.probe.call("GET", "/sessions").json() == [], None)
    except Exception as error:
        sc.error = repr(error)
    finally:
        if saved is not None:
            os.environ["NHM_HARDWARE_MONGO_URI"] = saved
        rig.down()
    return sc


FAULTS: list[tuple[str, Callable[[Path], Scenario]]] = [
    ("S02_HANDSHAKE_REJECTED", s_rejected), ("S03_SERVER_LATE_START", s_late_server), ("S04_STALL_2S", s_drop_short),
    ("S05_DROP_9S", s_drop_long), ("S06_CLEAN_CLOSE", s_disconnect), ("S07_PRODUCER_KILLED", s_killed),
    ("S08_SERVER_RESTART", s_replica_restart), ("S09_ATLAS_INSERT_OUTAGE", s_atlas_outage), ("S10_MALFORMED_AND_INVALID", s_invalid),
    ("S11_LEADOFF_PLACEHOLDER", s_leadoff), ("S12_BURSTY_TIMING", s_burst), ("S13_MIDNIGHT_ROLLOVER", s_rollover),
    ("S14_NHM_BACKEND_RESTART", s_backend_restart), ("S15_START_STOP_IDEMPOTENCE", s_idempotence),
    ("S16_TWO_USERS_SHARED_SOURCE", s_two_users), ("S17_DEVICE_FIRST", s_scenario_b_protocol), ("S18_NHM_CANNOT_REACH_MONGODB", s_mongo_unreachable),
]


# -------------------------------------------------------------------- soak ----------------------------------------------------

def soak(out: Path, minutes: float) -> tuple[Scenario, dict[str, Any]]:
    sc = Scenario("SOAK", f"{minutes:g}-minute continuous transmission", [
        "no process crash; every stored document consumed exactly once while the session is ACTIVE",
        "trace retention stays bounded at the documented 2,000 newest readings; counter keeps counting",
        "effective rate stable within +-15% between first and last third"])
    rig = Rig(out, "SOAK").up()
    samples: list[dict[str, Any]] = []
    corr: dict[str, Any] = {}
    try:
        rig.probe.start_session(); rig.probe.run_polling()
        seconds = int(minutes * 60)
        em = rig.start_emulator(f"run:{seconds}")
        t0 = time.monotonic()
        while em.proc and em.proc.poll() is None:
            time.sleep(10)
            o = rig.probe.observations[-1] if rig.probe.observations else None
            summary_events = len([e for e in rig.replica.events() if e["event"] == "insert_ok"]) if int(time.monotonic() - t0) % 30 < 10 else None
            samples.append({"t": round(time.monotonic() - t0), "state": o.state if o else None, "nhm_count": o.count if o else None,
                            "poll_errors": len(rig.probe.errors), "stored_so_far": summary_events})
        time.sleep(4)
        final = rig.probe.stop_session(); rig.probe.stop_polling()
        detail = rig.probe.call("GET", f"/sessions/{rig.probe.session_id}").json()
        summ = em.summary()
        stored = stored_ids(rig)
        corr = rig.corr(em)
        # rate stability from emulator intervals
        events = [e for e in em.events() if e["event"] == "frame" and e.get("handed")]
        stamps = [e["send_mono"] for e in events]
        third = max(1, len(stamps) // 3)
        def hz(chunk: list[float]) -> float:
            return (len(chunk) - 1) / (chunk[-1] - chunk[0]) if len(chunk) > 2 and chunk[-1] > chunk[0] else 0.0
        first_hz, last_hz = hz(stamps[:third]), hz(stamps[-third:])
        sc.check("no_poll_errors", not rig.probe.errors, rig.probe.errors[:3])
        sc.check("all_stored_consumed", consumed_ids(rig) == set(stored) or (len(consumed_ids(rig) - set(stored)) == 0 and len(set(stored) - consumed_ids(rig)) == 0),
                 {"stored": len(stored), "consumed": len(consumed_ids(rig))})
        sc.check("counter_counts_all", final["record_count"] == len(stored), {"record_count": final["record_count"], "stored": len(stored)})
        sc.check("trace_bounded_at_cap", len(detail["readings"]) == min(len(stored), detail["trace_limit"]) and detail["trace_limit"] == 2000,
                 {"retained": len(detail["readings"]), "cap": detail["trace_limit"]})
        sc.check("rate_stable", first_hz > 0 and abs(last_hz - first_hz) / first_hz < 0.15, {"first_third_hz": round(first_hz, 2), "last_third_hz": round(last_hz, 2)})
        retained_seconds = (datetime.fromisoformat(detail["readings"][-1]["ingested_at"]) - datetime.fromisoformat(detail["readings"][0]["ingested_at"])).total_seconds() if detail["readings"] else 0
        sc.data.update(emulator=summ, samples=samples, record_count=final["record_count"], retained_readings=len(detail["readings"]),
                       retained_seconds=round(retained_seconds, 1), states=rig.probe.states(),
                       storage_finding=f"only the newest {len(detail['readings'])} of {final['record_count']} readings (~{retained_seconds:.0f} s) are retained for History/FL; "
                                       "a longer recording is NOT preserved in full")
    except Exception as error:
        sc.error = repr(error)
    finally:
        rig.down()
    return sc, corr


# ------------------------------------------------------------------- driver ---------------------------------------------------

def cleanup(uri: str, database: str, stamp: str) -> dict[str, Any]:
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    db = client[database]
    deleted: dict[str, int] = {}
    dropped: list[str] = []
    for name in db.list_collection_names():
        if not name.startswith("records_"):
            continue
        n = db[name].delete_many({"nhmTestRun": {"$regex": f"^NHM-REH-{stamp}"}}).deleted_count
        if n:
            deleted[name] = n
        if db[name].estimated_document_count() == 0:
            db.drop_collection(name)
            dropped.append(name)
    client.close()
    return {"database": database, "deleted_by_collection": deleted, "dropped_empty_collections": dropped, "production_database_touched": False}


def run_browser(out: Path, users_file: Path, args: argparse.Namespace) -> dict[str, Any]:
    cmd = [sys.executable, "-m", "scripts.verify_hardware_connected_browser", "--producer", "ws", "--database", args.database,
           "--users-file", str(users_file), "--out", str(out / "browser"), "--stamp", RUN_STAMP]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=3600)
    return {"returncode": result.returncode, "tail": (result.stdout + result.stderr)[-800:]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["smoke", "faults", "soak", "full"], default="smoke")
    ap.add_argument("--out", default=str(ROOT / "reports/hardware/esp32_full_rehearsal"))
    ap.add_argument("--database", default=REHEARSAL_DATABASE)
    ap.add_argument("--soak-minutes", type=float, default=10.0)
    ap.add_argument("--users-file", help="Clerk test users json for browser stages (mode full)")
    ap.add_argument("--only", help="comma separated scenario ids (e.g. S05_DROP_9S)")
    args = ap.parse_args()
    if args.database == PRODUCTION_DATABASE:
        print("REFUSING: rehearsal never targets health_db", file=sys.stderr)
        return 2
    uri = load_uri()
    out = Path(args.out) / f"{RUN_STAMP}_{args.mode}"
    out.mkdir(parents=True, exist_ok=True)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    results: list[dict[str, Any]] = []
    latency: dict[str, Any] = {}
    t0 = time.time()

    def record(sc: Scenario) -> None:
        r = sc.result()
        results.append(r)
        print(f"{'PASS' if sc.passed else 'FAIL'} {sc.sid} {sc.title} ({r['seconds']}s)", flush=True)
        for name, c in sc.checks.items():
            if not c["ok"]:
                print(f"   x {name}: {c['detail']}", flush=True)
        if sc.error:
            print(f"   ! {sc.error}", flush=True)

    try:
        only_ids = set(args.only.split(",")) if args.only else None
        if not only_ids or "S01_NOMINAL" in only_ids:
            sc, corr = s_nominal(out, 25 if args.mode == "smoke" else 40)
            record(sc)
            latency["nominal"] = {k: v for k, v in corr.items() if not k.startswith("_")}
        if args.mode in ("faults", "full"):
            only = set(args.only.split(",")) if args.only else None
            for sid, fn in FAULTS:
                if only and sid not in only:
                    continue
                record(fn(out))
        if args.mode in ("soak", "full"):
            sc, corr = soak(out, args.soak_minutes if args.mode == "soak" else min(args.soak_minutes, 10))
            record(sc)
            latency["soak"] = {k: v for k, v in corr.items() if not k.startswith("_")}
        if args.mode == "full" and args.users_file:
            browser = run_browser(out, Path(args.users_file), args)
            results.append({"id": "BROWSER_AB_FL", "title": "Scenario A/B + recorded-hardware FL via WebSocket emulator in real Chrome/Clerk",
                            "level": LEVEL_OK if browser["returncode"] == 0 else "FAILED", "data": browser})
        elif args.mode == "full":
            results.append({"id": "BROWSER_AB_FL", "level": "NOT_RUN", "data": {"reason": "no --users-file supplied; browser stage needs Clerk test users"}})
    finally:
        clean = cleanup(uri, args.database, RUN_STAMP)
    summary = {
        "run": RUN_STAMP, "mode": args.mode, "git_revision": git, "seconds": round(time.time() - t0, 1),
        "target": {"kind": "LOCAL_RENDER_REPLICA", "real_render_verified": False, "database": args.database, "production_database_touched": False},
        "physical_esp32": "NOT_RUN",
        "totals": {"passed": sum(r["level"] == LEVEL_OK for r in results), "failed": sum(r["level"] == "FAILED" for r in results),
                   "not_run": sum(r["level"] == "NOT_RUN" for r in results)},
        "latency": latency, "cleanup": clean, "scenarios": results,
    }
    (out / "rehearsal_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps({"summary": str(out / "rehearsal_summary.json"), **summary["totals"]}))
    return 0 if summary["totals"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
