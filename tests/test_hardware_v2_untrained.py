"""A recorded-hardware run can start from the UNTRAINED V2 network (FL_INIT_V2): the same family, windows, peers, cohorts, evaluation and bundle as the pretrained start, only R0 differs."""

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
from studio.service import StudioService  # noqa: E402


def _service(tmp_path: Path):
    store, _ = store_with_sessions(tmp_path / "s", sessions=("HW-V2-A", "HW-V2-B"))
    service = StudioService(root=tmp_path / "studio", federation=MagicMock(), inference_factory=None, other_run_active=lambda: False)
    service.hardware = HardwareRunJobs(HardwareDemoService(store, tmp_path / "studio"), tmp_path / "studio", finalize=service.finalize_hardware)
    service.hardware.state_sink = service.submit_hardware_v2_state
    return service


def test_an_untrained_v2_start_is_validated_without_a_candidate_and_for_every_cohort(tmp_path):
    service = _service(tmp_path)
    demo = service.hardware.demo
    for cohort in ("ORIGINAL", "REALISTIC", "REALISTIC_NSTDB"):
        ctx = demo.prepare("user-a", session_ids=["HW-V2-A", "HW-V2-B"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="FL_INIT_V2", cohort=cohort)
        assert ctx["cohort"] == cohort and len(ctx["client_ids"]) == 8                                   # one recorded client + seven synthetic peers
        assert ctx["model_block"]["base_audit"]["model_id"] == "FL_INIT_V2" and ctx["model_block"]["base_audit"]["kind"] == "UNTRAINED_INIT"
        assert ctx["model_block"]["v2_initialisation"] == "UNTRAINED_V2_FROM_SCRATCH"
        assert ctx["model_block"]["base_audit"]["state_sha256"] == v2_init.initial_state(v2_init.INIT_FRESH)[1]["state_sha256"]
        assert ctx["model_block"]["base_audit"]["state_sha256"] != v2_init.load_v2_final()[1]["state_sha256"]   # not the pretrained checkpoint
    with pytest.raises(ValueError, match="candidate_id applies only"):
        demo.prepare("user-a", session_ids=["HW-V2-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="FL_INIT_V2", candidate_id="FL10_CANDIDATE_X")


def test_an_untrained_v2_hardware_run_completes_is_evaluated_and_described_as_untrained(tmp_path):
    async def go():
        service = _service(tmp_path)
        job = service.hardware.start("user-a", asyncio.get_running_loop(), session_ids=["HW-V2-A", "HW-V2-B"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7,
                                     initialisation="FL_INIT_V2", cohort="REALISTIC_NSTDB")
        for _ in range(2400):
            await asyncio.sleep(0.25)
            if job.status != "RUNNING" and job.journal.closed and job.export_status in ("READY", "FAILED"):
                break
        assert job.status == "COMPLETED" and job.export_status == "READY", (job.failure, job.export_status)
        d = service.describe("user-a", job.run_id)
        assert d["base_model"]["model_id"] == "FL_INIT_V2" and d["base_model"]["kind"] is None and "untrained" in d["base_model"]["label"].lower()
        assert d["label"].endswith("untrained V2") and d["cohort"] == "REALISTIC_NSTDB"
        summary = service.evaluation_summary("user-a", job.run_id)
        assert [r["round_id"] for r in summary["records"]] == [0, 1, 2, 3] and all(r["evaluation_status"] == "COMPLETED" for r in summary["records"])
        r0 = service.evaluation_round("user-a", job.run_id, 0)
        assert r0["global_state_digest"] == v2_init.initial_state(v2_init.INIT_FRESH)[1]["state_sha256"]          # R0 is the seeded untrained state, byte for byte
        assert r0["metric_result"]["windows"] == 1446 and r0["participant_summary"]["participants_defined"] + r0["participant_summary"]["participants_undefined"] == 16   # an untrained model may leave some participants' F1 undefined
        bundle = service.bundle("user-a", job.run_id)
        assert bundle["run"]["initialisation"]["model_id"] == "FL_INIT_V2" and bundle["run"]["initialisation"]["kind"] == "UNTRAINED_INIT"      # the lineage and tables start from the untrained model, never "pretrained checkpoint"
        assert "PRETRAINED" not in bundle["synthetic_label"]
        assert len(service.figures("user-a", job.run_id)["specs"]) >= 20 and len(service.tables("user-a", job.run_id)["tables"]) >= 12
    asyncio.run(go())
