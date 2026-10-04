"""V2-FL-004: MODEL_V2-shaped Flower SecAgg+ protocol fixture (additive).

privacy/secagg_app.py, privacy/server_visibility.py and privacy/accounting.py are
architecture-generic (lists of float arrays plus an integer weight per client) and are reused
BYTE-IDENTICALLY. This module supplies only what the historical harness hard-binds to MODEL_V1
(initialization, local update reconstruction, state specification): the deterministic V2-FL-001
round-1 client payloads.

It is a PROTOCOL FIXTURE, not an experiment: TRAIN only, one round, no checkpoint, no evaluation.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

from federated.aggregation import ClientUpdate
from federated.client_manifest import SITE_IDS
from federated.fedavg_runner import load_manifest_sites, normalized_population
from federated.model_adapter import model_v1_state_spec
from federated.model_v2_fl import (
    fresh_initial_state_v2,
    fresh_model_v2,
    state_sha,
    train_local_epoch_v2,
)
from nhm.model_v2_partition_guard import _append_ledger, check_partition_allowed
from privacy.secagg_app import ClientPayload
from training.train_central import load_population

ROOT = Path(__file__).resolve().parents[1]
STAGE_ID = "V2-FL-004"


def floating_keys() -> list[str]:
    """Entries that enter SecAgg+ (floating trainable parameters + floating BatchNorm buffers).
    `model_v1_state_spec` is generic over any nn.Module despite its name."""
    return [spec.key for spec in model_v1_state_spec(fresh_model_v2()) if spec.aggregatable]


def state_enumeration() -> dict:
    specs = model_v1_state_spec(fresh_model_v2())
    roles: dict[str, int] = {}
    for spec in specs:
        roles[spec.state_role] = roles.get(spec.state_role, 0) + 1
    return {"total_entries": len(specs), "role_counts": roles,
            "floating_entries": sum(1 for s in specs if s.aggregatable),
            "integer_entries": sum(1 for s in specs if not s.aggregatable),
            "integer_keys": [s.key for s in specs if not s.aggregatable]}


def v2_round_1_payloads(root: Path = ROOT) -> tuple[
        list[ClientPayload], list[np.ndarray], OrderedDict[str, np.ndarray], list[ClientUpdate]]:
    """Reconstruct V2-FL-001 round 1 (TRAIN only). Returns (payloads of FULL floating client
    states = global + delta, initial floating arrays, global state, ClientUpdates)."""
    cfg = yaml.safe_load((root / "configs/model_v2/fl_iid_model_v2_v1.yaml").read_text())
    check_partition_allowed("TRAIN", STAGE_ID, ("TRAIN",))
    sites = load_manifest_sites(root / "manifests/clients/CLIENTS_IID_V1.csv")
    train = load_population("TRAIN")
    _append_ledger(root, {
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "stage_id": STAGE_ID, "experiment_id": "round_1_protocol_fixture", "partition": "TRAIN",
        "access_type": "waveform_read", "rows": int(train.labels.size),
        "source_path": "frozen MITDB_WINDOWS_V1 caches (load_population)"})
    inputs = normalized_population(train)
    indices = {s: np.flatnonzero(np.isin(train.participant_group_ids, groups))
               for s, groups in sites.items()}
    seed = int(cfg["initialization"]["seed"])
    global_state = fresh_initial_state_v2(seed)
    keys = floating_keys()
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    payloads: list[ClientPayload] = []
    updates: list[ClientUpdate] = []
    for node_id, site in enumerate(SITE_IDS, start=1):
        selected = indices[site]
        result = train_local_epoch_v2(
            global_state=global_state, inputs=inputs[selected], labels=train.labels[selected],
            site_id=site, round_number=1, experiment_id=cfg["shuffle_seed_namespace"],
            base_seed=seed,
            batch_size=int(cfg["training"]["batch_size"]),
            learning_rate=float(cfg["optimizer"]["learning_rate"]),
            weight_decay=float(cfg["optimizer"]["weight_decay"]), pos_weight=pos_weight)
        arrays = tuple(np.asarray(global_state[k] + result.update.delta[k],
                                  dtype=global_state[k].dtype) for k in keys)
        payloads.append(ClientPayload(site, node_id, arrays, result.examples_seen))
        updates.append(result.update)
    initial = [np.array(global_state[k], copy=True) for k in keys]
    return payloads, initial, global_state, updates


def merge_state(floating: list[np.ndarray],
                global_state: OrderedDict[str, np.ndarray]) -> OrderedDict[str, np.ndarray]:
    """Floating aggregate + server-side non-floating buffers (FL_STATE_TRANSPORT_V1 policy)."""
    iterator = iter(floating)
    merged: OrderedDict[str, np.ndarray] = OrderedDict()
    for spec in model_v1_state_spec(fresh_model_v2()):
        merged[spec.key] = np.array(
            next(iterator) if spec.aggregatable else global_state[spec.key], copy=True)
    return merged


def sha(state: dict[str, np.ndarray]) -> str:
    return state_sha(state)
