# ruff: noqa: E501
"""CLERK-LIVE-001: the Clerk-connected launcher, credential boundaries and static auth guards (no network, no Clerk)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scripts import run_capstone_clerk_connected as launcher
from scripts.capstone_demo_workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
PK = "pk_test_" + "ZXhhbXBsZS1hcHAtMTIzNC5jbGVyay5hY2NvdW50cy5kZXYk"
SK = "sk_test_" + "A" * 24


def _env(**over: str) -> dict[str, str]:
    return {launcher.ENV_PK_NEXT: PK, launcher.ENV_SECRET: SK, **over}


def test_nextjs_style_publishable_name_is_mapped_to_the_vite_variable_for_the_frontend_only(tmp_path) -> None:
    cfg = launcher.resolve_config(_env(), 4173)
    assert cfg["publishable_key"] == PK and cfg["secret_key"] == SK and cfg["authorized_parties"] == ["http://127.0.0.1:4173"]
    ws = Workspace.create_fresh(tmp_path / "ws")
    services = {s.name: s for s in launcher.build_services(ws, {"inference": 8001, "product": 8002, "frontend": 4173}, cfg, {**_env(), "PATH": "/usr/bin"})}
    assert services["frontend"].env[launcher.ENV_PK_VITE] == PK
    assert not any(k.startswith("NEXT_PUBLIC") for k in services["frontend"].env)
    for name in ("frontend", "inference"):                       # the secret never reaches the frontend or inference processes
        assert SK not in services[name].env.values() and launcher.ENV_SECRET not in services[name].env
    product = services["product"].env
    assert product["NHM_PRODUCT_AUTH_MODE"] == "CLERK" and product[launcher.ENV_SECRET] == SK and product[launcher.ENV_PARTIES] == "http://127.0.0.1:4173"
    assert not any(k.startswith("NHM_PRODUCT_DEMO") for k in product)                       # no DemoAuth acknowledgement, no demo identity
    for spec in services.values():                              # no credential in any argument list (process listings)
        assert not any(SK in a or PK in a for a in spec.argv)


@pytest.mark.parametrize("env,code", [
    ({}, "CLERK_PUBLISHABLE_KEY_ABSENT"), ({launcher.ENV_PK_NEXT: PK}, "CLERK_SECRET_KEY_ABSENT"), ({launcher.ENV_SECRET: SK}, "CLERK_PUBLISHABLE_KEY_ABSENT"),
    ({launcher.ENV_PK_NEXT: "pk_live_" + "A" * 20, launcher.ENV_SECRET: SK}, "NOT_A_CLERK_TEST_KEY"), ({launcher.ENV_PK_NEXT: PK, launcher.ENV_SECRET: "sk_live_" + "A" * 24}, "NOT_A_CLERK_TEST_KEY"),
    ({launcher.ENV_PK_NEXT: PK, launcher.ENV_PK_VITE: "pk_test_" + "B" * 20, launcher.ENV_SECRET: SK}, "DISAGREE"),
    (_env(NHM_CLERK_AUTHORIZED_PARTIES="*"), "EXPLICIT_ORIGINS"), (_env(NHM_CLERK_AUTHORIZED_PARTIES="http://a.example,*"), "EXPLICIT_ORIGINS"), (_env(NHM_CLERK_AUTHORIZED_PARTIES="not-an-origin"), "EXPLICIT_ORIGINS"),
])
def test_launcher_refuses_invalid_configuration_and_never_falls_back_to_demo(env, code) -> None:
    with pytest.raises(launcher.ConnectedConfigError, match=code):
        launcher.resolve_config(env, 4173)


def test_explicit_authorized_parties_and_optional_localhost_origin() -> None:
    cfg = launcher.resolve_config(_env(), 4173, ["http://localhost:4173"])
    assert cfg["authorized_parties"] == ["http://127.0.0.1:4173", "http://localhost:4173"]
    assert launcher.resolve_config(_env(NHM_CLERK_AUTHORIZED_PARTIES="http://127.0.0.1:4173"), 4173)["authorized_parties"] == ["http://127.0.0.1:4173"]


def test_main_refuses_without_credentials_and_creates_no_workspace(tmp_path, monkeypatch, capsys) -> None:
    for var in (launcher.ENV_PK_NEXT, launcher.ENV_PK_VITE, launcher.ENV_SECRET):
        monkeypatch.delenv(var, raising=False)
    ws = tmp_path / "ws"
    assert launcher.main(["--workspace", str(ws)]) == launcher.EXIT["REFUSED"]
    assert not ws.exists() and "REFUSING TO START" in capsys.readouterr().err


def test_env_file_is_parsed_without_shell_evaluation_and_the_environment_wins(tmp_path) -> None:
    f = tmp_path / "creds.env"
    f.write_text(f"# comment\n{launcher.ENV_SECRET}=\"{SK}\"\n{launcher.ENV_PK_NEXT}={PK}\nBAD LINE\nX=$(touch /tmp/never)\n")
    parsed = launcher.parse_env_file(f)
    assert parsed[launcher.ENV_SECRET] == SK and parsed["X"] == "$(touch /tmp/never)"


def test_frontend_build_receives_only_the_publishable_key_never_the_secret(monkeypatch) -> None:
    seen: dict = {}

    def fake_run(cmd, **kw):
        seen.update(env=kw["env"], cmd=cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "boom " + SK)    # failure path must also redact the secret

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    cfg = launcher.resolve_config(_env(), 4173)
    with pytest.raises(RuntimeError) as err:
        launcher.build_frontend(cfg, {**_env(), launcher.ENV_PK_VITE: PK, "PATH": "/usr/bin"}, say=lambda _m: None)
    assert SK not in str(err.value) and "<REDACTED>" in str(err.value)
    assert seen["env"][launcher.ENV_PK_VITE] == PK and launcher.ENV_SECRET not in seen["env"] and not any(k.startswith("NEXT_PUBLIC") for k in seen["env"])


def test_product_readiness_probe_demands_clerk_not_demo(monkeypatch) -> None:
    class R:
        status_code = 200

        def __init__(self, body):
            self._b = body

        def json(self):
            return self._b

    good = {"product_api_implementation": "CAPSTONE_PRODUCT_API_V1_3", "software_system": "SOFTWARE_SYSTEM_V2", "model_id": "MODEL_V2_FINAL", "persistence_mode": "SQLITE", "auth_provider": "CLERK", "demo_mode": False,
            "federation_runtime": "ENABLED_ENGINEERING", "hardware_mode": "SIMULATED_ONLY"}
    monkeypatch.setattr(launcher.httpx, "get", lambda *a, **k: R(good))
    assert launcher.clerk_probe_product(8002)[0] is True
    for bad in ({"auth_provider": "DEMO", "demo_mode": True}, {"demo_mode": True}, {"model_id": "CAPSTONE_FL_CANDIDATE_0001"}):
        monkeypatch.setattr(launcher.httpx, "get", lambda *a, _b=bad, **k: R({**good, **_b}))
        assert launcher.clerk_probe_product(8002)[0] is False


def test_frontend_never_reads_next_public_or_contains_a_secret_and_the_key_comes_from_the_environment() -> None:
    files = [p for p in (ROOT / "frontend/src").rglob("*") if p.is_file() and p.suffix in {".ts", ".svelte", ".js"} and "__tests__" not in p.parts]
    body = "\n".join(p.read_text() for p in files) + (ROOT / "frontend/vite.config.ts").read_text()
    assert "NEXT_PUBLIC" not in body and "CLERK_SECRET_KEY" not in body and not re.search(r"sk_(test|live)_[A-Za-z0-9]{8,}", body)
    assert "VITE_CLERK_PUBLISHABLE_KEY" in body and not re.search(r"pk_(test|live)_[A-Za-z0-9+/=]{20,}", body)
    assert "define:" not in (ROOT / "frontend/vite.config.ts").read_text()
    tracked_env = subprocess.run(["git", "ls-files", ".env", "frontend/.env", "frontend/.env.local"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    assert tracked_env == ""


def test_no_custom_jwt_cryptography_and_no_token_in_websocket_urls() -> None:
    forbidden = re.compile(r"^\s*(import|from)\s+(jwt|jose|jwcrypto|cryptography|authlib)\b", re.M)
    for rel in ("product/auth", "api"):
        for p in (ROOT / rel).rglob("*.py"):
            assert not forbidden.search(p.read_text()), p
    assert "authenticate_request_async" in (ROOT / "product/auth/clerk.py").read_text()
    socket_src = (ROOT / "frontend/src/lib/product/socket.ts").read_text() + (ROOT / "frontend/src/lib/product/api.ts").read_text()
    assert not re.search(r"[?&]token=|access_token|searchParams\.set\(['\"](token|__session)", socket_src)


def test_demo_launcher_remains_demo_only_and_never_receives_clerk_credentials() -> None:
    demo = (ROOT / "scripts/run_capstone_faculty_demo.py").read_text()
    assert '"NHM_PRODUCT_AUTH_MODE": "DEMO"' in demo and 'product_env.pop(secret, None)' in demo
    assert "CLERK" not in re.sub(r'"CLERK_SECRET_KEY", "CLERK_JWT_KEY", "CLERK_PUBLISHABLE_KEY"', "", demo.replace("NOT CLERK", "").replace("not Clerk", ""))
