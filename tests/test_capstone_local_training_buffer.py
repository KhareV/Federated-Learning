# ruff: noqa: E501
"""CAP-006: LOCAL_TRAINING_BUFFER_V1, SIMULATION_LABEL_ADAPTER_V1, label semantics and the truth firewall."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from federated.wearable_sim_local_labels import SyntheticEventLabelProvider
from product.edge import buffer as contract
from product.edge.label_adapter import ADAPTER_ID, LABEL_CONTRACT, SimulationLabelAdapterV1
from product.edge.local_training_buffer import (
    BufferError,
    LocalTrainingBufferV1,
    window_id_for,
)
from product.federation.local_cohort import reference_evidence
from simulation.fl_cohort_v1 import cohort_profiles
from tests.capstone_local_support import cohort_buffers, tiny_buffer, tiny_dataset

ROOT = Path(__file__).resolve().parents[1]
NEW_MODULES = ("product/edge/label_adapter.py", "product/edge/local_training_buffer.py",
               "product/federation/client.py", "product/federation/update_bridge.py",
               "product/federation/local_cohort.py")


def _imports(path: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse((ROOT / path).read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names |= {f"{node.module}.{a.name}" for a in node.names}
    return names


def _ident_text(path: str) -> str:
    return " ".join(
        n.id if isinstance(n, ast.Name) else n.attr for n in ast.walk(ast.parse((ROOT / path).read_text()))
        if isinstance(n, ast.Name | ast.Attribute))


def test_all_eight_frozen_clients_are_reused_with_exact_v2_fl_005_counts_and_dataset_shas() -> None:
    ref = {c["client_id"]: c for c in reference_evidence()["cohort"]["clients"]}
    buffers = cohort_buffers()
    assert [b.client_id for b in buffers] == [f"SIM_FL_SITE_0{i}" for i in range(8)]
    assert [b.participant_id for b in buffers] == [f"SIM_P00010{i}" for i in range(1, 9)]
    assert len(ref) == 8
    for b in buffers:
        frozen = ref[b.client_id]
        assert b.participant_id == frozen["participant_id"]
        assert b.dataset_sha256 == frozen["dataset_sha256"]
        for key in ("source_records", "windows_emitted", "VALID", "DEGRADED", "UNUSABLE", "trainable", "synthetic_positive", "synthetic_negative"):
            assert b.counts[key] == frozen["counts"][key], (b.client_id, key)


def test_only_trainable_windows_become_records_and_all_are_quality_eligible() -> None:
    for b in cohort_buffers():
        manifest = b.manifest()
        assert manifest["record_count"] == b.counts["trainable"] == manifest["eligible_count"]
        assert manifest["all_quality_eligible"] is True
        assert manifest["synthetic_positive"] == b.counts["synthetic_positive"]
        assert manifest["synthetic_negative"] == b.counts["synthetic_negative"]
        assert b.counts["excluded_not_valid"] + b.counts["excluded_valid_but_incomplete"] == b.counts["windows_emitted"] - b.counts["trainable"]


def test_model_input_refs_are_opaque_references_not_sample_arrays() -> None:
    for record in cohort_buffers()[0].records():
        dumped = record.model_dump(mode="json")
        assert all(not isinstance(v, list | dict) for v in dumped.values())
        assert record.model_input_ref.startswith("LOCALREF:") and len(record.model_input_ref) < 80
    assert cohort_buffers()[0].manifest()["refs_are_opaque"] is True


def test_window_ids_batch_ids_and_provenance_are_deterministic_and_bound() -> None:
    b = cohort_buffers()[3]
    records = b.records()
    assert records[0].window_id == window_id_for("SIM_FL_SITE_03", records[0].timestamp_us)
    assert len({r.window_id for r in records}) == len(records)
    assert b.batch_ids() == (f"WEARABLE_SIM_FL_BATCH_0001__SIM_FL_SITE_03__{b.dataset_sha256[:12]}",)
    r = records[0]
    assert r.source == "WEARABLE_SIM_FL_COHORT_V1" and r.simulation is True
    assert "WEARABLE_SIM_V1" in r.provenance_id and "SIM_P000104" in r.provenance_id and b.dataset_sha256[:16] in r.provenance_id
    assert {x.label_source.value for x in records} == {"SIMULATION_TRUTH_ENGINEERING"}


def test_the_buffer_semantic_digest_is_deterministic_and_metadata_only() -> None:
    a = cohort_buffers()[1].semantic_digest()
    from product.federation.local_cohort import build_client
    from tests.capstone_local_support import base_state

    b = build_client(1, base_state())[1]
    assert a == b.semantic_digest()  # regenerated from scratch: identical
    assert "inputs" not in json.dumps([r.model_dump(mode="json") for r in b.records()])


def test_model_input_lookup_is_client_local_and_cross_client_access_fails() -> None:
    b0, b1 = cohort_buffers()[0], cohort_buffers()[1]
    ref = b0.records()[0].model_input_ref
    window = b0.resolve_input(ref, requester_client_id="SIM_FL_SITE_00")
    assert window.dtype == np.float32 and window.shape == (1, 2500)
    with pytest.raises(BufferError, match="CROSS_CLIENT_INPUT_ACCESS"):
        b0.resolve_input(ref, requester_client_id="SIM_FL_SITE_01")
    with pytest.raises(BufferError, match="CROSS_CLIENT_INPUT_ACCESS"):
        b0.training_arrays(requester_client_id="SIM_FL_SITE_01")
    with pytest.raises(BufferError, match="UNKNOWN_MODEL_INPUT_REF"):
        b1.resolve_input(ref, requester_client_id="SIM_FL_SITE_01")  # client 0's ref is unknown to client 1


def test_duplicate_batch_cross_client_record_and_missing_private_tensor_fail_closed() -> None:
    b = tiny_buffer()
    records = list(b.records())
    with pytest.raises(BufferError, match="DUPLICATE_BATCH_ID"):
        b.append_batch(records)
    other = LocalTrainingBufferV1("SIM_FL_SITE_01", "SIM_P000102")
    other.stage_private_inputs({r.model_input_ref: np.zeros((1, 2500), np.float32) for r in records})
    with pytest.raises(BufferError, match="CROSS_CLIENT_RECORD"):
        other.append_batch(records)
    fresh = LocalTrainingBufferV1("SIM_FL_SITE_00", "SIM_P000101")
    renamed = [r.model_copy(update={"buffer_batch_id": "OTHER_BATCH"}) for r in records]
    with pytest.raises(BufferError, match="MODEL_INPUT_REF_WITHOUT_PRIVATE_TENSOR"):
        fresh.append_batch(renamed)
    with pytest.raises(BufferError, match="CROSS_CLIENT_DATASET"):
        other.ingest_dataset(tiny_dataset())


def test_label_source_rules_forbidden_prediction_labels_and_real_data_rules_fail() -> None:
    b = tiny_buffer()
    record = b.records()[0]
    with pytest.raises(ValueError):  # frozen record model: MODEL_PREDICTION is not a LabelSource at all
        contract.TrainingBufferRecord(**{**record.model_dump(), "label_source": "MODEL_PREDICTION"})
    with pytest.raises(ValueError, match="SIMULATION_TRUTH_ENGINEERING_FORBIDDEN_FOR_REAL_DATA"):
        contract.TrainingBufferRecord(**{**record.model_dump(), "simulation": False})
    for bad_source in ("MODEL_PREDICTION", "SELF_LABEL", "PSEUDO_LABEL", "LIVE_INFERENCE_OUTPUT"):
        forged = record.model_construct(**{**record.__dict__, "label_source": bad_source, "buffer_batch_id": "B2"})
        target = LocalTrainingBufferV1("SIM_FL_SITE_00", "SIM_P000101")
        target.stage_private_inputs({record.model_input_ref: np.zeros((1, 2500), np.float32)})
        with pytest.raises(BufferError, match="FORBIDDEN_LABEL_SOURCE"):
            target.append_batch([forged])
    real = record.model_construct(**{**record.__dict__, "simulation": False, "buffer_batch_id": "B3"})
    target = LocalTrainingBufferV1("SIM_FL_SITE_00", "SIM_P000101")
    target.stage_private_inputs({record.model_input_ref: np.zeros((1, 2500), np.float32)})
    with pytest.raises(BufferError, match="SIMULATION_LABEL_ON_REAL_DATA"):
        target.append_batch([real])
    ineligible = record.model_construct(**{**record.__dict__, "quality_eligible": False, "buffer_batch_id": "B4"})
    target.stage_private_inputs({record.model_input_ref: np.zeros((1, 2500), np.float32)})
    with pytest.raises(BufferError, match="NON_ELIGIBLE_RECORD_NOT_STORED"):
        target.append_batch([ineligible])


def test_nonfinite_or_misshapen_private_inputs_are_rejected() -> None:
    b = LocalTrainingBufferV1("SIM_FL_SITE_00", "SIM_P000101")
    with pytest.raises(BufferError, match="MODEL_INPUT_NONFINITE"):
        b.stage_private_inputs({"r": np.full((1, 2500), np.nan, np.float32)})
    with pytest.raises(BufferError, match="MODEL_INPUT_SHAPE_INVALID"):
        b.stage_private_inputs({"r": np.zeros((1, 2000), np.float32)})


def test_a_tampered_dataset_sha_is_rejected_at_ingestion() -> None:
    dataset = tiny_dataset()
    forged = dataset.__class__(**{**dataset.__dict__, "dataset_sha256": "0" * 64})
    with pytest.raises(BufferError, match="DATASET_SHA_MISMATCH"):
        LocalTrainingBufferV1("SIM_FL_SITE_00", "SIM_P000101").ingest_dataset(forged)


def test_the_label_adapter_wraps_the_existing_adapter_and_keeps_engineering_semantics() -> None:
    profile = cohort_profiles()[0]
    wrapper, inner = SimulationLabelAdapterV1(profile), SyntheticEventLabelProvider(profile)
    edges = [15_000_000, 45_000_000, 75_000_000, 135_000_000]
    assert np.array_equal(wrapper.labels_for_windows(edges), inner.labels_for_windows(edges))
    assert ADAPTER_ID == "SIMULATION_LABEL_ADAPTER_V1" and LABEL_CONTRACT == "WEARABLE_SIM_EVENT_WINDOW_V1"
    assert isinstance(wrapper, contract.SimulationLabelAdapter)
    text = (ROOT / "product/edge/label_adapter.py").read_text()
    assert "NOT\nAAMI_SVF_WINDOW_V1" in text or "NOT AAMI_SVF_WINDOW_V1" in text
    assert "federated.wearable_sim_local_labels" in _imports("product/edge/label_adapter.py")


def test_product_wrappers_do_not_import_truth_modules_or_names_anywhere_under_product() -> None:
    boundary = json.loads((ROOT / "contracts/capstone/local_training_buffer_v1.json").read_text())["simulation_truth_boundary"]
    truth_mods, names = set(boundary["truth_modules"]), set(boundary["truth_names"])
    for path in (ROOT / "product").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        imports = _imports(rel)
        assert not imports & truth_mods, rel
        assert not any(i.split(".")[-1] in names for i in imports), rel
        assert not any(i.startswith(tuple(m + "." for m in truth_mods)) for i in imports), rel
        if rel not in NEW_MODULES:  # pre-existing modules may mention the names only as strings in comments
            continue
        assert "SimulationTruth" not in _ident_text(rel) and "get_truth" not in _ident_text(rel), rel


def test_no_new_module_writes_to_central_storage_or_depends_on_the_product_database() -> None:
    for rel in NEW_MODULES:
        imports = " ".join(_imports(rel))
        for forbidden in ("sqlite3", "capstone_persistence", "product.persistence", "product.sessions", "fastapi", "starlette"):
            assert forbidden not in imports, (rel, forbidden)


def test_no_prediction_derived_label_path_exists_in_the_new_modules() -> None:
    for rel in NEW_MODULES:
        ids = _ident_text(rel).lower()
        for banned in ("model_v2_final", "monitoring_state", "raw_probability", "calibrated_probability", "infer_window", "inferenceclient", "alert_policy", "threshold"):
            assert banned not in ids, (rel, banned)
