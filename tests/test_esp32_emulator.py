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


def test_ad8232_amplitude_pattern_stays_inside_the_analysis_rail_and_yields_valid_v2_windows_while_default_is_unchanged():
    """``ecg_ad8232`` is test tooling for the pretrained-V2 recorded-hardware path; the historical ``ecg`` pattern keeps its large amplitude (and its digests)."""
    from datetime import UTC, datetime, timedelta

    from api.hardware_v2_experimental import ADC_MIDPOINT, RUNTIME_COUNTS_PER_ADC, build_windows
    from scripts.emulate_esp32_ws import Signal

    def series(pattern: str, seconds: int = 40):
        signal, out = Signal(5), []
        start = datetime(2026, 10, 15, tzinfo=UTC)
        for i in range(seconds * 20):
            signal.step(0.05)
            out.append({"document_id": f"d{i}", "ingested_at": (start + timedelta(milliseconds=50 * i)).isoformat(), "ecg": signal.ecg(pattern), "bpm": 72, "spo2": 97})
        return out

    small, large = series("ecg_ad8232"), series("ecg")
    assert max(abs(r["ecg"] - ADC_MIDPOINT) for r in small) * RUNTIME_COUNTS_PER_ADC < 2500 < max(abs(r["ecg"] - ADC_MIDPOINT) for r in large) * RUNTIME_COUNTS_PER_ADC
    assert [Signal(5).ecg("ecg") for _ in range(3)] == [Signal(5).ecg("ecg") for _ in range(3)]
    windows, _ = build_windows(small, "HW-EMU", "MODEL_V2_FINAL")
    assert windows and sum(w["ecg_quality"] == "VALID" for w in windows) >= len(windows) - 1
    assert all(w["ecg_quality"] == "UNUSABLE" for w in build_windows(large, "HW-EMU", "MODEL_V2_FINAL")[0])


def test_sketch_vitals_reproduce_the_supplied_firmware_mock_bpm_ratio_spo2_and_finger_removal_and_leave_drift_unchanged():
    from scripts.emulate_esp32_ws import Signal, frame

    signal = Signal(9)
    seen, spo2s, held = [], [], []
    for i in range(600):                                     # 30 s at 20 Hz
        signal.step(0.05)
        bpm, spo2 = signal.vitals("sketch", False)
        seen.append(bpm); spo2s.append(spo2)
        if i % 20 == 19:
            held.append(bpm)
    assert min(seen) >= 72 and max(seen) <= 81 and len(set(seen)) > 1               # MOCK random(72, 82), never a measured pulse
    changes = sum(1 for a, b in zip(seen, seen[1:], strict=False) if a != b)
    assert changes <= 30/2 + 2                                                       # refreshed about every 2 s, constant in between
    assert all(90 <= v <= 100 for v in spo2s[20:]) and max(spo2s) <= 100              # 110 - 25 * red/ir, clipped to 100
    assert signal.vitals("sketch", True) == (0, 0) and signal.vitals("sketch", False)[1] > 80      # finger removed -> zeros, finger back -> valid again
    d = Signal(9)
    d.step(0.05)
    assert 48 <= d.vitals("drift", False)[0] <= 110 and frame(*d.vitals("drift", False), 2048).startswith('{"bpm":')   # the historical behaviour
    hi = Signal(9)
    rails = []
    for _ in range(400):
        hi.step(0.05)
        rails.append(hi.ecg("sketch_highgain"))
    assert min(rails) == 0 or max(rails) == 4095                                     # the high-gain board rails the 12-bit ADC


def test_hyper_realistic_ecg_has_the_modules_offset_wander_motion_bursts_and_stays_in_the_adc_range_deterministically():
    import random

    import numpy as np

    from scripts.emulate_esp32_ws import Signal

    def run(seed: int):
        signal, r, out = Signal(seed), random.Random(seed), []
        for _ in range(2200):                                 # ~2 min of the sketch's irregular ~17 Hz instants
            signal.step(0.052 + r.random() * 0.016)
            out.append(signal.ecg("sketch_real"))
        return np.array(out)

    a, b = run(4), run(4)
    assert (a == b).all() and not (a == run(5)).all()                                   # deterministic per seed
    assert 0 <= a.min() and a.max() <= 4095
    assert 1800 < np.median(a) < 1960                                                   # module output near mid-supply (~1.5 V), not the 2048 midpoint
    assert np.abs(np.diff(a)).max() > 120                                               # R waves / motion bursts are visible in single samples
    assert a.std() > 40 and (np.abs(a - np.median(a)) > 300).sum() > 5                  # baseline wander plus at least one motion burst
