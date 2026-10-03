#!/usr/bin/env python3
"""V2-013 Sections 1-3/5: entry state, V2-012 carry-forward audit (including the three
control-plane test edits and the non-byte-identical re-export disclosure), the pre-implementation
protected-artifact baseline/verification, and the runtime-architecture audit of the CURRENT V1
software path. No model scoring, no data access, nothing is regenerated."""

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

from evaluation.calibration import verify_cal_v1
from models.cal_v2_verify import verify_cal_v2
from models.explainability_v2_verify import verify_explainability_v2
from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2
from models.model_freeze import verify_frozen_model_v1
from models.model_v2_final_freeze import verify_model_v2_final
from nhm.hashing import hash_file
from preprocessing.freeze import verify_preproc_freeze
from scripts.verify_api_runtime_v1_1_c032 import verify as verify_api_runtime_v1_1
from scripts.verify_e2e_replay_v1_2_c032 import verify as verify_e2e_v1_2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_013"
EXPECTED_ENTRY = "40e127308b50bb4d5943826639d467203b9b4b29"
V2_012_METHOD = "4a3c5384e0446a9e5753d34a8f751e5d0b4b938e"
V2_012_RESULT = "40e127308b50bb4d5943826639d467203b9b4b29"
GATEWAY_SHA = "25ec0eed4dc9e2b4603229243d538ee58d33bcd8f8fe88efac681e94eb06b11f"
TESTS_EDITED_IN_V2_012 = [
    "tests/test_model_v2_control_plane.py",
    "tests/test_c_v2_pre006_control.py",
    "tests/test_v2_011_results.py",
]


def _sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          check=False).stdout.strip()


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _status(path: str, key: str, ident: str) -> str:
    return next(r["status"] for r in _rows(path) if r[key] == ident)


