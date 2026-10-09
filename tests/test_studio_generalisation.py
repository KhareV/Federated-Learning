# ruff: noqa: E501
"""Generalisation lane: verified V2 start, unseen G1 cohort, frozen-V2 baseline and per-round paired comparison.

Fast tests cover the checkpoint audit, the pinned cohort manifest and the strict record. One REAL pretrained-start 10-round run (module fixture) is executed through the
API and every claim is checked against stored evidence: R0 equals the frozen V2 checkpoint (digest AND predictions), later rounds differ, every number recomputes from
the stored predictions, pairs use the protocol's replicates, another user is refused, and the default untrained start is unchanged."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from studio import g1_cohort, v2_init
from studio.records import GeneralisationRecord
from tests.capstone_federation_support import DESCRIPTION
from tests.capstone_product_support import BASE, USER_A, USER_B

S = f"{BASE}/studio"


def test_v2_final_checkpoint_loads_strictly_and_matches_the_fl_layout():
    state, audit = v2_init.load_v2_final()
    assert audit["checkpoint_sha256"] == audit["manifest_checkpoint_sha256"] and audit["state_entries"] == 92 == len(state)
    assert audit["keys_and_order_equal"] and audit["shapes_dtypes_equal"] and audit["all_finite"] and audit["strict_load_round_trip_equal"]
    assert audit["trainable_and_buffer_float_elements"] == audit["manifest_parameter_count"] == 57553
    fresh, info = v2_init.initial_state(v2_init.INIT_FRESH)
    assert list(fresh) == list(state) and info["state_sha256"] != audit["state_sha256"]          # same layout, different weights: the fresh start is NOT replaced
    probe = np.random.default_rng(3).standard_normal((12, 1, 2500)).astype("float32")
    assert v2_init.logits_parity(state, probe)["equal"]


def test_a_tampered_checkpoint_digest_fails_closed(tmp_path):
    for relative in (v2_init.CHECKPOINT, v2_init.MANIFEST):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_bytes((v2_init.ROOT / relative).read_bytes())
    data = bytearray((tmp_path / v2_init.CHECKPOINT).read_bytes())
    data[len(data) // 2] ^= 0xFF
    (tmp_path / v2_init.CHECKPOINT).write_bytes(bytes(data))
    with pytest.raises(v2_init.V2InitError) as error:
        v2_init.load_v2_final(tmp_path)
    assert error.value.code == "CHECKPOINT_DIGEST_MISMATCH"


def test_pretrained_start_is_refused_with_frozen_prefix_parity():
    from fl10 import runner

    state, _ = v2_init.load_v2_final()
    with pytest.raises(runner.Fl10Error) as error:
        runner.run_training(mode="A", run_id="X", out_dir=g1_cohort.ROOT / "does-not-matter", datasets=[], manifest={}, initial_state=state, require_prefix_parity=True)
    assert "COHORT_MANIFEST_MISMATCH" in str(error.value) or "PREFIX_PARITY" in str(error.value)


def test_g1_manifest_is_pinned_and_describes_a_disjoint_cohort():
    manifest = json.loads((g1_cohort.ROOT / g1_cohort.MANIFEST).read_text())
    ids = [e["participant_id"] for e in manifest["participants"]]
    assert len(ids) == 16 and ids[0] == "SIM_P000401" and ids[-1] == "SIM_P000416" and manifest["cohort_id"] == g1_cohort.COHORT_ID
    from fl10 import holdout

    assert not set(ids) & {p.participant_id for p in holdout.profiles()}
    assert manifest["label"].startswith("UNSEEN SYNTHETIC COHORT")


def test_generalisation_record_is_strict():
    base = dict(run_id="R", run_length=0, round_id=0, global_state_digest="a" * 64, cohort_id="C", evaluation_status="QUEUED", evaluation_queued_at="2026-01-01T00:00:00+00:00")
    rec = GeneralisationRecord(**base, subject="FROZEN_V2_BASELINE")
    assert rec.schema_version == "STUDIO_GENERALISATION_EVALUATION_V1" and rec.cohort_use.startswith("UNSEEN SYNTHETIC COHORT") and rec.claim_boundary.endswith("NOT_AAMI_SVF_OR_CLINICAL")
    with pytest.raises(ValueError):
        GeneralisationRecord(**{**base, "evaluation_status": "COMPLETED"})                 # COMPLETED without metrics is impossible
    with pytest.raises(ValueError):
        GeneralisationRecord(**base, subject="SOMETHING_ELSE")


def _app(tmp_path):
    from api.product_app_observatory_v1 import create_product_app_observatory_v1
    from capstone_persistence.store import CapstoneSqliteStore
    from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver

    return create_product_app_observatory_v1(store=CapstoneSqliteStore(tmp_path / "p.sqlite3"), identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
                                             federation_artifact_root=tmp_path / "f", candidate_root=tmp_path / "c", inference_base_url="http://127.0.0.1:8001", auto_resume=False)


def _poll(c, url, headers, until, timeout=2400):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = c.get(url, headers=headers).json()
        if until(last):
            return last
        time.sleep(2.0)
    raise AssertionError(f"timeout: {str(last)[:400]}")


@pytest.fixture(scope="module")
def pretrained_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("gen")
    with TestClient(_app(tmp)) as c:
        caps = c.get(f"{S}/capabilities", headers=USER_A).json()
        assert [i["id"] for i in caps["ten_round"]["initialisations"]] == ["FL_INIT_V2", "MODEL_V2_FINAL"] and caps["generalisation"]["cohort_id"] == g1_cohort.COHORT_ID
        bad = c.post(f"{S}/runs", headers=USER_A, json={"run_length": 10, "initialisation": "SOMETHING_ELSE"})
        assert bad.status_code in (400, 409, 422)
        started = c.post(f"{S}/runs", headers=USER_A, json={"run_length": 10, "initialisation": "MODEL_V2_FINAL"})
        assert started.status_code == 200, started.text
        run = started.json()
        assert run["base_model"]["model_id"] == "MODEL_V2_FINAL"
        run_id = run["run_id"]
        done = _poll(c, f"{S}/runs/{run_id}", USER_A, lambda d: d["status"] in ("COMPLETED", "FAILED") and d["phase"] == "DONE")
        assert done["status"] == "COMPLETED", done
        gen = _poll(c, f"{S}/runs/{run_id}/generalisation", USER_A, lambda g: g["baseline"]["record"] and g["baseline"]["record"]["evaluation_status"] == "COMPLETED"
                    and all(r["record"] and r["record"]["evaluation_status"] in ("COMPLETED", "FAILED") for r in g["rounds"]) and all(r["paired_vs_v2"] for r in g["rounds"]))
        yield SimpleNamespace(c=c, run_id=run_id, done=done, gen=gen, tmp=tmp)


def test_pretrained_run_starts_from_the_verified_v2_weights(pretrained_run):
    run_id = pretrained_run.run_id
    done = pretrained_run.done
    tmp = pretrained_run.tmp
    audit = done["base_model"]
    assert audit["checkpoint_sha256"] == "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b" and audit["state_entries"] == 92
    report = json.loads(next((tmp / "f").parent.rglob(f"{run_id}/run/run_report.json")).read_text())
    assert report["initialisation"]["model_id"] == "MODEL_V2_FINAL" and report["initialisation"]["state_sha256"] == audit["state_sha256"]
    assert report["state_progression"]["0"]["sha256"] == audit["state_sha256"] and report["frozen_reference"] is None
    assert report["status"] == "COMPLETED" and report["rounds_committed"] == 10 and all(r["accepted_updates"] == 8 for r in report["rounds"])
    assert all(r["parity"] is None for r in report["rounds"]) and report["prefix_equals_frozen_reference"] == {}          # no frozen-FL_INIT claim for a different start
    assert len({report["state_progression"][str(i)]["sha256"] for i in range(11)}) == 11


def test_r0_equals_frozen_v2_and_later_rounds_move_away(pretrained_run):
    gen = pretrained_run.gen
    assert gen["integrity"] == {"r0_digest_equals_frozen_v2": True, "r0_predictions_equal_frozen_v2": True}
    base = gen["baseline"]["record"]
    assert base["subject"] == "FROZEN_V2_BASELINE" and base["evaluation_status"] == "COMPLETED" and base["threshold"] == 0.5 and base["calibration"] == "NONE"
    r0, r10 = gen["rounds"][0], gen["rounds"][10]
    assert r0["record"]["global_state_digest"] == base["global_state_digest"] and r0["paired_vs_v2"]["identical_predictions"] is True
    assert r10["record"]["global_state_digest"] != base["global_state_digest"] and r10["paired_vs_v2"]["identical_predictions"] is False
    assert all(r0["paired_vs_v2"]["metrics"][m]["difference_point"] == 0 for m in ("AUPRC", "AUROC", "BCE", "Brier"))
    assert gen["claim_boundary"].endswith("NOT_AAMI_SVF_OR_CLINICAL") and gen["cohort"]["label"].startswith("UNSEEN SYNTHETIC COHORT") and gen["base_model"]["model_id"] == "MODEL_V2_FINAL"


def test_every_stored_number_recomputes_from_the_stored_predictions(pretrained_run):
    from fl10 import metrics
    from studio.observer import read_predictions

    run_id = pretrained_run.run_id
    gen = pretrained_run.gen
    tmp = pretrained_run.tmp
    root = next(tmp.rglob(f"{run_id}/eval_g1"))
    base_root = next(tmp.rglob("V2FROZEN-BASELINE/eval_g1"))
    _o, yb, zb = read_predictions((base_root / "R00/predictions.csv").read_bytes())
    for r in (0, 4, 10):
        rec = gen["rounds"][r]["record"]
        _owners, y, z = read_predictions((root / f"R{r:02d}/predictions.csv").read_bytes())
        again = metrics.full_metrics(y, z)
        assert all(again[k] == rec["metric_result"][k] for k in ("AUPRC", "AUROC", "F1", "BCE", "Brier", "TP", "FP", "TN", "FN", "specificity", "recall"))
        assert np.array_equal(y, yb) and len(y) == gen["cohort"]["windows"] == 1446
        assert (rec["cohort_id"], rec["observer_id"]) == (g1_cohort.COHORT_ID, "NHM_STUDIO_GENERALISATION_OBSERVER_V1")
    pair = json.loads((root / "paired_vs_v2_R10.json").read_text())
    boot = json.loads((g1_cohort.ROOT / "configs/fl10/protocol_v1.json").read_text())["uncertainty"]
    assert (pair["replicates"], pair["seed"], pair["clusters"]) == (boot["replicates"], boot["seed"], 16) and pair["comparator"] == "FROZEN_V2" and "no significance claim" in pair["multiplicity"]
    _o, y10, z10 = read_predictions((root / "R10/predictions.csv").read_bytes())
    assert pair["metrics"]["AUPRC"]["difference_point"] == metrics.full_metrics(y10, z10)["AUPRC"] - metrics.full_metrics(yb, zb)["AUPRC"]


def test_curves_participants_and_interpretation_are_served_without_inventing_values(pretrained_run):
    c = pretrained_run.c
    run_id = pretrained_run.run_id
    gen = pretrained_run.gen
    curves = c.get(f"{S}/runs/{run_id}/generalisation/curves/10", headers=USER_A).json()
    assert curves["available"] and curves["round"]["roc"] and curves["baseline"]["roc"] and curves["round"]["pr"]
    parts = c.get(f"{S}/runs/{run_id}/generalisation/participants/10", headers=USER_A).json()
    assert parts["available"] and len(parts["round"]) == 16 == len(parts["baseline"])
    assert c.get(f"{S}/runs/{run_id}/generalisation/curves/11", headers=USER_A).status_code == 404
    text = " ".join(gen["interpretation"])
    assert "R10 versus frozen V2" in text and "not a significance test" in text and "not AAMI-SVF performance" in text
    assert "better" not in text.lower() and "superior" not in text.lower()


def test_another_user_is_refused_and_recorded_runs_have_no_fabricated_lane(pretrained_run):
    c, run_id = pretrained_run.c, pretrained_run.run_id
    assert c.get(f"{S}/runs/{run_id}/generalisation", headers=USER_B).status_code == 403
    assert c.get(f"{S}/runs/{run_id}/generalisation/curves/3", headers=USER_B).status_code == 403
    assert c.get(f"{S}/runs/{run_id}/generalisation").status_code == 401
    recorded = c.get(f"{S}/runs/recorded-A/generalisation", headers=USER_A)
    assert recorded.status_code == 409 and "GENERALISATION_NOT_AVAILABLE" in recorded.text


def test_the_primary_diagnostic_lane_is_unchanged_for_the_pretrained_run(pretrained_run):
    c = pretrained_run.c
    run_id = pretrained_run.run_id
    done = pretrained_run.done
    summary = _poll(c, f"{S}/runs/{run_id}/evaluation", USER_A, lambda s: len(s["records"]) == 11 and all(r["evaluation_status"] == "COMPLETED" for r in s["records"]))
    assert all(r["cohort_use"].startswith("REUSED SYNTHETIC DIAGNOSTIC EVALUATION") and r["schema_version"] == "STUDIO_ROUND_EVALUATION_V1" for r in summary["records"])
    assert summary["records"][0]["global_state_digest"] == done["base_model"]["state_sha256"]
