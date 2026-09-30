from __future__ import annotations

import numpy as np
import torch

from federated.fedavg_runner import fresh_initial_state, state_sha
from federated.local_training import derive_shuffle_seed, train_local_epoch


def test_fresh_initialization_and_local_epoch_contract() -> None:
    global_state = fresh_initial_state(20260927)
    assert state_sha(global_state) == state_sha(fresh_initial_state(20260927))
    rng = np.random.default_rng(17)
    inputs = rng.normal(size=(65, 1, 2500)).astype(np.float32)
    labels = np.asarray(([0, 1] * 32) + [0], dtype=np.int64)
    before = torch.optim.AdamW.__init__
    result = train_local_epoch(
        global_state=global_state,
        inputs=inputs,
        labels=labels,
        site_id="SITE_00",
        round_number=1,
        experiment_id="FL_IID_V1",
        base_seed=20260927,
        batch_size=64,
        learning_rate=0.001,
        weight_decay=0.0001,
        pos_weight=1.5,
    )
    assert torch.optim.AdamW.__init__ is before
    assert result.examples_seen == 65
    assert result.batch_count == 2
    assert result.update.num_examples == 65
    assert result.shuffle_seed == derive_shuffle_seed(20260927, "FL_IID_V1", 1, "SITE_00")
    assert result.update_norm > 0


def test_shuffle_seed_is_stable_and_not_python_hash() -> None:
    assert derive_shuffle_seed(20260927, "FL_IID_V1", 1, "SITE_00") == 6318989447729917868
    assert derive_shuffle_seed(20260927, "FL_IID_V1", 2, "SITE_00") != derive_shuffle_seed(
        20260927, "FL_IID_V1", 1, "SITE_00"
    )
