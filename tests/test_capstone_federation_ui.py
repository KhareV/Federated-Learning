# ruff: noqa: E501
"""CAP-008 Python-side guards: UI successor lineage, backend zero drift, no new dependency, scope boundaries."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "711a4a0a1233765d6f1200fc2b6d8f3aa62d4743"
UI_V1 = "artifacts/capstone/CAPSTONE_UI_V1.lock.json"
UI_V11 = "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def _shadow(tmp_path: Path) -> Path:
    from scripts.verify_capstone_ui_v1_1 import frontend_files

    shadow = tmp_path / "repo"
    paths = [*frontend_files(), UI_V1, UI_V11, "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", *(["artifacts/capstone/CAPSTONE_UI_V1_3.lock.json"] if (ROOT / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json").exists() else []), *(["artifacts/capstone/CAPSTONE_UI_V1_4.lock.json"] if (ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json").exists() else []), *(["artifacts/capstone/CAPSTONE_UI_V1_5.lock.json"] if (ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json").exists() else []), "artifacts/DASHBOARD_UI_V1_5.lock.json", *[str(p.relative_to(ROOT)) for p in (ROOT / "artifacts/capstone").glob("CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_*.json")]]
    for rel in paths:
        (shadow / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, shadow / rel)
    return shadow


def test_ui_v1_lock_file_is_preserved_byte_identical_to_entry() -> None:
    assert (ROOT / UI_V1).read_bytes() == subprocess.run(["git", "show", f"{ENTRY}:{UI_V1}"], cwd=ROOT, check=True, capture_output=True).stdout
    lock = json.loads((ROOT / UI_V11).read_text())
    assert lock["predecessor_id"] == "CAPSTONE_UI_V1" and lock["predecessor_sha256"] == hash_file(ROOT / UI_V1)


def test_ui_v1_1_successor_lock_verifies_and_binds_every_frontend_file() -> None:
    from scripts.verify_capstone_ui_v1 import verify as verify_v1
    from scripts.verify_capstone_ui_v1_1 import frontend_files, verify

    result = verify()
    assert result["status"] == "PASS" and result["predecessor_preserved"] is True
    lock = json.loads((ROOT / UI_V11).read_text())
    assert lock["owner_phase"] == "CAP-008" and lock["backend_modified"] is False and lock["scientific_state_semantics_changed"] is False
    assert lock["npm_dependencies_added"] == [] and lock["second_frontend_created"] is False and lock["changed_from_predecessor"]
    from scripts.verify_capstone_ui_v1_1 import bound_map

    assert set(frontend_files()) == set(bound_map(lock))
    assert verify_v1()["status"] == "PASS"  # the historical verifier accepts exactly the successor-bound changes


def test_unaccounted_frontend_drift_fails(tmp_path: Path, monkeypatch) -> None:
    import scripts.verify_capstone_ui_v1_1 as module

    shadow = _shadow(tmp_path)
    monkeypatch.setattr(module, "ROOT", shadow)
    monkeypatch.setattr(module, "frontend_files", lambda: sorted(str(p.relative_to(shadow)) for p in (shadow / "frontend").rglob("*") if p.is_file()))
    assert module.verify()["status"] == "PASS"
    extra = shadow / "frontend/src/lib/product/federation/unbound_extra.ts"
    extra.write_text("export const x = 1;\n")
    with pytest.raises(RuntimeError, match="CAPSTONE_UI_V1_1_UNACCOUNTED_FRONTEND_FILE"):
        module.verify()
    extra.unlink()
    victim = shadow / "frontend/src/lib/product/live-model.ts"
    victim.write_text(victim.read_text() + "\n// tamper\n")
    with pytest.raises(RuntimeError, match="CAPSTONE_UI_V1_1_TAMPER"):
        module.verify()


def test_ui_v1_verifier_accepts_only_successor_bound_changes(tmp_path: Path, monkeypatch) -> None:
    import scripts.verify_capstone_ui_v1 as module

    lock = json.loads((ROOT / UI_V1).read_text())
    successor = json.loads((ROOT / UI_V11).read_text())
    changed = sorted(p for p in lock["bound_artifacts"] if successor["bound_artifacts"].get(p) != lock["bound_artifacts"][p])
    assert changed, "CAP-008 must change at least one UI_V1-bound file"
    shadow = _shadow(tmp_path)
    for rel in lock["bound_artifacts"]:
        (shadow / rel).parent.mkdir(parents=True, exist_ok=True)
        if not (shadow / rel).exists():
            shutil.copyfile(ROOT / rel, shadow / rel)
    monkeypatch.setattr(module, "ROOT", shadow)
    assert module.verify()["status"] == "PASS"
    victim = "frontend/src/lib/product/live-model.ts"  # unchanged by CAP-008, bound by UI_V1
    assert victim in lock["bound_artifacts"] and victim not in changed
    (shadow / victim).write_text((shadow / victim).read_text() + "\n// tamper\n")
    with pytest.raises(RuntimeError, match="CAPSTONE_UI_V1_TAMPER"):
        module.verify()


def test_backend_scientific_fl_cap006_cap007_files_are_byte_identical_to_entry() -> None:
    trees = ["simulation", "src", "checkpoints", "contracts", "federated", "privacy", "reports/model_v2",
             "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json"]
    assert _git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *trees).split() == []
    # CAP-009 may ADD owner-scoped history/research files, but may not modify
    # any CAP-008-or-earlier API, product, or persistence implementation.
    assert _git("diff", "--name-only", "--diff-filter=MD", ENTRY, "--", "api", "product", "capstone_persistence").split() == []


def test_exactly_one_frontend_application_and_no_new_npm_dependency() -> None:
    manifests = [p for p in _git("ls-files").splitlines() if p.endswith(("package.json", "next.config.js", "angular.json", "nuxt.config.ts"))]
    assert sorted(manifests) == ["frontend/clerk-sdk/package.json", "frontend/package.json"]
    for rel in ("frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json"):
        assert (ROOT / rel).read_bytes() == subprocess.run(["git", "show", f"{ENTRY}:{rel}"], cwd=ROOT, check=True, capture_output=True).stdout, rel
    assert (ROOT / "frontend/svelte.config.js").is_file()


def test_federation_pages_are_not_placeholders() -> None:
    routes = ROOT / "frontend/src/routes/app"
    for rel in ("federation", "federation/clients", "federation/rounds", "federation/live", "federation/privacy", "models"):
        assert "FuturePhase" not in (routes / rel / "+page.svelte").read_text(), rel
    for rel in ("research/ml", "research/fl"):
        assert "FuturePhase" not in (routes / rel / "+page.svelte").read_text(), rel
        assert "product.api.research" in (routes / rel / "+page.svelte").read_text(), rel
    assert not (routes / "research/ml/analytics").exists()


def test_candidate_inference_and_sandbox_runtime_absent() -> None:
    tracked = _git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    assert not [p for p in tracked if "sandbox_runtime" in p.lower() or "candidate_inference" in p.lower()]
    scoped = [p for p in tracked if p.startswith(("frontend/src/lib/product/federation/", "frontend/src/lib/components/product/federation/", "frontend/src/routes/app/federation/", "frontend/src/routes/app/models/")) and "__tests__" not in p]
    assert scoped
    for rel in scoped:
        text = (ROOT / rel).read_text(errors="ignore")
        assert "CAPSTONE_FL_SANDBOX_RUNTIME" not in text and not re.search(r"state\.bin|infer-window", text), rel


def test_no_candidate_reference_in_monitoring_or_released_runtime() -> None:
    for rel in ("artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "product/session.py", "product/inference/client.py", "api/product_app_v1_1.py",
                "frontend/src/lib/product/live-model.ts", "frontend/src/lib/product/events.ts", "frontend/src/lib/product/state.svelte.ts", "frontend/src/routes/app/monitoring/+page.svelte"):
        assert "CAPSTONE_FL_CANDIDATE" not in (ROOT / rel).read_text(), rel
