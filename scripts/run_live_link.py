# ruff: noqa: E501
"""Opt-in live-monitored SITE_00 federation, end to end, against a FRESH released inference process (real MODEL_V2_FINAL + CAL_V2 monitoring).
  python -m scripts.run_live_link --out reports/final_showcase/live_link
Writes live_link_result.json (status, parity, digests) and keeps the run root so the synthetic evaluation can load the live-source candidate."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from api.product_app_observatory_v1 import create_product_app_observatory_v1
from capstone_persistence.store import CapstoneSqliteStore
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver
from scripts.run_capstone_monitoring_e2e import launch_released_inference
from tests.capstone_federation_support import DESCRIPTION, RunIds
from tests.capstone_product_support import BASE, USER_A

CANONICAL_CANDIDATE_DIGEST = "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--root")
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(tempfile.mkdtemp(prefix="live-link-"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with launch_released_inference() as (base, info):
        app = create_product_app_observatory_v1(store=CapstoneSqliteStore(root / "product.sqlite3"), identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
                                                inference_base_url=base, federation_artifact_root=root / "federation", candidate_root=root / "candidates", run_id_generator=RunIds("FEDRUN-LIVE"), auto_resume=False)
        with TestClient(app) as client:
            started = client.post(f"{BASE}/observatory/live-link/runs", headers=USER_A)
            assert started.status_code == 200, started.text
            link_id = started.json()["link_id"]
            deadline = time.time() + 900
            while time.time() < deadline:
                body = client.get(f"{BASE}/observatory/live-link/runs/{link_id}", headers=USER_A).json()
                if body["phase"] in ("COMPLETED", "BLOCKED") or body["phase"].startswith("RUN_"):
                    break
                time.sleep(1.0)
            disarmed = not app.state.live_link_provider.armed
    result = {**body, "disarmed_after_run": disarmed, "inference_service": {k: info.get(k) for k in ("fresh_process", "profile", "service_title")}, "run_root": str(root),
              "canonical_candidate_digest": CANONICAL_CANDIDATE_DIGEST,
              "candidate_digest_equals_canonical": body.get("candidate_state_digest") == CANONICAL_CANDIDATE_DIGEST if body.get("candidate_state_digest") else None}
    (out / "live_link_result.json").write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: result.get(k) for k in ("phase", "status", "run_id", "candidate_ids", "candidate_state_digest", "candidate_digest_equals_canonical", "blocked")}, default=str))
    print(json.dumps(result.get("parity"), default=str)[:900])
    return 0 if result["phase"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
