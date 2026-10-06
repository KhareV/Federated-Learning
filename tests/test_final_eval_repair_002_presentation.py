# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-002 anti-regression tests: the CLASS 'unsourced / fabricated / misleading quantitative or live-state presentation', accessibility of the public landing page, and the frozen machinery wiring."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import final_eval_repair_002_entry_evidence as ee
from scripts import final_eval_repair_002_provenance as prov
from scripts import final_eval_repair_presentation as pres

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "configs/final_eval_repair/fer_002_protocol_v1.json").read_text())


@pytest.mark.parametrize("text", ["99.8% Coverage", "Illustrates the 99.8% unmonitored blind intervals between sporadic clinic visits", "LIVE EDGE SYNAPSE GRAPH", "Hover any node to inspect real-time feature vectors", "Model confidence 91%", "Anomaly score 0.08", "Current SpO₂: 98%",
                                  "Normal ECG", "Live patient data", "Real wearable stream", "On-device inference", "Edge model running on wearable", "Model accuracy 97%", "Coverage 99%", "Clinical monitoring", "Normal 72 BPM", "4.5 Hours Unmonitored", "See reports/fedprox.json"])
def test_guard_flags_each_claim_class(text: str) -> None:
    assert prov.scan_text(f"<p>{text}</p>"), text


@pytest.mark.parametrize("text", ["Resting scenario (72 BPM, synthetic)", "ILLUSTRATIVE VALUE (NOT LIVE)", "Conceptual illustration only: No measured percentage is claimed.", "On-Device Inference: Not Implemented", "SYNTHETIC WAVEFORM // NOT LIVE HARDWARE", "Scenario parameter - not a measurement"])
def test_guard_accepts_qualified_text(text: str) -> None:
    assert prov.scan_text(f"<p>{text}</p>") == [], text


def test_percentage_is_never_excused_by_an_illustrative_word() -> None:
    assert prov.scan_text("<p>Illustrative: 99.8% of the time</p>")


def test_current_tree_claim_scan_and_provenance_pass() -> None:
    r = prov.verify_all()
    assert r["ok"], r


def test_every_landing_component_is_in_the_import_graph_inventory() -> None:
    files = set(prov.landing_files())
    for name in ("NeuralGraph", "WatchScene", "PhysiologicalWaveform", "SystemArchitecture", "ProductWorkstation", "HardwareStudio", "MultimodalStudio"):
        assert any(f.endswith(f"{name}.svelte") for f in files), name


def test_final_inventory_has_no_unsourced_or_misleading_classification() -> None:
    inv = ee.inventory(ROOT)
    claims = prov.contract()["claims"]
    bad = [r for r in inv["rows"] if r["classification"] in {"UNSUPPORTED_QUANTITATIVE_ASSERTION", "MISLEADING_LIVE_STATE_ASSERTION", "STALE_PRODUCT_ASSERTION"} and not any(c["surface"] == r["file"] and re.search(c["text_pattern"], r["text"], re.I) for c in claims)]
    assert bad == []


def test_provenance_contract_has_no_invented_sources() -> None:
    for e in prov.contract()["claims"]:
        assert e["provenance_type"] in prov.PROVENANCE_TYPES
        if e["provenance_type"] == "ILLUSTRATIVE":
            assert e["required_qualification"]
        if e["provenance_type"] == "FROZEN_PROJECT_EVIDENCE":
            assert (ROOT / e["source"]).exists()
    assert prov.provenance_ok()["ok"]


def test_landing_accessibility_static_checks() -> None:
    r = prov.a11y_static_ok()
    assert r["ok"], r


def test_neuralgraph_has_no_live_wording_or_statistic() -> None:
    t = (ROOT / "frontend/src/lib/components/landing/NeuralGraph.svelte").read_text()
    assert not re.search(r"99\.8|LIVE EDGE|real-time", t) and "ILLUSTRATIVE SIGNAL-FLOW GRAPH" in t


def test_candidate_identity_is_not_confused_with_state_digest() -> None:
    card = (ROOT / "frontend/src/lib/components/product/federation/CandidateCard.svelte").read_text()
    assert "candidate.candidate_id" in card and "State digest" in card and not re.search(r"duplicate|same candidate|deployed twice", card, re.I)


def test_fer1_presentation_guard_still_passes() -> None:
    assert pres.verify_all()["ok"]


def test_capstone_ui_v1_6_verifies() -> None:
    from scripts.verify_capstone_ui_v1_6 import verify

    assert verify()["status"] == "PASS"


def test_protocol_shape_is_frozen() -> None:
    assert PROTOCOL["criteria_count"] == len(PROTOCOL["ferg1_criteria"]) == 51 and PROTOCOL["mutation_control_count"] == 38 == len(PROTOCOL["mutation_controls"]) == len(set(PROTOCOL["mutation_controls"]))


def test_every_criterion_check_is_wired_in_the_evaluator() -> None:
    from scripts import final_eval_repair_002_evaluate_gate as ev

    checks = ev.build_checks()
    for row in PROTOCOL["ferg1_criteria"]:
        for c in row["checks"]:
            assert c in checks, c


def test_mutation_names_match_the_control_table() -> None:
    from scripts import final_eval_repair_002_mutation_controls as mc

    assert list(mc.CONTROLS) == PROTOCOL["mutation_controls"]
