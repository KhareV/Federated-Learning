# ruff: noqa: E501
"""Insert bounded, explicitly synthetic telemetry into isolated Atlas test collection.

Usage: NHM_HARDWARE_MONGO_URI=... python3 -m scripts.publish_hardware_test --count 20
"""

from __future__ import annotations

import argparse
import math
import os
import random
import signal
import time
from datetime import UTC, datetime

from pymongo import MongoClient

COLLECTION = "nhm_integration_test"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int)
    parser.add_argument("--duration", type=float, default=0.0, help="seconds; 0 emits until Ctrl+C")
    parser.add_argument("--rate", type=float, default=20.0, help="messages per second")
    parser.add_argument("--batch-size", type=int, default=10, help="documents per Atlas insert_many call")
    parser.add_argument("--interval", type=float, help="legacy alias overriding --rate")
    parser.add_argument("--initial-delay", type=float, default=0.0)
    parser.add_argument("--pause-at", type=float, help="pause once, seconds after emission starts")
    parser.add_argument("--pause-duration", type=float, default=7.0)
    parser.add_argument("--gap-every", type=int, default=0, help="pause after every N records")
    parser.add_argument("--gap-duration", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=20261015)
    parser.add_argument("--invalid-every", type=int, default=0)
    parser.add_argument("--run-tag", default=None)
    parser.add_argument("--cleanup", action="store_true", help="delete only this run tag on exit")
    args = parser.parse_args()
    if args.count is not None and args.count < 1:
        parser.error("count must be positive")
    if args.duration < 0 or args.rate <= 0 or args.initial_delay < 0 or args.batch_size < 1:
        parser.error("duration/delay must be nonnegative and rate positive")
    interval = args.interval if args.interval is not None else 1.0 / args.rate
    if not 0 <= interval <= 5:
        parser.error("interval must be 0..5 seconds")
    uri = os.environ.get("NHM_HARDWARE_MONGO_URI")
    if not uri:
        parser.error("NHM_HARDWARE_MONGO_URI is required")
    run_tag = args.run_tag or f"NHM-SYNTH-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    rng = random.Random(args.seed)
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    collection = client["health_db"][COLLECTION]
    paused = False
    stop = False

    def toggle_pause(*_: object) -> None:
        nonlocal paused
        paused = not paused
        print(f"{run_tag} {'PAUSED' if paused else 'RESUMED'}", flush=True)

    def request_stop(*_: object) -> None:
        nonlocal stop
        stop = True

    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, toggle_pause)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    time.sleep(args.initial_delay)
    started = time.monotonic()
    next_emit = started
    inserted: list[object] = []
    paused_once = False
    i = 0
    print(f"run_tag={run_tag} collection=health_db.{COLLECTION} synthetic=true", flush=True)
    try:
        while not stop:
            elapsed = time.monotonic() - started
            if args.count is not None and i >= args.count:
                break
            if args.duration and elapsed >= args.duration:
                break
            if args.pause_at is not None and not paused_once and elapsed >= args.pause_at:
                paused_once = True
                print(f"{run_tag} TIMED_PAUSE seconds={args.pause_duration}", flush=True)
                time.sleep(args.pause_duration)
                next_emit = time.monotonic()
            was_paused = paused
            while paused and not stop:
                time.sleep(0.1)
            if was_paused:
                next_emit = time.monotonic()
            if stop:
                break
            remaining = args.batch_size if args.count is None else min(args.batch_size, args.count - i)
            batch: list[dict[str, object]] = []
            for offset in range(remaining):
                sequence = i + offset
                phase = 2.0 * math.pi * (sequence % 20) / 20.0
                ecg = int(round(2048 + 420 * math.sin(phase) + 110 * math.sin(3 * phase) + rng.uniform(-18, 18)))
                reading: dict[str, object] = {
                    "bpm": 72 + int(4 * math.sin(sequence / 37.0)),
                    "spo2": 97 + (1 if (sequence // 50) % 2 else 0),
                    "ecg": max(0, min(4095, ecg)),
                    # BSON UTC Date captured immediately before this batch is inserted.
                    "timestamp": datetime.now(UTC),
                    "source": "NHM_SYNTHETIC_INTEGRATION_TEST", "nhmTestRun": run_tag,
                    "synthetic": True, "sequence": sequence,
                }
                if args.invalid_every and (sequence + 1) % args.invalid_every == 0:
                    reading["ecg"] = 9000; reading["invalidTestRecord"] = True
                batch.append(reading)
            result = collection.insert_many(batch, ordered=True)
            inserted.extend(result.inserted_ids)
            for oid, reading in zip(result.inserted_ids, batch, strict=True):
                print(f"{oid} seq={reading['sequence']} ecg={reading['ecg']} bpm={reading['bpm']} spo2={reading['spo2']}", flush=True)
            i += remaining
            if args.gap_every and i % args.gap_every == 0 and args.gap_duration:
                print(f"{run_tag} GAP seconds={args.gap_duration}", flush=True)
                time.sleep(args.gap_duration)
                next_emit = time.monotonic()
            next_emit += interval * remaining
            time.sleep(max(0.0, next_emit - time.monotonic()))
    finally:
        deleted = 0
        if args.cleanup:
            deleted = collection.delete_many({"nhmTestRun": run_tag, "_id": {"$in": inserted}}).deleted_count
        print(f"run_tag={run_tag} inserted={len(inserted)} cleaned={deleted}", flush=True)
        client.close()


if __name__ == "__main__":
    main()
