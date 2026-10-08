# ruff: noqa: E501
"""Gates A-F for NHM-FINAL-SHOWCASE-001 and (with --lock) the lock's byte bindings.   python -m scripts.verify_final_showcase [--lock] [--report PATH]
Gates only read committed evidence; they never train, tune or re-evaluate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from final_showcase import evaluate as ev
from final_showcase import research
from scripts.freeze_observatory_v1 import PROTECTED

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "aa36f53b26834f88e6ac41482e7190f1fa2086d8"
METHOD_COMMIT = "6d79274c0ca4f159d210c69411a68238be3d2112"
LOCK = ROOT / "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"
CANONICAL = "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def gate_a() -> dict:
    live = research.live_link_summary()
    p = live["parity"]
    return {"completed": live["phase"] == "COMPLETED", "inference_200_all_windows": live["monitoring"]["inference_http_statuses"] == {"200": p["windows_monitored"]}, "records_identical": p["records_identical"],
            "windows_identical": p["window_samples_and_timestamps_identical"], "dataset_identity_observed": p["dataset_identical_to_canonical"], "candidate_separate_id": bool(live["candidate_ids"]),
            "candidate_digest_observed_equal_canonical": live["candidate_digest_equals_canonical"], "blocked_state_tested": "test_blocked_route_never_starts_a_federation_run" in (ROOT / "tests/test_final_showcase_live_link.py").read_text(),
            "disabled_mode_digest_tested": "test_disabled_mode_reproduces_the_canonical_candidate_digest" in (ROOT / "tests/test_final_showcase_live_link.py").read_text()}


def gate_b() -> dict:
    ev.verify_method_freeze(METHOD_COMMIT)
    r = json.loads((ROOT / research.SYNTH).read_text())
    prog = json.loads((ROOT / "reports/model_v2/v2_fl_005/federation_run.json").read_text())["state_progression"]
    return {"protocol_matches_method_freeze_commit": True, "results_after_method_freeze": True, "separation_zero": all(v == 0 for k, v in r["separation"].items() if k.endswith("overlap")),
            "digests_match_frozen_progression": [r["state_digests"][k] for k in ev.STATE_KEYS] == [prog[str(i)]["sha256"] for i in range(4)], "holdout_windows": r["holdout_windows"],
            "all_four_states_evaluated": sorted(r["results"]) == sorted(ev.STATE_KEYS), "boundary_label": r["boundary_label"].startswith("SYNTHETIC ENGINEERING-EVENT CLASSIFICATION"),
            "undefined_reported_as_null": r["results"]["round_0"]["pooled"]["precision"] is None, "negative_tests_present": (ROOT / "tests/test_final_showcase_eval.py").exists()}


def gate_c() -> dict:
    b = research.bundle()
    rows = {r["dataset"]: r for r in b["comparability"]["rows"]}
    return {"models": len(b["models"]), "round_logs_50_rounds": all(x["rounds"] == 50 for x in b["round_logs"].values()),
            "targets": [round(rows["INTERNAL_TEST"]["centralized_V2_AUPRC"], 6), round(rows["INTERNAL_TEST"]["federated_V2_FedAvg_IID_AUPRC"], 6), round(rows["INCART"]["centralized_V2_AUPRC"], 6), round(rows["INCART"]["federated_V2_FedAvg_IID_AUPRC"], 6)] == [0.999473, 0.998931, 0.970004, 0.976604],
            "no_superiority_verdict": "NO SUPERIORITY" in b["comparability"]["verdict"], "four_interpretations": len(b["comparability"]["interpretations"]) == 4}


def gate_d() -> dict:
    m = json.loads((ROOT / "reports/final_showcase/publication/export_manifest.json").read_text())
    files = [e for item in (*m["figures"].values(), *m["tables"].values()) for e in item.values()]
    return {"figures": len(m["figures"]), "tables": len(m["tables"]), "all_hashes_match": all(sha(ROOT / e["path"]) == e["sha256"] for e in files)}


def gate_e() -> dict:
    out = {}
    for name in ("chrome_stable", "chrome_for_testing"):
        d = json.loads((ROOT / f"reports/final_showcase/browser/smoke_{name}/final_showcase_smoke.json").read_text())
        out[name] = {"passed": d["passed"], "errors": len(d["errors"]), "external_hosts": len(d["externalHosts"]), "live_completed": "phase COMPLETED" in d["live"]["phase"]}
    out["not_tested"] = ["firefox (not installed)", "webkit/safari (remote automation disabled)"]
    return out


def gate_f() -> dict:
    need = ["demo_runbook.md", "manuscript_material.md", "results_traceability.md", "results_traceability.csv", "viva_question_bank.md", "implementation_map.md"]
    rows = (ROOT / "docs/final_showcase/results_traceability.csv").read_text().splitlines()[1:]
    return {"documents_present": all((ROOT / "docs/final_showcase" / n).exists() for n in need), "recorded_run_present": (ROOT / "reports/final_showcase/recorded_run/recorded_verified_run.json").exists(),
            "traceability_rows": len(rows), "reference_required_markers": (ROOT / "docs/final_showcase/manuscript_material.md").read_text().count("REFERENCE_REQUIRED")}


def protected() -> dict:
    diff = [p for p in subprocess.run(["git", "diff", "--name-only", ENTRY, "--", *PROTECTED, ":(exclude)artifacts/capstone/*.amendment_*.json"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n") if p]
    return {"protected_surface_diff_against_entry": diff, "canonical_candidate_digest_in_frozen_progression": json.loads((ROOT / "reports/model_v2/v2_fl_005/federation_run.json").read_text())["state_progression"]["3"]["sha256"] == CANONICAL}


def verify_lock() -> dict:
    lock = json.loads(LOCK.read_text())
    for path, digest in lock["bound_files"].items():
        if sha(ROOT / path) != digest:
            raise RuntimeError(f"FINAL_SHOWCASE_TAMPER:{path}")
    from scripts import verify_obs_diag_001

    verify_obs_diag_001.verify()
    return {"bound_files": len(lock["bound_files"]), "status": lock["status"], "obs_diag_chain_verified": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args()
    gates = {"A_live_monitored_site00": gate_a(), "B_synthetic_evaluation": gate_b(), "C_scientific_outcomes": gate_c(), "D_exports": gate_d(), "E_browser": gate_e(), "F_documentation": gate_f(), "protected_surface": protected()}
    ok = (all(v is True or not isinstance(v, bool) for v in gates["A_live_monitored_site00"].values()) and all(v is True for k, v in gates["B_synthetic_evaluation"].items() if isinstance(v, bool))
          and gates["C_scientific_outcomes"]["targets"] and gates["C_scientific_outcomes"]["round_logs_50_rounds"] and gates["D_exports"]["all_hashes_match"]
          and all(gates["E_browser"][b]["passed"] and gates["E_browser"][b]["live_completed"] for b in ("chrome_stable", "chrome_for_testing")) and gates["F_documentation"]["documents_present"]
          and not gates["protected_surface"]["protected_surface_diff_against_entry"] and gates["protected_surface"]["canonical_candidate_digest_in_frozen_progression"])
    out = {"status": "PASS" if ok else "FAIL", "gates": gates}
    if a.lock:
        out["lock"] = verify_lock()
    if a.report:
        Path(a.report).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"status": out["status"], **({"lock": out["lock"]} if a.lock else {})}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
