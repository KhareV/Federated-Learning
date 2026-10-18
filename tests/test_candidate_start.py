# ruff: noqa: E501
"""Engineering candidates are kept in the library when a run completes and can start a later run: synthetic, monitored-site or recorded-hardware (pretrained-V2 family), across cohorts."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_hardware_v2_run import store_with_sessions  # noqa: E402

from studio import v2_init  # noqa: E402
from studio.hardware_demo import HardwareDemoService  # noqa: E402
from studio.hardware_runs import HardwareRunJobs  # noqa: E402
from studio.runner10 import StudioRunError  # noqa: E402
from studio.service import StudioService  # noqa: E402


def _service(tmp_path: Path) -> StudioService:
    federation = MagicMock()
    federation.active_live_run.return_value = False
    return StudioService(root=tmp_path / "studio", federation=federation, inference_factory=None, other_run_active=lambda: False)


async def _wait(job, timeout_s: int = 1200):
    for _ in range(timeout_s * 4):
        await asyncio.sleep(0.25)
        if job.status in ("COMPLETED", "FAILED") and job.export_status in ("READY", "FAILED"):
            return
    raise AssertionError("timeout")


def test_starting_from_a_candidate_is_validated_before_a_run_exists(tmp_path):
    async def go():
        service = _service(tmp_path)
        with pytest.raises(StudioRunError) as missing:                              # a candidate the owner does not have
            await service.runner10.create("user-a", "A", "CANDIDATE", 3, candidate_id="FL10_CANDIDATE_NOPE")
        assert missing.value.code == "NOT_FOUND"
        with pytest.raises(StudioRunError):                                         # CANDIDATE needs an id
            await service.runner10.create("user-a", "A", "CANDIDATE", 3)
        with pytest.raises(StudioRunError):                                         # an id without CANDIDATE
            await service.runner10.create("user-a", "A", v2_init.INIT_V2_FINAL, 3, candidate_id="FL10_CANDIDATE_X")
        with pytest.raises(StudioRunError):                                         # 3 rounds from an untrained start stays the frozen product contract
            await service.runner10.create("user-a", "A", v2_init.INIT_FRESH, 3)

    asyncio.run(go())


def test_candidates_are_kept_by_completed_runs_and_start_synthetic_and_hardware_runs_across_cohorts(tmp_path):
    async def go():
        store, _ = store_with_sessions(tmp_path / "s", sessions=("HW-V2-A", "HW-V2-B"))
        service = _service(tmp_path)
        service.hardware = HardwareRunJobs(HardwareDemoService(store, tmp_path / "studio"), tmp_path / "studio", finalize=service.finalize_hardware)
        service.hardware.state_sink = service.submit_hardware_v2_state
        service.hardware.demo.candidates = service.candidates
        loop = asyncio.get_running_loop()

        # 1. a REALISTIC synthetic run completes: its final candidate is stored, tagged with its cohort, source and evaluation snapshot
        one = await service.runner10.create("user-a", "A", v2_init.INIT_V2_FINAL, 3, cohort="REALISTIC")
        await service.runner10.start("user-a", one.run_id)
        await _wait(one)
        assert one.status == "COMPLETED", one.failure
        [stored] = service.candidates.list("user-a")
        assert stored["candidate_id"] == one.candidate["candidate_id"] and stored["state_sha256"] == one.candidate["state_sha256"]
        assert stored["cohort"] == "REALISTIC" and stored["source_kind"] == "SYNTHETIC_COHORT" and stored["source_run_id"] == one.run_id and stored["run_length"] == 3
        assert stored["metrics"]["AUPRC"] > 0 and stored["promoted"] is False and stored["deployed"] is False and stored["registered_in_product_registry"] is False
        assert service.candidates.list("user-b") == []                                # owner-scoped

        # 2. that candidate starts a RECORDED-HARDWARE run (pretrained-V2 family) on the ORIGINAL cohort's peers: R0 is the candidate, the run says so
        job = service.hardware.start("user-a", loop, session_ids=["HW-V2-A", "HW-V2-B"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="CANDIDATE", candidate_id=stored["candidate_id"])
        await _wait(job)
        assert job.status == "COMPLETED" and job.export_status == "READY", (job.failure, job.export_status)
        d = service.describe("user-a", job.run_id)
        assert d["base_model"]["kind"] == "CANDIDATE" and d["base_model"]["model_id"] == stored["candidate_id"] and d["base_model"]["candidate_cohort"] == "REALISTIC" and d["cohort"] == "ORIGINAL"
        assert "candidate start" in d["label"]
        r0 = service.evaluation_round("user-a", job.run_id, 0)
        assert r0["global_state_digest"] == stored["state_sha256"] != v2_init.load_v2_final()[1]["state_sha256"]      # R0 is the stored candidate, not the pretrained checkpoint
        assert {c["source_kind"] for c in service.candidates.list("user-a")} == {"SYNTHETIC_COHORT", "RECORDED_HARDWARE"}
        [hardware_candidate] = [c for c in service.candidates.list("user-a") if c["source_kind"] == "RECORDED_HARDWARE"]
        assert hardware_candidate["source_detail"]["session_ids"] == ["HW-V2-A", "HW-V2-B"] and hardware_candidate["base_model"]["kind"] == "CANDIDATE"      # lineage: it descends from the first candidate

        # 3. the hardware candidate starts a SYNTHETIC run on the REALISTIC cohort again (10 rounds are not needed: 3 rounds are allowed from a candidate)
        three = await service.runner10.create("user-a", "A", "CANDIDATE", 3, cohort="REALISTIC", candidate_id=hardware_candidate["candidate_id"])
        await service.runner10.start("user-a", three.run_id)
        await _wait(three)
        assert three.status == "COMPLETED", three.failure
        d3 = service.describe("user-a", three.run_id)
        assert d3["base_model"]["kind"] == "CANDIDATE" and d3["base_model"]["source_run_id"] == job.run_id and "candidate start" in d3["label"]
        assert service.evaluation_round("user-a", three.run_id, 0)["global_state_digest"] == hardware_candidate["state_sha256"]
        assert len(service.candidates.list("user-a")) == 3

    asyncio.run(go())


def test_the_studio_routes_list_only_the_callers_candidates_and_advertise_the_library(tmp_path):
    from fastapi.testclient import TestClient

    from tests.capstone_product_support import BASE, USER_A, USER_B
    from tests.test_studio_api import _app

    state = v2_init.load_v2_final()[0]
    with TestClient(_app(tmp_path)) as c:
        library = c.app.state.studio_service.candidates
        library.register(owner="demo:cap003-user-a", candidate_id="FL10_CANDIDATE_FL10RUN-AAA", source_run_id="FL10RUN-AAA", source_kind="SYNTHETIC_COHORT", source_detail={}, cohort="REALISTIC", evaluation_cohort_id="E", run_length=10, algorithm="FEDAVG",
                         secagg_mode="PLAIN", base_model={"model_id": "MODEL_V2_FINAL"}, state=state, metrics={"AUPRC": 0.8})
        assert c.get(f"{BASE}/studio/candidates").status_code == 401                                   # identity required
        mine = c.get(f"{BASE}/studio/candidates", headers=USER_A).json()
        assert [x["candidate_id"] for x in mine] == ["FL10_CANDIDATE_FL10RUN-AAA"] and mine[0]["cohort_label"] == "Realistic synthetic cohort" and "owner" not in mine[0]
        assert c.get(f"{BASE}/studio/candidates", headers=USER_B).json() == []                        # another account sees nothing
        assert c.get(f"{BASE}/studio/candidates/FL10_CANDIDATE_FL10RUN-AAA", headers=USER_A).status_code == 200
        assert c.get(f"{BASE}/studio/candidates/FL10_CANDIDATE_FL10RUN-AAA", headers=USER_B).status_code == 404
        caps_a = c.get(f"{BASE}/studio/capabilities", headers=USER_A).json()
        caps_b = c.get(f"{BASE}/studio/capabilities", headers=USER_B).json()
        assert caps_a["candidate_library"]["count"] == 1 and caps_b["candidate_library"]["count"] == 0
        assert caps_a["candidate_library"]["rounds"] == [3, 10] and "CANDIDATE" not in caps_a["ten_round"]["rounds_by_initialisation"]       # the pinned initialisation contract is unchanged
        assert {m["id"]: m["available"] for m in caps_a["hardware_demo"]["starting_models"]}["CANDIDATE"] is True
        assert {m["id"]: m["available"] for m in caps_b["hardware_demo"]["starting_models"]}["CANDIDATE"] is False
        # a candidate of another account is indistinguishable from a missing one when starting a run
        denied = c.post(f"{BASE}/studio/runs", headers=USER_B, json={"run_length": 3, "initialisation": "CANDIDATE", "candidate_id": "FL10_CANDIDATE_FL10RUN-AAA"})
        assert denied.status_code == 404
        assert c.post(f"{BASE}/studio/runs", headers=USER_A, json={"run_length": 3, "initialisation": "CANDIDATE"}).status_code == 400          # CANDIDATE needs an id
