"""A recorded-hardware run is a first-class Studio run: same federation journal, same bundle schema, same figure/table builders."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_hardware_demo_fl import populated  # noqa: E402

from studio.hardware_bundle import build_hardware_bundle  # noqa: E402
from studio.hardware_runs import HardwareRunJobs  # noqa: E402
from studio.specs import build_specs  # noqa: E402
from studio.tables import build_tables  # noqa: E402


async def _run(tmp_path: Path, *, algorithm: str = "FEDPROX", secagg: str = "SECAGG_SHADOW", rounds: int = 3):
    store, demo = populated(tmp_path, seconds=60)
    jobs = HardwareRunJobs(demo, tmp_path)
    job = jobs.start("user-a", asyncio.get_running_loop(), session_ids=["HW-RECORDED-A"], rounds=rounds, algorithm=algorithm, secagg_mode=secagg, label_seed=3)
    for _ in range(200):
        await asyncio.sleep(0.1)
        if job.status != "RUNNING" and job.journal.closed:
            break
    return store, demo, jobs, job


def test_hardware_run_emits_the_same_federation_journal_as_a_synthetic_run(tmp_path):
    async def go():
        _, _, _, job = await _run(tmp_path)
        assert job.status == "COMPLETED" and job.journal.closed
        kinds = [e.event_type for e in job.journal.events]
        assert kinds[0] == "federation.status" and kinds[-1] == "federation.completed"
        assert kinds.count("client.update_ready") == 24                      # 8 clients x 3 rounds
        clients = {e.payload.client_id for e in job.journal.events if e.event_type == "client.status"}
        assert clients == {f"RECORDED_DEMO_CLIENT_{i:02d}" for i in range(8)}
        # sequence is contiguous and every event validates (the journal enforces both)
        assert [e.sequence_index for e in job.journal.events] == list(range(len(job.journal.events)))
        # round-1 shadow is reported (this status was silently dropped by a non-existent enum member before)
        shadow = [(e.payload.round_id, str(e.payload.status)) for e in job.journal.events if e.event_type == "secagg.status"]
        assert shadow[:2] == [(1, "SHADOW_RUNNING"), (1, "SHADOW_VERIFIED")] and shadow[2:] == [(2, "NOT_USED"), (3, "NOT_USED")]
    asyncio.run(go())


def test_bundle_feeds_every_figure_and_table_builder_with_real_metrics(tmp_path):
    async def go():
        _, demo, _, job = await _run(tmp_path)
        directory = demo.root / job.run_id
        run = json.loads((directory / "run.json").read_text())
        dataset = json.loads((directory / "dataset.json").read_text())
        bundle = build_hardware_bundle(directory, run, dataset)
        assert sorted(bundle["evaluation"]["states"]) == ["R00", "R01", "R02", "R03"]
        pooled = bundle["evaluation"]["states"]["R03"]["pooled"]
        assert 0.0 <= pooled["AUROC"] <= 1.0 and pooled["TP"] + pooled["FN"] == pooled["positives"]
        specs, tables = build_specs(bundle, 2), build_tables(bundle)
        assert len(specs) == 20 and len(tables) == 12
        assert specs["FL10_FIG16"]["availability"] == "NOT_APPLICABLE" and tables["FL10_TAB02"]["availability"] == "NOT_APPLICABLE"
        assert tables["FL10_TAB11"]["availability"] == "NOT_APPLICABLE"
        assert len(tables["FL10_TAB03"]["rows"]) == 24 and len(tables["FL10_TAB07"]["rows"]) == 3
        # nothing synthetic-cohort leaks into hardware wording
        text = json.dumps({"s": specs["FL10_FIG01"], "t": tables["FL10_TAB10"]})
        assert "SIM_FL_SITE" not in text and "AdamW" not in text and "RECORDED" in text.upper()
    asyncio.run(go())


def test_partial_run_json_is_written_per_round_so_evaluation_is_progressive(tmp_path):
    async def go():
        _, demo, _, job = await _run(tmp_path)
        data = json.loads((demo.root / job.run_id / "run.json").read_text())
        assert data["status"] == "COMPLETED" and data["completed_at"] and len(data["rounds"]) == 3
        assert (demo.root / job.run_id / "checkpoints" / "R00.json").exists()      # the initial state is scored too
    asyncio.run(go())


def test_restart_marks_a_running_run_failed_and_never_a_result(tmp_path):
    async def go():
        store, demo, jobs, job = await _run(tmp_path)
        path = demo.root / job.run_id / "run.json"
        data = json.loads(path.read_text())
        path.write_text(json.dumps(data | {"status": "RUNNING", "completed_at": None}))
        reloaded = HardwareRunJobs(demo, tmp_path)
        again = reloaded.jobs[job.run_id]
        assert again.status == "FAILED" and again.failure["code"] == "INTERRUPTED_BY_RESTART"
    asyncio.run(go())


def test_one_hardware_run_at_a_time_and_owner_scope(tmp_path):
    async def go():
        store, demo = populated(tmp_path, seconds=60)
        jobs = HardwareRunJobs(demo, tmp_path)
        loop = asyncio.get_running_loop()
        with pytest.raises(PermissionError):
            jobs.start("someone-else", loop, session_ids=["HW-RECORDED-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1)
        job = jobs.start("user-a", loop, session_ids=["HW-RECORDED-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1)
        assert jobs.owner_of(job.run_id) == "user-a" and jobs.owner_of("HDFLRUN-NOPE") is None
        for _ in range(200):
            await asyncio.sleep(0.1)
            if job.status != "RUNNING":
                break
        assert job.status == "COMPLETED"
    asyncio.run(go())


def test_descriptor_carries_the_validated_provenance_the_ui_relies_on(tmp_path):
    async def go():
        _, _, jobs, job = await _run(tmp_path, algorithm="FEDAVG", secagg="PLAIN")
        d = jobs.describe(job)
        assert d["engine"] == "HARDWARE_DEMO" and d["source_mode"] == "RECORDED_HARDWARE" and d["origin"] == "LIVE" and d["run_type"] == "LIVE_RUN"
        assert d["base_model"]["model_id"] == "HARDWARE_DEMO_MODEL_V1" and d["base_model"]["initialisation"] == "FRESH_SEEDED"
        assert d["candidate"] is None and d["status"] == "COMPLETED" and d["client_ids"][0] == "RECORDED_DEMO_CLIENT_00"
    asyncio.run(go())
