# ruff: noqa: E501
"""Independent verification of every round of a Studio federated run (scripts/verify_fl_rounds.py): a genuine run verifies completely, and tampering with a state, a prediction or a stored metric is caught."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_realistic_cohort_option import _service, _wait

from scripts import verify_fl_rounds as vf
from studio import v2_init


# ---- the metric implementations written for the verifier, against known answers ------------------------------------------------------------------------------------------------------

def test_the_independent_metrics_agree_with_scikit_learn_and_hand_computed_values():
    from sklearn.metrics import average_precision_score, roc_auc_score

    rng = np.random.default_rng(5)
    y = (rng.random(400) < 0.2).astype(int)
    z = rng.normal(size=400) + 2.0 * y
    z[:30] = np.round(z[:30], 1)                                              # ties
    p = vf.sigmoid(z)
    assert abs(vf.auroc(y, p) - roc_auc_score(y, p)) < 1e-12 and abs(vf.average_precision(y, p) - average_precision_score(y, p)) < 1e-12
    assert vf.auroc(np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.35, 0.8])) == 0.75                         # the classic textbook example
    assert abs(vf.average_precision(np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.35, 0.8])) - 0.8333333333333333) < 1e-12
    m = vf.recompute_metrics(np.array([1, 1, 0, 0, 1]), np.array([4.0, -4.0, 4.0, -4.0, 4.0]))
    assert (m["TP"], m["FP"], m["TN"], m["FN"]) == (2, 1, 1, 1) and abs(m["F1"] - 2 * 2 / (2 * 2 + 1 + 1)) < 1e-12 and abs(m["balanced_accuracy"] - ((2 / 3) + 0.5) / 2) < 1e-12


def test_an_undefined_metric_is_none_on_both_sides_never_zero_or_nan():
    y, z = np.array([1, 0]), np.array([-5.0, -5.0])                           # nothing is predicted positive: precision is undefined, recall is a real zero
    m = vf.recompute_metrics(y, z)
    assert m["precision"] is None and m["recall"] == 0.0 and m["specificity"] == 1.0 and m["F1"] == 0.0 and m["balanced_accuracy"] == 0.5
    one_class = vf.recompute_metrics(np.array([0, 0, 0]), np.array([1.0, -1.0, 0.5]))
    assert one_class["AUROC"] is None and one_class["AUPRC"] is None and one_class["recall"] is None
    assert vf.same(None, None, 1e-9) and not vf.same(0.0, None, 1e-9) and not vf.same(None, 0.5, 1e-9) and vf.same(0.5 + 1e-12, 0.5, 1e-9)       # an undefined metric stored as zero would be a defect


def test_the_aggregation_formula_is_the_example_weighted_mean_of_the_client_deltas():
    base = {"w": np.array([1.0, 2.0], dtype=np.float32), "count": np.array(7, dtype=np.int64)}
    updates = [(1, {"w": np.array([0.4, 0.0], dtype=np.float32), "count": np.array(1, dtype=np.int64)}), (3, {"w": np.array([0.0, 0.8], dtype=np.float32), "count": np.array(1, dtype=np.int64)})]
    out = vf.aggregate_independently(base, updates)
    assert np.allclose(out["w"], [1.0 + 0.4 / 4, 2.0 + 0.8 * 3 / 4]) and out["count"] == 7 and out["w"].dtype == np.float32     # integer buffers stay as they were


# ---- a genuine run ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def finished_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("verify")
    result: dict = {}

    async def go():
        service = _service(tmp)
        job = await service.runner10.create("user-a", "A", v2_init.INIT_V2_FINAL, 3, cohort="REALISTIC_NSTDB")
        await service.runner10.start("user-a", job.run_id)
        await _wait(job)
        assert job.status == "COMPLETED", job.failure
        result["dir"] = service.runner10.job_dir(job.run_id)
        result["run_id"] = job.run_id

    asyncio.run(go())
    return result


def test_every_round_of_a_genuine_run_verifies_including_a_bit_exact_rederivation_of_each_aggregation(finished_run):
    r = vf.verify_run(finished_run["dir"], rederive={1, 2, 3})
    assert r["ok"], r["failures"]
    assert sorted(r["rounds"]) == ["0", "1", "2", "3"] and r["cohort"] == "REALISTIC_NSTDB" and r["start"] == "pretrained MODEL_V2_FINAL"
    for k in ("1", "2", "3"):
        d = r["rounds"][k]["aggregation_rederivation"]
        assert d["bit_identical"] and d["clients"] == 8 and d["max_abs_difference"] == 0.0
        assert r["rounds"][k]["max_logit_difference_vs_recomputed_from_state"] < 1e-6
    assert all("generalisation_lane" in r["rounds"][k] for k in r["rounds"]) and r["g1_windows"] == 1446          # the unseen-cohort lane is verified too
    assert r["paired"]["intervals_recomputed"] is True and r["paired"]["endpoint"] > r["paired"]["comparator"]


# ---- negative controls: the verifier must fail when the stored values are wrong -----------------------------------------------------------------------------------------------------------

def _copy(finished_run, tmp_path):
    target = tmp_path / finished_run["run_id"]
    shutil.copytree(finished_run["dir"], target)
    return target


def test_an_altered_stored_metric_is_caught(finished_run, tmp_path):
    d = _copy(finished_run, tmp_path)
    path = d / "eval" / "R02" / "record.json"
    record = json.loads(path.read_text())
    record["metric_result"]["AUPRC"] += 1e-6
    path.write_text(json.dumps(record))
    r = vf.verify_run(d)
    assert not r["ok"] and any("eval R2: AUPRC" in f for f in r["failures"])


def test_an_altered_prediction_is_caught(finished_run, tmp_path):
    d = _copy(finished_run, tmp_path)
    path = d / "eval" / "R01" / "predictions.csv"
    lines = path.read_text().splitlines()
    head, first = lines[0], lines[1].split(",")
    first[-1] = repr(float(first[-1]) + 1e-3)
    path.write_text("\n".join([head, ",".join(first), *lines[2:]]) + "\n")
    r = vf.verify_run(d)
    assert not r["ok"] and any("eval R1" in f and ("SHA-256" in f or "logits" in f) for f in r["failures"])


def test_an_altered_state_is_caught(finished_run, tmp_path):
    d = _copy(finished_run, tmp_path)
    path = d / "run" / "states" / "R02.bin"
    data = bytearray(path.read_bytes())
    data[-5] ^= 0x01
    path.write_bytes(bytes(data))
    r = vf.verify_run(d)
    assert not r["ok"] and any(f.startswith("R2:") or "R2" in f for f in r["failures"])


def test_a_run_that_does_not_start_from_its_declared_model_is_caught(finished_run, tmp_path):
    d = _copy(finished_run, tmp_path)
    meta = json.loads((d / "meta.json").read_text())
    meta["init"] = v2_init.INIT_FRESH                                            # claims an untrained start, but R0 is the pretrained V2
    (d / "meta.json").write_text(json.dumps(meta))
    r = vf.verify_run(d)
    assert not r["ok"] and any("starting state" in f for f in r["failures"])


# ---- the comparison of the values the page shows with the stored records ----------------------------------------------------------------------------------------------------------------

def test_the_page_value_comparison_accepts_display_rounding_and_catches_a_different_number(tmp_path):
    from scripts.verify_hardware_connected_browser import _floats, ui_round_mismatches

    assert _floats("AUPRC: 0.8995 (full 0.899584) || 0.899584 latest evaluated R0") == [0.8995, 0.899584, 0.899584]
    run = tmp_path / "FL10RUN-X"
    (run / "eval" / "R01").mkdir(parents=True)
    (run / "eval" / "R01" / "record.json").write_text(json.dumps({"metric_result": {"AUPRC": 0.8995843, "AUROC": 0.9488971, "F1": None, "BCE": 0.10832, "accuracy": 0.9, "precision": 0.5, "recall": 0.6, "specificity": 0.7}}))
    step = {"ui_rounds": [{"button": "round-btn-R1", "AUPRC": "0.899584", "AUROC": "0.948897", "F1": "UNDEFINED", "BCE": "0.108320", "accuracy": "0.900000", "precision": "0.500000", "recall": "0.600000", "specificity": "0.700000"}]}
    assert ui_round_mismatches(step, run) == []                                                       # rounded to six places: fine; an undefined metric shown as such: fine
    step["ui_rounds"][0]["AUPRC"] = "0.899999"
    assert any("AUPRC" in p for p in ui_round_mismatches(step, run))                                   # a different number is caught
    assert ui_round_mismatches({"ui_rounds": [{"button": "round-btn-R2"}]}, run) == ["R2: no stored record"]
