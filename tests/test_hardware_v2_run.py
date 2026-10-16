"""Pretrained MODEL_V2_FINAL fine-tuned by federated rounds on RECORDED-HARDWARE windows (studio.hardware_v2)."""

from __future__ import annotations

import asyncio
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from capstone_persistence.store import CapstoneSqliteStore  # noqa: E402
from studio import hardware_v2  # noqa: E402
from studio.hardware_bundle import build_hardware_bundle  # noqa: E402
from studio.hardware_demo import HardwareDemoService  # noqa: E402
from studio.hardware_runs import HardwareRunJobs  # noqa: E402
from studio.specs import build_specs  # noqa: E402
from studio.tables import build_tables  # noqa: E402


def _ecg(t: float, bpm: float = 72.0, amplitude: float = 120.0, noise: float = 0.0, rng: np.random.Generator | None = None) -> int:
    """ECG-like ADC counts that stay inside the runtime's +/-2.5 mV rail under the documented scaling (R wave ~ +-1000 runtime counts)."""
    phase = (t * bpm / 60.0) % 1.0
    v = 2048 + 0.1 * amplitude * math.sin(2 * math.pi * 0.25 * t)
    v += amplitude * math.exp(-((phase - 0.30) ** 2) / (2 * 0.012**2)) - 0.25 * amplitude * math.exp(-((phase - 0.27) ** 2) / (2 * 0.01**2))
    v += 0.22 * amplitude * math.exp(-((phase - 0.55) ** 2) / (2 * 0.05**2))
    if rng is not None and noise:
        v += rng.normal(0, noise)
    return int(round(v))


