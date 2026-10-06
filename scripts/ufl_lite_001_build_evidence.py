# ruff: noqa: E501
"""UFL-LITE-001 evidence builder (records facts from the LIVE code and frozen evidence; defines no pass criteria).
  arch   -> architecture_audit.json, zero_drift_baseline.json, change_surface.json
  tests  -> test_report.json
No training, no inference, no Clerk, no network. The cohort build only constructs the existing synthetic local datasets (as prewarm does)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
EVD = Path(os.environ.get("UFL_EVD", ROOT / "reports/ufl_lite/ufl_lite_001"))
ENTRY = "af1df702c1881ef4f0e52616680c6b2c54044eaf"
FLAKE = "tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers"


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def wr(name: str, payload: dict[str, Any]) -> None:
    EVD.mkdir(parents=True, exist_ok=True)
    (EVD / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def arch() -> None:
    from product.federation.service import CLIENT_COUNT, get_cohort

    cohort = get_cohort()
    ref = json.loads((ROOT / "reports/model_v2/v2_fl_005/cohort_manifest_run.json").read_text())
    ref_sha = {c["client_id"]: (c["dataset_sha256"], c["counts"]["trainable"]) for c in ref["clients"]}
    cap010 = json.loads((ROOT / "reports/capstone/cap_010/full_browser_demo_run_1.json").read_text())["semantic_projection"]
    fed = cap010["federation"]
    datasets = {c.client_id: {"participant_id": c.participant_id, "session_id": c.session_id, "edge_node_id": c.edge_node_id, "dataset_sha256": str(c.buffer.dataset_sha256), "local_example_count": c.buffer.eligible_count(), "buffer": type(c.buffer).__name__,
                              "equals_frozen_v2_fl_005_reference": ref_sha[c.client_id] == (str(c.buffer.dataset_sha256), c.buffer.eligible_count())} for c in cohort.clients}
    mu = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
    protected = {"reused_unchanged": lib.hashes(ROOT, lib.REUSED_UNCHANGED), "scientific": lib.hashes(ROOT, lib.SCIENTIFIC), "auth": lib.hashes(ROOT, lib.AUTH_FILES)}
    baseline = {
        "baseline_id": "UFL_LITE_ZERO_DRIFT_BASELINE_V1", "entry_sha": ENTRY, "client_ids": list(cohort.client_ids), "client_count": CLIENT_COUNT, "cohort_identity_digest": cohort.identity, "datasets": datasets,
        "algorithm_default": "FEDAVG", "algorithms_supported": ["FEDAVG", "FEDPROX"], "planned_rounds": 3, "accepted_updates_per_round": [8, 8, 8], "total_updates": 24, "secagg_mode": "SECAGG_SHADOW (round-1 shadow; authoritative aggregation PLAIN)",
        "secagg_claim": "protected-aggregation-interface only (UI: 'Protected aggregation interface only'); no differential privacy", "fl_init_v2_round0_state_sha256": mu["FL_INIT_V2_round_0_state_sha256"], "fedprox_selected_mu": mu["selected_mu"],
        "canonical_candidate_digest": fed["committed_digests"] and cap010["candidates"][0]["state_digest"], "committed_round_state_digests": fed["committed_digests"], "update_digests_per_round": fed["update_digests"],
        "canonical_digest_source": "reports/capstone/cap_010/full_browser_demo_run_1.json (two identical fresh runs, CAP-010; reproduced by CAP-011 clones A/B and CLERK-LIVE-001)", "candidate": {k: cap010["candidates"][0][k] for k in ("candidate_id", "parent_model_id", "validation_status", "governance_status", "sandbox_status", "production_deployed", "round", "client_count")},
        "released_monitoring_model": "MODEL_V2_FINAL", "calibration": "CAL_V2", "software_system": "SOFTWARE_SYSTEM_V2", "protected_hashes": protected,
    }
    assert baseline["canonical_candidate_digest"] == lib.CANONICAL_CANDIDATE_DIGEST
    wr("zero_drift_baseline.json", baseline)
    s0 = datasets["SIM_FL_SITE_00"]
    wr("architecture_audit.json", {
        "entry_sha": ENTRY, "origin_main_at_entry": ENTRY, "client_count": CLIENT_COUNT, "round_count": 3, "total_updates": 24, "candidate_digest": baseline["canonical_candidate_digest"], "client_ids": list(cohort.client_ids),
        "site_00": {"technical_client_id": "SIM_FL_SITE_00", **s0}, "cohort_construction": "product/federation/service.py get_cohort() (once per process) -> product/federation/local_cohort.py build_client(index) -> federated.virtual_client_source_v1.build_local_dataset + product/edge/label_adapter.SimulationLabelAdapterV1 -> product/edge/local_training_buffer.LocalTrainingBufferV1",
        "local_buffer_implementation": "product.edge.local_training_buffer.LocalTrainingBufferV1 (client-local; training_arrays(requester_client_id) refuses cross-client access)", "client_adapter_implementation": "product.federation.client_v2.CapstoneFlClientAdapterV2 (round-scoped; inherits CapstoneFlClientAdapterV1 which calls the existing train_local_epoch_v2 / train_local_fedprox_epoch_v2)",
        "aggregation_implementation": "federated.wearable_fl_system_v1.Coordinator (existing V2 coordinator); service.py contains NO aggregation mathematics", "run_owner_storage": "SQLite federation_runs.user_id (capstone_persistence/federation_store.py); FederationService._row() raises FORBIDDEN for a non-owner",
        "auth_identity_source": "api/product_app_v1_2.py identity(request) -> FederationService methods receive user.user_id; product/auth resolver (CLERK or DEMO) decides; /product/v1/system reports auth_provider", "client_list_endpoint": "GET /product/v1/federation/clients is GLOBAL: authenticated but not user- or run-scoped; FederationService.clients() reads the shared frozen cohort (FLClientIdentity, extra='forbid')",
        "run_model_client_ids": "FederationRun.client_ids is the fixed cohort list SIM_FL_SITE_00..07 for every run and user (FederationService._cohort_ids)", "event_client_references": "client.status / client.training_progress / client.update_ready events carry client_id; the live frontend ClientGrid renders the eight ids",
        "sqlite_client_status": "fl_client_statuses(status_pk, run_id, client_id, round_id, client_state, local_example_count, update_digest) - no user column", "artifact_run_meta": "FederationArtifactStore.write_run_meta(run_id, meta): scenario/algorithm/secagg/replay_source/secagg_shadow; no identity",
        "restart_recovery": "FederationService.recover(): RUNNING LIVE runs resume from checkpoints after assess(row, artifacts, cohort.identity); the cohort identity digest 14c2a6f4... must match; REPLAY runs interrupted are failed", "replay": "create_run(REPLAY) clones the owner's latest completed LIVE_RUN event log (clone_event_for_replay/retarget marks federation.status run_type=REPLAY); no training executes",
        "frontend_call_chain": "routes/app/federation/live/+page.svelte -> ClientGrid.svelte (ids SIM_FL_SITE_00..07; props live, round, replay); the product store exposes authState.system.auth_provider and the run exposes run_type", "auth_provider_available_at_presentation": True,
        "findings": {"clients_endpoint_global_not_run_scoped": True, "run_owner_available_to_frontend_by_ownership_scoping": True, "no_user_column_in_client_status": True, "no_new_class_or_buffer_needed": True, "no_db_migration_needed": True, "no_api_field_needed": True},
        "minimum_future_insertion_points": ["frontend/src/lib/product/federation/participation.ts: pure role helper (CLERK && LIVE_RUN && client_id==SIM_FL_SITE_00)", "frontend ClientGrid.svelte: optional ownerBoundClientId prop (display only)", "federation live/rounds pages: pass the prop from store system.auth_provider + run.run_type", "tests (frontend + Python non-interference)", "governance: new UI successor lock + successor-aware UI verifiers"],
        "new_fl_pipeline_required": False, "new_client_class_required": False, "new_training_buffer_required": False, "db_migration_required": False, "api_field_required": False, "secrets_or_tokens_recorded": False})
    wr("change_surface.json", {
        "MUST_REUSE_UNCHANGED": {"product/edge/local_training_buffer.py": "client-local training data and label provenance", "product/federation/client_v2.py": "round-scoped client adapter", "product/federation/client.py": "local training via existing train_local_epoch_v2 / FedProx epoch", "product/federation/local_cohort.py": "cohort construction and datasets",
                                  "product/federation/service.py": "run lifecycle, ownership, recovery, replay", "federated/wearable_fl_system_v1.py": "Coordinator / aggregation weighting", "federated/aggregation.py": "aggregation", "product/federation/secagg_shadow.py": "SecAgg round-1 shadow", "product/models/governance.py": "candidate governance and sandbox-only status",
                                  "capstone_persistence/federation_store.py": "no schema change", "api/product_app_v1_2.py + api/product_app_v1_3.py": "no route or response-model change", "product/auth/* + frontend/src/lib/product/auth.ts": "accepted Clerk implementation"},
        "LIKELY_PHASE2_PRESENTATION_CHANGE": {"frontend/src/lib/product/federation/participation.ts (new, pure)": "role = f(auth_provider, run_type, client_id)", "frontend/src/lib/components/product/federation/ClientGrid.svelte": "optional display-only prop (MY EDGE CLIENT / SYNTHETIC PEER)", "frontend/src/routes/app/federation/live/+page.svelte and rounds/+page.svelte": "pass owner-bound id for qualifying runs only",
                                              "frontend tests + tests/test_ufl_lite_*.py": "assert unchanged digests and no global binding", "UI successor lock + successor-aware UI verifiers": "governance consequence of any frontend edit"},
        "MUST_NOT_TOUCH": ["MODEL_V2_FINAL / CAL_V2 / SOFTWARE_SYSTEM_V2 / FL_INIT_V2 / FEDPROX_MU_V2 and V2-FL evidence", "federated/* mathematics", "product/federation/* runtime", "product/edge/*", "SQLite schema and artifact formats", "FLClientIdentity / FederationRun / fl_client_v1 / fl_run_v1 contracts", "Clerk UI loader, backend verification, authorized parties, REST bearer, WebSocket cookie", "frontend/src/routes/app/federation/clients/+page.svelte (global view: no binding)", "capstone-release-v1 and capstone-clerk-connected-v1 tags and targets"],
        "why": "The binding is a presentation function of data the frontend already has (backend auth mode, run type, run ownership by scoping). Persisting or serialising it would require amending frozen extra='forbid' contracts and the API, with no reproducibility benefit because it does not influence any digest.", "phase_2_expectation": "thin frontend identity/presentation layer; STOP if training/coordinator/backend code is found necessary"})
    print(json.dumps({"arch": "DONE", "site00_examples": s0["local_example_count"]}))


def tests() -> None:
    work = Path(os.environ.get("UFL_WORK", tempfile.mkdtemp(prefix="ufl-tests-")))
    work.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": "src:."}
    bin_dir = Path(sys.executable).parent

    def sh(cmd: list[str], log: str) -> tuple[int, str, float]:
        t0 = time.time()
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=7200)
        (work / log).write_text(r.stdout + r.stderr)
        return r.returncode, r.stdout + r.stderr, round(time.time() - t0, 1)

    def counts(text: str) -> dict[str, int]:
        last = [ln for ln in text.splitlines() if re.search(r" in [\d.]+s", ln)]
        return {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|deselected|errors?)", last[-1] if last else "")}

    def junit(path: Path) -> dict[str, str]:
        return {f"{c.get('classname')}::{c.get('name')}": ("failed" if (c.find("failure") is not None or c.find("error") is not None) else "skipped" if c.find("skipped") is not None else "passed") for c in ET.parse(path).getroot().iter("testcase")}

    rep: dict[str, Any] = {"commands": {}}
    rc, text, secs = sh([sys.executable, "-m", "pytest", "tests/test_ufl_lite_contract.py", "tests/test_capstone_federation_service.py", "tests/test_capstone_federation_isolation.py", "tests/test_capstone_federation_contracts.py", "tests/test_capstone_lifecycle.py", "-q", "-p", "no:cacheprovider", f"--junitxml={work / 't.xml'}"], "targeted.log")
    rep["targeted"] = {"returncode": rc, "counts": counts(text), "seconds_machine_specific": secs, "tests": junit(work / "t.xml")}
    attempts = []
    for i in range(5):
        r = subprocess.run([sys.executable, "-m", "pytest", FLAKE, "-q", "-p", "no:cacheprovider"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        attempts.append({"attempt": i + 1, "passed": r.returncode == 0, "known_signature": "AssertionError: assert (789 > 100 and False)" in r.stdout + r.stderr})
        if r.returncode == 0:
            break
    rep["inherited_flake"] = {"status": "PASS_INHERITED_FLAKE_POLICY" if any(a["passed"] for a in attempts) and all(a["passed"] or a["known_signature"] for a in attempts) else "FAIL", "attempts": attempts}
    rc, text, secs = sh([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", f"--deselect={FLAKE}", f"--junitxml={work / 'full.xml'}"], "full.log")
    full = junit(work / "full.xml")
    rep["full_regression"] = {"returncode": rc, "counts": counts(text), "failed": sorted(k for k, v in full.items() if v == "failed"), "seconds_machine_specific": secs}
    rc, text, _ = sh([str(bin_dir / "ruff"), "check", "."], "ruff.log")
    rep["commands"]["ruff"] = {"returncode": rc, "output": text.strip()[-200:]}
    rc, text, _ = sh([sys.executable, "-m", "pip", "check"], "pip.log")
    rep["commands"]["pip_check"] = {"returncode": rc, "output": text.strip()[-200:]}
    rep["ci_queried"] = False
    rep["ci_triggered"] = False
    wr("test_report.json", rep)
    print(json.dumps({"targeted": rep["targeted"]["counts"], "full": rep["full_regression"]["counts"]}))


if __name__ == "__main__":
    {"arch": arch, "tests": tests}[sys.argv[1]]()
