# ruff: noqa: E501
"""Trainer-entry tap for the FL10 runner (same purpose as final_showcase.link_trace.TrainerTap, bound to the FL10 runner's reference to the unchanged trainer)."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from final_showcase.link_trace import array_sha


class Fl10TrainerTap:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def __enter__(self) -> Fl10TrainerTap:
        from fl10 import runner

        self._module, self._original = runner, runner.train_local_epoch_v2
        original = self._original

        def tapped(**kwargs: Any) -> Any:
            inputs, labels = kwargs["inputs"], kwargs["labels"]
            record = {"site_id": kwargs["site_id"], "round_number": kwargs["round_number"], "examples": int(inputs.shape[0]), "inputs_sha256": array_sha(inputs, np.float32), "labels_sha256": array_sha(labels, np.float32)}
            result = original(**kwargs)
            record["examples_seen"] = int(result.examples_seen)
            with self._lock:
                self.calls.append(record)
            return result

        runner.train_local_epoch_v2 = tapped
        return self

    def __exit__(self, *exc: Any) -> None:
        self._module.train_local_epoch_v2 = self._original
