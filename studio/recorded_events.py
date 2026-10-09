# ruff: noqa: E501
"""Replay journal for a RECORDED FL10 run, reconstructed only from the recorded run report (rounds, client rounds, update digests, committed digests).

The frozen evidence has no event log, so this is an explicit REPLAY (run type REPLAY): the events are in the order the runner actually executed (clients in canonical
order, accept, aggregate, commit), carry no wall-clock timing (a deterministic counter), and no training happens. It adds no number that is not in the report."""

from __future__ import annotations

from itertools import count
from typing import Any

from product.federation.base import RunType
from product.federation.events import FederationEmitter
from product.federation.journal import FederationEventJournal
from studio.events10 import Fl10EventTranslator


def build_recorded_journal(run_id: str, bundle: dict[str, Any]) -> FederationEventJournal:
    journal = FederationEventJournal(run_id)
    tick = count(1)
    emitter = FederationEmitter(run_id, lambda: next(tick), [journal.append], 0)
    clients = tuple(sorted({r["client_id"] for r in bundle["client_rounds"]}))
    examples = {c["client_id"]: int(c["counts"]["trainable"]) for c in bundle["training_cohort"]}
    t = Fl10EventTranslator(emitter, lambda fn: fn(), planned_rounds=bundle["planned_rounds"], client_ids=clients, local_examples=examples, run_type=RunType.REPLAY)
    t.created()
    t.running()
    updates = {(u["round"], u["client_id"]): u["update_sha256"] for u in bundle["updates"]}
    by_round: dict[int, list[dict[str, Any]]] = {}
    for row in bundle["client_rounds"]:
        by_round.setdefault(row["round"], []).append(row)
    for rnd in bundle["rounds"]:
        r = rnd["round"]
        t.on_progress({"event": "ROUND_OPENED", "round": r, "base_state_sha256": rnd["base_state_sha256"]})
        for row in sorted(by_round[r], key=lambda x: x["client_id"]):
            t.on_progress({"event": "CLIENT_TRAINING_STARTED", "round": r, "client_id": row["client_id"]})
            t.on_progress({"event": "CLIENT_TRAINING_FINISHED", "round": r, "client_id": row["client_id"], "mean_loss": row["mean_training_loss"], "examples": row["examples_processed"], "update_sha256": updates[(r, row["client_id"])]})
        t.on_progress({"event": "UPDATES_ACCEPTED", "round": r, "accepted_clients": sorted(x["client_id"] for x in by_round[r]), "accepted_updates": rnd["accepted_updates"]})
        t.on_progress({"event": "ROUND_COMMITTED", "round": r, "global_state_sha256": rnd["global_state_sha256"]})
    t.completed(bundle["planned_rounds"])
    journal.close()
    return journal
