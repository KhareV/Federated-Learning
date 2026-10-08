# ruff: noqa: E501
"""Provenance trace for the live-monitored SITE_00 link: are the monitored windows the tensors the FL trainer actually consumed?

A read-only tap wraps the trainer entry point *as called by the unmodified client adapter* (``product.federation.client.train_local_epoch_v2``) and records,
per call, the SHA-256 of the exact ``inputs`` and ``labels`` arrays and the example count, then delegates unchanged. The expected digests are computed from
the windows the monitoring runtime emitted (never from a regenerated dataset). Any mismatch raises ``LinkTraceError``."""

from __future__ import annotations

import hashlib
import threading
from typing import Any

import numpy as np

from federated.virtual_client_source_v1 import LocalDataset
from product.edge.local_training_buffer import input_digest, input_ref_for, window_id_for


class LinkTraceError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}")
        self.code, self.detail = code, detail


def array_sha(array: np.ndarray, dtype: Any) -> str:
    return hashlib.sha256(np.ascontiguousarray(array, dtype=dtype).tobytes()).hexdigest()


class TrainerTap:
    """Context manager: records what the trainer was handed, then calls the real trainer."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def __enter__(self) -> TrainerTap:
        import product.federation.client as client_module

        self._module, self._original = client_module, client_module.train_local_epoch_v2
        original = self._original

        def tapped(**kwargs: Any) -> Any:
            inputs, labels = kwargs["inputs"], kwargs["labels"]
            record = {"site_id": kwargs["site_id"], "round_number": kwargs["round_number"], "examples": int(inputs.shape[0]), "inputs_sha256": array_sha(inputs, np.float32),
                      "labels_sha256": array_sha(labels, np.float32), "batch_size": kwargs["batch_size"], "base_seed": kwargs["base_seed"]}
            result = original(**kwargs)
            record.update(examples_seen=int(result.examples_seen), shuffle_seed=str(result.shuffle_seed))
            with self._lock:
                self.calls.append(record)
            return result

        client_module.train_local_epoch_v2 = tapped
        return self

    def __exit__(self, *exc: Any) -> None:
        self._module.train_local_epoch_v2 = self._original


def expected_trace(dataset: LocalDataset) -> dict[str, Any]:
    """What the trainer must see if (and only if) the buffer was filled from these monitored windows."""
    windows = []
    for position, edge in enumerate(dataset.right_edges_us):
        digest = input_digest(dataset.inputs[position])
        windows.append({"position": position, "right_edge_us": int(edge), "window_id": window_id_for(dataset.client_id, edge),
                        "model_input_ref": input_ref_for(dataset.dataset_sha256, position, digest), "input_digest": digest, "label": int(dataset.labels[position])})
    return {"client_id": dataset.client_id, "examples": len(windows), "inputs_sha256": array_sha(dataset.inputs, np.float32), "labels_sha256": array_sha(dataset.labels, np.float32),
            "dataset_sha256": dataset.dataset_sha256, "windows": windows}


def buffer_trace(buffer: Any) -> dict[str, Any]:
    """Window identities and tensor references as the client buffer holds them (private tensors read through the owner API)."""
    records = buffer.records()
    inputs, labels = buffer.training_arrays(requester_client_id=buffer.client_id)
    return {"dataset_sha256": buffer.dataset_sha256, "examples": len(records), "inputs_sha256": array_sha(inputs, np.float32), "labels_sha256": array_sha(labels, np.float32),
            "windows": [{"position": i, "right_edge_us": r.timestamp_us, "window_id": r.window_id, "model_input_ref": r.model_input_ref} for i, r in enumerate(records)]}


def verify_trace(expected: dict[str, Any], buffer: dict[str, Any], calls: list[dict[str, Any]], *, client_id: str, rounds: int) -> dict[str, Any]:
    if buffer["dataset_sha256"] != expected["dataset_sha256"] or buffer["inputs_sha256"] != expected["inputs_sha256"] or buffer["labels_sha256"] != expected["labels_sha256"]:
        raise LinkTraceError("BUFFER_NOT_FROM_MONITORED_WINDOWS")
    if [(w["position"], w["right_edge_us"], w["window_id"], w["model_input_ref"]) for w in buffer["windows"]] != [(w["position"], w["right_edge_us"], w["window_id"], w["model_input_ref"]) for w in expected["windows"]]:
        raise LinkTraceError("WINDOW_IDENTITIES_DIFFER")
    mine = sorted((c for c in calls if c["site_id"] == client_id), key=lambda c: c["round_number"])
    if [c["round_number"] for c in mine] != list(range(1, rounds + 1)):
        raise LinkTraceError("SITE_NOT_TRAINED_EVERY_ROUND", str([c["round_number"] for c in mine]))
    for call in mine:
        if call["inputs_sha256"] != expected["inputs_sha256"] or call["labels_sha256"] != expected["labels_sha256"] or call["examples"] != expected["examples"]:
            raise LinkTraceError("TRAINER_INPUT_NOT_THE_MONITORED_WINDOWS", f"round {call['round_number']}")
        if call["examples_seen"] != expected["examples"]:
            raise LinkTraceError("EXAMPLE_ACCOUNTING_MISMATCH")
    return {"verified": True, "client_id": client_id, "rounds_traced": len(mine), "windows": expected["examples"], "inputs_sha256": expected["inputs_sha256"], "labels_sha256": expected["labels_sha256"],
            "trainer_calls": mine, "peers_trained": sorted({c["site_id"] for c in calls if c["site_id"] != client_id})}
