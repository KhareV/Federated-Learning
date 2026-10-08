# ruff: noqa: E501
"""OBS-DIAG-001 parity: the same 8-client / 3-round FedAvg run with Observatory capture OFF versus sidecar + per-batch capture ON.
Compares update digests, examples, shuffle seeds, round base/committed digests, candidate digest + governance, and the deterministic event semantics
(timestamps and generated ids removed). Also checks that every per-batch table reproduces the end-of-epoch summary. Observations only.
  python -m scripts.observatory_fl_parity --out reports/observatory/obs_diag_001/fl_batch_parity.json"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.product_app_observatory_v1 import create_product_app_observatory_v1
from capstone_persistence.store import CapstoneSqliteStore
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver
from tests.capstone_federation_support import DESCRIPTION, SINGLE_RUN, RunIds, poll_run
from tests.capstone_product_support import BASE, USER_A

DROP = ("event_id", "run_id", "emitted_at", "created_at", "timestamp", "_us", "sequence_digest")


def run_once(root: Path, *, sidecar: bool, batch: bool) -> dict[str, Any]:
    app = create_product_app_observatory_v1(
        store=CapstoneSqliteStore(root / "product.sqlite3"), identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
        federation_artifact_root=root / "federation", candidate_root=root / "candidates", run_id_generator=RunIds("FEDRUN-PARITY"),
        auto_resume=False, acceptance_sidecar=sidecar, batch_capture=batch)
    with TestClient(app) as client:
        run_id = client.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).json()["run_id"]
        client.post(f"{BASE}/federation/runs/{run_id}/start", headers=USER_A)
        run = poll_run(client, run_id, USER_A)
        models = client.get(f"{BASE}/models", headers=USER_A).json()
        contributions = client.get(f"{BASE}/observatory/federation/runs/{run_id}/contributions", headers=USER_A).json()
    service = app.state.federation_service
    meta = service.artifacts.read_run_meta(run_id)

    def semantic(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: semantic(v) for k, v in sorted(value.items()) if not any(token in k for token in DROP)}
        if isinstance(value, list):
            return [semantic(v) for v in value]
        return value

    events = [semantic(e.model_dump(mode="json")) for e in service.journal_for(run_id).events]
    training = {rnd: {cid: {"update_sha256": rec.get("update_sha256"), "examples_seen": rec.get("examples_seen"), "shuffle_seed": str(rec.get("shuffle_seed"))} for cid, rec in sorted(by.items())} for rnd, by in sorted(meta["training_record"].items())}
    candidate = models["capstone_fl_candidates"][0]
    return {"status": run["status"], "training": training, "round_base_digests": meta["round_base_digests"], "committed_digests": meta["committed_digests"],
            "candidate": {k: candidate[k] for k in ("state_digest", "governance_status", "sandbox_status", "production_deployed", "client_count", "algorithm")},
            "events": events, "contributions": contributions}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    off = run_once(Path(tempfile.mkdtemp(prefix="obsdiag-off-")), sidecar=False, batch=False)
    on = run_once(Path(tempfile.mkdtemp(prefix="obsdiag-on-")), sidecar=True, batch=True)
    batches, consistent = 0, True
    for rnd in on["contributions"]["rounds"]:
        for client in rnd["clients"]:
            readout = client.get("training_diagnostic")
            if not readout or not readout.get("per_batch"):
                consistent = False
                continue
            rows = readout["per_batch"]["batches"]
            batches += len(rows)
            consistent &= len(rows) == readout["batch_count"] and sum(b["batch_size"] for b in rows) == readout["examples_seen"]
            consistent &= abs(sum(b["loss"] * b["batch_size"] for b in rows) / readout["examples_seen"] - readout["mean_loss_diagnostic_only"]) < 1e-9
    off_contrib_ok = all(not (c.get("training_diagnostic") or {}).get("per_batch") for r in off["contributions"]["rounds"] for c in r["clients"])
    checks = {"both_completed": off["status"] == on["status"] == "COMPLETED", "update_digests_and_examples_identical": off["training"] == on["training"],
              "round_base_digests_identical": off["round_base_digests"] == on["round_base_digests"], "committed_digests_identical": off["committed_digests"] == on["committed_digests"],
              "candidate_identical": off["candidate"] == on["candidate"], "event_semantics_identical": off["events"] == on["events"], "event_count": len(on["events"]),
              "per_batch_rows_total": batches, "per_batch_reproduces_epoch_summary": bool(consistent), "capture_off_run_has_no_per_batch": off_contrib_ok,
              "accepted_contributions_identical": [[(c["client_id"], c["accepted_examples"], c["update_digest"]) for c in r["clients"]] for r in off["contributions"]["rounds"]] == [[(c["client_id"], c["accepted_examples"], c["update_digest"]) for c in r["clients"]] for r in on["contributions"]["rounds"]]}
    verdict = all(v is True for k, v in checks.items() if isinstance(v, bool)) and batches == 48
    report = {"status": "PASS" if verdict else "FAIL", "checks": checks, "candidate": on["candidate"],
              "note": "Same protocol and run id; only the Observatory observers differ. A PASS shows observation did not change update digests, round states, the candidate digest or event semantics."}
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"status": report["status"], **{k: v for k, v in checks.items() if v is not True}}, default=str)[:600])
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
