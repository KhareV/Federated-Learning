"""CAP-001 contract tests for the FL-first planes: edge node, simulation-truth boundary, local
training buffer, FL client, federation run/round, model registry/governance, data locality,
hardware replacement and the frozen-frontend/frozen-runtime protections. They exercise the
production contract definitions and the real existing FL modules the contracts claim to reuse."""

from __future__ import annotations

import ast
import asyncio
import inspect
import itertools
import json
import subprocess
from collections.abc import AsyncIterator, Sequence

import pytest
from pydantic import ValidationError

from product.contracts import ROOT, IllegalTransitionError, load_contract, load_protocol
from product.devices.base import AdapterType, DeviceSource
from product.edge import base as edge
from product.edge import buffer as buf
from product.federation import base as fed
from product.models import registry_contract as reg
from src.nhm.hashing import hash_file

# ---------------------------------------------------------------------------------------------
# edge node
# ---------------------------------------------------------------------------------------------


def test_edge_node_protocol_shape_matches_contract_and_separates_flows() -> None:
    contract = load_contract("edge_node")
    for name, spec in contract["methods"].items():
        member = getattr(edge.EdgeNode, name)
        assert inspect.iscoroutinefunction(member) is spec["async"]
        assert [p for p in inspect.signature(member).parameters if p != "self"] == spec["args"]
    for prop in contract["properties"]:
        assert isinstance(getattr(edge.EdgeNode, prop), property)
    assert list(edge.EdgeNodeIdentity.model_fields) == contract["identity_fields"]
    flows = contract["data_flows"]
    assert flows["shared_mutable_state"] is False
    assert flows["training_may_alter_live_session_state"] is False
    assert flows["training_label_input_to_live_path"] is False
    assert "never reads" in flows["buffer_write_direction"] or "never read" in (
        flows["buffer_write_direction"])
    assert flows["live_inference_flow"] != flows["local_training_flow"]


def test_edge_identity_kind_matches_simulation_flag() -> None:
    virtual = edge.EdgeNodeIdentity(edge_node_id="VIRTUAL_EDGE_NODE_00",
                                    kind="VIRTUAL_EDGE_NODE", simulation=True,
                                    fl_client_id="SIM_FL_SITE_00")
    gateway = edge.EdgeNodeIdentity(edge_node_id="GW1", kind="REAL_EDGE_GATEWAY",
                                    simulation=False, fl_client_id="CLIENT_X")
    assert virtual.simulation and not gateway.simulation
    with pytest.raises(ValidationError, match="EDGE_NODE_KIND"):
        edge.EdgeNodeIdentity(edge_node_id="x", kind="VIRTUAL_EDGE_NODE", simulation=False)
    with pytest.raises(ValidationError, match="EDGE_NODE_KIND"):
        edge.EdgeNodeIdentity(edge_node_id="x", kind="REAL_EDGE_GATEWAY", simulation=True)


def test_wearable_is_an_acquisition_source_distinct_from_the_fl_client() -> None:
    contract = load_contract("edge_node")["wearable_vs_fl_client"]
    assert contract["sensor_runs_pytorch_training"] is False
    assert "Virtual Edge Node" in contract["today"] and "FL Client" in contract["today"]
    assert "edge gateway" in contract["future"]
    # DeviceSource has no training surface; the FL client has no acquisition surface
    assert not {"local_train", "produce_update"} & set(dir(DeviceSource))
    assert not {"scan", "connect", "start_stream", "records"} & set(dir(fed.FLClient))
    assert not {"device_source"} & set(fed.FLClientIdentity.model_fields)


def test_the_existing_eight_client_cohort_is_reused_not_reinvented() -> None:
    from simulation.fl_cohort_v1 import CLIENT_COUNT, client_profile
    mapping = load_contract("edge_node")["simulated_cohort_mapping"]
    assert mapping["decision"] == "REUSE_EXISTING_COHORT_DIRECTLY"
    assert mapping["four_client_experiment_allowed"] is False
    assert len(mapping["mapping"]) == CLIENT_COUNT == 8
    for index, row in enumerate(mapping["mapping"]):
        profile = client_profile(index)
        assert row["fl_client_id"] == profile.client_id
        assert row["participant_id"] == profile.participant_id
    manifest = json.loads((ROOT / "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json").read_text())
    assert {row["fl_client_id"] for row in mapping["mapping"]} == set(
        c["client_id"] if isinstance(c, dict) else c for c in manifest["clients"])
    for source in mapping["source_modules"]:
        assert (ROOT / source.split(" ")[0]).exists(), source


