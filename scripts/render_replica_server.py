"""LOCAL RENDER REPLICA: a WebSocket ingestion server shaped like the one the ESP32 talks to.

THIS IS NOT THE REAL RENDER SERVICE. The real server's source was not available. This replica is
built only from facts that were observed: the ESP32 sketch (secure WebSocket, port 443, path "/",
JSON text frames {"bpm":..,"spo2":..,"ecg":..}) and the Atlas schema (daily collections
``records_YYYY-MM-DD`` holding numeric bpm/spo2/ecg, a BSON UTC Date ``timestamp`` and an ObjectId).
Anything beyond that (validation, batching, idle timeouts, timezone of the daily name) is an
ASSUMPTION exposed as a flag. Evidence produced with it is LOCAL_RENDER_REPLICA, never
"deployed Render verified".

Safety:
* it refuses to write to the production database ``health_db`` (no override flag exists);
* it writes only to a rehearsal database on the same cluster, in daily collections
  ``<prefix><YYYY-MM-DD>``, and tags every document it stores with the run tag it was given;
* the Mongo URI is read from the environment and never printed or logged.

Fault switches (flag files, so the rehearsal runner can toggle them without a control channel):
``--fail-inserts-file``   while the file exists every insert fails (simulated Atlas outage);
``--reject-file``         while the file exists new WebSocket handshakes get HTTP 503.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import ssl
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import MongoClient
from websockets.asyncio.server import serve
from websockets.http11 import Response

PRODUCTION_DATABASE = "health_db"


class Clock:
    """Wall clock with an optional simulated start (to cross midnight in seconds)."""

    def __init__(self, simulated_start: str | None) -> None:
        self.mono0 = time.monotonic()
        self.base = datetime.fromisoformat(simulated_start.replace("Z", "+00:00")) if simulated_start else None
        self.real0 = datetime.now(UTC)

    def now(self) -> datetime:
        if self.base is None:
            return datetime.now(UTC)
        return self.base + timedelta(seconds=time.monotonic() - self.mono0)


class EventLog:
    def __init__(self, path: Path | None) -> None:
        self.handle = path.open("a", buffering=1) if path else None

    def write(self, event: str, **fields: Any) -> None:
        if self.handle:
            self.handle.write(json.dumps({"t_wall": datetime.now(UTC).isoformat(), "t_mono": time.monotonic(), "event": event, **fields}, default=str) + "\n")


class Replica:
    def __init__(self, args: argparse.Namespace, collection_provider: Any) -> None:
        self.args = args
        self.clock = Clock(args.simulated_start)
        self.log = EventLog(Path(args.event_log) if args.event_log else None)
        self.tz = ZoneInfo(args.collection_timezone)
        self.collection_provider = collection_provider
        self.stats = {"connections": 0, "rejected": 0, "frames": 0, "malformed": 0, "inserted": 0, "insert_errors": 0, "disconnects": 0}
        self.inflight = asyncio.Semaphore(args.insert_concurrency)
        self.conn_seq = 0

    def collection_name(self, stamp: datetime) -> str:
        return f"{self.args.collection_prefix}{stamp.astimezone(self.tz).date().isoformat()}"

    def process_request(self, connection: Any, request: Any):
        path = request.path.split("?")[0]
        if path == "/healthz":
            body = json.dumps({"replica": True, "not_real_render": True, **self.stats}).encode()
            return Response(200, "OK", __import__("websockets").Headers([("Content-Type", "application/json")]), body)
        if self.args.reject_file and Path(self.args.reject_file).exists():
            self.stats["rejected"] += 1
            self.log.write("handshake_rejected", path=path)
            return Response(503, "Service Unavailable", __import__("websockets").Headers(), b"unavailable\n")
        if path != "/":
            self.log.write("path_not_root", path=path)
        return None

    async def store(self, doc: dict[str, Any], received_mono: float, conn: int) -> None:
        async with self.inflight:
            if self.args.fail_inserts_file and Path(self.args.fail_inserts_file).exists():
                self.stats["insert_errors"] += 1
                self.log.write("insert_error", conn=conn, reason="SIMULATED_ATLAS_OUTAGE", ecg=doc.get("ecg"))
                return
            name = self.collection_name(doc["timestamp"])
            try:
                await asyncio.to_thread(self.collection_provider(name).insert_one, doc)
            except Exception as error:
                self.stats["insert_errors"] += 1
                self.log.write("insert_error", conn=conn, reason=type(error).__name__)
                return
            self.stats["inserted"] += 1
            self.log.write("insert_ok", conn=conn, id=str(doc["_id"]), collection=name, ecg=doc.get("ecg"), bpm=doc.get("bpm"),
                           spo2=doc.get("spo2"), stored_timestamp=doc["timestamp"], received_mono=received_mono,
                           insert_ack_mono=time.monotonic(), insert_ms=round((time.monotonic() - received_mono) * 1000, 2))

    async def handler(self, websocket: Any) -> None:
        self.conn_seq += 1
        conn = self.conn_seq
        self.stats["connections"] += 1
        run_tag = websocket.request.headers.get("X-NHM-Test-Run")
        self.log.write("connect", conn=conn, path=websocket.request.path, run_tag=run_tag, remote=str(websocket.remote_address))
        pending: set[asyncio.Task[None]] = set()
        try:
            async for message in websocket:
                received_mono = time.monotonic()
                self.stats["frames"] += 1
                if isinstance(message, bytes):
                    self.stats["malformed"] += 1
                    self.log.write("malformed", conn=conn, reason="BINARY_FRAME")
                    continue
                try:
                    payload = json.loads(message)
                    if not isinstance(payload, dict):
                        raise ValueError("not an object")
                except ValueError:
                    self.stats["malformed"] += 1
                    self.log.write("malformed", conn=conn, reason="JSON", bytes=len(message))
                    continue
                # ASSUMPTION (unverified): the real server stores the three fields as received, plus a server timestamp.
                doc: dict[str, Any] = {k: payload[k] for k in ("bpm", "spo2", "ecg") if k in payload}
                doc["timestamp"] = self.clock.now()
                if run_tag:
                    doc["nhmTestRun"] = run_tag
                doc["_id"] = ObjectId()  # client-side id, like a Mongo driver
                self.log.write("frame", conn=conn, received_mono=received_mono, ecg=doc.get("ecg"), bpm=doc.get("bpm"), spo2=doc.get("spo2"), bytes=len(message))
                task = asyncio.create_task(self.store(doc, received_mono, conn))
                pending.add(task)
                task.add_done_callback(pending.discard)
        except Exception as error:
            self.log.write("connection_error", conn=conn, reason=type(error).__name__)
        finally:
            self.stats["disconnects"] += 1
            self.log.write("disconnect", conn=conn)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)


def self_signed(directory: Path) -> tuple[Path, Path]:
    cert, key = directory / "replica.crt", directory / "replica.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "2",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
    return cert, key


async def amain(args: argparse.Namespace) -> int:
    if args.database == PRODUCTION_DATABASE:
        print("REFUSING: the replica never writes to the production database health_db", file=sys.stderr)
        return 2
    sink = None
    if args.sink == "mongo":
        uri = os.environ.get("NHM_HARDWARE_MONGO_URI")
        if not uri:
            print("NHM_HARDWARE_MONGO_URI is required for --sink mongo", file=sys.stderr)
            return 2
        client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True, maxPoolSize=max(4, args.insert_concurrency))
        db = client[args.database]
        collection_provider = lambda name: db[name]  # noqa: E731
    else:
        sink = open(args.sink_file, "a", buffering=1)  # noqa: SIM115

        class _File:
            def __init__(self, name: str) -> None:
                self.name = name

            def insert_one(self, doc: dict[str, Any]) -> None:
                sink.write(json.dumps({**doc, "_collection": self.name}, default=str) + "\n")  # type: ignore[union-attr]

        collection_provider = _File
    replica = Replica(args, collection_provider)
    ssl_context = None
    if args.tls:
        cert = Path(args.tls_cert) if args.tls_cert else None
        key = Path(args.tls_key) if args.tls_key else None
        if cert is None:
            cert, key = self_signed(Path(tempfile.mkdtemp(prefix="nhm-replica-tls-")))
            print(f"TLS_CERT={cert}", flush=True)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(str(cert), str(key))
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    async with serve(replica.handler, args.host, args.port, ssl=ssl_context, process_request=replica.process_request,
                     ping_interval=args.ping_interval or None, max_size=args.max_frame_bytes):
        scheme = "wss" if ssl_context else "ws"
        print(json.dumps({"status": "REPLICA_READY", "not_real_render": True, "url": f"{scheme}://{args.host}:{args.port}/",
                          "database": args.database, "collection_prefix": args.collection_prefix, "collection_timezone": args.collection_timezone,
                          "sink": args.sink, "simulated_start": args.simulated_start}), flush=True)
        await stop.wait()
    replica.log.write("shutdown", **replica.stats)
    print(json.dumps({"status": "REPLICA_STOPPED", **replica.stats}), flush=True)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--database", default="nhm_rehearsal", help="rehearsal database (never health_db)")
    p.add_argument("--collection-prefix", default="records_")
    p.add_argument("--collection-timezone", default="UTC", help="ASSUMPTION: timezone of the daily collection name")
    p.add_argument("--simulated-start", help="ISO instant for the replica clock (e.g. 2026-10-15T23:59:50Z) to cross midnight quickly")
    p.add_argument("--sink", choices=["mongo", "file"], default="mongo")
    p.add_argument("--sink-file", default="replica_sink.jsonl")
    p.add_argument("--insert-concurrency", type=int, default=4, help="in-flight inserts (Node-style unawaited insertOne)")
    p.add_argument("--tls", action="store_true", help="serve wss:// (self-signed unless --tls-cert/--tls-key)")
    p.add_argument("--tls-cert")
    p.add_argument("--tls-key")
    p.add_argument("--ping-interval", type=float, default=0.0)
    p.add_argument("--max-frame-bytes", type=int, default=4096)
    p.add_argument("--event-log")
    p.add_argument("--fail-inserts-file")
    p.add_argument("--reject-file")
    return p


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain(parser().parse_args())))