def entry_state() -> dict:
    task = "manifests/model_v2/task_registry_v1.csv"
    gate = "manifests/model_v2/gate_registry_v1.csv"
    comp = "manifests/model_v2/component_registry_v1.csv"
    registry = {
        "V2-012": _status(task, "task_id", "V2-012"), "V2G11": _status(gate, "gate_id", "V2G11"),
        "V2-013": _status(task, "task_id", "V2-013"), "V2G12": _status(gate, "gate_id", "V2G12"),
        "GATEWAY_ARTIFACT_V2": _status(comp, "component_id", "GATEWAY_ARTIFACT_V2"),
        "MODEL_V2_FINAL": _status(comp, "component_id", "MODEL_V2_FINAL"),
        "CAL_V2": _status(comp, "component_id", "CAL_V2"),
        "EXPLAINABILITY_V2": _status(comp, "component_id", "EXPLAINABILITY_V2"),
        "MODEL_V2_RUNTIME_ACCEPTED": _status(comp, "component_id", "MODEL_V2_RUNTIME_ACCEPTED"),
        "API_RUNTIME_V2": _status(comp, "component_id", "API_RUNTIME_V2"),
    }
    expected = {
        "V2-012": "PASS", "V2G11": "PASS", "V2-013": "NOT_STARTED", "V2G12": "NOT_STARTED",
        "GATEWAY_ARTIFACT_V2": "FROZEN_RESEARCH_GATEWAY", "MODEL_V2_FINAL": "FROZEN",
        "CAL_V2": "FROZEN", "EXPLAINABILITY_V2": "FROZEN_EXPLAINABILITY",
        "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED", "API_RUNTIME_V2": "NOT_STARTED",
    }
    promo = json.loads((ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
    data = {
        "head": _sh("git", "rev-parse", "HEAD"),
        "origin_main": _sh("git", "rev-parse", "origin/main"),
        "expected_entry_sha": EXPECTED_ENTRY, "registry": registry,
        "official_promotion": promo["promotion_decision"],
        "operational_lineage": promo["operational_lineage"],
        "cumulative_v2_neural_fits": 71, "ci_policy": "DEFERRED_NOT_QUERIED",
    }
    ok = (data["head"] == data["origin_main"] == EXPECTED_ENTRY and registry == expected
          and data["official_promotion"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
          and data["operational_lineage"] == "MODEL_V1")
    data["status"] = "PASS" if ok else "FAIL"
    _write("entry_state.json", data)
    if not ok:
        raise RuntimeError("V2_013_ENTRY_STATE_MISMATCH")
    return data


# --- Section 2B: classify every changed line of the three V2-012 test edits ------------------

ALLOWED_ADDED = [
    r'^\s*"V2-012",?\s*$', r'^\s*"V2G11",?\s*$', r'^\s*"V2-010", "V2-011", "V2-012",?\s*$',
    r'^\s*"V2G10", "V2G11",?\s*$', r'^\s*#', r'^\s*if task_id in \{.*"V2-012"\}:\s*$',
    r'^\s*if gate_id in \{.*"V2G11"\}:\s*$',
    r'^\s*assert tasks\["V2-012"\]\["status"\] in \{"NOT_STARTED", "PASS"\}\s*$',
    r'^\s*assert gates\["V2G11"\]\["status"\] in \{"NOT_STARTED", "PASS"\}\s*$',
    r'^\s*assert tasks\["V2-013"\]\["status"\] == "NOT_STARTED"\s*$',
    r'^\s*assert comps\["GATEWAY_ARTIFACT_V2"\]\["status"\] in '
    r'\{"NOT_STARTED", "FROZEN_RESEARCH_GATEWAY"\}\s*$',
]
ALLOWED_REMOVED = [
    r'^\s*"V2-010", "V2-011",?\s*$', r'^\s*"V2G10",?\s*$', r'^\s*#',
    r'^\s*if task_id in \{.*\}:\s*$', r'^\s*if gate_id in \{.*\}:\s*$',
    r'^\s*expected_gates = \{.*\}?\s*$', r'^\s*\}\s*$', r'^\s*expected_tasks = \{\s*$',
    r'^\s*assert tasks\["V2-012"\]\["status"\] == "NOT_STARTED" and gates\["V2G11"\]'
    r'\["status"\] == "NOT_STARTED"\s*$',
    r'^\s*assert comps\["GATEWAY_ARTIFACT_V2"\]\["status"\] == "NOT_STARTED"\s*$',
]


def _classify(diff: str) -> dict:
    added, removed, unclassified = [], [], []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if line.startswith("+"):
            body = line[1:]
            added.append(body)
            if not any(re.match(p, body) for p in ALLOWED_ADDED):
                unclassified.append(("+", body))
        elif line.startswith("-"):
            body = line[1:]
            removed.append(body)
            if not any(re.match(p, body) for p in ALLOWED_REMOVED):
                unclassified.append(("-", body))
    return {"added": added, "removed": removed, "unclassified": unclassified}


def carry_forward() -> dict:
    ancestry = {
        "method_commit_is_ancestor_of_result": subprocess.run(
            ["git", "merge-base", "--is-ancestor", V2_012_METHOD, V2_012_RESULT],
            cwd=ROOT, check=False).returncode == 0,
    }
    # chronology: the artifact and every result file first appear only in the RESULT commit
    first_artifact_commit = _sh(
        "git", "log", "--diff-filter=A", "--format=%H", "--",
        "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts").split()[-1]
    first_benchmark_commit = _sh(
        "git", "log", "--diff-filter=A", "--format=%H", "--",
        "reports/model_v2/v2_012/benchmark_summary.json").split()[-1]
    method_has_artifact = subprocess.run(
        ["git", "cat-file", "-e", f"{V2_012_METHOD}:artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts"],
        cwd=ROOT, capture_output=True, check=False).returncode == 0
    chronology = {
        "artifact_first_added_in": first_artifact_commit,
        "benchmark_first_added_in": first_benchmark_commit,
        "artifact_present_at_method_commit": method_has_artifact,
        "method_precedes_export_and_results": first_artifact_commit == V2_012_RESULT
        and first_benchmark_commit == V2_012_RESULT and not method_has_artifact,
    }
    artifact = ROOT / "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts"
    manifest = json.loads(
        (ROOT / "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json").read_text())
    corpus = json.loads((ROOT / "reports/model_v2/v2_012/parity_corpus_manifest.json").read_text())
    verified = verify_gateway_artifact_v2(ROOT)
    artifact_facts = {
        "sha256": hash_file(artifact), "expected_sha256": GATEWAY_SHA,
        "bytes": artifact.stat().st_size, "expected_bytes": 294959,
        "parameter_count": manifest["gateway_parameter_count"], "expected_parameter_count": 57553,
        "verifier": verified["status"],
        "parity_corpus_sha256": corpus["npz_sha256"],
        "parity_corpus_status": corpus["status"],
        "canonical_artifact_regenerated_by_v2_013": False,
    }
    repro = json.loads((ROOT / "reports/model_v2/v2_012/artifact_reproducibility.json").read_text())
    differing = sorted({m for c in repro["comparisons"].values()
                        for m in c["differing_archive_members"]})
    disclosure = {
        "fresh_workspace_exports_semantically_equivalent": repro["semantic_reproducibility"],
        "state_values_identical": all(c["state_values_identical"]
                                      for c in repro["comparisons"].values()),
        "jit_semantics_identical": all(
            c["jit_code_identical"] for c in repro["comparisons"].values()),
        "logits_identical_across_exports": repro[
            "fixture_and_corpus_logits_identical_across_exports"],
        "archive_bytes_identical": repro["byte_reproducible"],
        "serialization_id_differed": ".data/serialization_id" in differing,
        "generated_archive_members_differed": [m for m in differing if m.startswith("code/")][:3],
        "differing_member_count": len(differing),
        "handling": "documented reproducibility characteristic; the committed canonical artifact "
        "SHA is authoritative; the artifact is NOT rewritten or re-exported; deferred to V2-014",
    }
    disclosure_ok = (disclosure["fresh_workspace_exports_semantically_equivalent"]
                     and not disclosure["archive_bytes_identical"]
                     and disclosure["serialization_id_differed"]
                     and bool(disclosure["generated_archive_members_differed"]))
    tests = {}
    for rel in TESTS_EDITED_IN_V2_012:
        diff = _sh("git", "diff", V2_012_METHOD, V2_012_RESULT, "--", rel)
        cls = _classify(diff)
        tests[rel] = {
            "added_lines": len(cls["added"]), "removed_lines": len(cls["removed"]),
            "unclassified_changes": cls["unclassified"], "narrow": not cls["unclassified"],
        }
    # semantic strictness probes on the CURRENT test sources
    cp = (ROOT / "tests/test_model_v2_control_plane.py").read_text()
    pre = (ROOT / "tests/test_c_v2_pre006_control.py").read_text()
    v11 = (ROOT / "tests/test_v2_011_results.py").read_text()
    start = v11.index("def test_registry_transition_and_preserved_statuses")
    edited_fn = v11[start:v11.index("\ndef test_artifact_hashes_self_consistent")]
    strict = {
        "control_plane_keeps_exact_set_equality": "assert passed_tasks == expected_tasks" in cp
        and "assert passed_gates == expected_gates" in cp,
        "control_plane_still_rejects_other_passes":
        "assert row[\"status\"] == \"NOT_STARTED\"" in cp,
        "pre006_future_states_limited_to_not_started_or_pass":
        "in {\"NOT_STARTED\", \"PASS\"}" in pre and "== \"NOT_STARTED\"" in pre,
        "v2_011_results_states_limited_to_forward_lifecycle":
        'in {"NOT_STARTED", "PASS"}' in v11 and '"FROZEN_RESEARCH_GATEWAY"' in v11
        and 'tasks["V2-013"]["status"] == "NOT_STARTED"' in v11,
        "no_arbitrary_strings_or_missing_rows_accepted": (
            "startswith" not in edited_fn and ".get(" not in edited_fn
            and "!=" not in edited_fn),
    }
    ok = (all(ancestry.values()) and chronology["method_precedes_export_and_results"]
          and artifact_facts["sha256"] == GATEWAY_SHA and artifact_facts["bytes"] == 294959
          and artifact_facts["parameter_count"] == 57553 and artifact_facts["verifier"] == "PASS"
          and corpus["status"] == "PASS" and disclosure_ok
          and all(t["narrow"] for t in tests.values()) and all(strict.values()))
    data = {"commits": {"method": V2_012_METHOD, "result": V2_012_RESULT}, "ancestry": ancestry,
            "chronology": chronology, "gateway_artifact": artifact_facts,
            "non_byte_identical_reexport_disclosure": disclosure,
            "control_plane_test_audit": {"files": tests, "semantic_strictness": strict},
            "status": "PASS" if ok else "FAIL"}
    _write("v2_012_carry_forward_audit.json", data)
    if not ok:
        raise RuntimeError("V2_013_V2_012_CARRY_FORWARD_FAILED")
    return data


def protected() -> dict:
    results = {
        "MODEL_V1": verify_frozen_model_v1(ROOT)["status"],
        "CAL_V1": verify_cal_v1(ROOT)["status"],
        "PREPROC_V1": verify_preproc_freeze(ROOT)["status"],
        "ALERT_POLICY_V1": __import__("fusion.episode_manager", fromlist=["x"]
                                      ).verify_alert_policy_lock(ROOT)["status"],
        "API_RUNTIME_V1_1": verify_api_runtime_v1_1()["status"],
        "E2E_REPLAY_SOFTWARE_V1_2": verify_e2e_v1_2()["status"],
        "MODEL_V2_FINAL": verify_model_v2_final(ROOT)["status"],
        "CAL_V2": verify_cal_v2(ROOT)["status"],
        "GATEWAY_ARTIFACT_V2": verify_gateway_artifact_v2(ROOT)["status"],
        "EXPLAINABILITY_V2": verify_explainability_v2(ROOT)["status"],
    }
    gateway_v1 = json.loads((ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json").read_text())
    results["GATEWAY_ARTIFACT_V1"] = "PASS" if all(
        hash_file(ROOT / rel) == digest for rel, digest in gateway_v1["bound_artifacts"].items()
    ) else "FAIL"
    results["MODEL_V2_RESEARCH_PROTOCOL_V3"] = (
        "PASS" if hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json")
        == "287aff4ff3fcf583524f06e6af51f23bd65949a75abef14cde80ff0936873db8" else "FAIL")
    for name, rel in (("V2_010_EVIDENCE", "reports/model_v2/v2_010/artifact_hashes.json"),
                      ("V2_011_EVIDENCE", "reports/model_v2/v2_011/artifact_hashes.json"),
                      ("V2_012_EVIDENCE", "reports/model_v2/v2_012/artifact_hashes.json")):
        pins = json.loads((ROOT / rel).read_text())["artifacts"]
        results[name] = "PASS" if all(hash_file(ROOT / p) == d for p, d in pins.items()) else "FAIL"
    return results


PROTECTED_PATHS = [
    "checkpoints/MODEL_V1.pt", "artifacts/CAL_V1.json", "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
    "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts", "manifests/preprocessing/PREPROC_V1.lock.json",
    "artifacts/ALERT_POLICY_V1.lock.json", "configs/alert_policy_v1.yaml",
    "artifacts/ECG_HR_CONTEXT_V2.lock.json", "artifacts/API_RUNTIME_V1_1.lock.json",
    "artifacts/API_RUNTIME_V1.lock.json", "artifacts/DASHBOARD_UI_V1_3.lock.json",
    "artifacts/DASHBOARD_UI_V1_2.lock.json", "artifacts/E2E_REPLAY_SOFTWARE_V1_2.lock.json",
    "api/app.py", "api/runtime.py", "api/schemas.py", "api/session.py",
    "fusion/episode_manager.py", "fusion/state_machine.py", "deployment/runtime.py",
    "contracts/API_SCHEMA_V1.json", "contracts/openapi_v1.json",
    "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json",
    "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.npz",
    "checkpoints/MODEL_V2_FINAL.pt", "checkpoints/MODEL_V2_FINAL.manifest.json",
    "configs/model_v2_final_frozen.yaml", "artifacts/CAL_V2.json",
    "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts",
    "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
    "tests/fixtures/gateway_parity_corpus_v2_v1.npz",
    "artifacts/EXPLAINABILITY_V2_METHOD.lock.json",
    "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
    "reports/model_v2/v2_010/runtime_acceptance_decision.json",
    "reports/model_v2/v2_011/explainability_v2.json",
    "reports/model_v2/v2_012/artifact_hashes.json", "reports/model_v2/v2_012/run_manifest.json",
    "manifests/splits/MITDB_SPLIT_V1.csv", "manifests/labels/AAMI_SVF_MAP_V1.yaml",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entry_state()
    carry_forward()
    audit = protected()
    data = {"verifiers": audit, "status": "PASS" if all(v == "PASS" for v in audit.values())
            else "FAIL"}
    _write("protected_artifact_audit.json", {**data, "baseline": {
        p: hash_file(ROOT / p) for p in PROTECTED_PATHS}})
    (OUT / "protected_baseline.json").write_text(json.dumps(
        {"artifacts": {p: hash_file(ROOT / p) for p in PROTECTED_PATHS}}, indent=2,
        sort_keys=True) + "\n")
    if data["status"] != "PASS":
        raise RuntimeError(f"V2_013_PROTECTED_VERIFICATION_FAILED:{audit}")
    print("V2-013 entry/carry-forward/protected audits complete")


if __name__ == "__main__":
    main()