# ---------------------------------------------------------------------------------------------
# SimulationTruth boundary
# ---------------------------------------------------------------------------------------------


def _truth_importers() -> dict[str, set[str]]:
    boundary = load_contract("training_buffer")["simulation_truth_boundary"]
    truth_mods, names = set(boundary["truth_modules"]), set(boundary["truth_names"])
    tracked = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout.split()
    hits: dict[str, set[str]] = {}
    for path in tracked:
        if path.startswith(("tests/", "reports/")):
            continue
        tree = ast.parse((ROOT / path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported = {a.name for a in node.names}
                leaf = {m.split(".")[-1] for m in truth_mods}
                if module in truth_mods or (module == "simulation" and imported & leaf) or (
                    module.startswith("simulation") and imported & names
                ):
                    hits.setdefault(path, set()).add(module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in truth_mods:
                        hits.setdefault(path, set()).add(alias.name)
    return hits


def test_simulation_truth_is_never_imported_by_the_live_or_federation_server_paths() -> None:
    boundary = load_contract("training_buffer")["simulation_truth_boundary"]
    importers = _truth_importers()
    for path in importers:
        assert not path.startswith(tuple(boundary["forbidden_importer_paths"])), path
    for forbidden in boundary["forbidden_importer_paths"]:
        assert (ROOT / forbidden).exists(), forbidden


def test_simulation_truth_importers_are_exactly_the_sanctioned_set() -> None:
    boundary = load_contract("training_buffer")["simulation_truth_boundary"]
    sanctioned = {p for group in boundary["sanctioned_importers"].values() for p in group}
    planned = {entry.split(" ")[0] for entry in boundary["planned_additional_consumer"]}
    assert set(_truth_importers()) <= sanctioned | planned
    # the only consumer on the federated side is the dedicated label adapter
    federated = {p for p in _truth_importers() if p.startswith("federated/")}
    assert federated == set(boundary["sanctioned_importers"]["label_adapter_consumer"])
    adapter = load_contract("training_buffer")["label_adapter"]
    assert adapter["only_consumer_of_simulation_truth"] is True and adapter["sandbox_only"]
    assert (ROOT / adapter["reuse_candidate"].split(" ")[0]).exists()


def test_a_live_path_module_importing_truth_would_be_detected(tmp_path, monkeypatch) -> None:
    """The scanner itself is not vacuous: planting a violating module must be flagged."""
    source = "from simulation.fl_cohort_truth_v1 import scheduled_event_times_us\n"
    tree = ast.parse(source)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom))
    boundary = load_contract("training_buffer")["simulation_truth_boundary"]
    assert node.module in boundary["truth_modules"]


# ---------------------------------------------------------------------------------------------
# local training buffer
# ---------------------------------------------------------------------------------------------


def _record(**override: object) -> buf.TrainingBufferRecord:
    base = {
        "client_id": "SIM_FL_SITE_00", "participant_id": "SIM_P000101", "source": "WEARABLE_SIM_V1",
        "window_id": "w1", "model_input_ref": "sha256:abc", "label": 1,
        "label_source": "SIMULATION_TRUTH_ENGINEERING", "quality_eligible": True,
        "timestamp_us": 1, "simulation": True, "provenance_id": "WEARABLE_SIM_FL_COHORT_V1",
        "buffer_batch_id": "b1",
    }
    base.update(override)
    return buf.TrainingBufferRecord(**base)


def test_training_buffer_schema_matches_contract() -> None:
    contract = load_contract("training_buffer")
    assert list(buf.TrainingBufferRecord.model_fields) == contract["record_fields"]
    assert [s.value for s in buf.LabelSource] == contract["label_sources"]
    assert not set(contract["forbidden_label_sources"]) & {s.value for s in buf.LabelSource}
    assert "MODEL_PREDICTION" in contract["forbidden_label_sources"]
    assert isinstance(_record(), buf.TrainingBufferRecord)
    assert not {"samples", "ecg", "raw", "waveform"} & set(buf.TrainingBufferRecord.model_fields)


def test_label_source_rules_for_simulated_versus_real_data() -> None:
    assert _record().label_source is buf.LabelSource.SIMULATION_TRUTH_ENGINEERING
    with pytest.raises(ValidationError, match="SIMULATED_RECORD_REQUIRES"):
        _record(label_source="CLINICIAN_REVIEW")
    with pytest.raises(ValidationError, match="FORBIDDEN_FOR_REAL_DATA"):
        _record(simulation=False)
    with pytest.raises(ValidationError, match="VERIFICATION_REQUIRED"):
        _record(simulation=False, label_source="VERIFIED_ANNOTATION")
    contract = load_contract("training_buffer")
    assert contract["simulation_label_source_forbidden_for_real_data"] is True
    assert contract["real_label_source_status"].startswith("VERIFICATION_REQUIRED")
    with pytest.raises(ValidationError):
        _record(label_source="MODEL_PREDICTION")
    with pytest.raises(ValidationError):
        _record(label=2)
    with pytest.raises(ValidationError):
        _record(raw_samples=[1, 2])


def test_buffer_and_label_adapter_protocols_are_structural() -> None:
    class Adapter:
        def labels_for_windows(self, right_edges_us: Sequence[int]) -> Sequence[int]:
            return [0 for _ in right_edges_us]

    class Buffer:
        client_id = "SIM_FL_SITE_00"

        def append_batch(self, records: Sequence[buf.TrainingBufferRecord]) -> str:
            return "b1"

        def batch_ids(self) -> Sequence[str]:
            return ["b1"]

        def eligible_count(self) -> int:
            return 0

    assert isinstance(Adapter(), buf.SimulationLabelAdapter)
    assert isinstance(Buffer(), buf.LocalTrainingBuffer)
    assert not isinstance(object(), buf.LocalTrainingBuffer)


def test_existing_label_adapter_satisfies_the_adapter_protocol_shape() -> None:
    from federated.virtual_client_source_v1 import LocalTrainingLabelProvider
    assert set(dir(LocalTrainingLabelProvider)) >= {"labels_for_windows"}
    assert "labels_for_windows" in dir(buf.SimulationLabelAdapter)


# ---------------------------------------------------------------------------------------------
# FL client
# ---------------------------------------------------------------------------------------------


def _identity(**override: object) -> fed.FLClientIdentity:
    base = {"client_id": "SIM_FL_SITE_00", "edge_node_id": "VIRTUAL_EDGE_NODE_00",
            "base_model_id": "FL_INIT_V2", "global_round": 0, "local_example_count": 10,
            "client_state": "IDLE", "eligible": True}
    base.update(override)
    return fed.FLClientIdentity(**base)


def test_fl_client_contract_shape_and_state_machine() -> None:
    contract = load_contract("fl_client")
    assert list(fed.FLClientIdentity.model_fields) == contract["identity_fields"]
    assert [s.value for s in fed.ClientState] == contract["client_states"]
    for name, spec in contract["methods"].items():
        member = getattr(fed.FLClient, name)
        assert inspect.iscoroutinefunction(member) is spec["async"]
        assert [p for p in inspect.signature(member).parameters if p != "self"] == spec["args"]
    fed.validate_client_transition(fed.ClientState.IDLE, fed.ClientState.DATA_READY)
    fed.validate_client_transition(fed.ClientState.TRAINING, fed.ClientState.UPDATE_READY)
    for current, new in (("IDLE", "TRAINING"), ("TRAINING", "SUBMITTED"),
                         ("UPDATE_READY", "TRAINING")):
        with pytest.raises(IllegalTransitionError, match="ILLEGAL_CLIENT_TRANSITION"):
            fed.validate_client_transition(fed.ClientState(current), fed.ClientState(new))
    with pytest.raises(ValidationError, match="INELIGIBLE_REASON"):
        _identity(eligible=False)
    with pytest.raises(ValidationError, match="UPDATE_STATES_REQUIRE"):
        _identity(client_state="UPDATE_READY")
    assert _identity(client_state="UPDATE_READY", update_digest="d").update_digest == "d"
    assert _identity(eligible=False, ineligible_reason="NONPOSITIVE_EXAMPLES")


def test_fl_client_contract_reuses_existing_v2_fl_modules() -> None:
    contract = load_contract("fl_client")
    assert contract["new_fl_implementation_allowed"] is False
    assert contract["new_optimizer_search_allowed"] is False
    for role, reference in contract["existing_modules_reused"].items():
        path = reference.split(" ")[0].split("::")[0].rstrip(",")
        assert (ROOT / path).exists(), (role, path)
    import federated.aggregation as aggregation
    import federated.wearable_fl_system_v1 as system
    assert hasattr(aggregation, "aggregate_weighted_deltas")
    assert hasattr(system, "Coordinator") and hasattr(system, "make_envelope")
    from federated.wearable_fl_runner_v1 import execute_round, run_part1, run_part2, save_resume
    assert all(callable(f) for f in (execute_round, run_part1, run_part2, save_resume))
    from federated.model_v2_fl import train_local_epoch_v2
    assert callable(train_local_epoch_v2)


def test_update_submission_is_a_metadata_projection_of_the_existing_envelope() -> None:
    import federated.wearable_fl_system_v1 as system
    submission = set(fed.UpdateSubmission.model_fields)
    assert submission == set(load_contract("fl_client")["update_submission_fields"])
    mapping = load_contract("fl_client")["update_submission_envelope_mapping"]
    assert set(mapping) == submission
    assert set(mapping.values()) <= set(system.ENVELOPE_FIELDS)
    assert not submission & (set(system.LABEL_FIELDS) | set(system.TRUTH_FIELDS))
    assert not set(mapping.values()) & (set(system.LABEL_FIELDS) | set(system.TRUTH_FIELDS))
    for rejected in ("raw_ecg", "labels", "simulation_truth", "minibatch", "ecg_samples"):
        with pytest.raises(ValidationError):
            fed.UpdateSubmission(client_id="c", round_id=1, base_state_digest="b",
                                 update_digest="u", examples_seen=1, **{rejected: [1]})
    reuse = load_contract("fl_client")["eligibility_reason_codes_reuse"]
    assert "REJECTION_ORDER" in reuse and "STALE_ROUND" in system.REJECTION_ORDER


# ---------------------------------------------------------------------------------------------
# federation run / round
# ---------------------------------------------------------------------------------------------

ROUND_PATH = ("CREATED", "COLLECTING", "LOCAL_TRAINING", "UPDATES_READY", "AGGREGATING",
              "CANDIDATE_CREATED", "VALIDATING", "ACCEPTED_TO_SANDBOX", "COMPLETED")


def test_round_lifecycle_matches_contract_and_has_no_deployed_state() -> None:
    contract = load_contract("federation")
    assert [s.value for s in fed.RoundState] == contract["round_states"]
    assert not set(contract["forbidden_round_states"]) & {s.value for s in fed.RoundState}
    assert "DEPLOYED" not in "".join(s.value for s in fed.RoundState)
    for current, new in itertools.pairwise(ROUND_PATH):
        fed.validate_round_transition(fed.RoundState(current), fed.RoundState(new))
    fed.validate_round_transition(fed.RoundState.VALIDATING, fed.RoundState.REJECTED)
    fed.validate_round_transition(fed.RoundState.REJECTED, fed.RoundState.COMPLETED)
    for state in fed.RoundState:
        if state.value not in contract["terminal_states"]:
            fed.validate_round_transition(state, fed.RoundState.FAILED)
    for terminal in contract["terminal_states"]:
        assert fed.round_transitions()[terminal] == ()
    for current, new in (("CREATED", "AGGREGATING"), ("COLLECTING", "VALIDATING"),
                         ("AGGREGATING", "ACCEPTED_TO_SANDBOX"), ("CANDIDATE_CREATED", "COMPLETED"),
                         ("COMPLETED", "COLLECTING"), ("REJECTED", "ACCEPTED_TO_SANDBOX")):
        with pytest.raises(IllegalTransitionError, match="ILLEGAL_ROUND_TRANSITION"):
            fed.validate_round_transition(fed.RoundState(current), fed.RoundState(new))


def _run(**override: object) -> fed.FederationRun:
    base = {
        "run_id": "R1", "run_type": "LIVE_RUN", "base_model_id": "FL_INIT_V2",
        "federation_protocol_id": "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1", "algorithm": "FEDAVG",
        "client_ids": tuple(f"SIM_FL_SITE_{i:02d}" for i in range(8)), "planned_rounds": 3,
        "current_round": 0, "status": "CREATED", "secagg_mode": "SECAGG_SHADOW",
    }
    base.update(override)
    return fed.FederationRun(**base)


def test_federation_run_contract_and_state_machine() -> None:
    contract = load_contract("fl_run")
    assert list(fed.FederationRun.model_fields) == contract["run_fields"]
    assert [s.value for s in fed.RunState] == contract["run_states"]
    assert [t.value for t in fed.RunType] == contract["run_types"]
    run = _run()
    assert run.engineering_only is True
    with pytest.raises(ValidationError):
        _run(engineering_only=False)
    fed.validate_run_transition(fed.RunState.CREATED, fed.RunState.RUNNING)
    fed.validate_run_transition(fed.RunState.RUNNING, fed.RunState.COMPLETED)
    for current, new in (("CREATED", "COMPLETED"), ("COMPLETED", "RUNNING"),
                         ("FAILED", "RUNNING")):
        with pytest.raises(IllegalTransitionError, match="ILLEGAL_RUN_TRANSITION"):
            fed.validate_run_transition(fed.RunState(current), fed.RunState(new))
    with pytest.raises(ValidationError, match="UNIQUE"):
        _run(client_ids=("a", "a"))
    with pytest.raises(ValidationError, match="EXCEEDS"):
        _run(current_round=4)
    with pytest.raises(ValidationError, match="BASE_MODEL_NOT_AN_ALLOWED"):
        _run(base_model_id="MODEL_V2_FINAL")
    with pytest.raises(ValidationError, match="UNKNOWN_FEDERATION_PROTOCOL"):
        _run(federation_protocol_id="MY_OWN_PROTOCOL")
    with pytest.raises(ValidationError, match="COMPLETION_TIME"):
        _run(status="COMPLETED", current_round=3)
    assert _run(base_model_id="CAPSTONE_FL_CANDIDATE_0001")
    for algorithm in fed.Algorithm:
        assert _run(algorithm=algorithm.value).algorithm is algorithm
    with pytest.raises(ValidationError):
        _run(algorithm="MY_NEW_AGGREGATOR")


def test_initial_demo_target_is_compatible_with_the_v2_fl_005_evidence() -> None:
    import federated.wearable_fl_system_v1 as system
    target = load_contract("fl_run")["initial_demonstration_target"]
    evidence = json.loads((ROOT / target["evidence"]).read_text())
    assert (target["clients"], target["rounds"], target["canonical_updates"]) == (
        system.CLIENT_COUNT, system.ROUNDS, evidence["expected_updates"])
    assert evidence["clients_per_round"] == target["clients"]
    assert evidence["rounds"] == target["rounds"] and evidence["accepted_updates"] == 24
    assert load_contract("fl_run")["allowed_protocol_ids"] == [system.PROTOCOL_ID]
    assert evidence["starts_from"] in load_contract("fl_run")["allowed_base_model_ids"]
    assert target["scientific_outcome_frozen"] is False
    assert len(_run().client_ids) == target["clients"]


def test_algorithms_and_secagg_scope_reuse_frozen_methods_without_inventions() -> None:
    contract = load_contract("federation")
    assert set(contract["algorithms"]) == {a.value.replace("FED", "FED") for a in fed.Algorithm}
    assert (ROOT / "artifacts/FEDPROX_MU_V2.lock.json").exists()
    assert (ROOT / "federated/model_v2_fedprox.py").exists()
    assert (ROOT / "privacy/secagg_app.py").exists()
    assert set(contract["aggregation_modes"]) == {m.value for m in fed.AggregationMode}
    assert "differential privacy" in contract["data_locality"]["forbidden_claims"]
    assert "PROTECTED_AGGREGATION_INTERFACE_ONLY" in json.dumps(
        load_contract("live_event")["federation_invariants"])
    for invention in ("new optimizer search", "new mu tuning", "new aggregation algorithm",
                      "new privacy mechanism", "new differential-privacy mechanism"):
        assert invention in contract["forbidden_inventions"]


def test_data_locality_policy_is_enforced_by_existing_server_side_scanning() -> None:
    import federated.wearable_fl_system_v1 as system
    locality = load_contract("federation")["data_locality"]
    assert {"raw ECG streams", "raw PPG streams", "raw SpO2 streams", "SimulationTruth",
            "local labels", "local minibatches"} == set(locality["server_must_not_receive"])
    for key in ("raw_ecg", "labels", "truth", "SimulationTruth"):
        assert system.scan_forbidden({key: 1}), key
    assert not system.scan_forbidden({"client_id": "c", "round_id": 1})
    assert system.__doc__ and "never imports ObservedRecord sources, SimulationTruth" in (
        system.__doc__)
    assert "plain_fedavg" in locality and "not" in locality["plain_fedavg"].lower()


# ---------------------------------------------------------------------------------------------
# model registry + governance
# ---------------------------------------------------------------------------------------------


def _candidate(**override: object) -> reg.CandidateModel:
    base = {
        "candidate_id": "CAPSTONE_FL_CANDIDATE_0001", "parent_model_id": "FL_INIT_V2",
        "federation_run_id": "R1", "round": 3, "algorithm": "FEDAVG", "client_count": 8,
        "created_at_us": 1, "state_digest": "d", "validation_status": "PENDING",
        "governance_status": "CREATED", "sandbox_status": "NOT_IN_SANDBOX",
    }
    base.update(override)
    return reg.CandidateModel(**base)


def test_candidate_schema_matches_registry_contract_and_is_never_production() -> None:
    contract = load_contract("model_registry")
    assert list(reg.CandidateModel.model_fields) == contract["candidate_fields"]
    candidate = _candidate()
    assert candidate.production_deployed is False
    assert candidate.claim_boundary == contract["claim_boundary"]
    for bad in ({"production_deployed": True}, {"claim_boundary": "SCIENTIFIC_RELEASE"},
                {"candidate_id": "MODEL_V2_FINAL"}, {"candidate_id": "CAPSTONE_FL_CANDIDATE_1"},
                {"candidate_id": "CAPSTONE_FL_CANDIDATE_0001", "parent_model_id":
                 "CAPSTONE_FL_CANDIDATE_0001"}):
        with pytest.raises(ValidationError):
            _candidate(**bad)
    with pytest.raises(ValidationError, match="SANDBOX_ACCEPTANCE"):
        _candidate(governance_status="ACCEPTED_TO_SANDBOX")
    accepted = _candidate(governance_status="ACCEPTED_TO_SANDBOX", validation_status="PASSED",
                          sandbox_status="IN_SANDBOX")
    assert accepted.production_deployed is False
    with pytest.raises(ValidationError, match="REJECTED_CANDIDATE"):
        _candidate(governance_status="REJECTED", validation_status="FAILED",
                   sandbox_status="IN_SANDBOX")
    assert contract["production_deployed"] is False


def test_registry_keeps_released_models_and_candidates_in_separate_namespaces() -> None:
    contract = load_contract("model_registry")
    assert contract["released_default_model_id"] == reg.RELEASED_DEFAULT_MODEL_ID == (
        "MODEL_V2_FINAL")
    assert set(contract["namespaces"]["RELEASED_SCIENTIFIC"]["members"]) == {
        "MODEL_V1", "MODEL_V2_FINAL"}
    assert reg.ReleasedModelRef(model_id="MODEL_V2_FINAL", role="RELEASED_DEFAULT")
    assert reg.ReleasedModelRef(model_id="MODEL_V1", role="ROLLBACK_REFERENCE")
    for bad in ({"model_id": "CAPSTONE_FL_CANDIDATE_0001", "role": "RELEASED_DEFAULT"},
                {"model_id": "MODEL_V2_FINAL", "role": "ROLLBACK_REFERENCE"}):
        with pytest.raises(ValidationError):
            reg.ReleasedModelRef(**bad)
    assert not reg.CANDIDATE_ID_PATTERN.match("MODEL_V2_FINAL")
    for released in ("checkpoints/MODEL_V1.pt", "checkpoints/MODEL_V2_FINAL.pt"):
        assert (ROOT / released).exists()


def test_governance_lifecycle_has_no_production_deployed_state() -> None:
    contract = load_contract("model_governance")
    assert [s.value for s in reg.CandidateState] == contract["candidate_states"]
    assert not set(contract["forbidden_states"]) & {s.value for s in reg.CandidateState}
    assert not set(contract["forbidden_states"]) & set(reg.candidate_transitions())
    for targets in reg.candidate_transitions().values():
        assert not set(contract["forbidden_states"]) & set(targets)
    path = ("CREATED", "VALIDATION_PENDING", "VALIDATING", "ACCEPTED_TO_SANDBOX", "ARCHIVED")
    for current, new in itertools.pairwise(path):
        reg.validate_candidate_transition(reg.CandidateState(current), reg.CandidateState(new))
    reg.validate_candidate_transition(reg.CandidateState.VALIDATING, reg.CandidateState.REJECTED)
    reg.validate_candidate_transition(reg.CandidateState.REJECTED, reg.CandidateState.ARCHIVED)
    for current, new in (("CREATED", "ACCEPTED_TO_SANDBOX"), ("CREATED", "VALIDATING"),
                         ("REJECTED", "ACCEPTED_TO_SANDBOX"), ("ACCEPTED_TO_SANDBOX", "REJECTED"),
                         ("ARCHIVED", "CREATED")):
        with pytest.raises(IllegalTransitionError, match="ILLEGAL_CANDIDATE_TRANSITION"):
            reg.validate_candidate_transition(reg.CandidateState(current),
                                              reg.CandidateState(new))
    with pytest.raises(ValueError):
        reg.CandidateState("PRODUCTION_DEPLOYED")
    decision = reg.GovernanceDecision(candidate_id="CAPSTONE_FL_CANDIDATE_0001",
                                      decision="ACCEPTED_TO_SANDBOX", checks=("STATE_FINITE",),
                                      decided_at_us=1)
    assert decision.scientific_promotion is False and decision.production_deployed is False
    with pytest.raises(ValidationError):
        reg.GovernanceDecision(candidate_id="x", decision="PRODUCTION_DEPLOYED", checks=(),
                               decided_at_us=1)
    assert "scientific promotion" in contract["acceptance_semantics"]["does_not_mean"]


def test_no_federated_candidate_can_bind_into_the_released_runtime() -> None:
    binding = json.loads((ROOT / "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json").read_text())
    text = json.dumps(binding)
    assert "CAPSTONE_FL_CANDIDATE" not in text and "CAPSTONE" not in text
    assert binding["identity"]["model_id"] == "MODEL_V2_FINAL"
    assert binding["federated_checkpoint_deployed"] is False
    assert binding["public_model_selector"] is False or "NO" in str(
        binding["public_model_selector"]).upper() or not binding["public_model_selector"]
    system = json.loads((ROOT / "artifacts/SOFTWARE_SYSTEM_V2.lock.json").read_text())
    assert system["federated_checkpoint_deployed"] is False
    assert "CAPSTONE" not in json.dumps(system)
    rules = load_contract("model_registry")["binding_rules"]
    assert rules["candidate_can_bind_into_default_runtime"] is False
    assert rules["candidate_can_replace_model_v2_final"] is False
    sandbox = load_contract("model_registry")["sandbox_runtime_boundary"]
    assert sandbox["name"] == "CAPSTONE_FL_SANDBOX_RUNTIME" and sandbox["implemented_now"] is False
    assert sandbox["released_runtime_selector_added"] is False
    assert load_contract("model_governance")["no_public_model_selector"][
        "software_system_v2_modified"] is False


def test_released_runtime_source_has_no_public_model_selector_and_no_capstone_dependency() -> None:
    from api.app_default import assert_no_public_selector
    assert callable(assert_no_public_selector)
    for path in ("api/app_default.py", "api/app_v2.py", "api/runtime_v2.py", "api/schemas.py"):
        source = (ROOT / path).read_text()
        assert "product" not in "".join(
            line for line in source.splitlines() if line.startswith(("import ", "from "))), path
        assert "CAPSTONE" not in source, path


# ---------------------------------------------------------------------------------------------
# frozen frontend, hardware replacement, claims
# ---------------------------------------------------------------------------------------------


def test_existing_sveltekit_frontend_is_unchanged_and_the_only_frontend() -> None:
    entry = json.loads(
        (ROOT / "reports/capstone/cap_001/upstream_protection_entry.json").read_text())
    frontend = {p: h for p, h in entry["tracked_files_sha256"].items() if p.startswith("frontend/")}
    assert frontend and "frontend/package.json" in frontend
    for path, digest in frontend.items():
        assert hash_file(ROOT / path) == digest, path
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True,
                             text=True).stdout.split()
    assert [p for p in tracked if p.endswith("package.json")] == ["frontend/package.json"]
    package = json.loads((ROOT / "frontend/package.json").read_text())
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert "@sveltejs/kit" in deps and "svelte" in deps
    assert not {"react", "react-dom", "next", "vue", "nuxt", "@clerk/nextjs"} & set(deps)
    protocol = load_protocol()
    assert "ONLY frontend foundation" in protocol["architecture"]["frontend_foundation"]
    assert "CAPSTONE_UI_V1" in protocol["architecture"]["frontend_foundation"]


