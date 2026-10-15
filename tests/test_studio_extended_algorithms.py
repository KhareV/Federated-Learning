from __future__ import annotations

from functools import cache

from federated.wearable_fl_runner_v1 import build_cohort
from federated.wearable_fl_runner_v1 import BASE_SEED, BATCH_SIZE, LEARNING_RATE, POS_WEIGHT, WEIGHT_DECAY, new_session
from federated.model_v2_fl import train_local_epoch_v2
from federated.model_v2_fedprox import train_local_fedprox_epoch_v2
from federated.wearable_fl_system_v1 import EXPERIMENT_ID
from fl10 import runner


@cache
def cohort():
    _, datasets, manifest = build_cohort()
    return datasets, manifest


def execute(tmp_path, *, algorithm: str, secagg_mode: str = "PLAIN"):
    datasets, manifest = cohort()
    return runner.run_training(
        mode="A", run_id="EXTENDED-ALGORITHM-TEST", out_dir=tmp_path,
        datasets=datasets, manifest=manifest, rounds=1, capture_batches=False,
        require_prefix_parity=algorithm == "FEDAVG", algorithm=algorithm,
        secagg_mode=secagg_mode,
    )


def test_extended_fedprox_executes_real_v2_optimizer_and_commits(tmp_path):
    report = execute(tmp_path, algorithm="FEDPROX")
    assert report["status"] == "COMPLETED" and report["algorithm"] == "FEDPROX"
    assert report["fedprox_mu"] == 0.1 and report["accepted_updates_total"] == 8
    assert report["rounds"][0]["global_state_sha256"] != report["rounds"][0]["base_state_sha256"]
    assert all(row["optimizer_steps"] > 0 for row in report["client_rounds"])


def test_extended_fedprox_mu_zero_matches_fedavg_local_update_exactly():
    datasets, _ = cohort(); state, _ = new_session(); data = datasets[0]
    kwargs = dict(global_state=state, inputs=data.inputs, labels=data.labels, site_id=data.client_id, round_number=1, experiment_id=EXPERIMENT_ID, base_seed=BASE_SEED,
                  batch_size=BATCH_SIZE, learning_rate=LEARNING_RATE, weight_decay=WEIGHT_DECAY, pos_weight=POS_WEIGHT)
    avg = train_local_epoch_v2(**kwargs)
    prox = train_local_fedprox_epoch_v2(**kwargs, mu=0.0)
    assert avg.mean_loss == prox.mean_loss and avg.examples_seen == prox.examples_seen
    assert all((avg.update.delta[key] == prox.update.delta[key]).all() for key in avg.update.delta)


def test_extended_fedprox_round_one_secagg_shadow_is_real_and_plain_authoritative(tmp_path):
    report = execute(tmp_path, algorithm="FEDPROX", secagg_mode="SECAGG_SHADOW")
    shadow = report["secagg_shadow"]
    assert shadow["status"] == "PASS" and shadow["round"] == 1
    assert shadow["plain_clear_update_count"] == 8
    assert shadow["protected_clear_update_count"] == 0
    assert shadow["authoritative_aggregation"] == "PLAIN"
