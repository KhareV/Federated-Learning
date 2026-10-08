# ruff: noqa: E501
"""OBS-DIAG-001: per-batch observation and activation inspection are read-only, bounded, isolated and numerically inert."""

from __future__ import annotations

import threading

import pytest
import torch
from torch import nn
from torch.nn.modules import module as torch_module
from torch.optim import optimizer as torch_optimizer

from api import observatory_batch_capture as capture_module
from api.observatory_batch_capture import BatchCapture
from product.observatory.acceptance_capture import consistent


def _train(capture: BatchCapture | None, batches: int = 3) -> tuple[list[float], list[torch.Tensor]]:
    torch.manual_seed(7)
    model = nn.Linear(4, 1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01, weight_decay=0.0001)
    criterion = nn.BCEWithLogitsLoss()
    data = torch.randn(batches * 5, 4)
    targets = (torch.rand(batches * 5, 1) > 0.5).float()
    losses: list[float] = []

    def loop() -> None:
        for index in range(batches):
            signals, labels = data[index * 5:(index + 1) * 5], targets[index * 5:(index + 1) * 5]
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(signals), labels)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))

    if capture is None:
        loop()
    else:
        with capture:
            loop()
    return losses, [p.detach().clone() for p in model.parameters()]


def test_batch_capture_is_numerically_inert_and_removes_its_hooks() -> None:
    forward_before = len(torch_module._global_forward_hooks)
    step_before = len(torch_optimizer._global_optimizer_post_hooks)
    plain_losses, plain_params = _train(None)
    capture = BatchCapture()
    observed_losses, observed_params = _train(capture)
    assert plain_losses == observed_losses
    assert all(torch.equal(a, b) for a, b in zip(plain_params, observed_params, strict=True))
    assert [b["loss"] for b in capture.batches] == observed_losses
    assert [b["batch_index"] for b in capture.batches] == [0, 1, 2]
    assert all(b["batch_size"] == 5 and b["gradient_l2_norm"] > 0 and b["learning_rate"] == 0.01 for b in capture.batches)
    assert len(torch_module._global_forward_hooks) == forward_before
    assert len(torch_optimizer._global_optimizer_post_hooks) == step_before


def test_capture_ignores_other_threads_and_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = BatchCapture()
    with capture:
        worker = threading.Thread(target=_train, args=(None,))
        worker.start()
        worker.join()
    assert capture.batches == []          # another thread's training is never recorded
    monkeypatch.setattr(capture_module, "MAX_BATCHES", 2)
    bounded = BatchCapture()
    _train(bounded, batches=4)
    assert len(bounded.batches) == 2 and bounded.dropped == 2


def test_consistency_gate_rejects_rows_that_do_not_reproduce_the_epoch_summary() -> None:
    rows = [{"batch_size": 64, "loss": 0.5}, {"batch_size": 29, "loss": 0.9}]
    mean = (0.5 * 64 + 0.9 * 29) / 93
    record = {"batch_count": 2, "examples_seen": 93, "mean_loss_diagnostic_only": mean}
    assert consistent(rows, record)
    assert not consistent(rows, {**record, "mean_loss_diagnostic_only": mean + 1e-3})
    assert not consistent(rows[:1], record)


def test_activation_inspection_is_bit_identical_isolated_bounded_and_matches_the_runtime() -> None:
    import numpy as np

    from api.observatory_activation import MAX_BINS, MAX_CHANNELS, inspect_activations
    from api.runtime_v2 import ResearchRuntimeV2
    from product.devices.scenarios import load_scenarios
    from product.observatory.pipeline import canonical_emitted_window

    spec = load_scenarios()["NORMAL_MONITORING"]
    body = inspect_activations(spec, 2)
    assert body["parity"] == {"logit_bit_identical_with_and_without_hooks": True, "hooks_remaining_after_inspection": 0}
    assert body["parameter_count"] == 57_553 and body["model_id"] == "MODEL_V2_FINAL"
    heat = body["selected_layer_heatmap"]
    assert heat["channels"] <= MAX_CHANNELS and heat["time_bins"] <= MAX_BINS
    assert len(heat["mean_pooled_values"]) == heat["channels"]
    assert all(len(row) == heat["time_bins"] for row in heat["mean_pooled_values"])
    runtime = ResearchRuntimeV2(verify="manifest")
    samples = np.asarray(canonical_emitted_window(spec, 2)["ecg"]["samples"], dtype=np.float64)
    assert abs(runtime.infer(list(samples)).raw_probability - body["raw_probability"]) < 1e-6
    again = inspect_activations(spec, 2)                       # a second call reuses nothing mutable
    assert again["raw_logit"] == body["raw_logit"] and again["layers"] == body["layers"]
    unusable = load_scenarios()["MIXED_MONITORING_SESSION"]   # long transport gap at 330-345 s
    with pytest.raises(ValueError, match="WINDOW_UNUSABLE_NO_MODEL_INPUT"):
        for index in range(65, 69):
            inspect_activations(unusable, index)


def test_obs_diag_lock_chains_to_the_immutable_v1_lock_and_detects_tamper(tmp_path, monkeypatch) -> None:
    import json as _json

    from scripts import verify_obs_diag_001 as verifier
    from scripts import verify_observatory_v1 as v1

    assert verifier.verify()["status"] == "PASS"
    assert v1.verify()["status"] == "PASS"                      # V1 verifier accepts the successor-repinned files only through the chained lock
    lock = _json.loads(verifier.LOCK_PATH.read_text())
    assert lock["status"] == "FROZEN_DELIVERED_CAPABILITIES_ONLY"
    assert _json.loads(verifier.V1_LOCK.read_text())["status"] == "FROZEN_IMPLEMENTED_SCOPE_NOT_FULL_MASTER_PROMPT_ACCEPTANCE"
    lock["bound_files"][sorted(lock["bound_files"])[0]] = "0" * 64
    tampered = tmp_path / "lock.json"
    tampered.write_text(_json.dumps(lock))
    monkeypatch.setattr(verifier, "LOCK_PATH", tampered)
    with pytest.raises(RuntimeError, match="OBS_DIAG_TAMPER"):
        verifier.verify()
