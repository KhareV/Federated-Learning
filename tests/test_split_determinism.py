"""Determinism, seed-immutability, and no-result-driven-input checks for the T009 split
builder (v2.2 Sections 32/39/40)."""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_split_builder_regenerates_byte_identical_output() -> None:
    from scripts.build_mitdb_split_t009 import build_split

    first = build_split()
    second = build_split()
    assert first["groups_text"] == second["groups_text"]
    assert first["strata_text"] == second["strata_text"]
    assert first["split_text"] == second["split_text"]
    assert first["split_yaml_text"] == second["split_yaml_text"]


def test_committed_split_generation_report_confirms_determinism() -> None:
    report = json.loads((ROOT / "reports/t009/split_generation.json").read_text(encoding="utf-8"))
    assert report["determinism_check"] is True
    assert report["candidate_seeds_tried"] == 1
    assert report["manual_adjustments"] == "none"


def test_split_manifest_records_seed_and_algorithm_identifiers() -> None:
    split_yaml = yaml.safe_load(
        (ROOT / "manifests/splits/MITDB_SPLIT_V1.yaml").read_text(encoding="utf-8")
    )
    assert split_yaml["split_seed"] == 20260927
    assert split_yaml["allocation_algorithm"]
    assert split_yaml["rounding_algorithm"]
    assert split_yaml["stable_order_method"]


def test_different_seed_produces_different_order_where_data_permits() -> None:
    from datasets.grouping import stable_group_order

    ids = [f"MITDB_P{n}" for n in range(10)]
    committed = stable_group_order("MITDB_SPLIT_V1", 20260927, "POSITIVE", ids)
    alternate = stable_group_order("MITDB_SPLIT_V1", 1, "POSITIVE", ids)
    assert committed != alternate


def test_build_script_exposes_no_seed_search_or_best_balance_cli() -> None:
    source = (ROOT / "scripts/build_mitdb_split_t009.py").read_text(encoding="utf-8")
    for forbidden in ("--try-seeds", "--best-balance", "argparse", "candidate_split"):
        assert forbidden not in source


def test_grouping_module_exposes_no_seed_search_or_best_balance_cli() -> None:
    source = (ROOT / "datasets/grouping.py").read_text(encoding="utf-8")
    for forbidden in ("--try-seeds", "--best-balance", "argparse"):
        assert forbidden not in source


def test_split_independence_audit_passes_with_no_forbidden_imports_or_paths() -> None:
    report = json.loads(
        (ROOT / "reports/t009/split_independence_audit.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "PASS"
    assert report["errors"] == []
    for module_findings in report["findings"].values():
        assert module_findings["forbidden_imports"] == []
        assert module_findings["forbidden_path_strings"] == []


def test_split_builder_source_imports_no_model_training_or_evaluation_code() -> None:
    import ast

    tree = ast.parse((ROOT / "scripts/build_mitdb_split_t009.py").read_text(encoding="utf-8"))
    forbidden_prefixes = ("models", "training", "evaluation", "calibration", "federated")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_prefixes
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module.split(".")[0] not in forbidden_prefixes
