"""V2-FL-002 method tests: frozen-reference integrity, matched budgets, heterogeneity
construction, feature-noise determinism, firewall roles, metrics and a synthetic 2-round smoke of
the runner for a clean and a noised condition. Synthetic fixtures and frozen metadata only."""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
import yaml

import federated.model_v2_non_iid_runner as runner
from federated.client_manifest import SITE_IDS
from federated.feature_noise import NOISE_SCHEDULE, mix_noise, noise_offset
from federated.fedavg_runner import choose_best_round
from federated.local_training import derive_shuffle_seed
from federated.model_v2_fl import fresh_initial_state_v2, state_sha
from federated.non_iid_runner import load_sites
from nhm.hashing import hash_file
from nhm.model_v2_partition_guard import PartitionAccessViolation

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs/model_v2/fl_non_iid_model_v2_v1.yaml").read_text())
V1 = yaml.safe_load((ROOT / "configs/fl_non_iid_v1.yaml").read_text())
IID = yaml.safe_load((ROOT / "configs/model_v2/fl_iid_model_v2_v1.yaml").read_text())
T025 = yaml.safe_load((ROOT / "configs/fl_iid_v1.yaml").read_text())
FEATURE = yaml.safe_load((ROOT / "configs/fl_feature_noise_v1.yaml").read_text())
INIT_SHA = "6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f"


def _manifest(condition: str) -> list[dict]:
    path = ROOT / "manifests/clients" / f"{CONFIG['conditions'][condition]['manifest']}.csv"
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("condition", ["label", "quantity", "feature", "combined"])
def test_exact_frozen_manifest_reuse_and_patient_closure(condition: str) -> None:
    cond = CONFIG["conditions"][condition]
    path = ROOT / "manifests/clients" / f"{cond['manifest']}.csv"
    assert hash_file(path) == cond["manifest_sha256"]
    rows = _manifest(condition)
    patients = [r["participant_group_id"] for r in rows]
    assert len(patients) == len(set(patients)) == 27 and {r["partition"] for r in rows} == {"TRAIN"}
    with (ROOT / "manifests/splits/MITDB_SPLIT_V1.csv").open(newline="") as handle:
        split = list(csv.DictReader(handle))
    assert set(patients) == {r["participant_group_id"] for r in split if r["partition"] == "TRAIN"}
    for held in ("VALIDATION", "CALIBRATION", "INTERNAL_TEST"):
        assert not set(patients) & {r["participant_group_id"] for r in split
                                    if r["partition"] == held}
    counts = Counter(r["site_id"] for r in rows)
    assert [counts[s] for s in SITE_IDS] == cond["site_patient_counts"]
    assert sum(int(r["eligible_window_count"]) for r in rows) == 9660
    assert load_sites(path)  # frozen loader accepts it (27 patients, 8 sites)


def test_condition_constructions_match_the_frozen_design() -> None:
    assert [CONFIG["conditions"][c]["site_patient_counts"] for c in ("label", "feature")] == [
        [4, 4, 4, 3, 3, 3, 3, 3]] * 2
    assert CONFIG["conditions"]["quantity"]["site_patient_counts"] == [2, 2, 2, 3, 3, 4, 5, 6]
    assert CONFIG["conditions"]["combined"]["site_patient_counts"] == [2, 2, 2, 3, 3, 4, 5, 6]
    iid = {r["participant_group_id"]: r["site_id"] for r in csv.DictReader(
        (ROOT / "manifests/clients/CLIENTS_IID_V1.csv").open(newline=""))}
    feature = {r["participant_group_id"]: r["site_id"] for r in _manifest("feature")}
    assert feature == iid  # FEATURE changes the signal distribution only, not the mapping
    assert CONFIG["conditions"]["feature"]["feature_noise"] is True
    assert CONFIG["conditions"]["combined"]["feature_noise"] is True
    assert CONFIG["conditions"]["label"]["feature_noise"] is False
    assert CONFIG["conditions"]["quantity"]["feature_noise"] is False
    assert CONFIG["run_order"] == ["label", "quantity", "feature", "combined"]


