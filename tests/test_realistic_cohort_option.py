# ruff: noqa: E501
"""The synthetic-cohort option: a run can choose the REALISTIC cohort (training clients, evaluation holdout and wording) while ORIGINAL stays the default and unchanged."""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_hardware_v2_run import store_with_sessions

from studio import cohorts, v2_init
from studio.hardware_demo import HardwareDemoService
from studio.hardware_runs import HardwareRunJobs
from studio.runner10 import StudioRunError
from studio.service import StudioService


def _service(tmp_path: Path) -> StudioService:
    federation = MagicMock()
    federation.active_live_run.return_value = False
    return StudioService(root=tmp_path / "studio", federation=federation, inference_factory=None, other_run_active=lambda: False)


async def _wait(job, timeout_s: int = 900):
    for _ in range(timeout_s * 4):
        await asyncio.sleep(0.25)
        if job.status in ("COMPLETED", "FAILED") and job.export_status in ("READY", "FAILED"):
            return
    raise AssertionError("timeout")


def test_the_default_cohort_is_the_original_one_and_the_choice_is_validated(tmp_path):
    async def go():
        service = _service(tmp_path)
        job = await service.runner10.create("user-a", "A", v2_init.INIT_V2_FINAL, 3)
        d = service.describe("user-a", job.run_id)
        assert job.cohort == "ORIGINAL" and d["cohort"] == "ORIGINAL" and d["client_ids"][0] == "SIM_FL_SITE_00"
        with pytest.raises(StudioRunError):
            await service.runner10.create("user-a", "A", v2_init.INIT_V2_FINAL, 3, cohort="BOGUS")
        with pytest.raises(StudioRunError):                              # a History session regenerates the ORIGINAL cohort's site signal
            await service.runner10.create("user-a", "B", v2_init.INIT_V2_FINAL, 3, signal_session={"session_id": "x"}, cohort="REALISTIC")

    asyncio.run(go())


def test_the_registry_describes_every_cohort_and_each_realistic_holdout_matches_its_pinned_manifest():
    assert cohorts.COHORTS == ("ORIGINAL", "REALISTIC", "REALISTIC_NSTDB") and cohorts.REALISTIC_FAMILY == ("REALISTIC", "REALISTIC_NSTDB") and cohorts.DEFAULT == "ORIGINAL"
    original, realistic = cohorts.spec("ORIGINAL"), cohorts.spec("REALISTIC")
    assert original.client_ids[0] == "SIM_FL_SITE_00" and realistic.client_ids == original.client_ids and len(realistic.client_ids) == 8       # the same eight logical sites; participants, sessions and signals differ
    assert original.use_label.startswith("REUSED SYNTHETIC DIAGNOSTIC EVALUATION") and realistic.use_label.startswith("REALISTIC SYNTHETIC EVALUATION COHORT")
    holdout = cohorts.load_realistic()
    assert holdout.windows == cohorts.static_info()["windows"] and len(holdout.datasets) == 16
    assert len(holdout.separation) == 5 and all(row["participant_overlap"] == row["session_overlap"] == row["window_input_overlap"] == 0 for row in holdout.separation.values())
    nstdb = cohorts.spec("REALISTIC_NSTDB")
    assert nstdb.client_ids == original.client_ids and nstdb.evaluation_cohort_id == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3" and nstdb.use_label.startswith("REALISTIC SYNTHETIC EVALUATION COHORT WITH RECORDED NSTDB NOISE")
    assert "recorded" in nstdb.description.lower() and nstdb.claim_boundary.endswith("NOT_AAMI_SVF_OR_CLINICAL") and cohorts.is_realistic("REALISTIC_NSTDB") and not cohorts.is_realistic("ORIGINAL")
    h3 = cohorts.load_realistic("REALISTIC_NSTDB")
    assert h3.cohort_id == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3" and h3.windows == cohorts.static_info("REALISTIC_NSTDB")["windows"] and len(h3.datasets) == 16
    assert len(h3.separation) == 7 and "realistic_v2_evaluation_cohort_16_participants" in h3.separation        # also disjoint from the invented-noise realistic cohort
    assert all(row["participant_overlap"] == row["session_overlap"] == row["window_input_overlap"] == 0 for row in h3.separation.values())
    assert cohorts.holdout_provider("REALISTIC_NSTDB")() is h3 and cohorts.loaded_holdout("REALISTIC_NSTDB") is h3 and cohorts.loaded_holdout("REALISTIC") is holdout


