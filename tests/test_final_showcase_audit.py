# ruff: noqa: E501
"""Pre-push audit controls: evaluation reconciliation, lane separation in figures/tables/manuscript, and lock-chain tamper controls."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from final_showcase import LANE_LABEL, audit
from scripts import verify_final_showcase as vf
from scripts import verify_obs_diag_001 as vd


def test_evaluation_reconciles_and_round3_all_positive_is_preserved():
    e = audit.evaluation_integrity()
    assert e["method_commit_is_ancestor_of_first_prediction_commit"] and e["predictions_absent_at_method_commit"] and e["manifest_sha256_matches_protocol"]
    assert e["state_digests_equal_frozen_progression"] and all(v == 0 for k, v in e["separation"].items() if k.endswith("overlap"))
    for state in e["states"].values():
        assert all(v for v in state.values() if isinstance(v, bool)), state
    assert e["round_3_all_positive_preserved"] and e["rounds_0_to_2_predict_no_positive"] and e["no_threshold_tuning_or_calibration"]


def test_figures_tables_and_manuscript_keep_the_three_evidence_lanes_apart():
    r = audit.lane_separation()
    assert all(not f["mixes_synthetic_with_scientific_sources"] for f in r["figures"].values()) and all(not t["mixes"] for t in r["tables"].values())
    assert r["figures"]["FIG6_SYNTHETIC"]["svg_carries_synthetic_label"] and all(not f["svg_carries_synthetic_label"] for k, f in r["figures"].items() if k != "FIG6_SYNTHETIC")
    assert r["figures"]["FIG5_PERFORMANCE"]["historical_reference_marked"] and all(t["label_in_caption"] for t in r["tables"].values() if t["uses_synthetic_source"])
    m = r["manuscript"]
    assert m["every_such_paragraph_has_exact_label"] and m["abstract_synthetic_sentence_labelled"] and m["centralized_comparison_declares_point_only"] and m["superiority_only_negated"] and m["boundary_statement_present"]


def test_every_synthetic_number_in_viva_and_traceability_carries_the_boundary():
    viva = (Path("docs/final_showcase/viva_question_bank.md")).read_text()
    assert LANE_LABEL in viva.split("**Q3.")[1].split("**Q4.")[0]
    trace = Path("docs/final_showcase/results_traceability.md").read_text()
    rows = [row for row in trace.splitlines() if "synth_fl_eval_results.json" in row and not row.startswith("| T15")]
    assert len(rows) == 4 and all(LANE_LABEL in row for row in rows)


def test_bibliography_is_explicitly_unverified():
    text = Path("docs/final_showcase/manuscript_material.md").read_text()
    assert text.count("REFERENCE_REQUIRED") >= 3 and not re.search(r"\[\d+\]|\bet al\.", text)
    assert "not reference-complete" in Path("docs/final_showcase/implementation_map.md").read_text().lower()


# ---------------------------------------------------------------- lock governance
def test_final_lock_chain_verifies_and_predecessor_is_the_pushed_commit_bytes():
    out = vf.verify_lock()
    assert out["obs_diag_chain_verified"] and out["v1_chain_verified"]
    lock = json.loads(vf.LOCK.read_text())
    assert lock["predecessor_lock_edited"] is False and lock["predecessor_commit"].startswith("aa36f53")
    assert vf.sha(vf.DIAG_LOCK) == lock["predecessor_sha256"]


ORIGINAL_LOCK = vf.LOCK


def _tampered(tmp_path: Path, monkeypatch, mutate) -> Path:
    lock = json.loads(ORIGINAL_LOCK.read_text())
    mutate(lock)
    path = tmp_path / "final.lock.json"
    path.write_text(json.dumps(lock))
    monkeypatch.setattr(vf, "LOCK", path)
    return path


def test_tamper_controls_on_the_final_lock(tmp_path, monkeypatch):
    first = lambda lock: sorted(lock["bound_files"])[0]  # noqa: E731
    _tampered(tmp_path, monkeypatch, lambda lock: lock["bound_files"].__setitem__(first(lock), "0" * 64))
    with pytest.raises(RuntimeError, match="FINAL_SHOWCASE_TAMPER"):
        vf.verify_lock()
    _tampered(tmp_path, monkeypatch, lambda lock: lock.__setitem__("predecessor_sha256", "0" * 64))
    with pytest.raises(RuntimeError, match="PREDECESSOR_LOCK_MUTATED"):
        vf.verify_lock()
    _tampered(tmp_path, monkeypatch, lambda lock: lock.__setitem__("repins_predecessor_files", lock["repins_predecessor_files"][1:]))
    with pytest.raises(RuntimeError, match="REPIN_SET_MISMATCH"):
        vf.verify_lock()
    _tampered(tmp_path, monkeypatch, lambda lock: lock["bound_artifacts"].__setitem__(sorted(lock["bound_artifacts"])[0], "0" * 64))
    # A substituted historical lock cannot inherit FL10 re-pins, so it fails
    # earlier on the first changed bound API file; either way it fails closed.
    with pytest.raises(RuntimeError, match=r"FINAL_SHOWCASE_TAMPER|FRONTEND_BINDING_DRIFT"):
        vf.verify_lock()
    _tampered(tmp_path, monkeypatch, lambda lock: lock.__setitem__("candidate_promoted_or_deployed", True))
    with pytest.raises(RuntimeError, match=r"FINAL_SHOWCASE_TAMPER|SCOPE_DRIFT"):
        vf.verify_lock()


def test_mutated_predecessor_lock_is_detected(tmp_path, monkeypatch):
    mutated = tmp_path / "diag.lock.json"
    shutil.copyfile(vf.DIAG_LOCK, mutated)
    mutated.write_text(mutated.read_text() + "\n ")
    monkeypatch.setattr(vf, "DIAG_LOCK", mutated)
    with pytest.raises(RuntimeError, match="PREDECESSOR_LOCK_MUTATED"):
        vf.verify_lock()


def test_obs_diag_verifier_rejects_a_successor_that_does_not_chain_to_its_exact_bytes(tmp_path, monkeypatch):
    other = json.loads(vf.LOCK.read_text())
    other["predecessor_sha256"] = "1" * 64
    path = tmp_path / "final.lock.json"
    path.write_text(json.dumps(other))
    monkeypatch.setattr(vd, "FINAL_PATH", path)
    with pytest.raises(RuntimeError, match="SUCCESSOR_CHAIN_BROKEN"):
        vd.verify()


def test_obs_diag_lock_bytes_equal_the_pushed_origin_tip():
    pushed = vf.git_show("aa36f53", "artifacts/observatory/NHM_OBS_DIAG_001.lock.json")
    assert pushed == vf.DIAG_LOCK.read_bytes()


# ---------------------------------------------------------------- successor-compatibility amendments added since the pushed tip
def _new_amendments() -> list[Path]:
    import subprocess

    out = subprocess.run(["git", "ls-files", "--others", "--cached", "--exclude-standard", "artifacts"], capture_output=True, text=True, check=True).stdout.split()
    pushed = set(subprocess.run(["git", "ls-tree", "-r", "--name-only", "aa36f53", "artifacts"], capture_output=True, text=True, check=True).stdout.split())
    return sorted(Path(p) for p in out if ".amendment_" in p and p not in pushed)


def test_new_amendments_are_pure_successor_compatibility_with_continuous_digests():
    from scripts.final_eval_repair_lib import sha
    from scripts.observatory_amend import authorised

    new = _new_amendments()
    studio = [path for path in new if json.loads(path.read_text()).get("amendment_id", "").startswith("NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001")]
    assert len(new) - len(studio) == 8, new  # six accepted predecessors + two pure FL10 successor-compatibility amendments; the Studio's own pure compatibility amendments are checked by the same loop below
    for path in new:
        doc = json.loads(path.read_text())
        assert doc["scope"] == "SUCCESSOR_COMPATIBILITY_ONLY" and doc["result_evidence_committed_with_amendment"] is False and doc["made_after_method_freeze"] is True
        for rel, digests in doc["files"].items():
            assert authorised(rel), rel                                   # frontend / successor-aware verifiers / accounting tests / route policy only
            assert not rel.startswith(("reports/", "checkpoints/", "models/", "federated/", "simulation/", "product/federation/", "product/monitoring/", "product/models/"))
            assert digests["old_sha256"] != digests["new_sha256"]
    # the LAST amendment per (lock, file) must name the digest of the file as it is now (chain ends at the present bytes)
    last: dict[tuple[str, str], str] = {}
    for amend in sorted(Path("artifacts").glob("**/*.amendment_*.json")):
        stem = amend.name.split(".amendment_")[0]
        for rel, digests in json.loads(amend.read_text()).get("files", {}).items():
            if isinstance(digests, dict) and "new_sha256" in digests:
                last[(stem, rel)] = digests["new_sha256"]
    for path in new:
        stem = path.name.split(".amendment_")[0]
        for rel in json.loads(path.read_text())["files"]:
            assert last[(stem, rel)] == sha(Path(rel)), (stem, rel)
