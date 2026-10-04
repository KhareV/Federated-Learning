"""V2-FL-EVAL-001 pre-access method tests. Synthetic inputs only: no INTERNAL_TEST/INCART waveform
is read and no held-out FL prediction exists. Covers roster, adapters, shapes, raw-sigmoid and
threshold semantics, patient metrics, bootstrap multiplicity, paired draws, table alignment, the
one-shot guards, population expectations and a full synthetic end-to-end pass of the real roster."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

import evaluation.model_v2_fl_eval as ev
import scripts.compute_v2_fl_eval_stats as stats
from evaluation.bootstrap import generate_patient_draws
from evaluation.metrics import pooled_binary_metrics
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
FAMILY = yaml.safe_load((ROOT / ev.FAMILY_RELATIVE).read_text())
PROTOCOL = yaml.safe_load((ROOT / "configs/model_v2/fl_eval_protocol_v1.yaml").read_text())


def _rows(n: int, groups: list[str]) -> tuple[list[dict], np.ndarray]:
    rows = [{"example_id": f"E{i:05d}", "participant_group_id": groups[i % len(groups)],
             "record_id": f"R{i % len(groups)}"} for i in range(n)]
    labels = np.asarray([1 if (i % 3 == 0) else 0 for i in range(n)], dtype=np.int64)
    return rows, labels


def test_roster_is_exactly_the_20_frozen_checkpoints_with_exact_hashes() -> None:
    roster = ev.load_roster(ROOT)
    assert len(roster) == 20
    assert {(m["generation"], m["algorithm"]) for m in roster} == {
        ("V1", "FedAvg"), ("V1", "FedProx"), ("V2", "FedAvg"), ("V2", "FedProx")}
    assert sorted({m["condition"] for m in roster}) == ["combined", "feature", "iid", "label",
                                                        "quantity"]
    assert {m["mu"] for m in roster if m["generation"] == "V1" and m["algorithm"] == "FedProx"} == {
        0.01}
    assert {m["mu"] for m in roster if m["generation"] == "V2" and m["algorithm"] == "FedProx"} == {
        0.1}
    for m in roster:
        assert "round50" not in m["checkpoint"]
        assert hash_file(ROOT / m["checkpoint"]) == m["checkpoint_sha256"]
    lock = json.loads((ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json").read_text())
    assert set(lock["checkpoints"]) == {m["id"] for m in roster}


def test_v2_fedprox_label_is_the_selected_mu_0p1_alias() -> None:
    roster = {m["id"]: m for m in ev.load_roster(ROOT)}
    lock = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
    assert roster["V2_FEDPROX_LABEL"]["checkpoint_sha256"] == lock[
        "candidate_checkpoint_sha256"]["0.1"]["best_checkpoint_sha256"]
    v1 = json.loads((ROOT / "artifacts/FEDPROX_MU_V1.lock.json").read_text())
    assert roster["V1_FEDPROX_LABEL"]["checkpoint_sha256"] == v1["candidate_checkpoint_sha256"][
        "0.01"]


@pytest.mark.parametrize("bad", ["checkpoints/model_v2/v2_fl_001/FL_IID_MODEL_V2_V1_round50.pt",
                                 "checkpoints/MODEL_V2_FINAL.pt", "checkpoints/MODEL_V1.pt",
                                 "checkpoints/model_v2/v2_fl_003/candidates/"
                                 "FL_LABEL_FEDPROX_MODEL_V2_MU_0p01_best.pt"])
def test_excluded_checkpoints_are_rejected_by_the_roster_loader(bad: str, tmp_path: Path) -> None:
    (tmp_path / "configs/model_v2").mkdir(parents=True)
    family = json.loads(json.dumps(FAMILY))
    family["models"][0]["checkpoint"] = bad
    (tmp_path / ev.FAMILY_RELATIVE).write_text(yaml.safe_dump(family))
    with pytest.raises(ev.FamilyEvalError):
        ev.load_roster(tmp_path)


def test_roster_loader_rejects_wrong_count_and_hash_tamper(tmp_path: Path) -> None:
    (tmp_path / "configs/model_v2").mkdir(parents=True)
    short = json.loads(json.dumps(FAMILY))
    short["models"] = short["models"][:19]
    short["model_count"] = 19
    (tmp_path / ev.FAMILY_RELATIVE).write_text(yaml.safe_dump(short))
    with pytest.raises(ev.FamilyEvalError):
        ev.load_roster(tmp_path)
    tampered = json.loads(json.dumps(FAMILY))
    shutil.copytree(ROOT / "checkpoints", tmp_path / "checkpoints", dirs_exist_ok=True)
    tampered["models"][3]["checkpoint_sha256"] = "0" * 64
    (tmp_path / ev.FAMILY_RELATIVE).write_text(yaml.safe_dump(tampered))
    with pytest.raises(ev.FamilyEvalError):
        ev.load_roster(tmp_path)


def test_both_architectures_load_and_emit_one_raw_logit_per_window() -> None:
    rng = np.random.default_rng(3)
    inputs = ev.normalize_inputs(rng.normal(size=(7, 2500)) * 5 + 3)
    assert inputs.shape == (7, 1, 2500) and inputs.dtype == np.float32
    for generation in ("V1", "V2"):
        entry = next(m for m in ev.load_roster(ROOT) if m["generation"] == generation)
        logits = ev.infer_logits(ev.load_model(ROOT, entry), inputs, batch_size=3)
        assert logits.shape == (7,) and logits.dtype == np.float64 and np.isfinite(logits).all()
    with pytest.raises((ev.FamilyEvalError, ValueError)):
        ev.normalize_inputs(np.zeros((2, 100)))


def test_zscore_matches_the_frozen_formula_and_probability_is_raw_sigmoid() -> None:
    window = np.sin(np.linspace(0, 20, 2500)) * 3 + 1
    out = ev.normalize_inputs(window[None, :])[0, 0].astype(np.float64)
    expected = (window - window.mean()) / (window.std() + 1e-8)
    np.testing.assert_allclose(out, expected, atol=1e-5)
    logits = np.array([-3.0, 0.0, 2.5])
    np.testing.assert_allclose(ev.sigmoid_float32_consistent(logits), 1 / (1 + np.exp(-logits)),
                               atol=1e-15)
    assert ev.THRESHOLD == 0.5 and ev.THRESHOLD_ID == "FL_EVAL_RAW_THRESHOLD_0P5_V1"
    for forbidden in ("CAL_V1", "CAL_V2", "temperature"):
        assert forbidden not in (ROOT / "evaluation/model_v2_fl_eval.py").read_text()


def test_threshold_is_inclusive_at_exactly_one_half(tmp_path: Path) -> None:
    rows, labels = _rows(4, ["A", "B"])
    logits = np.array([0.0, -1e-9, 1e-9, 2.0])  # sigmoid(0) == 0.5 exactly
    path = tmp_path / "t.csv.gz"
    ev.write_prediction_table(path, {"id": "X"}, rows, labels, logits)
    table = ev.read_prediction_table(path)
    assert table["prediction"].tolist() == [1, 0, 1, 1]
    ev.validate_prediction_table(table, [r["example_id"] for r in rows])


def test_prediction_table_is_deterministic_and_alignment_is_enforced(tmp_path: Path) -> None:
    rows, labels = _rows(10, ["A", "B", "C"])
    logits = np.linspace(-2, 2, 10)
    first = ev.write_prediction_table(tmp_path / "a.csv.gz", {"id": "M"}, rows, labels, logits)
    second = ev.write_prediction_table(tmp_path / "b.csv.gz", {"id": "M"}, rows, labels, logits)
    assert first == second
    table = ev.read_prediction_table(tmp_path / "a.csv.gz")
    ids = [r["example_id"] for r in rows]
    ev.validate_prediction_table(table, ids)
    with pytest.raises(ev.FamilyEvalError):
        ev.validate_prediction_table(table, ids[::-1])
    with pytest.raises(ev.FamilyEvalError):
        ev.validate_prediction_table(table, ids[:-1])
    duplicated = dict(table)
    duplicated["example_id"] = table["example_id"].copy()
    duplicated["example_id"][1] = duplicated["example_id"][0]
    with pytest.raises(ev.FamilyEvalError):
        ev.validate_prediction_table(duplicated, ids)


def _table(n: int = 90, seed: int = 0) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    groups = np.asarray([f"G{i % 3}" for i in range(n)])
    labels = np.asarray([1 if (i % 3 == 0 or i % 7 == 0) else 0 for i in range(n)])
    probs = np.clip(rng.uniform(0, 1, n) * 0.4 + labels * 0.35, 0, 1)
    return {"example_id": np.asarray([f"E{i:04d}" for i in range(n)]),
            "participant_group_id": groups, "record_id": groups, "label": labels,
            "raw_logit": np.log(probs / (1 - probs + 1e-12) + 1e-12), "probability": probs,
            "prediction": (probs >= 0.5).astype(np.int64)}


def test_point_and_patient_metrics_including_undefined_values() -> None:
    table = _table()
    m = ev.point_metrics(table)
    assert m["TP"] + m["FP"] + m["TN"] + m["FN"] == m["windows"] == 90
    assert m["positives"] + m["negatives"] == 90 and m["contributing_patients"] == 3
    assert m["accuracy"] == pytest.approx((m["TP"] + m["TN"]) / 90)
    assert m["BCE"] > 0
    patient = {
        "participant_group_id": np.asarray(["P", "P", "Q", "Q"]),
        "label": np.asarray([1, 1, 0, 0]), "probability": np.asarray([0.9, 0.2, 0.1, 0.3]),
        "prediction": np.asarray([1, 0, 0, 0])}
    rows = {r["participant_group_id"]: r for r in ev.patient_metrics(patient)}
    assert rows["Q"]["AUPRC"] is None and rows["Q"]["AUROC"] is None  # no positives: undefined
    assert rows["P"]["AUROC"] is None and rows["P"]["AUPRC"] == 1.0  # single class: AUROC undef
    assert rows["Q"]["F1_at_0_5"] is None  # tp=fp=fn=0 -> F1 denominator zero -> undefined
    assert rows["P"]["F1_at_0_5"] == pytest.approx(2 / 3)


def test_bootstrap_preserves_multiplicity_and_uses_whole_patient_blocks() -> None:
    table = _table()
    groups = table["participant_group_id"]
    patients, draws = ev.shared_draws(groups)
    assert draws.shape == (2000, 3) and patients.tolist() == ["G0", "G1", "G2"]
    matrix = ev.replicate_matrix(table, draws)
    assert matrix.shape == (2000, 7)
    # manual check of replicate 0: concatenate sampled patient BLOCKS with repetition
    draw = draws[0]
    index = np.concatenate([np.flatnonzero(groups == patients[int(i)]) for i in draw])
    manual = pooled_binary_metrics(table["label"][index], table["probability"][index],
                                   table["prediction"][index], groups[index],
                                   allow_undefined=True)
    assert matrix[0, ev.REPLICATE_METRICS.index("AUPRC")] == pytest.approx(manual["AUPRC"])
    if len(set(draw.tolist())) < len(draw):  # a duplicated patient contributes twice
        assert len(index) > len(set(index.tolist()))
    assert draws.shape[1] == len(patients)  # slots per replicate == clusters (no set conversion)


def test_paired_delta_uses_identical_draws_and_is_zero_for_identical_models() -> None:
    table = _table()
    _, draws = ev.shared_draws(table["participant_group_id"])
    matrix = ev.replicate_matrix(table, draws)
    point = ev.point_metrics(table)
    delta = ev.paired_delta(point, matrix, point, matrix)
    for j, (name, row) in enumerate(delta.items()):
        assert row["point_delta"] == 0.0 and row["ci_lower_95"] == 0.0, name
        undefined = int(np.isnan(matrix[:, j]).sum())  # replicates where the metric is undefined
        assert row["ci_upper_95"] == 0.0 and row["invalid_replicates"] == undefined, name
    other = _table(seed=5)
    other_point = ev.point_metrics(other)
    shifted = ev.paired_delta(point, matrix, other_point, ev.replicate_matrix(other, draws))
    assert shifted["AUPRC"]["valid_replicates"] + shifted["AUPRC"]["invalid_replicates"] == 2000
    summary = ev.ci_summary(point, matrix)
    assert summary["AUPRC"]["valid_replicates"] + summary["AUPRC"]["invalid_replicates"] == 2000


def test_comparison_pairs_cover_the_predeclared_contrasts() -> None:
    ids = [m["id"] for m in ev.load_roster(ROOT)]
    pairs = ev.comparison_pairs(ids)
    names = {p[0] for p in pairs}
    assert "V2_FEDAVG_IID_minus_V1_FEDAVG_IID" in names           # primary architecture effect
    assert "V2_FEDPROX_IID_minus_V2_FEDAVG_IID" in names          # secondary method effect
    assert sum(1 for p in pairs if p[3] == "architecture_effect") == 10
    assert sum(1 for p in pairs if p[3] == "fedprox_effect") == 5
    assert sum(1 for p in pairs if p[3] == "condition_vs_iid") == 8
    with pytest.raises(ev.FamilyEvalError):
        ev.comparison_pairs(ids[:10])


def test_one_shot_guard_lifecycle_and_second_attempt_blocked(tmp_path: Path) -> None:
    for dataset in ev.GUARDS:
        assert ev.guard_state(tmp_path, dataset) == "NOT_STARTED"
        ev.begin_guard(tmp_path, dataset, {"git_head": "x"})
        assert ev.guard_state(tmp_path, dataset) == "RUN_STARTED"
        with pytest.raises(ev.FamilyEvalError, match="INTERRUPTED"):  # no reset after start
            ev.begin_guard(tmp_path, dataset, {})
        ev.complete_guard(tmp_path, dataset, {"models": 20})
        assert ev.guard_state(tmp_path, dataset) == "COMPLETED"
        with pytest.raises(ev.FamilyEvalError, match="ALREADY_CONSUMED"):
            ev.begin_guard(tmp_path, dataset, {})
        with pytest.raises(ev.FamilyEvalError):
            ev.complete_guard(tmp_path, dataset, {})
    assert (ROOT / "artifacts/internal_test_access_v1.json").exists()  # historical guard untouched
    assert ev.GUARDS["INTERNAL_TEST"] != "artifacts/internal_test_access_v1.json"
    assert ev.GUARDS["INCART"] != "artifacts/external_incart_access_v1.json"


def test_real_guards_are_not_started_before_exposure() -> None:
    if (ROOT / "reports/model_v2/v2_fl_eval_001/inference_manifest.json").exists():
        pytest.skip("post-exposure state")
    for dataset in ev.GUARDS:
        assert ev.guard_state(ROOT, dataset) == "NOT_STARTED"


def test_frozen_population_expectations_match_the_prompt_and_zero_eligible_group() -> None:
    internal = ev.internal_expectations(ROOT)
    assert (internal["candidate_windows"], internal["eligible_windows"], internal["positive"],
            internal["negative"]) == (2520, 2157, 1156, 1001)
    assert len(internal["frozen_groups"]) == 7 and len(internal["contributing_groups"]) == 6
    assert internal["zero_eligible_groups"] == ["MITDB_P107"]
    assert internal["historical_ids_match"] is True
    assert len(set(internal["ids"])) == 2157 == len(internal["ids"])
    incart = ev.incart_expectations(ROOT)
    assert (incart["records"], incart["clusters"], incart["eligible_windows"]) == (75, 32, 26864)
    assert incart["patient_map_rows"] == 75
    ev.verify_population(internal, internal["ids"], np.asarray(internal["labels"]),
                         internal["groups"])
    with pytest.raises(ev.FamilyEvalError):
        ev.verify_population(internal, internal["ids"][::-1], np.asarray(internal["labels"]),
                             internal["groups"])
    with pytest.raises(ev.FamilyEvalError):
        ev.verify_population(incart, incart["ids"], np.asarray(incart["labels"])[::-1],
                             incart["groups"])


def test_incart_clusters_are_patient_clusters_not_records() -> None:
    incart = ev.incart_expectations(ROOT)
    by_group: dict[str, set[str]] = {}
    for group, record in zip(incart["groups"], incart["records_list"], strict=True):
        by_group.setdefault(group, set()).add(record)
    assert len(by_group) == 32 and len({r for s in by_group.values() for r in s}) == 75
    assert max(len(s) for s in by_group.values()) > 1  # several records share one cluster
    _, draws = generate_patient_draws(np.asarray(incart["groups"]), 2000, 20260927)
    assert draws.shape == (2000, 32)


def test_frozen_t018_and_t020_bootstrap_draws_are_reproduced_exactly() -> None:
    internal = ev.internal_expectations(ROOT)
    incart = ev.incart_expectations(ROOT)
    for npz, groups, clusters in (("reports/t018/bootstrap_draws.npz", internal["groups"], 6),
                                  ("reports/t020/bootstrap_draws.npz", incart["groups"], 32)):
        stored = np.load(ROOT / npz, allow_pickle=False)["draws_int64"]
        _, regenerated = generate_patient_draws(np.asarray(groups), 2000, 20260927)
        assert regenerated.shape == (2000, clusters)
        assert np.array_equal(stored, regenerated)


def test_protocol_freezes_estimands_wording_and_pass_rule() -> None:
    assert PROTOCOL["bootstrap"]["B"] == 2000 and PROTOCOL["bootstrap"]["seed"] == 20260927
    assert PROTOCOL["threshold"]["id"] == "FL_EVAL_RAW_THRESHOLD_0P5_V1"
    assert PROTOCOL["pass_rule"] == "performance_independent"
    assert PROTOCOL["probability"]["definition"] == "sigmoid(raw_logit)"
    assert PROTOCOL["input_contract"]["calibration"] == "NONE"
    assert "NOT project-globally unseen" in PROTOCOL["datasets"]["INTERNAL_TEST"]["wording"]
    assert "NOT project-blind" in PROTOCOL["datasets"]["INCART"]["wording"]
    assert PROTOCOL["estimands"]["primary_absolute"]["model"] == "V2 FedAvg IID"
    assert PROTOCOL["estimands"]["primary_architecture"]["gate_threshold"] == "NONE"
    assert PROTOCOL["scientific_model_fits_added"] == 0
    assert PROTOCOL["firewall"]["CALIBRATION"] == "FORBIDDEN"
    assert PROTOCOL["firewall"]["NSTDB"] == "FORBIDDEN_FOR_EVALUATION"


def test_stats_script_never_loads_checkpoints_or_source_data() -> None:
    source = (ROOT / "scripts/compute_v2_fl_eval_stats.py").read_text()
    tree = ast.parse(source)
    calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not {c for c in calls if "load_model" in c or "torch.load" in c or "infer_logits" in c}
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not {m for m in imported if "internal_test" in m or "external_incart" in m}


def test_runner_orders_stages_and_exposes_no_metrics_before_completion() -> None:
    source = (ROOT / "scripts/run_v2_fl_eval_001.py").read_text()
    assert source.index('begin_guard(ROOT, "INTERNAL_TEST"') < source.index(
        'begin_guard(ROOT, "INCART"') < source.index("complete_guard(ROOT")
    for forbidden in ("point_metrics", "replicate_matrix", "paired_delta", "AUPRC"):
        assert forbidden not in source
    assert "V2_FL_EVAL_GUARD_NOT_NOT_STARTED" in source
    assert "V2_FL_EVAL_METHOD_DRIFT_BEFORE_ACCESS" in source


def test_end_to_end_synthetic_pass_over_the_real_roster(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """All 20 real checkpoints over a SYNTHETIC population -> tables -> statistics (incl. the
    multiprocess bootstrap, shared draws and paired comparisons). Proves the code path
    pre-access."""
    import scripts.run_v2_fl_eval_001 as runner

    monkeypatch.setattr(runner, "PRED", tmp_path / "predictions")
    monkeypatch.setattr(stats, "PRED", tmp_path / "predictions")
    rng = np.random.default_rng(11)
    rows, labels = _rows(36, ["G0", "G1", "G2"])
    waves = rng.normal(size=(36, 2500)) * 2.0
    roster = ev.load_roster(ROOT)
    bindings = runner.run_stage("INTERNAL_TEST", roster, rows, labels, waves)
    assert len(bindings) == 20 and len({b["checkpoint_sha256"] for b in bindings}) == 20
    for binding in bindings:
        table = ev.read_prediction_table(tmp_path / "predictions/INTERNAL_TEST" /
                                         f"{binding['checkpoint_id']}.csv.gz")
        ev.validate_prediction_table(table, [r["example_id"] for r in rows])
        assert table["label"].tolist() == labels.tolist()
    data = stats.evaluate_dataset("INTERNAL_TEST", roster)
    assert len(data["models"]) == 20 and len(data["comparisons"]) == 23
    assert data["bootstrap"]["B"] == 2000 and data["bootstrap"]["multiplicity_preserved"]
    assert data["bootstrap"]["slots_per_replicate"] == 3
    primary = data["comparisons"]["V2_FEDAVG_IID_minus_V1_FEDAVG_IID"]["delta"]["AUPRC"]
    assert primary["valid_replicates"] + primary["invalid_replicates"] == 2000
