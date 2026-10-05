"""CAP-009 frozen-summary catalog parity, read firewall, and tamper controls."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest

import scripts.build_capstone_research_evidence_catalog as builder
import scripts.verify_capstone_research_evidence_catalog as verifier

ROOT = Path(__file__).resolve().parents[1]


def test_two_fresh_catalog_builds_are_byte_identical_and_verified() -> None:
    first = builder.build()
    second = builder.build()
    assert first == second
    assert verifier.verify()["status"] == "PASS"
    assert first[0]["scientific_fl_phases"] == [
        "V2-FL-001",
        "V2-FL-002",
        "V2-FL-003",
        "V2-FL-EVAL-001",
        "V2-FL-004",
    ]
    assert all(
        f["source_sha256"] and f["source_locator"]
        for f in first[0]["ml_facts"] + first[0]["fl_facts"]
    )


def test_catalog_builder_only_reads_approved_summary_files() -> None:
    paths = {
        builder.source_path(spec).relative_to(ROOT).as_posix()
        for spec in (*builder.ML, *builder.FL)
    }
    assert all(path.startswith(("reports/model_v2/", "artifacts/CAL_V2.json")) for path in paths)
    assert not any("prediction" in path.lower() or path.endswith(".csv") for path in paths)
    assert not any("v2_fl_005" in path.lower() for path in paths)
    for relative in (
        "product/research/service.py",
        "product/research/catalog.py",
        "scripts/build_capstone_research_evidence_catalog.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(
            name.startswith(("torch", "wfdb", "federated", "models", "simulation"))
            for name in imports
        )


@pytest.mark.parametrize("target", ["catalog", "lock", "source"])
def test_catalog_verifier_rejects_tamper_in_private_shadow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    shadow = tmp_path / "repo"
    source_paths = sorted(
        {builder.source_path(spec).relative_to(ROOT) for spec in (*builder.ML, *builder.FL)}
    )
    for relative in [
        *source_paths,
        builder.CATALOG.relative_to(ROOT),
        builder.LOCK.relative_to(ROOT),
    ]:
        (shadow / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, shadow / relative)
    monkeypatch.setattr(builder, "ROOT", shadow)
    monkeypatch.setattr(verifier, "CATALOG", shadow / builder.CATALOG.relative_to(ROOT))
    monkeypatch.setattr(verifier, "LOCK", shadow / builder.LOCK.relative_to(ROOT))
    assert verifier.verify()["status"] == "PASS"
    victim = {
        "catalog": shadow / builder.CATALOG.relative_to(ROOT),
        "lock": shadow / builder.LOCK.relative_to(ROOT),
        "source": shadow / source_paths[0],
    }[target]
    if target == "source":
        payload = json.loads(victim.read_text(encoding="utf-8"))
        payload["temperature"] = -123
        victim.write_text(json.dumps(payload), encoding="utf-8")
    else:
        victim.write_text(victim.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        verifier.verify()
