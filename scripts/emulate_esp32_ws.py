"""ESP32 network emulator: speaks to a WebSocket ingestion server exactly like the sketch does.

Wire behaviour copied from the firmware:
* ``webSocket.beginSSL(host, 443, "/")``: TLS WebSocket, path "/", reconnect interval 5000 ms;
* frames are the compact text ``{"bpm":%d,"spo2":%d,"ecg":%d}`` with integers only, no other fields;
* an unavailable BPM / SpO2 is sent as 0 (not null); ECG is 2048 while a lead-off pin is high;
* a frame is attempted only when ``millis() - lastNetworkSend > 50`` is true at a loop iteration, so the
  real period is 50 ms plus the loop's own work (TFT drawing), i.e. NOT exactly 20 Hz. The default
  ``--timing firmware`` reproduces that rule; ``--timing fixed`` uses an absolute monotonic schedule.

It has NO database credentials and writes nothing but WebSocket frames. The optional
``X-NHM-Test-Run`` header only lets a staging/replica server tag documents for cleanup; the
production-compatible payload is unchanged.

Signal values are engineering test patterns. They are not physiological ECG.

Plan DSL (``--plan``), comma separated, executed in order:
  run:S[:pattern]   transmit for S seconds (pattern: ecg|ecg_ad8232|sine|flat|leadoff|rail|steps)
  pause:S           stay connected, transmit nothing (device busy)
  drop:S            abrupt network loss for S seconds (TCP aborted, no close frame; the send loop keeps running, frames are
                    not handed; reconnect only after the network is back AND >= 5 s after the loss was noticed)
  stall:S           network stalls for S seconds but TCP survives: frames are written to the socket buffer and arrive as one
                    delayed burst when the path recovers (server-side timestamps then compress them)
  disconnect:S      clean close, reconnect after S seconds
  unavail:S         transmit with BPM=0 and SpO2=0 (no finger on the MAX30102)
  burst:S           transmit in 150 ms bursts of 3 frames
  malformed:N       send N malformed text frames
  kill              terminate the process abruptly (os._exit)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import ssl
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from websockets.asyncio.client import connect

RECONNECT_INTERVAL_S = 5.0  # webSocket.setReconnectInterval(5000)
SEND_THRESHOLD_MS = 50  # millis() - lastNetworkSend > 50


class Recorder:
    def __init__(self, path: Path | None) -> None:
        self.handle = path.open("w", buffering=1) if path else None
        self.counters = {"connect_attempts": 0, "connects": 0, "disconnects": 0, "reconnects": 0, "frames_attempted": 0,
                         "frames_handed": 0, "frames_not_handed": 0, "transport_errors": 0, "malformed_sent": 0}
        self.intervals_ms: list[float] = []
        self.last_handed: float | None = None

    def event(self, kind: str, **fields: Any) -> None:
        if self.handle:
            self.handle.write(json.dumps({"t_wall": datetime.now(UTC).isoformat(), "t_mono": time.monotonic(), "event": kind, **fields}) + "\n")


class Signal:
    """Seeded test patterns in ADC counts (0..4095), BPM and SpO2 estimates."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.t = 0.0
        self.bpm = 72.0
        self.spo2 = 97.0

    def step(self, dt: float) -> None:
        self.t += dt
        self.bpm = min(110.0, max(48.0, self.bpm + self.rng.uniform(-0.15, 0.15)))
        self.spo2 = min(100.0, max(90.0, self.spo2 + self.rng.uniform(-0.05, 0.05)))

    def ecg(self, pattern: str) -> int:
        if pattern == "leadoff":
            return 2048  # firmware placeholder while LO+ / LO- is high
        if pattern == "flat":
            return 2100
        if pattern == "rail":
            return 4095 if int(self.t * 4) % 2 == 0 else 0
        if pattern == "steps":
            return 1000 + 800 * (int(self.t) % 4) + self.rng.randint(-3, 3)
        if pattern == "sine":
            return int(2048 + 600 * math.sin(2 * math.pi * self.t * (self.bpm / 60.0)))
        phase = (self.t * self.bpm / 60.0) % 1.0  # ecg-like: baseline wander, QRS spike, T wave, noise
        # "ecg_ad8232": the same shape at an amplitude an AD8232 front end plausibly produces (R wave ~ +200 counts), which stays inside the
        # analysis runtime's +/-2.5 mV rail under the documented scaling; the default "ecg" keeps its large historical amplitude (it exceeds that rail).
        scale = 0.3 if pattern == "ecg_ad8232" else 1.0
        value = 2048 + 40 * scale * math.sin(2 * math.pi * 0.25 * self.t)
        value += scale * (700 * math.exp(-((phase - 0.30) ** 2) / (2 * 0.012**2)) - 180 * math.exp(-((phase - 0.27) ** 2) / (2 * 0.01**2)))
        value += scale * 160 * math.exp(-((phase - 0.55) ** 2) / (2 * 0.05**2)) + self.rng.gauss(0, 9 * scale)
        return max(0, min(4095, int(value)))


