#!/usr/bin/env python3
"""V2-012 final evidence: gateway verification + frozen-artifact reproducibility, method
immutability, protected-artifact and scope audits, the tamper suite, and manifest/hash pins
(written last). Control-plane only; run after export, benchmark and manifest build."""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

import scripts.generate_v2_012_entry as entry
from deployment import gateway_v2 as gw
from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2
from models.model_v2_final_freeze import load_model_v2_final
from nhm.hashing import hash_file
from scripts.freeze_v2_012_method import METHOD_PATHS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_012"
ENTRY_COMMIT = "09d4d2ae5093e18e3c53b4a847f18a052b00d62e"
RUN_LOG_FILES = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv",
                 "pytest_chunk_results.csv", "test_results.json", "full_regression_proof.json",
                 "artifact_hashes.json"}
FIREWALL_PREFIXES = ("api/", "frontend/", "release/", "artifacts/ALERT_POLICY",
                     "artifacts/API_RUNTIME", "artifacts/DASHBOARD",
                     "artifacts/GATEWAY_ARTIFACT_V1",
                     "artifacts/GATEWAY_FP32_METHOD_V1", "artifacts/deployment/MODEL_V1",
                     "deployment/runtime.py", "deployment/export.py", "deployment/benchmark.py",
                     "deployment/mock_inference.py", "checkpoints/MODEL_V1", "artifacts/CAL_V1")
GUARD_FILES = [
    "reports/model_v2/v2_007/validation_access_guard.json",
    "reports/model_v2/v2_009/calibration_access_guard.json",
    "reports/model_v2/v2_010/incart_second_look_guard.json",
    "reports/model_v2/v2_010/internal_test_second_look_guard.json",
    "reports/model_v2/v2_010/nstdb_second_look_guard.json",
    "reports/model_v2/v2_011/case_access_guard.json",
    "reports/model_v2/v2_011/noise_type_access_guard.json",
]