def test_frozen_references_and_v2_fl_001_entry_verify() -> None:
    entry = runner.verify_entry(ROOT)
    assert entry["status"] == "PASS", entry["problems"]
    assert hash_file(ROOT / "configs/model_v2/fl_protocol_v1.yaml") == CONFIG["references"][
        "MODEL_V2_FL_PROTOCOL_V1"]["sha256"]


def test_common_initialization_and_round_zero_expectations() -> None:
    assert CONFIG["initialization"]["round_0_state_sha256"] == INIT_SHA
    assert state_sha(fresh_initial_state_v2(20260927)) == INIT_SHA
    assert CONFIG["initialization"]["round_0_validation_AUPRC"] == 0.25769234928353735
    assert CONFIG["model"]["sequential_transfer_between_conditions"] is False
    assert CONFIG["model"]["centralized_checkpoint_warm_start"] is False


def test_budget_optimizer_aggregation_transport_match_t025_t026_and_v2_fl_001() -> None:
    for section in ("training", "loss", "aggregation"):
        left = {k: v for k, v in CONFIG[section].items() if k != "augmentation"}
        assert left == {k: v for k, v in T025[section].items()}, section
    for key in ("implementation", "learning_rate", "weight_decay", "state_policy", "scheduler"):
        assert CONFIG["optimizer"][key] == T025["optimizer"][key] == IID["optimizer"][key]
    assert CONFIG["transport"]["id"] == "FL_STATE_TRANSPORT_V1"
    assert CONFIG["shuffle_seed_namespace"] == V1["shuffle_seed_namespace"] == "FL_IID_V1"
    assert CONFIG["loss"]["pos_weight"] == 6103 / 3557
    assert CONFIG["loss"]["client_specific_weights"] is False
    assert CONFIG["training"]["rounds"] == 50 and CONFIG["training"]["local_epochs"] == 1
    assert derive_shuffle_seed(20260927, "FL_IID_V1", 1, "SITE_00") == 6318989447729917868
    assert CONFIG["checkpoint"]["tie_policy"] == "EARLIEST_EXACT_MAXIMUM"


def test_feature_noise_schedule_source_snr_determinism_and_round_independence() -> None:
    for site, spec in FEATURE["schedule"].items():
        assert NOISE_SCHEDULE[site] == (spec["source"], float(spec["snr_db"]))
    assert FEATURE["role"] == "PURE_NOISE_TRAINING_RESOURCE_ONLY"
    assert FEATURE["validation_noise"] is False and FEATURE["fixed_across_rounds"] is True
    rng = np.random.default_rng(0)
    clean = np.sin(np.linspace(0, 40 * np.pi, 2500)) * 0.7
    noise = rng.normal(size=2500)
    for site, (_, target) in NOISE_SCHEDULE.items():
        noisy, achieved = mix_noise(clean, noise, target)
        assert abs(achieved - target) <= FEATURE["snr_tolerance_db"]
        again, achieved_again = mix_noise(clean, noise, target)
        assert np.array_equal(noisy, again) and achieved == achieved_again
        first = noise_offset(site, "EX1", NOISE_SCHEDULE[site][0], 451389)
        assert first == noise_offset(site, "EX1", NOISE_SCHEDULE[site][0], 451389)
    import inspect

    assert "round" not in inspect.signature(noise_offset).parameters


def test_cal_v2_and_central_checkpoints_are_never_inputs() -> None:
    source = (ROOT / "federated/model_v2_non_iid_runner.py").read_text()
    assert "CAL_V2" not in source.replace("CAL_V2_applied", "") and "temperature" not in source
    assert "MODEL_V2_FINAL.pt" not in source and "FL_IID_MODEL_V2_V1_best" not in source.replace(
        "FL_IID_MODEL_V2_V1", "")
    assert CONFIG["evaluation"]["calibration"] == "NONE"