def test_a_realistic_studio_run_trains_on_realistic_clients_and_is_scored_on_the_realistic_holdout(tmp_path):
    async def go():
        service = _service(tmp_path)
        job = await service.runner10.create("user-a", "A", v2_init.INIT_V2_FINAL, 3, cohort="REALISTIC")
        await service.runner10.start("user-a", job.run_id)
        await _wait(job)
        assert job.status == "COMPLETED" and job.export_status == "READY", (job.failure, job.export_status)
        d = service.describe("user-a", job.run_id)
        assert d["cohort"] == "REALISTIC" and d["client_ids"] == list(cohorts.spec("REALISTIC").client_ids) and "realistic cohort" in d["label"]
        summary = service.evaluation_summary("user-a", job.run_id)
        assert [r["round_id"] for r in summary["records"]] == [0, 1, 2, 3] and all(r["evaluation_status"] == "COMPLETED" for r in summary["records"])
        assert summary["cohort_use"] == cohorts.REALISTIC_USE_LABEL and summary["claim_boundary"] == cohorts.REALISTIC_CLAIM_BOUNDARY and summary["comparison"]["paired_available"] is True
        assert all(r["cohort_id"] == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2" and r["cohort_use"] == cohorts.REALISTIC_USE_LABEL for r in summary["records"])
        r0 = service.evaluation_round("user-a", job.run_id, 0)
        assert r0["metric_result"]["windows"] == cohorts.load_realistic().windows and r0["global_state_digest"] == v2_init.load_v2_final()[1]["state_sha256"]
        # the stored predictions reproduce the stored metrics at the documented fixed threshold, independently of the engine
        rows = list(csv.DictReader((service.observer.run_dir(job.run_id) / "R03" / "predictions.csv").open()))
        y, z = np.array([int(r["label"]) for r in rows]), np.array([float(r["logit"]) for r in rows])
        predicted = (1 / (1 + np.exp(-z)) >= 0.5).astype(int)
        stored = service.evaluation_round("user-a", job.run_id, 3)["metric_result"]
        assert [int(((predicted == 1) & (y == 1)).sum()), int(((predicted == 1) & (y == 0)).sum())] == [stored["TP"], stored["FP"]] and len(y) == stored["windows"]
        bundle = service.bundle("user-a", job.run_id)
        assert bundle["cohort"] == "REALISTIC" and bundle["evaluation"]["cohort_id"] == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2" and bundle["evaluation"]["method_freeze_commit"].startswith("NONE")
        assert [c["client_id"] for c in bundle["training_cohort"]] == d["client_ids"] and "REALISTIC" in bundle["synthetic_label"]
        assert len(service.figures("user-a", job.run_id)["specs"]) >= 20 and len(service.tables("user-a", job.run_id)["tables"]) >= 12
        assert (service.root / job.run_id / "export" / "export_manifest.json").exists()

    asyncio.run(go())


def test_a_recorded_noise_studio_run_trains_on_its_own_clients_and_is_scored_on_its_own_holdout(tmp_path):
    async def go():
        service = _service(tmp_path)
        job = await service.runner10.create("user-a", "A", v2_init.INIT_V2_FINAL, 3, cohort="REALISTIC_NSTDB")
        await service.runner10.start("user-a", job.run_id)
        await _wait(job)
        assert job.status == "COMPLETED" and job.export_status == "READY", (job.failure, job.export_status)
        d = service.describe("user-a", job.run_id)
        assert d["cohort"] == "REALISTIC_NSTDB" and d["client_ids"] == list(cohorts.spec("REALISTIC_NSTDB").client_ids) and "recorded noise" in d["label"]
        summary = service.evaluation_summary("user-a", job.run_id)
        assert [r["round_id"] for r in summary["records"]] == [0, 1, 2, 3] and all(r["evaluation_status"] == "COMPLETED" for r in summary["records"])
        assert summary["cohort_use"] == cohorts.NSTDB_USE_LABEL and summary["claim_boundary"] == cohorts.NSTDB_CLAIM_BOUNDARY
        assert all(r["cohort_id"] == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3" for r in summary["records"])
        assert service.evaluation_round("user-a", job.run_id, 0)["metric_result"]["windows"] == cohorts.load_realistic("REALISTIC_NSTDB").windows
        bundle = service.bundle("user-a", job.run_id)
        assert bundle["cohort"] == "REALISTIC_NSTDB" and bundle["evaluation"]["cohort_id"] == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3" and "RECORDED NSTDB NOISE" in bundle["synthetic_label"]
        assert [c["client_id"] for c in bundle["training_cohort"]] == d["client_ids"]

    asyncio.run(go())


@pytest.mark.parametrize("cohort", ["REALISTIC", "REALISTIC_NSTDB"])
def test_a_hardware_v2_run_can_take_its_seven_peers_and_its_evaluation_from_each_realistic_cohort(tmp_path, cohort):
    holdout_id = {"REALISTIC": "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2", "REALISTIC_NSTDB": "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3"}[cohort]
    use_label = {"REALISTIC": cohorts.REALISTIC_USE_LABEL, "REALISTIC_NSTDB": cohorts.NSTDB_USE_LABEL}[cohort]

    async def go():
        store, _ = store_with_sessions(tmp_path / "s", sessions=("HW-V2-A", "HW-V2-B"))
        service = _service(tmp_path)
        service.hardware = HardwareRunJobs(HardwareDemoService(store, tmp_path / "studio"), tmp_path / "studio", finalize=service.finalize_hardware)
        service.hardware.state_sink = service.submit_hardware_v2_state
        with pytest.raises(ValueError):                                   # the tabular family has eight recorded blocks and no synthetic peers
            service.hardware.demo.prepare("user-a", session_ids=["HW-V2-A"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="FRESH_SEEDED", cohort=cohort)
        job = service.hardware.start("user-a", asyncio.get_running_loop(), session_ids=["HW-V2-A", "HW-V2-B"], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="MODEL_V2_FINAL", cohort=cohort)
        await _wait(job)
        assert job.status == "COMPLETED" and job.export_status == "READY", (job.failure, job.export_status)
        d = service.describe("user-a", job.run_id)
        assert d["cohort"] == cohort and d["client_ids"][0] == "RECORDED_DEMO_CLIENT_00" and d["client_ids"][1:] == list(cohorts.spec(cohort).client_ids[1:])
        summary = service.evaluation_summary("user-a", job.run_id)
        assert all(r["evaluation_status"] == "COMPLETED" and r["cohort_id"] == holdout_id for r in summary["records"]) and summary["cohort_use"] == use_label
        assert service.evaluation_round("user-a", job.run_id, 0)["metric_result"]["windows"] == cohorts.load_realistic(cohort).windows
        bundle = service.bundle("user-a", job.run_id)
        assert bundle["cohort"] == cohort and "RECORDED HARDWARE WINDOWS" in bundle["synthetic_label"]
        assert max(c["counts"]["trainable"] for c in bundle["training_cohort"]) <= 93         # the frozen SecAgg+ round-1 size rule still holds

    asyncio.run(go())


# ---- the monitored site (source mode B) on the realistic cohort ------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("site", [0, 4])
def test_a_monitored_realistic_site_reproduces_its_own_canonical_dataset_and_reports_parity(site):
    from simulation import fl_cohort_realistic_v2 as realistic
    from studio import realistic_monitor
    from tests.capstone_product_support import StrictInferenceDouble

    profile = realistic.train_profile(site)
    canonical = realistic.build_dataset(profile)
    double = StrictInferenceDouble()
    monitored = asyncio.run(realistic_monitor.monitor_site(double.client, site, session_id=f"LIVELINK-REAL-{site}"))
    assert monitored["scenario_id"] == f"RL_SITE_{site:02d}_LIVE_LINK" and monitored["session_state"] == "COMPLETED"
    dataset = realistic_monitor.dataset_from_windows(monitored["windows"], profile)
    assert dataset.client_id == f"SIM_FL_SITE_{site:02d}" and dataset.counts["trainable"] > 0
    evidence = realistic_monitor.parity(monitored, dataset, profile, canonical.dataset_sha256)
    assert evidence["records_identical"] and evidence["window_samples_and_timestamps_identical"] and evidence["dataset_identical_to_canonical"]
    assert evidence["label_contract"] == "WEARABLE_SIM_REALISTIC_EVENT_WINDOW_V2" and len(double.requests) > 0


def test_a_monitored_recorded_noise_site_reproduces_its_own_canonical_dataset_and_reports_parity():
    from simulation import fl_cohort_realistic_v3 as recorded
    from studio import realistic_monitor
    from tests.capstone_product_support import StrictInferenceDouble

    site = 3
    profile = recorded.train_profile(site)
    canonical = recorded.build_dataset(profile)
    double = StrictInferenceDouble()
    monitored = asyncio.run(realistic_monitor.monitor_site(double.client, site, session_id="LIVELINK-NSTDB-3", cohort="REALISTIC_NSTDB"))
    assert monitored["scenario_id"] == "RL_SITE_03_LIVE_LINK" and monitored["session_state"] == "COMPLETED"
    dataset = realistic_monitor.dataset_from_windows(monitored["windows"], profile)
    assert dataset.client_id == "SIM_FL_SITE_03" and dataset.counts["trainable"] > 0
    evidence = realistic_monitor.parity(monitored, dataset, profile, canonical.dataset_sha256)
    assert evidence["records_identical"] and evidence["window_samples_and_timestamps_identical"] and evidence["dataset_identical_to_canonical"]
    assert evidence["label_contract"] == "WEARABLE_SIM_REALISTIC_EVENT_WINDOW_V3" and len(double.requests) > 0


def test_the_hardware_peers_of_the_recorded_noise_cohort_are_its_own_seven_clients():
    from studio import hardware_v2

    peers = hardware_v2.peer_datasets("REALISTIC_NSTDB")
    assert [p.client_id for p in peers] == list(cohorts.spec("REALISTIC_NSTDB").client_ids[1:]) and len(peers) == 7
    assert {p.dataset_sha256 for p in peers}.isdisjoint({p.dataset_sha256 for p in hardware_v2.peer_datasets("REALISTIC")})
    with pytest.raises(ValueError, match="REALISTIC_NSTDB"):
        hardware_v2.peer_datasets("BOGUS")


def test_a_realistic_run_can_monitor_a_site_live_and_trains_on_what_the_runtime_emitted(tmp_path):
    from tests.capstone_product_support import StrictInferenceDouble

    async def go():
        federation = MagicMock()
        federation.active_live_run.return_value = False
        double = StrictInferenceDouble()
        service = StudioService(root=tmp_path / "studio", federation=federation, inference_factory=double.client, other_run_active=lambda: False)
        job = await service.runner10.create("user-a", "B", v2_init.INIT_V2_FINAL, 3, monitored_site=2, cohort="REALISTIC")
        await service.runner10.start("user-a", job.run_id)
        await _wait(job)
        assert job.status == "COMPLETED" and job.export_status == "READY", (job.failure, job.export_status)
        d = service.describe("user-a", job.run_id)
        assert d["cohort"] == "REALISTIC" and d["monitored_site"] == 2 and d["source_mode"] == "LIVE_MONITORED_SITE_00"
        bundle = service.bundle("user-a", job.run_id)
        link = bundle["monitoring_link"]
        assert link["monitored_client_id"] == "SIM_FL_SITE_02" and link["parity"]["dataset_identical_to_canonical"] is True and link["parity"]["label_contract"] == "WEARABLE_SIM_REALISTIC_EVENT_WINDOW_V2"
        assert bundle["cohort"] == "REALISTIC" and bundle["evaluation"]["cohort_id"] == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2"
        assert all(r["evaluation_status"] == "COMPLETED" for r in service.evaluation_summary("user-a", job.run_id)["records"])

    asyncio.run(go())


# ---- the HTTP surface ----------------------------------------------------------------------------------------------------------------------------------------------------------

def test_the_studio_routes_advertise_every_cohort_and_validate_the_choice(tmp_path):
    from fastapi.testclient import TestClient

    from tests.capstone_product_support import BASE, USER_A
    from tests.test_studio_api import _app

    with TestClient(_app(tmp_path)) as c:
        caps = c.get(f"{BASE}/studio/capabilities", headers=USER_A).json()["ten_round"]
        assert [(x["id"], x["default"]) for x in caps["cohorts"]] == [("ORIGINAL", True), ("REALISTIC", False), ("REALISTIC_NSTDB", False)]
        assert caps["cohorts"][1]["evaluation_cohort_id"] == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2" and caps["cohorts"][2]["evaluation_cohort_id"] == "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3" and "frozen product contract" in caps["cohort_note"]
        bad = c.post(f"{BASE}/studio/runs", headers=USER_A, json={"run_length": 10, "cohort": "EXOTIC"})
        assert bad.status_code == 400 and "cohort must be one of ORIGINAL, REALISTIC, REALISTIC_NSTDB" in bad.text
        untrained3 = c.post(f"{BASE}/studio/runs", headers=USER_A, json={"run_length": 3, "initialisation": "FL_INIT_V2"})
        assert untrained3.status_code == 400                                  # 3 untrained rounds on the ORIGINAL cohort are the frozen product contract (a realistic cohort runs on the extended engine)
        extra = c.post(f"{BASE}/studio/runs", headers=USER_A, json={"run_length": 10, "cohorts": "REALISTIC"})
        assert extra.status_code == 400                                       # unknown keys are still refused


def test_figure_titles_name_the_cohort_they_are_scored_on():
    from studio.specs import figure_title

    original = figure_title("FL10_FIG04", 10)
    realistic = figure_title("FL10_FIG04", 10, "REALISTIC")
    assert "reused diagnostic holdout" in original and "realistic" not in original
    assert "realistic diagnostic holdout" in realistic and "reused" not in realistic
    assert figure_title("FL10_FIG04", 10, "ORIGINAL") == original                         # the default is unchanged
    assert figure_title("FL10_FIG04", 10, "REALISTIC_NSTDB") == realistic                 # the recorded-noise cohort is a realistic-family holdout
