# ruff: noqa: E501
"""The Observatory's PTB-XL external-check view: read from the stored report, protocol hash verified, fail closed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import observatory_external_check as oc

ROOT = Path(__file__).resolve().parents[1]


def test_the_view_is_read_from_the_stored_report_and_names_its_hashes():
    v = oc.view()
    report = json.loads((ROOT / oc.REPORT).read_text())
    assert v["classification"] == "FROZEN_EXTENSION_EVIDENCE" and "NOT AAMI-SVF" in v["label"] and "NOT CLINICAL" in v["label"]
    assert v["protocol"]["verified"] is True and v["protocol"]["sha256"] == report["protocol"]["sha256"] and len(v["report"]["sha256"]) == 64
    primary, replication = v["sets"]
    assert primary["name"].startswith("primary") and replication["name"].startswith("replication") and primary["records"] == 4336 and primary["positives"] == 476
    base = next(r for r in primary["rows"] if r["model"] == "MODEL_V2_FINAL (central)")
    assert base["AUROC"] == report["sets"][primary["name"]]["rule A"]["models"]["MODEL_V2_FINAL (central)"]["AUROC"] and base["paired_vs_central_V2"] is None
    v1 = next(r for r in primary["rows"] if r["model"].startswith("MODEL_V1"))
    assert v1["paired_vs_central_V2"]["AUROC"]["delta"] < -0.15 and v1["paired_vs_central_V2"]["AUROC"]["ci95"][1] < 0       # V1 is clearly worse, interval excludes zero
    assert [r["rule"] for r in v["label_rules"]][:3] == ["rule A", "rule B", "rule C"] and v["label_agreement"]["both"] == 1052


def test_a_changed_protocol_fails_closed(tmp_path):
    for rel in (oc.REPORT, "docs/ptbxl/PTBXL_EXTERNAL_CHECK_V1.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    assert oc.view(tmp_path)["protocol"]["verified"] is True
    (tmp_path / "docs/ptbxl/PTBXL_EXTERNAL_CHECK_V1.md").write_text("amended after the results existed\n")
    with pytest.raises(oc.ExternalCheckError, match="PROTOCOL_HASH_MISMATCH"):
        oc.view(tmp_path)
    with pytest.raises(oc.ExternalCheckError, match="REPORT_MISSING"):
        oc.view(tmp_path / "nowhere")


def test_the_route_needs_an_identity_and_returns_the_view():
    app = FastAPI()

    async def identity(request):
        return "user-a"

    oc.register(app, "/product/v1/observatory", identity)
    r = TestClient(app).get("/product/v1/observatory/evidence/external-check")
    assert r.status_code == 200 and r.json()["target"] == "PTBXL_PREMATURE_BEAT_RECORD_V1" and r.json()["protocol"]["verified"] is True