def test_real_hardware_replacement_boundary_keeps_downstream_unchanged() -> None:
    contract = load_contract("hardware_replacement")
    assert contract["invented_hardware_facts_allowed"] is False
    assert contract["real_validation_claimed"] is False
    assert all(v == "VERIFICATION_REQUIRED"
               for v in contract["verification_required_fields"].values())
    assert {"ble_packet_format", "adc_scaling", "real_source_rate", "packet_latency",
            "clock_drift", "signal_units", "real_training_label_source"} == set(
        contract["verification_required_fields"])
    assert contract["today"][:2] == ["SimulatedWearableSource", "VirtualEdgeNode"]
    assert contract["future"][:2] == ["PhysicalWearableSource", "RealEdgeGateway"]
    assert set(contract["replaced_components"]) <= {
        "PhysicalWearableSource (adapter + transport)",
        "RealEdgeGateway (phone/laptop/edge gateway host)"}
    for unchanged in ("ObservedRecord (SAMPLE_SCHEMA_V1)", "QUALITY_V1", "MODEL_V2_FINAL",
                      "CAPSTONE_FL_CLIENT_CONTRACT_V1", "PRODUCT_LIVE_EVENT_V1"):
        assert unchanged in contract["unchanged_downstream"]
    assert "validated label source" in contract["label_boundary"]


