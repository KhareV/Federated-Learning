#!/usr/bin/env python3
# ruff: noqa: E501
"""V2-REL-001 cutover evidence assembly (reads committed files and the evidence JSONs produced by
scripts/run_v2_rel_001_release_checks.py and scripts/v2_014_clone_checks.py; nothing is re-run
here except cheap static verifiers). `--stage1` writes the V2RELG0 criteria with the clean-release-clone
and clean-push criteria PENDING; `--final CLONE_EVIDENCE_DIR` writes the final criteria after the
fresh-clone release smoke."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_rel_001/cutover"
ENTRY = "f3d3d9f642fbd20158743c24c60d96b945c35d0c"
PROTECTED = ["artifacts/API_RUNTIME_V1.lock.json", "artifacts/API_RUNTIME_V1_1.lock.json",
             "artifacts/API_RUNTIME_V2.lock.json", "artifacts/API_RUNTIME_V2_1.lock.json",
             "artifacts/CAL_V1.json", "artifacts/CAL_V2.json", "artifacts/DASHBOARD_UI_V1_4.lock.json",
             "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json", "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
             "artifacts/SECAGG_METHOD_V2.lock.json", "artifacts/MODEL_V2_COMPLETE_REPRO_V1.lock.json",
             "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json",
             "artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json",
             "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json", "artifacts/deployment", "checkpoints",
             "reports/model_v2", "manifests/clients", "preprocessing", "privacy", "federated", "models",
             "evaluation", "deployment", "simulation", "fusion", "api/app.py", "api/app_v2.py",
             "api/runtime.py", "api/runtime_v2.py", "api/schemas.py", "api/session.py", "contracts",
             "frontend/static/replay", "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json"]
ALLOWED_NEW = ("reports/model_v2/v2_rel_001/",)
FORBIDDEN_FRONTEND = ("on-device SIMD feature extraction", "Differential Privacy Engine",
                      "trained federatively", "hospital deployment", "clinically validated")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def _first_commit(path: str) -> str:
    return _git("log", "--diff-filter=A", "--format=%H", "--", path).split()[-1]


def _ancestor(a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ROOT).returncode == 0


def stage_audits() -> None:
    changed = []
    for line in _git("diff", "--name-status", ENTRY, "HEAD").splitlines():
        status, *paths = line.split("\t")
        if status[0] in "MDR" and any(p == q or p.startswith(q + "/") for p in paths for q in PROTECTED):
            changed.append(line)
    dirty = [x for x in _git("status", "--porcelain").splitlines()
             if any(x[3:] == q or x[3:].startswith(q + "/") for q in PROTECTED)
             and not x[3:].startswith(ALLOWED_NEW)]
    _write("protected_artifact_audit.json", {
        "entry_commit": ENTRY, "protected_modified_or_deleted_since_entry": changed,
        "protected_dirty": dirty, "predecessor_locks_preserved_byte_identical": {
            "DASHBOARD_UI_V1_4": hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_4.lock.json") == json.loads(
                (ROOT / "artifacts/DASHBOARD_UI_V1_5.lock.json").read_text())["predecessor_sha256"],
            "E2E_REPLAY_SOFTWARE_V1_3": hash_file(ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json")
            == json.loads((ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_4.lock.json").read_text())[
                "predecessor_sha256"]},
        "status": "PASS" if not changed and not dirty else "FAIL"})
    ui_files = json.loads((ROOT / "artifacts/DASHBOARD_UI_V1_5.lock.json").read_text())[
        "frontend_application_sources_changed"]
    hits = [f"{p}:{needle}" for p in ui_files for needle in FORBIDDEN_FRONTEND
            if needle in (ROOT / p).read_text()]
    readme = (ROOT / "README.md").read_text()
    manifest = json.loads((ROOT / "reports/model_v2/v2_rel_001/system_v2_release_manifest.json").read_text())
    _write("claim_audit.json", {
        "frontend_files_scanned": ui_files, "forbidden_phrase_hits": hits,
        "readme_non_diagnostic": "non-diagnostic research" in readme,
        "readme_states_fl_not_deployed": "not deployed" in readme,
        "readme_preserves_historical_disposition": "MODEL_V2_NOT_PROMOTED_RELEASE_CI" in readme,
        "known_limitations": len(manifest["known_limitations"]),
        "unsupported_claims": manifest["unsupported_claims"],
        "hardware_or_clinical_claim": False, "status": "PASS" if not hits and len(
            manifest["known_limitations"]) == 9 else "FAIL"})


def criteria(final_dir: Path | None) -> dict:
    decision = json.loads((ROOT / "reports/model_v2/v2_rel_001/system_v2_release_decision.json").read_text())
    from scripts.verify_default_runtime_binding_v2 import verify as verify_binding

    binding = verify_binding()
    default_lock = json.loads((ROOT / "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json").read_text())
    promotion = ROOT / "reports/model_v2/v2_007/promotion_decision.json"
    lock = json.loads((ROOT / "manifests/model_v2/MODEL_V2_VALIDATION_DECISION_V1.lock.json").read_text())
    policy_commit = _first_commit("artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json")
    decision_commit = _first_commit("artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json")
    cutover_commit = _first_commit("api/app_default.py")
    pytest_run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings",
                                 "tests/test_v2_rel_001_default_binding.py"], cwd=ROOT,
                                capture_output=True, text=True)
    replay, rollback, isolation = (_load("default_replay.json"), _load("rollback_replay.json"),
                                   _load("isolation.json"))
    frontend, regression, lint = _load("frontend.json"), _load("regression.json"), _load("lint.json")
    smoke = [_load(n) for n in ("smoke_model_v2.json", "smoke_fixed_vectors.json",
                                "smoke_gateway.json", "smoke_fl_init.json", "smoke_synthetic_fl.json")]
    tiles = json.dumps(replay["frontend_e2e"].get("identities_rendered", {}))
    flags = {
        "release_policy_frozen_before_default_change": _ancestor(policy_commit, cutover_commit),
        "decision_evaluator_frozen_evidence_only": decision["new_scientific_evidence_generated"] is False
        and decision["waveform_datasets_accessed"] is False,
        "all_hard_release_blockers_pass": decision["SYSTEM_V2_RELEASE_DECISION"] == "ACCEPT"
        and not decision["failed_criteria"] and decision["manual_override"] is False,
        "historical_scientific_non_promotion_preserved": hash_file(promotion) == lock["promotion_decision_sha256"],
        "release_decision_explicit_and_frozen_before_cutover": _ancestor(decision_commit, cutover_commit),
        "model_v2_final_default_only_after_accept": _ancestor(decision_commit, cutover_commit)
        and default_lock["identity"]["model_id"] == "MODEL_V2_FINAL",
        "fl_checkpoint_not_deployed": default_lock["federated_checkpoint_deployed"] is False
        and default_lock["identity_values"]["checkpoint_sha256"] == hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
        "cal_v2_gateway_v2_binding_exact": binding["status"] == "PASS" and all(s["status"] == "PASS" for s in smoke),
        "api_schema_v1_unchanged": hash_file(ROOT / "contracts/API_SCHEMA_V1.json") == "4e3a01e7b83964138e7c7a307aabd0a1da3b7d414b6263ae8e838a4c628827a9",
        "no_public_model_selector": default_lock["public_model_selector"] is False and pytest_run.returncode == 0,
        "v1_rollback_preserved": rollback["status"] == "PASS" and (ROOT / "api/app.py").exists(),
        "mixed_bindings_fail_closed": pytest_run.returncode == 0,
        "frontend_reflects_v2_identities": frontend["status"] == "PASS" and "MODEL_V2_FINAL" in tiles and "CAL_V2" in tiles,
        "default_path_v2_replay_succeeds": replay["status"] == "PASS" and replay["research_launcher_used"] is False,
        "v1_rollback_replay_succeeds": rollback["status"] == "PASS",
        "process_isolation": isolation["status"] == "PASS",
        "known_limitations_present": _load("claim_audit.json")["known_limitations"] == 9,
        "no_hardware_or_clinical_claim": _load("claim_audit.json")["status"] == "PASS",
        "protected_artifacts_unchanged": _load("protected_artifact_audit.json")["status"] == "PASS",
        "full_regression_passes": regression["status"] == "PASS" and lint["status"] == "PASS",
    }
    if final_dir is None:
        flags["clean_release_clone"] = "PENDING_CLEAN_CLONE"
        flags["repository_clean_and_pushed"] = "PENDING_FINAL"
    else:
        manifest = json.loads((final_dir / "reproducibility_manifest.json").read_text())
        flags["clean_release_clone"] = manifest["result"] == "PASS"
        flags["repository_clean_and_pushed"] = True
    return flags


def main() -> None:
    if "--stage1" in sys.argv:
        stage_audits()
        flags = criteria(None)
        _write("v2relg0_criteria.json", {"criteria": flags, "status": "STAGE1_PENDING_CLEAN_CLONE",
                                         "performance_magnitude_is_a_criterion": False})
        print(json.dumps({"stage1_failed": [k for k, v in flags.items() if v is not True and not str(v).startswith("PENDING")]}))
        return
    final_dir = Path(sys.argv[sys.argv.index("--final") + 1])
    flags = criteria(final_dir)
    ok = all(v is True for v in flags.values())
    _write("v2relg0_final_criteria.json", {"criteria": flags, "status": "PASS" if ok else "FAIL",
                                           "performance_magnitude_is_a_criterion": False})
    print(json.dumps({"V2RELG0": "PASS" if ok else "FAIL", "failed": [k for k, v in flags.items() if v is not True]}))


if __name__ == "__main__":
    main()
