# ruff: noqa: E501
"""NHM-FL10-001 training negative controls and genuine-evidence checks (no fresh-holdout scoring)."""

from __future__ import annotations

import json
from collections import OrderedDict
from functools import cache
from pathlib import Path

import numpy as np
import pytest

from federated.wearable_fl_runner_v1 import build_cohort
from final_showcase import link_trace as lt
from fl10 import runner
from fl10.trace import Fl10TrainerTap

ROOT = Path(__file__).resolve().parents[1]
MODE_A = ROOT / "reports/fl10/runs/modeA"
MODE_B = ROOT / "reports/fl10/runs/modeB"


@cache
def _cohort():
    _, datasets, manifest = build_cohort()
    return datasets, manifest


def _run(tmp_path, rounds=1, **kw):
    datasets, manifest = _cohort()
    return runner.run_training(mode="A", run_id="T", out_dir=tmp_path, datasets=kw.pop("datasets", datasets), manifest=kw.pop("manifest", manifest), rounds=rounds, capture_batches=False, **kw)


def test_existing_run_directory_is_never_overwritten(tmp_path):
    directory = tmp_path / "previous-attempt"
    directory.mkdir()
    marker = directory / "run_report.partial.json"
    marker.write_text("preserve failed evidence")
    with pytest.raises(runner.Fl10Error, match="RUN_ARTIFACT_DIRECTORY_NOT_EMPTY"):
        _run(directory)
    assert marker.read_text() == "preserve failed evidence"


def test_wrong_initial_state_is_refused(tmp_path, monkeypatch):
    from federated.wearable_fl_runner_v1 import new_session

    state, spec = new_session()
    key = next(k for k, v in state.items() if np.issubdtype(np.asarray(v).dtype, np.floating))
    bad = OrderedDict(state)
    bad[key] = np.asarray(state[key]) + 1e-3
    monkeypatch.setattr(runner, "new_session", lambda: (bad, spec))
    with pytest.raises(runner.Fl10Error, match="WRONG_INITIAL_STATE"):
        _run(tmp_path)


def test_prefix_parity_mismatch_stops_the_run_and_leaves_no_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "LEARNING_RATE", 0.002)          # an (illegitimate) parameter change must be caught, never silently accepted
    with pytest.raises(runner.Fl10Error, match="PREFIX_PARITY_MISMATCH"):
        _run(tmp_path)
    report = json.loads((tmp_path / "run_report.json").read_text())
    assert report["status"] == "INCOMPLETE_NOT_A_CANDIDATE" and "candidate" not in report and report["rounds_committed"] == 0


def test_incorrect_previous_round_base_is_refused(tmp_path):
    def tamper(round_id, state):
        if round_id != 2:
            return state
        out = OrderedDict(state)
        key = next(k for k, v in out.items() if np.issubdtype(np.asarray(v).dtype, np.floating))
        out[key] = np.asarray(out[key]) * 1.0001
        return out

    with pytest.raises(runner.Fl10Error, match="INCORRECT_PREVIOUS_ROUND_BASE"):
        _run(tmp_path, rounds=2, tamper_before_round=tamper)


def test_every_round_rejects_all_seven_adversarial_updates_and_probes_missing_client(tmp_path):
    report = _run(tmp_path, rounds=3)
    assert report["status"] == "COMPLETED" and report["accepted_updates_total"] == 24
    for r in report["rounds"]:
        codes = sorted(x["code"] for x in r["rejections"])
        expected = sorted(["DUPLICATE_UPDATE", "BASE_STATE_MISMATCH", "UNKNOWN_CLIENT", "UPDATE_SHA_MISMATCH", "SCHEMA_MISMATCH", "NONFINITE_UPDATE", *(["STALE_ROUND"] if r["round"] > 1 else [])])
        assert codes == expected and r["accepted_updates"] == 8 and r["missing_client_probe"] == "INCOMPLETE_ROUND" and r["second_commit"] == "ROUND_ALREADY_COMMITTED"
        assert abs(sum(r["weights"].values()) - 1.0) < 1e-12 and r["server_boundary_forbidden_hits"] == []
    assert all(v is True for v in report["prefix_equals_frozen_reference"].values())


def test_missing_client_wrong_dataset_digest_and_cross_client_access_are_refused(tmp_path):
    datasets, manifest = _cohort()
    with pytest.raises(runner.Fl10Error, match="COHORT_MANIFEST_MISMATCH"):
        _run(tmp_path / "a", datasets=datasets[:7], manifest={k: v for k, v in manifest.items() if k != datasets[7].client_id})
    bad = {k: dict(v) for k, v in manifest.items()}
    bad[datasets[0].client_id]["dataset_sha"] = "0" * 64
    with pytest.raises(runner.Fl10Error, match="DATASET_DIGEST_MISMATCH"):
        _run(tmp_path / "b", manifest=bad)
    from product.edge.local_training_buffer import BufferError, LocalTrainingBufferV1

    buf = LocalTrainingBufferV1(datasets[0].client_id, datasets[0].participant_id)
    buf.ingest_dataset(datasets[0])
    with pytest.raises(BufferError, match="CROSS_CLIENT"):
        buf.training_arrays(requester_client_id=datasets[1].client_id)


