"""A completed History monitoring session as the signal of one federation client (studio.session_source)."""

from __future__ import annotations

import asyncio
import types

import pytest

from product.devices.scenarios import load_scenarios
from simulation.fl_cohort_v1 import cohort_profiles
from studio import session_source
from studio.runner10 import StudioFl10Service, StudioRunError


def test_every_frozen_scenario_session_regenerates_a_trainable_dataset_with_named_synthetic_labels():
    profile = cohort_profiles()[2]
    for scenario_id, scenario in load_scenarios().items():
        dataset, used = session_source.dataset_for_session({"session_id": "SESS-X", "scenario_id": scenario_id, "seed": scenario.seed}, profile)
        n = int(dataset.counts["trainable"])
        assert n >= session_source.MIN_TRAINABLE and dataset.inputs.shape == (n, 1, 2500) and abs(dataset.counts["synthetic_positive"] - n / 2) <= 1
        assert (dataset.client_id, dataset.session_id) == (profile.client_id, "SESS-X")
        assert used["source"] == "HISTORY_SESSION" and "SYNTHETIC_ASSIGNED" in used["labels"] and used["label_contract"] == session_source.LABEL_ID
        again, _ = session_source.dataset_for_session({"session_id": "SESS-X", "scenario_id": scenario_id, "seed": scenario.seed}, profile)
        other, _ = session_source.dataset_for_session({"session_id": "SESS-Y", "scenario_id": scenario_id, "seed": scenario.seed}, profile)
        assert again.dataset_sha256 == dataset.dataset_sha256 != other.dataset_sha256        # deterministic per session; labels differ by session


class _Store:
    def __init__(self, sessions: dict[str, object]) -> None:
        self._sessions = sessions

    def get_session(self, session_id: str):
        return self._sessions.get(session_id)


def _session(owner: str, state: str, scenario_id: str | None, seed: int | None = None):
    provenance = types.SimpleNamespace(scenario_id=scenario_id, seed=seed) if scenario_id else None
    return types.SimpleNamespace(user_id=owner, state=types.SimpleNamespace(value=state), simulation_provenance=provenance)


def test_only_a_completed_owned_frozen_scenario_session_can_be_a_signal_source():
    scenario = load_scenarios()["NORMAL_MONITORING"]
    store = _Store({"OK": _session("u", "COMPLETED", "NORMAL_MONITORING", scenario.seed), "RUNNING": _session("u", "RUNNING", "NORMAL_MONITORING", scenario.seed),
                    "OTHER": _session("v", "COMPLETED", "NORMAL_MONITORING", scenario.seed), "FORGED": _session("u", "COMPLETED", "NORMAL_MONITORING", scenario.seed + 1),
                    "NOPROV": _session("u", "COMPLETED", None)})
    assert session_source.resolve(store, "u", "OK") == {"session_id": "OK", "scenario_id": "NORMAL_MONITORING", "seed": scenario.seed}
    for sid, code in (("MISSING", "NOT_FOUND"), ("OTHER", "FORBIDDEN"), ("RUNNING", "INVALID_STATE"), ("FORGED", "INVALID_STATE"), ("NOPROV", "INVALID_STATE")):
        with pytest.raises(session_source.SessionSourceError) as error:
            session_source.resolve(store, "u", sid)
        assert error.value.code == code, sid


def test_the_runner_accepts_a_signal_session_only_for_the_live_monitored_mode_and_persists_it(tmp_path):
    service = StudioFl10Service(root=tmp_path, observer=None, inference_factory=None, other_run_active=lambda: False)   # type: ignore[arg-type]
    descriptor = {"session_id": "SESS-1", "scenario_id": "MIXED_MONITORING_SESSION", "seed": 1}

    async def go():
        with pytest.raises(StudioRunError) as error:
            await service.create("u", "A", "MODEL_V2_FINAL", 3, "FEDAVG", "PLAIN", 0, descriptor)
        assert error.value.code == "INVALID_REQUEST"
        job = await service.create("u", "B", "MODEL_V2_FINAL", 3, "FEDAVG", "PLAIN", 4, descriptor)       # needs no inference factory: nothing is monitored now
        assert job.signal_session == descriptor and job.monitored_site == 4
        reloaded = StudioFl10Service(root=tmp_path, observer=None, inference_factory=None, other_run_active=lambda: False)   # type: ignore[arg-type]
        assert reloaded.jobs[job.run_id].signal_session == descriptor
    asyncio.run(go())


class _Observer:
    """Stands in for the evaluation observer (scoring on the frozen holdouts is exercised elsewhere): accepts submissions and reports everything settled."""

    def __init__(self) -> None:
        self.submitted: list[int] = []
        self.rounds = 3

    def declare_pair(self, *a, **k) -> None:
        pass

    def submit(self, *, round_id: int, **k) -> None:
        self.submitted.append(round_id)

    def records(self, run_id: str):
        return [types.SimpleNamespace(evaluation_status="COMPLETED")] * (self.rounds + 1)

    def paired(self, run_id: str):
        return {}


def test_a_history_session_trains_one_client_for_real_and_the_other_seven_stay_canonical(tmp_path):
    """3 genuine rounds from the pretrained start with SITE_03 replaced by the regenerated session windows: the coordinator accepts 8 updates a round, the trace of the buffer matches."""
    import json

    observer = _Observer()
    service = StudioFl10Service(root=tmp_path, observer=observer, inference_factory=None, other_run_active=lambda: False)   # type: ignore[arg-type]
    scenario = load_scenarios()["MIXED_MONITORING_SESSION"]
    descriptor = {"session_id": "SESS-MIXED", "scenario_id": "MIXED_MONITORING_SESSION", "seed": scenario.seed}

    async def go():
        job = await service.create("u", "B", "MODEL_V2_FINAL", 3, "FEDAVG", "PLAIN", 3, descriptor)
        await service.start("u", job.run_id)
        await asyncio.wait_for(job.task, 900)
        return job

    job = asyncio.run(go())
    assert job.status == "COMPLETED", job.failure
    directory = tmp_path / job.run_id
    cohort = {c["client_id"]: c for c in json.loads((directory / "training_cohort.json").read_text())}
    assert cohort["SIM_FL_SITE_03"]["session_id"] == "SESS-MIXED" and all(cohort[f"SIM_FL_SITE_{i:02d}"]["session_id"] != "SESS-MIXED" for i in (0, 1, 2, 4, 5, 6, 7))
    link = json.loads((directory / "run/monitoring_link.json").read_text())
    assert link["site00_source"] == "HISTORY_SESSION_WINDOWS" and link["signal_session"] == descriptor and link["monitored_site"] == 3 and link["monitoring_sessions_executed"] == 0
    assert link["parity"]["label_contract"] == session_source.LABEL_ID and link["trace"]
    assert observer.submitted == [0, 1, 2, 3]
    report = json.loads((directory / "run/run_report.json").read_text())
    assert report["status"] == "COMPLETED" and all(r["accepted_updates"] == 8 for r in report["rounds"])
