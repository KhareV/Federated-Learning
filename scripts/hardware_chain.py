"""Chain harness: virtual ESP32 -> (local replica | staging) WebSocket server -> Atlas -> NHM backend.

Provides managed subprocesses (replica, emulator), an in-process NHM backend probe that exercises the real
``HardwareSessions`` + authenticated REST routes against the same Atlas database the replica writes to,
and the cross-stage correlation that produces the latency report.

Evidence levels (never conflate): the replica is NOT the deployed Render service.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv-studio311/bin/python")
REHEARSAL_DATABASE = "nhm_rehearsal"
PRODUCTION_DATABASE = "health_db"
LEVELS = (
    "VERIFIED_DIRECT_ATLAS_INJECTION",
    "VERIFIED_WEBSOCKET_TO_STAGING_RENDER_TO_ATLAS",
    "VERIFIED_LOCAL_RENDER_REPLICA",
    "VERIFIED_PHYSICAL_ESP32_PRODUCTION",
    "NOT_RUN",
    "FAILED",
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def load_uri(env_file: Path | None = None) -> str:
    uri = os.environ.get("NHM_HARDWARE_MONGO_URI")
    if uri:
        return uri
    from dotenv import dotenv_values

    values = dotenv_values(env_file or ROOT / ".env")
    uri = values.get("NHM_HARDWARE_MONGO_URI")
    if not uri:
        raise SystemExit("NHM_HARDWARE_MONGO_URI is not configured (never printed)")
    return str(uri)


class Replica:
    """The local Render replica as a managed subprocess. Flags files toggle injected faults."""

    def __init__(self, workdir: Path, *, database: str = REHEARSAL_DATABASE, port: int | None = None, tz: str = "UTC",
                 simulated_start: str | None = None, tls: bool = False, sink: str = "mongo", insert_concurrency: int = 4) -> None:
        if database == PRODUCTION_DATABASE:
            raise SystemExit("refusing to point the replica at the production database")
        self.workdir = workdir
        self.port = port or free_port()
        self.database, self.tz, self.simulated_start, self.tls, self.sink = database, tz, simulated_start, tls, sink
        self.insert_concurrency = insert_concurrency
        self.event_log = workdir / "replica_events.jsonl"
        self.fail_inserts = workdir / "FAIL_INSERTS"
        self.reject = workdir / "REJECT_HANDSHAKES"
        self.proc: subprocess.Popen[str] | None = None
        self.cert: str | None = None
        self.out = workdir / "replica_stdout.log"

    @property
    def url(self) -> str:
        return f"{'wss' if self.tls else 'ws'}://127.0.0.1:{self.port}/"

    def start(self, timeout: float = 20.0) -> None:
        cmd = [PYTHON, "-m", "scripts.render_replica_server", "--port", str(self.port), "--database", self.database,
               "--collection-timezone", self.tz, "--event-log", str(self.event_log), "--insert-concurrency", str(self.insert_concurrency),
               "--fail-inserts-file", str(self.fail_inserts), "--reject-file", str(self.reject), "--sink", self.sink,
               "--sink-file", str(self.workdir / "replica_sink.jsonl")]
        if self.simulated_start:
            cmd += ["--simulated-start", self.simulated_start]
        if self.tls:
            cmd += ["--tls"]
        env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}"}
        if self.sink == "mongo":
            env["NHM_HARDWARE_MONGO_URI"] = load_uri()
        self.proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=self.out.open("a"), stderr=subprocess.STDOUT, text=True)
        end = time.time() + timeout
        while time.time() < end:
            text = self.out.read_text() if self.out.exists() else ""
            for line in text.splitlines():
                if line.startswith("TLS_CERT="):
                    self.cert = line.split("=", 1)[1]
            if "REPLICA_READY" in text:
                return
            if self.proc.poll() is not None:
                raise RuntimeError(f"replica exited early: {text[-400:]}")
            time.sleep(0.1)
        raise RuntimeError("replica did not become ready")

    def stop(self, hard: bool = False) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL if hard else signal.SIGINT)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def events(self) -> list[dict[str, Any]]:
        if not self.event_log.exists():
            return []
        return [json.loads(line) for line in self.event_log.read_text().splitlines() if line.strip()]


class Emulator:
    def __init__(self, workdir: Path, name: str, url: str, *, cafile: str | None = None) -> None:
        self.name, self.url, self.cafile, self.workdir = name, url, cafile, workdir
        self.event_log = workdir / f"emulator_{name}_events.jsonl"
        self.summary_file = workdir / f"emulator_{name}_summary.json"
        self.proc: subprocess.Popen[str] | None = None

    def start(self, *args: str, run_tag: str | None = None, timing: str = "firmware", seed: int = 20261015) -> Emulator:
        cmd = [PYTHON, "-m", "scripts.emulate_esp32_ws", "--url", self.url, "--timing", timing, "--seed", str(seed),
               "--event-log", str(self.event_log), "--summary-file", str(self.summary_file), *args]
        if self.cafile:
            cmd += ["--cafile", self.cafile]
        if run_tag:
            cmd += ["--run-tag", run_tag]
        env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}"}
        env.pop("NHM_HARDWARE_MONGO_URI", None)  # the emulator must not hold database credentials
        self.proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=(self.workdir / f"emulator_{self.name}.log").open("w"), stderr=subprocess.STDOUT, text=True)
        return self

    def wait(self, timeout: float = 300) -> int | None:
        assert self.proc
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return None

    def terminate(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def kill(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)

    def summary(self) -> dict[str, Any]:
        return json.loads(self.summary_file.read_text()) if self.summary_file.exists() else {}

    def events(self) -> list[dict[str, Any]]:
        if not self.event_log.exists():
            return []
        out = []
        for line in self.event_log.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out


@dataclass
class Observation:
    mono: float
    state: str
    count: int
    status: str


@dataclass
class NhmProbe:
    """The real NHM hardware backend (service + authenticated REST routes), polled like the browser does (800 ms)."""

    sqlite_path: Path
    database: str = REHEARSAL_DATABASE
    collection: str = "records_*"
    poll_interval: float = 0.8
    users: tuple[str, ...] = ("user_rehearsal_a",)
    first_seen: dict[str, float] = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    readings: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.session_id: str | None = None
        self._build()

    def _build(self) -> None:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient

        from api.hardware_telemetry_routes import install_hardware_routes
        from capstone_persistence.store import CapstoneSqliteStore
        from product.api.errors import ProductError
        from product.auth.base import AuthIdentity, AuthProviderType

        app = FastAPI()
        self.store = CapstoneSqliteStore(self.sqlite_path)

        async def identity(request: Request) -> Any:
            user = request.headers.get("x-test-user")
            if not user:
                return None
            return AuthIdentity(user_id=user, auth_provider=AuthProviderType.CLERK, auth_session_id="rehearsal", demo_mode=False)

        @app.exception_handler(ProductError)
        async def error(_request: Request, exc: ProductError) -> Any:
            return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

        env = {"NHM_HARDWARE_MONGO_ENABLED": "true", "NHM_HARDWARE_MONGO_URI": load_uri(),
               "NHM_HARDWARE_MONGO_DATABASE": self.database, "NHM_HARDWARE_MONGO_COLLECTION": self.collection}
        install_hardware_routes(app, self.store, identity, env)
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()

    def restart_backend(self) -> None:
        """Simulate the NHM product backend restarting (same SQLite file, new service instance)."""
        with self.lock:
            self._cm.__exit__(None, None, None)
            self._build()

    def call(self, method: str, path: str, user: str | None = None, **kw: Any) -> Any:
        headers = {"x-test-user": user or self.users[0]} if user != "" else {}
        with self.lock:
            return self.client.request(method, f"/product/v1/hardware{path}", headers=headers, **kw)

    def start_session(self, user: str | None = None) -> dict[str, Any]:
        r = self.call("POST", "/sessions", user)
        r.raise_for_status()
        body = r.json()
        if (user or self.users[0]) == self.users[0]:
            self.session_id = body["session_id"]
        return body

    def stop_session(self, sid: str | None = None, user: str | None = None) -> dict[str, Any]:
        r = self.call("POST", f"/sessions/{sid or self.session_id}/stop", user)
        r.raise_for_status()
        return r.json()

    def poll_once(self, sid: str | None = None, user: str | None = None) -> dict[str, Any] | None:
        sid = sid or self.session_id
        if not sid:
            return None
        try:
            r = self.call("GET", f"/sessions/{sid}/poll?after=0", user)
            now = time.monotonic()
            if r.status_code != 200:
                self.errors.append(f"poll {r.status_code}")
                return None
            body = r.json()
        except Exception as error:
            self.errors.append(type(error).__name__)
            return None
        for reading in body["readings"]:
            if reading["id"] not in self.first_seen:
                self.first_seen[reading["id"]] = now
            self.readings[reading["id"]] = reading
        self.observations.append(Observation(now, body["source_state"], body["record_count"], body["status"]))
        return body

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.poll_interval)

    def run_polling(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop_polling(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def wait_state(self, wanted: str, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.observations and wanted in self.observations[-1].state:
                return True
            time.sleep(0.1)
        return False

    def states(self) -> list[str]:
        out: list[str] = []
        for o in self.observations:
            if not out or out[-1] != o.state:
                out.append(o.state)
        return out

    def close(self) -> None:
        self.stop_polling()
        with self.lock:
            self._cm.__exit__(None, None, None)


# ---------------------------------------------------------------- correlation ------------------------------------------------

def _tuple(text: str) -> tuple[Any, ...] | None:
    try:
        d = json.loads(text)
        return (d.get("bpm"), d.get("spo2"), d.get("ecg"))
    except Exception:
        return None


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(p * len(s)))], 3)


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "status": "UNMEASURED"}
    return {"n": len(values), "min": round(min(values), 3), "p50": pct(values, 0.5), "p95": pct(values, 0.95), "p99": pct(values, 0.99),
            "max": round(max(values), 3), "mean": round(sum(values) / len(values), 3)}


def correlate(emulator_events: list[dict[str, Any]], replica_events: list[dict[str, Any]], nhm_first_seen: dict[str, float],
              session_ids: set[str] | None = None) -> dict[str, Any]:
    """Stage-by-stage latency (milliseconds) and loss accounting. Monotonic clocks are comparable on one host."""
    sent = [e for e in emulator_events if e["event"] == "frame" and e.get("handed") and not e.get("malformed")]
    received = [e for e in replica_events if e["event"] == "frame"]
    inserted = {e["id"]: e for e in replica_events if e["event"] == "insert_ok"}
    # Pair received frames with their insert acknowledgement through the replica's own ordering (same conn, same tuple).
    by_value: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for ins in inserted.values():
        by_value.setdefault((ins.get("bpm"), ins.get("spo2"), ins.get("ecg")), []).append(ins)
    pointer = 0
    s1: list[float] = []
    s2: list[float] = []
    s3: list[float] = []
    e2e: list[float] = []
    unmatched = 0
    used_inserts: set[str] = set()
    for frame in sent:
        key = _tuple(frame["text"])
        match = None
        while pointer < len(received):
            rec = received[pointer]
            if (rec.get("bpm"), rec.get("spo2"), rec.get("ecg")) == key and rec["received_mono"] >= frame["send_mono"] - 0.02:
                match = rec
                pointer += 1
                break
            if rec["received_mono"] > frame["send_mono"] + 10:
                break
            pointer += 1
        if match is None:
            unmatched += 1
            continue
        s1.append((match["received_mono"] - frame["send_mono"]) * 1000)
        candidates = [i for i in by_value.get(key, []) if i["id"] not in used_inserts and abs(i["received_mono"] - match["received_mono"]) < 1e-6]
        if not candidates:
            continue
        ins = candidates[0]
        used_inserts.add(ins["id"])
        s2.append((ins["insert_ack_mono"] - ins["received_mono"]) * 1000)
        seen = nhm_first_seen.get(ins["id"])
        if seen is not None:
            s3.append((seen - ins["insert_ack_mono"]) * 1000)
            e2e.append((seen - frame["send_mono"]) * 1000)
    consumed = set(nhm_first_seen)
    stored_after_start = {i for i, e in inserted.items() if not nhm_first_seen or e["insert_ack_mono"] >= min(nhm_first_seen.values()) - 3600}
    return {
        "frames_handed_by_emulator": len(sent),
        "frames_received_by_replica": len(received),
        "documents_inserted": len(inserted),
        "documents_consumed_by_nhm": len(consumed),
        "emulator_frames_unmatched_at_replica": unmatched,
        "consumed_not_in_replica_log": len(consumed - set(inserted)),
        "latency_ms": {
            "emulator_send_to_replica_receipt": stats(s1),
            "replica_receipt_to_atlas_ack": stats(s2),
            "atlas_ack_to_nhm_consumption": stats(s3),
            "nhm_consumption_to_browser_display": {"n": 0, "status": "UNMEASURED_IN_PROTOCOL_RUN"},
            "emulator_send_to_nhm_consumption": stats(e2e),
        },
        "note": "stage 'atlas_ack_to_nhm_consumption' is dominated by the 800 ms NHM poll interval by design",
        "_inserted_ids": sorted(stored_after_start),
    }


def browser_latency(seen_wall_ms: dict[str, float], replica_events: list[dict[str, Any]], emulator_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Atlas-ack -> browser display and emulator-send -> browser display, from wall clocks of one host (ms resolution)."""
    def wall(ts: str) -> float:
        return datetime.fromisoformat(ts).timestamp() * 1000.0

    acks = {e["id"]: e for e in replica_events if e["event"] == "insert_ok"}
    ack_to_display = [seen - wall(acks[i]["t_wall"]) for i, seen in seen_wall_ms.items() if i in acks]
    sent = [e for e in emulator_events if e["event"] == "frame" and e.get("handed") and not e.get("malformed")]
    by_tuple: dict[tuple[Any, ...], list[float]] = {}
    for e in sent:
        by_tuple.setdefault(_tuple(e["text"]) or (), []).append(wall(e["t_wall"]))
    send_to_display = []
    for i, seen in seen_wall_ms.items():
        ack = acks.get(i)
        if not ack:
            continue
        candidates = [t for t in by_tuple.get((ack.get("bpm"), ack.get("spo2"), ack.get("ecg")), []) if 0 <= wall(ack["t_wall"]) - t <= 5000]
        if candidates:
            send_to_display.append(seen - max(candidates))
    return {"displayed_ids": len(seen_wall_ms), "atlas_ack_to_browser_display_ms": stats(ack_to_display),
            "emulator_send_to_browser_display_ms": stats(send_to_display),
            "note": "freshness of the NEWEST record on screen at each refresh (the page shows one 'Latest received' id per poll); per-document display delay is this plus up to one 800 ms poll interval for older documents in a batch. 60 ms DOM sampling step."}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def workdir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"{prefix}-"))


__all__ = [
    "LEVELS",
    "PYTHON",
    "REHEARSAL_DATABASE",
    "Emulator",
    "NhmProbe",
    "Replica",
    "browser_latency",
    "correlate",
    "free_port",
    "load_uri",
    "now_iso",
    "stats",
    "workdir",
]
if __name__ == "__main__":  # pragma: no cover
    print("library module", file=sys.stderr)
