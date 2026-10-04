#!/usr/bin/env python3
"""V2-FL-002 method freeze + preflight (before any V2
non-IID outcome). Verifies the committed
V2-FL-001 reference and every frozen manifest/config, audits patient closure and heterogeneity
descriptors, reproduces the frozen feature-noise fixtures (source, SNR, determinism,
round-independence, identity with the T026 fixtures), and writes the V2FLG1 definition inputs,
the FL_NON_IID_MODEL_V2_V1 lock and method_freeze.json. No model is trained and no outcome
exists."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from evaluation.bootstrap import generate_patient_draws
from federated.feature_noise import NOISE_SCHEDULE, mix_noise, noise_offset
from federated.fedavg_runner import normalized_population
from federated.model_v2_non_iid_runner import (
    CONFIG_RELATIVE,
    guarded_noise_bank,
    guarded_population,
    verify_entry,
)
from nhm.hashing import hash_bytes, hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_002"
CONFIG = yaml.safe_load((ROOT / CONFIG_RELATIVE).read_text())
METHOD_FILES = [
    CONFIG_RELATIVE, "federated/model_v2_non_iid_runner.py", "federated/model_v2_fl.py",
    "scripts/freeze_v2_fl_002_method.py", "scripts/run_v2_fl_002.py",
    "scripts/verify_v2_fl_002_replay.py", "scripts/finalize_v2_fl_002_evidence.py",
    "tests/test_v2_fl_002_method.py",
    "federated/feature_noise.py", "federated/non_iid_runner.py", "federated/aggregation.py",
    "federated/model_adapter.py", "federated/local_training.py", "federated/evaluation.py",
    "federated/fedavg_runner.py", "federated/client_manifest.py",
    "federated/validation_group_metrics.py", "models/model_v2_architectures.py",
    "evaluation/bootstrap.py", "configs/fl_non_iid_v1.yaml", "configs/fl_feature_noise_v1.yaml",
    "configs/fl_state_transport_v1.yaml", "configs/model_v2/fl_iid_model_v2_v1.yaml",
    "configs/model_v2/fl_init_v2.yaml", "configs/model_v2/fl_protocol_v1.yaml",
    "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json",
    "manifests/clients/CLIENTS_IID_V1.csv", "manifests/clients/NONIID_LABEL_V1.csv",
    "manifests/clients/NONIID_QUANTITY_V1.csv", "manifests/clients/NONIID_FEATURE_V1.csv",
    "manifests/clients/NONIID_COMBINED_V1.csv", "artifacts/FL_CONFIG_V1.lock.json",
]
PROTECTED = [
    "checkpoints/MODEL_V1.pt", "artifacts/CAL_V1.json", "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
    "manifests/preprocessing/PREPROC_V1.lock.json", "configs/quality_v1.yaml",
    "preprocessing/quality.py", "checkpoints/MODEL_V2_FINAL.pt", "artifacts/CAL_V2.json",
    "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts",
    "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
    "artifacts/API_RUNTIME_V2.lock.json", "artifacts/API_RUNTIME_V2_1.lock.json",
    "artifacts/FL_IID_V1.lock.json", "artifacts/FL_IID_METHOD_V1.lock.json",
    "artifacts/FEDPROX_METHOD_V1.lock.json", "artifacts/FEDPROX_MU_V1.lock.json",
    "artifacts/SECAGG_CONFIG_V1.lock.json", "reports/t026/artifact_hashes.json",
    "reports/t025/fl_iid_rounds.csv", "reports/fl_iid.json",
    "reports/model_v2/v2_fl_001/artifact_hashes.json",
    "reports/model_v2/v2_fl_001/fl_iid_model_v2_result.json",
    "checkpoints/model_v2/v2_fl_001/FL_IID_MODEL_V2_V1_best.pt",
    "checkpoints/model_v2/v2_fl_001/FL_IID_MODEL_V2_V1_round50.pt",
    "reports/model_v2/v2_013/artifact_hashes.json",
    "reports/model_v2/c_v2_013_quality_flatline/artifact_hashes.json",
    "manifests/splits/MITDB_SPLIT_V1.csv", "manifests/labels/AAMI_SVF_MAP_V1.yaml",
]


def _write(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def manifest_audit() -> dict:
    with (ROOT / "manifests/splits/MITDB_SPLIT_V1.csv").open(newline="") as handle:
        split = list(csv.DictReader(handle))
    train_groups = {r["participant_group_id"] for r in split if r["partition"] == "TRAIN"}
    held = {p: {r["participant_group_id"] for r in split if r["partition"] == p}
            for p in ("VALIDATION", "CALIBRATION", "INTERNAL_TEST")}
    with (ROOT / "manifests/clients/CLIENTS_IID_V1.csv").open(newline="") as handle:
        iid = {r["participant_group_id"]: r["site_id"] for r in csv.DictReader(handle)}
    out: dict = {"conditions": {}, "status": "PASS"}
    for key, cond in CONFIG["conditions"].items():
        path = ROOT / "manifests/clients" / f"{cond['manifest']}.csv"
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        patients = [r["participant_group_id"] for r in rows]
        site_counts: dict[str, int] = {}
        site_windows: dict[str, int] = {}
        site_pos: dict[str, int] = {}
        for r in rows:
            s = r["site_id"]
            site_counts[s] = site_counts.get(s, 0) + 1
            site_windows[s] = site_windows.get(s, 0) + int(r["eligible_window_count"])
            site_pos[s] = site_pos.get(s, 0) + int(r["positive_window_count"])
        rates = [site_pos[s] / site_windows[s] for s in sorted(site_pos)]
        entry = {
            "manifest_sha256": hash_file(path), "expected_sha256": cond["manifest_sha256"],
            "regenerated": False, "patient_groups": len(set(patients)),
            "duplicates": len(patients) - len(set(patients)),
            "closure_exact": set(patients) == train_groups and len(patients) == 27,
            "overlap_with_heldout": {p: sorted(set(patients) & v) for p, v in held.items()},
            "site_patient_counts": [site_counts[s] for s in sorted(site_counts)],
            "expected_site_patient_counts_sorted_as_config": cond["site_patient_counts"],
            "site_windows": [site_windows[s] for s in sorted(site_windows)],
            "site_positive_rates": rates, "label_variance_across_sites": float(np.var(rates)),
            "mapping_equals_CLIENTS_IID_V1": {r["participant_group_id"]: r["site_id"]
                                              for r in rows} == iid,
            "windows": sum(site_windows.values()), "positives": sum(site_pos.values())}
        entry["status"] = "PASS" if (
            entry["manifest_sha256"] == entry["expected_sha256"] and entry["closure_exact"]
            and not entry["duplicates"] and not any(entry["overlap_with_heldout"].values())
            and entry["site_patient_counts"] == cond["site_patient_counts"]
            and entry["windows"] == 9660 and entry["positives"] == 3557) else "FAIL"
        if entry["status"] != "PASS":
            out["status"] = "FAIL"
        out["conditions"][key] = entry
    _write("manifest_audit.json", out)
    return out


def noise_verification() -> dict:
    cfg = yaml.safe_load((ROOT / "configs/fl_feature_noise_v1.yaml").read_text())
    train = guarded_population(ROOT, "TRAIN", "preflight_noise_fixtures")
    bank = guarded_noise_bank(ROOT, "preflight_noise_fixtures")
    v1_bank = json.loads((ROOT / "reports/t026/noise_bank_audit.json").read_text())["records"]
    bank_match = {k: hash_bytes(v.tobytes()) == v1_bank[k]["result_sha256"]
                  for k, v in bank.items()}
    clean = normalized_population(train)  # noqa: F841 (shape check of the frozen path)
    waves = np.asarray(train.waveforms, dtype=np.float64)
    index_of = {str(e): i for i, e in enumerate(train.example_ids)}
    per_condition: dict = {}
    ok = all(bank_match.values())
    for key in ("feature", "combined"):
        with (ROOT / "manifests/clients" / f"{CONFIG['conditions'][key]['manifest']}.csv"
              ).open(newline="") as handle:
            site_of_group = {r["participant_group_id"]: r["site_id"]
                             for r in csv.DictReader(handle)}
        v1_fix = {f["site_id"]: f for f in json.loads(
            (ROOT / f"reports/t026/{key}_result.json").read_text())["noise_fixtures"]}
        fixtures = []
        seen = set()
        for example, group in zip(train.example_ids, train.participant_group_ids, strict=True):
            site = site_of_group[str(group)]
            if site in seen:
                continue
            seen.add(site)
            source, target = NOISE_SCHEDULE[site]
            assert cfg["schedule"][site] == {"source": source, "snr_db": target}
            offset = noise_offset(site, str(example), source, bank[source].size)
            window = waves[index_of[str(example)]]
            noisy, achieved = mix_noise(window, bank[source][offset:offset + 2500], target)
            noisy2, achieved2 = mix_noise(
                window, bank[source][noise_offset(site, str(example), source, bank[source].size)
                                     :][:2500], target)  # repeated call (round-independent)
            ref = v1_fix[site]
            fixtures.append({
                "site_id": site, "example_id": str(example), "noise_source": source,
                "target_snr_db": target, "achieved_snr_db": achieved,
                "snr_error_db": abs(achieved - target),
                "within_tolerance_0_05_db": abs(achieved - target) <= cfg["snr_tolerance_db"],
                "offset": offset, "noisy_sha256": hash_bytes(noisy.tobytes()),
                "deterministic_repeat_identical": bool(np.array_equal(noisy, noisy2)
                                                       and achieved == achieved2),
                "round_independent": "noise_offset(site, example, source) has no round argument",
                "identical_to_T026_fixture": (
                    ref["example_id"] == str(example) and ref["offset"] == offset
                    and ref["noisy_sha256"] == hash_bytes(noisy.tobytes()))})
        per_condition[key] = fixtures
        ok &= (len(fixtures) == 8 and all(
            f["within_tolerance_0_05_db"] and f["deterministic_repeat_identical"]
            and f["identical_to_T026_fixture"] for f in fixtures))
    data = {"noise_config_sha256": hash_file(ROOT / "configs/fl_feature_noise_v1.yaml"),
            "nstdb_bank_matches_T026_audit": bank_match, "fixtures": per_condition,
            "nstdb_role": "NSTDB_PURE_NOISE_TRAINING_RESOURCE", "tuned_on_model_output": False,
            "status": "PASS" if ok else "FAIL"}
    _write("noise_verification.json", data)
    return data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entry = verify_entry(ROOT)
    _write("entry_verification.json", entry)
    manifests = manifest_audit()
    noise = noise_verification()
    patients = [f"P{i}" for i in range(7)]
    _, draws = generate_patient_draws(np.asarray(patients), 2000, 20260927)
    bootstrap = {"B": 2000, "seed": 20260927, "validation_patient_groups": 7,
                 "draw_matrix_sha256": hash_bytes(draws.tobytes()),
                 "note": "deterministic draws (PCG64) over the 7 sorted VALIDATION groups; "
                         "identical to the V2-FL-001 draws by construction"}
    _write("bootstrap_draws_pin.json", bootstrap)
    audits = {"entry": entry["status"], "manifests": manifests["status"], "noise": noise["status"]}
    if set(audits.values()) != {"PASS"}:
        sys.exit(f"V2_FL_002_PREFLIGHT_FAILED:{audits}")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    (OUT / "protected_baseline.json").write_text(json.dumps(
        {"artifacts": {p: hash_file(ROOT / p) for p in PROTECTED}}, indent=2,
        sort_keys=True) + "\n", encoding="utf-8")
    lock = {
        "lock_id": "FL_NON_IID_MODEL_V2_V1", "status": "FROZEN_BEFORE_FIRST_V2_NON_IID_OUTCOME",
        "owner_task": "V2-FL-002", "gate": "V2FLG1",
        "bound_artifacts": {p: hash_file(ROOT / p) for p in METHOD_FILES},
        "run_order": CONFIG["run_order"], "conditions": {
            k: {"experiment_id": v["experiment_id"], "manifest_sha256": v["manifest_sha256"]}
            for k, v in CONFIG["conditions"].items()},
        "change_control": "Any change requires a successor; no retuning after results."}
    lock_path = ROOT / "manifests/model_v2/FL_NON_IID_MODEL_V2_V1.lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write("method_freeze.json", {
        "owner_task": "V2-FL-002", "family": "FL_NON_IID_MODEL_V2_V1", "entry_head": head,
        "lock_sha256": hash_file(lock_path), "method_file_sha256": {
            p: hash_file(ROOT / p) for p in METHOD_FILES},
        "real_outcome_exists_at_method_freeze": False, "preflight": audits,
        "bootstrap_draws_pin_sha256": bootstrap["draw_matrix_sha256"],
        "run_order": CONFIG["run_order"], "status": "PASS"})
    print("V2-FL-002 method frozen at", head)


if __name__ == "__main__":
    main()
