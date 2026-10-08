# ruff: noqa: E501
"""NHM-FL10-001 evaluation integrity: protocol freeze, independence, metric correctness, uncertainty, chart/table consistency."""

from __future__ import annotations

import copy
import dataclasses
import json
import shutil
import subprocess
from functools import cache
from pathlib import Path

import numpy as np
import pytest

from fl10 import audit, charts, consistency, holdout, metrics, tables
from fl10 import evaluate as ev
from fl10.bundle import build_bundle
from fl10.constants import METHOD_COMMIT
from fl10.inventory import FIGURES, TABLES

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "reports/fl10/eval/modeA"
RUN = ROOT / "reports/fl10/runs/modeA"


@cache
def _holdout():
    return [holdout.build_dataset(p) for p in holdout.profiles()]


@cache
def _training():
    from federated.wearable_fl_runner_v1 import build_cohort

    return build_cohort()[1]


@cache
def _bundle():
    return build_bundle(RUN, EVAL)


def test_method_was_frozen_before_any_result_and_protocol_bytes_are_unchanged():
    first_run = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", "reports/fl10/runs"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()[-1]
    first_eval = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", "reports/fl10/eval"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()[-1]
    for later in (first_run, first_eval):
        assert subprocess.run(["git", "merge-base", "--is-ancestor", METHOD_COMMIT, later], cwd=ROOT).returncode == 0 and later != METHOD_COMMIT
    assert subprocess.run(["git", "cat-file", "-e", f"{METHOD_COMMIT}:reports/fl10/eval/modeA/evaluation_results.json"], cwd=ROOT, capture_output=True).returncode != 0
    assert ev.verify_method_freeze(METHOD_COMMIT)


def test_protocol_mutation_after_freeze_is_detected(monkeypatch):
    monkeypatch.setattr(ev, "sha256_file", lambda path: "0" * 64)
    with pytest.raises(ev.Fl10EvalError, match="PROTOCOL_CHANGED_AFTER_METHOD_FREEZE"):
        ev.verify_method_freeze(METHOD_COMMIT)


def test_threshold_is_fixed_and_no_calibration_in_protocol_and_results():
    protocol = json.loads((ROOT / ev.PROTOCOL).read_text())
    assert protocol["decision_threshold"] == {"rule": "positive iff raw sigmoid(logit) >= 0.5", "predeclared": True, "tuned": False, "calibrated": False, "CAL_V2": "NOT APPLIED"} and metrics.THRESHOLD == 0.5
    r = json.loads((EVAL / "evaluation_results.json").read_text())
    assert r["threshold"] == 0.5 and r["calibration"] == "NONE" and r["round_selection"].startswith("NONE")
    m = metrics.full_metrics(np.array([0, 1]), np.array([0.0, 0.0]))     # p == 0.5 is positive
    assert m["TP"] == 1 and m["FP"] == 1


def test_holdout_has_16_independent_participants_two_per_site_and_matches_manifest():
    protocol = json.loads((ROOT / ev.PROTOCOL).read_text())
    entries = ev.check_manifest(protocol, _holdout())
    assert len(entries) == 16 and {e["site_condition"] for e in entries} == {f"SIM_FL_SITE_0{i}" for i in range(8)}
    assert all(sum(1 for e in entries if e["site_condition"] == f"SIM_FL_SITE_0{i}") == 2 for i in range(8))
    sep = ev.separation(_holdout(), {"training": _training()})
    assert sep["training"]["participant_overlap"] == sep["training"]["session_overlap"] == sep["training"]["window_input_overlap"] == 0
    assert audit.seed_overlap([e["seed"] for e in entries], [p.seed for p in __import__("simulation.fl_cohort_v1", fromlist=["x"]).cohort_profiles()]) == []