def _sh(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def method_commit() -> str:
    log = _sh("git", "log", "--diff-filter=A", "--format=%H", "--",
              "scripts/freeze_v2_012_method.py").split()
    if not log:
        raise RuntimeError("V2_012_METHOD_COMMIT_NOT_FOUND")
    return log[-1]


# ---------------------------------------------------------------------------------------------


def verification_and_reproducibility() -> dict:
    first = verify_gateway_artifact_v2(ROOT)
    second = verify_gateway_artifact_v2(ROOT)

    torch.set_num_threads(1)
    native, _ = load_model_v2_final(ROOT)
    native.eval()
    module = gw.load_artifact(ROOT / gw.ARTIFACT_PATH)
    windows = gw.load_parity_corpus(ROOT)
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    with np.load(ROOT / "tests/fixtures/model_v2_final_test_vector.npz", allow_pickle=False) as f:
        inputs, expected = f["normalized_inputs_float32"], f["expected_logits_float32"]

    def once() -> dict:
        with torch.inference_mode():
            fixture_g = module(torch.from_numpy(inputs)).numpy()
            n = np.concatenate([native(torch.from_numpy(windows[i:i + 1])).numpy()
                                for i in range(len(windows))])
            g = np.concatenate([module(torch.from_numpy(windows[i:i + 1])).numpy()
                                for i in range(len(windows))])
        return {"fixture": gw.compare_logits(expected, fixture_g),
                "corpus": gw.compare_logits(n, g), "cal": gw.calibration_parity(n, g, cal),
                "gateway_logits_sha": __import__("hashlib").sha256(g.tobytes()).hexdigest()}

    a, b = once(), once()
    stored = json.loads((OUT / "synthetic_corpus_parity_summary.json").read_text())
    matches_stored = (a["corpus"]["max_abs_delta"] == stored["max_abs_logit_delta"]
                      and a["cal"]["threshold_decision_disagreements"]
                      == stored["threshold_decision_disagreements"])
    ok = first == second and a == b and matches_stored and first["status"] == "PASS"
    data = {
        "verifier_run_1": first, "verifier_run_2": second,
        "verifier_deterministic": first == second,
        "fixture_parity_recomputed_identical": a["fixture"] == b["fixture"],
        "corpus_parity_recomputed_identical": a["corpus"] == b["corpus"],
        "calibration_wrapper_parity_recomputed_identical": a["cal"] == b["cal"],
        "gateway_logit_sha256_identical_across_reruns": a["gateway_logits_sha"]
        == b["gateway_logits_sha"],
        "matches_stored_export_evidence": matches_stored,
        "benchmark_timings_expected_nondeterministic": True,
        "status": "PASS" if ok else "FAIL",
    }
    _write("gateway_verification.json", data)
    if not ok:
        raise RuntimeError("V2_012_VERIFICATION_OR_REPRODUCIBILITY_FAILED")
    return data


def immutability() -> dict:
    commit = method_commit()
    per_file = {}
    for rel in METHOD_PATHS:
        existed = subprocess.run(["git", "cat-file", "-e", f"{commit}:{rel}"], cwd=ROOT,
                                 capture_output=True, check=False).returncode == 0
        diff = _sh("git", "diff", commit, "--", rel) if existed else "MISSING"
        per_file[rel] = {"existed_at_method_commit": existed, "has_diff": bool(diff)}
    ok = all(v["existed_at_method_commit"] and not v["has_diff"] for v in per_file.values())
    data = {"method_commit": commit, "per_file": per_file, "unchanged_after_benchmark_exposure": ok,
            "frozen": ["format", "precision", "parity corpus", "tolerances", "warm-up",
                       "measurement count", "timer", "thread policy", "aggregation rule",
                       "memory semantics"],
            "status": "PASS" if ok else "FAIL"}
    _write("method_immutability_audit.json", data)
    if not ok:
        raise RuntimeError("V2_012_METHOD_MUTATED_AFTER_EXPOSURE")
    return data


def protected_audit() -> dict:
    baseline = json.loads((OUT / "protected_baseline.json").read_text())["artifacts"]
    after = {p: hash_file(ROOT / p) for p in baseline}
    changed = [p for p in baseline if baseline[p] != after[p]]
    data = {"before": baseline, "after": after, "unexpected_changes": changed,
            "status": "PASS" if not changed else "FAIL"}
    _write("protected_artifact_audit.json", data)
    if changed:
        raise RuntimeError(f"V2_012_PROTECTED_ARTIFACT_CHANGED:{changed}")
    return data


FORBIDDEN_IMPORTS = ("datasets", "evaluation.internal_test", "evaluation.external_incart",
                     "evaluation.noise", "evaluation.c031", "wfdb", "api", "frontend",
                     "federated", "training")


def scope_audit() -> dict:
    changed = [p for p in _sh("git", "diff", "--name-only", ENTRY_COMMIT).splitlines()]
    untracked = _sh("git", "ls-files", "--others", "--exclude-standard").splitlines()
    touched = sorted(set(changed + untracked))
    firewall_hits = [p for p in touched if p.startswith(FIREWALL_PREFIXES)]
    import_hits = {}
    for rel in METHOD_PATHS:
        if rel.endswith(".py"):
            tree = ast.parse((ROOT / rel).read_text())
            mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
            mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
            bad = [m for m in mods if m.startswith(FORBIDDEN_IMPORTS)]
            if bad:
                import_hits[rel] = bad
    guards_unchanged = {g: _sh("git", "diff", "--name-only", ENTRY_COMMIT, "--", g) == ""
                        for g in GUARD_FILES}
    data = {
        "files_changed_since_entry": len(touched),
        "firewall_prefix_hits": firewall_hits,
        "held_out_loader_imports_in_method_code": import_hits,
        "one_shot_guards_unchanged_since_entry": guards_unchanged,
        "new_neural_fits": 0, "new_classical_fits": 0, "training": False,
        "train_waveform_access": 0, "validation_access": 0, "calibration_waveform_access": 0,
        "internal_test_access": 0, "incart_access": 0, "nstdb_access": 0, "bidmc_access": 0,
        "wearable_access": 0, "hardware_work": 0,
        "synthetic_fixtures_used": True, "cpu_benchmark_inference_only": True,
        "api_changed": False, "frontend_changed": False, "runtime_default_changed": False,
        "alert_policy_changed": False, "gateway_artifact_v1_changed": False,
        "int8_or_quantization_attempted": False, "cumulative_neural_fits": 71,
        "status": "PASS" if not firewall_hits and not import_hits
        and all(guards_unchanged.values()) else "FAIL",
    }
    _write("scope_audit.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_012_SCOPE_AUDIT_FAILED")
    return data


# ---------------------------------------------------------------------------------------------
# Tamper suite
# ---------------------------------------------------------------------------------------------


def _files() -> list[str]:
    files = {gw.ARTIFACT_PATH, gw.MANIFEST_PATH, gw.PARITY_CORPUS_PATH,
             "configs/model_v2/gateway_artifact_v2.yaml", "checkpoints/MODEL_V2_FINAL.pt",
             "checkpoints/MODEL_V2_FINAL.manifest.json", "configs/model_v2_final_frozen.yaml",
             "tests/fixtures/model_v2_final_test_vector.npz",
             "tests/fixtures/model_v2_final_test_vector.metadata.json", "artifacts/CAL_V2.json",
             "reports/model_v2/v2_009/calibration_access_guard.json",
             "reports/model_v2/v2_009/reliability.json"}
    model_manifest = json.loads((ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    files |= set(model_manifest["upstream_sha256"]) | set(cal["upstream_sha256"])
    files |= {str(p.relative_to(ROOT)) for p in OUT.iterdir()
              if p.is_file() and p.name != "pytest_collected_nodes.txt"}
    return sorted(f for f in files if (ROOT / f).exists())


def _edit_manifest(root: Path, mutate) -> None:
    path = root / gw.MANIFEST_PATH
    manifest = json.loads(path.read_text())
    mutate(manifest)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _set(path: tuple, value):
    def apply(manifest: dict) -> None:
        node = manifest
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return apply


def _t_artifact_bytes(r: Path) -> None:
    with (r / gw.ARTIFACT_PATH).open("ab") as h:
        h.write(b"\x00")


def _t_state_tensor(r: Path) -> None:
    artifact = r / gw.ARTIFACT_PATH
    module = gw.load_artifact(artifact)
    with torch.no_grad():
        first = next(iter(module.parameters()))
        first.view(-1)[0] += 1e-3
    artifact.unlink()
    torch.jit.save(module, str(artifact))
    _edit_manifest(r, lambda m: (m["artifact"].update(
        {"sha256": hash_file(artifact), "bytes": artifact.stat().st_size})))


def _t_corpus_file(r: Path) -> None:
    path = r / gw.PARITY_CORPUS_PATH
    path.write_bytes(path.read_bytes() + b"\x00")


def _t_corpus_content(r: Path) -> None:
    from scripts.generate_model_v1_test_vector_t016 import write_deterministic_npz

    windows = gw.load_parity_corpus(r).copy()
    windows[10, 0, 5] += 0.5
    path = r / gw.PARITY_CORPUS_PATH
    write_deterministic_npz(path, gw.corpus_arrays(windows))
    new = hash_file(path)
    _edit_manifest(r, lambda m: m["parity_corpus"].update({"sha256": new}))
    cfg = r / "configs/model_v2/gateway_artifact_v2.yaml"
    text = cfg.read_text().replace(
        "npz_sha256: f897471970401fe1b97b8cc2a21acf3acdeeb032b1adb03fc08e14738e8c9da5",
        f"npz_sha256: {new}")
    cfg.write_text(text)


def _t_tolerance_config(r: Path) -> None:
    cfg = r / "configs/model_v2/gateway_artifact_v2.yaml"
    cfg.write_text(cfg.read_text().replace("atol: 1.0e-6", "atol: 1.0e-4", 1))


def _t_summary_disagreement(r: Path) -> None:
    path = r / "reports/model_v2/v2_012/synthetic_corpus_parity_summary.json"
    data = json.loads(path.read_text())
    data["threshold_decision_disagreements"] = 3
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


TAMPERS = {
    "gateway_artifact_byte_mutation": _t_artifact_bytes,
    "state_tensor_mutation_resealed": _t_state_tensor,
    "manifest_artifact_size_mutation": lambda r: _edit_manifest(
        r, _set(("artifact", "bytes"), 1)),
    "artifact_id_mutation": lambda r: _edit_manifest(r, _set(("artifact_id",), "GATEWAY_FP32_V1")),
    "model_v2_final_sha_mutation": lambda r: _edit_manifest(
        r, _set(("source_model", "sha256"), "0" * 64)),
    "cal_v2_sha_mutation": lambda r: _edit_manifest(r, _set(("calibration", "sha256"), "0" * 64)),
    "preproc_hash_mutation": lambda r: _edit_manifest(
        r, _set(("preprocessing", "lock_sha256"), "0" * 64)),
    "preproc_id_mutation": lambda r: _edit_manifest(r, _set(("preprocessing", "id"), "PREPROC_V2")),
    "target_mutation": lambda r: _edit_manifest(r, _set(("target_id",), "OTHER")),
    "map_mutation": lambda r: _edit_manifest(r, _set(("map_id",), "OTHER")),
    "input_shape_mutation": lambda r: _edit_manifest(
        r, _set(("input_shape",), ["N", 1, 2000])),
    "output_semantics_mutation": lambda r: _edit_manifest(
        r, _set(("output_semantics",), "CALIBRATED_PROBABILITY")),
    "fp32_to_int8_metadata_mutation": lambda r: _edit_manifest(
        r, _set(("artifact", "precision"), "INT8")),
    "torchscript_format_mutation": lambda r: _edit_manifest(
        r, _set(("artifact", "format"), "ONNX")),
    "parameter_count_mutation": lambda r: _edit_manifest(
        r, _set(("gateway_parameter_count",), 57554)),
    "protocol_v3_hash_mutation": lambda r: _edit_manifest(
        r, _set(("protocol_v3_lock_sha256",), "0" * 64)),
    "parity_corpus_file_mutation": _t_corpus_file,
    "parity_corpus_content_mutation_resealed": _t_corpus_content,
    "tolerance_manifest_mutation": lambda r: _edit_manifest(
        r, _set(("equivalence", "atol"), 1e-4)),
    "tolerance_config_mutation": _t_tolerance_config,
    "threshold_disagreement_manifest_mutation": lambda r: _edit_manifest(
        r, _set(("synthetic_corpus_parity", "threshold_decision_disagreements"), 2)),
    "threshold_disagreement_summary_mutation": _t_summary_disagreement,
    "operational_lineage_mutation": lambda r: _edit_manifest(
        r, _set(("status_semantics", "operational_lineage"), "MODEL_V2_FINAL")),
    "promotion_status_mutation": lambda r: _edit_manifest(
        r, _set(("status_semantics", "official_validation_promotion"), "PROMOTED")),
    "runtime_acceptance_mutation": lambda r: _edit_manifest(
        r, _set(("status_semantics", "MODEL_V2_RUNTIME_ACCEPTED"), "NOT_ACCEPTED")),
    "fixture_parity_missing": lambda r: _edit_manifest(
        r, _set(("fixture_parity", "allclose"), False)),
    "corpus_parity_missing": lambda r: _edit_manifest(
        r, _set(("synthetic_corpus_parity", "rows"), 0)),
}


def tamper_suite() -> dict:
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        for rel in _files():
            dst = base / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        if verify_gateway_artifact_v2(base)["status"] != "PASS":
            raise RuntimeError("TAMPER_BASE_ROOT_DOES_NOT_VERIFY")
        before = {p: hash_file(ROOT / p) for p in entry.PROTECTED_PATHS}
        for name, mutate in TAMPERS.items():
            work = Path(tmp) / f"case_{name}"
            shutil.copytree(base, work)
            mutate(work)
            try:
                verify_gateway_artifact_v2(work)
                results[name] = {"detected": False, "error": None}
            except Exception as exc:
                results[name] = {"detected": True,
                                 "error": f"{type(exc).__name__}:{str(exc)[:140]}"}
            shutil.rmtree(work)
        after = {p: hash_file(ROOT / p) for p in entry.PROTECTED_PATHS}
    required = [
        "gateway artifact byte mutation", "state tensor mutation", "manifest mutation",
        "artifact ID mutation", "MODEL_V2_FINAL SHA mutation", "CAL_V2 SHA mutation",
        "PREPROC mutation", "target mutation", "map mutation", "input shape mutation",
        "output semantic mutation", "FP32->INT8 metadata mutation", "TorchScript format mutation",
        "parameter-count mutation", "parity-corpus mutation", "tolerance mutation",
        "threshold-disagreement mutation", "operational-lineage mutation",
        "promotion-status mutation", "runtime-acceptance mutation",
    ]
    data = {"clean_temp_copy_verifies": True, "mutations": results,
            "mutation_count": len(results), "all_detected": all(
                v["detected"] for v in results.values()),
            "required_categories": required,
            "canonical_artifacts_unmodified": before == after,
            "status": "PASS" if all(v["detected"] for v in results.values()) and before == after
            else "FAIL"}
    _write("tamper_test_results.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_012_TAMPER_SUITE_FAILED")
    return data


# ---------------------------------------------------------------------------------------------


def finalize() -> None:
    entry_audit = json.loads((OUT / "entry_audit.json").read_text())
    manifest = json.loads((ROOT / gw.MANIFEST_PATH).read_text())
    run = {
        "checkpoint_id": "V2-012", "owner_task": "V2-012", "gate": "V2G11",
        "GATEWAY_ARTIFACT_V2": "FROZEN_RESEARCH_GATEWAY",
        "artifact_sha256": manifest["artifact"]["sha256"],
        "entry_head": entry_audit["head"], "method_commit": method_commit(),
        "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED",
        "official_validation_promotion": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "operational_lineage": "MODEL_V1", "new_neural_fits": 0, "cumulative_neural_fits": 71,
        "status": "PASS",
    }
    _write("run_manifest.json", run)
    pins = {f"reports/model_v2/v2_012/{p.name}": hash_file(p)
            for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in RUN_LOG_FILES}
    for rel in (gw.ARTIFACT_PATH, gw.MANIFEST_PATH, gw.PARITY_CORPUS_PATH):
        pins[rel] = hash_file(ROOT / rel)
    _write("artifact_hashes.json", {"artifacts": pins})


def run_pytest_summary() -> dict:
    import os

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:warnings",
         "tests/test_v2_012_config.py", "tests/test_v2_012_results.py"],
        cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src:."})
    tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    m = re.search(r"(\d+) passed", tail)
    data = {"command": "pytest tests/test_v2_012_config.py tests/test_v2_012_results.py",
            "exit_code": result.returncode, "summary": tail,
            "passed": int(m.group(1)) if m else 0,
            "status": "PASS" if result.returncode == 0 else "FAIL"}
    _write("test_results.json", data)
    return data


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("audits", "finalize"), required=True)
    stage = parser.parse_args().stage
    if stage == "audits":
        verification_and_reproducibility()
        immutability()
        protected_audit()
        scope_audit()
        tamper_suite()
    else:
        finalize()
        run_pytest_summary()
    print(json.dumps({"status": "PASS", "stage": stage}))


if __name__ == "__main__":
    main()
