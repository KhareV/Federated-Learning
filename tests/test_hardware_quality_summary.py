# ruff: noqa: E501
"""A pretrained-V2 hardware run trains on every COMPLETE window whatever its grade. Every quality summary must therefore separate genuinely VALID windows from lower-quality windows ACCEPTED for experimental
training, and a run recorded before grades were kept per window must say so instead of showing an invented number."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from capstone_persistence.store import CapstoneSqliteStore
from product.hardware_demo_session import LONG_DEMO_COLLECTION, documents_for, owner_session_id
from product.hardware_telemetry import HardwareSessions
from studio import hardware_v2
from studio.hardware_demo import HardwareDemoService
from studio.service import StudioService
from studio.specs import _quality_label, _quality_series


class Source:
    collection_name = "records_*"

    def read_collection(self, name):
        return [d | {"_nhm_collection": name} for d in documents_for(name)]


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("quality")
    store = CapstoneSqliteStore(tmp / "p.sqlite3")
    sessions = HardwareSessions(store, Source())
    sessions.demo_collection = LONG_DEMO_COLLECTION
    sid = owner_session_id("user-a", LONG_DEMO_COLLECTION)
    assert sessions.list("user-a")[0]["session_id"] == sid
    demo = HardwareDemoService(store, tmp / "runs")
    records = demo._records("user-a", [sid])
    ctx = demo.prepare("user-a", session_ids=[sid], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=7, initialisation="MODEL_V2_FINAL")
    return SimpleNamespace(sid=sid, records=records, ctx=ctx)


def test_the_preview_separates_valid_windows_from_lower_quality_windows_that_would_be_accepted(prepared):
    info = hardware_v2.preview(prepared.records, [prepared.sid])
    [s] = info["sessions"]
    assert s["usable"] == s["valid"] + s["below_valid"] == 93                       # every complete window is accepted ...
    assert s["below_valid"] == 14 and s["valid"] == 79                              # ... but only 79 of them are graded VALID
    assert info["valid_windows"] == 79 and info["below_valid_windows"] == 14
    assert s["train_valid"] + s["train_below_valid"] == s["train"] and s["holdout_valid"] + s["holdout_below_valid"] == s["holdout"]
    assert info["train_below_valid"] + info["holdout_below_valid"] <= 14             # the purge between train and holdout can drop a few


def test_the_recorded_clients_counts_no_longer_call_every_window_valid(prepared):
    mine = prepared.ctx["datasets"][0]
    c = mine.counts
    assert c["windows_emitted"] == c["trainable"] == len(mine.labels)
    assert c["VALID"] + c["DEGRADED"] + c["UNUSABLE"] == c["trainable"]              # grades add up to the windows used
    assert c["accepted_below_valid"] == c["DEGRADED"] + c["UNUSABLE"] and c["accepted_below_valid"] > 0 and c["VALID"] < c["trainable"]
    assert c["excluded_windows"] == 0 and c["quality_recorded"] is True               # nothing is excluded: below-VALID windows are accepted, not dropped
    for holdout in prepared.ctx["holdout"]:
        assert holdout.counts["VALID"] + holdout.counts["accepted_below_valid"] == holdout.counts["trainable"]


def test_the_run_record_keeps_the_grades_per_client_run_and_window(prepared):
    dataset = prepared.ctx["dataset"]
    mine = dataset["clients"][hardware_v2.HARDWARE_CLIENT_ID]
    assert sum(mine["quality_counts"].values()) == mine["samples"] and mine["accepted_below_valid"] == mine["samples"] - mine["quality_counts"]["VALID"]
    assert dataset["training_quality"] == mine["quality_counts"] and dataset["training_windows_below_valid"] == mine["accepted_below_valid"]
    assert set(dataset["holdout_quality"]) == {"VALID", "DEGRADED", "UNUSABLE"}
    assert all("ecg_quality" in w for w in dataset["window_manifest"]) and {w["ecg_quality"] for w in dataset["window_manifest"]} <= {"VALID", "DEGRADED", "UNUSABLE"}
    assert all("quality_counts" not in dataset["clients"][c] for c in dataset["clients"] if c != hardware_v2.HARDWARE_CLIENT_ID)      # synthetic peers have no grades to report


def _service(tmp_path: Path, clients: dict) -> tuple[StudioService, str]:
    federation = MagicMock()
    federation.active_live_run.return_value = False
    service = StudioService(root=tmp_path / "studio", federation=federation, inference_factory=None, other_run_active=lambda: False)
    run_id = "HDFLRUN-QUALITY00001"
    directory = tmp_path / "hw" / run_id
    directory.mkdir(parents=True)
    (directory / "dataset.json").write_text(json.dumps({"clients": clients}))
    service.hardware = SimpleNamespace(demo=SimpleNamespace(root=tmp_path / "hw"))
    return service, run_id


PEER = {"samples": 90, "kind": "SYNTHETIC_PEER", "session_id": "S", "label_counts": {"0": 60, "1": 30}, "feature_sha256": "x"}


def test_the_cohort_and_the_run_summary_report_valid_and_accepted_below_valid_separately(tmp_path):
    mine = {"samples": 73, "kind": "RECORDED", "session_id": "HW", "label_counts": {"0": 37, "1": 36}, "feature_sha256": "y", "quality_counts": {"VALID": 60, "DEGRADED": 5, "UNUSABLE": 8}, "accepted_below_valid": 13}
    service, run_id = _service(tmp_path, {"RECORDED_DEMO_CLIENT_00": mine, "SIM_FL_SITE_01": PEER})
    summary = service._recorded_quality(run_id)
    assert summary == {"recorded": True, "windows": 73, "VALID": 60, "DEGRADED": 5, "UNUSABLE": 8, "accepted_below_valid": 13}
    cohort = {c["client_id"]: c["counts"] for c in service._hardware_cohort(run_id)}
    assert cohort["RECORDED_DEMO_CLIENT_00"]["VALID"] == 60 and cohort["RECORDED_DEMO_CLIENT_00"]["trainable"] == 73 and cohort["RECORDED_DEMO_CLIENT_00"]["excluded_windows"] == 0
    assert cohort["SIM_FL_SITE_01"]["VALID"] == 90 and cohort["SIM_FL_SITE_01"]["accepted_below_valid"] == 0            # peers hold only VALID complete windows


def test_a_run_recorded_before_grades_were_kept_says_so_instead_of_inventing_numbers(tmp_path):
    old = {"samples": 73, "kind": "RECORDED", "session_id": "HW", "label_counts": {"0": 37, "1": 36}, "feature_sha256": "y"}
    service, run_id = _service(tmp_path, {"RECORDED_DEMO_CLIENT_00": old, "SIM_FL_SITE_01": PEER})
    assert service._recorded_quality(run_id) == {"recorded": False, "windows": 73, "VALID": None, "DEGRADED": None, "UNUSABLE": None, "accepted_below_valid": None}
    counts = service._hardware_cohort(run_id)[0]["counts"]
    assert counts["VALID"] is None and counts["accepted_below_valid"] is None and counts["quality_recorded"] is False and counts["trainable"] == 73   # the number of windows used is still known


def test_the_composition_figure_names_the_accepted_windows_and_never_calls_them_excluded():
    hardware = [{"trainable": 73, "VALID": 60, "DEGRADED": 5, "UNUSABLE": 8, "accepted_below_valid": 13}, {"trainable": 90, "VALID": 90, "DEGRADED": 0, "UNUSABLE": 0, "accepted_below_valid": 0}]
    names = [s["name"] for s in _quality_series(hardware)]
    assert names == ["VALID (trained)", "accepted below VALID (trained, experimental)"] and _quality_series(hardware)[0]["values"] == [60, 90] and _quality_series(hardware)[1]["values"] == [13, 0]
    assert "excluded" not in " ".join(names) and "accepted below VALID" in _quality_label("Training", hardware)
    older = [{"trainable": 73, "VALID": None, "DEGRADED": None, "UNUSABLE": None, "accepted_below_valid": None}]
    assert _quality_series(older)[0]["values"] == [None]                                                                  # a gap, not a number


def test_synthetic_cohort_composition_keeps_its_original_eligible_vs_excluded_meaning():
    cohort = [{"trainable": 91, "DEGRADED": 2, "UNUSABLE": 0, "VALID": 93}, {"trainable": 89, "DEGRADED": 0, "UNUSABLE": 4, "VALID": 93}]
    assert [s["name"] for s in _quality_series(cohort)] == ["quality-eligible", "excluded (degraded)", "excluded (unusable)"]
    assert _quality_label("Training", cohort) == "Training quality: eligible vs excluded"


# ---- label provenance of a History-derived run --------------------------------------------------------------------------------------------------------------------------------

def _bundle(tmp_path: Path, link: dict | None, mode: str):
    from studio.bundle import build_live_bundle

    run_dir = tmp_path / ("hist" if link and link.get("signal_session") else "live" if link else "plain")
    (run_dir).mkdir(parents=True)
    if link is not None:
        (run_dir / "monitoring_link.json").write_text(json.dumps(link))
    observer = SimpleNamespace(records=lambda rid: [], run_dir=lambda rid: tmp_path, paired=lambda rid: None, revision=lambda rid: 0)
    return build_live_bundle(run_id="FL10RUN-X", run_length=3, run_dir=run_dir, observer=observer, mode=mode, engine="FL10_10R", status="RUNNING")


def test_a_history_derived_run_is_not_called_live_monitored_and_names_its_assigned_labels(tmp_path):
    b = _bundle(tmp_path, {"monitored_site": 2, "signal_session": {"session_id": "SES-1"}, "monitoring_sessions_executed": 0}, "B")
    assert b["live_label"].startswith("HISTORY MONITORING SESSION SIGNAL") and "NOT LIVE-MONITORED" in b["live_label"] and "LIVE-MONITORED SIMULATED ECG" not in b["live_label"]
    assert "SITE_02 TRAINS ON YOUR HISTORY SESSION" in b["synthetic_label"] and "SYNTHETIC-ASSIGNED LABELS" in b["synthetic_label"] and "OTHER SEVEN CLIENTS USE EVENT-WINDOW LABELS" in b["synthetic_label"]


def test_a_genuinely_live_monitored_site_and_a_plain_run_keep_their_labels(tmp_path):
    live = _bundle(tmp_path, {"monitored_site": 0, "signal_session": None, "monitoring_sessions_executed": 1}, "B")
    assert live["live_label"] == "LIVE-MONITORED SIMULATED ECG — NOT A REAL PHYSIOLOGICAL PATIENT" and "HISTORY" not in live["synthetic_label"] and "ASSIGNED" not in live["synthetic_label"]
    plain = _bundle(tmp_path, None, "A")
    assert plain["live_label"] is None and "ASSIGNED" not in plain["synthetic_label"] and plain["monitoring_link"] is None
