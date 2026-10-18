# ruff: noqa: E501
"""WEARABLE_SIM_REALISTIC_ECG_V2 and the realistic cohort: rhythm physiology of the ectopic beats, annotation-based labels, the unchanged pipeline, disjointness from every earlier cohort, drift against the pinned manifest."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from simulation import fl_cohort_realistic_v2 as C
from simulation import realistic_ecg_v2 as G

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/realistic/realistic_cohort_manifest_v2.json"


@pytest.fixture(scope="module")
def long_render():
    return G.render(seed=20271003, hr_bpm=72, duration_s=1800, burden_per_min=4.0, minimum_ectopic=3)


def _rr_context(beats):
    times = [b.time_s for b in beats]
    for i in range(2, len(beats) - 2):
        if beats[i].kind != "N" and beats[i - 1].kind == "N" and beats[i + 1].kind == "N" and beats[i - 2].kind == "N":
            yield beats[i].kind, times[i - 1] - times[i - 2], times[i] - times[i - 1], times[i + 1] - times[i]


def test_the_render_is_deterministic_and_seed_dependent():
    a, _ = G.render(1, 70, 60, 2.0)
    b, _ = G.render(1, 70, 60, 2.0)
    c, _ = G.render(2, 70, 60, 2.0)
    assert np.array_equal(a.mv, b.mv) and a.annotations == b.annotations
    assert not np.array_equal(a.mv, c.mv)


def test_a_ventricular_beat_is_premature_and_followed_by_a_compensatory_pause(long_render):
    rows = [r for r in _rr_context(long_render[0].beats) if r[0] == "V"]
    assert len(rows) >= 12
    premature = [coupling < 0.9 * before for _, before, coupling, _ in rows]
    compensatory = [abs((coupling + after) - 2 * before) < 0.25 * before for _, before, coupling, after in rows]
    assert sum(premature) / len(rows) > 0.9
    assert sum(compensatory) / len(rows) > 0.7


def test_a_supraventricular_beat_resets_the_sinus_node_without_a_full_compensatory_pause(long_render):
    rows = [r for r in _rr_context(long_render[0].beats) if r[0] == "S"]
    assert len(rows) >= 8
    assert sum(coupling < 0.9 * before for _, before, coupling, _ in rows) / len(rows) > 0.9
    assert float(np.median([(coupling + after) / before for _, before, coupling, after in rows])) < 1.85


def test_sinus_rhythm_varies_beat_to_beat(long_render):
    times = np.array([b.time_s for b in long_render[0].beats if b.kind == "N"])
    rr = np.diff(times)
    rr = rr[(rr > 0.5) & (rr < 1.3)]
    assert 0.02 < np.std(rr) / np.mean(rr) < 0.12      # the original generator had about 3 % jitter and nothing else


def test_labels_come_from_annotations_not_from_the_hidden_truth():
    profile = C.eval_profile(0)
    result, _ = C.rendered(profile)
    assert result.annotations != tuple(sorted(result.true_ectopic))        # annotators miss some beats and add false ones
    provider = C.RealisticEventLabelProvider(profile)
    edges = [round((t + 1.0) * 1e6) for t in result.annotations[:3]]
    assert provider.labels_for_windows(edges).tolist() == [1.0, 1.0, 1.0]
    assert provider.labels_for_windows([1_000_000]).tolist() == [0.0] or result.annotations[0] <= 1.0


def test_a_person_with_no_ectopy_has_only_negative_windows():
    quiet = [k for k in range(C.EVAL_COUNT) if C.eval_profile(k).burden_per_min == 0.0]
    assert quiet, "the evaluation cohort includes participants without ectopy"
    d = C.build_dataset(C.eval_profile(quiet[0]))
    assert len(d.labels) > 60 and float(d.labels.sum()) == 0.0


@pytest.fixture(scope="module")
def cohorts():
    return [C.build_dataset(p) for p in C.train_profiles()], [C.build_dataset(p) for p in C.eval_profiles()]


def test_the_cohort_goes_through_the_unchanged_pipeline_with_the_original_site_conditions(cohorts):
    train, evaluation = cohorts
    from simulation import fl_cohort_v1 as original

    assert len(train) == 8 and len(evaluation) == 16
    for index, dataset in enumerate(train):
        assert C.train_profile(index).coverage == original.client_profile(index).coverage
        assert 80 <= len(dataset.labels) <= 93
        assert float(dataset.labels.sum()) >= 1
    assert sum(len(d.labels) for d in evaluation) > 1300
    prevalence = float(np.concatenate([d.labels for d in evaluation]).mean())
    assert 0.08 < prevalence < 0.30


def test_the_cohorts_are_disjoint_from_every_earlier_cohort_and_from_each_other(cohorts):
    from fl10 import holdout as fl10_holdout
    from simulation.fl_cohort_v1 import cohort_profiles
    from studio import g1_cohort

    earlier = {p.participant_id for p in cohort_profiles()} | {p.participant_id for p in fl10_holdout.profiles()} | {p.participant_id for p in g1_cohort.profiles()}
    train_ids, eval_ids = {p.participant_id for p in C.train_profiles()}, {p.participant_id for p in C.eval_profiles()}
    assert not (earlier & (train_ids | eval_ids)) and not (train_ids & eval_ids)
    train, evaluation = cohorts
    assert not ({w.tobytes() for d in train for w in d.inputs} & {w.tobytes() for d in evaluation for w in d.inputs})


def test_the_evaluation_cohort_matches_the_manifest_pinned_before_any_model_scored_it(cohorts):
    pinned = json.loads(MANIFEST.read_text())
    assert "Revision B" in pinned["pin_note"] and pinned["eval"]["generator_id"] == G.GENERATOR_ID
    for tag, datasets in (("train", cohorts[0]), ("eval", cohorts[1])):
        entries = pinned[tag]["participants"]
        assert [e["dataset_sha256"] for e in entries] == [d.dataset_sha256 for d in datasets]


def test_the_task_is_no_longer_solved_by_a_trivial_amplitude_feature(cohorts):
    """On the original cohort peak-to-peak alone gave AUROC 0.868 and a 6-feature logistic regression 0.993. Guard against the realistic cohort drifting back to an easy task."""
    _, evaluation = cohorts
    x = np.concatenate([d.inputs.reshape(len(d.inputs), -1) for d in evaluation])
    y = np.concatenate([d.labels for d in evaluation]).astype(int)
    for feature in (x.max(1) - x.min(1), np.abs(x).max(1), (np.abs(x) > 3).mean(1)):
        auc = roc_auc_score(y, feature)
        assert max(auc, 1 - auc) < 0.80
