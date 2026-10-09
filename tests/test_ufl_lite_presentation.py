# ruff: noqa: E501
"""UFL-LITE-002: non-interference + governance assertions for the presentation-only change (reuses the UFL-LITE-001 baseline)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

from scripts import ufl_lite_002_lib as plib
from scripts import ufl_lite_lib as lib
from tests.capstone_federation_support import completed_run

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "6871e0891ad697dab3f122afaba2d331a279ec8c"
BASELINE = lib.load_baseline(ROOT)


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def test_cohort_and_baseline_unchanged() -> None:
    from product.federation.service import CLIENT_COUNT, get_cohort

    cohort = get_cohort()
    assert CLIENT_COUNT == 8 and cohort.client_ids == lib.CLIENT_IDS and cohort.identity == BASELINE["cohort_identity_digest"]
    for c in cohort.clients:
        frozen = BASELINE["datasets"][c.client_id]
        assert (str(c.buffer.dataset_sha256), c.buffer.eligible_count(), c.participant_id, c.edge_node_id) == (frozen["dataset_sha256"], frozen["local_example_count"], frozen["participant_id"], frozen["edge_node_id"])
    assert cohort.clients[0].buffer.eligible_count() == 93 and BASELINE["fl_init_v2_round0_state_sha256"]


def test_completed_run_reproduces_baseline() -> None:
    run = completed_run("FEDAVG", "SECAGG_SHADOW")
    assert [r["accepted_update_count"] for r in run.rounds] == [8, 8, 8] and sum(1 for e in run.events if e["event_type"] == "client.update_ready") == 24
    with sqlite3.connect(run.root / "product.sqlite3") as db:
        (digest, governance, sandbox, deployed, clients) = db.execute("select state_digest, governance_status, sandbox_status, production_deployed, client_count from candidate_models").fetchone()
    assert digest == lib.CANONICAL_CANDIDATE_DIGEST and (governance, sandbox, deployed, clients) == ("ACCEPTED_TO_SANDBOX", "IN_SANDBOX", 0, 8)
    assert not any(k in run.run for k in ("participation_role", "owner", "user_id")) and lib.identity_in_payload([e["payload"] for e in run.events if e["event_type"].startswith("client.")]) == []


def test_backend_api_db_fl_and_auth_are_byte_identical_to_the_entry() -> None:
    from scripts.successor_chain import accounted_changes     # the additive successors (NHM_FL10_001, NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001) account for their own frontend delta; anything else still fails

    drift = [p for p in git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", "api", "product", "capstone_persistence", "federated", "privacy", "simulation", "src", "checkpoints", "contracts", "frontend/package.json", "frontend/package-lock.json",
             "frontend/clerk-sdk", "frontend/src/lib/product/auth.ts", "frontend/src/lib/product/federation/types.ts", "frontend/src/lib/product/federation/live-model.ts", "frontend/src/lib/product/federation/state.svelte.ts", ":(exclude)product/observatory", ":(exclude)api/product_app_observatory_v1.py", ":(exclude)api/observatory_*.py").split()
             if p not in accounted_changes(ROOT)]
    assert drift == []  # UI-ENH-001: the clients page is redesigned; its unbound-global-view audit remains in ufl_lite_002_lib.global_page_audit
    for group in ("reused_unchanged", "scientific", "auth"):
        assert lib.hash_drift(ROOT, BASELINE, group) == [], group
    assert lib.monitoring_isolation_audit(ROOT)["ok"] and lib.class_audit(ROOT)["ok"]


def test_presentation_implementation_audits() -> None:
    for name in ("helper_audit", "grid_audit", "live_audit", "text_audit"):
        assert getattr(plib, name)()["ok"], (name, getattr(plib, name)())
    assert plib.global_page_ok()


def test_ui_v1_4_chain_verifies_and_predecessor_locks_are_byte_identical() -> None:
    from scripts.verify_capstone_ui_v1 import verify as v1
    from scripts.verify_capstone_ui_v1_1 import verify as v11
    from scripts.verify_capstone_ui_v1_2 import verify as v12
    from scripts.verify_capstone_ui_v1_3 import verify as v13
    from scripts.verify_capstone_ui_v1_4 import verify as v14

    assert all(f()["status"] == "PASS" for f in (v1, v11, v12, v13, v14))
    assert git("diff", "--name-only", ENTRY, "--", "artifacts/capstone/CAPSTONE_UI_V1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json") == ""
    lock = json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json").read_text())
    assert lock["predecessor_id"] == "CAPSTONE_UI_V1_3" and lock["owner_phase"] == "UFL-LITE-002" and lock["reason"] == "USER_BOUND_FL_PRESENTATION_SUCCESSOR" and lock["npm_dependencies_added"] == []
    changed = sorted(set(git("diff", "--name-only", "--diff-filter=AM", ENTRY, "--", "frontend").split()))
    accounted = set(lock["changed_from_predecessor"])
    successor15 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json"       # FINAL-EVAL-REPAIR-001: V1_5 accounts for its own, separately governed delta
    if successor15.exists():
        accounted |= set(json.loads(successor15.read_text())["changed_from_predecessor"])
    successor16 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json"       # FINAL-EVAL-REPAIR-002: V1_6 accounts for its own, separately governed delta
    if successor16.exists():
        accounted |= set(json.loads(successor16.read_text())["changed_from_predecessor"])
    successor17 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_7.lock.json"       # UI-ENH-001: V1_7 accounts for its own, separately governed delta
    if successor17.exists():
        accounted |= set(json.loads(successor17.read_text())["changed_from_predecessor"])
    successor18 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_8.lock.json"
    if successor18.exists():
        accounted |= set(json.loads(successor18.read_text())["changed_from_predecessor"])
    successor19 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_9.lock.json"
    if successor19.exists():
        accounted |= set(json.loads(successor19.read_text())["changed_from_predecessor"])
    observatory = ROOT / "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"       # additive Observatory successor tip
    if observatory.exists():
        accounted |= set(json.loads(observatory.read_text())["changed_from_predecessor"])
    diag = ROOT / "artifacts/observatory/NHM_OBS_DIAG_001.lock.json"
    if diag.exists():
        accounted |= set(json.loads(diag.read_text())["changed_from_predecessor"])
    final = ROOT / "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"
    if final.exists():
        accounted |= set(json.loads(final.read_text())["changed_from_predecessor"])
    from scripts.successor_chain import accounted_changes     # NHM_FL10_001 / NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 account for their own delta (exact-identity chain)

    accounted |= accounted_changes(ROOT)
    assert changed == sorted(accounted), changed


def _with_v15(then=lambda s: None):
    """The shadow copies the CURRENT frontend, which FINAL-EVAL-REPAIR-001 governs through its V1_5 successor lock: register that lock in the shadow too."""
    def mutate(s):
        import shutil

        v15 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json"
        if v15.exists():
            shutil.copyfile(v15, s / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json")
        v16 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json"
        if v16.exists():
            shutil.copyfile(v16, s / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json")
        v17 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_7.lock.json"
        if v17.exists():
            shutil.copyfile(v17, s / "artifacts/capstone/CAPSTONE_UI_V1_7.lock.json")
        v18 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_8.lock.json"
        if v18.exists():
            shutil.copyfile(v18, s / "artifacts/capstone/CAPSTONE_UI_V1_8.lock.json")
        v19 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_9.lock.json"
        if v19.exists():
            shutil.copyfile(v19, s / "artifacts/capstone/CAPSTONE_UI_V1_9.lock.json")
        obs = ROOT / "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"
        if obs.exists():
            (s / "artifacts/observatory").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(obs, s / "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json")
        diag = ROOT / "artifacts/observatory/NHM_OBS_DIAG_001.lock.json"
        if diag.exists():
            shutil.copyfile(diag, s / "artifacts/observatory/NHM_OBS_DIAG_001.lock.json")
        final = ROOT / "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"
        if final.exists():
            (s / "artifacts/final_showcase").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(final, s / "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json")
        for rel in ("artifacts/fl10/NHM_FL10_001.lock.json", "artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json"):      # the additive successors after the final showcase
            if (ROOT / rel).exists():
                (s / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / rel, s / rel)
        then(s)
    return mutate


def test_ui_v1_4_verifier_fails_closed_on_unbound_missing_wrong_digest_and_modified_predecessor() -> None:
    assert plib.shadow_ui14(_with_v15()) is None
    assert "UNBOUND_OR_MISSING" in (plib.shadow_ui14(_with_v15(lambda s: (s / "frontend/src/lib/product/federation/unbound_extra.ts").write_text("x"))) or "")
    assert "UNBOUND_OR_MISSING" in (plib.shadow_ui14(_with_v15(lambda s: (s / "frontend/src/lib/product/federation/participation.ts").unlink())) or "")
    assert "TAMPER" in (plib.shadow_ui14(_with_v15(lambda s: (s / "frontend/src/lib/product/federation/participation.ts").write_text("export const x = 1;\n"))) or "")
    assert "PREDECESSOR_DRIFT" in (plib.shadow_ui14(_with_v15(lambda s: (s / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json").write_text("{}\n"))) or "")


def test_compatibility_amendments_are_pure_successor_records() -> None:
    names = ["CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_9_1.json", "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_4.json", "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.amendment_9_4.json", "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_3.json"]
    for n in names:
        a = json.loads((ROOT / "artifacts/capstone" / n).read_text())
        assert a["scope"] == "SUCCESSOR_COMPATIBILITY_ONLY" and a["result_evidence_committed_with_amendment"] is False and a["previous_amendment"] and a["owner_phase"]
        assert all({"old_sha256", "new_sha256"} <= set(v) for v in a["files"].values()) and set(a) >= {"defect", "change", "reason"}