def frame(bpm: int, spo2: int, ecg: int) -> str:
    return '{"bpm":%d,"spo2":%d,"ecg":%d}' % (bpm, spo2, ecg)  # byte-identical to the snprintf in the sketch


def parse_plan(text: str) -> list[tuple[str, float, str]]:
    steps: list[tuple[str, float, str]] = []
    for item in filter(None, (x.strip() for x in text.split(","))):
        parts = item.split(":")
        kind = parts[0]
        if kind not in {"run", "pause", "drop", "stall", "disconnect", "unavail", "burst", "malformed", "kill"}:
            raise SystemExit(f"unknown plan step {item!r}")
        amount = float(parts[1]) if len(parts) > 1 else 0.0
        steps.append((kind, amount, parts[2] if len(parts) > 2 else "ecg"))
    return steps


def legacy_plan(args: argparse.Namespace) -> list[tuple[str, float, str]]:
    """Translate the flags of scripts.publish_hardware_test so the browser driver can use either producer."""
    plan: list[tuple[str, float, str]] = []
    if args.initial_delay:
        plan.append(("pause", args.initial_delay, "ecg"))
    seconds = args.duration or ((args.count / args.rate) if args.count else 0.0)
    if args.pause_at is not None and seconds:
        plan += [("run", args.pause_at, args.pattern), ("pause", args.pause_duration, args.pattern)]
        seconds = max(0.0, seconds - args.pause_at)
    plan.append(("run", seconds or 10**9, args.pattern))
    return plan


