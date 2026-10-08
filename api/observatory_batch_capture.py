# ruff: noqa: E501
"""Opt-in, bounded, READ-ONLY per-batch observation of one local training call (OBS-DIAG-001).

Uses only torch's documented global observer hooks (module forward post-hook, optimizer step post-hook). Hooks return None, never modify
inputs/outputs/parameters/gradients, are active only while the context is open and only for the thread that opened it. The frozen
training function (federated/model_v2_fl.py), optimizer, loss, seeds and states are untouched. Lives outside `product/` because it needs torch."""

from __future__ import annotations

import math
import threading
from types import TracebackType
from typing import Any

import torch
from torch import nn
from torch.nn.modules.module import register_module_forward_hook
from torch.optim.optimizer import register_optimizer_step_post_hook

MAX_BATCHES = 64          # hard bound per client-round capture (the canonical protocol uses 2)


class BatchCapture:
    def __init__(self) -> None:
        self.batches: list[dict[str, Any]] = []
        self.dropped = 0
        self._thread = threading.get_ident()
        self._handles: list[Any] = []
        self._pending_loss: tuple[int, float] | None = None

    def _mine(self) -> bool:
        return threading.get_ident() == self._thread

    def _on_loss(self, module: nn.Module, args: tuple[Any, ...], output: torch.Tensor) -> None:
        if not isinstance(module, nn.BCEWithLogitsLoss) or not self._mine() or not args:
            return
        logits = args[0]
        self._pending_loss = (int(logits.shape[0]), float(output.detach().item()))

    def _on_step(self, optimizer: torch.optim.Optimizer, _args: Any, _kwargs: Any) -> None:
        if not self._mine() or self._pending_loss is None:
            return
        size, loss = self._pending_loss
        self._pending_loss = None
        if len(self.batches) >= MAX_BATCHES:
            self.dropped += 1
            return
        squared = 0.0
        for group in optimizer.param_groups:
            for parameter in group["params"]:
                if parameter.grad is not None:
                    squared += float(parameter.grad.detach().double().pow(2).sum().item())
        self.batches.append({"batch_index": len(self.batches), "batch_size": size, "loss": loss,
                             "learning_rate": float(optimizer.param_groups[0]["lr"]),
                             "gradient_l2_norm": math.sqrt(squared), "optimizer_step": len(self.batches) + 1})

    def __enter__(self) -> BatchCapture:
        self._handles = [register_module_forward_hook(self._on_loss), register_optimizer_step_post_hook(self._on_step)]
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        for handle in self._handles:
            handle.remove()
        self._handles = []
