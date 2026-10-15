"""ESP32 WebSocket emulator and local replica: wire format, fault behaviour, isolation. Offline (file sink)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}"}
ENV.pop("NHM_HARDWARE_MONGO_URI", None)


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_frame_is_byte_identical_to_the_sketch_and_has_exactly_three_integer_fields():
    from scripts.emulate_esp32_ws import frame

    assert frame(76, 97, 2134) == '{"bpm":76,"spo2":97,"ecg":2134}'
    assert list(json.loads(frame(0, 0, 2048))) == ["bpm", "spo2", "ecg"]


def test_plan_parser_rejects_unknown_steps_and_translates_publisher_flags():
    from scripts.emulate_esp32_ws import legacy_plan, parse_plan, parser

    assert parse_plan("run:5,drop:2,stall:1,malformed:3") == [("run", 5.0, "ecg"), ("drop", 2.0, "ecg"), ("stall", 1.0, "ecg"), ("malformed", 3.0, "ecg")]
    with pytest.raises(SystemExit):
        parse_plan("explode:1")
    args = parser().parse_args(["--count", "1200", "--rate", "20", "--initial-delay", "10", "--pause-at", "25", "--pause-duration", "7"])
    assert legacy_plan(args) == [("pause", 10.0, "ecg"), ("run", 25.0, "ecg"), ("pause", 7.0, "ecg"), ("run", 35.0, "ecg")]


def test_replica_refuses_the_production_database():
    r = subprocess.run([sys.executable, "-m", "scripts.render_replica_server", "--database", "health_db", "--port", str(free_port())],
                       cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=30)
    assert r.returncode == 2 and "never writes to the production database" in r.stderr


def test_end_to_end_local_chain_with_drop_reconnect_and_malformed_frames(tmp_path):
    port = free_port()
    sink = tmp_path / "sink.jsonl"
    replica = subprocess.Popen([sys.executable, "-m", "scripts.render_replica_server", "--port", str(port), "--sink", "file", "--sink-file", str(sink),
                                "--event-log", str(tmp_path / "replica.jsonl"), "--collection-timezone", "UTC"], cwd=ROOT, env=ENV,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        assert "REPLICA_READY" in replica.stdout.readline()
        summary_path = tmp_path / "summary.json"
        done = subprocess.run([sys.executable, "-m", "scripts.emulate_esp32_ws", "--url", f"ws://127.0.0.1:{port}/", "--plan",
                               "run:3,drop:1,run:7,malformed:2", "--run-tag", "UNIT-1", "--seed", "7", "--summary-file", str(summary_path),
                               "--event-log", str(tmp_path / "emulator.jsonl")], cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr
        summary = json.loads(summary_path.read_text())
        assert summary["reconnects"] >= 1 and summary["frames_not_handed"] > 0 and summary["malformed_sent"] == 2
        assert summary["frames_handed"] - summary["malformed_sent"] > 100
        assert 12 <= summary["effective_hz"] <= 20.5, "firmware timing is >50 ms per frame, so strictly below 20 Hz"
        time.sleep(0.5)
        rows = [json.loads(x) for x in sink.read_text().splitlines()]
        valid = [r for r in rows if isinstance(r.get("ecg"), int)]
        assert len(valid) == summary["frames_handed"] - 2
        assert {r["nhmTestRun"] for r in rows} == {"UNIT-1"}
        assert all(set(r) >= {"bpm", "spo2", "ecg", "timestamp"} for r in valid)
        assert all(0 <= r["ecg"] <= 4095 for r in valid)
        assert len({r["_id"] for r in rows}) == len(rows)
    finally:
        replica.terminate()
        replica.wait(timeout=10)


def test_emulator_never_needs_database_credentials(tmp_path):
    source = (ROOT / "scripts/emulate_esp32_ws.py").read_text()
    assert "pymongo" not in source and "MONGO" not in source.upper().replace("MONGODB", "")
