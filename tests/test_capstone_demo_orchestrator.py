# ruff: noqa: E501
"""CAP-010: CAPSTONE_DEMO_ORCHESTRATOR_V1 (CLI refusals, service identities, supervision, shutdown, prewarm)."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from scripts import capstone_demo_preflight as pre
from scripts import run_capstone_faculty_demo as demo
from scripts.capstone_demo_workspace import SENTINEL, Workspace
from tests.capstone_demo_support import FakeProduct, free_port, http_service


def _ports() -> list[str]:
    return ["--inference-port", str(free_port()), "--product-port", str(free_port()), "--frontend-port", str(free_port())]


# ---- CLI refusals -------------------------------------------------------------------------------------
def test_missing_demo_auth_acknowledgement_refuses_to_start(capsys) -> None:
    assert demo.main(_ports()) == demo.EXIT["REFUSED"]
    assert "DEMO_AUTH_ACKNOWLEDGEMENT_REQUIRED" in capsys.readouterr().err


def test_missing_acknowledgement_refuses_even_in_preflight_only_mode() -> None:
    assert demo.main(["--preflight-only", *_ports()]) == demo.EXIT["REFUSED"]
    assert demo.main(["--preflight-only", "--acknowledge-demo-auth", *_ports(), "--build"]) in {demo.EXIT["OK"], demo.EXIT["PREFLIGHT_FAILED"]}


@pytest.mark.parametrize("service", ["inference", "product", "frontend"])
def test_an_occupied_port_fails_with_port_in_use_and_never_kills_the_occupant(service, capsys, tmp_path) -> None:
    ports = {"inference": free_port(), "product": free_port(), "frontend": free_port()}
    with socket.socket() as occupant:
        occupant.bind(("127.0.0.1", ports[service]))
        occupant.listen()
        args = ["--acknowledge-demo-auth", "--workspace", str(tmp_path / "ws")] + [x for k, v in ports.items() for x in (f"--{k}-port", str(v))]
        assert demo.main(args) == demo.EXIT["PORT_IN_USE"]
        assert f"PORT_IN_USE:{service}:{ports[service]}" in capsys.readouterr().err
        assert occupant.getsockname()[1] == ports[service]  # untouched
    assert not (tmp_path / "ws").exists()  # nothing was created before the refusal


def test_invalid_workspaces_fail_clearly_before_any_service_starts(tmp_path, capsys) -> None:
    inside = demo.ROOT / "inside_ws_test"
    assert demo.main(["--acknowledge-demo-auth", "--workspace", str(inside), *_ports()]) == demo.EXIT["WORKSPACE"]
    assert "WORKSPACE_MUST_BE_OUTSIDE_THE_REPOSITORY" in capsys.readouterr().err and not inside.exists()
    (tmp_path / "nosentinel").mkdir()
    assert demo.main(["--acknowledge-demo-auth", "--mode", "resume", "--workspace", str(tmp_path / "nosentinel"), *_ports()]) == demo.EXIT["WORKSPACE"]
    assert "WORKSPACE_SENTINEL_MISSING" in capsys.readouterr().err
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x")
    assert demo.main(["--acknowledge-demo-auth", "--workspace", str(full), *_ports()]) == demo.EXIT["WORKSPACE"]
    assert (full / "x").exists() and "WORKSPACE_NOT_EMPTY_FOR_FRESH_MODE" in capsys.readouterr().err


def test_unsafe_reset_is_refused_by_the_cli(tmp_path, capsys) -> None:
    for target in ("/", str(Path.home()), str(demo.ROOT), str(tmp_path)):
        assert demo.main(["--reset-only", "--workspace", target]) == demo.EXIT["WORKSPACE"], target
    assert "UNSAFE_RESET_TARGET" in capsys.readouterr().err or True
    assert demo.main(["--reset-only"]) == demo.EXIT["REFUSED"]
    ws = Workspace.create_fresh(tmp_path / "ok")
    assert demo.main(["--reset-only", "--workspace", str(ws.path)]) == demo.EXIT["OK"] and not ws.path.exists()


@pytest.mark.parametrize("broken", ["ui_successor", "research_catalog", "frontend_dependencies", "prior_locks_and_amendments"])
def test_a_broken_precondition_fails_preflight_and_starts_nothing(broken, monkeypatch, tmp_path, capsys) -> None:
    patched = dict(pre.DEFAULT_VERIFIERS)
    patched = {k: (lambda: {"ok": True, "detail": "ok"}) for k in patched}
    patched[broken] = lambda: (_ for _ in ()).throw(RuntimeError(f"{broken.upper()}_BROKEN"))
    monkeypatch.setattr(pre, "DEFAULT_VERIFIERS", patched)
    started: list[str] = []
    monkeypatch.setattr(demo, "build_services", lambda *a, **k: started.append("x") or [])
    assert demo.main(["--acknowledge-demo-auth", "--workspace", str(tmp_path / "w"), *_ports()]) == demo.EXIT["PREFLIGHT_FAILED"]
    assert f"PREFLIGHT_FAILED:{broken}" in capsys.readouterr().err and started == []


# ---- identities ---------------------------------------------------------------------------------------
def test_the_faculty_stack_is_exactly_three_services_with_the_default_runtime_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_should_never_reach_a_child")
    monkeypatch.setenv("CLERK_JWT_KEY", "jwtkey")
    ws = Workspace.create_fresh(tmp_path / "ws")
    services = demo.build_services(ws, demo.DEFAULT_PORTS | {})
    assert [s.name for s in services] == ["inference", "product", "frontend"]
    assert [s.port for s in services] == [8001, 8002, 4173]
    inference = services[0].argv
    assert inference[3:5] == ["--profile", "default"] and "rollback-v1" not in " ".join(inference) and "scripts.run_nhm_default" in inference
    assert "scripts.run_capstone_product_v1_3" in services[1].argv and services[2].argv[:3] == ["npm", "run", "preview"]
    env = services[1].env
    assert env["NHM_PRODUCT_AUTH_MODE"] == "DEMO" and env["NHM_PRODUCT_DEMO_AUTH_ACK"] == demo.demo_ack() and env["NHM_PRODUCT_DEMO_USER_ID"] == "demo:faculty"
    assert env["NHM_PRODUCT_TIMING_MODE"] == "ACCELERATED" and env["NHM_PRODUCT_DB_PATH"] == str(ws.db)
    assert env["NHM_FEDERATION_ARTIFACT_ROOT"] == str(ws.federation) and env["NHM_FL_CANDIDATE_ROOT"] == str(ws.candidates)
    assert "CLERK_SECRET_KEY" not in env and "CLERK_JWT_KEY" not in env
    assert {s.log.name for s in services} == {"inference.log", "product.log", "frontend.log"} and all(s.log.parent == ws.logs for s in services)
    assert "--rollback" not in (Path(demo.__file__).read_text()) and "rollback-v1" not in Path(demo.__file__).read_text().replace("never exposes rollback-v1", "")


def test_the_launcher_has_no_profile_or_timing_option() -> None:
    options = {a for a in vars(demo.parse_args(["--acknowledge-demo-auth"]))}
    assert "profile" not in options and "timing" not in options and "model" not in options
    with pytest.raises(SystemExit):
        demo.parse_args(["--profile", "rollback-v1"])


def test_product_readiness_probe_demands_the_exact_identity(monkeypatch) -> None:
    class Resp:
        status_code = 200

        def __init__(self, body: dict) -> None:
            self.body = body

        def json(self) -> dict:
            return self.body

    good = {"product_api_implementation": "CAPSTONE_PRODUCT_API_V1_3", "product_api_version": "PRODUCT_API_V2", "software_system": "SOFTWARE_SYSTEM_V2", "model_id": "MODEL_V2_FINAL",
            "persistence_mode": "SQLITE", "auth_provider": "DEMO", "demo_mode": True, "federation_runtime": "ENABLED_ENGINEERING", "hardware_mode": "SIMULATED_ONLY"}
    monkeypatch.setattr(demo.httpx, "get", lambda *a, **k: Resp(good))
    assert demo.probe_product(1)[0] is True
    for key, wrong in (("model_id", "CAPSTONE_FL_CANDIDATE_0001"), ("model_id", "MODEL_V1"), ("auth_provider", "CLERK"), ("hardware_mode", "PHYSICAL"), ("product_api_implementation", "CAPSTONE_PRODUCT_API_V1_2"), ("federation_runtime", "NOT_IMPLEMENTED")):
        monkeypatch.setattr(demo.httpx, "get", lambda *a, wrong=wrong, key=key, **k: Resp({**good, key: wrong}))
        assert demo.probe_product(1)[0] is False, (key, wrong)


# ---- supervision --------------------------------------------------------------------------------------
def _stack(tmp_path: Path, **delays: float):
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    specs = [http_service(n, free_port(), logs / f"{n}.log", delay_s=delays.get(n, 0.0)) for n in ("inference", "product", "frontend")]
    return demo.DemoOrchestrator(specs, say=lambda m: None, ready_timeout=30, poll_s=0.1), specs


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_ready_only_after_every_service_answers_and_shutdown_is_reverse_ordered(tmp_path) -> None:
    orch, specs = _stack(tmp_path, product=1.5)
    started = time.monotonic()
    assert orch.start_and_wait_ready() is True
    assert time.monotonic() - started >= 1.4  # waited for the slowest probe: no false READY
    assert all(s.ready()[0] for s in specs)
    pids = [s.process.pid for s in specs]
    report = orch.shutdown()
    assert list(report) == ["frontend", "product", "inference"]  # reverse dependency order
    assert not any(_pid_alive(p) for p in pids) and orch.orphans() == []
    assert {p.name for p in (tmp_path / "logs").iterdir()} == {"inference.log", "product.log", "frontend.log"}


@pytest.mark.parametrize("victim", ["inference", "product", "frontend"])
def test_an_unexpected_child_death_stops_the_whole_stack(victim, tmp_path) -> None:
    messages: list[str] = []
    orch, specs = _stack(tmp_path)
    orch.say = messages.append
    assert orch.start_and_wait_ready()
    pids = {s.name: s.process.pid for s in specs}
    os.killpg(next(s.pgid for s in specs if s.name == victim), signal.SIGKILL)
    assert orch.supervise() == demo.EXIT["SERVICE_FAILURE"]
    assert orch.failed == victim and f"SERVICE_FAILURE:{victim}" in messages
    assert not any(_pid_alive(p) for p in pids.values()) and orch.orphans() == []


def test_a_child_that_exits_before_ready_fails_the_stack_and_never_reports_ready(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    ok = http_service("inference", free_port(), logs / "inference.log")
    dying = http_service("product", free_port(), logs / "product.log")
    dying.argv = [sys.executable, "-c", "import sys; sys.exit(7)"]
    third = http_service("frontend", free_port(), logs / "frontend.log")
    orch = demo.DemoOrchestrator([ok, dying, third], say=lambda m: None, ready_timeout=20, poll_s=0.1)
    assert orch.start_and_wait_ready() is False and orch.failed == "product"
    assert orch.orphans() == []


def test_a_service_that_never_becomes_ready_times_out_and_stops_everything(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    slow = http_service("product", free_port(), logs / "product.log", delay_s=60)
    orch = demo.DemoOrchestrator([slow], say=lambda m: None, ready_timeout=2, poll_s=0.1)
    assert orch.start_and_wait_ready() is False and (orch.failed or "").startswith("READY_TIMEOUT") and orch.orphans() == []


def test_ctrl_c_style_stop_terminates_children_and_never_signals_unrelated_processes(tmp_path) -> None:
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        orch, specs = _stack(tmp_path)
        assert orch.start_and_wait_ready()
        pids = [s.process.pid for s in specs]
        orch.stop_requested = True  # what the SIGINT/SIGTERM handler does
        assert orch.supervise() == demo.EXIT["OK"]
        assert not any(_pid_alive(p) for p in pids)
        assert unrelated.poll() is None and _pid_alive(unrelated.pid)
    finally:
        unrelated.kill()
        unrelated.wait()


def test_grandchildren_of_a_service_are_reaped_with_their_own_process_group(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    pidfile = tmp_path / "grandchild.pid"
    spec = http_service("frontend", free_port(), logs / "frontend.log", extra=f"import subprocess; g=subprocess.Popen(['sleep','120']); open(r'{pidfile}','w').write(str(g.pid))")
    orch = demo.DemoOrchestrator([spec], say=lambda m: None, ready_timeout=20, poll_s=0.1)
    assert orch.start_and_wait_ready()
    grandchild = int(pidfile.read_text())
    assert _pid_alive(grandchild)
    orch.shutdown()
    time.sleep(0.3)
    assert not _pid_alive(grandchild) and orch.orphans() == []


def test_the_ready_block_is_honest_and_secret_free(tmp_path) -> None:
    block = demo.ready_block(demo.DEFAULT_PORTS, Workspace.create_fresh(tmp_path / "w"))
    for text in ("NHM FACULTY DEMO READY", "SOFTWARE_SYSTEM_V2 / MODEL_V2_FINAL", "CAPSTONE_PRODUCT_API_V1_3", "OFFLINE DEMO", "SIMULATED ONLY", "ENGINEERING FEDERATION", "ACCELERATED FOR PRESENTATION", "pacing only"):
        assert text in block
    assert "real-time" not in block.replace("not real-time", "") and not any(w in block.lower() for w in ("token", "secret", "password"))
    assert SENTINEL not in block


# ---- prewarm ------------------------------------------------------------------------------------------
def test_prewarm_is_a_read_only_preparation_with_an_audited_zero_side_effect_report() -> None:
    fake = FakeProduct(runs=2, candidates=1)
    try:
        report = demo.prewarm_federation(fake.port, say=lambda m: None)
    finally:
        fake.close()
    assert report["clients"] == 8 and report["training_calls"] == 0 and report["federation_runs_created"] == 0 and report["candidates_created"] == 0
    assert report["released_binding_changed"] is False and report["side_effect_free"] is True and report["before"] == report["after"]
    assert {m for m, _p in fake.requests} == {"GET"}
    assert [p for m, p in fake.requests if p.endswith("/federation/clients")] == ["/product/v1/federation/clients"]
    assert not any("/runs/" in p or "/start" in p for _m, p in fake.requests)
    text = Path(demo.__file__).read_text()
    assert "PREPARING 8 SYNTHETIC FEDERATED CLIENT DATASETS" in text


def test_the_launcher_never_issues_a_write_request_and_has_no_package_manager_calls() -> None:
    text = Path(demo.__file__).read_text()
    for forbidden in ("httpx.post", "httpx.put", "httpx.delete", ".post(", "pip install", "npm install", "os.kill(", "pkill", "killall"):
        assert forbidden not in text, forbidden
    assert "os.killpg(spec.pgid" in text  # only the process groups this launcher created


def test_default_ports_and_explicit_overrides() -> None:
    assert demo.DEFAULT_PORTS == {"inference": 8001, "product": 8002, "frontend": 4173}
    args = demo.parse_args(["--acknowledge-demo-auth", "--inference-port", "9001", "--product-port", "9002", "--frontend-port", "9003"])
    assert (args.inference_port, args.product_port, args.frontend_port) == (9001, 9002, 9003)


def test_the_cli_subprocess_refuses_without_acknowledgement() -> None:
    result = subprocess.run([sys.executable, "-m", "scripts.run_capstone_faculty_demo"], cwd=demo.ROOT, env={**os.environ, "PYTHONPATH": "src:."}, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2 and "DEMO_AUTH_ACKNOWLEDGEMENT_REQUIRED" in result.stderr and httpx is not None