@pytest.mark.parametrize("partition", ["CALIBRATION", "INTERNAL_TEST", "INCART", "BIDMC"])
def test_forbidden_partitions_denied_before_any_read(partition: str) -> None:
    with pytest.raises(PartitionAccessViolation):
        runner.check_partition_allowed(partition, runner.STAGE_ID, runner.ALLOWED)
    with pytest.raises(PartitionAccessViolation):
        runner.guarded_population(ROOT, partition, "x")
    for name in ("CALIBRATION", "INTERNAL_TEST", "INCART", "BIDMC", "WEARABLE_V1"):
        assert CONFIG["access"][name] == "FORBIDDEN"
    assert CONFIG["feature_noise"]["nstdb_role"] == runner.NSTDB_ROLE


def test_checkpoint_selection_and_patient_metrics_preserve_undefined_values() -> None:
    rows = [{"round": 0, "validation_AUPRC": 0.9}, {"round": 1, "validation_AUPRC": 0.3},
            {"round": 2, "validation_AUPRC": 0.6}, {"round": 3, "validation_AUPRC": 0.6}]
    assert choose_best_round(rows) == 2
    labels = np.array([1, 0, 1, 1, 0, 0, 0, 0])
    probs = np.array([0.9, 0.2, 0.7, 0.4, 0.1, 0.3, 0.2, 0.2])
    groups = np.array(["A", "A", "B", "B", "C", "C", "C", "C"])
    result = runner.per_patient_metrics(labels, probs, groups)
    by = {r["participant_group_id"]: r for r in result["per_group"]}
    assert by["B"]["AUROC"] is None and by["B"]["negatives"] == 0  # single-class: undefined
    assert by["C"]["AUPRC"] is None and by["C"]["positives"] == 0   # no positives: undefined
    assert by["C"]["F1_at_0_5"] is None
    assert by["A"]["AUPRC"] == 1.0 and by["A"]["AUROC"] == 1.0
    assert result["finite_AUPRC_patients"] == 2 and result["undefined_AUPRC_patients"] == 1
    finite = [by["A"]["AUPRC"], by["B"]["AUPRC"]]
    assert result["VALIDATION_PATIENT_MACRO_AUPRC_V2"] == float(np.mean(finite))
    assert result["VALIDATION_PATIENT_WORST_AUPRC_V2"] == min(finite)
    assert result["validation_patients_are_clients"] is False


def _fake_population(partition: str, groups: list[str], per_group: int, seed: int):
    from training.train_central import WindowPopulation

    rng = np.random.default_rng(seed)
    gid, labels, ids = [], [], []
    for g in groups:
        for i in range(per_group):
            gid.append(g)
            labels.append(1 if i % 3 == 0 else 0)
            ids.append(f"{partition}_{g}_{i}")
    waves = rng.normal(size=(len(ids), 2500)) * rng.uniform(0.5, 2.0, size=(len(ids), 1))
    return WindowPopulation(partition=partition, waveforms=waves,
                            labels=np.asarray(labels, dtype=np.int64), example_ids=tuple(ids),
                            participant_group_ids=np.asarray(gid, dtype=str), accessed_paths=())