def test_overlap_of_participant_session_seed_and_window_is_rejected():
    held = _holdout()
    train = _training()
    with pytest.raises(ev.Fl10EvalError, match="EVALUATION_OVERLAP"):
        ev.separation([dataclasses.replace(held[0], participant_id=train[0].participant_id), *held[1:]], {"t": train})
    with pytest.raises(ev.Fl10EvalError, match="EVALUATION_OVERLAP"):
        ev.separation([dataclasses.replace(held[0], session_id=train[0].session_id), *held[1:]], {"t": train})
    with pytest.raises(ev.Fl10EvalError, match="EVALUATION_OVERLAP"):                     # a training input accidentally entering the holdout
        ev.separation([dataclasses.replace(held[0], inputs=train[0].inputs), *held[1:]], {"t": train})
    assert audit.seed_overlap([20260927, 1], [20260927]) == [20260927]


def test_altered_label_or_changed_dataset_is_detected_and_missing_class_rejected():
    protocol = json.loads((ROOT / ev.PROTOCOL).read_text())
    flipped = [dataclasses.replace(_holdout()[0], labels=1 - _holdout()[0].labels), *_holdout()[1:]]
    with pytest.raises(ev.Fl10EvalError, match="HOLDOUT_DATASET_DIFFERS_FROM_MANIFEST"):
        ev.check_manifest(protocol, flipped)
    with pytest.raises(ev.Fl10EvalError, match="MISSING_CLASS_IN_HOLDOUT"):
        ev.require_both_classes([dataclasses.replace(d, labels=np.zeros_like(d.labels)) for d in _holdout()])


def test_undefined_denominators_are_none_with_reasons_never_zero():
    m = metrics.full_metrics(np.zeros(8, dtype=int), np.full(8, -3.0))
    for key in ("AUPRC", "AUROC", "recall", "F1", "precision", "MCC", "false_discovery_rate", "false_negative_rate"):
        assert m[key] is None and key in m["undefined"], key
    assert m["specificity"] == 1.0 and m["false_omission_rate"] == 0.0
    allpos = metrics.full_metrics(np.ones(5, dtype=int), np.full(5, 3.0))
    assert allpos["specificity"] is None and allpos["false_positive_rate"] is None and allpos["recall"] == 1.0


def test_metrics_agree_with_independent_implementations():
    from sklearn.metrics import brier_score_loss, matthews_corrcoef

    rng = np.random.default_rng(7)
    y = (rng.random(500) < 0.3).astype(int)
    z = rng.normal(size=500) + 1.3 * y - 0.4
    p = 1 / (1 + np.exp(-z))
    m = metrics.full_metrics(y, z)
    assert abs(m["MCC"] - matthews_corrcoef(y, (p >= 0.5).astype(int))) < 1e-12 and abs(m["Brier"] - brier_score_loss(y, p)) < 1e-12
    assert m["false_discovery_rate"] == pytest.approx(1 - m["precision"]) and m["false_omission_rate"] == pytest.approx(1 - m["negative_predictive_value"])
    assert sum(m["histogram"]["positive"]) == int(y.sum()) and sum(m["histogram"]["negative"]) == int((1 - y).sum())


def test_recorded_evaluation_reconciles_to_the_prediction_table():
    r = audit.reconcile(EVAL)
    assert r["windows"] == 1446 and r["all_ok"]
    assert audit.baseline_unchanged()["changed"] == []


def test_paired_bootstrap_is_deterministic_valid_and_counts_degenerate_replicates():
    ev_json = json.loads((EVAL / "evaluation_results.json").read_text())
    p = ev_json["paired"]
    assert p["replicates"] == 2000 and p["seed"] == 20261201 and p["clusters"] == 16 and "multiplicity" in p
    for name, v in p["metrics"].items():
        d = v["difference_interval"]
        assert d["valid_replicates"] + v["invalid_replicates"] == 2000, name
        if d["lower"] is not None:
            assert d["lower"] <= d["upper"], name
            assert d["lower"] - 1e-9 <= v["difference_point"] <= d["upper"] + 1e-9 or name in ("F1", "accuracy"), name
    rng = np.random.default_rng(0)
    owners = np.repeat(np.arange(4), 25)
    y = np.zeros(100, dtype=int)
    y[:25] = 1                                                         # only participant 0 has positives: many resamples have no positives
    z = rng.normal(size=100)
    b = metrics.paired_cluster_bootstrap(owners, y, z, z + 1, replicates=100, seed=1)
    assert b["metrics"]["AUPRC"]["invalid_replicates"] > 0 and b["metrics"]["AUPRC"]["difference_interval"]["valid_replicates"] + b["metrics"]["AUPRC"]["invalid_replicates"] == 100
    again = metrics.paired_cluster_bootstrap(owners, y, z, z + 1, replicates=100, seed=1)
    assert again == b


