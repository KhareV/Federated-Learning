# ruff: noqa: E501
"""UFL-LITE-001 / UFLG0 frozen evaluator (criteria in configs/ufl_lite/uflg0_protocol_v1.json).
  --pre-transition  defer only the registry PASS checks;  (no flag) strict final evaluation; writes uflg0_criteria.json"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
EVD = Path(os.environ.get("UFL_EVD", ROOT / "reports/ufl_lite/ufl_lite_001"))
CONFIG = ROOT / "configs/ufl_lite/uflg0_protocol_v1.json"
LOCK = ROOT / "artifacts/ufl_lite/UFL_LITE_001_PROTOCOL_V1.lock.json"
ENTRY = "af1df702c1881ef4f0e52616680c6b2c54044eaf"
PRE = "--pre-transition" in sys.argv
DEFERRED = {"task_pass", "gate_pass"}


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def rd(name: str) -> dict[str, Any]:
    return json.loads((EVD / name).read_text())


def drift(*paths: str) -> list[str]:
    return git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *paths).split()


def added() -> list[str]:
    return git("diff", "--name-only", "--diff-filter=A", ENTRY).split() + git("ls-files", "--others", "--exclude-standard").split()


def registry(name: str, key: str) -> dict[str, str]:
    with (ROOT / f"manifests/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        return {r[key]: r["status"] for r in csv.DictReader(h)}


def tags() -> dict[str, str]:
    out = {}
    for t in lib.RELEASE_TAGS:
        out[t] = subprocess.run(["git", "ls-remote", "origin", f"refs/tags/{t}^{{}}"], cwd=ROOT, capture_output=True, text=True).stdout.split("\t")[0]
    return out


def build_checks() -> dict[str, Callable[[], bool]]:
    k = lambda: json.loads((ROOT / lib.CONTRACT).read_text())  # noqa: E731
    base = lambda: rd("zero_drift_baseline.json")  # noqa: E731
    arch = lambda: rd("architecture_audit.json")  # noqa: E731
    rep = lambda: rd("test_report.json")  # noqa: E731
    return {
        "entry_audited": lambda: rd("entry_audit.json")["entry_sha"] == ENTRY and rd("entry_audit.json")["origin_main_sha"] == ENTRY and rd("entry_audit.json")["working_tree_clean_before_entry"] is True,
        "tags_unchanged": lambda: lib.tags_ok(tags()),
        "locks_verify": lambda: _locks(),
        "c_client_count": lambda: k()["client_count"] == 8 and k()["synthetic_peer_count"] == 7 and k()["no_ninth_client"] is True,
        "c_owner_slot": lambda: k()["owner_bound_client_id"] == "SIM_FL_SITE_00" and k()["no_dynamic_hash_of_user_to_client"] is True,
        "c_peers": lambda: k()["synthetic_peer_client_ids"] == [f"SIM_FL_SITE_{i:02d}" for i in range(1, 8)],
        "b_cohort": lambda: lib.cohort_ok(base()["client_ids"])["ok"] and base()["client_count"] == 8 and bool(base()["cohort_identity_digest"]),
        "b_dataset_shas": lambda: all(len(v["dataset_sha256"]) == 64 and v["equals_frozen_v2_fl_005_reference"] for v in base()["datasets"].values()) and base()["datasets"]["SIM_FL_SITE_00"]["dataset_sha256"] == k()["site_00"]["dataset_sha256"],
        "b_example_counts": lambda: base()["datasets"]["SIM_FL_SITE_00"]["local_example_count"] == k()["site_00"]["local_example_count"] == 93,
        "c_reuse_buffer": lambda: k()["reuse"]["training_buffer"] == "LocalTrainingBufferV1" and k()["reuse"]["new_training_buffer"] is False and base()["datasets"]["SIM_FL_SITE_00"]["buffer"] == "LocalTrainingBufferV1",
        "c_reuse_adapter": lambda: k()["reuse"]["client_adapter"] == "CapstoneFlClientAdapterV2" and k()["reuse"]["new_client_class"] is False,
        "a_adapter": lambda: "CapstoneFlClientAdapterV2" in arch()["client_adapter_implementation"] and arch()["new_client_class_required"] is False,
        "c_reuse_coordinator": lambda: "Coordinator" in k()["reuse"]["coordinator"] and k()["reuse"]["new_fl_pipeline"] is False,
        "a_coordinator": lambda: "Coordinator" in arch()["aggregation_implementation"] and arch()["new_fl_pipeline_required"] is False,
        "h_reused_unchanged": lambda: lib.hash_drift(ROOT, base(), "reused_unchanged") == [],
        "h_scientific": lambda: lib.hash_drift(ROOT, base(), "scientific") == [],
        "h_auth": lambda: lib.hash_drift(ROOT, base(), "auth") == [],
        "b_algorithms": lambda: base()["algorithm_default"] == "FEDAVG" and base()["algorithms_supported"] == ["FEDAVG", "FEDPROX"] and k()["algorithm_orthogonality"],
        "b_secagg": lambda: "SECAGG_SHADOW" in base()["secagg_mode"] and "protected-aggregation-interface only" in base()["secagg_claim"] and k()["secagg_unchanged"] is True,
        "b_fl_init": lambda: len(base()["fl_init_v2_round0_state_sha256"]) == 64 and k()["fl_init_unchanged"] is True,
        "b_rounds": lambda: base()["planned_rounds"] == 3 == k()["planned_rounds"],
        "b_updates": lambda: base()["total_updates"] == 24 == k()["expected_updates"] and base()["accepted_updates_per_round"] == [8, 8, 8],
        "b_candidate_digest": lambda: base()["canonical_candidate_digest"] == lib.CANONICAL_CANDIDATE_DIGEST == k()["canonical_candidate_digest"] and sorted(base()["committed_round_state_digests"]) == ["1", "2", "3"],
        "c_monitoring_excluded": lambda: k()["monitoring_data_used_for_training"] is False and k()["monitoring_session_feeds_local_buffer"] is False and k()["prediction_as_label"] is False and lib.monitoring_isolation_audit(ROOT)["ok"],
        "c_no_physiology_claim": lambda: k()["real_user_physiology_claimed_as_training_data"] is False and k()["site_00"]["dataset_represents_user_physiology"] is False and k()["site_00"]["data_origin"] == "SYNTHETIC_ENGINEERING",
        "c_no_personal": lambda: k()["personal_model"] is False and k()["personalized_fl_claim"] is False and "personalized federated learning" in k()["forbidden_claims"],
        "c_no_ninth": lambda: k()["no_ninth_client"] is True and base()["client_count"] == 8,
        "c_no_migration": lambda: k()["reuse"]["db_migration"] is False and k()["binding_decision"].startswith("DERIVED_AT_PRESENTATION_TIME"),
        "a_no_migration": lambda: arch()["db_migration_required"] is False and arch()["api_field_required"] is False and arch()["findings"]["no_user_column_in_client_status"] is True,
        "a_ownership": lambda: "federation_runs.user_id" in arch()["run_owner_storage"] and "FORBIDDEN" in arch()["run_owner_storage"] and arch()["auth_provider_available_at_presentation"] is True,
        "c_identity_excluded": lambda: len(k()["clerk_identity_never_enters"]) >= 9 and "candidate digest" in k()["clerk_identity_never_enters"],
        "c_context": lambda: k()["qualifying_auth_mode"] == "CLERK" and k()["qualifying_run_type"] == "LIVE_RUN" and "GLOBAL" in k()["non_qualifying"]["global_clients_view"] and arch()["findings"]["clients_endpoint_global_not_run_scoped"] is True and lib.global_view_binding_audit(ROOT)["ok"],
        "c_replay": lambda: "REPLAY" in k()["non_qualifying"] and "never alters replay" in k()["non_qualifying"]["REPLAY"],
        "no_sci_drift": lambda: not drift("checkpoints", "reports/model_v2", "src", "simulation", "privacy", "contracts/capstone", ":(glob)artifacts/*.json", "federated"),
        "no_hardware": lambda: not [p for p in added() if re.search(r"ble_|bluetooth|serial_port|firmware", p, re.I)],
        "no_runtime_drift": lambda: not drift("api", "product", "capstone_persistence", "federated", "frontend", "src", "scripts/run_capstone_clerk_connected.py", "scripts/run_capstone_faculty_demo.py") and not [p for p in added() if p.startswith(("api/", "product/", "capstone_persistence/", "federated/", "frontend/"))],
        "contract_exists": lambda: (ROOT / lib.CONTRACT).is_file() and k()["contract_id"] == "USER_BOUND_FL_PARTICIPATION_V1",
        "note_exists": lambda: (ROOT / "docs/ufl_lite/USER_BOUND_FL_PARTICIPATION_V1.md").is_file() and "Why slot 00" in (ROOT / "docs/ufl_lite/USER_BOUND_FL_PARTICIPATION_V1.md").read_text(),
        "change_surface_ok": lambda: set(rd("change_surface.json")) >= {"MUST_REUSE_UNCHANGED", "LIKELY_PHASE2_PRESENTATION_CHANGE", "MUST_NOT_TOUCH", "why"},
        "baseline_exists": lambda: base()["baseline_id"] == "UFL_LITE_ZERO_DRIFT_BASELINE_V1",
        "mutation_log": lambda: (m := rd("mutation_controls.json"))["all_caught"] and m["all_restored"] and [x["mutation"] for x in m["controls"]] == json.loads(CONFIG.read_text())["mutation_controls"] and len(m["controls"]) == 15,
        "targeted_ok": lambda: rep()["targeted"]["returncode"] == 0 and rep()["targeted"]["counts"].get("failed", 0) == 0 and rep()["commands"]["ruff"]["returncode"] == 0 and rep()["commands"]["pip_check"]["returncode"] == 0 and rep()["ci_queried"] is False and rep()["ci_triggered"] is False,
        "full_ok": lambda: rep()["full_regression"]["returncode"] == 0 and not rep()["full_regression"]["failed"] and rep()["inherited_flake"]["status"] == "PASS_INHERITED_FLAKE_POLICY",
        "b_model": lambda: base()["released_monitoring_model"] == "MODEL_V2_FINAL" and base()["calibration"] == "CAL_V2" and base()["candidate"]["production_deployed"] is False and base()["candidate"]["sandbox_status"] == "IN_SANDBOX" and k()["candidate_deployed"] is False,
        "c_decision": lambda: "option A" in k()["binding_decision"] and len(k()["binding_decision_rationale"]) >= 4,
        "lock_ok": lambda: _lock_ok(),
        "task_pass": lambda: registry("ufl_lite/task", "task_id").get("UFL-LITE-001") == "PASS",
        "gate_pass": lambda: registry("ufl_lite/gate", "gate_id").get("UFLG0") == "PASS",
    }


def _locks() -> bool:
    from scripts.cap_011_protected_audit import all_locks
    from scripts.verify_clerk_connected import verify

    return all(v["verified"] for v in all_locks().values()) and verify()["status"] == "PASS"


def _lock_ok() -> bool:
    lock = json.loads(LOCK.read_text())
    return all(lib.sha(ROOT / p) == h for p, h in lock["bound_files"].items()) and lock["criteria_count"] == json.loads(CONFIG.read_text())["criteria_count"]


def evaluate() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text())
    frozen = config["uflg0_criteria"]
    if len(frozen) != config["criteria_count"]:
        raise RuntimeError("UFLG0_FROZEN_CRITERIA_CHANGED")
    from scripts.ufl_lite_001_protected_audit import final as protected_final

    protected_final()
    checks = build_checks()
    tests = rd("test_report.json")["targeted"]["tests"]
    cache: dict[str, tuple[bool, str]] = {}

    def run(name: str) -> tuple[bool, str]:
        if name not in cache:
            if PRE and name in DEFERRED:
                cache[name] = (True, "DEFERRED")
            else:
                try:
                    cache[name] = (bool(checks[name]()), "")
                except Exception as e:
                    cache[name] = (False, f"{type(e).__name__}:{str(e)[:120]}")
        return cache[name]

    rows = []
    for row in frozen:
        res = []
        for c in row["checks"]:
            if c.startswith("T:"):
                hits = [v for kk, v in tests.items() if kk.split("::")[-1] == c[2:]]
                res.append((c, bool(hits) and all(v == "passed" for v in hits), ""))
            else:
                res.append((c, *run(c)))
        rows.append({"id": row["id"], "text": row["text"], "pass": all(r[1] for r in res), "checks": [{"check": n, "pass": ok, **({"note": w} if w else {})} for n, ok, w in res]})
    prot = rd("protected_artifact_final.json")
    ok_prot = prot["protected_artifact_drift"] is False
    return {"gate": "UFLG0", "mode": "PRE_TRANSITION" if PRE else "FINAL", "criteria_count": len(rows), "protected_artifact_drift_false": ok_prot, "all_decided_pass": all(r["pass"] for r in rows) and ok_prot, "failed": [r["id"] for r in rows if not r["pass"]], "criteria": rows}


def main() -> int:
    r = evaluate()
    (EVD / ("uflg0_pre_transition.json" if PRE else "uflg0_criteria.json")).write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"mode": r["mode"], "all_decided_pass": r["all_decided_pass"], "failed": r["failed"]}))
    return 0 if r["all_decided_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