@pytest.mark.parametrize("condition", ["quantity", "feature"])
def test_runner_smoke_two_rounds_clean_and_noised(condition: str, tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "configs/model_v2").mkdir(parents=True)
    (tmp_path / "manifests/clients").mkdir(parents=True)
    for name in ("NONIID_QUANTITY_V1.csv", "NONIID_FEATURE_V1.csv"):
        shutil.copy(ROOT / "manifests/clients" / name, tmp_path / "manifests/clients")
    patients = [r["participant_group_id"] for r in _manifest(condition)]
    train = _fake_population("TRAIN", patients, 6, 1)
    validation = _fake_population("VALIDATION", [f"VAL_{i}" for i in range(3)], 9, 2)
    config = yaml.safe_load((ROOT / runner.CONFIG_RELATIVE).read_text())
    config["training"]["rounds"] = 2
    config["loss"]["pos_weight"] = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    from federated.model_adapter import restore_state
    from federated.model_v2_fl import fresh_model_v2

    probe = fresh_model_v2()
    restore_state(probe, fresh_initial_state_v2(20260927))
    metrics0, _, _ = runner.evaluate_model(
        probe, runner.normalized_population(validation), validation.labels,
        validation.participant_group_ids, pos_weight=1.7, partition="VALIDATION")
    config["initialization"]["round_0_validation_AUPRC"] = metrics0["AUPRC"]
    (tmp_path / runner.CONFIG_RELATIVE).write_text(yaml.safe_dump(config))
    seen = {"validation_inputs": None}
    monkeypatch.setattr(runner, "load_population",
                        lambda p: {"TRAIN": train, "VALIDATION": validation}[p])
    monkeypatch.setattr(runner, "build_noise_bank", lambda root: (
        {k: np.random.default_rng(7).normal(size=6000) for k in ("bw", "em", "ma")}, {}))
    original = runner.evaluate_model

    def spy(model, inputs, labels, groups, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs["partition"] == "VALIDATION":
            seen["validation_inputs"] = np.array(inputs)
        return original(model, inputs, labels, groups, **kwargs)

    monkeypatch.setattr(runner, "evaluate_model", spy)
    report = runner.run_condition(tmp_path, condition)
    assert report["status"] == "COMPLETE" and report["round_0_state_sha256"] == INIT_SHA
    assert report["stability"]["client_updates_received"] == 16
    ledger = [json.loads(x) for x in (tmp_path / "reports/model_v2/access_ledger.jsonl"
                                      ).read_text().splitlines()]
    nstdb = [r for r in ledger if r["partition"] == "NSTDB"]
    assert bool(nstdb) == (condition == "feature")
    assert all(r["access_type"] == "NSTDB_PURE_NOISE_TRAINING_RESOURCE" for r in nstdb)
    assert {r["partition"] for r in ledger} <= {"TRAIN", "VALIDATION", "NSTDB"}
    clean = runner.normalized_population(validation)
    np.testing.assert_array_equal(seen["validation_inputs"], clean)  # validation never noised
    patient_path = tmp_path / runner.OUT_RELATIVE / f"{condition}_validation_patient_metrics.json"
    patient = json.loads(patient_path.read_text())
    assert patient["validation_patients_are_clients"] is False
    for name in ("round_log.csv", "client_rounds.csv", "validation_predictions.csv"):
        assert (tmp_path / runner.OUT_RELATIVE / f"{condition}_{name}").exists()


def test_historical_v1_and_v2_fl_001_files_untouched_by_method() -> None:
    for relative, digest in {
        "configs/fl_non_iid_v1.yaml": CONFIG["references"]["fl_non_iid_v1"]["sha256"],
        "configs/fl_feature_noise_v1.yaml": CONFIG["references"]["fl_feature_noise_v1"]["sha256"],
        "configs/model_v2/fl_iid_model_v2_v1.yaml": CONFIG["references"]["FL_IID_MODEL_V2_V1"][
            "sha256"]}.items():
        assert hash_file(ROOT / relative) == digest
    for relative in ("federated/non_iid_runner.py", "federated/feature_noise.py",
                     "federated/local_training.py"):
        assert "model_v2" not in (ROOT / relative).read_text().lower()


def test_v2flg1_defined_before_any_result_and_future_work_not_started() -> None:
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {r["gate_id"]: r for r in csv.DictReader(handle)}
    assert gates["V2FLG1"]["blocks_tasks"] == "V2-FL-003"
    assert "performance direction" in gates["V2FLG1"]["purpose"]
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {r["task_id"]: r for r in csv.DictReader(handle)}
    assert tasks["V2-FL-002"]["gate_impact"] == "V2FLG1"
    assert tasks["V2-FL-003"]["status"] == "NOT_STARTED"
    assert gates["V2FLG0"]["status"] == "PASS"