def test_candidate_digest_mismatch_and_foreign_evaluation_are_rejected(tmp_path):
    bad = tmp_path / "eval"
    shutil.copytree(EVAL, bad)
    doc = json.loads((bad / "evaluation_results.json").read_text())
    doc["final_candidate_digest"] = "0" * 64
    (bad / "evaluation_results.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="EVALUATION_DOES_NOT_BELONG_TO_RUN"):
        build_bundle(RUN, bad)


# ---------------------------------------------------------------- charts and tables
def test_inventory_is_complete_and_every_chart_matches_its_table():
    specs, tabs = charts.build_specs(_bundle()), tables.build_tables(_bundle())
    consistency.assert_specs_have_data(specs, [f[0] for f in FIGURES])
    assert sorted(tabs) == sorted(t[0] for t in TABLES) and len(specs) == 20 and len(tabs) == 12
    assert all(consistency.check_chart_table(specs, tabs).values())
    assert all(row[1] == "PASS" for row in tabs["FL10_TAB12"]["rows"])
    sums = specs["FL10_FIG13"]["views"][0]["total_check"]
    assert len(sums) == 10 and all(abs(s - 1) < 1e-12 for s in sums)


def test_chart_to_table_mismatch_and_missing_graph_source_are_detected():
    specs, tabs = copy.deepcopy(charts.build_specs(_bundle())), tables.build_tables(_bundle())
    specs["FL10_FIG04"]["views"][0]["series"][0]["y"][3] += 0.01
    with pytest.raises(consistency.ConsistencyError, match="CHART_TABLE_MISMATCH"):
        consistency.check_chart_table(specs, tabs)
    specs = copy.deepcopy(charts.build_specs(_bundle()))
    specs["FL10_FIG07"]["views"][0]["series"] = []
    with pytest.raises(consistency.ConsistencyError, match="EMPTY_GRAPH_VIEW"):
        consistency.assert_specs_have_data(specs, [f[0] for f in FIGURES])
    specs = copy.deepcopy(charts.build_specs(_bundle()))
    specs["FL10_FIG11"]["sources"] = []
    with pytest.raises(consistency.ConsistencyError, match="MISSING_GRAPH_SOURCE"):
        consistency.assert_specs_have_data(specs, [f[0] for f in FIGURES])


def test_exports_are_deterministic_complete_and_unrounded(tmp_path):
    from fl10.figures import export_all

    m1, m2 = export_all(_bundle(), tmp_path / "a"), export_all(_bundle(), tmp_path / "b")
    assert len(m1["figures"]) == 20 and len(m1["tables"]) == 12
    assert {k: {e: v["sha256"] for e, v in f.items() if "sha256" in v} for k, f in m1["tables"].items()} == {k: {e: v["sha256"] for e, v in f.items() if "sha256" in v} for k, f in m2["tables"].items()}
    assert {k: v["svg"]["sha256"] for k, v in m1["figures"].items()} == {k: v["svg"]["sha256"] for k, v in m2["figures"].items()}
    csv1 = (tmp_path / "a/tables/FL10_TAB01.csv").read_text().splitlines()
    assert len(csv1) == 12 and len(csv1[1].split(",")[1]) > 12      # full-precision AUPRC, not display-rounded
    committed = json.loads((ROOT / "reports/fl10/publication/modeA/export_manifest.json").read_text())
    assert {k: v["csv"]["sha256"] for k, v in committed["tables"].items()} == {k: v["csv"]["sha256"] for k, v in m1["tables"].items()}
