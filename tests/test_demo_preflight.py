# ruff: noqa: E501
"""The demo preflight: every check is a pure function with injected dependencies, so each outcome is tested without a network, a port or a database."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from scripts import demo_preflight as pf


def _key(host: str = "demo-example-1.clerk.accounts.dev") -> str:
    return "pk_test_" + base64.b64encode(f"{host}$".encode()).decode().rstrip("=")


def test_ports_fail_only_when_one_is_held():
    assert pf.check_ports(in_use=lambda p: False).status == "PASS"
    held = pf.check_ports(in_use=lambda p: p == 8002)
    assert held.status == "FAIL" and "8002" in held.detail and "earlier site" in held.detail


def test_clerk_host_is_decoded_from_the_publishable_key_and_never_printed_with_secrets():
    assert pf.clerk_host(_key()) == "demo-example-1.clerk.accounts.dev" and pf.clerk_host("garbage") is None
    env = {"CLERK_PUBLISHABLE_KEY": _key(), "CLERK_SECRET_KEY": "sk_test_SECRETVALUE"}
    ok = pf.check_clerk(env, connect=lambda addr, timeout: type("C", (), {"close": lambda self: None})())
    assert ok.status == "PASS" and "SECRETVALUE" not in ok.detail
    down = pf.check_clerk(env, connect=lambda addr, timeout: (_ for _ in ()).throw(OSError("offline")))
    assert down.status == "WARN" and "--demo" in down.detail                                    # offline authentication is the named fallback
    assert pf.check_env(env).status == "PASS" and pf.check_env({}).status == "FAIL" and "SECRETVALUE" not in pf.check_env(env).detail


def test_mongodb_reports_reachability_and_whether_demo_data_shares_the_real_database():
    class Client:
        admin = type("A", (), {"command": staticmethod(lambda c: {"ok": 1})})()

        def close(self):
            pass

    base = {"NHM_HARDWARE_MONGO_ENABLED": "true", "NHM_HARDWARE_MONGO_URI": "mongodb://secret-host", "NHM_HARDWARE_MONGO_DATABASE": "health_db"}
    assert pf.check_mongo({}).status == "PASS"                                                  # hardware source disabled: nothing to check
    shared = pf.check_mongo(base, factory=lambda uri: Client())
    assert shared.status == "WARN" and "share `health_db`" in shared.detail and "secret-host" not in shared.detail
    split = pf.check_mongo({**base, "NHM_HARDWARE_DEMO_DATABASE": "nhm_demo"}, factory=lambda uri: Client())
    assert split.status == "PASS" and "nhm_demo" in split.detail
    broken = pf.check_mongo(base, factory=lambda uri: (_ for _ in ()).throw(ConnectionError("no route")))
    assert broken.status == "WARN" and "not reachable" in broken.detail and "secret-host" not in broken.detail


def test_checkpoint_and_evidence_are_verified_against_their_own_manifests(tmp_path: Path):
    (tmp_path / "checkpoints").mkdir()
    (tmp_path / "checkpoints/MODEL_V2_FINAL.pt").write_bytes(b"weights")
    import hashlib

    manifest = {"checkpoint": {"sha256": hashlib.sha256(b"weights").hexdigest()}}
    (tmp_path / "checkpoints/MODEL_V2_FINAL.manifest.json").write_text(json.dumps(manifest))
    assert pf.check_checkpoint(tmp_path).status == "PASS"
    (tmp_path / "checkpoints/MODEL_V2_FINAL.pt").write_bytes(b"tampered")
    assert pf.check_checkpoint(tmp_path).status == "FAIL"
    assert pf.check_checkpoint(tmp_path / "nowhere").status == "FAIL"
    assert pf.check_evidence(tmp_path).status == "FAIL" and pf.check_evidence().status == "PASS"           # the real repository has its key evidence


def test_workspace_says_what_a_restart_will_do(tmp_path: Path):
    assert pf.check_workspace(None).status == "WARN" and "lost at the next restart" in pf.check_workspace(None).detail
    assert "does not exist yet" in pf.check_workspace(tmp_path / "ws").detail
    ws = tmp_path / "ws"
    (ws / "federation/studio_runs/FL10RUN-A").mkdir(parents=True)
    (ws / "federation/studio_runs/FL10RUN-A/meta.json").write_text("{}")
    (ws / "CAPSTONE_DEMO_WORKSPACE_V1.json").write_text("{}")
    resumed = pf.check_workspace(ws)
    assert resumed.status == "PASS" and "will resume" in resumed.detail and "1 stored run" in resumed.detail


def test_library_disk_and_the_overall_exit_code(tmp_path: Path):
    assert "0 stored candidates" in pf.check_library({"NHM_CANDIDATE_LIBRARY_DIR": str(tmp_path)}).detail
    assert pf.check_disk(usage=lambda p: type("U", (), {"free": 10 * 1024**3})()).status == "PASS"
    assert pf.check_disk(usage=lambda p: type("U", (), {"free": 10**8})()).status == "WARN"
    assert pf.check_python((3, 11)).status == "PASS" and pf.check_python((3, 13)).status == "FAIL"
    assert pf.check_node(which=lambda n: None).status == "FAIL"
    assert pf.check_node(which=lambda n: "/usr/bin/node", root=tmp_path).status == "WARN"          # node present, node_modules missing


def test_main_prints_a_verdict_and_exits_nonzero_only_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(pf, "run_checks", lambda env, ws: [pf.Check("a", "PASS", "ok"), pf.Check("b", "WARN", "careful")])
    assert pf.main(["--env-file", "/nonexistent"]) == 0 and "READY: 1 pass, 1 warn, 0 fail" in capsys.readouterr().out
    monkeypatch.setattr(pf, "run_checks", lambda env, ws: [pf.Check("a", "FAIL", "broken")])
    assert pf.main(["--env-file", "/nonexistent"]) == 1 and "NOT READY" in capsys.readouterr().out
