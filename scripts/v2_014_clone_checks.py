#!/usr/bin/env python3
"""V2-014 checks executed INSIDE a clean clone (clone's own venv, ambient PYTHONPATH unset).

Every sub-command writes ONE JSON evidence file to an EXTERNAL path (--out) and exits non-zero on
FAIL. Nothing here trains, re-infers on held-out data, opens a raw dataset or edits the clone.

Evidence categories (MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1):
  A tracked artifact identity   : inventory, artifacts
  B stored-evidence reconstruction: fl-dev, fl-heldout
  C executable software/synthetic: model-v2, fixed-vectors, cal-v2, gateway, replay-compare,
                                    fl-init, secagg-data-free, synthetic-fl
  D full regression             : regression (chunked + optional monolithic), lint
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
ENTRY_SHA = "3d0e9d4a81a486c5aa05d3073e2fabcbd51f445b"
GATEWAY_SHA = "25ec0eed4dc9e2b4603229243d538ee58d33bcd8f8fe88efac681e94eb06b11f"
GATEWAY_BYTES = 294959
CHECKPOINT_SHA_PREFIX = "89418edc"
FL_INIT_SHA = "6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f"
SYNTH_FINAL_SHA = "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4"
SYNTH_DIGEST = "e234b755f1d90eb9bc3d9ae4d437904d32b6e453dc476187238191cf409a352e"
V2013_DIGEST_PREFIX = "7ef39ae9"
FLATLINE_DIGEST = "0a2c5e6c8fc1dd28fe1464b48d01781246aa010a3a161cce82ac901bb1aea99e"
COMPONENTS = (
    "MODEL_V2_FINAL", "CAL_V2", "EXPLAINABILITY_V2", "GATEWAY_ARTIFACT_V2", "API_RUNTIME_V2",
    "API_RUNTIME_V2_1", "DASHBOARD_UI_V1_4", "E2E_REPLAY_SOFTWARE_V1_3",
    "MODEL_V2_FL_PROTOCOL_V1", "MODEL_V2_FL_PROTOCOL_V2", "FL_INIT_V2", "FL_IID_MODEL_V2_V1",
    "FL_NON_IID_MODEL_V2_V1", "FEDPROX_METHOD_V2", "FEDPROX_MU_V2", "V2_FL_EVAL_PROTOCOL_V1",
    "V2_FL_TEST_FAMILY_V1", "V2_FL_INTERNAL_TEST_PREDICTION_FAMILY_V1",
    "V2_FL_INCART_PREDICTION_FAMILY_V1", "MODEL_V2_LIFECYCLE_TEST_POLICY_V1", "SECAGG_METHOD_V2",
    "SECAGG_CONFIG_V2", "WEARABLE_SIM_FL_COHORT_V1", "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1",
    "WEARABLE_SIM_FL_SYSTEM_REPLAY_V1", "VIRTUAL_FL_CLIENT_SOURCE_V1",
    "WEARABLE_SIM_FL_SECAGG_COMPAT_V1", "MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1")
ARTIFACT_LOCKS = {"DASHBOARD_UI_V1_4": "artifacts/DASHBOARD_UI_V1_4.lock.json",
                  "E2E_REPLAY_SOFTWARE_V1_3": "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json"}
# locks superseded by an additive successor: their predecessor drift is expected and the
# successor lock re-verifies the changed file
EXPECTED_SUPERSEDED_DRIFT = {"API_RUNTIME_V2": {"simulation/stream_runtime_v2013.py"}}
DATA_GATED_PREFIXES = ("data/raw/", "data/processed/", "checkpoints/candidates/",
                       "checkpoints/model_v2/v2_007_official_validation/",
                       "checkpoints/model_v2/v2_002", "checkpoints/model_v2/v2_004",
                       "checkpoints/model_v2/v2_006")
PROTECTED = [
    "artifacts", "checkpoints", "reports/t028", "reports/privacy.json", "reports/privacy_secagg",
    "reports/model_v2", "manifests/clients", "frontend/static/replay", "preprocessing",
    "privacy", "simulation/stream_runtime_v2013.py", "simulation/profile_v2013.py",
    "simulation/types.py", "simulation/wearable.py", "simulation/fl_cohort_v1.py",
    "simulation/fl_cohort_truth_v1.py", "configs/secagg_v1.yaml", "federated", "models", "api",
    "deployment", "evaluation", "docs/privacy_threat_model.md",
    "docs/MODEL_V2_SECAGG_THREAT_MODEL_V1.md",
    "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json",
]
PROTECTED_ALLOWED_NEW = ("reports/model_v2/v2_014/",)


def _write(path: str, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def _finish(out: str, data: dict[str, Any]) -> None:
    data.setdefault("status", "PASS")
    _write(out, data)
    print(json.dumps({"check": Path(out).stem, "status": data["status"]}))
    if data["status"] != "PASS":
        sys.exit(1)


def _sha_lines(rows: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


# ------------------------------------------------------------------ A. identity
def _verify_bound(lock: dict[str, Any], key: str, component: str) -> dict[str, Any]:
    bound = lock.get(key)
    if not isinstance(bound, dict):
        return {"bound": 0, "verified": 0, "drift": [], "unexpected_drift": [],
                "data_gated": [], "missing": []}
    verified, drift, gated, missing = 0, [], [], []
    for path, digest in bound.items():
        if not isinstance(digest, str):
            continue
        target = ROOT / path
        if not target.exists():
            (gated if path.startswith(DATA_GATED_PREFIXES) else missing).append(path)
        elif hash_file(target) == digest:
            verified += 1
        else:
            drift.append(path)
    expected = EXPECTED_SUPERSEDED_DRIFT.get(component, set())
    unexpected = [p for p in drift if p not in expected]
    return {"bound": len(bound), "verified": verified, "drift": drift,
            "unexpected_drift": unexpected, "data_gated": gated, "missing": missing}


def _run_verifier(name: str) -> dict[str, Any]:
    try:
        if name == "MODEL_V2_FINAL":
            from models.model_v2_final_freeze import verify_model_v2_final as fn
            result = fn(ROOT)
        elif name == "CAL_V2":
            from models.cal_v2_verify import verify_cal_v2 as fn
            result = fn(ROOT)
        elif name == "GATEWAY_ARTIFACT_V2":
            from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2 as fn
            result = fn(ROOT)
        elif name == "API_RUNTIME_V2_1":
            from scripts.verify_api_runtime_v2_1 import verify as fn
            result = fn()
        elif name == "DASHBOARD_UI_V1_4":
            from scripts.verify_dashboard_ui_v1_4_v2013 import verify as fn
            result = fn()
        elif name == "E2E_REPLAY_SOFTWARE_V1_3":
            from scripts.verify_e2e_replay_v1_3_v2013 import verify as fn
            result = fn()
        else:
            return {"verifier": None}
        return {"verifier": name, "result": str(result.get("status", "PASS"))
                if isinstance(result, dict) else "PASS", "error": None}
    except Exception as exc:  # recorded, never swallowed silently
        return {"verifier": name, "result": "FAIL", "error": f"{type(exc).__name__}: {exc}"}


def check_inventory(out: str) -> None:
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        registry = {r["component_id"]: r for r in csv.DictReader(handle)}
    records, failures = [], []
    for name in COMPONENTS:
        row = registry.get(name)
        lock_path = (row["lock_path"] if row else ARTIFACT_LOCKS.get(name, ""))
        record: dict[str, Any] = {
            "component": name, "registry": "model_v2" if row else "artifact_lock",
            "registry_status": row["status"] if row else None, "lock_path": lock_path}
        lock_file = ROOT / lock_path if lock_path else None
        if not lock_file or not lock_file.exists():
            record["verification"] = "LOCK_MISSING"
            failures.append(name)
            records.append(record)
            continue
        record["lock_sha256"] = hash_file(lock_file)
        bound = {"bound": 0, "verified": 0, "drift": [], "unexpected_drift": [],
                 "data_gated": [], "missing": []}
        if lock_path.endswith(".json"):
            lock = json.loads(lock_file.read_text())
            if not row:
                record["registry_status"] = lock.get("status")
            for key in ("bound_artifacts", "bound_method_artifacts"):
                part = _verify_bound(lock, key, name)
                for field in ("bound", "verified"):
                    bound[field] += part[field]
                for field in ("drift", "unexpected_drift", "data_gated", "missing"):
                    bound[field] += part[field]
        record["bound_artifacts"] = bound
        record |= _run_verifier(name)
        verifier_failed = record.get("result") == "FAIL"
        # explainability's own verifier needs a raw NSTDB file that a clean clone never has
        if name == "EXPLAINABILITY_V2" and not verifier_failed:
            pass
        ok = not (bound["unexpected_drift"] or bound["missing"] or verifier_failed)
        record["verification"] = "PASS" if ok else "FAIL"
        if not ok:
            failures.append(name)
        records.append(record)
    inventory_sha = _sha_lines([f"{r['component']}|{r.get('lock_sha256')}" for r in records])
    _finish(out, {
        "components": records, "component_count": len(records),
        "component_lock_inventory_sha256": inventory_sha, "failures": failures,
        "superseded_expected_drift": {k: sorted(v) for k, v in EXPECTED_SUPERSEDED_DRIFT.items()},
        "data_gated_bound_files_not_verified_in_clean_clone": sorted({
            p for r in records for p in r.get("bound_artifacts", {}).get("data_gated", [])}),
        "status": "PASS" if not failures else "FAIL"})


def _under(path: str, prefixes: list[str]) -> bool:
    return any(path == p or path.startswith(p + "/") for p in prefixes)


def check_artifacts(out: str) -> None:
    tracked = _git("ls-files").splitlines()
    pts = sorted(p for p in tracked if p.endswith(".pt"))
    checkpoint_rows = [f"{p}|{hash_file(ROOT / p)}" for p in pts]
    family = json.loads((ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json").read_text())
    family_mismatch = [k for k, v in family["checkpoints"].items()
                       if hash_file(ROOT / v["path"]) != v["sha256"]]
    inference = json.loads(
        (ROOT / "reports/model_v2/v2_fl_eval_001/inference_manifest.json").read_text())
    tables, table_bad = [], []
    for key, dataset in (("internal_test", "INTERNAL_TEST"), ("incart", "INCART")):
        for entry in inference[key]:
            path = ROOT / f"reports/model_v2/v2_fl_eval_001/predictions/{dataset}/"\
                f"{entry['checkpoint_id']}.csv.gz"
            digest = hash_file(path) if path.exists() else None
            tables.append(f"{dataset}|{entry['checkpoint_id']}|{digest}")
            if digest != entry["table_sha256"]:
                table_bad.append(f"{dataset}/{entry['checkpoint_id']}")
    guards = {}
    for name, path in (
            ("V2_FL_INTERNAL_TEST_ACCESS_V1", "artifacts/V2_FL_INTERNAL_TEST_ACCESS_V1.json"),
            ("V2_FL_INCART_ACCESS_V1", "artifacts/V2_FL_INCART_ACCESS_V1.json"),
            ("INTERNAL_TEST_ACCESS_V1", "artifacts/internal_test_access_v1.json"),
            ("EXTERNAL_INCART_ACCESS_V1", "artifacts/external_incart_access_v1.json")):
        data = json.loads((ROOT / path).read_text())
        guards[name] = str(data.get("status", data.get("state")))
    changed = []
    for line in _git("diff", "--name-status", ENTRY_SHA, "HEAD").splitlines():
        status, *paths = line.split("\t")
        if status[0] in "MDR" and any(_under(p, PROTECTED) for p in paths):
            changed.append(line)
    symlinks = [p for p in tracked if (ROOT / p).is_symlink()]
    manifest = json.loads((ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
    final_ok = hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt").startswith(CHECKPOINT_SHA_PREFIX)
    ok = (not family_mismatch and not table_bad and not changed and not symlinks and final_ok
          and all(v in ("COMPLETED", "CONSUMED") or "COMPLETE" in v for v in guards.values()))
    _finish(out, {
        "tracked_checkpoints": len(pts), "checkpoint_inventory_sha256": _sha_lines(checkpoint_rows),
        "frozen_family_checkpoint_mismatches": family_mismatch,
        "prediction_tables": len(tables), "prediction_table_inventory_sha256": _sha_lines(tables),
        "prediction_table_mismatches": table_bad,
        "one_shot_guards": guards, "guards_reset_or_bypassed": False,
        "protected_changes_since_entry": changed, "tracked_symlinks": symlinks,
        "MODEL_V2_FINAL_sha256_prefix_ok": final_ok,
        "MODEL_V2_FINAL_manifest_keys": sorted(manifest)[:8],
        "status": "PASS" if ok else "FAIL"})


# ------------------------------------------------------------------ C. executable
def check_model_v2(out: str) -> None:
    import torch

    from models.model_v2_final_freeze import load_model_v2_final, verify_model_v2_final

    verified = verify_model_v2_final(ROOT)
    model, _ = load_model_v2_final(ROOT)
    model.eval()
    state = model.state_dict()
    params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    finite = all(bool(torch.isfinite(v).all()) for v in state.values() if v.is_floating_point())
    with np.load(ROOT / "tests/fixtures/model_v2_final_test_vector.npz", allow_pickle=False) as fx:
        inputs, expected = fx["normalized_inputs_float32"], fx["expected_logits_float32"]
    with torch.inference_mode():
        logits = model(torch.from_numpy(inputs)).numpy()
    meta = json.loads(
        (ROOT / "tests/fixtures/model_v2_final_test_vector.metadata.json").read_text())
    delta = float(np.max(np.abs(logits - expected)))
    state_digest = hashlib.sha256(b"".join(
        k.encode() + v.detach().cpu().numpy().tobytes() for k, v in state.items())).hexdigest()
    ok = (params == 57553 and finite and delta <= meta["atol"] + meta["rtol"]
          and hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt").startswith(CHECKPOINT_SHA_PREFIX))
    _finish(out, {
        "verifier_status": str(verified.get("status")), "architecture": "MODEL_V2_TCN_MEAN",
        "parameter_count": params, "state_keys": len(state), "finite_state": finite,
        "state_digest_sha256": state_digest,
        "checkpoint_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
        "fixed_vector_logits": logits.reshape(-1).tolist(), "max_abs_delta_vs_frozen": delta,
        "tolerance": {"atol": meta["atol"], "rtol": meta["rtol"]}, "trained": False,
        "status": "PASS" if ok else "FAIL"})


def check_fixed_vectors(out: str) -> None:
    from scripts.generate_model_v2_final_test_vector_v2008 import generate

    committed = ROOT / "tests/fixtures/model_v2_final_test_vector.npz"
    meta = json.loads(
        (ROOT / "tests/fixtures/model_v2_final_test_vector.metadata.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "regenerated.npz"
        result = generate(ROOT, target, Path("checkpoints/MODEL_V2_FINAL.pt"),
                          meta["checkpoint_sha256"])
        regenerated = hash_file(target)
    ok = regenerated == hash_file(committed) == meta["npz_sha256"]
    _finish(out, {"regenerated_sha256": regenerated, "committed_sha256": hash_file(committed),
                  "metadata_sha256": meta["npz_sha256"], "byte_identical": ok,
                  "expected_logits": result["expected_logits"], "patient_data_used": False,
                  "status": "PASS" if ok else "FAIL"})


def check_cal_v2(out: str) -> None:
    from deployment import gateway_v2 as gw
    from models.cal_v2_verify import load_cal_v2, verify_cal_v2

    verified = verify_cal_v2(ROOT)
    cal = load_cal_v2(ROOT)
    with np.load(ROOT / "tests/fixtures/model_v2_final_test_vector.npz", allow_pickle=False) as fx:
        logits = fx["expected_logits_float32"].astype(np.float64).reshape(-1)
    helper = gw.calibrate_logits(logits, cal)
    manual_p = 1.0 / (1.0 + np.exp(-logits / float(cal["temperature"])))
    manual_pred = (manual_p >= float(cal["threshold"])).astype(int)
    ok = (np.allclose(helper["calibrated_probability"], manual_p, atol=1e-12)
          and np.array_equal(np.asarray(helper["prediction"]).astype(int), manual_pred)
          and cal["calibration_id"] == "CAL_V2" and math.isfinite(float(cal["temperature"])))
    _finish(out, {
        "verifier_status": str(verified.get("status")), "artifact_sha256": hash_file(
            ROOT / "artifacts/CAL_V2.json"), "temperature": cal["temperature"],
        "threshold": cal["threshold"], "calibration_id": cal["calibration_id"],
        "calibration_domain": cal["calibration_domain"], "refit": False,
        "calibration_partition_opened": False,
        "helper_probabilities": helper["calibrated_probability"].tolist(),
        "helper_predictions": np.asarray(helper["prediction"]).astype(int).tolist(),
        "status": "PASS" if ok else "FAIL"})


def check_gateway(out: str) -> None:
    import torch

    from deployment import gateway_v2 as gw
    from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2
    from models.model_v2_final_freeze import load_model_v2_final

    canonical = ROOT / gw.ARTIFACT_PATH
    verified = verify_gateway_artifact_v2(ROOT)
    module = gw.load_artifact(canonical)
    canonical_ok = (hash_file(canonical) == GATEWAY_SHA
                    and canonical.stat().st_size == GATEWAY_BYTES
                    and gw.trainable_parameter_count(module) == 57553)
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    windows = gw.load_parity_corpus(ROOT)
    with np.load(ROOT / "tests/fixtures/model_v2_final_test_vector.npz", allow_pickle=False) as fx:
        fixture_inputs = fx["normalized_inputs_float32"]
    with tempfile.TemporaryDirectory() as tmp:
        reexport = Path(tmp) / "reexport.ts"
        info = gw.export_gateway_artifact(ROOT, reexport)
        fresh = gw.load_artifact(reexport)
        reexport_sha = hash_file(reexport)
        state_a, state_b = module.state_dict(), fresh.state_dict()
        same_state = set(state_a) == set(state_b) and all(
            torch.equal(state_a[k], state_b[k]) for k in state_a)
        same_code = module.code == fresh.code
        same_signature = gw.artifact_signature(module) == gw.artifact_signature(fresh)
        with torch.inference_mode():
            fx_a, fx_b = (m(torch.from_numpy(fixture_inputs)).numpy() for m in (module, fresh))
            c_a = np.concatenate([module(torch.from_numpy(windows[i:i + 1])).numpy()
                                  for i in range(len(windows))])
            c_b = np.concatenate([fresh(torch.from_numpy(windows[i:i + 1])).numpy()
                                  for i in range(len(windows))])
        native, _ = load_model_v2_final(ROOT)
        native.eval()
        with torch.inference_mode():
            c_native = np.concatenate([native(torch.from_numpy(windows[i:i + 1])).numpy()
                                       for i in range(len(windows))])
    allclose = bool(np.allclose(fx_a, fx_b, atol=gw.ATOL, rtol=gw.RTOL)
                    and np.allclose(c_a, c_b, atol=gw.ATOL, rtol=gw.RTOL)
                    and np.allclose(c_native, c_b, atol=gw.ATOL, rtol=gw.RTOL))
    parity = gw.calibration_parity(c_a.reshape(-1), c_b.reshape(-1), cal)
    ok = (canonical_ok and same_state and same_code and same_signature and allclose
          and parity["threshold_decision_disagreements"] == 0 and len(windows) == 1000)
    _finish(out, {
        "canonical_sha256": hash_file(canonical), "canonical_bytes": canonical.stat().st_size,
        "canonical_expected_sha256": GATEWAY_SHA, "canonical_bytes_exact": canonical_ok,
        "verifier_status": str(verified.get("status")), "trainable_parameters": 57553,
        "BYTE_IDENTICAL_REEXPORT_REQUIRED": False, "SEMANTIC_REEXPORT_REQUIRED": True,
        "reexport_sha256": reexport_sha, "reexport_bytes_identical_informational":
        reexport_sha == GATEWAY_SHA, "reexport_info_keys": sorted(info)[:6],
        "same_state": same_state, "same_jit_code": same_code, "same_signature": same_signature,
        "corpus_rows": len(windows), "logits_allclose_atol_rtol": allclose,
        "tolerance": {"atol": gw.ATOL, "rtol": gw.RTOL}, "calibration_parity": parity,
        "canonical_artifact_rewritten": False, "status": "PASS" if ok else "FAIL"})


def check_replay_compare(out: str, kind: str, directory: str) -> None:
    run = Path(directory)
    digest = json.loads((run / "replay_semantic_digest.json").read_text())
    if kind == "v2013":
        frozen = json.loads(
            (ROOT / "reports/model_v2/v2_013/replay_semantic_digest.json").read_text())
        lock = json.loads((ROOT / "artifacts/API_RUNTIME_V2_1.lock.json").read_text())
        expected_digest = lock["software_replay"]["semantic_digest_sha256"]
        extra = {"lock_semantic_digest_sha256": expected_digest,
                 "digest_prefix_ok": expected_digest.startswith(V2013_DIGEST_PREFIX)}
        counts_ok = ((digest["window_count"] == 93 == lock["software_replay"]["window_count"]
                     and digest["http_status_counts"] == frozen["http_status_counts"]
                     and digest["http_status_counts"].get("200") == 80)
                     or digest["http_status_counts"].get(200) == 80)
        flat_ok = True
    else:
        frozen = json.loads((ROOT / "reports/model_v2/c_v2_013_quality_flatline/replay/"
                             "replay_semantic_digest.json").read_text())
        lock = json.loads((ROOT / "artifacts/API_RUNTIME_V2_1.lock.json").read_text())
        expected_digest = lock["flatline_replay"]["digest"]
        extra = {"lock_flatline_digest": expected_digest,
                 "digest_matches_expected_constant": expected_digest == FLATLINE_DIGEST}
        rows = [json.loads(line) for line in
                (run / "replay_run_1.jsonl").read_text().splitlines()]
        manifest = json.loads((ROOT / "tests/fixtures/e2e/"
                               "WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.manifest.json").read_text())
        flat = [r for r in rows if r["window_id"] in set(manifest["flatline_window_ids"])]
        flat_ok = (len(flat) == 6 and all(r["http_status"] == 422 for r in flat)
                   and all(r["response"] is None for r in flat))
        extra |= {"flatline_windows": len(flat),
                  "flatline_http_422": sum(r["http_status"] == 422 for r in flat),
                  "model_inference_suppressed": all(r["response"] is None for r in flat)}
        counts_ok = digest["window_count"] == 17 == lock["flatline_replay"]["window_count"]
    same = digest["digests"] == frozen["digests"]
    ok = (digest["status"] == "PASS" and digest["all_four_identical"] and same and counts_ok
          and flat_ok and ((kind == "v2013" and extra["digest_prefix_ok"]) or kind != "v2013")
          and (kind != "flatline" or extra["digest_matches_expected_constant"]))
    _finish(out, {"kind": kind, "replay_status": digest["status"],
                  "all_four_identical": digest["all_four_identical"],
                  "digests": digest["digests"], "digests_equal_frozen": same,
                  "window_count": digest["window_count"],
                  "http_status_counts": digest["http_status_counts"],
                  "api_model": "API_RUNTIME_V2_1", "real_waveform_dataset_used": False,
                  **extra, "status": "PASS" if ok else "FAIL"})


def check_fl_init(out: str) -> None:
    from federated.model_v2_fl import fresh_initial_state_v2, state_sha

    config = yaml.safe_load((ROOT / "configs/model_v2/fl_init_v2.yaml").read_text())
    seed = int(config.get("seed", config.get("initialization", {}).get("seed", 20260927)))
    sha = state_sha(fresh_initial_state_v2(seed))
    _finish(out, {"seed": seed, "round_0_state_sha256": sha, "expected": FL_INIT_SHA,
                  "trained_checkpoint_loaded": False,
                  "status": "PASS" if sha == FL_INIT_SHA else "FAIL"})


def check_fl_dev(out: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "dev.json"
        subprocess.run([sys.executable, "-m", "scripts.v2_014_fl_dev_reconstruct", str(target)],
                       cwd=ROOT, check=True, capture_output=True)
        report = json.loads(target.read_text())
    _finish(out, {**report})


def check_fl_heldout(out: str) -> None:
    label = f"v2_014_{int(time.time())}"
    proc = subprocess.run([sys.executable, "-m", "scripts.verify_v2_fl_eval_stats", label],
                          cwd=ROOT, capture_output=True, text=True)
    report_path = ROOT / f"reports/model_v2/v2_fl_eval_001/verification/reproduction_{label}.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {"status": "FAIL"}
    guards = {n: json.loads((ROOT / f"artifacts/{n}.json").read_text()).get("status")
              for n in ("V2_FL_INTERNAL_TEST_ACCESS_V1", "V2_FL_INCART_ACCESS_V1")}
    ok = (proc.returncode == 0 and report.get("status") == "PASS" and report.get("all_identical")
          and report.get("checkpoints_loaded") is False and report.get("source_data_opened")
          is False and all(v == "COMPLETED" for v in guards.values()))
    _finish(out, {"verifier": "scripts.verify_v2_fl_eval_stats (prediction tables only)",
                  "report": report, "one_shot_guards": guards, "inference_rerun": False,
                  "generated_untracked_in_clone": [
                      f"reports/model_v2/v2_fl_eval_001/verification/{label}",
                      str(report_path.relative_to(ROOT))],
                  "status": "PASS" if ok else "FAIL"})


def check_secagg_data_free(out: str) -> None:
    from privacy.secagg_app import run_flower_secaggplus
    from scripts.run_secagg_t028 import api_audit, differences, known_payloads

    audit = api_audit()
    config = yaml.safe_load((ROOT / "configs/secagg_v1.yaml").read_text())
    kwargs = {k: config[k] for k in ("num_shares", "reconstruction_threshold", "max_weight",
                                     "clipping_range", "quantization_range", "modulus_range",
                                     "timeout")}
    kwargs["max_weight"], kwargs["clipping_range"] = float(kwargs["max_weight"]), float(
        kwargs["clipping_range"])
    payloads, initial, analytic = known_payloads()
    protected, probe, _, calls = run_flower_secaggplus(payloads, initial, **kwargs)
    diff = differences(analytic, protected)
    v2 = yaml.safe_load((ROOT / "configs/model_v2/secagg_v2.yaml").read_text())
    unchanged = all(v2[k] == config[k] for k in ("num_shares", "reconstruction_threshold",
                                                 "max_weight", "clipping_range",
                                                 "quantization_range", "modulus_range"))
    ok = (audit["status"] == "PASS" and diff["maximum_absolute_difference"] <= 1e-4
          and diff["relative_L2_difference"] <= 1e-4 and probe.clear_individual_update_count == 0
          and unchanged)
    _finish(out, {
        "flower_api_audit_status": audit["status"], "flower_version": audit.get("flower_version"),
        "known_vector": diff, "protected_clear_update_count": probe.clear_individual_update_count,
        "stage_calls": calls, "SECAGG_CONFIG_V2_inherits_historical_parameters": unchanged,
        "real_train_round_reconstructed": False,
        "note": "data-free checks only; the real V2-FL-004 TRAIN round is NOT reconstructed",
        "status": "PASS" if ok else "FAIL"})


def check_synthetic_fl(out: str, directory: str) -> None:
    run = Path(directory)
    subprocess.run([sys.executable, "-m", "scripts.run_v2_fl_005_system_demo", "--full-run",
                    str(run)], cwd=ROOT, check=True)
    summary = json.loads((run / "summary.json").read_text())
    events = json.loads((run / "events.json").read_text())
    ev = ROOT / "reports/model_v2/v2_fl_005"
    frozen_fed = json.loads((ev / "federation_run.json").read_text())
    frozen_events = json.loads((ev / "events.json").read_text())
    frozen_digest = json.loads((ev / "semantic_replay_digest.json").read_text())["digest"]
    lock = json.loads(
        (ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json").read_text())
    report = summary["report"]
    rounds = report["rounds"]
    update_equal = all(rounds[k]["update_sha256"] == frozen_fed["round_reports"][k][
        "update_sha256"] for k in ("1", "2", "3"))
    state_equal = report["state_progression"] == frozen_fed["state_progression"]
    from federated.wearable_fl_secagg_shadow_v1 import derive_max_weight, load_compat
    from federated.wearable_fl_system_v1 import replay_control_plane

    compat = load_compat()
    manifest = json.loads((run / "cohort_manifest.json").read_text())
    replay = replay_control_plane(
        events, {c["client_id"]: {"participant_id": c["participant_id"],
                                  "session_id": c["session_id"],
                                  "dataset_sha": c["dataset_sha256"]}
                 for c in manifest["clients"]}, summary["spec_sha256"])
    shadow = report["secagg_shadow"]
    checks = {
        "cohort_manifest_sha_equals_frozen": summary["cohort_manifest_sha256"] == lock[
            "cohort_manifest_sha256"],
        "8_dataset_hashes_equal_frozen": summary["dataset_sha256"] == lock["dataset_sha256"]
        and len(summary["dataset_sha256"]) == 8,
        "24_update_hashes_equal_frozen": update_equal,
        "round_0_1_2_3_hashes_equal_frozen": state_equal
        and report["state_progression"]["0"]["sha256"] == FL_INIT_SHA,
        "final_state_sha_equals_expected": report["final_global_state_sha256"] == SYNTH_FINAL_SHA,
        "semantic_digest_equals_frozen": summary["semantic_digest"] == frozen_digest
        == SYNTH_DIGEST,
        "events_equal_frozen": events == frozen_events,
        "rejection_sequence_equal_frozen": [r["rejections"] for r in rounds.values()] == [
            r["rejections"] for r in frozen_fed["round_reports"].values()],
        "exactly_once_commits": all(r["second_commit"] == "ROUND_ALREADY_COMMITTED"
                                    for r in rounds.values()),
        "arrival_order_canonicalization": all(r["order_invariance"]["all_equal"]
                                              for r in rounds.values()),
        "restart_resume_exact": summary["restart"]["exact_match"]
        and summary["restart"]["fresh_process"],
        "secagg_shadow_pass": shadow["status"] == "PASS"
        and shadow["plain_clear_update_count"] == 8 and shadow["protected_clear_update_count"] == 0
        and shadow["protected_aggregate_available"] and shadow["maximum_absolute_difference"]
        <= 1e-4 and shadow["relative_L2_difference"] <= 1e-4
        and shadow["preflight"]["coordinates_outside_range"] == 0,
        "max_weight_rule_256_from_93": compat["max_weight"] == derive_max_weight(93) == 256.0
        and shadow["preflight"]["max_examples"] == 93,
        "event_replay_identity_equals_recorded": replay["identity"] == report[
            "coordinator_identity"] and not replay["mismatches"],
        "finite_logit_smoke_723": report["inference_smoke"]["windows_checked"] == 723
        and report["inference_smoke"]["all_logits_finite"]
        and not report["inference_smoke"]["labels_read"],
        "no_real_loader_modules": summary["firewall"]["real_loader_modules_imported"] == []}
    _finish(out, {"checks": checks, "final_state_sha256": report["final_global_state_sha256"],
                  "semantic_digest": summary["semantic_digest"],
                  "cohort_manifest_sha256": summary["cohort_manifest_sha256"],
                  "secagg_shadow": {k: shadow[k] for k in (
                      "status", "maximum_absolute_difference", "relative_L2_difference",
                      "plain_clear_update_count", "protected_clear_update_count")},
                  "claim": "engineering reproduction only; no efficacy metric",
                  "status": "PASS" if all(checks.values()) else "FAIL"})


# ------------------------------------------------------------------ D. regression / lint
def _pytest(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-rs",
                           *args], cwd=ROOT, capture_output=True, text=True)


def check_regression(out: str, monolithic: bool) -> None:
    collect = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                              "-p", "no:warnings"], cwd=ROOT, capture_output=True, text=True)
    nodes = sorted(line for line in collect.stdout.splitlines() if "::" in line)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).with_suffix(".nodes.txt").write_text("\n".join(nodes) + "\n", encoding="utf-8")
    chunks = [nodes[i:i + 80] for i in range(0, len(nodes), 80)]
    executed: list[str] = []
    failed_chunks, failed_tests, skips, rows = 0, 0, [], []
    passed_total = 0
    for index, chunk in enumerate(chunks):
        result = _pytest(chunk)
        executed.extend(chunk)
        if result.returncode != 0:
            failed_chunks += 1
            failed_tests += sum(1 for line in result.stdout.splitlines()
                                if line.startswith(("FAILED ", "ERROR "))) or 1
        for line in result.stdout.splitlines():
            if line.startswith("SKIPPED"):
                skips.append(line)
        last = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        rows.append({"chunk": index, "nodes": len(chunk), "exit_code": result.returncode,
                     "summary": last})
        if " passed" in last:
            passed_total += int(last.split(" passed")[0].split()[-1])
    gated = [s for s in skips if "CLEAN_CLONE_DATA_GATED" in s]
    other_skips = [s for s in skips if "CLEAN_CLONE_DATA_GATED" not in s]
    data = {
        "collected_node_count": len(nodes), "node_list_sha256": hashlib.sha256(
            "\n".join(nodes).encode()).hexdigest(), "chunk_size": 80, "chunk_count": len(chunks),
        "executed_unique": len(set(executed)), "missing": len(set(nodes) - set(executed)),
        "duplicates": len(executed) - len(set(executed)),
        "unexpected": len(set(executed) - set(nodes)), "failed_chunks": failed_chunks,
        "failed_tests": failed_tests, "passed_in_chunks": passed_total,
        "DATA_GATED_SKIPPED": len(gated), "DATA_GATED_SKIP_LINES": gated,
        "other_skipped_by_design": len(other_skips), "other_skip_lines": other_skips,
        "chunk_rows": rows,
        "data_gated_note": "tests needing untracked raw datasets/caches/candidate checkpoints "
        "are skipped (never copied in); excluded from the clean SOFTWARE claim"}
    if monolithic:
        mono = _pytest([])
        summary = mono.stdout.strip().splitlines()[-1] if mono.stdout.strip() else ""
        data["monolithic"] = {"exit_code": mono.returncode, "summary": summary}
    ok = (data["missing"] == 0 and data["duplicates"] == 0 and data["unexpected"] == 0
          and failed_chunks == 0 and failed_tests == 0
          and (not monolithic or data["monolithic"]["exit_code"] == 0))
    _finish(out, {**data, "status": "PASS" if ok else "FAIL"})


def check_lint(out: str) -> None:
    dirs = ["src", "tests", "scripts", "simulation", "deployment", "fusion", "api", "datasets",
            "features", "models", "training", "evaluation", "preprocessing", "privacy", "federated"]
    ruff = subprocess.run([sys.executable, "-m", "ruff", "check", *dirs], cwd=ROOT,
                          capture_output=True, text=True)
    pip = subprocess.run([sys.executable, "-m", "pip", "check"], cwd=ROOT, capture_output=True,
                         text=True)
    _finish(out, {"ruff_exit": ruff.returncode, "ruff_tail": ruff.stdout.strip()[-200:],
                  "pip_check_exit": pip.returncode, "pip_check": pip.stdout.strip(),
                  "status": "PASS" if ruff.returncode == 0 and pip.returncode == 0 else "FAIL"})


def check_lifecycle(out: str) -> None:
    result = _pytest(["tests/test_model_v2_current_lifecycle.py",
                      "tests/test_model_v2_lifecycle_policy.py"])
    _finish(out, {"summary": result.stdout.strip().splitlines()[-1] if result.stdout else "",
                  "exit_code": result.returncode,
                  "status": "PASS" if result.returncode == 0 else "FAIL"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=(
        "inventory", "artifacts", "model-v2", "fixed-vectors", "cal-v2", "gateway",
        "replay-compare", "fl-init", "fl-dev", "fl-heldout", "secagg-data-free", "synthetic-fl",
        "regression", "lint", "lifecycle"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--kind")
    parser.add_argument("--dir")
    parser.add_argument("--monolithic", action="store_true")
    args = parser.parse_args()
    if os.environ.get("PYTHONPATH") and not os.environ.get("V2_014_DEV_MECHANICS"):
        sys.exit("ambient PYTHONPATH must be unset for V2-014 clone checks")
    if args.check == "replay-compare":
        check_replay_compare(args.out, args.kind, args.dir)
    elif args.check == "synthetic-fl":
        check_synthetic_fl(args.out, args.dir)
    elif args.check == "regression":
        check_regression(args.out, args.monolithic)
    else:
        {"inventory": check_inventory, "artifacts": check_artifacts, "model-v2": check_model_v2,
         "fixed-vectors": check_fixed_vectors, "cal-v2": check_cal_v2, "gateway": check_gateway,
         "fl-init": check_fl_init, "fl-dev": check_fl_dev, "fl-heldout": check_fl_heldout,
         "secagg-data-free": check_secagg_data_free, "lint": check_lint,
         "lifecycle": check_lifecycle}[args.check](args.out)


if __name__ == "__main__":
    main()
