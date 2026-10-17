"""A pretrained-V2 recorded-hardware run is evaluated, bundled and described EXACTLY like a synthetic V2 run: same observer, same frozen evaluation cohort, same candidate, same figure builders."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from test_hardware_v2_run import store_with_sessions  # noqa: E402

from studio import v2_init  # noqa: E402
from studio.hardware_demo import HardwareDemoService  # noqa: E402
from studio.hardware_runs import HardwareRunJobs  # noqa: E402
from studio.service import StudioService  # noqa: E402


async def _go(tmp_path: Path):
    store, _ = store_with_sessions(tmp_path / "s", sessions=("HW-V2-A", "HW-V2-B"))
    service = StudioService(root=tmp_path / "studio", federation=MagicMock(), inference_factory=None, other_run_active=lambda: False)
    service.hardware = HardwareRunJobs(HardwareDemoService(store, tmp_path / "studio"), tmp_path / "studio", finalize=service.finalize_hardware)
    service.hardware.state_sink = service.submit_hardware_v2_state
    job = service.hardware.start("user-a", asyncio.get_running_loop(), session_ids=["HW-V2-A", "HW-V2-B"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="MODEL_V2_FINAL")
    for _ in range(2400):
        await asyncio.sleep(0.25)
        if job.status != "RUNNING" and job.journal.closed and job.export_status in ("READY", "FAILED"):
            break
    return service, job


def test_hardware_v2_run_uses_the_synthetic_evaluation_candidate_and_bundle(tmp_path):
    async def go():
        service, job = await _go(tmp_path)
        assert job.status == "COMPLETED" and job.export_status == "READY", (job.failure, job.export_status)
        d = service.describe("user-a", job.run_id)
        assert d["evaluation"]["available"] is True and d["evaluation"]["evaluation_run_id"] == job.run_id
        assert d["candidate"]["candidate_id"] == f"FL10_CANDIDATE_{job.run_id}"
        summary = service.evaluation_summary("user-a", job.run_id)
        assert [r["round_id"] for r in summary["records"]] == [0, 1, 2, 3] and all(r["evaluation_status"] == "COMPLETED" for r in summary["records"])
        assert summary["evaluation_protocol_id"] == "NHM_FL10_SYNTHETIC_EVALUATION_V1" and summary["comparison"]["paired_available"] is True
        r0 = service.evaluation_round("user-a", job.run_id, 0)
        assert r0["metric_result"]["windows"] == 1446 and r0["participant_summary"]["participants_defined"] == 16     # the frozen synthetic cohort, not an 11-window recording block
        assert r0["global_state_digest"] == v2_init.load_v2_final()[1]["state_sha256"]                                  # R0 is the pretrained checkpoint, byte for byte
        bundle = service.bundle("user-a", job.run_id)
        assert bundle["run"]["candidate"]["candidate_id"].startswith("FL10_CANDIDATE_") and len(bundle["evaluation"]["states"]) == 4
        assert [c["client_id"] for c in bundle["training_cohort"]] == d["client_ids"] and "RECORDED HARDWARE WINDOWS" in bundle["synthetic_label"]
        assert len(service.figures("user-a", job.run_id)["specs"]) >= 20 and len(service.tables("user-a", job.run_id)["tables"]) >= 12
        assert service.generalisation_summary("user-a", job.run_id)["run_id"] == job.run_id
        assert (service.hardware.demo.root / job.run_id / "export" / "export_manifest.json").exists()
    asyncio.run(go())