def test_site00_tensor_substitution_and_spoofed_buffer_are_rejected(tmp_path):
    import dataclasses

    from federated.virtual_client_source_v1 import build_local_dataset
    from federated.wearable_sim_local_labels import SyntheticObservedSource
    from product.edge.label_adapter import SimulationLabelAdapterV1
    from product.edge.local_training_buffer import LocalTrainingBufferV1
    from simulation.fl_cohort_v1 import cohort_profiles

    datasets, _ = _cohort()
    monitored = datasets[0]                                           # what the monitoring session claims to have produced
    other = cohort_profiles()[3]
    stolen = dataclasses.replace(build_local_dataset(SyntheticObservedSource(other), SimulationLabelAdapterV1(other)), client_id=monitored.client_id, participant_id=monitored.participant_id, session_id=monitored.session_id)
    swapped = [stolen, *datasets[1:]]
    manifest = {d.client_id: {"participant_id": d.participant_id, "session_id": d.session_id, "dataset_sha": d.dataset_sha256} for d in swapped}
    tap = Fl10TrainerTap()
    with tap:
        runner.run_training(mode="B", run_id="T", out_dir=tmp_path, datasets=swapped, manifest=manifest, rounds=1, require_prefix_parity=False, capture_batches=False)
    expected = lt.expected_trace(monitored)
    honest = LocalTrainingBufferV1(monitored.client_id, monitored.participant_id)
    honest.ingest_dataset(monitored)
    with pytest.raises(lt.LinkTraceError, match="TRAINER_INPUT_NOT_THE_MONITORED_WINDOWS"):   # spoofed buffer report cannot hide the optimizer-entry tensors
        lt.verify_trace(expected, lt.buffer_trace(honest), tap.calls, client_id=monitored.client_id, rounds=1)
    with pytest.raises(lt.LinkTraceError):                                                    # altered synthetic event labels
        lt.verify_trace(lt.expected_trace(dataclasses.replace(monitored, labels=1 - monitored.labels)), lt.buffer_trace(honest), tap.calls, client_id=monitored.client_id, rounds=1)


# ---------------------------------------------------------------- the genuine recorded evidence
@cache
def _report(path: Path):
    return json.loads((path / "run_report.json").read_text())


@pytest.mark.parametrize("path", [MODE_A, MODE_B])
def test_recorded_run_is_a_genuine_ten_round_run(path):
    r = _report(path)
    assert r["status"] == "COMPLETED" and r["rounds_committed"] == 10 and r["accepted_updates_total"] == 80 and len(r["updates"]) == 80 and len({u["update_sha256"] for u in r["updates"]}) == 80
    assert all(x["accepted_updates"] == 8 and x["aggregation_state"] == "COMPLETE" for x in r["rounds"])
    assert r["example_exposures_total"] == sum(x["total_accepted_example_weight"] for x in r["rounds"]) == r["unique_training_windows"] * 10
    prev = r["state_progression"]["0"]["sha256"]
    for x in r["rounds"]:                                              # lineage: each base is the previous committed state
        assert x["base_state_sha256"] == prev
        prev = x["global_state_sha256"]
    assert r["candidate"]["state_sha256"] == prev and r["candidate"]["promoted"] is False and r["candidate"]["deployed"] is False and r["candidate"]["registered_in_product_registry"] is False
    assert all(len(list((path / "states").glob("R*.bin"))) == 11 for _ in [0])


def test_prefix_equals_frozen_canonical_run_and_mode_b_equals_mode_a_by_computed_digest():
    a, b = _report(MODE_A), _report(MODE_B)
    frozen = runner.frozen_progression()
    assert all(a["state_progression"][str(i)]["sha256"] == frozen[str(i)] for i in range(4))
    assert {k: v["sha256"] for k, v in a["state_progression"].items()} == {k: v["sha256"] for k, v in b["state_progression"].items()}
    link = json.loads((MODE_B / "monitoring_link.json").read_text())
    assert link["trace"]["verified"] and link["trace"]["rounds_traced"] == 10 and link["monitoring_sessions_executed"] == 1 and link["buffer_reused_for_rounds"] == 10 and all(link["states_equal_mode_a"].values())
    assert link["parity"]["dataset_identical_to_canonical"] is True and link["label"].startswith("LIVE-MONITORED SIMULATED ECG")


def test_state_artifacts_match_recorded_digests_and_tampering_is_detected(tmp_path):
    r = _report(MODE_A)
    for i in range(11):
        runner.load_state(MODE_A, i, r["state_progression"][str(i)]["sha256"])
    with pytest.raises(runner.Fl10Error, match="STATE_ARTIFACT_DIGEST_MISMATCH"):
        runner.load_state(MODE_A, 5, r["state_progression"]["6"]["sha256"])


def test_ten_round_contract_does_not_change_the_three_round_product_default():
    from product.federation.execution_binding import BindingViolation, check_public_request

    with pytest.raises((BindingViolation, ValueError)):
        check_public_request(run_type="LIVE_RUN", algorithm="FEDAVG", secagg_mode="PLAIN", planned_rounds=10, scenario_id="FL_SINGLE_RUN")
    check_public_request(run_type="LIVE_RUN", algorithm="FEDAVG", secagg_mode="PLAIN", planned_rounds=3, scenario_id="FL_SINGLE_RUN")
