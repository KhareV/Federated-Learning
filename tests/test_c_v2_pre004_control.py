"""C-V2-PRE004-CONTROL tests: locks the corrected V2-004 fit budget, D1/D2 staging rules,
architecture identities, the active promotion rule, V1-protocol immutability, and D0.6
provenance-chronology facts. Fails if any of these regress.
"""

from __future__ import annotations

import csv
import itertools
import json
import subprocess
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
V2_PROTOCOL_PATH = ROOT / "configs/model_v2/research_protocol_v2.yaml"
V1_PROTOCOL_PATH = ROOT / "configs/model_v2/research_protocol_v1.yaml"


def _load_v2_protocol() -> dict:
    return yaml.safe_load(V2_PROTOCOL_PATH.read_text(encoding="utf-8"))


def test_v2_004_registry_does_not_say_45_fits() -> None:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next(r for r in rows if r["task_id"] == "V2-004")
    assert "45 fits" not in row["notes"]
    assert "x 3 seeds = 45" not in row["notes"]


def test_v2_004_registry_states_35_fit_cap() -> None:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next(r for r in rows if r["task_id"] == "V2-004")
    assert "35" in row["notes"]
    # V2-004 has since legitimately run and passed (see tests/test_v2_004_results.py); this
    # checkpoint's own scope was only the fit-budget correction, not V2-004's eventual status.
    assert row["status"] in {"NOT_STARTED", "PASS"}


def test_d1_uses_only_release_seed() -> None:
    protocol = _load_v2_protocol()
    d1 = protocol["architecture_search_policy"]["stage_D1"]
    assert d1["seed"] == 20260927
    assert d1["total_fits"] == 15
    assert d1["folds"] == 5
    assert len(d1["architectures"]) == 3


def test_d2_at_most_two_architectures_and_remaining_seeds() -> None:
    protocol = _load_v2_protocol()
    d2 = protocol["architecture_search_policy"]["stage_D2"]
    assert d2["seeds"] == [20260928, 20260929]
    assert d2["max_additional_fits"] == 20
    assert d2["folds"] == 5


def test_v2_004_fit_budget_exactly_35() -> None:
    protocol = _load_v2_protocol()
    assert protocol["architecture_search_policy"]["maximum_v2_004_fits"] == 35


def test_architecture_identities_and_parameter_counts_unchanged() -> None:
    from models.model_v2_architectures import (
        ModelV2CapCtrl,
        ModelV2TcnMean,
        ModelV2TcnMeanMax,
        analytic_tcn_receptive_field_samples,
        count_trainable_parameters,
    )

    assert count_trainable_parameters(ModelV2CapCtrl()) == 51969
    assert count_trainable_parameters(ModelV2TcnMean()) == 57553
    assert count_trainable_parameters(ModelV2TcnMeanMax()) == 57577
    assert analytic_tcn_receptive_field_samples() == 3063


def test_active_promotion_rule_matches_authoritative_target() -> None:
    protocol = _load_v2_protocol()
    promotion = protocol["official_validation"]["promotion_requirement"]
    assert promotion["mean_three_seed_validation_auprc_min"] == 0.646
    assert (
        promotion["paired_patient_cluster_bootstrap_delta_auprc_vs_model_v1_lower_95_ci_bound_min"]
        == 0.0
    )
    assert "release_seed_validation_auprc_min" not in promotion


def test_v1_protocol_file_not_mutated() -> None:
    expected = "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
    assert hash_file(lock_path) == expected


