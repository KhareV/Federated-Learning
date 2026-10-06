# ruff: noqa: E501
"""CLERK-LIVE-001: pure checks (secret scanning, static audits, WebSocket/ownership/identity/noninterference evidence rules)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from scripts import clerk_connected_lib as lib

ROOT = Path(__file__).resolve().parents[1]
SECRET = "sk_test_" + "Q" * 30


def test_find_secret_reports_paths_never_values(tmp_path) -> None:
    (tmp_path / "a.js").write_text("clean")
    (tmp_path / "b.js").write_text(f"x = '{SECRET}'")
    assert lib.find_secret(tmp_path, SECRET) == ["b.js"] and lib.find_secret(tmp_path, "") == []
    assert lib.secret_prefix_hits(tmp_path) == ["b.js"]


def test_sqlite_secret_and_token_detection(tmp_path) -> None:
    db = tmp_path / "p.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute("create table users (user_id text, display_name text)")
    conn.execute("insert into users values ('user_1', 'ok')")
    conn.commit()
    assert lib.sqlite_secret_hits(db, SECRET) == []
    conn.execute("insert into users values ('user_2', ?)", (SECRET,))
    conn.commit()
    assert lib.sqlite_secret_hits(db, SECRET) == ["users"]
    conn.execute("delete from users where user_id='user_2'")
    conn.execute("insert into users values ('user_3', 'eyJhbGciOiJSUzI1NiJ9abc.eyJzdWIiOiJ1c2VyIn0abcd.sig')")
    conn.commit()
    conn.close()
    assert lib.sqlite_secret_hits(db, SECRET) == ["users"]


def test_repository_passes_the_frontend_and_backend_static_audits() -> None:
    assert lib.frontend_static_audit(ROOT) == {"ok": True, "failures": []}
    assert lib.backend_static_audit(ROOT) == {"ok": True, "failures": []}
    assert lib.fl_isolation_static(ROOT) == {"ok": True, "failures": []}


def test_static_audits_catch_each_violation(tmp_path) -> None:
    shutil.copytree(ROOT / "frontend/src", tmp_path / "frontend/src")
    shutil.copy(ROOT / "frontend/vite.config.ts", tmp_path / "frontend/vite.config.ts")
    probe = tmp_path / "frontend/src/lib/product/leak.ts"
    for body, failure in ((f"const k = '{SECRET}';", "frontend_source_contains_secret"), ("const k = import.meta.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;", "frontend_reads_NEXT_PUBLIC"), ("// CLERK_SECRET_KEY", "frontend_references_secret_variable")):
        probe.write_text(body)
        assert failure in lib.frontend_static_audit(tmp_path, SECRET)["failures"], failure
    probe.unlink()
    (tmp_path / "product/auth").mkdir(parents=True)
    (tmp_path / "api").mkdir()
    (tmp_path / "product/auth/clerk.py").write_text("from clerk_backend_api.security import authenticate_request_async\n")
    assert lib.backend_static_audit(tmp_path)["ok"]
    (tmp_path / "product/auth/custom.py").write_text("import jwt\n")
    assert not lib.backend_static_audit(tmp_path)["ok"]
    (tmp_path / "product/auth/custom.py").unlink()
    (tmp_path / "product/auth/clerk.py").write_text("x = 1\n")
    assert "official_sdk_not_used" in lib.backend_static_audit(tmp_path)["failures"]
    (tmp_path / "product/federation").mkdir(parents=True)
    (tmp_path / "product/federation/leak.py").write_text("from product.history import x\n")
    assert not lib.fl_isolation_static(tmp_path)["ok"]


GOOD_WS = {"handshakeStatus": 101, "urlHasToken": False, "cookieSessionSent": True, "framesReceived": 5, "sessionIdInPathIsOwned": True}


def test_websocket_evidence_rules() -> None:
    assert lib.ws_evidence_ok(GOOD_WS, "sessionIdInPathIsOwned")
    for bad in ({"urlHasToken": True}, {"handshakeStatus": 400}, {"cookieSessionSent": False}, {"framesReceived": 0}, {"sessionIdInPathIsOwned": False}):
        assert not lib.ws_evidence_ok({**GOOD_WS, **bad}, "sessionIdInPathIsOwned")
    assert lib.unauth_ws_rejected({"closeCode": 4401, "frames": 0}) and not lib.unauth_ws_rejected({"closeCode": 1000, "frames": 3})


def test_ownership_rules() -> None:
    probes = [{"label": "read A session", "rewritten": True, "app_bearer_kept": True, "status": 403}, {"label": "CONTROL: nonexistent session", "rewritten": True, "app_bearer_kept": True, "status": 404}, {"label": "CONTROL: global research view", "rewritten": True, "app_bearer_kept": True, "status": 200}]
    ws = {"monitoring": {"closeCode": 4403, "frames": 0}, "federation": {"closeCode": 4403, "frames": 0}}
    ui = [{"target": "session", "status": 403}]
    assert lib.ownership_ok(ui, probes, ws)["ok"]
    assert not lib.ownership_ok(ui, [{**probes[0], "status": 200}, *probes[1:]], ws)["ok"]
    assert not lib.ownership_ok(ui, probes, {**ws, "monitoring": {"closeCode": None, "frames": 9}})["ok"]
    assert not lib.ownership_ok([{"target": "session", "status": 200}], probes, ws)["ok"]


def test_identity_candidate_and_noninterference_rules() -> None:
    system = {"auth_provider": "CLERK", "demo_mode": False, "model_id": "MODEL_V2_FINAL", "software_system": "SOFTWARE_SYSTEM_V2", "product_api_implementation": "CAPSTONE_PRODUCT_API_V1_3"}
    me = {"status": 200, "auth_provider": "CLERK", "demo_mode": False, "user_id_is_clerk_shaped": True, "user_id_is_demo": False}
    assert lib.identity_ok(system, me)["ok"]
    assert not lib.identity_ok({**system, "auth_provider": "DEMO", "demo_mode": True}, me)["ok"]
    assert not lib.identity_ok(system, {**me, "user_id_is_demo": True, "user_id_is_clerk_shaped": False})["ok"]
    models = {"candidate": [{"production_deployed": False, "governance_status": "ACCEPTED_TO_SANDBOX", "sandbox_status": "IN_SANDBOX", "state_digest": "abc"}], "released_default": "MODEL_V2_FINAL", "controls": []}
    assert lib.candidate_ok(models)["ok"]
    assert not lib.candidate_ok({**models, "candidate": [{**models["candidate"][0], "production_deployed": True}]})["ok"]
    assert lib.noninterference_ok(models, {"model_id": "MODEL_V2_FINAL"}, "abc", {"model_id": "MODEL_V2_FINAL"})["ok"]
    assert not lib.noninterference_ok(models, {"model_id": "MODEL_V2_FINAL"}, "different", {})["ok"]
    assert not lib.noninterference_ok(models, {"model_id": "CAPSTONE_FL_CANDIDATE_0001"}, "abc", {})["ok"]
    assert lib.tag_ok(lib.HISTORICAL_RELEASE_TARGET) and not lib.tag_ok("0" * 40)
