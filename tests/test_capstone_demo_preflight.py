# ruff: noqa: E501
"""CAP-010: CAPSTONE_DEMO_PREFLIGHT_V1 (each failure path; no science; no installs)."""

from __future__ import annotations

import socket

from scripts import capstone_demo_preflight as pre
from tests.capstone_demo_support import free_port

OK = {"ok": True, "detail": "ok"}


def _all_ok(extra: dict | None = None) -> dict:
    verifiers = {name: (lambda: OK) for name in pre.DEFAULT_VERIFIERS}
    verifiers.update(extra or {})
    return verifiers


def _run(verifiers=None, **kw):
    ports = kw.pop("ports", {"inference": free_port(), "product": free_port(), "frontend": free_port()})
    return pre.run_preflight(ports=ports, acknowledged=kw.pop("acknowledged", True), verifiers=verifiers or _all_ok(), **kw)


def test_a_healthy_environment_passes_and_executes_no_science() -> None:
    result = _run()
    assert result["passed"] and all(c["ok"] for c in result["checks"].values())
    assert set(result["science_executed"].values()) == {0}
    assert {"prior_locks_and_amendments", "phase_state", "runtime_binding", "product_api_import", "ui_successor", "research_catalog", "frontend_dependencies", "frontend_build"} <= set(result["checks"])


def test_every_verifier_failure_fails_the_whole_preflight() -> None:
    for name in pre.DEFAULT_VERIFIERS:
        result = _run(_all_ok({name: lambda: {"ok": False, "detail": "broken"}}))
        assert not result["passed"] and result["checks"][name]["ok"] is False, name
    exploding = _all_ok({"ui_successor": lambda: (_ for _ in ()).throw(RuntimeError("CAPSTONE_UI_V1_2_TAMPER:x"))})
    result = _run(exploding)
    assert not result["passed"] and "CAPSTONE_UI_V1_2_TAMPER" in result["checks"]["ui_successor"]["detail"]


def test_missing_acknowledgement_or_invalid_workspace_fails() -> None:
    assert not _run(acknowledged=False)["passed"]
    assert _run(acknowledged=False)["checks"]["demo_auth_acknowledgement"]["detail"] == "DEMO_AUTH_ACKNOWLEDGEMENT_REQUIRED"
    assert not _run(workspace_ok=False, workspace_detail="WORKSPACE_SENTINEL_MISSING")["passed"]


def test_an_occupied_port_fails_and_names_the_service_without_touching_the_occupant() -> None:
    with socket.socket() as occupant:
        occupant.bind(("127.0.0.1", 0))
        occupant.listen()
        busy = occupant.getsockname()[1]
        result = _run(ports={"inference": free_port(), "product": busy, "frontend": free_port()})
        assert not result["passed"] and result["checks"]["port_product"]["detail"] == f"PORT_IN_USE:product:{busy}"
        occupant.getsockname()  # the occupant is still bound and untouched
    assert pre.port_free(busy)


def test_missing_frontend_dependencies_report_the_exact_setup_command_and_never_install(monkeypatch) -> None:
    real = pre.FRONTEND
    monkeypatch.setattr(pre, "FRONTEND", real / "does_not_exist")
    result = pre.v_frontend_deps()
    assert result["ok"] is False and "npm ci" in result["detail"] and "never installs" in result["detail"]
    text = (pre.ROOT / "scripts/capstone_demo_preflight.py").read_text() + (pre.ROOT / "scripts/run_capstone_faculty_demo.py").read_text()
    for forbidden in ("pip install", "npm install", '"npm", "ci"', "npm ci\"]", "--upgrade"):
        assert forbidden not in text.replace("(cd frontend/clerk-sdk && npm ci)", "").replace("(cd frontend && npm ci)", ""), forbidden


def test_stale_or_missing_frontend_build_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    monkeypatch.setattr(pre, "FRONTEND", tmp_path / "frontend")
    (tmp_path / "frontend").mkdir()
    assert "FRONTEND_BUILD_MISSING" in pre.v_frontend_build()["detail"]


def test_the_real_environment_passes_the_real_preflight() -> None:
    result = pre.run_preflight(ports={"inference": free_port(), "product": free_port(), "frontend": free_port()}, acknowledged=True, skip_build_check=True)
    assert result["passed"], {k: v for k, v in result["checks"].items() if not v["ok"]}
    assert result["checks"]["phase_state"]["ok"] and result["checks"]["runtime_binding"]["ok"]


def test_preflight_module_runs_no_science_by_construction() -> None:
    import ast

    tree = ast.parse((pre.ROOT / "scripts/capstone_demo_preflight.py").read_text())
    called, imported = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called.add(node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", ""))
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    assert not called & {"train_local_epoch_v2", "train_local_fedprox_epoch_v2", "infer_window", "run_flower_secaggplus", "run_shadow", "create_candidate", "post", "put", "fit", "backward"}
    assert not any(m.startswith(("federated", "privacy", "training", "evaluation", "product.federation", "simulation")) for m in imported)


BASE = {"CAP-009": "PASS", "CAP-010": "PASS", "CAP-011": "NOT_STARTED"}
GATES = {"CAPG8": "PASS", "CAPG9": "PASS"}


def _phase(**tasks) -> bool:
    gates = tasks.pop("gates", GATES)
    return pre.phase_state_result({**BASE, **tasks}, gates)["ok"]


def test_phase_state_accepts_every_governed_successor_state() -> None:
    assert _phase()                                    # after CAP-010, before CAP-011
    assert _phase(**{"CAP-011": "IN_PROGRESS"})        # the CAP-011 release target
    assert _phase(**{"CAP-011": "PASS"})               # the released repository
    assert _phase(**{"CAP-010": "IN_PROGRESS"}, gates={"CAPG8": "PASS"})   # historical CAP-010 execution


def test_phase_state_rejects_a_successor_that_starts_before_cap_010_is_closed() -> None:
    for status in ("IN_PROGRESS", "PASS"):
        assert not _phase(**{"CAP-010": "IN_PROGRESS", "CAP-011": status}, gates={"CAPG8": "PASS", "CAPG9": "NOT_STARTED"})
        assert not _phase(**{"CAP-011": status}, gates={"CAPG8": "PASS", "CAPG9": "NOT_STARTED"})
    assert not _phase(**{"CAP-011": "IN_PROGRESS"}, gates={"CAPG8": "PASS"})


def test_phase_state_still_rejects_unknown_or_unfinished_predecessors() -> None:
    assert not _phase(**{"CAP-009": "IN_PROGRESS"})
    assert not _phase(**{"CAP-010": "NOT_STARTED"})
    assert not _phase(**{"CAP-011": "FAILED"})
    assert not _phase(gates={"CAPG8": "NOT_STARTED", "CAPG9": "PASS"})
