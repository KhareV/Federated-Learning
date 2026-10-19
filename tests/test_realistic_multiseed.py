# ruff: noqa: E501
"""The multi-seed validation helpers: metrics, prevalence-aware lift, deterministic bootstrap intervals, paired differences, and that no two cohorts share a participant's seed."""

from __future__ import annotations

import numpy as np

from scripts import realistic_multiseed as ms


def test_cell_metrics_report_lift_over_the_prevalence_chance_level():
    y = np.array([1] * 20 + [0] * 80)
    perfect = np.where(y == 1, 4.0, -4.0)
    m = ms.cell_metrics(perfect, y)
    assert m["AUROC"] == 1.0 and m["AUPRC"] == 1.0 and m["F1"] == 1.0 and abs(m["prevalence"] - 0.2) < 1e-12 and abs(m["lift"] - 5.0) < 1e-12      # perfect ranking = 1 / prevalence
    rng = np.random.default_rng(0)
    chance = ms.cell_metrics(rng.normal(size=4000), rng.random(4000) < 0.2)
    assert abs(chance["AUROC"] - 0.5) < 0.05 and abs(chance["lift"] - 1.0) < 0.15                                                                       # no skill = lift of about 1, whatever the prevalence


def test_the_same_ranking_has_a_higher_raw_auprc_at_higher_prevalence_but_a_comparable_lift():
    rng = np.random.default_rng(1)

    def draw(prevalence):
        y = rng.random(6000) < prevalence
        return ms.cell_metrics(np.where(y, rng.normal(1.2, 1, y.size), rng.normal(0, 1, y.size)), y)

    low, high = draw(0.10), draw(0.20)
    assert high["AUPRC"] > low["AUPRC"] + 0.1                                      # raw AUPRC mostly tracks the base rate ...
    assert abs(high["AUROC"] - low["AUROC"]) < 0.03                               # ... AUROC does not, and lift removes the base rate from AUPRC
    assert abs(high["lift"] - low["lift"]) < 0.8 * abs(high["AUPRC"] - low["AUPRC"]) / low["prevalence"]


def test_bootstrap_intervals_are_deterministic_and_bracket_the_mean():
    grid = np.array([[0.80, 0.84, 0.82], [0.78, 0.86, 0.81], [0.83, 0.85, 0.80], [0.79, 0.88, 0.84]])
    a, b = ms.bootstrap_ci(grid), ms.bootstrap_ci(grid)
    assert a == b and a[1] <= a[0] <= a[2] and abs(a[0] - grid.mean()) < 1e-12
    wide = ms.bootstrap_ci(grid + np.array([[0.0, 0.2, -0.2]] * 4))
    assert (wide[2] - wide[1]) > (a[2] - a[1])                                  # more variation between cohorts, wider interval


def test_group_bootstrap_delta_detects_a_change_and_is_zero_for_identical_scores():
    rng = np.random.default_rng(2)
    groups = np.repeat([f"P{i}" for i in range(8)], 120)
    y = (rng.random(groups.size) < 0.3).astype(int)
    base = np.where(y == 1, rng.normal(0.8, 1, y.size), rng.normal(0, 1, y.size))
    worse = base + rng.normal(0, 2.5, y.size)
    same = ms.group_bootstrap_delta(y, groups, base, base.copy())
    assert same["delta_AUROC"] == 0.0 and same["delta_AUROC_lo"] == 0.0 and same["groups"] == 8
    down = ms.group_bootstrap_delta(y, groups, base, worse)
    assert down["delta_AUROC"] < -0.03 and down["delta_AUROC_hi"] < 0.02 and down["valid_replicates"] > 1500                           # a real degradation is visible, with its interval
    assert ms.group_bootstrap_delta(y, groups, base, worse) == down                                                                  # deterministic


def _cells(values: dict[tuple[str, int, int], dict[str, float]]):
    return [{"model": m, "train_seed": k, "holdout": h, **v} for (m, k, h), v in values.items()]


def test_summary_and_paired_differences_are_computed_over_the_cohort_grid():
    values = {}
    for k in range(3):
        for h in range(4):
            values[("V2 R0", k, h)] = {"AUROC": 0.90 + 0.01 * k, "AUPRC": 0.6, "lift": 4.0, "F1": 0.7}
            values[("Beat-timing logistic", k, h)] = {"AUROC": 0.85, "AUPRC": 0.6, "lift": 3.0, "F1": 0.1}
    cells = _cells(values)
    seeds, holds = [0, 1, 2], [0, 1, 2, 3]
    summary = ms.summarise(cells, seeds, holds)
    auroc = summary["V2 R0"]["AUROC"]
    assert abs(auroc["mean"] - 0.91) < 1e-9 and auroc["ci95"][0] <= 0.91 <= auroc["ci95"][1] and abs(auroc["sd_over_training_cohorts"] - np.std([0.90, 0.91, 0.92])) < 1e-9
    assert auroc["min_cell"] == 0.90 and auroc["max_cell"] == 0.92 and "Federated final" not in summary                   # models without cells are simply absent
    paired = ms.paired_differences(cells, seeds, holds, "V2 R0", "Beat-timing logistic")
    assert abs(paired["AUROC"]["mean_difference"] - 0.06) < 1e-9 and paired["AUROC"]["fraction_of_cells_a_better"] == 1.0
    assert paired["AUPRC"]["mean_difference"] == 0.0 and paired["AUPRC"]["fraction_of_cells_a_better"] == 0.0 and abs(paired["lift"]["mean_difference"] - 1.0) < 1e-9


def test_no_two_cohorts_share_a_participants_seed():
    from simulation import fl_cohort_realistic_v2 as c

    evaluation = {ms.eval_seed(h, r, s) for h in range(8) for r in range(2) for s in range(8)}
    training = {ms.train_seed(k, i) for k in range(8) for i in range(8)}
    assert len(evaluation) == 8 * 2 * 8 and len(training) == 8 * 8                       # every participant of every cohort has its own seed (the earlier 100-apart layout overlapped)
    assert not (evaluation & training)
    assert [ms.eval_seed(0, r, s) for r in range(2) for s in range(8)] == [p.seed for p in c.eval_profiles()]       # h = 0 is exactly the pinned evaluation cohort
    assert [ms.train_seed(0, i) for i in range(8)] == [p.seed for p in c.train_profiles()]                           # k = 0 is exactly the pinned training cohort
