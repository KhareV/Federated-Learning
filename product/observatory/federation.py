"""Read-only, owner-scoped federation contribution projection.

Acceptance is taken from coordinator_digests, never inferred from a client SUBMITTED
event. Older/incomplete runs may legitimately have no accepted-contribution record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from capstone_persistence.federation_store import FederationStore
from federated.wearable_sim_local_labels import SyntheticEventLabelProvider
from product.federation.artifact_store import FederationArtifactStore
from product.federation.base import FederationRound, FederationRun, RunState, RunType
from product.observatory.acceptance_capture import read_verified as read_acceptance_capture
from product.observatory.models import WindowTrace
from product.observatory.pipeline import reconstruct_window
from simulation.fl_cohort_v1 import DURATION_S, ClientProfile, cohort_profiles
from simulation.fl_cohort_v1 import iter_observed_records as fl_observed_records

MANIFEST = (Path(__file__).resolve().parents[2]
            / "reports/model_v2/v2_fl_005/cohort_manifest_run.json")
EXPECTED_MANIFEST_SHA256 = "e586b8cb425dfcfb9c5c72222b174477519445f2cc2529a2d11a2ec6e55803dc"


class FrozenClient(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    participant_id: str
    session_id: str
    source_rate_hz: int
    scenario: str
    windows_emitted: int
    valid: int
    degraded: int
    unusable: int
    trainable: int
    synthetic_positive: int
    synthetic_negative: int
    dataset_sha256: str
    faults: tuple[tuple[str, float, float], ...]


class FrozenCohort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cohort_id: str
    source_relative_path: str
    source_sha256: str
    label_contract: Literal["WEARABLE_SIM_EVENT_WINDOW_V1"]
    claim_boundary: Literal["SYNTHETIC_ENGINEERING_DATA_NOT_AAMI_SVF_EFFICACY"]
    clients: tuple[FrozenClient, ...]


class BatchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_index: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    loss: float = Field(ge=0)
    learning_rate: float = Field(gt=0)
    gradient_l2_norm: float = Field(ge=0)
    optimizer_step: int = Field(ge=1)


class PerBatchCapture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    batches: tuple[BatchRecord, ...]
    dropped_beyond_bound: int = Field(ge=0)
    loss_term: str


class LocalTrainingDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    examples_seen: int = Field(ge=1)
    batch_count: int = Field(ge=1)
    shuffle_seed: str
    update_bytes: int = Field(ge=1)
    mean_loss_diagnostic_only: float = Field(ge=0)
    update_norm_diagnostic_only: float = Field(ge=0)
    per_batch: PerBatchCapture | None = None


class ClientContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    local_trainable_windows: int
    examples_seen: int | None = None
    shuffle_seed: str | None = None
    update_digest: str | None = None
    training_completed: bool | None = None
    update_produced: bool | None = None
    update_submitted: bool | None = None
    accepted: bool | None = None
    aggregated: bool | None = None
    accepted_examples: int | None = None
    weight: float | None = Field(default=None, ge=0, le=1)
    training_diagnostic: LocalTrainingDiagnostic | None = None
    evidence_state: Literal[
        "NOT_RECORDED", "TRAINED_ACCEPTANCE_NOT_RECORDED", "NOT_ACCEPTED", "ACCEPTED",
        "GOVERNANCE_ATTESTED_ACCEPTED", "DIRECT_OBSERVED_ACCEPTED",
    ]


class RoundContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    round_id: int
    base_state_digest: str | None
    committed_state_digest: str | None
    accepted_update_count: int | None
    reported_accepted_update_count: int | None
    accepted_example_total: int | None
    acceptance_basis: Literal[
        "DIRECT_COORDINATOR_MAP", "DIRECT_OBSERVED_COORDINATOR_MAP",
        "GOVERNANCE_ATTESTED_SERVER_JOURNAL", "NOT_RECORDED"
    ]
    clients: tuple[ClientContribution, ...]


class RunContributions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    run_type: str
    run_status: str
    algorithm: str
    source_run_id: str | None
    evidence_status: Literal["RUN_ARTIFACT_METADATA", "NO_TRAINING_IN_REPLAY", "NOT_RECORDED"]
    cohort_manifest_sha256: str
    reported_total_accepted_updates: int | None
    claim_boundary: Literal["ENGINEERING_SAMPLE_WEIGHT_NOT_ACCURACY_OR_EFFICACY"]
    rounds: tuple[RoundContribution, ...]


class FlClientWindowTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    participant_id: str
    cohort_manifest_sha256: str
    label_contract: Literal["WEARABLE_SIM_EVENT_WINDOW_V1"]
    training_eligible: bool
    engineering_label: int | None
    claim_boundary: Literal["SYNTHETIC_EVENT_LABEL_NOT_AAMI_SVF_TARGET"]
    signal: WindowTrace


@dataclass(frozen=True)
class _FlProfileAdapter:
    profile_value: ClientProfile

    @property
    def scenario_id(self) -> str:
        return self.profile_value.client_id

    @property
    def duration_s(self) -> int:
        return DURATION_S

    def profile(self) -> ClientProfile:
        return self.profile_value


def fl_client_window(client_id: str, window_index: int) -> FlClientWindowTrace:
    cohort = frozen_cohort()
    profile = next((item for item in cohort_profiles() if item.client_id == client_id), None)
    frozen = next((item for item in cohort.clients if item.client_id == client_id), None)
    if profile is None or frozen is None or profile.participant_id != frozen.participant_id:
        raise ValueError("UNKNOWN_OR_MISMATCHED_FL_CLIENT")
    trace = reconstruct_window(
        _FlProfileAdapter(profile), window_index, session_id=profile.session_id,
        records_factory=fl_observed_records,
    )
    eligible = (trace.quality_state == "VALID" and trace.missing_slots == 0
                and trace.normalization.status == "RECONSTRUCTED_MODEL_INPUT")
    label = (int(SyntheticEventLabelProvider(profile).labels_for_windows(
        [trace.right_timestamp_us])[0]) if eligible else None)
    return FlClientWindowTrace(
        client_id=client_id, participant_id=profile.participant_id,
        cohort_manifest_sha256=cohort.source_sha256,
        label_contract="WEARABLE_SIM_EVENT_WINDOW_V1", training_eligible=eligible,
        engineering_label=label, claim_boundary="SYNTHETIC_EVENT_LABEL_NOT_AAMI_SVF_TARGET",
        signal=trace,
    )


def frozen_cohort() -> FrozenCohort:
    raw = MANIFEST.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_MANIFEST_SHA256:
        raise ValueError("FROZEN_COHORT_MANIFEST_HASH_MISMATCH")
    source = json.loads(raw)
    clients = tuple(FrozenClient(
        client_id=item["client_id"], participant_id=item["participant_id"],
        session_id=item["session_id"], source_rate_hz=item["source_rate_hz"],
        scenario=", ".join(item["coverage"]), windows_emitted=item["counts"]["windows_emitted"],
        valid=item["counts"]["VALID"], degraded=item["counts"]["DEGRADED"],
        unusable=item["counts"]["UNUSABLE"], trainable=item["counts"]["trainable"],
        synthetic_positive=item["counts"]["synthetic_positive"],
        synthetic_negative=item["counts"]["synthetic_negative"],
        dataset_sha256=item["dataset_sha256"], faults=tuple(tuple(f) for f in item["faults"]),
    ) for item in source["clients"])
    return FrozenCohort(
        cohort_id="WEARABLE_SIM_FL_COHORT_V1",
        source_relative_path=str(MANIFEST.relative_to(MANIFEST.parents[3])),
        source_sha256=digest,
        label_contract="WEARABLE_SIM_EVENT_WINDOW_V1",
        claim_boundary="SYNTHETIC_ENGINEERING_DATA_NOT_AAMI_SVF_EFFICACY", clients=clients,
    )


def _attested_final_updates(
    run: FederationRun, artifacts: FederationArtifactStore, store: FederationStore,
    training: dict[str, Any], committed: dict[str, str], cohort_ids: set[str],
    reported_rounds: dict[int, FederationRound],
) -> dict[str, str] | None:
    """Recover final-round identity only from server journal + persisted governance attestation.

    A client SUBMITTED event alone is insufficient. The frozen governance check consumed the
    actual coordinator-accepted digest map and proved it equal to all published digests for
    every client in every round; the journal binds each published digest to a client and
    its recorded example count. Missing or contradictory evidence leaves the map unknown.
    """
    if run.status is not RunState.COMPLETED or not run.candidate_ids:
        return None
    final = run.planned_rounds
    key = str(final)
    if (final not in reported_rounds
            or reported_rounds[final].accepted_update_count != len(cohort_ids)):
        return None
    if len(run.candidate_ids) != 1:
        return None
    candidate_id = run.candidate_ids[0]
    candidate = store.get_candidate(candidate_id)
    decisions = store.list_decisions(candidate_id)
    if (candidate is None or candidate["federation_run_id"] != run.run_id
            or candidate["state_digest"] != committed.get(key)
            or candidate["governance_status"] != "ACCEPTED_TO_SANDBOX"
            or candidate["validation_status"] != "PASSED"
            or candidate["sandbox_status"] != "IN_SANDBOX"
            or candidate["production_deployed"] != 0 or len(decisions) != 1
            or decisions[0]["decision"] != "ACCEPTED_TO_SANDBOX"
            or decisions[0]["scientific_promotion"] != 0
            or decisions[0]["production_deployed"] != 0):
        return None
    checks = json.loads(decisions[0]["checks_json"])
    if ({item.get("check_id") for item in checks if item.get("passed") is True}
            != {"STATE_FINITE", "STATE_SPEC_MATCHES_BASE", "UPDATE_DIGESTS_RECONCILE",
                "ROUND_ACCEPTED_UPDATE_COUNT_COMPLETE", "BASE_STATE_LINEAGE_VERIFIED"}
            or len(checks) != 5):
        return None
    events = artifacts.read_events(run.run_id)
    if not events or [item.sequence_index for item in events] != list(range(len(events))) \
            or any(item.run_id != run.run_id for item in events):
        return None
    published: dict[str, str] = {}
    aggregate_seen = False
    for index, event in enumerate(events):
        body = event.model_dump(mode="json")
        payload = body["payload"]
        if body["event_type"] == "client.update_ready" and payload["round_id"] == final:
            client_id = payload["client_id"]
            record = training.get(key, {}).get(client_id)
            if (client_id not in cohort_ids or client_id in published or record is None
                    or record.get("update_sha256") != payload["update_digest"]
                    or int(record.get("examples_seen", 0)) != payload["examples_seen"]
                    or index + 1 >= len(events)):
                return None
            successor = events[index + 1].model_dump(mode="json")
            if (successor["event_type"] != "client.status"
                    or successor["payload"].get("client_id") != client_id
                    or successor["payload"].get("client_state") != "SUBMITTED"):
                return None
            published[client_id] = payload["update_digest"]
        if (body["event_type"] == "aggregation.status" and payload["round_id"] == final):
            if aggregate_seen or payload["accepted_updates"] != len(cohort_ids) \
                    or payload["state_digest"] != committed.get(key) \
                    or payload["aggregation_mode"] != "PLAIN":
                return None
            aggregate_seen = True
    return published if aggregate_seen and set(published) == cohort_ids else None


def run_contributions(run: FederationRun, artifacts: FederationArtifactStore,
                      reported_rounds: tuple[FederationRound, ...] = (),
                      federation_store: FederationStore | None = None) -> RunContributions:
    cohort = frozen_cohort()
    round_reports = {round_item.round_id: round_item for round_item in reported_rounds}
    meta = artifacts.read_run_meta(run.run_id) or {}
    if run.run_type is RunType.REPLAY:
        return RunContributions(
            run_id=run.run_id, run_type=run.run_type.value, run_status=run.status.value,
            algorithm=run.algorithm.value, source_run_id=meta.get("replay_source_run_id"),
            evidence_status="NO_TRAINING_IN_REPLAY", cohort_manifest_sha256=cohort.source_sha256,
            reported_total_accepted_updates=None,
            claim_boundary="ENGINEERING_SAMPLE_WEIGHT_NOT_ACCURACY_OR_EFFICACY", rounds=(),
        )
    training = meta.get("training_record", {})
    events = artifacts.read_events(run.run_id)
    submitted: set[tuple[int, str]] = set()
    ready: set[tuple[int, str, str]] = set()
    for index, event in enumerate(events):
        if event.event_type != "client.update_ready":
            continue
        payload = event.model_dump(mode="json")["payload"]
        round_id, client_id, digest = (payload["round_id"], payload["client_id"],
                                        payload["update_digest"])
        ready.add((round_id, client_id, digest))
        if index + 1 < len(events):
            successor = events[index + 1]
            if successor.event_type == "client.status":
                status = successor.model_dump(mode="json")["payload"]
                if status["client_id"] == client_id and status["client_state"] == "SUBMITTED":
                    submitted.add((round_id, client_id))
    accepted = dict(meta.get("coordinator_digests", {}))
    # Round-boundary checkpoints preserve coordinator acceptance maps. The final
    # candidate round currently has no checkpoint and the run summary does not
    # persist that map: do not infer it from SUBMITTED UI state.
    latest = artifacts.latest_checkpoint_round(run.run_id)
    if latest is not None:
        checkpoint, _ = artifacts.read_checkpoint(run.run_id, latest)
        accepted.update(checkpoint.get("coordinator_digests", {}))
    bases = meta.get("round_base_digests", {})
    committed = meta.get("committed_digests", {})
    observed = read_acceptance_capture(artifacts, run.run_id)
    captured_diagnostics: dict[str, dict[str, LocalTrainingDiagnostic]] = {}
    if observed is not None:
        if (run.status is not RunState.COMPLETED
                or observed.get("candidate_id") not in run.candidate_ids
                or observed.get("planned_rounds") != run.planned_rounds
                or set(observed.get("rounds", {})) != {
                    str(index) for index in range(1, run.planned_rounds + 1)
                }):
            raise ValueError("OBSERVATORY_ACCEPTANCE_CAPTURE_RUN_MISMATCH")
        if federation_store is not None:
            candidate = federation_store.get_candidate(observed["candidate_id"])
            if (candidate is None or candidate["federation_run_id"] != run.run_id
                    or candidate["state_digest"] != committed.get(str(run.planned_rounds))):
                raise ValueError("OBSERVATORY_ACCEPTANCE_CAPTURE_CANDIDATE_MISMATCH")
        for key, item in observed["rounds"].items():
            digests = item["accepted_updates"]
            if (item["base_state_digest"] != bases.get(key)
                    or item["committed_state_digest"] != committed.get(key)
                    or (key in accepted and accepted[key] != digests)
                    or set(item["training"]) != set(digests)):
                raise ValueError("OBSERVATORY_ACCEPTANCE_CAPTURE_LINEAGE_MISMATCH")
            for client_id, digest in digests.items():
                record = training.get(key, {}).get(client_id)
                if (record is None or digest != record.get("update_sha256")
                        or item["training"][client_id] != {
                            "examples_seen": int(record["examples_seen"]),
                            "update_sha256": digest,
                        }):
                    raise ValueError("OBSERVATORY_ACCEPTANCE_CAPTURE_TRAINING_MISMATCH")
            accepted[key] = digests
        for key, by_client in observed.get("local_training_diagnostics", {}).items():
            if key not in observed["rounds"] or not isinstance(by_client, dict):
                raise ValueError("OBSERVATORY_TRAINING_DIAGNOSTIC_ROUND_MISMATCH")
            captured_diagnostics[key] = {}
            for client_id, raw in by_client.items():
                record = training.get(key, {}).get(client_id)
                if record is None or client_id not in observed["rounds"][key]["training"]:
                    raise ValueError("OBSERVATORY_TRAINING_DIAGNOSTIC_CLIENT_MISMATCH")
                diagnostic = LocalTrainingDiagnostic.model_validate(raw)
                if (diagnostic.examples_seen != int(record["examples_seen"])
                        or diagnostic.shuffle_seed != str(record["shuffle_seed"])):
                    raise ValueError("OBSERVATORY_TRAINING_DIAGNOSTIC_RECORD_MISMATCH")
                captured_diagnostics[key][client_id] = diagnostic
    round_ids = sorted({int(k) for k in (*training, *accepted, *bases, *committed)}
                       | set(round_reports))
    result: list[RoundContribution] = []
    cohort_ids = {client.client_id for client in cohort.clients}
    attested_final = (_attested_final_updates(
        run, artifacts, federation_store, training, committed, cohort_ids, round_reports)
        if federation_store is not None and str(run.planned_rounds) not in accepted else None)
    for round_id in round_ids:
        key = str(round_id)
        trained = training.get(key, {})
        acceptance_recorded = key in accepted or (round_id == run.planned_rounds
                                                   and attested_final is not None)
        accepted_digests = (attested_final if round_id == run.planned_rounds
                            and key not in accepted and attested_final is not None
                            else accepted.get(key, {}))
        attested = round_id == run.planned_rounds and key not in accepted \
            and attested_final is not None
        if set(trained) - cohort_ids or set(accepted_digests) - cohort_ids:
            raise ValueError("RUN_CONTAINS_UNKNOWN_SYNTHETIC_CLIENT")
        accepted_counts: dict[str, int] = {}
        for client_id, digest in accepted_digests.items():
            record = trained.get(client_id)
            if record is None or record.get("update_sha256") != digest:
                raise ValueError("ACCEPTED_UPDATE_TRAINING_DIGEST_MISMATCH")
            accepted_counts[client_id] = int(record["examples_seen"])
            if accepted_counts[client_id] <= 0:
                raise ValueError("ACCEPTED_EXAMPLE_COUNT_INVALID")
        total = sum(accepted_counts.values())
        reported_count = (round_reports[round_id].accepted_update_count
                          if round_id in round_reports else None)
        if (acceptance_recorded and reported_count is not None
                and reported_count != len(accepted_digests)):
            raise ValueError("ROUND_ACCEPTED_COUNT_MISMATCH")
        clients: list[ClientContribution] = []
        for client in cohort.clients:
            record = trained.get(client.client_id)
            accepted_count = accepted_counts.get(client.client_id)
            clients.append(ClientContribution(
                client_id=client.client_id, local_trainable_windows=client.trainable,
                examples_seen=int(record["examples_seen"]) if record else None,
                shuffle_seed=str(record["shuffle_seed"]) if record else None,
                update_digest=record.get("update_sha256") if record else None,
                training_completed=True if record else None,
                update_produced=(round_id, client.client_id, record["update_sha256"]) in ready
                if record and events else (True if record else None),
                update_submitted=(round_id, client.client_id) in submitted
                if record and events else None,
                accepted=(client.client_id in accepted_digests)
                if record and acceptance_recorded else None,
                aggregated=bool(committed.get(key)) if accepted_count is not None else
                (False if record and acceptance_recorded else None),
                accepted_examples=accepted_count,
                weight=accepted_count / total if accepted_count is not None and total else None,
                training_diagnostic=captured_diagnostics.get(key, {}).get(client.client_id),
                evidence_state=("DIRECT_OBSERVED_ACCEPTED" if observed is not None
                                and accepted_count is not None else
                                "GOVERNANCE_ATTESTED_ACCEPTED" if attested
                                and accepted_count is not None else
                                "ACCEPTED" if accepted_count is not None else
                                "NOT_ACCEPTED" if record and acceptance_recorded else
                                "TRAINED_ACCEPTANCE_NOT_RECORDED" if record else "NOT_RECORDED"),
            ))
        result.append(RoundContribution(
            round_id=round_id, base_state_digest=bases.get(key),
            committed_state_digest=committed.get(key),
            accepted_update_count=len(accepted_digests) if acceptance_recorded else None,
            reported_accepted_update_count=reported_count,
            accepted_example_total=total if acceptance_recorded else None,
            acceptance_basis=("DIRECT_OBSERVED_COORDINATOR_MAP" if observed is not None else
                              "GOVERNANCE_ATTESTED_SERVER_JOURNAL" if attested else
                              "DIRECT_COORDINATOR_MAP" if key in accepted else "NOT_RECORDED"),
            clients=tuple(clients),
        ))
    return RunContributions(
        run_id=run.run_id, run_type=run.run_type.value, run_status=run.status.value,
        algorithm=run.algorithm.value, source_run_id=meta.get("replay_source_run_id"),
        evidence_status="RUN_ARTIFACT_METADATA" if result else "NOT_RECORDED",
        cohort_manifest_sha256=cohort.source_sha256,
        reported_total_accepted_updates=(sum(item.accepted_update_count for item in reported_rounds)
                                         if reported_rounds else None),
        claim_boundary="ENGINEERING_SAMPLE_WEIGHT_NOT_ACCURACY_OR_EFFICACY", rounds=tuple(result),
    )