def test_v1_protocol_still_contains_its_original_rule_as_historical_record() -> None:
    v1 = yaml.safe_load(V1_PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert v1["architecture_search_policy"]["primary_experiment_fits"]["total"] == 45
    assert (
        v1["official_validation"]["promotion_requirement"]["release_seed_validation_auprc_min"]
        == 0.5628607838787021
    )


def test_v2_protocol_is_additive_successor_not_a_v1_replacement() -> None:
    protocol = _load_v2_protocol()
    assert protocol["protocol_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V2"
    assert protocol["parent_protocol"] == "MODEL_V2_RESEARCH_PROTOCOL_V1"


def test_v2_protocol_unchanged_fields_match_v1() -> None:
    v1 = yaml.safe_load(V1_PROTOCOL_PATH.read_text(encoding="utf-8"))
    v2 = _load_v2_protocol()
    for key in (
        "fixed_scientific_constants",
        "model_seeds",
        "primary_metrics",
        "patient_cluster_bootstrap",
        "architectures",
        "feature_ablation_contract",
        "hybrid_trigger",
        "loss_and_sampling",
        "optimizer_experiment",
        "calibration_policy",
        "post_freeze_second_look",
        "runtime_acceptance_guardrails",
        "downstream_impact",
    ):
        assert v1[key] == v2[key], f"{key} changed between V1 and V2"


def test_tcn_gap_alias_resolves_to_tcn_mean_not_a_fourth_architecture() -> None:
    audit = json.loads(
        (ROOT / "reports/model_v2/c_v2_pre004_control/architecture_identity_audit.json").read_text()
    )
    assert audit["legacy_alias_resolution"]["resolves_to"] == "MODEL_V2_TCN_MEAN"
    assert audit["fourth_architecture_created"] is False


def test_d0_6_run_d0_6_diagnostics_not_in_method_or_correction_commit() -> None:
    audit = json.loads(
        (ROOT / "reports/model_v2/c_v2_pre004_control/d0_6_git_chronology_audit.json").read_text()
    )
    assert audit["defect_confirmed"]["concealed_or_relabeled"] is False
    never_frozen = audit["scope_of_missing_freeze"][
        "never_independently_frozen_before_producing_its_result"
    ]
    assert "scripts/run_d0_6_diagnostics.py" in never_frozen


def test_d0_6_ancestry_checks_all_pass() -> None:
    audit = json.loads(
        (ROOT / "reports/model_v2/c_v2_pre004_control/d0_6_git_chronology_audit.json").read_text()
    )
    for check in audit["ancestry_checks"].values():
        assert check["exit_code"] == 0
        assert check["pass"] is True


def test_missing_validation_sources_never_regenerated() -> None:
    audit = json.loads(
        (
            ROOT / "reports/model_v2/c_v2_pre004_control/missing_validation_source_audit.json"
        ).read_text()
    )
    for source in audit["missing_sources"]:
        assert source["still_missing"] is True
        assert source["regenerated"] is False
        assert source["classified_as_leakage"] is False


def test_no_forbidden_partition_access_in_firewall() -> None:
    from nhm.model_v2_d0_6_guard import FORBIDDEN_PATH_SUBSTRINGS, known_allowed_paths

    for path in known_allowed_paths():
        for forbidden in FORBIDDEN_PATH_SUBSTRINGS:
            assert forbidden not in path


def test_merge_base_ancestry_still_holds_mechanically() -> None:
    commits = [
        "37a2cecfa824be7b7d5b4dfc29b2ed0039b50f28",
        "19e62e297c3d94dc65c2556690e1bb939bf6bad1",
        "fff5f166f46fd266a3149334ace518536fae73e7",
        "69d7d90bf8a311a1c6ce65af0571cc5e620b8e2d",
    ]
    for ancestor, descendant in itertools.pairwise(commits):
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0


def test_registries_parse_consistently() -> None:
    for name in ["task_registry_v1.csv", "gate_registry_v1.csv", "component_registry_v1.csv"]:
        path = ROOT / "manifests/model_v2" / name
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        header_len = len(rows[0])
        assert all(len(row) == header_len for row in rows[1:])


def test_v2_protocol_component_registry_row_exists() -> None:
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next(r for r in rows if r["component_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V2")
    assert row["predecessor_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V1"
    assert row["status"] == "FROZEN_RESEARCH_PROTOCOL"


def test_v2_004_and_v2g3_not_regressed() -> None:
    # This checkpoint (C-V2-PRE004-CONTROL) ran strictly before V2-004; it required V2-004/
    # V2G3 to still be NOT_STARTED at that time, which was true and is preserved in
    # reports/model_v2/c_v2_pre004_control/entry_audit.json. V2-004 has since legitimately
    # run and passed -- this test only guards against an invalid status value.
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row["status"] for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    assert tasks["V2-004"] in {"NOT_STARTED", "PASS"}
    assert gates["V2G3"] in {"NOT_STARTED", "PASS"}
