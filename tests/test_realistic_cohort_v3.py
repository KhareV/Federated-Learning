# ruff: noqa: E501
"""WEARABLE_SIM_REALISTIC_ECG_V3 and its cohort: the realistic generator with RECORDED NSTDB noise. Same clean physiology as V2, real noise at NSTDB's levels, disjoint noise regions, the unchanged pipeline, disjointness
from every earlier cohort, drift against the committed manifest."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from simulation import fl_cohort_realistic_v2 as C2
from simulation import fl_cohort_realistic_v3 as C
from simulation import realistic_ecg_v2 as G2
from simulation import realistic_ecg_v3 as G

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/realistic/realistic_cohort_manifest_v3.json"
N = C.DURATION_S * 360


def test_the_clean_physiology_and_the_true_ectopic_beats_are_exactly_those_of_v2():
    a, _, _ = G.render(20272001, 64, 480, 1.0, evaluation=False)
    b, _ = G2.render(20272001, 64, 480, 1.0)
    assert a.beats == b.beats and a.true_ectopic == b.true_ectopic                      # only the noise differs


def test_the_render_is_deterministic_and_seed_dependent():
    a, _, ia = G.render(1, 70, 60, 2.0, evaluation=False)
    b, _, ib = G.render(1, 70, 60, 2.0, evaluation=False)
    c, _, _ = G.render(2, 70, 60, 2.0, evaluation=False)
    assert np.array_equal(a.mv, b.mv) and a.annotations == b.annotations and ia == ib
    assert not np.array_equal(a.mv, c.mv)


def test_the_noise_is_the_recorded_nstdb_noise_and_the_files_are_checked_against_their_official_digests(tmp_path, monkeypatch):
    rec = G.noise_records()
    assert set(rec) == {"bw", "em", "ma"} and all(v.shape == (650_000, 2) for v in rec.values())
    assert G.noise_manifest()["em"] == "4f9416a04b2bed98081ee3118c1282f9e35321bfd5da96ce48056a3fe147358d"
    bad = tmp_path / "files.csv"
    bad.write_text(G.NSTDB_FILES.read_text().replace("4f9416a04b2bed98081ee3118c1282f9e35321bfd5da96ce48056a3fe147358d", "0" * 64))
    monkeypatch.setattr(G, "NSTDB_FILES", bad)
    G.noise_records.cache_clear()
    try:
        with pytest.raises(G.NoiseDataError, match="NSTDB_FILE_DIGEST_MISMATCH"):
            G.noise_records()
    finally:
        monkeypatch.undo()
        G.noise_records.cache_clear()


def test_the_composite_noise_hits_the_participants_snr_level():
    rendered, _, info = G.render(20272009, 70, 120, 1.0, evaluation=True)
    assert info.snr_db in G.SNR_LEVELS_DB
    assert abs(info.noise_rms_mv - info.signal_rms_mv / 10 ** (info.snr_db / 20)) < 1e-12
    unit, _, _ = G._unit_segment(G.noise_records()["em"], np.random.default_rng(3), 36000, G.EVAL_REGION)
    assert abs(float(np.sqrt(np.mean(unit**2))) - 1.0) < 1e-9 and abs(float(unit.mean())) < 1e-9


def test_training_and_evaluation_participants_never_share_a_recorded_noise_segment():
    pinned = json.loads(MANIFEST.read_text())
    for e in pinned["train"]["participants"]:
        assert all(s + N <= G.TRAIN_REGION[1] and s >= G.TRAIN_REGION[0] for s in e["noise_segment_starts"])
    for e in pinned["eval"]["participants"]:
        assert all(s >= G.EVAL_REGION[0] and s + N <= G.EVAL_REGION[1] for s in e["noise_segment_starts"])


def test_labels_come_from_annotations_not_from_the_hidden_truth():
    profile = C.eval_profile(0)
    result, _, _ = C.rendered(profile)
    assert result.annotations != tuple(sorted(result.true_ectopic))
    provider = C.RealisticEventLabelProvider(profile)
    edges = [round((t + 1.0) * 1e6) for t in result.annotations[:3]]
    assert provider.labels_for_windows(edges).tolist() == [1.0, 1.0, 1.0]


@pytest.fixture(scope="module")
def cohorts():
    return [C.build_dataset(p) for p in C.train_profiles()], [C.build_dataset(p) for p in C.eval_profiles()]


def test_the_cohort_goes_through_the_unchanged_pipeline_with_the_original_site_conditions(cohorts):
    from simulation import fl_cohort_v1 as original

    train, evaluation = cohorts
    assert len(train) == 8 and len(evaluation) == 16
    for index, dataset in enumerate(train):
        assert C.train_profile(index).coverage == original.client_profile(index).coverage
        assert 70 <= len(dataset.labels) <= 93 and float(dataset.labels.sum()) >= 1        # the quality step may drop a few more windows than for the invented noise
    assert sum(len(d.labels) for d in evaluation) > 1300
    assert 0.05 < float(np.concatenate([d.labels for d in evaluation]).mean()) < 0.30
    assert sum(float(d.labels.sum()) > 0 for d in evaluation) >= 10                       # most evaluation participants have both classes (some people simply have no ectopy)


def test_the_cohort_is_disjoint_from_every_earlier_cohort_including_v2(cohorts):
    from fl10 import holdout as fl10_holdout
    from simulation.fl_cohort_v1 import cohort_profiles
    from studio import g1_cohort

    earlier = {p.participant_id for p in cohort_profiles()} | {p.participant_id for p in fl10_holdout.profiles()} | {p.participant_id for p in g1_cohort.profiles()} | {p.participant_id for p in C2.train_profiles()} | {p.participant_id for p in C2.eval_profiles()}
    train_ids, eval_ids = {p.participant_id for p in C.train_profiles()}, {p.participant_id for p in C.eval_profiles()}
    assert not (earlier & (train_ids | eval_ids)) and not (train_ids & eval_ids)
    train, evaluation = cohorts
    assert not ({w.tobytes() for d in train for w in d.inputs} & {w.tobytes() for d in evaluation for w in d.inputs})
    v2_windows = {w.tobytes() for p in C2.eval_profiles() for w in C2.build_dataset(p).inputs}
    assert not (v2_windows & {w.tobytes() for d in evaluation for w in d.inputs})


def test_the_cohort_matches_the_committed_manifest(cohorts):
    pinned = json.loads(MANIFEST.read_text())
    assert "RECORDED noise" in pinned["pin_note"] and "looked at ONCE" in pinned["pin_note"] and pinned["eval"]["generator_id"] == G.GENERATOR_ID
    assert pinned["train"]["noise_source"]["record_sha256"] == G.noise_manifest()
    for tag, datasets in (("train", cohorts[0]), ("eval", cohorts[1])):
        assert [e["dataset_sha256"] for e in pinned[tag]["participants"]] == [d.dataset_sha256 for d in datasets]


def test_the_task_is_not_solved_by_a_trivial_amplitude_feature(cohorts):
    from scripts.realistic_multiseed import baseline_logits, cell_metrics, fit_baselines

    train, evaluation = cohorts
    x = np.concatenate([d.inputs for d in evaluation])
    y = np.concatenate([d.labels for d in evaluation]).astype(int)
    fits = fit_baselines(train)
    assert cell_metrics(baseline_logits(fits["Amplitude logistic"], x.reshape(len(x), -1)), y)["AUROC"] < 0.92
