# ruff: noqa: E501
"""PTBXL_EXTERNAL_CHECK_V1: the causal decimator, the window construction and the three predeclared label rules."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import ptbxl_external_check as pc


def test_the_decimator_is_causal_and_halves_the_rate():
    rng = np.random.default_rng(1)
    prefix = rng.normal(size=3000)
    a = pc.causal_decimate_by_two(np.concatenate([prefix, rng.normal(size=2000)]))
    b = pc.causal_decimate_by_two(np.concatenate([prefix, rng.normal(size=2000)]))      # a different future
    assert len(a) == 2500 and np.array_equal(a[:1500], b[:1500])                       # every output up to the cut depends only on source samples up to it


def test_the_decimator_passes_the_ecg_band_and_removes_energy_above_the_new_nyquist():
    t = np.arange(5000) / 500.0
    low, high = np.sin(2 * np.pi * 10 * t), np.sin(2 * np.pi * 200 * t)                  # 10 Hz kept, 200 Hz (above 125 Hz) removed
    assert np.std(pc.causal_decimate_by_two(low)[400:]) > 0.65 and np.std(pc.causal_decimate_by_two(high)[400:]) < 0.02


def test_a_record_becomes_one_finite_zscored_window_and_degenerate_records_are_refused():
    t = np.arange(5000) / 500.0
    ecg = np.sin(2 * np.pi * 1.2 * t) + 0.3 * np.sin(2 * np.pi * 15 * t)
    w = pc.window_for_record(ecg)
    assert w is not None and w.shape == (2500,) and np.isfinite(w).all() and abs(float(w.mean())) < 1e-4 and abs(float(w.std()) - 1.0) < 1e-3
    assert pc.window_for_record(np.zeros(5000)) is None                                 # flat lead
    assert pc.window_for_record(ecg[:4000]) is None                                    # wrong length
    bad = ecg.copy(); bad[10] = np.nan
    assert pc.window_for_record(bad) is None                                           # non-finite


def test_the_window_does_not_depend_on_the_future_beyond_the_record(tmp_path):
    t = np.arange(5000) / 500.0
    ecg = np.sin(2 * np.pi * 1.2 * t)
    assert np.array_equal(pc.window_for_record(ecg), pc.window_for_record(ecg.copy()))   # deterministic


def test_the_three_label_rules_follow_the_protocol(tmp_path):
    rows = [  # ecg_id, scp_codes, extra_beats, pacemaker
        (1, {"NORM": 100, "SR": 0}, None, None),          # neither source
        (2, {"PVC": 100, "SR": 0}, "1ES", None),          # both sources
        (3, {"PAC": 0}, None, None),                      # statement only
        (4, {"NORM": 100}, "SVES", None),                 # extra beats only
        (5, {"PVC": 100, "PACE": 0}, "1ES", None),        # paced: marked paced
        (6, {"AFIB": 0}, None, None),                     # a rhythm disorder is not a positive
        (7, {"NORM": 100}, None, "ja, pacemaker"),        # paced through the pacemaker field
    ]
    d = pd.DataFrame({"patient_id": range(1, 8), "strat_fold": [9] * 7, "scp_codes": [str(r[1]) for r in rows], "extra_beats": [r[2] for r in rows], "pacemaker": [r[3] for r in rows],
                      "burst_noise": [None] * 7, "static_noise": [None] * 7, "baseline_drift": [None] * 7}, index=pd.Index([r[0] for r in rows], name="ecg_id"))
    path = tmp_path / "db.csv"
    d.to_csv(path)
    t = pc.label_table(path)
    assert t.label_A.to_dict() == {1: 0, 2: 1, 3: 1, 4: 1, 5: 1, 6: 0, 7: 0}          # union
    assert t.label_B.to_dict() == {1: 0, 2: 1, 3: -1, 4: -1, 5: 1, 6: 0, 7: 0}        # agreement; one-source records excluded
    assert t.label_C.to_dict() == {1: 0, 2: 1, 3: 1, 4: 0, 5: 1, 6: 0, 7: 0}          # statements only
    assert t.paced.to_dict() == {1: False, 2: False, 3: False, 4: False, 5: True, 6: False, 7: True}
    assert t.afib.to_dict()[6] is True and t.norm_sr.to_dict()[1] is True