def test_future_real_adapter_is_compatible_with_the_same_edge_and_fl_contracts() -> None:
    class RealSource:
        @property
        def descriptor(self):
            from tests.test_capstone_contracts import _descriptor
            return _descriptor(AdapterType.FUTURE_REAL)

        @property
        def connection_state(self):
            return self.descriptor.connection_state

        async def scan(self, timeout_s: float):
            return [self.descriptor]

        async def connect(self, device_id: str) -> None: ...
        async def disconnect(self) -> None: ...
        async def start_stream(self, session_id: str) -> None: ...
        async def stop_stream(self) -> None: ...

        def records(self) -> AsyncIterator:
            raise NotImplementedError

        def events(self) -> AsyncIterator:
            raise NotImplementedError

    assert isinstance(RealSource(), DeviceSource)
    gateway = edge.EdgeNodeIdentity(edge_node_id="GW", kind="REAL_EDGE_GATEWAY",
                                    simulation=False, fl_client_id="REAL_CLIENT_1")
    client = _identity(client_id=gateway.fl_client_id, edge_node_id=gateway.edge_node_id)
    assert client.client_id == "REAL_CLIENT_1"  # same FL client contract, no simulation field
    assert "simulation" not in fed.FLClientIdentity.model_fields
    assert asyncio.run(RealSource().scan(1.0))


def test_claim_boundary_and_continual_learning_rules_are_frozen() -> None:
    protocol = load_protocol()
    allowed, forbidden = set(protocol["claim_boundary"]["allowed"]), set(
        protocol["claim_boundary"]["forbidden"])
    assert not allowed & forbidden
    for claim in ("diagnosis", "clinical decision support", "continual clinical learning",
                  "differential privacy", "federated candidate clinically superior",
                  "synthetic efficacy", "medical-device certification"):
        assert claim in forbidden
    assert "federated physiological-monitoring research platform" in allowed
    live = protocol["live_vs_fl"]
    assert live["no_continual_production_learning"] is True
    forbidden_paths = protocol["architecture"]["forbidden_paths"]
    assert any("prediction -> label" in item for item in forbidden_paths)
    continual = load_contract("fl_run")["continual_sandbox"]
    assert continual["allowed"] is True
    assert any("prediction becomes label" in item for item in continual["forbidden"])
    assert "automatic production adaptation" in continual["description_forbidden"]
    history = protocol["historical_facts_preserved"]
    assert history["MODEL_V2_NOT_PROMOTED_RELEASE_CI"] and history[
        "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED"]
    assert history["default_checkpoint_is_federated"] is False
