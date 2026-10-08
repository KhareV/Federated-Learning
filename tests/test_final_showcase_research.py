# ruff: noqa: E501
"""NHM-FINAL-SHOWCASE-001 workstreams C/D: frozen-evidence bundle, comparability audit, exports and routes."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from final_showcase import figures, research
from tests.capstone_federation_support import DESCRIPTION
from tests.capstone_product_support import BASE, USER_A


def test_bundle_matches_frozen_verification_targets():
    b = research.bundle()
    rows = {r["dataset"]: r for r in b["comparability"]["rows"]}
    assert round(rows["INTERNAL_TEST"]["centralized_V2_AUPRC"], 6) == 0.999473
    assert round(rows["INTERNAL_TEST"]["federated_V2_FedAvg_IID_AUPRC"], 6) == 0.998931
    assert round(rows["INCART"]["centralized_V2_AUPRC"], 6) == 0.970004
    assert round(rows["INCART"]["federated_V2_FedAvg_IID_AUPRC"], 6) == 0.976604
    assert len(b["models"]) == 40 and len(b["round_logs"]) == 10
    assert all(log["rounds"] == 50 for log in b["round_logs"].values())


def test_comparability_makes_no_superiority_claim():
    c = research.bundle()["comparability"]
    assert "NO SUPERIORITY" in c["verdict"] and len(c["interpretations"]) == 4
    assert any(x["item"] == "Paired uncertainty" and x["status"] == "NOT_AVAILABLE" for x in c["checks"])


def test_tampered_frozen_artifact_is_refused(monkeypatch, tmp_path):
    rel = "reports/model_v2/v2_fl_001/round_log.csv"
    (tmp_path / "reports/model_v2/v2_fl_001").mkdir(parents=True)
    (tmp_path / rel).write_text("round\n0\n")
    (tmp_path / "reports/model_v2/v2_fl_001/artifact_hashes.json").write_text(json.dumps({"artifacts": {rel: "0" * 64}}))
    monkeypatch.setattr(research, "ROOT", tmp_path)
    research._manifest.cache_clear()
    research.round_log.cache_clear()
    try:
        with pytest.raises(research.ResearchError, match="HASH_MISMATCH"):
            research.round_log("FedAvg", "iid")
    finally:
        research._manifest.cache_clear()
        research.round_log.cache_clear()


def test_synthetic_section_is_labelled_and_uses_none_for_undefined():
    s = research.bundle()["synthetic"]
    assert s["boundary_label"].startswith("SYNTHETIC ENGINEERING-EVENT CLASSIFICATION")
    assert s["states"]["round_0"]["pooled"]["precision"] is None and "precision" in s["states"]["round_0"]["undefined"]


def test_exports_are_complete_deterministic_and_hash_listed():
    a = Path(tempfile.mkdtemp())
    b = Path(tempfile.mkdtemp())
    ma, mb = figures.export_all(a), figures.export_all(b)
    assert len(ma["figures"]) == 6 and len(ma["tables"]) == 4
    for item in (*ma["figures"].values(), *ma["tables"].values()):
        for entry in item.values():
            assert hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
    assert {k: {e: v["sha256"] for e, v in f.items()} for k, f in ma["tables"].items()} == {k: {e: v["sha256"] for e, v in f.items()} for k, f in mb["tables"].items()}
    assert {k: v["svg"]["sha256"] for k, v in ma["figures"].items()} == {k: v["svg"]["sha256"] for k, v in mb["figures"].items()}
    t1 = (a / "tables/TAB1_ALL_MODELS.csv").read_text().splitlines()
    assert len(t1) == 41                      # header + 20 models x 2 datasets
    assert "UNDEFINED" not in (a / "tables/TAB3_SYNTHETIC_GLOBAL.csv").read_text()   # undefined stays blank, never a fake number


def test_committed_exports_match_regeneration():
    committed = json.loads((figures.OUT / "export_manifest.json").read_text())
    fresh = figures.export_all(Path(tempfile.mkdtemp()))
    assert {k: v["csv"]["sha256"] for k, v in committed["tables"].items()} == {k: v["csv"]["sha256"] for k, v in fresh["tables"].items()}


def test_routes_require_identity_and_serve_hashed_exports(tmp_path):
    from api.product_app_observatory_v1 import create_product_app_observatory_v1
    from capstone_persistence.store import CapstoneSqliteStore
    from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver

    app = create_product_app_observatory_v1(store=CapstoneSqliteStore(tmp_path / "p.sqlite3"), identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
                                            federation_artifact_root=tmp_path / "f", candidate_root=tmp_path / "c", auto_resume=False)
    with TestClient(app) as c:
        assert c.get(f"{BASE}/observatory/showcase/bundle").status_code == 401
        ok = c.get(f"{BASE}/observatory/showcase/bundle", headers=USER_A)
        assert ok.status_code == 200 and ok.json()["schema_version"] == research.SCHEMA
        csv = c.get(f"{BASE}/observatory/showcase/exports/TAB2_MAIN_COMPARISON/csv", headers=USER_A)
        assert csv.status_code == 200 and hashlib.sha256(csv.content).hexdigest() == csv.headers["x-content-sha256"]
        assert c.get(f"{BASE}/observatory/showcase/exports/TAB2_MAIN_COMPARISON/exe", headers=USER_A).status_code == 404
        assert c.get(f"{BASE}/observatory/showcase/exports/NOPE/csv", headers=USER_A).status_code == 404
