# ruff: noqa: E501
"""CAP-007: CAPSTONE_FEDERATION_RECOVERY_V1 (restart after round 2, invalid checkpoints, orphans)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import tempfile
from pathlib import Path

from capstone_persistence.federation_store import FederationStore
from capstone_persistence.store import CapstoneSqliteStore
from federated.wearable_fl_runner_v1 import new_session
from product.auth.base import AuthIdentity, AuthProviderType
from product.federation.artifact_store import FederationArtifactStore
from product.federation.replay import semantic_projection
from product.federation.service import FederationService
from product.models.candidate_artifacts import CandidateArtifactStore
from product.models.governance import GovernanceRuntime
from product.models.registry import ModelRegistry
from tests.capstone_federation_support import SINGLE_RUN, completed_run

USER = "demo:cap003-user-a"


class SimulatedCrash(BaseException):
    """Stands in for a killed process (the hook fires right after the round checkpoint is durable)."""


def _service(root: Path, hook=None) -> FederationService:
    store = CapstoneSqliteStore(root / "product.sqlite3")
    store.upsert_user(AuthIdentity(user_id=USER, display_name="a", auth_provider=AuthProviderType.DEMO,
                                   auth_session_id="s", demo_mode=True))
    fed = FederationStore(root / "product.sqlite3")
    return FederationService(
        store=fed, artifacts=FederationArtifactStore(root / "federation"),
        registry=ModelRegistry(fed, CandidateArtifactStore(root / "candidates")),
        governance=GovernanceRuntime(fed), id_generator=lambda: "FEDRUN-R0001", checkpoint_hook=hook)


def _crash_after(round_id: int):
    def hook(run_id: str, completed: int) -> None:
        if completed == round_id:
            raise SimulatedCrash(f"{run_id}@{completed}")
    return hook


def _crashed_run() -> Path:
    root = Path(tempfile.mkdtemp(prefix="cap007-recovery-"))

    async def first_process() -> None:
        svc = _service(root, _crash_after(2))
        run = svc.create_run(USER, **SINGLE_RUN)
        await svc.start_run(USER, run.run_id)
        with contextlib.suppress(SimulatedCrash):
            await svc.wait(run.run_id)

    asyncio.run(first_process())
    return root


def test_restart_after_round_two_resumes_round_three_with_the_identical_final_digest() -> None:
    root = _crashed_run()
    fed = FederationStore(root / "product.sqlite3")
    row = fed.get_run("FEDRUN-R0001")
    assert row["status"] == "RUNNING"  # the crashed process never finished it
    assert [r["state"] for r in fed.list_rounds("FEDRUN-R0001")][:2] == ["COMPLETED", "COMPLETED"]
    assert fed.list_candidates() == []
    # an orphan artifact (written, row never committed) must not make the resumed run allocate 0002
    ModelRegistry(fed, CandidateArtifactStore(root / "candidates")).artifacts.write(
        "CAPSTONE_FL_CANDIDATE_0001", new_session()[0], {"federation_run_id": "FEDRUN-R0001"})

    async def second_process() -> list[dict]:
        svc = _service(root)  # a fresh service object over the same files = a new process
        report = await svc.recover()
        await svc.wait("FEDRUN-R0001")
        return report

    report = asyncio.run(second_process())
    assert report == [{"run_id": "FEDRUN-R0001", "action": "RESUME", "reason": "VALID_CHECKPOINT",
                       "last_committed_round": 2}]
    fed = FederationStore(root / "product.sqlite3")
    done = completed_run()
    meta = FederationArtifactStore(root / "federation").read_run_meta("FEDRUN-R0001")
    assert fed.get_run("FEDRUN-R0001")["status"] == "COMPLETED"
    assert meta["final_global_state_sha256"] == done.meta["final_global_state_sha256"]
    assert meta["training_record"] == done.meta["training_record"]
    assert fed.candidate_ids_for_run("FEDRUN-R0001") == ["CAPSTONE_FL_CANDIDATE_0001"]
    counts = fed.counts()
    assert counts == {"federation_runs": 1, "federation_rounds": 3, "fl_client_statuses": 24,
                      "candidate_models": 1, "governance_decisions": 1}
    events = FederationArtifactStore(root / "federation").read_events("FEDRUN-R0001")
    assert [e.sequence_index for e in events] == list(range(len(events)))
    assert semantic_projection(events) == semantic_projection(
        [e for e in _events_of(done)])  # the resumed stream equals the uninterrupted one
    updates = [e for e in events if e.event_type == "client.update_ready"]
    assert len(updates) == 24 and len({(e.payload.round_id, e.payload.client_id) for e in updates}) == 24


def _events_of(done):
    from product.events import parse_federation_event

    return [parse_federation_event(e) for e in done.events]


def _running_without_checkpoint() -> tuple[Path, FederationService]:
    root = Path(tempfile.mkdtemp(prefix="cap007-nockpt-"))
    svc = _service(root)
    run = svc.create_run(USER, **SINGLE_RUN)
    svc.store.update_run(run.run_id, status="RUNNING", started_at_us=1, current_round=1)
    return root, _service(root)


def test_a_running_run_without_a_valid_checkpoint_is_marked_failed_never_fabricated() -> None:
    root, svc = _running_without_checkpoint()
    report = asyncio.run(svc.recover())
    assert report[0]["action"] == "FAIL" and report[0]["reason"] == "NO_VALID_CHECKPOINT"
    fed = FederationStore(root / "product.sqlite3")
    assert fed.get_run("FEDRUN-R0001")["status"] == "FAILED"
    assert fed.list_candidates() == [] and fed.list_rounds("FEDRUN-R0001") == []


def test_corrupt_or_mismatched_checkpoints_fail_the_run() -> None:
    for damage in ("state", "binding", "events"):
        root = _crashed_run()
        base = root / "federation" / "runs" / "FEDRUN-R0001"
        ckpt = base / "checkpoints" / "round_2"
        if damage == "state":
            blob = bytearray((ckpt / "state.bin").read_bytes())
            blob[len(blob) // 2] ^= 0xFF
            (ckpt / "state.bin").write_bytes(bytes(blob))
            expected = "CHECKPOINT_STATE_FILE_HASH_MISMATCH"
        elif damage == "binding":
            record = json.loads((ckpt / "checkpoint.json").read_text())
            record["algorithm"] = "FEDPROX"
            (ckpt / "checkpoint.json").write_text(json.dumps(record))
            expected = "CHECKPOINT_BINDING_MISMATCH:algorithm"
        else:
            (base / "events.jsonl").write_text("")
            expected = "EVENT_LOG_SHORTER_THAN_CHECKPOINT"
        report = asyncio.run(_service(root).recover())
        assert report[0]["action"] == "FAIL" and report[0]["reason"] == expected, damage
        assert FederationStore(root / "product.sqlite3").get_run("FEDRUN-R0001")["status"] == "FAILED"
        shutil.rmtree(root)


def test_recovery_is_a_no_op_for_finished_runs_and_for_runs_owned_by_this_process() -> None:
    done = completed_run()
    svc = _service(done.root)
    assert asyncio.run(svc.recover()) == []