def store_with_sessions(tmp_path: Path, *, owner: str = "user-a", seconds: int = 100, amplitude: float = 120.0, sessions: tuple[str, ...] = ("HW-V2-A",)):
    store = CapstoneSqliteStore(tmp_path / "product.sqlite3")
    with store._lock, store._connection:
        store._connection.execute("""CREATE TABLE hardware_sessions (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, collection TEXT NOT NULL,
            started_at TEXT NOT NULL, stopped_at TEXT, status TEXT NOT NULL,
            mark TEXT, last_received_at TEXT, record_count INTEGER NOT NULL DEFAULT 0)""")
        store._connection.execute("""CREATE TABLE hardware_trace (
            session_id TEXT NOT NULL, ordinal INTEGER NOT NULL, document_id TEXT NOT NULL,
            ingested_at TEXT NOT NULL, ecg INTEGER NOT NULL, bpm INTEGER, spo2 INTEGER,
            collection TEXT, PRIMARY KEY(session_id, document_id))""")
        for index, sid in enumerate(sessions):
            rng = np.random.default_rng(100 + index)
            start = datetime(2026, 10, 15, 8 + index, tzinfo=UTC)
            count = seconds * 20
            store._connection.execute("INSERT INTO hardware_sessions VALUES (?,?,?,?,?,?,?,?,?)",
                                      (sid, owner, "nhm_integration_test", start.isoformat(), (start + timedelta(seconds=seconds)).isoformat(), "STOPPED", None, None, count))
            for i in range(count):
                stamp = start + timedelta(milliseconds=50 * i)
                store._connection.execute("INSERT INTO hardware_trace VALUES (?,?,?,?,?,?,?,?)",
                                          (sid, i + 1, f"{sid}-doc-{i:05d}", stamp.isoformat(), _ecg(i / 20.0, noise=3.0, amplitude=amplitude, rng=rng), 70 + i % 7, 96 + i % 3, "nhm_integration_test"))
    return store, HardwareDemoService(store, tmp_path / "runs")


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v2hw")
    store, demo = store_with_sessions(tmp, sessions=("HW-V2-A", "HW-V2-B"))     # NHM keeps ~100 s (2000 readings) per session, so a V2 run combines several
    ctx = demo.prepare("user-a", session_ids=["HW-V2-A", "HW-V2-B"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="MODEL_V2_FINAL")
    return tmp, store, demo, ctx


def test_ecg_like_recording_yields_valid_v2_windows_and_a_time_purged_split(prepared):
    _, _, _, ctx = prepared
    d = ctx["dataset"]
    assert d["training_windows"] >= hardware_v2.MIN_TRAIN_WINDOWS and d["holdout_windows"] >= hardware_v2.MIN_HOLDOUT_WINDOWS
    # ONE recorded client + the seven canonical synthetic peers, unchanged
    assert [x.client_id for x in ctx["datasets"]] == ["RECORDED_DEMO_CLIENT_00", *[f"SIM_FL_SITE_{i:02d}" for i in range(1, 8)]] == ctx["client_ids"]
    from federated.wearable_fl_runner_v1 import build_cohort

    canonical = build_cohort()[1]
    assert [x.dataset_sha256 for x in ctx["datasets"][1:]] == [c.dataset_sha256 for c in canonical[1:]]
    assert ctx["datasets"][0].counts["trainable"] == d["training_windows"] <= hardware_v2.MAX_CLIENT_WINDOWS == 93
    assert ctx["initialisation"] == "MODEL_V2_FINAL" and ctx["engine"] == "HARDWARE_V2"
    assert d["label_assignment"]["status"] == "SYNTHETIC_ASSIGNED_FOR_DEMO" and d["topology"] == "ONE_RECORDED_CLIENT_PLUS_SEVEN_SYNTHETIC_PEERS"
    assert {k: v["kind"] for k, v in d["clients"].items()} == {"RECORDED_DEMO_CLIENT_00": "RECORDED", **{f"SIM_FL_SITE_{i:02d}": "SYNTHETIC_PEER" for i in range(1, 8)}}
    # no training window overlaps a holdout window of the same session (10 s windows, right-edge timestamps)
    by_id = {w["window_id"]: w for w in d["window_manifest"]}
    for session in ("HW-V2-A", "HW-V2-B"):
        hold = [w["timestamp_us"] for w in by_id.values() if w["session_id"] == session and w["split"] == "HOLDOUT"]
        train = [w["timestamp_us"] for w in by_id.values() if w["session_id"] == session and w["split"] == "TRAIN"]
        assert hold and train and max(train) <= min(hold) - hardware_v2.WINDOW_US
    # every training window belongs to the recorded client
    assert {w["client_id"] for w in by_id.values() if w["split"] == "TRAIN"} == {"RECORDED_DEMO_CLIENT_00"}


def test_preparation_is_deterministic_for_the_same_seed(prepared):
    tmp, _, demo, ctx = prepared
    again = demo.prepare("user-a", session_ids=["HW-V2-A", "HW-V2-B"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="MODEL_V2_FINAL")
    assert again["dataset"]["label_sha256"] == ctx["dataset"]["label_sha256"] and again["dataset"]["input_feature_sha256"] == ctx["dataset"]["input_feature_sha256"]
    assert [d.dataset_sha256 for d in again["datasets"]] == [d.dataset_sha256 for d in ctx["datasets"]]
    other = demo.prepare("user-a", session_ids=["HW-V2-A", "HW-V2-B"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=8, initialisation="MODEL_V2_FINAL")
    assert other["dataset"]["label_sha256"] != ctx["dataset"]["label_sha256"]


def test_one_retention_capped_session_is_not_enough_and_the_reason_says_to_combine_sessions(tmp_path):
    _, demo = store_with_sessions(tmp_path, sessions=("HW-V2-A",))
    info = hardware_v2.preview(demo._records("user-a", ["HW-V2-A"]), ["HW-V2-A"])
    assert info["eligible"] is False and info["sessions"][0]["readings"] == 2000 and "two or more recorded sessions" in info["reason"]
    with pytest.raises(ValueError, match="two or more recorded sessions"):
        demo.prepare("user-a", session_ids=["HW-V2-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1, initialisation="MODEL_V2_FINAL")


def test_too_clean_a_gate_fails_closed_with_the_reason(tmp_path):
    """A signal the unchanged PREPROC_V1 gate grades CLIPPING (amplitude beyond the runtime rail) leaves nothing to train on: the run is refused, with counts, never faked."""
    _, demo = store_with_sessions(tmp_path, amplitude=700.0)
    with pytest.raises(ValueError, match=r"INSUFFICIENT_V2_WINDOWS.*CLIPPING"):
        demo.prepare("user-a", session_ids=["HW-V2-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1, initialisation="MODEL_V2_FINAL")
    info = hardware_v2.preview(demo._records("user-a", ["HW-V2-A"]), ["HW-V2-A"])
    assert info["eligible"] is False and "CLIPPING" in info["reason"] and info["sessions"][0]["by_quality"].get("UNUSABLE", 0) > 0


def test_foreign_and_active_sessions_are_refused_for_v2_too(tmp_path):
    _, demo = store_with_sessions(tmp_path)
    with pytest.raises(PermissionError):
        demo.prepare("someone-else", session_ids=["HW-V2-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1, initialisation="MODEL_V2_FINAL")
    with pytest.raises(LookupError):
        demo.prepare("user-a", session_ids=["NOPE"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1, initialisation="MODEL_V2_FINAL")


async def _run(tmp_path: Path, *, algorithm: str, secagg: str, rounds: int = 3):
    _, demo = store_with_sessions(tmp_path, sessions=("HW-V2-A", "HW-V2-B"))
    jobs = HardwareRunJobs(demo, tmp_path)
    job = jobs.start("user-a", asyncio.get_running_loop(), session_ids=["HW-V2-A", "HW-V2-B"], rounds=rounds, algorithm=algorithm, secagg_mode=secagg, label_seed=7, initialisation="MODEL_V2_FINAL")
    for _ in range(1200):
        await asyncio.sleep(0.25)
        if job.status != "RUNNING" and job.journal.closed:
            break
    return demo, jobs, job


@pytest.mark.parametrize(("algorithm", "secagg"), [("FEDAVG", "PLAIN"), ("FEDPROX", "SECAGG_SHADOW")])
def test_v2_hardware_run_trains_for_real_and_feeds_every_builder(tmp_path, algorithm, secagg):
    async def go():
        demo, jobs, job = await _run(tmp_path, algorithm=algorithm, secagg=secagg)
        assert job.status == "COMPLETED", job.failure
        d = jobs.describe(job)
        assert d["base_model"]["model_id"] == "MODEL_V2_FINAL" and d["source_mode"] == "RECORDED_HARDWARE" and d["algorithm"] == algorithm
        assert d["client_ids"] == ["RECORDED_DEMO_CLIENT_00", *[f"SIM_FL_SITE_{i:02d}" for i in range(1, 8)]]
        assert {e.payload.client_id for e in job.journal.events if e.event_type == "client.status"} == set(d["client_ids"])
        kinds = [e.event_type for e in job.journal.events]
        assert kinds[0] == "federation.status" and kinds[-1] == "federation.completed" and kinds.count("client.update_ready") == 24
        if secagg == "SECAGG_SHADOW":
            shadow = [str(e.payload.status) for e in job.journal.events if e.event_type == "secagg.status"]
            assert "SHADOW_VERIFIED" in shadow
        directory = demo.root / job.run_id
        run = json.loads((directory / "run.json").read_text())
        dataset = json.loads((directory / "dataset.json").read_text())
        # the starting state is the verified pretrained checkpoint, and every committed round genuinely changed the weights
        from studio import v2_init

        assert run["state_progression"]["0"] == v2_init.load_v2_final()[1]["state_sha256"]
        digests = [run["state_progression"][str(i)] for i in range(4)]
        assert len(set(digests)) == 4
        assert all(r["clients"] and all(c["examples"] > 0 for c in r["clients"].values()) for r in run["rounds"])
        bundle = build_hardware_bundle(directory, run, dataset)
        assert sorted(bundle["evaluation"]["states"]) == ["R00", "R01", "R02", "R03"]
        pooled = bundle["evaluation"]["states"]["R03"]["pooled"]
        assert pooled["TP"] + pooled["FN"] == pooled["positives"] and 0.0 <= pooled["AUROC"] <= 1.0
        assert bundle["run"]["initialisation"]["model_id"] == "MODEL_V2_FINAL" and "V2" in bundle["synthetic_label"]
        assert len(build_specs(bundle, 2)) == 20 and len(build_tables(bundle)) == 12
    asyncio.run(go())


def test_a_restart_reloads_a_v2_hardware_run_with_its_base_model(tmp_path):
    async def go():
        demo, jobs, job = await _run(tmp_path, algorithm="FEDAVG", secagg="PLAIN")
        assert job.status == "COMPLETED", job.failure
        reloaded = HardwareRunJobs(demo, tmp_path)
        again = reloaded.jobs[job.run_id]
        d = reloaded.describe(again)
        assert d["base_model"]["model_id"] == "MODEL_V2_FINAL" and d["base_model"]["state_sha256"] and d["status"] == "COMPLETED"
    asyncio.run(go())


def test_the_recorded_client_is_capped_at_the_canonical_cohorts_largest_client_so_the_frozen_shadow_still_applies(tmp_path):
    ids = tuple(f"HW-V2-{c}" for c in "ABCDEFGH")
    _, demo = store_with_sessions(tmp_path, sessions=ids)
    ctx = demo.prepare("user-a", session_ids=list(ids), rounds=3, algorithm="FEDAVG", secagg_mode="SECAGG_SHADOW", label_seed=3, initialisation="MODEL_V2_FINAL")
    assert ctx["dataset"]["training_windows_available"] > 93 and ctx["datasets"][0].counts["trainable"] == 93 == ctx["dataset"]["training_windows"]
    assert max(len(d.labels) for d in ctx["datasets"]) == 93        # the frozen SecAgg+ preflight's input rule (largest client == 93)