class Emulator:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.rec = Recorder(Path(args.event_log) if args.event_log else None)
        self.signal = Signal(args.seed)
        self.rng = random.Random(args.seed + 1)
        self.ws: Any = None
        self.reconnect_not_before = 0.0
        self.last_attempt = 0.0
        self.loop_count = 0
        self.last_send = time.monotonic()
        self.had_connection = False
        self.hold: list[str] | None = None

    def ssl_context(self) -> ssl.SSLContext | None:
        if not self.args.url.startswith("wss://"):
            return None
        if self.args.insecure:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return ssl.create_default_context(cafile=self.args.cafile)

    async def ensure_connection(self, force: bool = False) -> None:
        """setReconnectInterval(5000): one attempt per 5 s while disconnected."""
        if self.ws is not None and getattr(self.ws, "state", None) is not None and self.ws.state.name == "OPEN":
            return
        now = time.monotonic()
        if self.ws is not None:
            self.rec.counters["disconnects"] += 1
            self.rec.event("disconnect", reason="CONNECTION_LOST")
            self.ws = None
        if now < self.reconnect_not_before or (not force and self.last_attempt and now - self.last_attempt < RECONNECT_INTERVAL_S):
            return
        self.last_attempt = now
        self.rec.counters["connect_attempts"] += 1
        headers = {"X-NHM-Test-Run": self.args.run_tag} if self.args.run_tag else {}
        try:
            self.ws = await asyncio.wait_for(connect(self.args.url, ssl=self.ssl_context(), additional_headers=headers,
                                                     ping_interval=None, open_timeout=self.args.connect_timeout, max_size=None), self.args.connect_timeout + 1)
        except Exception as error:
            self.rec.counters["transport_errors"] += 1
            self.rec.event("connect_failed", error=type(error).__name__, detail=str(error)[:160])
            self.ws = None
            return
        self.rec.counters["connects"] += 1
        if self.had_connection:
            self.rec.counters["reconnects"] += 1
        self.had_connection = True
        self.rec.event("connected", url=self.args.url)

    async def send_text(self, text: str, *, malformed: bool = False) -> bool:
        self.rec.counters["frames_attempted"] += 1
        now = time.monotonic()
        handed = False
        if self.hold is not None and self.ws is not None:
            self.hold.append(text)  # written to the local socket buffer; delivery is delayed by the stalled path
            self.rec.event("frame", handed=True, malformed=malformed, buffered=True, text=text[:80], send_mono=now)
            self.rec.counters["frames_handed"] += 1
            return True
        if self.ws is not None and self.ws.state.name == "OPEN":
            try:
                await self.ws.send(text)
                handed = True
            except Exception as error:
                self.rec.counters["transport_errors"] += 1
                self.rec.event("send_error", error=type(error).__name__)
        key = "frames_handed" if handed else "frames_not_handed"
        self.rec.counters[key] += 1
        if handed and not malformed:
            if self.rec.last_handed is not None:
                self.rec.intervals_ms.append((now - self.rec.last_handed) * 1000)
            self.rec.last_handed = now
        if malformed and handed:
            self.rec.counters["malformed_sent"] += 1
        self.rec.event("frame", handed=handed, malformed=malformed, text=text if len(text) < 80 else text[:80], send_mono=now)
        return handed

    def loop_work_seconds(self) -> float:
        """Duration of one sketch loop iteration (sensor reads + TFT drawing), a model, not a measurement."""
        self.loop_count += 1
        work = self.rng.uniform(0.0015, 0.0045)  # analogRead + MAX30102 I2C + drawLine
        if self.loop_count % 5 == 0:
            work += self.rng.uniform(0.010, 0.016)  # tft.printf text refresh
        if self.loop_count % 160 == 0:
            work += self.rng.uniform(0.025, 0.040)  # tft.fillScreen
        return work

    async def transmit_for(self, seconds: float, pattern: str, *, unavailable: bool = False, burst: bool = False) -> None:
        end = time.monotonic() + seconds
        next_fixed = time.monotonic()
        interval = 1.0 / self.args.rate
        while time.monotonic() < end:
            await self.ensure_connection()
            now = time.monotonic()
            if self.args.timing == "firmware":
                # Accumulate whole sketch loop iterations until `millis() - lastNetworkSend > 50` holds, then sleep once.
                period = 0.0
                while period * 1000 <= SEND_THRESHOLD_MS:
                    period += self.loop_work_seconds()
                await asyncio.sleep(max(0.0, self.last_send + period - time.monotonic()))
                due = True
            else:
                if burst:
                    due = False
                else:
                    due = time.monotonic() >= next_fixed
                    if not due:
                        await asyncio.sleep(max(0.0, min(0.005, next_fixed - time.monotonic())))
            if burst and self.args.timing != "firmware":
                for _ in range(3):
                    await self.emit(pattern, unavailable)
                await asyncio.sleep(0.15)
                continue
            if not due:
                continue
            jitter = self.rng.uniform(-self.args.jitter_ms, self.args.jitter_ms) / 1000.0 if self.args.timing == "fixed" else 0.0
            next_fixed = max(next_fixed + interval + jitter, time.monotonic() - interval)
            self.last_send = time.monotonic()
            if burst:
                for _ in range(3):
                    await self.emit(pattern, unavailable)
            else:
                await self.emit(pattern, unavailable)
            self.signal.step(max(0.001, time.monotonic() - now))

    async def emit(self, pattern: str, unavailable: bool) -> None:
        bpm = 0 if unavailable else int(round(self.signal.bpm))
        spo2 = 0 if unavailable else int(round(self.signal.spo2))
        await self.send_text(frame(bpm, spo2, self.signal.ecg(pattern)))

    async def execute(self, plan: list[tuple[str, float, str]]) -> None:
        await self.ensure_connection(force=True)
        for kind, amount, pattern in plan:
            self.rec.event("plan_step", step=kind, amount=amount, pattern=pattern)
            if kind == "run":
                await self.transmit_for(amount, pattern)
            elif kind == "unavail":
                await self.transmit_for(amount, "ecg", unavailable=True)
            elif kind == "burst":
                await self.transmit_for(amount, pattern, burst=True)
            elif kind == "pause":
                end = time.monotonic() + amount
                while time.monotonic() < end:
                    await self.ensure_connection()
                    await asyncio.sleep(0.1)
            elif kind == "drop":
                if self.ws is not None:
                    self.ws.transport.abort()  # TCP reset, no WebSocket close handshake
                    self.rec.event("network_drop", seconds=amount)
                    self.rec.counters["disconnects"] += 1
                    self.ws = None
                self.last_attempt = time.monotonic()  # _lastConnectionFail: next attempt not before +5 s
                self.reconnect_not_before = time.monotonic() + amount
                await self.transmit_for(amount, pattern)  # loop keeps running; frames are not handed
            elif kind == "stall":
                self.hold = []
                self.rec.event("network_stall", seconds=amount)
                await self.transmit_for(amount, pattern)
                backlog, self.hold = self.hold, None
                self.rec.event("stall_release", frames=len(backlog))
                for text in backlog:
                    try:
                        await self.ws.send(text)
                    except Exception as error:
                        self.rec.counters["transport_errors"] += 1
                        self.rec.event("send_error", error=type(error).__name__)
                        break
            elif kind == "disconnect":
                if self.ws is not None:
                    await self.ws.close()
                    self.rec.counters["disconnects"] += 1
                    self.ws = None
                await asyncio.sleep(amount)
                await self.ensure_connection(force=True)
            elif kind == "malformed":
                bad = ['{"bpm":76,"spo2":97,"ecg":', "not json", '{"bpm":"x","spo2":97}', '[1,2,3]', '{"ecg":99999,"bpm":-5,"spo2":400}', '{"bpm":-5,"spo2":400,"ecg":3777}']
                for i in range(int(amount)):
                    await self.send_text(bad[i % len(bad)], malformed=True)
                    await asyncio.sleep(0.05)
            elif kind == "kill":
                self.rec.event("killed")
                self.finish(final=False)
                os._exit(137)
        if self.ws is not None:
            await self.ws.close()

    def finish(self, final: bool = True) -> dict[str, Any]:
        all_iv = sorted(self.rec.intervals_ms)
        iv = [x for x in all_iv if x <= 1000.0]  # steady-state period; outages/stalls are reported as gaps instead
        gaps = [round(x, 1) for x in all_iv if x > 1000.0]

        def pct(p: float) -> float | None:
            return round(iv[min(len(iv) - 1, int(p * len(iv)))], 2) if iv else None

        summary = {"status": "EMULATOR_DONE" if final else "EMULATOR_KILLED", "target": urlparse(self.args.url)._replace(query="").geturl(),
                   "run_tag": self.args.run_tag, "timing": self.args.timing, "seed": self.args.seed, **self.rec.counters,
                   "interval_ms": {"n": len(iv), "p50": pct(0.5), "p95": pct(0.95), "max": round(iv[-1], 2) if iv else None,
                                   "mean": round(sum(iv) / len(iv), 2) if iv else None},
                   "effective_hz": round(1000 / (sum(iv) / len(iv)), 2) if iv else None,
                   "gaps_over_1s_ms": gaps[:20], "gap_count": len(gaps),
                   "note": "frames_handed means the WebSocket transport accepted the frame; it is not proof MongoDB stored a document"}
        self.rec.event("summary", **summary)
        if self.args.summary_file:
            Path(self.args.summary_file).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary), flush=True)
        return summary


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=os.environ.get("NHM_EMULATOR_URL", "ws://127.0.0.1:8765/"))
    p.add_argument("--cafile", help="CA/self-signed certificate to trust for wss://")
    p.add_argument("--insecure", action="store_true", help="skip certificate verification (replica self-signed only)")
    p.add_argument("--timing", choices=["firmware", "fixed"], default="firmware")
    p.add_argument("--rate", type=float, default=20.0, help="nominal Hz for --timing fixed (and for translating --count)")
    p.add_argument("--jitter-ms", type=float, default=4.0)
    p.add_argument("--seed", type=int, default=20261015)
    p.add_argument("--pattern", default="ecg", choices=["ecg", "ecg_ad8232", "sine", "flat", "leadoff", "rail", "steps"])
    p.add_argument("--plan", help="step DSL, see module docstring")
    # flags compatible with scripts.publish_hardware_test
    p.add_argument("--count", type=int)
    p.add_argument("--duration", type=float, default=0.0)
    p.add_argument("--initial-delay", type=float, default=0.0)
    p.add_argument("--pause-at", type=float)
    p.add_argument("--pause-duration", type=float, default=7.0)
    p.add_argument("--run-tag")
    p.add_argument("--cleanup", action="store_true", help="accepted for compatibility; the emulator has no database access")
    p.add_argument("--connect-timeout", type=float, default=8.0)
    p.add_argument("--event-log")
    p.add_argument("--summary-file")
    return p


async def amain(args: argparse.Namespace) -> int:
    emulator = Emulator(args)
    plan = parse_plan(args.plan) if args.plan else legacy_plan(args)
    try:
        await emulator.execute(plan)
    except asyncio.CancelledError:
        pass
    emulator.finish()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(amain(parser().parse_args())))
    except KeyboardInterrupt:
        sys.exit(0)
