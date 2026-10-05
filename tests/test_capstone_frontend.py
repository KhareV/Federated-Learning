# ruff: noqa: E501
"""CAP-005 (CAPSTONE_UI_V1) Python-side guards: supersession of DASHBOARD_UI_V1_5, the product proxy,
the additive Clerk package, and 'no backend change'. The frontend behaviour itself is covered by the
vitest suites under frontend/src/lib/product/__tests__ (unit, component, static and real-backend)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI_LOCK = ROOT / "artifacts/capstone/CAPSTONE_UI_V1.lock.json"
ENTRY = "9db76b482678114ac5c22f3f91a3f55ccb159e17"


def _git_show(path: str) -> bytes:
    return subprocess.run(["git", "show", f"{ENTRY}:{path}"], cwd=ROOT, check=True,
                          capture_output=True).stdout


def test_capstone_ui_v1_lock_supersedes_dashboard_ui_v1_5_and_verifies() -> None:
    from scripts.verify_capstone_ui_v1 import verify

    result = verify()
    assert result["status"] == "PASS" and result["predecessor_preserved"] is True
    lock = json.loads(UI_LOCK.read_text())
    assert lock["predecessor_id"] == "DASHBOARD_UI_V1_5"
    assert lock["backend_modified"] is False and lock["second_frontend_created"] is False


def test_the_superseded_dashboard_ui_v1_5_lock_is_byte_identical_and_reports_drift() -> None:
    lock_path = ROOT / "artifacts/DASHBOARD_UI_V1_5.lock.json"
    assert lock_path.read_bytes() == _git_show("artifacts/DASHBOARD_UI_V1_5.lock.json")
    from scripts.verify_dashboard_ui_v1_5_v2rel001 import verify as v15

    with pytest.raises(RuntimeError, match="DASHBOARD_UI_V1_5_TAMPER"):
        v15()


def test_capstone_ui_v1_detects_tamper_on_any_bound_file(tmp_path: Path, monkeypatch) -> None:
    import scripts.verify_capstone_ui_v1 as module

    lock = json.loads(UI_LOCK.read_text())
    shadow = tmp_path / "repo"
    for rel in [*lock["bound_artifacts"], "artifacts/DASHBOARD_UI_V1_5.lock.json",
                "artifacts/capstone/CAPSTONE_UI_V1.lock.json"]:
        (shadow / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, shadow / rel)
    monkeypatch.setattr(module, "ROOT", shadow)
    # shadow copies hold the CURRENT bytes: amendments (if any) already describe them
    victim = "frontend/src/lib/product/live-model.ts"
    assert victim in lock["bound_artifacts"]
    (shadow / victim).write_text((shadow / victim).read_text() + "\n// tamper\n")
    with pytest.raises(RuntimeError, match="CAPSTONE_UI_V1_TAMPER"):
        module.verify()


def test_package_json_and_lock_are_untouched_and_clerk_js_is_pinned_in_the_additive_package() -> None:
    for rel in ("frontend/package.json", "frontend/package-lock.json"):
        assert (ROOT / rel).read_bytes() == _git_show(rel), rel  # the frozen V2-014 lock binds these
    sdk = json.loads((ROOT / "frontend/clerk-sdk/package.json").read_text())
    assert sdk["dependencies"] == {"@clerk/clerk-js": "6.37.0"}
    sdk_lock = json.loads((ROOT / "frontend/clerk-sdk/package-lock.json").read_text())
    assert sdk_lock["packages"]["node_modules/@clerk/clerk-js"]["version"] == "6.37.0"
    assert "clerk-sveltekit" not in json.dumps(sdk_lock)


def test_vite_proxies_product_separately_from_the_research_runtime() -> None:
    text = (ROOT / "frontend/vite.config.ts").read_text()
    assert "'/product': productProxy" in text and "'/v1': nhmApiProxy" in text
    assert "NHM_PRODUCT_API_PORT" in text and "'8002'" in text
    assert "ws: true" in text.split("productProxy: ProxyOptions")[1].split("};")[0]
    assert "NHM_API_PORT" in text and "'8001'" in text  # /v1 still points at the research runtime


def test_exactly_one_frontend_application_exists() -> None:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True,
                             text=True).stdout.splitlines()
    manifests = [p for p in tracked if p.endswith("package.json") and "node_modules" not in p]
    assert sorted(manifests) == ["frontend/clerk-sdk/package.json", "frontend/package.json"]
    assert (ROOT / "frontend/svelte.config.js").is_file()
    assert not [p for p in tracked if p.endswith(("next.config.js", "angular.json", "nuxt.config.ts"))]


def test_backend_and_scientific_trees_are_byte_identical_to_the_entry_commit() -> None:
    # Existing files are byte-identical (no file modified or deleted); later phases may ADD files
    # (CAP-006 adds client-local modules under product/ - CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1 amendment 6).
    changed = subprocess.run(["git", "diff", "--name-only", "--diff-filter=MD", ENTRY, "--", "api", "product",
                              "capstone_persistence", "simulation", "src", "checkpoints",
                              "contracts", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json"],
                             cwd=ROOT, check=True, capture_output=True, text=True).stdout.split()
    assert changed == []


def test_product_routes_exist_and_future_destinations_are_shells_only() -> None:
    routes = ROOT / "frontend/src/routes"
    for rel in ("sign-in", "app", "app/device", "app/monitoring"):
        assert (routes / rel / "+page.svelte").is_file(), rel
    for rel in ("federation", "federation/clients", "federation/rounds", "federation/live",
                "federation/privacy", "models", "research/ml", "research/fl"):
        assert "FuturePhase" in (routes / "app" / rel / "+page.svelte").read_text(), rel
