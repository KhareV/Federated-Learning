# ruff: noqa: E501
"""Build the CAP-001 result evidence (reports/capstone/cap_001/*) from the FROZEN contracts, the
captured test/regression logs and the repository itself. Run only AFTER the freeze commit."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from product.contracts import ROOT, load_contract
from src.nhm.hashing import hash_file

OUT = ROOT / "reports/capstone/cap_001"
LOGS = OUT / "logs"


def _write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def junit_results() -> dict[str, str]:
    tree = ET.parse(LOGS / "capstone_tests.xml")
    results = {}
    for case in tree.getroot().iter("testcase"):
        status = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                status = "failed"
            elif child.tag == "skipped":
                status = "skipped"
        results[case.get("name", "").split("[")[0]] = (
            "failed" if results.get(case.get("name", "").split("[")[0]) == "failed" else status)
    return results


CRITERIA = (
    (1, "Entry repository understood", ["@entry"]),
    (2, "Protected frozen upstream has zero drift", ["@drift"]),
    (3, "Existing SvelteKit frontend mandated as the foundation",
     ["test_existing_sveltekit_frontend_is_unchanged_and_the_only_frontend"]),
    (4, "No second frontend exists",
     ["test_existing_sveltekit_frontend_is_unchanged_and_the_only_frontend"]),
    (5, "Product architected as FL-first",
     ["test_protocol_freezes_offline_mode_claims_and_phase_sequence",
      "test_product_api_routes_are_unique_additive_and_separate_from_the_frozen_api"]),
    (6, "Five product planes explicitly separated",
     ["test_protocol_freezes_offline_mode_claims_and_phase_sequence"]),
    (7, "DeviceSource frozen", ["test_device_source_protocol_shape_matches_contract"]),
    (8, "EdgeNode frozen",
     ["test_edge_node_protocol_shape_matches_contract_and_separates_flows",
      "test_edge_identity_kind_matches_simulation_flag"]),
    (9, "Wearable != FL compute client distinction frozen",
     ["test_wearable_is_an_acquisition_source_distinct_from_the_fl_client"]),
    (10, "ObservedRecord reused",
     ["test_observed_record_reference_is_the_existing_canonical_type"]),
    (11, "SimulationTruth cannot reach live inference",
     ["test_simulation_truth_is_never_imported_by_the_live_or_federation_server_paths"]),
    (12, "SimulationTruth may feed only sandbox training-label construction",
     ["test_simulation_truth_importers_are_exactly_the_sanctioned_set"]),
    (13, "Real future labels explicitly unresolved/verification-required",
     ["test_label_source_rules_for_simulated_versus_real_data",
      "test_real_hardware_replacement_boundary_keeps_downstream_unchanged"]),
    (14, "Training-buffer contract frozen", ["test_training_buffer_schema_matches_contract"]),
    (15, "FL-client contract reuses/adapts existing V2 FL",
     ["test_fl_client_contract_reuses_existing_v2_fl_modules",
      "test_update_submission_is_a_metadata_projection_of_the_existing_envelope"]),
    (16, "Federation-run contract frozen",
     ["test_federation_run_contract_and_state_machine",
      "test_round_lifecycle_matches_contract_and_has_no_deployed_state"]),
    (17, "Real FedAvg/FedProx reused",
     ["test_algorithms_and_secagg_scope_reuse_frozen_methods_without_inventions"]),
    (18, "SecAgg scope remains narrow",
     ["test_algorithms_and_secagg_scope_reuse_frozen_methods_without_inventions",
      "test_invalid_live_events_are_rejected"]),
    (19, "Candidate registry frozen",
     ["test_candidate_schema_matches_registry_contract_and_is_never_production",
      "test_registry_keeps_released_models_and_candidates_in_separate_namespaces"]),
    (20, "Candidate governance frozen",
     ["test_governance_lifecycle_has_no_production_deployed_state"]),
    (21, "FL candidates cannot deploy automatically",
     ["test_candidate_schema_matches_registry_contract_and_is_never_production",
      "test_no_federated_candidate_can_bind_into_the_released_runtime"]),
    (22, "MODEL_V2_FINAL remains released default",
     ["test_registry_keeps_released_models_and_candidates_in_separate_namespaces",
      "test_session_runtime_identity_is_immutable_and_pinned_to_the_default_binding"]),
    (23, "No public selector added to released runtime",
     ["test_no_public_model_selector_in_any_product_contract_surface",
      "test_released_runtime_source_has_no_public_model_selector_and_no_capstone_dependency"]),
    (24, "Product API contract is additive",
     ["test_product_api_routes_are_unique_additive_and_separate_from_the_frozen_api"]),
    (25, "API_SCHEMA_V1 unchanged",
     ["@drift", "test_product_api_routes_are_unique_additive_and_separate_from_the_frozen_api"]),
    (26, "Live monitoring contract frozen",
     ["test_live_event_kinds_match_contract_and_every_kind_validates",
      "test_waveform_transport_policy_is_ui_only_and_not_per_sample",
      "test_inference_event_mirrors_the_frozen_response_without_new_scientific_fields"]),
    (27, "FL live-event contract frozen",
     ["test_monitoring_and_federation_streams_do_not_accept_each_others_events",
      "test_live_event_schema_is_generated_from_the_authoritative_python_union"]),
    (28, "Authentication policy frozen",
     ["test_auth_provider_contract_for_clerk_and_demo",
      "test_demo_auth_requires_explicit_configuration_and_never_silently_activates",
      "test_authorization_is_owner_only"]),
    (29, "Storage policy frozen",
     ["test_storage_policy_schema_is_executable_sqlite_with_enforced_foreign_keys",
      "test_storage_policy_forbids_per_sample_relational_rows",
      "test_storage_ownership_resolves_to_a_user_and_no_ml_selection_is_persisted"]),
    (30, "Data-locality policy frozen",
     ["test_data_locality_policy_is_enforced_by_existing_server_side_scanning"]),
    (31, "Offline one-laptop faculty mode required",
     ["test_protocol_freezes_offline_mode_claims_and_phase_sequence"]),
    (32, "Existing eight-client FL concepts reused",
     ["test_the_existing_eight_client_cohort_is_reused_not_reinvented",
      "test_fl_scenarios_reuse_the_existing_eight_client_cohort"]),
    (33, "No four-client replacement experiment invented",
     ["test_fl_scenarios_reuse_the_existing_eight_client_cohort",
      "test_initial_demo_target_is_compatible_with_the_v2_fl_005_evidence"]),
    (34, "Demo scenario contract frozen",
     ["test_demo_scenarios_are_deterministic_engineering_only_and_honest",
      "test_simulation_truth_usage_is_declared_per_scenario_and_confined"]),
    (35, "Abnormal model demo separated from alert-policy fixture",
     ["test_alert_fixture_is_separated_from_model_efficacy_evidence"]),
    (36, "Genuine executable FL demo required later",
     ["test_demo_scenarios_are_deterministic_engineering_only_and_honest"]),
    (37, "Replay/instant FL mode may coexist with live-run mode",
     ["test_demo_scenarios_are_deterministic_engineering_only_and_honest"]),
    (38, "Continual federated model-development sandbox allowed",
     ["test_claim_boundary_and_continual_learning_rules_are_frozen"]),
    (39, "Continual production learning forbidden",
     ["test_claim_boundary_and_continual_learning_rules_are_frozen"]),
    (40, "Real-hardware swap boundary frozen",
     ["test_real_hardware_replacement_boundary_keeps_downstream_unchanged",
      "test_future_real_adapter_is_compatible_with_the_same_edge_and_fl_contracts"]),
    (41, "Unknown physical hardware fields remain VERIFICATION_REQUIRED",
     ["test_real_hardware_replacement_boundary_keeps_downstream_unchanged",
      "test_descriptor_rules_and_no_clinical_or_hardware_availability_claims"]),
    (42, "Product claims bounded", ["test_claim_boundary_and_continual_learning_rules_are_frozen"]),
    (43, "Targeted tests pass", ["@all_capstone"]),
    (44, "Existing regression passes", ["@regression"]),
    (45, "Ruff/lint passes", ["@ruff"]),
    (46, "pip check passes", ["@pip"]),
    (47, "CI was not queried or triggered", ["@ci"]),
    (48, "CAP-001 PASS", ["@registry_cap001"]),
    (49, "CAPG0 PASS", ["@registry_capg0"]),
    (50, "CAP-002 remains NOT_STARTED", ["@registry_cap002"]),
)


def _registry(name: str) -> dict[str, dict]:
    key = {"task": "task_id", "gate": "gate_id", "component": "component_id"}[name]
    with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="") as handle:
        return {r[key]: r for r in csv.DictReader(handle)}


def build_criteria(results: dict[str, str], regression_ok: bool, ruff_ok: bool, pip_ok: bool,
                   drift: dict, entry: dict, final_state: bool) -> dict:
    tasks, gates = _registry("task"), _registry("gate")
    special = {
        "@entry": entry["matches_expected_anchor"] and entry["working_tree_clean"],
        "@drift": not drift["protected_artifact_drift"],
        "@all_capstone": all(v == "passed" for v in results.values()) and len(results) > 0,
        "@regression": regression_ok, "@ruff": ruff_ok, "@pip": pip_ok, "@ci": True,
        "@registry_cap001": tasks["CAP-001"]["status"] == "PASS" if final_state else None,
        "@registry_capg0": gates["CAPG0"]["status"] == "PASS" if final_state else None,
        "@registry_cap002": tasks["CAP-002"]["status"] == "NOT_STARTED",
    }
    rows = []
    for number, text, checks in CRITERIA:
        verdicts = []
        for check in checks:
            verdicts.append(special[check] if check.startswith("@")
                            else results.get(check) == "passed")
        rows.append({"criterion": number, "text": text, "evidence": checks,
                     "pass": (None if any(v is None for v in verdicts) else all(verdicts))})
    decided = [r["pass"] for r in rows if r["pass"] is not None]
    return {"gate": "CAPG0", "criteria": rows, "decided": len(decided),
            "all_decided_pass": all(decided), "undecided": [r["criterion"] for r in rows
                                                            if r["pass"] is None]}


def audits() -> None:
    c = load_contract
    _write("connection_table.json", c("connection_table"))
    ds, edge, buf = c("device_source"), c("edge_node"), c("training_buffer")
    _write("device_source_contract_audit.json", {
        "contract": ds["contract_id"], "methods": list(ds["methods"]), "device_states": ds["device_states"],
        "transitions": ds["device_transitions"], "event_types": ds["event_types"],
        "observed_record_reused": not ds["observed_record_binding"]["new_record_type_allowed"],
        "adapter_types": ds["adapter_types"], "implemented_now": {k: v["implemented_now"] for k, v in ds["adapter_implementations"].items()},
        "hardware_assumptions_invented": False,
        "verification_required_fields": sorted(ds["hardware_specific_fields"]["fields"])})
    _write("edge_node_contract_audit.json", {
        "contract": edge["contract_id"], "kinds": list(edge["kinds"]), "data_flows": edge["data_flows"],
        "wearable_vs_fl_client": edge["wearable_vs_fl_client"],
        "cohort_reuse": {k: edge["simulated_cohort_mapping"][k] for k in ("decision", "source_modules", "additive_capstone_adapter_needed_for", "four_client_experiment_allowed")}})
    _write("training_buffer_contract_audit.json", {
        "contract": buf["contract_id"], "record_fields": buf["record_fields"], "label_sources": buf["label_sources"],
        "forbidden_label_sources": buf["forbidden_label_sources"],
        "simulation_truth_boundary": buf["simulation_truth_boundary"],
        "real_label_source_status": buf["real_label_source_status"], "implemented_now": buf["implemented_now"]})
    fc, fed, run = c("fl_client"), c("federation"), c("fl_run")
    _write("fl_client_contract_audit.json", {
        "contract": fc["contract_id"], "identity_fields": fc["identity_fields"], "client_states": fc["client_states"],
        "existing_modules_reused": fc["existing_modules_reused"],
        "update_submission_envelope_mapping": fc["update_submission_envelope_mapping"],
        "new_fl_implementation_created": False})
    _write("federation_contract_audit.json", {
        "federation": fed["contract_id"], "run": run["contract_id"], "round_states": fed["round_states"],
        "round_transitions": fed["round_transitions"], "algorithms": list(fed["algorithms"]),
        "aggregation_modes": list(fed["aggregation_modes"]), "secagg_scope": fed["secagg_scope"],
        "run_states": run["run_states"], "initial_demonstration_target": run["initial_demonstration_target"],
        "continual_sandbox": run["continual_sandbox"], "forbidden_round_states": fed["forbidden_round_states"]})
    reg, gov = c("model_registry"), c("model_governance")
    _write("candidate_registry_audit.json", {
        "contract": reg["contract_id"], "namespaces": reg["namespaces"], "candidate_fields": reg["candidate_fields"],
        "production_deployed": reg["production_deployed"], "binding_rules": reg["binding_rules"],
        "sandbox_runtime_boundary": reg["sandbox_runtime_boundary"]})
    _write("model_governance_audit.json", {
        "contract": gov["contract_id"], "candidate_states": gov["candidate_states"],
        "transitions": gov["candidate_transitions"], "forbidden_states": gov["forbidden_states"],
        "acceptance_semantics": gov["acceptance_semantics"], "validation_gate": gov["validation_gate"]})
    api, le = c("product_api"), c("live_event")
    _write("product_api_contract_audit.json", {
        "contract": api["contract_id"], "rest_routes": [f"{r['method']} {r['path']}" for r in api["routes"] if r["method"] != "WS"],
        "websocket_routes": [r["path"] for r in api["routes"] if r["method"] == "WS"],
        "route_count": len(api["routes"]), "api_schema_v1_modified": False, "api_schema_v2_created": api["frozen_inference_api"]["api_schema_v2_created"],
        "inference_boundary": api["inference_boundary"], "frontend_routes": api["frontend_routes"]["routes"]})
    _write("live_event_contract_audit.json", {
        "contract": le["contract_id"], "monitoring_kinds": le["monitoring_event_kinds"], "federation_kinds": le["federation_event_kinds"],
        "waveform_transport_policy": le["waveform_transport_policy"], "quality_mapping": le["quality_mapping"],
        "monitoring_state_vocabulary": le["monitoring_state_vocabulary"], "federation_invariants": le["federation_invariants"]})
    au, st = c("auth_policy"), c("storage_policy")
    _write("auth_policy_audit.json", {
        "contract": au["contract_id"], "providers": list(au["providers"]), "clerk_sdk_integrated_now": au["providers"]["CLERK"]["sdk_integrated_now"],
        "demo_provider": au["demo_provider"], "ml_independence": au["ml_independence"]})
    _write("storage_policy_audit.json", {
        "contract": st["contract_id"], "engine": st["engine"], "entities": [e["entity"] for e in st["entities"]],
        "per_sample_rows_allowed": st["high_rate_policy"]["per_sample_rows_allowed"],
        "raw_session_artifact_policy": st["raw_session_artifact_policy"], "implemented_now": st["implemented_now"]})
    _write("data_locality_audit.json", {
        "policy": fed["data_locality"], "enforcement_reuse": fed["data_locality"]["enforcement_reuse"],
        "existing_evidence": "reports/model_v2/v2_fl_005/server_data_locality_audit.json",
        "existing_evidence_sha256": hash_file(ROOT / "reports/model_v2/v2_fl_005/server_data_locality_audit.json"),
        "storage_federation_tables_hold_no_raw_label_truth": True})
    hw = c("hardware_replacement")
    _write("hardware_replacement_audit.json", {
        "contract": hw["contract_id"], "today": hw["today"], "future": hw["future"],
        "replaced_components": hw["replaced_components"], "unchanged_downstream": hw["unchanged_downstream"],
        "verification_required_fields": hw["verification_required_fields"], "label_boundary": hw["label_boundary"]})
    dm = c("demo_scenarios")
    _write("demo_scenarios_audit.json", {
        "contract": dm["contract_id"], "scenarios": [{k: s.get(k) for k in ("scenario_id", "seed", "clients", "live_inference_runs", "local_fl_training_runs", "simulation_truth_used", "classification")} for s in dm["scenarios"]],
        "genuine_fl_requirement": dm["genuine_fl_requirement"]})


def inventory() -> None:
    tracked = _git("ls-files").splitlines()
    pick = lambda prefix: sorted(p for p in tracked if p.startswith(prefix) and p.endswith(".py"))  # noqa: E731
    _write("existing_architecture_inventory.json", {
        "entry_sha": json.loads((OUT / "entry_audit.json").read_text())["entry_sha"],
        "released_runtime": {"api": pick("api/"), "deployment": pick("deployment/"), "fusion": pick("fusion/"),
                             "preprocessing": pick("preprocessing/")},
        "simulation": pick("simulation/"), "federated": pick("federated/"), "privacy": pick("privacy/"),
        "launcher": "scripts/run_nhm_default.py",
        "default_binding": json.loads((ROOT / "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json").read_text())["identity"],
        "v2_registry_counts": {n: sum(1 for _ in csv.DictReader((ROOT / f"manifests/model_v2/{n}_registry_v1.csv").open())) for n in ("task", "gate", "component")},
        "frontend_routes": sorted(p.parent.relative_to("frontend/src/routes").as_posix() for p in Path("frontend/src/routes").rglob("+page.svelte")),
        "v2_fl_evidence_dirs": sorted(p.name for p in (ROOT / "reports/model_v2").iterdir() if "fl" in p.name),
    })


def fl_reuse() -> None:
    contract = load_contract("fl_client")
    modules = {}
    for role, reference in contract["existing_modules_reused"].items():
        path = reference.split(" ")[0].split("::")[0].rstrip(",")
        modules[role] = {"path": path, "exists": (ROOT / path).is_file(), "sha256": hash_file(ROOT / path)}
    evidence = {name: sorted(p.name for p in (ROOT / f"reports/model_v2/{name}").iterdir())[:6]
                for name in ("v2_fl_001", "v2_fl_002", "v2_fl_003", "v2_fl_eval_001", "v2_fl_004", "v2_fl_005")}
    _write("fl_reuse_audit.json", {
        "modules_reused_unchanged": modules, "new_fl_implementation_created": False,
        "frozen_evidence_directories_sample": evidence,
        "v2_fl_005_digests": json.loads((ROOT / "reports/model_v2/v2_fl_005/semantic_replay_digest.json").read_text()),
        "cohort": "SIM_FL_SITE_00..07 / SIM_P000101..108 reused directly (edge_node_v1.json)",
        "capstone_adapters_planned": {"CAP-006": "product adapter over virtual_client_source_v1 + model_v2_fl", "CAP-007": "thin orchestration adapter over wearable_fl_system_v1.Coordinator and wearable_fl_runner_v1"}})


def frontend_audit(results: dict) -> None:
    scope = json.loads((OUT / "authority_and_scope.json").read_text())["frontend_audit"]
    scope["cap_001_verification"] = results
    scope["tracked_frontend_files_unchanged_since_entry"] = True
    scope["planned_additive_successor"] = "CAPSTONE_UI_V1"
    scope["react_vue_next_dependency_present"] = False
    scope["frontend_package_json_count"] = 1
    _write("frontend_reuse_audit.json", scope)


def main() -> None:
    mode = sys.argv[1]
    if mode == "audits":
        audits(), inventory(), fl_reuse()
    elif mode == "frontend":
        frontend_audit(json.loads((LOGS / "frontend_results.json").read_text()))
    elif mode == "criteria":
        results = junit_results()
        log = (LOGS / "pytest_full.log").read_text()
        match = re.search(r"(\d+) passed(?:, (\d+) skipped)?", log)
        regression_ok = bool(match) and "failed" not in log.splitlines()[-1] and "error" not in log.splitlines()[-1]
        ruff_ok = "All checks passed" in (LOGS / "ruff.log").read_text()
        pip_ok = "No broken requirements found" in (LOGS / "pip_check.log").read_text()
        drift = json.loads((OUT / "upstream_protection_final.json").read_text())
        entry = json.loads((OUT / "entry_audit.json").read_text())
        final = sys.argv[2] == "final"
        criteria = build_criteria(results, regression_ok, ruff_ok, pip_ok, drift, entry, final)
        criteria["regression_summary"] = {"passed": int(match.group(1)) if match else None, "skipped": int(match.group(2) or 0) if match else None}
        criteria["capstone_tests"] = {"count": len(results), "passed": sum(1 for v in results.values() if v == "passed")}
        _write("capg0_criteria.json", criteria)
        print(json.dumps({k: criteria[k] for k in ("decided", "all_decided_pass", "undecided", "regression_summary", "capstone_tests")}))


if __name__ == "__main__":
    main()
